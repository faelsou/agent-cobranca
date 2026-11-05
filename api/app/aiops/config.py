from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.config import SECRETS_DIR


class AiopsSettings(BaseSettings):
    """Configuração do processo `aiops`. Não lê banco nem Redis da aplicação.

    O AIOps tem de continuar de pé quando Postgres ou Redis caem: é justamente
    quando ele precisa diagnosticar.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        secrets_dir=str(SECRETS_DIR) if SECRETS_DIR.is_dir() else None,
    )

    # Bot token (xoxb-) para postar. App token (xapp-) liga o Socket Mode, que não
    # precisa de URL pública. Sem app token, os eventos chegam por HTTP assinado.
    slack_bot_token: str = ""
    slack_app_token: str = ""
    slack_signing_secret: str = ""
    slack_channel: str = "#aiops"
    # IDs de usuário do Slack (U0123...) que podem aprovar ações. Vazio = qualquer um do canal.
    slack_approvers: list[str] = Field(default_factory=list)

    # Bearer que o Alertmanager manda no webhook.
    aiops_webhook_token: str = ""

    aiops_prometheus_url: str = "http://thanos-query:9090"
    aiops_alertmanager_url: str = "http://alertmanager:9093"
    aiops_loki_url: str = "http://loki:3100"
    aiops_grafana_url: str = "http://127.0.0.1:3001"
    aiops_kube_api: str = "https://kubernetes.default.svc"
    aiops_namespace: str = "cobranca"

    # Ações que rodam sem clique. Vazio = toda ação pede aprovação no Slack.
    aiops_auto_actions: list[str] = Field(default_factory=list)
    aiops_dry_run: bool = False
    aiops_cooldown_seconds: int = 600
    aiops_max_actions_per_hour: int = 6
    aiops_max_replicas: int = 3
    aiops_verify_seconds: int = 90

    @property
    def slack_enabled(self) -> bool:
        return bool(self.slack_bot_token)


@lru_cache
def get_aiops_settings() -> AiopsSettings:
    return AiopsSettings()
