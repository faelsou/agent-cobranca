import re
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator


class InvoiceIn(BaseModel):
    """Título normalizado, venha de planilha ou de emissor."""

    external_id: str = Field(min_length=1, max_length=120)
    debtor_name: str = Field(min_length=1, max_length=200)
    debtor_document: str
    debtor_phone: str | None = None
    debtor_email: str | None = None
    amount: Decimal = Field(gt=0)
    due_date: date
    description: str | None = None
    txid: str | None = None
    digitable_line: str | None = None
    pix_copy_paste: str | None = None
    payment_url: str | None = None

    @field_validator("debtor_document")
    @classmethod
    def _doc(cls, v: str) -> str:
        digits = re.sub(r"\D", "", v)
        if len(digits) not in (11, 14):
            raise ValueError("documento precisa ser CPF (11) ou CNPJ (14 dígitos)")
        return digits

    @field_validator("debtor_phone")
    @classmethod
    def _phone(cls, v: str | None) -> str | None:
        if not v:
            return None
        digits = re.sub(r"\D", "", v)
        if len(digits) in (10, 11):
            digits = "55" + digits
        if len(digits) not in (12, 13):
            raise ValueError("telefone inválido")
        return digits


class ImportResult(BaseModel):
    created: int = 0
    updated: int = 0
    errors: list[str] = []
