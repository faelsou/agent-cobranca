from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

engine = create_engine(get_settings().database_url, pool_pre_ping=True, pool_size=5, max_overflow=5)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


def set_tenant(session: Session, tenant_id: UUID) -> None:
    """Escopa a transação ao tenant. As policies de RLS leem `app.tenant_id`."""
    session.execute(text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": str(tenant_id)})


@contextmanager
def tenant_session(tenant_id: UUID) -> Iterator[Session]:
    """Sessão transacional escopada a um tenant, usada por workers e webhooks."""
    with SessionLocal() as session, session.begin():
        set_tenant(session, tenant_id)
        yield session


@contextmanager
def system_session() -> Iterator[Session]:
    """Sessão sem tenant, para resolver o tenant a partir de dados externos
    (instância da Evolution, token do emissor) e para o agendador listar tenants.
    Só lê a tabela `tenants`, que não tem RLS."""
    with SessionLocal() as session, session.begin():
        yield session
