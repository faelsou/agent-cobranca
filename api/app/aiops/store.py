"""Estado dos incidentes e orçamento de ações, em memória.

Uma réplica só (strategy Recreate). Perder o estado num restart custa, no pior caso,
uma mensagem nova no Slack para um incidente que já existia: o Alertmanager reenvia
o que ainda está disparando a cada `repeat_interval`.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from app.aiops.models import Alert, Incident

_KEEP_RESOLVED = timedelta(hours=24)


class IncidentStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._by_id: dict[str, Incident] = {}
        self._open: dict[str, str] = {}

    def ingest(
        self, key: str, alert: Alert, factory: Callable[[], Incident]
    ) -> tuple[Incident | None, bool, bool]:
        """Junta o alerta ao incidente aberto da chave.

        Devolve (incidente, criado, sinal_novo). Sinal novo é um alertname que ainda
        não disparava no incidente: vale rediagnosticar. Repetição do Alertmanager
        não é sinal novo. Resolved sem incidente aberto devolve None.
        """
        with self._lock:
            self._gc()
            incident_id = self._open.get(key)
            incident = self._by_id.get(incident_id) if incident_id else None
            created = False
            if incident is None:
                if alert.status == "resolved":
                    return None, False, False
                incident = factory()
                self._by_id[incident.id] = incident
                self._open[key] = incident.id
                created = True
            fp = alert.fingerprint or alert.name
            new_signal = alert.status == "firing" and alert.name not in {
                a.name for a in incident.firing
            }
            previous = incident.alerts.get(fp)
            if previous is None or previous.status != alert.status:
                incident.note(f"{alert.name} {alert.status}")
            incident.alerts[fp] = alert
            if alert.severity == "critical":
                incident.severity = "critical"
            return incident, created, new_signal and not created

    def resolve(self, incident: Incident, reason: str) -> None:
        """Fecha o incidente porque a ação aceita foi executada e verificada."""
        with self._lock:
            if incident.status == "resolvido":
                return
            incident.status = "resolvido"
            incident.resolved_at = datetime.now(UTC)
            incident.note(reason)
            self._open.pop(incident.key, None)

    def close_if_clear(self, incident: Incident) -> bool:
        with self._lock:
            if incident.firing or incident.status == "resolvido":
                return False
            incident.status = "resolvido"
            incident.resolved_at = datetime.now(UTC)
            incident.note("todos os alertas resolvidos")
            self._open.pop(incident.key, None)
            return True

    def get(self, incident_id: str) -> Incident | None:
        with self._lock:
            return self._by_id.get(incident_id)

    def open_incidents(self) -> list[Incident]:
        with self._lock:
            return [self._by_id[i] for i in self._open.values() if i in self._by_id]

    def _gc(self) -> None:
        cutoff = datetime.now(UTC) - _KEEP_RESOLVED
        for iid, inc in list(self._by_id.items()):
            if inc.resolved_at and inc.resolved_at < cutoff:
                del self._by_id[iid]


class ActionBudget:
    """Freio de remediação: cooldown por deployment e teto global por hora.

    Evita o laço "restart → alerta → restart" quando a causa não é o processo.
    """

    def __init__(
        self, cooldown_s: int, max_per_hour: int, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self.cooldown_s = cooldown_s
        self.max_per_hour = max_per_hour
        self.clock = clock
        self._lock = threading.Lock()
        self._last: dict[str, float] = {}
        self._window: deque[float] = deque()

    def check(self, deployment: str) -> str | None:
        """None se pode agir; senão, o motivo da recusa."""
        with self._lock:
            now = self.clock()
            while self._window and now - self._window[0] > 3600:
                self._window.popleft()
            last = self._last.get(deployment)
            if last is not None and now - last < self.cooldown_s:
                wait = int(self.cooldown_s - (now - last))
                return f"{deployment} recebeu uma ação há pouco; cooldown de mais {wait}s"
            if len(self._window) >= self.max_per_hour:
                return f"teto de {self.max_per_hour} ações por hora atingido"
            return None

    def spend(self, deployment: str) -> None:
        with self._lock:
            now = self.clock()
            self._last[deployment] = now
            self._window.append(now)
