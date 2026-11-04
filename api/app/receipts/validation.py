"""Validação determinística dos campos extraídos pelo LLM (FLUXOS.md §9)."""

import re
from datetime import UTC, datetime, timedelta

from app.receipts.schemas import ReceiptExtraction

E2E_PATTERN = re.compile(r"^[ED]\d{8}(\d{12})[A-Za-z0-9]{11}$")
MAX_RECEIPT_AGE_DAYS = 120


def validate_extraction(
    data: ReceiptExtraction, now: datetime, min_confidence: float
) -> list[str]:
    """Lista de problemas. Vazia significa que o comprovante pode virar `payment`."""
    problems: list[str] = []

    if not data.is_payment_receipt:
        return ["documento não parece um comprovante de pagamento"]
    if data.confidence < min_confidence:
        problems.append(f"confiança baixa na leitura ({data.confidence:.2f})")
    if data.amount is None or data.amount <= 0:
        problems.append("valor ausente ou não positivo")
    if data.paid_at is None:
        problems.append("data do pagamento ausente")
    else:
        paid_at = data.paid_at if data.paid_at.tzinfo else data.paid_at.replace(tzinfo=UTC)
        if paid_at > now + timedelta(hours=1):
            problems.append("data do pagamento no futuro")
        if paid_at < now - timedelta(days=MAX_RECEIPT_AGE_DAYS):
            problems.append("comprovante antigo demais")

    if data.e2e_id:
        e2e = data.e2e_id.strip()
        match = E2E_PATTERN.match(e2e)
        if not match:
            problems.append("ID E2E em formato inválido")
        elif data.paid_at is not None:
            stamp = datetime.strptime(match.group(1), "%Y%m%d%H%M").date()
            if abs((stamp - data.paid_at.date()).days) > 1:
                problems.append("data do E2E não confere com a data do comprovante")

    return problems
