"""Entrada pública. O painel e os webhooks chegam aqui e seguem para o serviço dono."""

from app.services.gateway import app

__all__ = ["app"]
