import json
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import AuditLog


def _jsonable(data: dict[str, Any] | None) -> dict[str, Any]:
    return json.loads(json.dumps(data or {}, default=str))


def audit(
    session: Session,
    *,
    tenant_id: UUID | None,
    actor: str,
    action: str,
    entity: str,
    entity_id: Any = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> None:
    session.add(
        AuditLog(
            tenant_id=tenant_id,
            actor=actor,
            action=action,
            entity=entity,
            entity_id=str(entity_id) if entity_id is not None else None,
            before=_jsonable(before),
            after=_jsonable(after),
        )
    )
