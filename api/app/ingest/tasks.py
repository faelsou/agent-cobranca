from uuid import UUID

import httpx

from app.core.db import tenant_session
from app.core.logging import get_logger
from app.ingest.issuers import get_adapter
from app.ingest.schemas import InvoiceIn
from app.ingest.service import import_invoices, upsert_invoice
from app.models import Tenant
from app.models.enums import PaymentOrigin
from app.reconciliation.service import BankPaymentIn, register_bank_payment
from app.reconciliation.tasks import reconcile
from app.workers.celery_app import celery_app

log = get_logger(__name__)


@celery_app.task(name="app.ingest.tasks.import_invoices")
def import_invoices_task(tenant_id: str, rows: list[dict], actor: str) -> dict:
    invoices = [InvoiceIn(**row) for row in rows]
    with tenant_session(UUID(tenant_id)) as session:
        result = import_invoices(session, UUID(tenant_id), invoices, actor)
    log.info("ingest.done", tenant_id=tenant_id, created=result.created, updated=result.updated)
    return result.model_dump()


@celery_app.task(
    name="app.ingest.tasks.handle_issuer_event",
    autoretry_for=(httpx.TransportError,), retry_backoff=True, max_retries=5,
)
def handle_issuer_event(tenant_id: str, body: dict) -> str:
    tid = UUID(tenant_id)
    with tenant_session(tid) as session:
        tenant = session.get(Tenant, tid)
        parsed = get_adapter(tenant.issuer_provider, tenant.issuer_config).parse(body)

        if isinstance(parsed, InvoiceIn):
            upsert_invoice(session, tid, parsed, actor=f"emissor:{tenant.issuer_provider}")
            return "invoice"
        if isinstance(parsed, BankPaymentIn):
            payment = register_bank_payment(session, tid, parsed, PaymentOrigin.WEBHOOK)
            if payment is None:
                return "duplicate"
            payment_id = str(payment.id)
        else:
            return "ignored"

    reconcile.delay(tenant_id, payment_id)
    return "payment"
