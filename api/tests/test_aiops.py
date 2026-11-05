"""AIOps sem cluster, sem Slack e sem LLM: correlação, guardrails e o ciclo do incidente."""

import hashlib
import hmac
import json
import time
from concurrent.futures import Executor, Future
from datetime import UTC, datetime, timedelta

import pytest

from app.aiops import diagnose as dx
from app.aiops.config import AiopsSettings
from app.aiops.engine import Engine
from app.aiops.models import (
    ActionKind,
    Alert,
    AlertmanagerPayload,
    Diagnosis,
    Incident,
    ProposedAction,
)
from app.aiops.remediation import Remediator
from app.aiops.runbooks import allowed_actions, correlation_key, deployment_of
from app.aiops.slack import EXECUTE, incident_blocks
from app.aiops.sources import SourceError
from app.aiops.store import ActionBudget, IncidentStore

NS = "cobranca"


def _iso(minutes_ago: int) -> str:
    return (datetime.now(UTC) - timedelta(minutes=minutes_ago)).isoformat().replace("+00:00", "Z")


def alert(name: str, status: str = "firing", fp: str | None = None, **labels: str) -> Alert:
    return Alert(
        status=status,
        labels={"alertname": name, "severity": labels.pop("severity", "warning"), **labels},
        annotations={"summary": f"{name} resumo"},
        startsAt=datetime.now(UTC),
        fingerprint=fp or f"{name}-{sorted(labels.items())}",
    )


class Inline(Executor):
    def submit(self, fn, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        f: Future = Future()
        f.set_result(fn(*args, **kwargs))
        return f


class FakeKube:
    enabled = True

    def __init__(self, revisions: int = 2, replicas: int = 1, recent: bool = True) -> None:
        self.replicas = replicas
        self.revisions = revisions
        self.recent = recent
        self.patches: list[dict] = []
        self.templates: list[dict] = []
        self.catalog: tuple[str, ...] = ()

    def deployment(self, ns, name):  # noqa: ANN001, ANN201
        return {
            "metadata": {
                "generation": 2,
                "annotations": {"deployment.kubernetes.io/revision": str(self.revisions)},
            },
            "spec": {
                "replicas": self.replicas,
                "template": {"spec": {"containers": [{"image": "api:new"}]}},
            },
            "status": {
                "observedGeneration": 2,
                "replicas": self.replicas,
                "updatedReplicas": self.replicas,
                "availableReplicas": self.replicas,
            },
        }

    def replicasets(self, ns, name):  # noqa: ANN001, ANN201
        return [
            {
                "metadata": {
                    "annotations": {"deployment.kubernetes.io/revision": str(rev)},
                    "creationTimestamp": _iso(
                        5 if (rev == self.revisions and self.recent) else 600
                    ),
                },
                "spec": {
                    "template": {
                        "metadata": {"labels": {"app": name, "pod-template-hash": f"h{rev}"}},
                        "spec": {"containers": [{"image": f"api:v{rev}"}]},
                    }
                },
                "status": {"replicas": 1 if rev == self.revisions else 0},
            }
            for rev in range(1, self.revisions + 1)
        ]

    def pods(self, ns, name):  # noqa: ANN001, ANN201
        return [
            {
                "metadata": {"name": f"{name}-7d9f8c6b5d-abcde"},
                "status": {
                    "phase": "Running",
                    "containerStatuses": [{"ready": False, "restartCount": 3}],
                },
            }
        ]

    def hpa_targets(self, ns):  # noqa: ANN001, ANN201
        return {"webhook-api"}

    def events(self, ns, prefix):  # noqa: ANN001, ANN201
        return ["Warning BackOff pod: Back-off restarting failed container (x3)"]

    def pod_logs(self, *a, **kw):  # noqa: ANN002, ANN003, ANN201
        return []

    def deployments(self, ns):  # noqa: ANN001, ANN201
        items = []
        for name in self.catalog:
            item = self.deployment(ns, name)
            item["metadata"]["name"] = name
            items.append(item)
        return items

    def patch_deployment(self, ns, name, body):  # noqa: ANN001, ANN201
        self.patches.append(body)
        replicas = body.get("spec", {}).get("replicas")
        if isinstance(replicas, int):
            self.replicas = replicas
        return {}

    def replace_template(self, ns, name, template):  # noqa: ANN001, ANN201
        self.templates.append(template)
        return {}


class FakeProm:
    def summarize(self, q, limit=10):  # noqa: ANN001, ANN201
        return '{status="500"} 0.4'


class DownLoki:
    def tail(self, *a, **kw):  # noqa: ANN002, ANN003, ANN201
        raise SourceError("Loki: ConnectError")


class FakeSlack:
    def __init__(self) -> None:
        self.posts: list[dict] = []
        self.updates: list[list[dict]] = []

    def post(self, text, *, blocks=None, thread_ts=None, channel=None):  # noqa: ANN001, ANN201
        self.posts.append({"text": text, "blocks": blocks, "thread_ts": thread_ts})
        return "C1", thread_ts or f"ts{len(self.posts)}"

    def update(self, channel, ts, text, blocks):  # noqa: ANN001, ANN201
        self.updates.append(blocks)


def settings(**kw) -> AiopsSettings:  # noqa: ANN003
    base = {
        "aiops_namespace": NS,
        "aiops_cooldown_seconds": 600,
        "aiops_max_actions_per_hour": 6,
        "aiops_verify_seconds": 1,
        "slack_approvers": ["UOK"],
    }
    return AiopsSettings(**{**base, **kw})


@pytest.fixture(autouse=True)
def _sem_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dx, "_llm_enabled", lambda: False)


def make_engine(kube: FakeKube | None = None, **kw) -> tuple[Engine, FakeSlack, FakeKube]:  # noqa: ANN003
    kube = kube or FakeKube()
    slack = FakeSlack()
    src = dx.Sources(prom=FakeProm(), loki=DownLoki(), kube=kube)
    engine = Engine(settings(**kw), sources=src, slack=slack, pool=Inline())
    engine.remediator.sleep = lambda _s: None
    return engine, slack, kube


# Runbook ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("labels", "deployment"),
    [
        (
        {"alertname": "DeploymentSemReplica", "deployment": "cadastro", "namespace": NS},
        "cadastro",
    ),
    ({"alertname": "CobrancaHttp5xx", "service": "conci-pgto"}, "conci-pgto"),
        (
            {
                "alertname": "KubePodCrashLoop",
                "namespace": NS,
                "pod": "worker-cadastro-6b7c9d8f4-x2k9p",
            },
            "worker-cadastro",
        ),
        (
            {"alertname": "FilaCeleryCrescendo", "queue_name": "conciliacao-llm"},
            "worker-conciliacao",
        ),
        (
            {"alertname": "TaskCeleryFalhou", "name": "app.dunning.tasks.run_dunning"},
            "worker-cobranca",
        ),
        ({"alertname": "PostgresFora", "service": "postgres"}, "postgres"),
        ({"alertname": "KubeNodeNaoPronto", "node": "minikube"}, None),
    ],
)
def test_alerta_aponta_o_deployment(labels: dict, deployment: str | None) -> None:
    assert deployment_of(Alert(status="firing", labels=labels), NS) == deployment


def test_estado_e_singleton_nao_recebem_acao_proibida() -> None:
    assert allowed_actions(["PostgresFora"], "postgres") == set()
    assert ActionKind.SCALE not in allowed_actions(["KubeContainerCPUThrottled"], "relo-disp")
    assert allowed_actions(["KubePodOOM"], "cobranca") == set()
    assert allowed_actions(["CobrancaHttp5xx"], "cobranca") == {
        ActionKind.ROLLBACK,
        ActionKind.RESTART,
    }


def test_alertas_do_mesmo_deployment_viram_um_incidente() -> None:
    store = IncidentStore()
    a, b = (
        alert("CobrancaHttp5xx", service="cobranca"),
        alert("CobrancaLatenciaAlta", service="cobranca"),
    )
    assert correlation_key(a) == correlation_key(b)

    def new(x: Alert) -> Incident:
        return Incident(
            key=correlation_key(x), title="t", severity="warning", deployment="cobranca"
        )

    inc, created, _ = store.ingest(correlation_key(a), a, lambda: new(a))
    assert created
    same, created, signal = store.ingest(correlation_key(b), b, lambda: new(b))
    assert same is inc and not created and signal
    _, _, signal = store.ingest(correlation_key(b), b, lambda: new(b))
    assert not signal, "repetição do Alertmanager não é sinal novo"


def test_cada_area_chama_o_especialista() -> None:
    from app.aiops.specialists import route_incident, route_question

    assert route_incident(["PostgresFora"], "postgres") == ["kubernetes", "database"]
    assert route_incident(["CobrancaHttp5xx"], "cobranca") == ["kubernetes", "software"]
    assert route_incident(["KubePodCrashLoop"], "cadastro") == ["kubernetes", "software"]
    assert route_incident(["KubePodOOM"], "cobranca") == ["kubernetes", "software"]
    assert route_question("tem lock no postgres") == ["kubernetes", "database"]
    assert route_question("por que o cobranca está com 5xx") == ["kubernetes", "software"]
    assert route_question("o que está acontecendo") == ["kubernetes", "software", "database"]


def test_heuristica_registra_quem_analisa() -> None:
    from app.aiops.diagnose import heuristic

    diag = heuristic(_incident("cobranca", "CobrancaHttp5xx"), dx.Evidence())
    assert diag.specialists == ["sre", "kubernetes", "software"]


# Guardrails ------------------------------------------------------------------


def test_orcamento_tem_cooldown_e_teto_por_hora() -> None:
    now = [0.0]
    budget = ActionBudget(cooldown_s=600, max_per_hour=2, clock=lambda: now[0])
    assert budget.check("cobranca") is None
    budget.spend("cobranca")
    assert "cooldown" in budget.check("cobranca")
    budget.spend("cadastro")
    assert "teto" in budget.check("conci-pgto")
    now[0] = 3601
    assert budget.check("cobranca") is None


def _incident(dep: str = "cobranca", *names: str) -> Incident:
    inc = Incident(key=f"deploy:{dep}", title="t", severity="warning", deployment=dep)
    for n in names or ("CobrancaHttp5xx",):
        a = alert(n, service=dep)
        inc.alerts[a.fingerprint] = a
    return inc


def test_validacao_recusa_fora_do_runbook_e_do_teto() -> None:
    kube = FakeKube(replicas=2)
    rem = Remediator(kube, ActionBudget(600, 6), settings(aiops_max_replicas=3))
    inc = _incident("cobranca", "CobrancaLatenciaAlta")
    assert "runbook" in rem.validate(
        ProposedAction(kind=ActionKind.ROLLBACK, deployment="cobranca"), inc
    )
    assert "incidente é de" in rem.validate(
        ProposedAction(kind=ActionKind.RESTART, deployment="cadastro"), inc
    )
    assert "teto" in rem.validate(
        ProposedAction(kind=ActionKind.SCALE, deployment="cobranca", replicas=5), inc
    )
    assert "mais de 2" in rem.validate(
        ProposedAction(kind=ActionKind.SCALE, deployment="cobranca", replicas=2), inc
    )
    assert (
        rem.validate(ProposedAction(kind=ActionKind.SCALE, deployment="cobranca", replicas=3), inc)
        is None
    )
    gw = _incident("webhook-api", "CobrancaLatenciaAlta")
    assert "HPA" in rem.validate(
        ProposedAction(kind=ActionKind.SCALE, deployment="webhook-api", replicas=3), gw
    )


def test_rollback_volta_para_a_revisao_anterior() -> None:
    kube = FakeKube(revisions=3)
    rem = Remediator(kube, ActionBudget(600, 6), settings())
    result = rem.execute(ProposedAction(kind=ActionKind.ROLLBACK, deployment="cobranca"), actor="t")
    assert "revisão 2" in result and "api:v2" in result
    assert kube.templates[0]["metadata"]["labels"] == {"app": "cobranca"}
    rem_single = Remediator(FakeKube(revisions=1), ActionBudget(600, 6), settings())
    assert "não há revisão" in rem_single.validate(
        ProposedAction(kind=ActionKind.ROLLBACK, deployment="cobranca"), _incident()
    )


def test_dry_run_nao_toca_no_cluster() -> None:
    kube = FakeKube()
    rem = Remediator(kube, ActionBudget(600, 6), settings(aiops_dry_run=True))
    assert rem.execute(
        ProposedAction(kind=ActionKind.RESTART, deployment="cobranca"), "t"
    ).startswith("dry-run")
    assert kube.patches == []


def test_hpa_deixa_subir_de_zero() -> None:
    kube = FakeKube(replicas=0)
    rem = Remediator(kube, ActionBudget(600, 6), settings())
    gw = _incident("webhook-api", "DeploymentSemReplica")
    assert (
        rem.validate(
            ProposedAction(kind=ActionKind.SCALE, deployment="webhook-api", replicas=1), gw
        )
        is None
    )


def test_watch_avisa_o_slack_10s_depois_e_o_aceite_sobe_a_replica() -> None:
    kube = FakeKube(replicas=0)
    kube.catalog = ("frontend-web", "webhook-api")
    engine, slack, kube = make_engine(kube)
    assert engine.watch_once(0) == []
    assert engine.watch_once(9) == []
    assert slack.posts == []
    assert engine.watch_once(10) == ["frontend-web", "webhook-api"]
    assert engine.watch_once(12) == []
    cards = [json.dumps(blocks, ensure_ascii=False) for blocks in slack.updates]
    assert len(cards) >= 2
    assert all("Aceitar e resolver" in card and "Troubleshooting" in card for card in cards)
    assert any("HPA" in card and "webhook-api" in card for card in cards)
    button = next(
        e
        for b in slack.updates[0]
        if b["type"] == "actions"
        for e in b["elements"]
        if e["action_id"] == EXECUTE
    )
    engine.dispatch(
        "interactive",
        {
            "type": "block_actions",
            "user": {"id": "UOK", "username": "rafael"},
            "actions": [{"action_id": EXECUTE, "value": button["value"]}],
        },
    )
    assert kube.replicas == 1
    assert any(p.get("spec", {}).get("replicas") == 1 for p in kube.patches)
    assert "Resolvido" in slack.posts[-1]["text"]
    assert "Escalar" in slack.posts[-1]["text"]


def test_zero_replicas_pede_scale_e_nao_conta_como_resolvido() -> None:
    inc = _incident("cadastro", "CobrancaAlvoFora")
    action = dx.suggest_action(inc, dx.Evidence(replicas=0))
    assert action is not None
    assert action.kind == ActionKind.SCALE and action.replicas == 1
    kube = FakeKube(replicas=0, revisions=1)
    rem = Remediator(kube, ActionBudget(600, 6), settings())
    assert rem.validate(action, inc) is None
    ok, detail = rem.verify("cadastro")
    assert ok is False
    assert "0 réplicas" in detail


def test_runbook_sugere_acao_quando_a_ia_nao_escolhe() -> None:
    inc = _incident("cobranca", "CobrancaHttp5xx")
    diag = Diagnosis(summary="s", probable_cause="c")
    out = dx.ensure_action(diag, inc, dx.Evidence(recent_deploy="rollout novo"))
    assert out.action is not None and out.action.kind == ActionKind.ROLLBACK


def test_acao_da_ia_fora_do_runbook_e_descartada() -> None:
    inc = _incident("cobranca", "KubePodOOM")
    diag = Diagnosis(
        summary="s",
        probable_cause="c",
        action=ProposedAction(kind=ActionKind.RESTART, deployment="cobranca"),
    )
    out = dx._sanitize(diag, inc, dx.Evidence())
    assert out.action is None
    assert any("fora do runbook" in s for s in out.next_steps)


# Ciclo do incidente ------------------------------------------------------------


def test_deploy_recente_com_5xx_propoe_rollback_e_humano_aprova() -> None:
    engine, slack, kube = make_engine()
    engine.handle_alerts(AlertmanagerPayload(alerts=[alert("CobrancaHttp5xx", service="cobranca")]))

    incident = engine.store.open_incidents()[0]
    assert incident.diagnosis.action.kind == ActionKind.ROLLBACK
    assert "rollout novo" in incident.diagnosis.evidence[0]
    assert any("Loki: ConnectError" in e for e in incident.diagnosis.evidence)
    button = next(
        e
        for b in incident_blocks(incident, engine.settings)
        if b["type"] == "actions"
        for e in b["elements"]
        if e["action_id"] == EXECUTE
    )

    click = {"type": "block_actions", "actions": [{"action_id": EXECUTE, "value": button["value"]}]}
    engine.dispatch("interactive", {**click, "user": {"id": "UNOPE"}})
    assert kube.templates == []
    assert "SLACK_APPROVERS" in slack.posts[-1]["text"]

    rendered = json.dumps(incident_blocks(incident, engine.settings), ensure_ascii=False)
    assert "Problema" in rendered and "Troubleshooting" in rendered and "Ação sugerida" in rendered
    assert "Aceitar e resolver" in rendered

    engine.dispatch("interactive", {**click, "user": {"id": "UOK", "username": "rafael"}})
    assert len(kube.templates) == 1
    closed = slack.posts[-1]["text"]
    assert "*Status:* Resolvido" in closed
    assert "Rollback de cobranca" in closed
    assert "*Postmortem*" in closed
    assert incident.status == "resolvido"
    assert engine.store.open_incidents() == []
    card = json.dumps(slack.updates[-1], ensure_ascii=False)
    assert "Resolvido" in card and "Ação tomada" in card and "Postmortem" in card

    engine.dispatch("interactive", {**click, "user": {"id": "UOK"}})
    assert len(kube.templates) == 1
    assert "já resolvido" in slack.posts[-1]["text"]


def test_acao_automatica_so_com_opt_in() -> None:
    engine, _, kube = make_engine(FakeKube(recent=False), aiops_auto_actions=["restart"])
    engine.handle_alerts(
        AlertmanagerPayload(alerts=[alert("CobrancaAlvoFora", service="cadastro")])
    )
    assert len(kube.patches) == 1
    assert "restartedAt" in json.dumps(kube.patches[0])


def test_postgres_fora_nao_oferece_acao() -> None:
    engine, _, kube = make_engine()
    engine.handle_alerts(
        AlertmanagerPayload(alerts=[alert("PostgresFora", service="postgres", severity="critical")])
    )
    incident = engine.store.open_incidents()[0]
    assert incident.severity == "critical"
    assert incident.diagnosis.action is None
    assert kube.patches == [] and kube.templates == []


def test_comando_incidentes_responde_no_ack() -> None:
    engine, _, _ = make_engine()
    engine.handle_alerts(AlertmanagerPayload(alerts=[alert("CobrancaHttp5xx", service="cobranca")]))
    body = engine.dispatch("slash_commands", {"text": "incidentes", "channel_id": "C1"})
    assert "cobranca" in body["text"]


# HTTP ----------------------------------------------------------------------------


def _client(monkeypatch: pytest.MonkeyPatch, **env: str):  # noqa: ANN202
    from fastapi.testclient import TestClient

    from app.aiops import config

    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("SLACK_APP_TOKEN", raising=False)
    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
    config.get_aiops_settings.cache_clear()
    from app.services.aiops import app

    return TestClient(app)


def test_webhook_do_alertmanager_exige_token(monkeypatch: pytest.MonkeyPatch) -> None:
    with _client(monkeypatch, AIOPS_WEBHOOK_TOKEN="segredo") as client:
        assert client.get("/health").json()["service"] == "aiops"
        payload = {"alerts": []}
        assert client.post("/aiops/alertmanager", json=payload).status_code == 401
        ok = client.post(
            "/aiops/alertmanager", json=payload, headers={"Authorization": "Bearer segredo"}
        )
        assert ok.status_code == 202


def test_slack_http_verifica_assinatura(monkeypatch: pytest.MonkeyPatch) -> None:
    with _client(monkeypatch, SLACK_SIGNING_SECRET="s3cr3t") as client:
        body = json.dumps({"type": "url_verification", "challenge": "abc"}).encode()
        assert (
            client.post(
                "/slack/events",
                content=body,
                headers={"x-slack-request-timestamp": "1", "x-slack-signature": "v0=x"},
            ).status_code
            == 401
        )
        ts = str(int(time.time()))
        sig = "v0=" + hmac.new(b"s3cr3t", f"v0:{ts}:".encode() + body, hashlib.sha256).hexdigest()
        resp = client.post(
            "/slack/events",
            content=body,
            headers={"x-slack-request-timestamp": ts, "x-slack-signature": sig},
        )
        assert resp.json() == {"challenge": "abc"}
