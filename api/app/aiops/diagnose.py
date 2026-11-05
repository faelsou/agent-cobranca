"""Coleta de evidências, análise de causa e investigação sob demanda.

1. Evidência determinística: métricas do runbook, pods, eventos, histórico de
   rollout (mudança recente é a causa mais comum) e logs de erro.
2. O LLM lê só essas evidências e devolve um `Diagnosis` estruturado.
3. A ação proposta é filtrada pela lista do runbook. Sem LLM, a heurística do
   runbook responde no lugar.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool

from app.aiops.config import get_aiops_settings
from app.aiops.models import ActionKind, Diagnosis, Incident, ProposedAction
from app.aiops.runbooks import MANAGED, allowed_actions, queries_for, runbook_for
from app.aiops.sources import (
    Kubernetes,
    Loki,
    Prometheus,
    SourceError,
    pod_status,
    rollout_history,
)
from app.aiops.specialists import (
    SRE_PROMPT,
    consult_evidence,
    render_reports,
    route_incident,
    route_question,
)
from app.aiops.specialists import (
    investigate_with as consult_question,
)
from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)

RECENT_DEPLOY = timedelta(minutes=60)

SYSTEM = SRE_PROMPT


@dataclass
class Evidence:
    sections: dict[str, str] = field(default_factory=dict)
    replicas: int | None = None
    available: int | None = None
    hpa: bool = False
    event_lines: list[str] = field(default_factory=list)
    recent_deploy: str | None = None
    failed_sources: list[str] = field(default_factory=list)

    def render(self, max_chars: int = 9000) -> str:
        text = "\n\n".join(f"## {k}\n{v}" for k, v in self.sections.items() if v)
        return text[:max_chars]


class Sources:
    def __init__(
        self,
        prom: Prometheus | None = None,
        loki: Loki | None = None,
        kube: Kubernetes | None = None,
    ) -> None:
        self.prom = prom or Prometheus()
        self.loki = loki or Loki()
        self.kube = kube or Kubernetes()


def collect_evidence(incident: Incident, src: Sources) -> Evidence:
    ns = get_aiops_settings().aiops_namespace
    dep = incident.deployment
    ev = Evidence()
    ev.sections["Alertas"] = "\n".join(
        f"- [{a.status}] {a.name} ({a.severity}): {a.summary} desde {a.startsAt:%H:%M}Z"
        if a.startsAt
        else f"- [{a.status}] {a.name}: {a.summary}"
        for a in incident.alerts.values()
    )
    queries = {q for name in incident.alert_names for q in queries_for(name, dep, ns)}

    def metrics() -> str:
        out = []
        for q in sorted(queries):
            try:
                out.append(f"`{q}`\n{src.prom.summarize(q)}")
            except SourceError as exc:
                ev.failed_sources.append(str(exc))
                return f"{exc}"
        return "\n".join(out)

    def workload() -> dict[str, str]:
        if dep is None:
            return {}
        sections: dict[str, str] = {}
        try:
            deploy = src.kube.deployment(ns, dep)
            ev.replicas = deploy.get("spec", {}).get("replicas", 1)
            ev.available = deploy.get("status", {}).get("availableReplicas") or 0
            ev.hpa = dep in src.kube.hpa_targets(ns)
            pods = src.kube.pods(ns, dep)
            sections["Pods"] = "\n".join(pod_status(p) for p in pods) or "nenhum pod"
            ev.event_lines = src.kube.events(ns, dep)
            sections["Eventos"] = "\n".join(ev.event_lines) or "sem eventos"
            rs = src.kube.replicasets(ns, dep)
            sections["Rollouts"] = "\n".join(rollout_history(rs))
            if rs:
                created = datetime.fromisoformat(
                    rs[-1]["metadata"]["creationTimestamp"].replace("Z", "+00:00")
                )
                gap = incident.opened_at - created
                if gap < RECENT_DEPLOY and len(rs) > 1:
                    minutes = int(gap.total_seconds() // 60)
                    ev.recent_deploy = f"rollout novo de {dep} {minutes} min antes do incidente"
            crashed = [
                p
                for p in pods
                if any(
                    cs.get("lastState", {}).get("terminated")
                    for cs in p.get("status", {}).get("containerStatuses", [])
                )
            ]
            if crashed:
                name = crashed[0]["metadata"]["name"]
                sections["Log do container anterior"] = "\n".join(
                    src.kube.pod_logs(ns, name, previous=True, tail=25)
                )
        except SourceError as exc:
            ev.failed_sources.append(str(exc))
            sections["Kubernetes"] = str(exc)
        return sections

    def logs() -> str:
        if dep is None:
            return ""
        log_filter = runbook_for(incident.alert_names[0]).log_filter
        logql = f'{{namespace="{ns}", service="{dep}"}} {log_filter}'
        try:
            return (
                "\n".join(src.loki.tail(logql, minutes=15, limit=25))
                or "sem erro nos últimos 15 min"
            )
        except SourceError as exc:
            ev.failed_sources.append(str(exc))
            return str(exc)

    with ThreadPoolExecutor(max_workers=3) as pool:
        f_metrics, f_work, f_logs = pool.submit(metrics), pool.submit(workload), pool.submit(logs)
        ev.sections["Métricas"] = f_metrics.result()
        ev.sections.update(f_work.result())
        ev.sections["Logs de erro (Loki, 15 min)"] = f_logs.result()
    if ev.recent_deploy:
        ev.sections["Mudança recente"] = ev.recent_deploy
    return ev


def _llm_enabled() -> bool:
    return bool(get_settings().llm_api_key)


def _sanitize(diag: Diagnosis, incident: Incident, ev: Evidence) -> Diagnosis:
    allowed = allowed_actions(incident.alert_names, incident.deployment)
    action = diag.action
    if action is not None:
        if action.kind not in allowed or action.deployment != incident.deployment:
            diag.next_steps.append(
                f"A IA sugeriu {action.label()}, fora do runbook. Avaliar manualmente."
            )
            action = None
        elif action.kind == ActionKind.SCALE and action.replicas is None:
            action.replicas = (ev.replicas or 1) + 1
    diag.action = action
    return diag


def suggest_action(incident: Incident, ev: Evidence) -> ProposedAction | None:
    """Ação do runbook quando o diagnóstico não escolheu uma. Deploy recente pede rollback."""
    allowed = allowed_actions(incident.alert_names, incident.deployment)
    dep = incident.deployment
    if dep not in MANAGED:
        return None
    if ev.replicas == 0:
        return ProposedAction(
            kind=ActionKind.SCALE,
            deployment=dep,
            replicas=1,
            reason="deployment com 0 réplicas; restart não cria pod",
        )
    if ev.recent_deploy and ActionKind.ROLLBACK in allowed:
        return ProposedAction(kind=ActionKind.ROLLBACK, deployment=dep, reason=ev.recent_deploy)
    if ActionKind.RESTART in allowed:
        return ProposedAction(kind=ActionKind.RESTART, deployment=dep, reason="runbook")
    if ActionKind.SCALE in allowed:
        return ProposedAction(
            kind=ActionKind.SCALE,
            deployment=dep,
            replicas=(ev.replicas or 1) + 1,
            reason="runbook",
        )
    return None


def ensure_action(diag: Diagnosis, incident: Incident, ev: Evidence) -> Diagnosis:
    """Garante uma ação sugerida sempre que o runbook permite."""
    if diag.action is None:
        diag.action = suggest_action(incident, ev)
    return diag


def specialist_troubleshooting(incident: Incident, ev: Evidence) -> Diagnosis | None:
    """Indisponibilidade fechada por evidência. A ação do botão é esta, não a do LLM.

    Com 0 réplicas pedidas não existe pod: restart não cura, e o HPA de CPU não sobe
    porque não há métrica. Com réplicas pedidas e nenhuma disponível, a causa é o pod
    que não ficou Ready.
    """
    dep = incident.deployment
    if dep not in MANAGED:
        return None
    if ev.replicas != 0 and not (ev.available == 0 and ev.replicas):
        return None
    events = [line for line in ev.event_lines[:2] if line]
    if ev.replicas == 0:
        hpa = (
            f"`{dep}` tem HPA. Sem pod a utilização de CPU não existe, então o HPA não sobe "
            "sozinho. Escalar para 1 repõe o mínimo e o HPA volta a controlar."
            if ev.hpa
            else f"`{dep}` não tem HPA. A réplica permanece em 1."
        )
        facts = [
            f"Kubernetes: spec.replicas=0 e availableReplicas={ev.available or 0}. "
            "O Service fica sem endpoint.",
            "Restart não cria pod: o ReplicaSet continua com desired=0.",
            hpa,
            "Engenharia: quem chama este serviço recebe falha de upstream. "
            "Não é regressão de código.",
        ]
        return Diagnosis(
            summary=f"{dep} indisponível: nenhuma réplica ativa",
            probable_cause=(
                f"O spec de `{dep}` está em 0. Não há processo para a readinessProbe nem para "
                "receber tráfego, e o scrape de /internal/metrics some."
            ),
            confidence="alta",
            evidence=[*facts, *events],
            next_steps=[
                f"Aceitar e resolver escala `{dep}` para 1 réplica.",
                "O incidente só fecha quando 1 pod estiver disponível.",
            ],
            action=ProposedAction(
                kind=ActionKind.SCALE,
                deployment=dep,
                replicas=1,
                reason="spec em 0; sem pod não há serviço",
            ),
            specialists=["sre", "kubernetes", "software"],
        )
    allowed = allowed_actions(incident.alert_names, dep)
    if ev.recent_deploy and ActionKind.ROLLBACK in allowed:
        action = ProposedAction(
            kind=ActionKind.ROLLBACK, deployment=dep, reason=ev.recent_deploy
        )
        correction = (
            "Aceitar e resolver volta a revisão anterior. A migração de banco não é desfeita."
        )
        cause = f"Nenhuma réplica disponível logo após mudança: {ev.recent_deploy}."
    elif ActionKind.RESTART in allowed:
        action = ProposedAction(
            kind=ActionKind.RESTART,
            deployment=dep,
            reason="réplicas pedidas, nenhuma Ready",
        )
        correction = (
            "Aceitar e resolver recria o pod. Sem rollout novo, a imagem atual continua."
        )
        cause = (
            f"`{dep}` pede {ev.replicas} réplica(s) e tem 0 disponíveis. "
            "O pod não passou na readiness."
        )
    else:
        return None
    return Diagnosis(
        summary=f"{dep} indisponível: nenhum pod Ready",
        probable_cause=cause,
        confidence="alta" if ev.recent_deploy or events else "media",
        evidence=[
            f"Kubernetes: spec.replicas={ev.replicas}, availableReplicas=0.",
            *events,
            "Engenharia: o processo não está servindo. 5xx e alvo fora são sintoma.",
        ],
        next_steps=[
            correction,
            "Se o pod novo não ficar Ready, o evento e o log do container dizem o porquê.",
        ],
        action=action,
        specialists=["sre", "kubernetes", "software"],
    )


def heuristic(incident: Incident, ev: Evidence) -> Diagnosis:
    """Diagnóstico sem LLM: o runbook do alerta mais grave e a regra 'mudou, volta'."""
    names = incident.alert_names
    hints = [runbook_for(n).hint for n in names]
    dep = incident.deployment
    action = suggest_action(incident, ev)
    evidence = [s for s in [ev.recent_deploy, *ev.failed_sources] if s]
    return Diagnosis(
        summary=f"{', '.join(names)} em {dep or 'serviço não identificado'}",
        probable_cause=" ".join(hints),
        confidence="media" if ev.recent_deploy else "baixa",
        evidence=evidence,
        next_steps=[
            "Conferir os logs e os eventos abaixo",
            "Ver o painel Cobrança — aplicação no Grafana",
        ],
        action=action,
        specialists=["sre", *route_incident(names, dep)],
    )


def diagnose(incident: Incident, ev: Evidence) -> Diagnosis:
    grounded = specialist_troubleshooting(incident, ev)
    if grounded is not None:
        log.info("aiops.specialists", incident=incident.id, specialists=grounded.specialists)
        return grounded
    workers = route_incident(incident.alert_names, incident.deployment)
    if not _llm_enabled():
        return heuristic(incident, ev)
    from app.core.llm import get_chat_model, llm_callbacks

    allowed = sorted(allowed_actions(incident.alert_names, incident.deployment))
    hints = "\n".join(f"- {n}: {runbook_for(n).hint}" for n in incident.alert_names)
    reports = consult_evidence(
        workers,
        f"Incidente em `{incident.deployment}`.\n<evidencias>\n{ev.render()}\n</evidencias>",
    )
    in_scope = [item.specialist for item in reports if not item.report.out_of_scope]
    log.info("aiops.specialists", incident=incident.id, specialists=["sre", *in_scope])
    prompt = (
        f"Incidente {incident.id} em `{incident.deployment}` (severidade {incident.severity}).\n"
        f"Runbook:\n{hints}\n\n"
        f"Ações permitidas neste incidente: {allowed or 'nenhuma'} "
        f"(deployment `{incident.deployment}`, réplicas atuais {ev.replicas}, "
        f"máximo {get_aiops_settings().aiops_max_replicas}).\n\n"
        f"Pareceres:\n{render_reports(reports) or 'nenhum especialista adicional'}\n\n"
        f"<evidencias>\n{ev.render(4000)}\n</evidencias>"
    )
    try:
        model = get_chat_model().with_structured_output(Diagnosis)
        diag = model.invoke(
            [SystemMessage(SYSTEM), HumanMessage(prompt)],
            config={"callbacks": llm_callbacks(), "run_name": "aiops_sre"},
        )
    except Exception:  # noqa: BLE001
        log.warning("aiops.llm_failed", incident=incident.id, exc_info=True)
        return heuristic(incident, ev)
    diag = ensure_action(_sanitize(diag, incident, ev), incident, ev)
    diag.specialists = ["sre", *in_scope]
    return diag


def postmortem(incident: Incident) -> str:
    """Resumo pós-incidente para a thread (blameless: fatos, causa, ação, próximos passos)."""
    timeline = "\n".join(f"• {ts:%H:%M}Z {text}" for ts, text in incident.timeline)
    diag = incident.diagnosis
    base = (
        f"*Resolvido em {incident.duration()}*\n{timeline}\n"
        f"*Causa provável:* {diag.probable_cause if diag else 'não diagnosticada'}"
    )
    if not _llm_enabled():
        return base
    from app.core.llm import get_chat_model, llm_callbacks

    try:
        response = get_chat_model().invoke(
            [
                SystemMessage(
                    SYSTEM + "\nEscreva um postmortem blameless de até 8 linhas: impacto, "
                    "causa, o que resolveu, e uma ação preventiva concreta (alerta, limite, teste)."
                ),
                HumanMessage(base + f"\nAlertas: {', '.join(incident.alert_names)}"),
            ],
            config={"callbacks": llm_callbacks(), "run_name": "aiops_postmortem"},
        )
        return f"*Resolvido em {incident.duration()}*\n{response.content}"
    except Exception:  # noqa: BLE001
        log.warning("aiops.postmortem_failed", incident=incident.id, exc_info=True)
        return base


def build_tools(src: Sources, open_incidents) -> list:  # noqa: ANN001
    """Ferramentas só de leitura para a investigação pelo Slack."""
    ns = get_aiops_settings().aiops_namespace

    def _safe(fn):  # noqa: ANN001, ANN202
        try:
            return fn()
        except SourceError as exc:
            return str(exc)

    @tool
    def promql(query: str) -> str:
        """Executa uma consulta PromQL instantânea no Thanos. Métricas úteis:
        cobranca_http_requests_total, cobranca_http_request_duration_seconds_bucket,
        celery_queue_length, celery_tasks_total, pg_up, redis_up, kube_pod_*."""
        return _safe(lambda: src.prom.summarize(query, limit=15))

    @tool
    def logs(service: str, contains: str = "", minutes: int = 15) -> str:
        """Últimas linhas de log de um deployment no Loki.

        `contains` filtra por regex (ex.: 'error|inbound\\.')."""
        selector = f'{{namespace="{ns}", service="{service}"}}'
        if contains:
            selector += f' |~ "(?i){contains.replace(chr(34), "")}"'
        return _safe(
            lambda: (
                "\n".join(src.loki.tail(selector, minutes=min(minutes, 120), limit=30))
                or "sem linhas"
            )
        )

    @tool
    def pods(deployment: str) -> str:
        """Status, restarts e último término dos pods de um deployment."""
        return _safe(
            lambda: "\n".join(pod_status(p) for p in src.kube.pods(ns, deployment)) or "nenhum pod"
        )

    @tool
    def events(deployment: str) -> str:
        """Eventos recentes do Kubernetes dos objetos do deployment."""
        return _safe(lambda: "\n".join(src.kube.events(ns, deployment)) or "sem eventos")

    @tool
    def rollouts(deployment: str) -> str:
        """Histórico de revisões (imagem e idade) de um deployment."""
        return _safe(lambda: "\n".join(rollout_history(src.kube.replicasets(ns, deployment))))

    @tool
    def incidentes_abertos() -> str:
        """Incidentes abertos agora no AIOps."""
        rows = [
            f"{i.id} {i.deployment}: {', '.join(i.alert_names)} há {i.duration()}"
            for i in open_incidents()
        ]
        return "\n".join(rows) or "nenhum"

    return [promql, logs, pods, events, rollouts, incidentes_abertos]


def status_report(src: Sources, open_incidents) -> str:  # noqa: ANN001
    """Fotografia sem LLM: alvos fora, 5xx, filas e pods não prontos."""
    ns = get_aiops_settings().aiops_namespace
    checks = {
        "Alvos fora": 'up{job=~"cobranca-http|postgres|redis|celery"} == 0',
        "5xx/s por serviço": (
            'sum by (service) (rate(cobranca_http_requests_total{status=~"5.."}[5m])) > 0'
        ),
        "Filas": "max by (queue_name) (celery_queue_length) > 0",
        "Pods não prontos": f'kube_pod_status_ready{{namespace="{ns}",condition="true"}} == 0',
    }
    lines = []
    for title, q in checks.items():
        try:
            lines.append(f"*{title}*\n```{src.prom.summarize(q)}```")
        except SourceError as exc:
            lines.append(f"*{title}*: {exc}")
    incidents = open_incidents()
    lines.append(
        "*Incidentes abertos*: "
        + (", ".join(f"`{i.id}` {i.deployment}" for i in incidents) or "nenhum")
    )
    return "\n".join(lines)


def investigate(question: str, src: Sources, open_incidents) -> str:  # noqa: ANN001
    """Pergunta livre do Slack. Cada especialista usa as ferramentas da própria área."""
    if not _llm_enabled():
        return "Sem `LLM_API_KEY`, respondo só com o status:\n" + status_report(src, open_incidents)
    try:
        return consult_question(question, route_question(question), src, open_incidents)
    except Exception as exc:  # noqa: BLE001
        log.warning("aiops.investigate_failed", exc_info=True)
        return f"A investigação parou ({type(exc).__name__}). Status atual:\n" + status_report(
            src, open_incidents
        )
