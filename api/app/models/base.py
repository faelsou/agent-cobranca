import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any

from sqlalchemy import DateTime, ForeignKey, Numeric, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

Money = Annotated[Decimal, mapped_column(Numeric(14, 2))]
Json = Annotated[dict[str, Any], mapped_column(JSONB, default=dict, server_default="{}")]


class Base(DeclarativeBase):
    type_annotation_map = {uuid.UUID: UUID(as_uuid=True)}


class IdMixin:
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TenantMixin:
    """Toda tabela com este mixin recebe policy de RLS na migration inicial."""

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), index=True)
