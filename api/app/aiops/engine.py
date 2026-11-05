"""Ciclo de vida do incidente: detectar → correlacionar → diagnosticar → notificar →
remediar com aprovação → verificar → postmortem.

Todo trabalho lento roda no pool: o webhook do Alertmanager e o ack do Slack
respondem na hora.
"""

from __future__ import annotations

import re
import time
from concurrent.futures import Executor, ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

from prometheus_client import Counter, Histogram

from app.aiops import diagnose as dx
from app.aiops.config import AiopsSettings, get_aiops_settings
from app.aiops.models import Alert, AlertmanagerPayload, Incident, ProposedAction
from app.aiops.remediation import Remediator
from app.aiops.runbooks import MANAGED, correlation_key, deployment_of
from app.aiops.slack import (
    DISMISS,
    EXECUTE,
    REINVESTIGATE,
    SlackClient,
    fallback_text,
    incident_blocks,
    parse_action_value,
)
from app.aiops.sources import SourceError
from app.aiops.store import ActionBudget, IncidentStore
from app.core.logging import get_logger

log = get_logger(__name__)

ALERTS = Counter(
    "aiops_alerts_total", "Alertas recebidos do Alertmanager.", ["alertname", "status"]
)
INCIDENTS = Counter("aiops_incidents_total", "Incidentes abertos.", ["severity"])
ACTIONS = Counter("aiops_actions_total", "Ações de remediação.", ["kind", "result", "mode"])
DIAGNOSES = Counter("aiops_diagnoses_total", "Diagnósticos por confiança.", ["confidence"])
RESOLVE = Histogram(
    "aiops_time_to_resolve_seconds",
    "Abertura até resolução (MTTR).",
    buckets=(60, 300, 600, 1800, 3600, 7200, 21600),
)

_MENTION = re.compile(r"<@[A-Z0-9]+>\s*")


class Engine:
    def __init__(
        self,
        settings: AiopsSettings | None = None,
        sources: dx.Sources | None = None,
        slack: SlackClient | None = None,
        pool: Executor | None = None,
    ) -> None:
        self.settings = settings or get_aiops_settings()
        self.sources = sources or dx.Sources()
        self.slack = slack or SlackClient(self.settings)
        self.store = IncidentStore()
        self.budget = ActionBudget(
            self.settings.aiops_cooldown_seconds, self.settings.aiops_max_actions_per_hour
        )
        self.remediator = Remediator(self.sources.kube, self.budget, self.settings)
        self.pool = pool or ThreadPoolExecutor(max_workers=4, thread_name_prefix="aiops")
        self._down_since: dict[str, float] = {}
        self._down_alerted: set[str] = set()

    def _submit(self, fn, *args) -> None:  # noqa: ANN001
        def run() -> None:
            try:
                fn(*args)
            except Exception:  # noqa: BLE001
                log.exception("aiops.task_failed", task=getattr(fn, "__name__", "?"))

        self.pool.submit(run)

    def watch_once(self, now: float | None = None) -> list[str]:
        """Abre incidente 10s depois de ver o deployment sem réplica disponível.

        Lê a API do Kubernetes, não o kube-state-metrics (scrape de dezenas de
        segundos). Enquanto continuar fora, não abre de novo.
        """
        now = time.monotonic() if now is None else now
        kube = self.sources.kube
        if not getattr(kube, "enabled", False):
            return []
        try:
            items = kube.deployments(self.settings.aiops_namespace)
        except SourceError as exc:
            log.warning("aiops.watch_failed", error=str(exc))
            return []
        opened: list[str] = []
        down_now: set[str] = set()
        for item in items:
            name = item.get("metadata", {}).get("name", "")
            if name not in MANAGED:
                continue
            spec = item.get("spec", {}).get("replicas", 1)
            available = item.get("status", {}).get("availableReplicas") or 0
            if spec >= 1 and available >= 1:
                continue
            down_now.add(name)
            first = self._down_since.setdefault(name, now)
            if now - first < 10 or name in self._down_alerted:
                continue
            if any(inc.deployment == name for inc in self.store.open_incidents()):
                self._down_alerted.add(name)
                continue
            self.handle_alerts(
                AlertmanagerPayload(
                    receiver="aiops-watch",
                    alerts=[self._unavailable_alert(name, spec)],
                )
            )
            self._down_alerted.add(name)
            opened.append(name)
        for name in list(self._down_since):
            if name not in down_now:
                self._down_since.pop(name, None)
                self._down_alerted.discard(name)
        return opened

    def _unavailable_alert(self, name: str, spec: int) -> Alert:
        if spec < 1:
            return Alert(
                status="firing",
                labels={
                    "alertname": "DeploymentSemReplica",
                    "deployment": name,
                    "namespace": self.settings.aiops_namespace,
                    "severity": "critical",
                },
                annotations={"summary": f"{name} com 0 réplicas"},
                startsAt=datetime.now(UTC),
                fingerprint=f"watch:{name}:zero",
            )
        return Alert(
            status="firing",
            labels={
                "alertname": "AplicacaoIndisponivel",
                "deployment": name,
                "namespace": self.settings.aiops_namespace,
                "severity": "critical",
            },
            annotations={"summary": f"{name} sem réplica disponível"},
            startsAt=datetime.now(UTC),
            fingerprint=f"watch:{name}:unavailable",
        )

    # Alertmanager -----------------------------------------------------------

    def handle_alerts(self, payload: AlertmanagerPayload) -> dict:
        ns = self.settings.aiops_namespace
        touched: dict[str, list] = {}
        for alert in payload.alerts:
            ALERTS.labels(alert.name, alert.status).inc()
            key = correlation_key(alert, ns)
            incident, created, new_signal = self.store.ingest(
                key, alert, lambda a=alert, k=key: self._new(a, k)
            )
            if incident is None:
                continue
            state = touched.setdefault(key, [incident, False, False])
            state[1] |= created
            state[2] |= new_signal
        for incident, created, new_signal in touched.values():
            if created:
                INCIDENTS.labels(incident.severity).inc()
                self._submit(self._open, incident)
            elif self.store.close_if_clear(incident):
                self._submit(self._resolve, incident)
            elif new_signal:
                self._submit(self._correlated, incident)
        return {"incidentes": [i.id for i, _, _ in touched.values()]}

    def _new(self, alert: Alert, key: str) -> Incident:
        dep = deployment_of(alert, self.settings.aiops_namespace)
        return Incident(key=key, title=f"{alert.summary}", severity=alert.severity, deployment=dep)

    def _open(self, incident: Incident) -> None:
        channel, ts = self.slack.post(
            fallback_text(incident), blocks=incident_blocks(incident, self.settings)
        )
        incident.slack_channel, incident.slack_ts = channel, ts
        self._diagnose(incident)

    def _correlated(self, incident: Incident) -> None:
        self._thread(
            incident, f":link: Alerta correlacionado: {', '.join(a.name for a in incident.firing)}"
        )
        self._diagnose(incident)

    def _diagnose(self, incident: Incident) -> None:
        evidence = dx.collect_evidence(incident, self.sources)
        diag = dx.diagnose(incident, evidence)
        if diag.action and (refusal := self.remediator.validate(diag.action, incident)):
            diag.next_steps.append(f"{diag.action.label()} não oferecida: {refusal}")
            diag.action = None
        incident.diagnosis = diag
        incident.note(f"diagnóstico ({diag.confidence}): {diag.probable_cause[:120]}")
        DIAGNOSES.labels(diag.confidence).inc()
        self._refresh(incident)
        self._thread(incident, f"*Evidências coletadas*\n```{evidence.render(2800)}```")
        if diag.action and diag.action.kind in self.settings.aiops_auto_actions:
            self._run_action(incident, diag.action, actor="aiops:auto", mode="auto")

    def _resolve(self, incident: Incident) -> None:
        RESOLVE.observe((incident.resolved_at - incident.opened_at).total_seconds())
        self._announce_resolved(incident, incident.taken_action, "")

    # Remediação -------------------------------------------------------------

    def _run_action(
        self, incident: Incident, action: ProposedAction, actor: str, mode: str
    ) -> None:
        if incident.status == "resolvido":
            self._thread(incident, "Incidente já resolvido. Nada a executar.")
            return
        if refusal := self.remediator.validate(action, incident):
            ACTIONS.labels(action.kind, "recusada", mode).inc()
            self._thread(incident, f":no_entry: {action.label()} recusada: {refusal}")
            return
        incident.status = "mitigando"
        incident.note(f"{action.label()} por {actor}")
        self._refresh(incident)
        self._thread(incident, f":gear: Agente resolutor executando: {action.label()}.")
        try:
            result = self.remediator.execute(action, actor)
        except SourceError as exc:
            ACTIONS.labels(action.kind, "erro", mode).inc()
            incident.status = "aberto"
            self._refresh(incident)
            self._thread(incident, f":x: {action.label()} falhou: {exc}")
            return
        ok, detail = self.remediator.verify(action.deployment)
        ACTIONS.labels(action.kind, "ok" if ok else "nao_verificada", mode).inc()
        incident.note(detail)
        if not ok or self.settings.aiops_dry_run:
            if incident.status != "resolvido":
                incident.status = "mitigando" if ok else "aberto"
            self._refresh(incident)
            self._thread(incident, f":warning: {result}. {detail}")
            return
        silence = self._silence(incident)
        self.store.resolve(incident, f"resolvido por {action.label()}")
        RESOLVE.observe((incident.resolved_at - incident.opened_at).total_seconds())
        self._announce_resolved(incident, action, f"{result}. {detail}.{silence}")

    def _announce_resolved(
        self, incident: Incident, action: ProposedAction | None, detail: str
    ) -> None:
        """Card e thread: status resolvido, a ação que rodou e o postmortem."""
        incident.taken_action = action
        incident.postmortem = dx.postmortem(incident)
        self._refresh(incident)
        taken = (
            action.label()
            if action
            else "Nenhuma ação do agente. Os alertas deixaram de disparar."
        )
        lines = [":white_check_mark: *Status:* Resolvido", f"*Ação tomada:* {taken}"]
        if detail:
            lines.append(detail)
        lines.append(f"*Postmortem*\n{incident.postmortem}")
        self._thread(incident, "\n".join(lines))

    def _silence(self, incident: Incident) -> str:
        """Evita o mesmo alerta reabrir o incidente enquanto a correção assenta."""
        import httpx

        now = datetime.now(UTC)
        ends = now + timedelta(hours=2)
        url = self.settings.aiops_alertmanager_url.rstrip("/") + "/api/v2/silences"
        failed = False
        for alert in incident.firing:
            matchers = [
                {"name": "alertname", "value": alert.name, "isRegex": False, "isEqual": True}
            ]
            for key in ("service", "namespace", "pod", "queue_name"):
                if value := alert.labels.get(key):
                    matchers.append(
                        {"name": key, "value": value, "isRegex": False, "isEqual": True}
                    )
            body = {
                "matchers": matchers,
                "startsAt": now.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                "endsAt": ends.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                "createdBy": "aiops-resolutor",
                "comment": f"incidente {incident.id} resolvido por ação aceita",
            }
            try:
                resp = httpx.post(url, json=body, timeout=httpx.Timeout(3.0, connect=1.0))
                resp.raise_for_status()
            except httpx.HTTPError:
                failed = True
                log.warning("aiops.silence_failed", incident=incident.id, alert=alert.name)
        if failed:
            return " O alerta não foi silenciado e pode reabrir."
        return ""

    # Slack ------------------------------------------------------------------

    def dispatch(self, kind: str, payload: dict) -> dict | None:
        """Entrada única do Slack (Socket Mode ou HTTP). Devolve o corpo do ack."""
        if kind == "events_api":
            event = payload.get("event", {})
            if event.get("type") == "app_mention" and not event.get("bot_id"):
                question = _MENTION.sub("", event.get("text", "")).strip()
                self._submit(
                    self._answer, question, event["channel"], event.get("thread_ts") or event["ts"]
                )
            return None
        if kind == "interactive" and payload.get("type") == "block_actions":
            self._submit(self._interaction, payload)
            return None
        if kind == "slash_commands":
            return self._command(payload)
        return None

    def _authorized(self, user_id: str) -> bool:
        return not self.settings.slack_approvers or user_id in self.settings.slack_approvers

    def _interaction(self, payload: dict) -> None:
        user = payload.get("user", {})
        actor = f"slack:{user.get('username') or user.get('id')}"
        for action in payload.get("actions", []):
            action_id = action.get("action_id")
            if action_id == EXECUTE:
                incident_id, proposed = parse_action_value(action["value"])
                incident = self.store.get(incident_id)
                if incident is None:
                    continue
                if not self._authorized(user.get("id", "")):
                    self._thread(
                        incident, f":lock: <@{user.get('id')}> não está em SLACK_APPROVERS."
                    )
                    continue
                self._run_action(incident, proposed, actor=actor, mode="aprovada")
            elif action_id == REINVESTIGATE and (incident := self.store.get(action["value"])):
                self._thread(incident, f":mag: Reinvestigando a pedido de {actor}…")
                self._diagnose(incident)
            elif action_id == DISMISS and (incident := self.store.get(action["value"])):
                incident.note(f"{actor} assumiu")
                if incident.diagnosis:
                    incident.diagnosis.action = None
                self._refresh(incident)
                self._thread(
                    incident,
                    f":handshake: <@{user.get('id')}> assumiu o incidente. "
                    "Ações do AIOps desligadas aqui.",
                )

    def _answer(self, question: str, channel: str, thread_ts: str) -> None:
        if not question or question.lower() in {"status", "saúde", "saude"}:
            text = dx.status_report(self.sources, self.store.open_incidents)
        else:
            text = dx.investigate(question, self.sources, self.store.open_incidents)
        self.slack.post(text, thread_ts=thread_ts, channel=channel)

    def _command(self, payload: dict) -> dict:
        text = (payload.get("text") or "").strip()
        channel = payload.get("channel_id") or self.settings.slack_channel
        if text in {"", "status"}:
            self._submit(self._answer, "status", channel, None)
            return {"response_type": "ephemeral", "text": ":mag: Coletando o status…"}
        if text in {"incidentes", "incidents"}:
            rows = [
                f"• `{i.id}` {i.deployment}: {', '.join(i.alert_names)} "
                f"({i.status}, {i.duration()})"
                for i in self.store.open_incidents()
            ]
            return {
                "response_type": "ephemeral",
                "text": "\n".join(rows) or "Nenhum incidente aberto.",
            }
        self._submit(self._answer, text, channel, None)
        return {"response_type": "in_channel", "text": f":mag: Investigando: _{text}_"}

    # Saída ------------------------------------------------------------------

    def _refresh(self, incident: Incident) -> None:
        if incident.slack_channel and incident.slack_ts:
            self.slack.update(
                incident.slack_channel,
                incident.slack_ts,
                fallback_text(incident),
                incident_blocks(incident, self.settings),
            )

    def _thread(self, incident: Incident, text: str) -> None:
        self.slack.post(text, thread_ts=incident.slack_ts, channel=incident.slack_channel)

    def shutdown(self) -> None:
        self.pool.shutdown(wait=False, cancel_futures=True)
