"""Leitura de Prometheus (Thanos), Loki e API do Kubernetes.

Toda leitura devolve texto curto ou levanta `SourceError`. O diagnóstico registra a
falha como evidência ("Loki inacessível") em vez de parar: a própria fonte fora do
ar já diz algo sobre o incidente.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from app.aiops.config import get_aiops_settings

_SA_DIR = Path("/var/run/secrets/kubernetes.io/serviceaccount")
_TIMEOUT = httpx.Timeout(10.0, connect=3.0)
MAX_LOG_LINES = 40


class SourceError(RuntimeError):
    pass


def _fmt_value(raw: str) -> str:
    try:
        value = float(raw)
    except ValueError:
        return raw
    if value != value:  # NaN
        return "NaN"
    return f"{value:.0f}" if value.is_integer() else f"{value:.3g}"


class Prometheus:
    def __init__(self, base_url: str | None = None, client: httpx.Client | None = None) -> None:
        self.base_url = (base_url or get_aiops_settings().aiops_prometheus_url).rstrip("/")
        self.client = client or httpx.Client(timeout=_TIMEOUT)

    def query(self, promql: str) -> list[dict[str, Any]]:
        try:
            resp = self.client.get(f"{self.base_url}/api/v1/query", params={"query": promql})
            resp.raise_for_status()
            body = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise SourceError(f"Prometheus: {type(exc).__name__}") from exc
        if body.get("status") != "success":
            raise SourceError(f"Prometheus: {body.get('error', 'erro')}")
        return body["data"].get("result", [])

    def summarize(self, promql: str, limit: int = 10) -> str:
        rows = self.query(promql)
        if not rows:
            return "sem série"
        lines = []
        for row in rows[:limit]:
            labels = ",".join(f"{k}={v}" for k, v in row["metric"].items() if k != "__name__")
            lines.append(f"{{{labels}}} {_fmt_value(row['value'][1])}")
        if len(rows) > limit:
            lines.append(f"... mais {len(rows) - limit} séries")
        return "\n".join(lines)


class Loki:
    def __init__(self, base_url: str | None = None, client: httpx.Client | None = None) -> None:
        self.base_url = (base_url or get_aiops_settings().aiops_loki_url).rstrip("/")
        self.client = client or httpx.Client(timeout=_TIMEOUT)

    def tail(self, logql: str, minutes: int = 15, limit: int = MAX_LOG_LINES) -> list[str]:
        end = time.time_ns()
        start = end - minutes * 60 * 1_000_000_000
        try:
            resp = self.client.get(
                f"{self.base_url}/loki/api/v1/query_range",
                params={
                    "query": logql,
                    "start": start,
                    "end": end,
                    "limit": limit,
                    "direction": "backward",
                },
            )
            resp.raise_for_status()
            streams = resp.json()["data"]["result"]
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            raise SourceError(f"Loki: {type(exc).__name__}") from exc
        entries = [(ts, line) for s in streams for ts, line in s.get("values", [])]
        entries.sort(reverse=True)
        return [line[:300] for _, line in entries[:limit]]


class Kubernetes:
    """Cliente mínimo da API, com o token do ServiceAccount. Sem token, fica desligado."""

    def __init__(self, base_url: str | None = None, client: httpx.Client | None = None) -> None:
        self.base_url = (base_url or get_aiops_settings().aiops_kube_api).rstrip("/")
        if client is not None:
            self.client = client
            return
        token_file = _SA_DIR / "token"
        if not token_file.is_file():
            self.client = None
            return
        self.client = httpx.Client(
            timeout=_TIMEOUT,
            verify=str(_SA_DIR / "ca.crt"),
            headers={"Authorization": f"Bearer {token_file.read_text().strip()}"},
        )

    @property
    def enabled(self) -> bool:
        return self.client is not None

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        if self.client is None:
            raise SourceError("Kubernetes: sem ServiceAccount (fora do cluster)")
        try:
            resp = self.client.request(method, f"{self.base_url}{path}", **kwargs)
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise SourceError(f"Kubernetes: HTTP {exc.response.status_code} em {path}") from exc
        except httpx.HTTPError as exc:
            raise SourceError(f"Kubernetes: {type(exc).__name__}") from exc
        return (
            resp.json()
            if resp.content and "json" in resp.headers.get("content-type", "")
            else resp.text
        )

    def deployment(self, ns: str, name: str) -> dict:
        return self._request("GET", f"/apis/apps/v1/namespaces/{ns}/deployments/{name}")

    def deployments(self, ns: str) -> list[dict]:
        body = self._request("GET", f"/apis/apps/v1/namespaces/{ns}/deployments")
        return body.get("items", [])

    def pods(self, ns: str, deployment: str) -> list[dict]:
        body = self._request(
            "GET", f"/api/v1/namespaces/{ns}/pods", params={"labelSelector": f"app={deployment}"}
        )
        return body.get("items", [])

    def replicasets(self, ns: str, deployment: str) -> list[dict]:
        body = self._request(
            "GET",
            f"/apis/apps/v1/namespaces/{ns}/replicasets",
            params={"labelSelector": f"app={deployment}"},
        )
        items = body.get("items", [])
        return sorted(
            items, key=lambda rs: int(_annotation(rs, "deployment.kubernetes.io/revision") or 0)
        )

    def hpa_targets(self, ns: str) -> set[str]:
        path = f"/apis/autoscaling/v2/namespaces/{ns}/horizontalpodautoscalers"
        body = self._request("GET", path)
        return {h["spec"]["scaleTargetRef"]["name"] for h in body.get("items", [])}

    def events(self, ns: str, prefix: str, limit: int = 15) -> list[str]:
        body = self._request("GET", f"/api/v1/namespaces/{ns}/events")
        rows = [
            e
            for e in body.get("items", [])
            if e.get("involvedObject", {}).get("name", "").startswith(prefix)
        ]
        rows.sort(key=lambda e: e.get("lastTimestamp") or e.get("eventTime") or "", reverse=True)
        return [
            f"{e.get('type')} {e.get('reason')} {e['involvedObject']['name']}: "
            f"{(e.get('message') or '')[:200]} (x{e.get('count', 1)})"
            for e in rows[:limit]
        ]

    def pod_logs(
        self, ns: str, pod: str, *, previous: bool = False, tail: int = MAX_LOG_LINES
    ) -> list[str]:
        text = self._request(
            "GET",
            f"/api/v1/namespaces/{ns}/pods/{pod}/log",
            params={"tailLines": tail, "previous": str(previous).lower()},
        )
        return [line[:300] for line in str(text).splitlines()[-tail:]]

    def patch_deployment(self, ns: str, name: str, body: dict) -> dict:
        return self._request(
            "PATCH",
            f"/apis/apps/v1/namespaces/{ns}/deployments/{name}",
            json=body,
            headers={"Content-Type": "application/strategic-merge-patch+json"},
        )

    def replace_template(self, ns: str, name: str, template: dict) -> dict:
        """Troca o template inteiro (é o que `kubectl rollout undo` faz)."""
        patch = [{"op": "replace", "path": "/spec/template", "value": template}]
        return self._request(
            "PATCH",
            f"/apis/apps/v1/namespaces/{ns}/deployments/{name}",
            json=patch,
            headers={"Content-Type": "application/json-patch+json"},
        )


def _annotation(obj: dict, key: str) -> str | None:
    return (obj.get("metadata", {}).get("annotations") or {}).get(key)


def image_of(obj: dict) -> str:
    spec = obj.get("spec", {}).get("template", {}).get("spec", {})
    containers = spec.get("containers") or [{}]
    return containers[0].get("image", "?")


def age(ts: str | None) -> str:
    if not ts:
        return "?"
    started = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    minutes = int((datetime.now(UTC) - started).total_seconds() // 60)
    return f"{minutes} min" if minutes < 120 else f"{minutes // 60} h"


def pod_status(pod: dict) -> str:
    name = pod["metadata"]["name"]
    status = pod.get("status", {})
    parts = [f"{name} phase={status.get('phase')}"]
    for cs in status.get("containerStatuses", []):
        state = cs.get("state", {})
        waiting = state.get("waiting", {}).get("reason")
        last = cs.get("lastState", {}).get("terminated", {})
        parts.append(f"ready={cs.get('ready')} restarts={cs.get('restartCount', 0)}")
        if waiting:
            parts.append(f"waiting={waiting}")
        if last:
            parts.append(
                f"last_terminated={last.get('reason')}(exit {last.get('exitCode')}) "
                f"há {age(last.get('finishedAt'))}"
            )
    return " ".join(parts)


def rollout_history(replicasets: list[dict]) -> list[str]:
    rows = []
    for rs in replicasets[-4:]:
        rev = _annotation(rs, "deployment.kubernetes.io/revision")
        created = rs["metadata"].get("creationTimestamp")
        replicas = rs.get("status", {}).get("replicas", 0)
        rows.append(f"rev {rev}: {image_of(rs)} criada há {age(created)}, réplicas={replicas}")
    return rows
