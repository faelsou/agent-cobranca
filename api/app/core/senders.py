"""Números de WhatsApp da empresa, os que disparam a cobrança. No máximo cinco.
O primeiro da lista é o que envia. Os outros ficam prontos para substituir um que cair."""

from app.core.phones import normalize_br_phone

MAX_SENDERS = 5


def normalize_senders(rows: list[dict]) -> list[dict]:
    if len(rows) > MAX_SENDERS:
        raise ValueError("no máximo 5 números de WhatsApp")
    cleaned: list[dict] = []
    instances: set[str] = set()
    numbers: set[str] = set()
    for row in rows:
        instance = str(row.get("instance") or "").strip()
        if not instance:
            raise ValueError("instância obrigatória")
        if len(instance) > 120:
            raise ValueError("instância longa demais")
        number = normalize_br_phone(str(row.get("number") or ""))
        if number is None:
            raise ValueError(f"número de WhatsApp inválido: {row.get('number')}")
        if instance in instances:
            raise ValueError("instância repetida")
        if number in numbers:
            raise ValueError("número repetido")
        instances.add(instance)
        numbers.add(number)
        cleaned.append({"instance": instance, "number": number})
    return cleaned


def listed_senders(tenant) -> list[dict]:
    """Lista salva. Se a conta antiga só tem a instância principal, ela entra na frente."""
    senders: list[dict] = []
    seen: set[str] = set()
    for item in tenant.whatsapp_senders or []:
        if not isinstance(item, dict):
            continue
        instance = str(item.get("instance") or "").strip()
        if not instance or instance in seen:
            continue
        seen.add(instance)
        senders.append({"instance": instance, "number": str(item.get("number") or "")})
    primary = (tenant.whatsapp_instance or "").strip()
    if primary and primary not in seen:
        senders.insert(0, {"instance": primary, "number": tenant.whatsapp_number or ""})
    return senders[:MAX_SENDERS]


def apply_senders(tenant, senders: list[dict]) -> None:
    """Grava a lista e deixa o primeiro como número que dispara."""
    tenant.whatsapp_senders = senders
    if senders:
        tenant.whatsapp_instance = senders[0]["instance"]
        tenant.whatsapp_number = senders[0]["number"] or None
    else:
        tenant.whatsapp_instance = None
        tenant.whatsapp_number = None


def fold_primary(tenant) -> None:
    """A agência mudou a instância ou o número principal. Ele passa a disparar;
    os outros números da empresa continuam na lista."""
    primary = (tenant.whatsapp_instance or "").strip()
    others = [
        item for item in listed_senders(tenant)
        if item["instance"] != primary
    ]
    senders: list[dict] = []
    if primary:
        senders.append({"instance": primary, "number": tenant.whatsapp_number or ""})
    senders.extend(others)
    apply_senders(tenant, senders[:MAX_SENDERS])
