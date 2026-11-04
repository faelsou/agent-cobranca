"""Login do painel. Em produção o JWT vem do Supabase Auth; em dev a API emite o token."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.models import Tenant

router = APIRouter(prefix="/auth", tags=["auth"])


class DevLoginIn(BaseModel):
    email: str = Field(default="operador@demo.local", min_length=3, max_length=200)
    tenant_slug: str = Field(default="demo", min_length=2, max_length=80)
    role: str = Field(default="operador", pattern=r"^(operador|agencia)$")


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    tenant_id: UUID
    tenant_name: str
    email: str
    role: str


@router.post("/dev-login", response_model=TokenOut)
def dev_login(body: DevLoginIn) -> TokenOut:
    """Só existe fora de produção. O JWT tem o mesmo formato do Supabase
    (`app_metadata.tenant_id`), então o restante da API não muda."""
    settings = get_settings()
    if settings.env == "prod":
        raise HTTPException(404, "indisponível")

    with SessionLocal() as session:
        tenant = session.scalars(select(Tenant).where(Tenant.slug == body.tenant_slug)).first()
        if tenant is None:
            raise HTTPException(404, "tenant não encontrado — rode python -m app.cli seed-demo")

    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": body.email,
            "email": body.email,
            "aud": settings.jwt_audience,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(hours=12)).timestamp()),
            "app_metadata": {"tenant_id": str(tenant.id), "role": body.role},
        },
        settings.jwt_secret,
        algorithm="HS256",
    )
    return TokenOut(
        access_token=token,
        tenant_id=tenant.id,
        tenant_name=tenant.name,
        email=body.email,
        role=body.role,
    )
