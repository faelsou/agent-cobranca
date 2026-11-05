"""Mensagens (Block Kit) e transporte do Slack.

Transporte:
- Socket Mode (`SLACK_APP_TOKEN`): conexão de saída, sem URL pública. Serve no Minikube.
- HTTP (`SLACK_SIGNING_SECRET`): /slack/events, /slack/interactions e /slack/commands,
  com assinatura v0 verificada e janela de 5 minutos contra replay.

Sem `SLACK_BOT_TOKEN`, as mensagens só vão para o log.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from app.aiops.config import AiopsSettings, get_aiops_settings
from app.aiops.models import Incident, ProposedAction
from app.core.logging import get_logger

log = get_logger(__name__)

EXECUTE = "aiops_execute"
REINVESTIGATE = "aiops_reinvestigate"
DISMISS = "aiops_dismiss"

_SEVERITY = {"critical": ":red_circle:", "warning": ":large_orange_circle:"}
_STATUS = {
    "aberto": ":rotating_light: Aberto",
    "mitigando": ":hammer_and_wrench: Mitigando",
    "resolvido": ":white_check_mark: Resolvido",
}
_CONFIDENCE = {
    "alta": ":large_green_circle: alta",
    "media": ":large_yellow_circle: média",
    "baixa": ":white_circle: baixa",
}
_SPECIALIST = {
    "sre": "SRE",
    "kubernetes": "Kubernetes",
    "software": "Engenharia",
    "database": "Banco de dados",
}


def _text(s: str, limit: int = 2900) -> str:
    return s if len(s) <= limit else s[: limit - 1] + "…"


def _bullets(items: list[str], limit: int = 6) -> str:
    return "\n".join(f"• {i}" for i in items[:limit]) or "—"


def incident_blocks(incident: Incident, settings: AiopsSettings | None = None) -> list[dict]:
    settings = settings or get_aiops_settings()
    icon = _SEVERITY.get(incident.severity, ":large_blue_circle:")
    blocks: list[dict] = [
        {"type": "header", "text": {"type": "plain_text", "text": _text(f"{incident.title}", 150)}},
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Status*\n{_STATUS[incident.status]}"},
                {"type": "mrkdwn", "text": f"*Severidade*\n{icon} {incident.severity}"},
                {"type": "mrkdwn", "text": f"*Deployment*\n`{incident.deployment or '?'}`"},
                {"type": "mrkdwn", "text": f"*Duração*\n{incident.duration()}"},
            ],
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": (
                        f"Incidente `{incident.id}` · alertas: {', '.join(incident.alert_names)}"
                    ),
                }
            ],
        },
    ]
    diag = incident.diagnosis
    if diag is None:
        blocks.append(
            {"type": "section", "text": {"type": "mrkdwn", "text": ":mag: Coletando evidências…"}}
        )
        return blocks
    blocks += [
        {"type": "divider"},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": _text(
                    f"*Problema* ({_CONFIDENCE[diag.confidence]})\n{diag.summary}\n\n"
                    f"*Causa provável:* {diag.probable_cause}"
                ),
            },
        },
    ]
    if diag.specialists:
        who = ", ".join(_SPECIALIST.get(name, name) for name in diag.specialists)
        blocks.append(
            {"type": "context", "elements": [{"type": "mrkdwn", "text": f"Analisado por {who}"}]}
        )
    troubleshooting = [*diag.evidence, *diag.next_steps]
    if troubleshooting:
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": _text(f"*Troubleshooting*\n{_bullets(troubleshooting)}"),
                },
            }
        )
    if diag.action and incident.status != "resolvido":
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": _text(
                        f"*Ação sugerida*\n{diag.action.label()}"
                        + (f"\n{diag.action.reason}" if diag.action.reason else "")
                    ),
                },
            }
        )
    if incident.status == "resolvido":
        taken = incident.taken_action
        action_text = taken.label() if taken else "Nenhuma ação do agente."
        if taken and taken.reason:
            action_text = f"{action_text}\n{taken.reason}"
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": _text(f"*Ação tomada*\n{action_text}")},
            }
        )
        if incident.postmortem:
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": _text(f"*Postmortem*\n{incident.postmortem}"),
                    },
                }
            )

    buttons: list[dict] = []
    if diag.action and incident.status != "resolvido":
        buttons.append(
            {
                "type": "button",
                "action_id": EXECUTE,
                "style": "primary",
                "text": {"type": "plain_text", "text": "Aceitar e resolver"},
                "value": json.dumps(
                    {"incident": incident.id, "action": diag.action.model_dump(mode="json")}
                ),
                "confirm": {
                    "title": {"type": "plain_text", "text": "Aceitar e resolver?"},
                    "text": {
                        "type": "mrkdwn",
                        "text": _text(
                            f"{diag.action.label()} no namespace `{settings.aiops_namespace}`."
                            f"\n{diag.action.reason}",
                            300,
                        ),
                    },
                    "confirm": {"type": "plain_text", "text": "Aceitar"},
                    "deny": {"type": "plain_text", "text": "Cancelar"},
                },
            }
        )
    if incident.status != "resolvido":
        buttons += [
            {
                "type": "button",
                "action_id": REINVESTIGATE,
                "value": incident.id,
                "text": {"type": "plain_text", "text": "Investigar de novo"},
            },
            {
                "type": "button",
                "action_id": DISMISS,
                "value": incident.id,
                "text": {"type": "plain_text", "text": "Assumo daqui"},
            },
        ]
    grafana = settings.aiops_grafana_url.rstrip("/")
    namespace = settings.aiops_namespace
    buttons.append(
        {
            "type": "button",
            "action_id": "aiops_grafana",
            "url": f"{grafana}/dashboards",
            "text": {"type": "plain_text", "text": "Grafana"},
        }
    )
    buttons.append(
        {
            "type": "button",
            "action_id": "aiops_k8s_dashboard",
            "url": (
                f"{grafana}/d/k8s-metrics/kubernetes-metricas"
                f"?orgId=1&from=now-3h&to=now&var-namespace={namespace}"
            ),
            "text": {"type": "plain_text", "text": "Kubernetes"},
        }
    )
    blocks.append({"type": "actions", "elements": buttons})
    return blocks


def fallback_text(incident: Incident) -> str:
    return f"[{incident.severity}] {incident.title} ({incident.status})"


def parse_action_value(value: str) -> tuple[str, ProposedAction]:
    data = json.loads(value)
    return data["incident"], ProposedAction.model_validate(data["action"])


class SlackClient:
    """Fachada do WebClient. Sem token, registra no log e devolve um ts falso."""

    def __init__(self, settings: AiopsSettings | None = None, web: Any = None) -> None:
        self.settings = settings or get_aiops_settings()
        self.web = web
        if self.web is None and self.settings.slack_enabled:
            from slack_sdk import WebClient

            self.web = WebClient(token=self.settings.slack_bot_token)

    def post(
        self,
        text: str,
        *,
        blocks: list[dict] | None = None,
        thread_ts: str | None = None,
        channel: str | None = None,
    ) -> tuple[str, str]:
        channel = channel or self.settings.slack_channel
        if self.web is None:
            log.info("aiops.slack_off", channel=channel, thread_ts=thread_ts, text=text[:500])
            return channel, thread_ts or "local"
        try:
            resp = self.web.chat_postMessage(
                channel=channel,
                text=_text(text, 3900),
                blocks=blocks,
                thread_ts=thread_ts,
                unfurl_links=False,
            )
            return resp["channel"], resp["ts"]
        except Exception:  # noqa: BLE001
            log.warning("aiops.slack_post_failed", channel=channel, exc_info=True)
            return channel, thread_ts or ""

    def update(self, channel: str, ts: str, text: str, blocks: list[dict]) -> None:
        if self.web is None or not ts or ts == "local":
            return
        try:
            self.web.chat_update(channel=channel, ts=ts, text=text, blocks=blocks)
        except Exception:  # noqa: BLE001
            log.warning("aiops.slack_update_failed", exc_info=True)


def verify_signature(
    body: bytes, timestamp: str | None, signature: str | None, settings: AiopsSettings | None = None
) -> bool:
    settings = settings or get_aiops_settings()
    if not settings.slack_signing_secret or not timestamp or not signature:
        return False
    from slack_sdk.signature import SignatureVerifier

    return SignatureVerifier(settings.slack_signing_secret).is_valid(body, timestamp, signature)


def start_socket_mode(
    dispatch: Callable[[str, dict], dict | None], settings: AiopsSettings | None = None
) -> Any:
    """Abre o Socket Mode. `dispatch(tipo, payload)` precisa ser rápido: o ack é síncrono."""
    settings = settings or get_aiops_settings()
    if not (settings.slack_app_token and settings.slack_bot_token):
        return None
    from slack_sdk import WebClient
    from slack_sdk.socket_mode import SocketModeClient
    from slack_sdk.socket_mode.request import SocketModeRequest
    from slack_sdk.socket_mode.response import SocketModeResponse

    client = SocketModeClient(
        app_token=settings.slack_app_token, web_client=WebClient(token=settings.slack_bot_token)
    )

    def listener(sm: SocketModeClient, req: SocketModeRequest) -> None:
        try:
            body = dispatch(req.type, req.payload)
        except Exception:  # noqa: BLE001
            log.warning("aiops.socket_dispatch_failed", type=req.type, exc_info=True)
            body = None
        sm.send_socket_mode_response(SocketModeResponse(envelope_id=req.envelope_id, payload=body))

    client.socket_mode_request_listeners.append(listener)
    client.connect()
    log.info("aiops.socket_mode_on")
    return client
