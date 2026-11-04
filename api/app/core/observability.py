"""Sentry e Langfuse. Os dois ficam desligados se o ambiente não tiver as chaves.

Não há serviço de observabilidade na stack: Sentry é SaaS e o Langfuse, quando
existir, sobe à parte. Falha ao iniciar qualquer um dos dois não interrompe
cobrança nem conciliação.
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_sentry_active = False
_langfuse_ready = False
_langfuse_failed = False


def sentry_enabled() -> bool:
    return _sentry_active


def langfuse_enabled() -> bool:
    settings = get_settings()
    configured = bool(settings.langfuse_public_key and settings.langfuse_secret_key)
    return configured and not _langfuse_failed


def init_sentry(*, force: bool = False) -> bool:
    """Liga o Sentry só com `SENTRY_DSN`. `force` reinicia depois do fork do Celery."""
    global _sentry_active
    settings = get_settings()
    if not settings.sentry_dsn:
        _sentry_active = False
        return False
    if _sentry_active and not force:
        return True
    try:
        _start_sentry(settings.sentry_dsn, settings.env)
    except Exception:
        _sentry_active = False
        logger.warning("sentry desligado: falha ao iniciar", exc_info=True)
        return False
    _sentry_active = True
    logger.info("sentry ligado")
    return True


def _start_sentry(dsn: str, environment: str) -> None:
    import sentry_sdk
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.fastapi import FastApiIntegration

    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        traces_sample_rate=0.1,
        send_default_pii=False,
        integrations=[FastApiIntegration(), CeleryIntegration()],
    )


def llm_callbacks() -> list[Any]:
    """Handler do Langfuse para intenção, comprovante e negociação. Vazio se desligado."""
    if not _ensure_langfuse():
        return []
    try:
        from langfuse.langchain import CallbackHandler
    except Exception:
        _disable_langfuse("callback indisponível")
        return []
    return [CallbackHandler()]


def flush_traces() -> None:
    if not _langfuse_ready:
        return
    try:
        from langfuse import get_client

        get_client().flush()
    except Exception:
        logger.warning("langfuse: falha ao enviar traces pendentes", exc_info=True)


def _ensure_langfuse() -> bool:
    global _langfuse_ready
    settings = get_settings()
    if not (settings.langfuse_public_key and settings.langfuse_secret_key):
        return False
    if _langfuse_failed:
        return False
    if _langfuse_ready:
        return True
    endpoint = settings.langfuse_host or settings.langfuse_base_url
    try:
        from langfuse import Langfuse

        kwargs: dict[str, Any] = {
            "public_key": settings.langfuse_public_key,
            "secret_key": settings.langfuse_secret_key,
            "environment": settings.env,
        }
        if endpoint:
            kwargs["host"] = endpoint
            kwargs["base_url"] = endpoint
        Langfuse(**kwargs)
    except Exception:
        _disable_langfuse("falha ao iniciar")
        return False
    _langfuse_ready = True
    logger.info("langfuse ligado")
    return True


def _disable_langfuse(reason: str) -> None:
    global _langfuse_ready, _langfuse_failed
    _langfuse_ready = False
    _langfuse_failed = True
    logger.warning("langfuse desligado: %s", reason, exc_info=True)
