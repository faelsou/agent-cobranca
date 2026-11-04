from uuid import UUID

from app.core.db import tenant_session
from app.core.logging import get_logger
from app.models import Payment, Tenant
from app.reconciliation.service import reconcile_payment
from app.workers.celery_app import celery_app

log = get_logger(__name__)


@celery_app.task(name="app.reconciliation.tasks.reconcile", max_retries=5, default_retry_delay=5)
def reconcile(tenant_id: str, payment_id: str) -> str:
    with tenant_session(UUID(tenant_id)) as session:
        tenant = session.get(Tenant, UUID(tenant_id))
        payment = session.get(Payment, UUID(payment_id))
        result = reconcile_payment(session, payment, tenant)
        log.info("reconcile.done", payment_id=payment_id, decision=result.decision, layer=result.layer)
        return result.decision
