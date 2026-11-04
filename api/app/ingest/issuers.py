"""Adaptadores de emissor de cobrança. Cada um traduz o webhook do emissor para
`InvoiceIn` (título novo/alterado) ou `BankPaymentIn` (dinheiro recebido)."""

from datetime import UTC, datetime, time
from decimal import Decimal
from typing import Any

import httpx

from app.ingest.schemas import InvoiceIn
from app.reconciliation.service import BankPaymentIn

ASAAS_INVOICE_EVENTS = {"PAYMENT_CREATED", "PAYMENT_UPDATED"}
ASAAS_PAYMENT_EVENTS = {"PAYMENT_RECEIVED", "PAYMENT_CONFIRMED"}


class AsaasAdapter:
    def __init__(self, config: dict[str, Any]):
        self.base_url = config.get("base_url", "https://api.asaas.com/v3")
        self.api_key = config.get("api_key", "")

    def _customer(self, customer_id: str) -> dict[str, Any]:
        response = httpx.get(
            f"{self.base_url}/customers/{customer_id}",
            headers={"access_token": self.api_key},
            timeout=20,
        )
        response.raise_for_status()
        return response.json()

    def parse(self, body: dict[str, Any]) -> InvoiceIn | BankPaymentIn | None:
        event = body.get("event")
        payment = body.get("payment") or {}

        if event in ASAAS_INVOICE_EVENTS:
            customer = self._customer(payment["customer"])
            return InvoiceIn(
                external_id=payment["id"],
                debtor_name=customer["name"],
                debtor_document=customer["cpfCnpj"],
                debtor_phone=customer.get("mobilePhone") or customer.get("phone"),
                debtor_email=customer.get("email"),
                amount=Decimal(str(payment["value"])),
                due_date=payment["dueDate"],
                description=payment.get("description"),
                txid=payment["id"],
                digitable_line=payment.get("identificationField"),
                payment_url=payment.get("invoiceUrl"),
            )

        if event in ASAAS_PAYMENT_EVENTS:
            paid = payment.get("clientPaymentDate") or payment.get("paymentDate")
            paid_at = datetime.combine(datetime.fromisoformat(paid).date(), time(12), tzinfo=UTC)
            return BankPaymentIn(
                amount=Decimal(str(payment["value"])),
                paid_at=paid_at,
                txid=payment["id"],
                raw={"provider": "asaas", "event": event, "payment": payment},
            )
        return None


def get_adapter(provider: str | None, config: dict[str, Any]) -> AsaasAdapter:
    if provider == "asaas":
        return AsaasAdapter(config)
    raise NotImplementedError(f"emissor sem adaptador: {provider}")
