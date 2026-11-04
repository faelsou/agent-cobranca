"""Métricas Prometheus em `/internal/metrics`.

O `GET /metrics` do cadastro continua sendo a métrica de negócio (recuperação,
promessas, baixa). Este caminho é só para o Prometheus e não entra no gateway.
"""

from __future__ import annotations

import time

from fastapi import FastAPI, Request
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.types import ASGIApp, Message, Receive, Scope, Send

HTTP_REQUESTS = Counter(
    "cobranca_http_requests_total",
    "Requisições HTTP por serviço, rota, método e status.",
    ["service", "method", "path", "status"],
)
HTTP_LATENCY = Histogram(
    "cobranca_http_request_duration_seconds",
    "Latência das requisições HTTP.",
    ["service", "method", "path"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60),
)

_METRICS_PATH = "/internal/metrics"


def _path_label(request: Request) -> str:
    """Template da rota. O catch-all do gateway vira o primeiro segmento."""
    route = request.scope.get("route")
    template = getattr(route, "path", None)
    if template and template != "/{path:path}":
        return template
    head = request.url.path.strip("/").split("/", 1)[0]
    return f"/{head}" if head else "/"


class MetricsMiddleware:
    def __init__(self, app: ASGIApp, service: str) -> None:
        self.app = app
        self.service = service

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path") == _METRICS_PATH:
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()
        status = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = int(message["status"])
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            request = Request(scope)
            path = _path_label(request)
            method = scope.get("method", "GET")
            HTTP_REQUESTS.labels(self.service, method, path, str(status)).inc()
            HTTP_LATENCY.labels(self.service, method, path).observe(time.perf_counter() - start)


def install_metrics(app: FastAPI, service: str) -> None:
    app.add_middleware(MetricsMiddleware, service=service)

    @app.get(_METRICS_PATH, include_in_schema=False)
    def prometheus_metrics() -> Response:
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
