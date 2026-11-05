"""Números de WhatsApp do devedor. A régua dispara para todos, até cinco."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_db, require_tenant_user
from app.api.schemas import DebtorOut
from app.core.audit import audit
from app.core.phones import contact_phones, normalize_phone_list
from app.models import Debtor

router = APIRouter(prefix="/debtors", tags=["devedores"])


class WhatsappNumbersIn(BaseModel):
    phones: list[str] = []

    @field_validator("phones")
    @classmethod
    def _phones(cls, value: list[str]) -> list[str]:
        try:
            return normalize_phone_list(value)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc


@router.patch("/{debtor_id}/whatsapp", response_model=DebtorOut)
def update_whatsapp_numbers(
    debtor_id: UUID,
    body: WhatsappNumbersIn,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_tenant_user),
) -> Debtor:
    debtor = db.get(Debtor, debtor_id)
    if debtor is None or debtor.tenant_id != user.tenant_id:
        raise HTTPException(404, "devedor não encontrado")
    before = contact_phones(debtor.phone, debtor.phones)
    debtor.phones = body.phones
    debtor.phone = body.phones[0] if body.phones else None
    audit(
        db,
        tenant_id=user.tenant_id,
        actor=user.actor,
        action="atualiza_whatsapp",
        entity="debtor",
        entity_id=debtor.id,
        before={"phones": before},
        after={"phones": body.phones},
    )
    return debtor
