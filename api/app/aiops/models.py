from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class Alert(BaseModel):
    """Um alerta do webhook do Alertmanager (versão 4 do payload)."""

    status: Literal["firing", "resolved"]
    labels: dict[str, str] = Field(default_factory=dict)
    annotations: dict[str, str] = Field(default_factory=dict)
    startsAt: datetime | None = None  # noqa: N815
    endsAt: datetime | None = None  # noqa: N815
    fingerprint: str = ""
    generatorURL: str = ""  # noqa: N815

    @property
    def name(self) -> str:
        return self.labels.get("alertname", "desconhecido")

    @property
    def severity(self) -> str:
        return self.labels.get("severity", "warning")

    @property
    def summary(self) -> str:
        return self.annotations.get("summary") or self.name


class AlertmanagerPayload(BaseModel):
    status: str = "firing"
    receiver: str = ""
    groupKey: str = ""  # noqa: N815
    alerts: list[Alert] = Field(default_factory=list)


class ActionKind(StrEnum):
    RESTART = "restart"
    ROLLBACK = "rollback"
    SCALE = "scale"


class ProposedAction(BaseModel):
    kind: ActionKind
    deployment: str
    replicas: int | None = Field(default=None, description="Só para scale: total desejado.")
    reason: str = ""

    def label(self) -> str:
        if self.kind == ActionKind.SCALE:
            return f"Escalar {self.deployment} para {self.replicas}"
        if self.kind == ActionKind.ROLLBACK:
            return f"Rollback de {self.deployment}"
        return f"Reiniciar {self.deployment}"


class Diagnosis(BaseModel):
    """Saída do diagnóstico. O LLM preenche; a ação é validada depois, em código."""

    summary: str = Field(
        description="Uma frase: o que está acontecendo, para quem está de plantão."
    )
    probable_cause: str = Field(description="Causa mais provável, apoiada nas evidências.")
    confidence: Literal["alta", "media", "baixa"] = "baixa"
    evidence: list[str] = Field(
        default_factory=list, description="Fatos observados que sustentam a causa."
    )
    next_steps: list[str] = Field(
        default_factory=list, description="Passos de investigação para um humano."
    )
    action: ProposedAction | None = Field(
        default=None, description="Uma ação da lista permitida, ou nada se nenhuma resolve."
    )
    specialists: list[str] = Field(
        default_factory=list,
        description="Preenchido pelo código. Não altere.",
    )


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass
class Incident:
    key: str
    title: str
    severity: str
    deployment: str | None
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    status: Literal["aberto", "mitigando", "resolvido"] = "aberto"
    opened_at: datetime = field(default_factory=_now)
    resolved_at: datetime | None = None
    alerts: dict[str, Alert] = field(default_factory=dict)
    diagnosis: Diagnosis | None = None
    taken_action: ProposedAction | None = None
    postmortem: str | None = None
    slack_channel: str | None = None
    slack_ts: str | None = None
    timeline: list[tuple[datetime, str]] = field(default_factory=list)

    def note(self, text: str) -> None:
        self.timeline.append((_now(), text))

    @property
    def firing(self) -> list[Alert]:
        return [a for a in self.alerts.values() if a.status == "firing"]

    @property
    def alert_names(self) -> list[str]:
        return sorted({a.name for a in self.alerts.values()})

    def duration(self) -> str:
        end = self.resolved_at or _now()
        minutes = int((end - self.opened_at).total_seconds() // 60)
        return f"{minutes} min" if minutes < 120 else f"{minutes // 60} h {minutes % 60} min"
