"""Runbook em código: de qual deployment é o alerta, o que coletar e o que é permitido fazer.

Espelha docs/TROUBLESHOOTING.md. A IA recebe isto como contexto e só pode propor
ações que estejam em `actions` do runbook do alerta.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.aiops.models import ActionKind, Alert
from app.services.queues import queue_for

# Deployments em que o AIOps pode agir. Postgres e Redis têm estado: só humano.
MANAGED = frozenset(
    {
        "webhook-api",
        "cobranca",
        "conci-pgto",
        "cadastro",
        "worker-cobranca",
        "worker-conciliacao",
        "worker-cadastro",
        "relo-disp",
        "frontend-web",
    }
)
# O beat agenda a régua: duas réplicas disparam a régua em dobro.
SINGLETONS = frozenset({"relo-disp"})

QUEUE_WORKER = {
    "cobranca": "worker-cobranca",
    "cobranca-llm": "worker-cobranca",
    "conciliacao": "worker-conciliacao",
    "conciliacao-llm": "worker-conciliacao",
    "cadastro": "worker-cadastro",
}

_POD_SUFFIX = re.compile(r"-[a-z0-9]{8,10}-[a-z0-9]{5}$")


@dataclass(frozen=True)
class Runbook:
    hint: str
    actions: tuple[ActionKind, ...] = ()
    queries: tuple[str, ...] = ()
    log_filter: str = '|~ "(?i)error|exception|failed|traceback"'
    extra: dict[str, str] = field(default_factory=dict)


_HTTP = (
    'sum by (status) (rate(cobranca_http_requests_total{{service="{svc}"}}[5m]))',
    "histogram_quantile(0.95, sum by (le) "
    '(rate(cobranca_http_request_duration_seconds_bucket{{service="{svc}"}}[5m])))',
)
_POD = (
    'sum by (pod) (kube_pod_container_status_restarts_total{{namespace="{ns}",pod=~"{dep}-.*"}})',
    "max by (pod, reason) "
    '(kube_pod_container_status_last_terminated_reason{{namespace="{ns}",pod=~"{dep}-.*"}})',
    'sum by (pod) (container_memory_working_set_bytes{{namespace="{ns}",pod=~"{dep}-.*"}})',
)
_QUEUE = (
    "max by (queue_name) (celery_queue_length)",
    "sum by (name, state) (rate(celery_tasks_total[10m]))",
)

RUNBOOKS: dict[str, Runbook] = {
    "AplicacaoIndisponivel": Runbook(
        "Nenhuma réplica disponível. Spec em 0 pede scale para 1. Spec acima de 0 com "
        "nenhum pod Ready pede rollback se o rollout é novo, senão restart.",
        (ActionKind.SCALE, ActionKind.RESTART, ActionKind.ROLLBACK),
        _POD,
    ),
    "DeploymentSemReplica": Runbook(
        "O deployment foi para 0 réplicas. Não há pod para raspar /internal/metrics, então o "
        "alerta de alvo fora pode nem disparar. Restart não cria pod: é preciso voltar para 1.",
        (ActionKind.SCALE,),
        _POD,
    ),
    "CobrancaAlvoFora": Runbook(
        "O Prometheus não raspa /internal/metrics. Pod caído, reiniciando ou sem Ready. "
        "Ver eventos e o /health (Postgres e Redis).",
        (ActionKind.RESTART,),
        _POD,
    ),
    "CobrancaHttp5xx": Runbook(
        "5xx no serviço. Se começou logo após um deploy, rollback. `gateway.upstream_down` no "
        "gateway é o dono fora do ar; 5xx no span do dono é bug ou dependência (Evolution, LLM).",
        (ActionKind.ROLLBACK, ActionKind.RESTART),
        _HTTP + _POD,
    ),
    "CobrancaLatenciaAlta": Runbook(
        "p95 acima de 2s. Ver CPU throttled, fila e chamadas externas (LLM, Evolution) no trace.",
        (ActionKind.SCALE, ActionKind.RESTART),
        _HTTP + _POD,
    ),
    "FilaCeleryCrescendo": Runbook(
        "Fila crescendo: worker parado, lento ou task falhando em loop. Ver se o worker está "
        "Ready e se `celery_tasks_total{state=FAILURE}` subiu.",
        (ActionKind.SCALE, ActionKind.RESTART),
        _QUEUE + _POD,
    ),
    "TaskCeleryFalhou": Runbook(
        "Task falhando. Ler o traceback no log do worker. Se começou após deploy, rollback.",
        (ActionKind.ROLLBACK, ActionKind.RESTART),
        _QUEUE + _POD,
    ),
    "KubePodCrashLoop": Runbook(
        "CrashLoopBackOff. Ler o log do container anterior. Variável ausente, `localhost` "
        "ou imagem nova quebrada. Se a imagem mudou, rollback.",
        (ActionKind.ROLLBACK,),
        _POD,
    ),
    "KubePodOOM": Runbook(
        "OOMKilled: o limit de memória é menor que o uso. Reiniciar não resolve; o ajuste é "
        "no manifesto (resources.limits.memory) ou o vazamento no código.",
        (),
        _POD,
    ),
    "KubePodNaoReady": Runbook(
        "Running sem Ready: a readinessProbe (/health) falha. Normalmente Postgres ou Redis; "
        "se é o pod de um rollout novo, a configuração nova está errada.",
        (ActionKind.ROLLBACK, ActionKind.RESTART),
        _POD,
    ),
    "KubeContainerCPUThrottled": Runbook(
        "CPU throttled: o container bate no limit. Escalar alivia; o ajuste é o limit.",
        (ActionKind.SCALE,),
        _POD,
    ),
    "KubeMemoriaSaturada": Runbook(
        "Memória acima de 90% do limit. Reiniciar ganha tempo antes do OOM.",
        (ActionKind.RESTART,),
        _POD,
    ),
    "PostgresFora": Runbook(
        "Postgres não responde. Todo /health vira 503. Ação só humana: PVC, disco, pod.",
        (),
        ("pg_up", 'kube_pod_status_ready{{namespace="{ns}",pod=~"postgres-.*",condition="true"}}'),
    ),
    "RedisFora": Runbook(
        "Redis não responde. Fila e trava do turno param. Ação só humana.",
        (),
        ("redis_up", 'kube_pod_status_ready{{namespace="{ns}",pod=~"redis-.*",condition="true"}}'),
    ),
}

DEFAULT = Runbook("Alerta sem runbook. Coletar sinais do serviço e escalar para humano.", (), _POD)


def runbook_for(alertname: str) -> Runbook:
    return RUNBOOKS.get(alertname, DEFAULT)


def deployment_of(alert: Alert, namespace: str = "cobranca") -> str | None:
    """Deployment afetado, a partir dos labels que cada regra carrega."""
    labels = alert.labels
    if labels.get("alertname") == "PostgresFora":
        return "postgres"
    if labels.get("alertname") == "RedisFora":
        return "redis"
    named = labels.get("deployment")
    if named in MANAGED or named in ("postgres", "redis"):
        return named
    svc = labels.get("service")
    if svc in MANAGED:
        return svc
    if labels.get("namespace") == namespace and (pod := labels.get("pod")):
        return _POD_SUFFIX.sub("", pod)
    if (queue := labels.get("queue_name")) in QUEUE_WORKER:
        return QUEUE_WORKER[queue]
    if task := labels.get("name"):
        try:
            return QUEUE_WORKER.get(queue_for(task))
        except KeyError:
            return None
    return None


def correlation_key(alert: Alert, namespace: str = "cobranca") -> str:
    """Alertas do mesmo deployment viram um incidente só (5xx + latência + restart)."""
    dep = deployment_of(alert, namespace)
    return f"deploy:{dep}" if dep else f"alert:{alert.name}"


def queries_for(alertname: str, deployment: str | None, namespace: str) -> list[str]:
    dep = deployment or ".+"
    return [q.format(svc=dep, dep=dep, ns=namespace) for q in runbook_for(alertname).queries]


def allowed_actions(alertnames: list[str], deployment: str | None) -> set[ActionKind]:
    if deployment not in MANAGED:
        return set()
    kinds: set[ActionKind] = set()
    for name in alertnames:
        kinds.update(runbook_for(name).actions)
    if deployment in SINGLETONS:
        kinds.discard(ActionKind.SCALE)
    return kinds
