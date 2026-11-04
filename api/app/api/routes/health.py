from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy import text

from app.api.deps import CurrentUser, get_current_user
from app.api.schemas import Me
from app.core.db import SessionLocal, engine
from app.core.observability import langfuse_enabled, sentry_enabled
from app.core.redis import get_redis
from app.models import Tenant

router = APIRouter()


@router.get("/health", tags=["infra"])
def health(response: Response, request: Request) -> dict:
    """200 só quando Postgres e Redis respondem. O Traefik tira da rotação se falhar.

    `sentry` e `langfuse` são informativos (`on`/`off`) e não derrubam a réplica.
    """
    checks = {"service": getattr(request.app.state, "service_name", "gateway")}
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["postgres"] = f"erro: {type(exc).__name__}"
    try:
        get_redis().ping()
        checks["redis"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["redis"] = f"erro: {type(exc).__name__}"

    if checks.get("postgres") != "ok" or checks.get("redis") != "ok":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    checks["sentry"] = "on" if sentry_enabled() else "off"
    checks["langfuse"] = "on" if langfuse_enabled() else "off"
    return checks


@router.get("/me", response_model=Me, tags=["auth"])
def me(user: CurrentUser = Depends(get_current_user)) -> Me:
    tenant_name = None
    if user.tenant_id:
        with SessionLocal() as session:
            tenant = session.get(Tenant, user.tenant_id)
            tenant_name = tenant.name if tenant else None
    return Me(id=user.id, email=user.email, tenant_id=user.tenant_id, role=user.role,
              tenant_name=tenant_name)
