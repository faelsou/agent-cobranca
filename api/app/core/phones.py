"""Celulares de WhatsApp do devedor. No máximo cinco, o primeiro é o principal."""

import re

MAX_WHATSAPP_NUMBERS = 5
_SPLIT = re.compile(r"[|/,]")


def normalize_br_phone(value: str | None) -> str | None:
    if not value or not value.strip():
        return None
    digits = re.sub(r"\D", "", value)
    if len(digits) in (10, 11):
        digits = "55" + digits
    if len(digits) not in (12, 13):
        raise ValueError(f"telefone inválido: {value.strip()}")
    return digits


def normalize_phone_list(values: list[str | None]) -> list[str]:
    """Aceita várias células e, dentro de uma célula, números separados por | , ou /."""
    seen: list[str] = []
    for raw in values:
        if not raw or not str(raw).strip():
            continue
        for part in _SPLIT.split(str(raw)):
            number = normalize_br_phone(part)
            if number and number not in seen:
                seen.append(number)
    if len(seen) > MAX_WHATSAPP_NUMBERS:
        raise ValueError("no máximo 5 números de WhatsApp")
    return seen


def contact_phones(phone: str | None, phones: list[str] | None) -> list[str]:
    ordered: list[str] = []
    for number in [*(phones or []), phone]:
        if number and number not in ordered:
            ordered.append(number)
    return ordered[:MAX_WHATSAPP_NUMBERS]


def merge_phones(phone: str | None, phones: list[str] | None, incoming: list[str]) -> list[str]:
    """O primeiro número que chegou substitui o principal. Os outros já salvos ficam, até 5."""
    if not incoming:
        return contact_phones(phone, phones)
    existing = contact_phones(phone, phones)
    old_primary = existing[0] if existing else None
    kept = [number for number in existing if number not in incoming and number != old_primary]
    merged: list[str] = []
    for number in [*incoming, *kept]:
        if number and number not in merged:
            merged.append(number)
        if len(merged) == MAX_WHATSAPP_NUMBERS:
            break
    return merged
