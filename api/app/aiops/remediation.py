"""Ações no cluster. Lista fechada, validada duas vezes: ao propor e ao executar.

O que é permitido vem do runbook do alerta (`runbooks.allowed_actions`), nunca do
texto do LLM. Toda execução passa pelo `ActionBudget` e termina com verificação
do rollout, que vai para a thread do incidente.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import UTC, datetime

from app.aiops.config import AiopsSettings, get_aiops_settings
from app.aiops.models import ActionKind, Incident, ProposedAction
from app.aiops.runbooks import allowed_actions
from app.aiops.sources import Kubernetes, SourceError, _annotation, image_of
from app.aiops.store import ActionBudget
from app.core.logging import get_logger

log = get_logger(__name__)

_REVISION = "deployment.kubernetes.io/revision"


class Remediator:
    def __init__(
        self,
        kube: Kubernetes,
        budget: ActionBudget,
        settings: AiopsSettings | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.kube = kube
        self.budget = budget
        self.settings = settings or get_aiops_settings()
        self.sleep = sleep

    @property
    def ns(self) -> str:
        return self.settings.aiops_namespace

    def validate(self, action: ProposedAction, incident: Incident) -> str | None:
        """None se a ação pode rodar; senão, o motivo em português."""
        if action.deployment != incident.deployment:
            return f"a ação é em {action.deployment}, mas o incidente é de {incident.deployment}"
        restoring = action.kind == ActionKind.SCALE and action.replicas == 1
        allowed = allowed_actions(incident.alert_names, incident.deployment)
        if action.kind not in allowed and not restoring:
            return f"{action.kind} não está no runbook de {', '.join(incident.alert_names)}"
        if refusal := self.budget.check(action.deployment):
            return refusal
        try:
            if action.kind == ActionKind.SCALE:
                current = self.kube.deployment(self.ns, action.deployment)["spec"].get(
                    "replicas", 1
                )
                # Sem pod o HPA de CPU não tem série e não sobe. 0 → 1 repõe o mínimo.
                if action.deployment in self.kube.hpa_targets(self.ns) and not (
                    action.replicas == 1 and current < 1
                ):
                    return f"{action.deployment} tem HPA; o scale manual seria desfeito"
                if action.replicas is None or action.replicas <= current:
                    return f"scale precisa de mais de {current} réplicas"
                if action.replicas > self.settings.aiops_max_replicas:
                    return f"o teto é {self.settings.aiops_max_replicas} réplicas"
            if (
                action.kind == ActionKind.ROLLBACK
                and self._previous_template(action.deployment) is None
            ):
                return "não há revisão anterior para voltar"
        except SourceError as exc:
            return str(exc)
        return None

    def execute(self, action: ProposedAction, actor: str) -> str:
        log.info(
            "aiops.action",
            kind=action.kind,
            deployment=action.deployment,
            actor=actor,
            dry_run=self.settings.aiops_dry_run,
        )
        if self.settings.aiops_dry_run:
            return f"dry-run: {action.label()} não foi aplicado"
        if action.kind == ActionKind.RESTART:
            stamp = datetime.now(UTC).isoformat()
            self.kube.patch_deployment(
                self.ns,
                action.deployment,
                {
                    "spec": {
                        "template": {
                            "metadata": {
                                "annotations": {
                                    "kubectl.kubernetes.io/restartedAt": stamp,
                                    "aiops/actor": actor,
                                }
                            }
                        }
                    }
                },
            )
            result = f"rollout restart de {action.deployment}"
        elif action.kind == ActionKind.SCALE:
            self.kube.patch_deployment(
                self.ns, action.deployment, {"spec": {"replicas": action.replicas}}
            )
            result = f"{action.deployment} escalado para {action.replicas} réplicas"
        else:
            previous = self._previous_template(action.deployment)
            if previous is None:
                raise SourceError("não há revisão anterior para voltar")
            revision, template = previous
            self.kube.replace_template(self.ns, action.deployment, template)
            image = image_of({"spec": {"template": template}})
            result = f"rollback de {action.deployment} para a revisão {revision} ({image})"
        self.budget.spend(action.deployment)
        return result

    def verify(self, deployment: str) -> tuple[bool, str]:
        """Espera o rollout ficar disponível. (ok, texto para a thread)."""
        if self.settings.aiops_dry_run:
            return True, "dry-run: sem verificação"
        deadline = time.monotonic() + self.settings.aiops_verify_seconds
        status_text = "sem status"
        while time.monotonic() < deadline:
            try:
                dep = self.kube.deployment(self.ns, deployment)
            except SourceError as exc:
                status_text = str(exc)
                self.sleep(5)
                continue
            spec, status = dep.get("spec", {}), dep.get("status", {})
            want = spec.get("replicas", 1)
            if want < 1:
                return False, f"{deployment} continua com 0 réplicas; o serviço não voltou"
            updated, available = (
                status.get("updatedReplicas", 0),
                status.get("availableReplicas", 0),
            )
            status_text = f"{available}/{want} disponíveis, {updated} atualizadas"
            done = (
                status.get("observedGeneration", 0) >= dep["metadata"].get("generation", 0)
                and updated == want
                and available == want
                and status.get("replicas", 0) == want
            )
            if done:
                return True, f"rollout concluído: {status_text}"
            self.sleep(5)
        return (
            False,
            f"rollout não concluiu em {self.settings.aiops_verify_seconds}s: {status_text}",
        )

    def _previous_template(self, deployment: str) -> tuple[str, dict] | None:
        current = _annotation(self.kube.deployment(self.ns, deployment), _REVISION)
        older = [
            rs
            for rs in self.kube.replicasets(self.ns, deployment)
            if int(_annotation(rs, _REVISION) or 0) < int(current or 0)
        ]
        if not older:
            return None
        rs = older[-1]
        template = rs["spec"]["template"]
        labels = dict(template.get("metadata", {}).get("labels") or {})
        labels.pop("pod-template-hash", None)
        template = {**template, "metadata": {**template.get("metadata", {}), "labels": labels}}
        return _annotation(rs, _REVISION) or "?", template
