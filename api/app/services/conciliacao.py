"""Conciliação: pagamentos, exceções, comprovante e o webhook do banco."""

from app.api.routes import exceptions, payments
from app.api.routes.webhooks import bank_router
from app.services.runtime import create_service

app = create_service(
    "conciliacao",
    [bank_router, payments.router, exceptions.router],
)
