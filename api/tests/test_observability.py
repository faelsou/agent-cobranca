"""Sentry e Langfuse só ligam com as variáveis preenchidas."""

import sys
import types

import pytest

from app.core.config import get_settings
from app.core.observability import (
    flush_traces,
    init_sentry,
    langfuse_enabled,
    llm_callbacks,
    sentry_enabled,
)


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    import app.core.observability as obs

    obs._sentry_active = False
    obs._langfuse_ready = False
    obs._langfuse_failed = False
    get_settings.cache_clear()
    yield
    obs._sentry_active = False
    obs._langfuse_ready = False
    obs._langfuse_failed = False
    monkeypatch.undo()
    get_settings.cache_clear()


def test_blank_values_stay_off(monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", "  ")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "")
    monkeypatch.setenv("LANGFUSE_HOST", "   ")
    get_settings.cache_clear()

    settings = get_settings()
    assert settings.sentry_dsn is None
    assert settings.langfuse_public_key is None
    assert settings.langfuse_host is None
    assert init_sentry() is False
    assert sentry_enabled() is False
    assert langfuse_enabled() is False
    assert llm_callbacks() == []
    flush_traces()


def test_tracing_fica_desligado_sem_endpoint(monkeypatch):
    import app.core.tracing as tracing

    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    tracing._provider = None
    tracing._meter_provider = None
    tracing._logger_provider = None
    get_settings.cache_clear()

    assert tracing.setup_tracing("gateway") is False
    assert tracing.tracing_enabled() is False
    assert tracing.add_trace_ids(None, None, {"event": "ok"}) == {"event": "ok"}
    tracing.emit_log("info", {"event": "sem coletor"})
    tracing.shutdown_tracing()


def test_log_otlp_grava_evento():
    from opentelemetry.sdk._logs import LoggerProvider
    from opentelemetry.sdk._logs.export import (
        InMemoryLogRecordExporter,
        SimpleLogRecordProcessor,
    )
    from opentelemetry.sdk.resources import Resource

    import app.core.tracing as tracing

    exporter = InMemoryLogRecordExporter()
    provider = LoggerProvider(resource=Resource.create({"service.name": "teste"}))
    provider.add_log_record_processor(SimpleLogRecordProcessor(exporter))
    tracing._logger_provider = provider
    try:
        tracing.emit_log(
            "error",
            {"event": "titulo importado", "tenant": "demo", "n": 2, "vazio": None},
        )
        finished = exporter.get_finished_logs()
        assert len(finished) == 1
        record = finished[0].log_record
        assert record.body == "titulo importado"
        assert record.attributes["tenant"] == "demo"
        assert record.attributes["n"] == 2
        assert "vazio" not in record.attributes
    finally:
        provider.shutdown()
        tracing._logger_provider = None


def test_setup_sobe_traces_metricas_e_logs(monkeypatch):
    import app.core.tracing as tracing

    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:4317")
    tracing._provider = None
    tracing._meter_provider = None
    tracing._logger_provider = None
    _reset_otel_api()
    get_settings.cache_clear()
    try:
        assert tracing.setup_tracing("gateway") is True
        assert tracing._provider is not None
        assert tracing._meter_provider is not None
        assert tracing._logger_provider is not None
        assert tracing.setup_tracing("outro") is True
    finally:
        tracing.shutdown_tracing()
        _reset_otel_api()
        get_settings.cache_clear()


def _reset_otel_api() -> None:
    from opentelemetry import trace as trace_api
    from opentelemetry._logs import _internal as logs_api
    from opentelemetry.metrics import _internal as metrics_api

    trace_api._TRACER_PROVIDER = None
    trace_api._TRACER_PROVIDER_SET_ONCE._done = False
    metrics_api._METER_PROVIDER = None
    metrics_api._METER_PROVIDER_SET_ONCE._done = False
    logs_api._LOGGER_PROVIDER = None
    logs_api._LOGGER_PROVIDER_SET_ONCE._done = False


def test_host_without_keys_does_not_trace(monkeypatch):
    monkeypatch.setenv("LANGFUSE_HOST", "http://langfuse:3000")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "")
    get_settings.cache_clear()

    assert langfuse_enabled() is False
    assert llm_callbacks() == []


def test_sentry_starts_only_with_dsn(monkeypatch):
    started: dict = {"calls": 0}

    def _start(dsn: str, environment: str) -> None:
        started["calls"] += 1
        started["dsn"] = dsn
        started["environment"] = environment

    monkeypatch.setattr("app.core.observability._start_sentry", _start)
    monkeypatch.setenv("SENTRY_DSN", "https://public@o.ingest.sentry.io/1")
    get_settings.cache_clear()

    assert init_sentry() is True
    assert sentry_enabled() is True
    assert started["environment"] == get_settings().env
    assert init_sentry() is True
    assert started["calls"] == 1


def test_sentry_failure_keeps_the_process_up(monkeypatch):
    def _boom(dsn: str, environment: str) -> None:
        raise RuntimeError(dsn or environment)

    monkeypatch.setattr("app.core.observability._start_sentry", _boom)
    monkeypatch.setenv("SENTRY_DSN", "https://public@o.ingest.sentry.io/1")
    get_settings.cache_clear()

    assert init_sentry() is False
    assert sentry_enabled() is False


def test_langfuse_callback_when_keys_exist(monkeypatch):
    monkeypatch.setattr(
        "app.core.observability.get_settings",
        lambda: types.SimpleNamespace(
            langfuse_public_key="pk-test",
            langfuse_secret_key="sk-test",
            langfuse_host="http://langfuse.invalid",
            langfuse_base_url=None,
            env="test",
        ),
    )
    created: dict = {}

    class FakeLangfuse:
        def __init__(self, **kwargs):
            created["init"] = kwargs

    class Handler:
        pass

    langfuse_mod = types.ModuleType("langfuse")
    langfuse_mod.Langfuse = FakeLangfuse
    def _flush() -> None:
        created["flushed"] = True

    langfuse_mod.get_client = lambda: types.SimpleNamespace(flush=_flush)
    langchain_mod = types.ModuleType("langfuse.langchain")
    langchain_mod.CallbackHandler = Handler
    monkeypatch.setitem(sys.modules, "langfuse", langfuse_mod)
    monkeypatch.setitem(sys.modules, "langfuse.langchain", langchain_mod)

    handlers = llm_callbacks()
    assert len(handlers) == 1
    assert isinstance(handlers[0], Handler)
    assert created["init"]["public_key"] == "pk-test"
    assert created["init"]["host"] == "http://langfuse.invalid"
    assert langfuse_enabled() is True
    flush_traces()
    assert created["flushed"] is True
