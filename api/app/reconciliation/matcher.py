"""Matcher em camadas (FLUXOS.md §10). Python puro, sem LLM e sem banco.

Recebe um pagamento e os títulos em aberto do tenant e devolve uma decisão.
Para no primeiro critério que casa:

1. `txid` / E2E igual ao do título → baixa automática.
2. Valor + documento do pagador + janela de data → baixa automática.
3. Valor + nome aproximado + janela, ou soma de títulos do mesmo devedor → sugestão.
4. Sem candidato → exceção "pagamento não identificado".
"""

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from difflib import SequenceMatcher
from enum import StrEnum
from itertools import combinations
from uuid import UUID

from app.models.enums import MatchMethod

CENT = Decimal("0.01")


@dataclass(frozen=True)
class PaymentData:
    amount: Decimal
    paid_on: date
    e2e_id: str | None = None
    txid: str | None = None
    payer_doc: str | None = None
    payer_name: str | None = None
    debtor_id: UUID | None = None


@dataclass(frozen=True)
class InvoiceCandidate:
    id: UUID
    debtor_id: UUID
    amount_open: Decimal
    due_date: date
    debtor_doc: str
    debtor_name: str
    txid: str | None = None


@dataclass(frozen=True)
class ReconciliationRules:
    """Regras do tenant (`tenants.reconciliation_rules`)."""

    days_before_due: int = 10
    days_after_due: int = 60
    name_similarity_min: float = 0.82
    max_invoices_in_sum: int = 4
    allow_partial: bool = True
    max_overpay_pct: Decimal = Decimal("2")
    max_underpay_pct: Decimal = Decimal("0")

    @classmethod
    def from_json(cls, data: dict | None) -> "ReconciliationRules":
        data = data or {}
        kwargs = {}
        for name, f in cls.__dataclass_fields__.items():
            if name in data:
                kwargs[name] = Decimal(str(data[name])) if f.type is Decimal else data[name]
        return cls(**kwargs)


class Decision(StrEnum):
    AUTO = "auto"
    SUGGESTION = "suggestion"
    PARTIAL = "partial"
    AMOUNT_MISMATCH = "amount_mismatch"
    UNIDENTIFIED = "unidentified"


@dataclass(frozen=True)
class Allocation:
    invoice_id: UUID
    amount: Decimal


@dataclass
class MatchResult:
    decision: Decision
    layer: int
    method: MatchMethod | None = None
    score: float = 0.0
    allocations: list[Allocation] = field(default_factory=list)
    suggestions: list[dict] = field(default_factory=list)
    reason: str = ""


def only_digits(value: str | None) -> str:
    return re.sub(r"\D", "", value or "")


def normalize_name(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-z ]", " ", text.lower())
    stop = {"da", "de", "do", "das", "dos", "e", "ltda", "me", "eireli", "sa"}
    return " ".join(t for t in text.split() if t not in stop)


def name_similarity(a: str | None, b: str | None) -> float:
    na, nb = normalize_name(a), normalize_name(b)
    if not na or not nb:
        return 0.0
    ratio = SequenceMatcher(None, na, nb).ratio()
    ta, tb = set(na.split()), set(nb.split())
    token_overlap = len(ta & tb) / max(len(ta), len(tb))
    return round(max(ratio, token_overlap), 4)


def document_matches(payer_doc: str | None, debtor_doc: str) -> bool:
    """Compara o documento do pagador, que em comprovante costuma vir mascarado
    (ex.: `***.456.789-**`), com o documento cadastrado. Exige pelo menos 6 dígitos
    visíveis na posição certa."""
    if not payer_doc:
        return False
    debtor = only_digits(debtor_doc)
    if "*" not in payer_doc and "x" not in payer_doc.lower():
        return only_digits(payer_doc) == debtor

    masked = re.sub(r"[.\-/\s]", "", payer_doc.lower()).replace("x", "*")
    if len(masked) != len(debtor):
        return False
    visible = [(i, c) for i, c in enumerate(masked) if c.isdigit()]
    return len(visible) >= 6 and all(debtor[i] == c for i, c in visible)


def in_window(paid_on: date, due_date: date, rules: ReconciliationRules) -> bool:
    return (
        due_date - timedelta(days=rules.days_before_due)
        <= paid_on
        <= due_date + timedelta(days=rules.days_after_due)
    )


def amount_fits(paid: Decimal, due: Decimal, rules: ReconciliationRules) -> bool:
    """Valor compatível considerando juros (acima) e tolerância abaixo do tenant."""
    upper = due * (1 + rules.max_overpay_pct / 100)
    lower = due * (1 - rules.max_underpay_pct / 100)
    return lower.quantize(CENT) <= paid <= upper.quantize(CENT)


def _settle(
    payment: PaymentData,
    invoice: InvoiceCandidate,
    layer: int,
    method: MatchMethod,
    rules: ReconciliationRules,
) -> MatchResult:
    """Depois de achar o título com confiança, decide baixa total, parcial ou exceção."""
    paid, due = payment.amount, invoice.amount_open
    if amount_fits(paid, due, rules):
        return MatchResult(
            Decision.AUTO, layer, method, 1.0, [Allocation(invoice.id, min(paid, due))]
        )
    if paid < due and rules.allow_partial:
        return MatchResult(
            Decision.PARTIAL, layer, method, 1.0, [Allocation(invoice.id, paid)],
            reason=f"pagamento parcial: {paid} de {due}",
        )
    return MatchResult(
        Decision.AMOUNT_MISMATCH, layer, method, 1.0,
        suggestions=[{"invoice_id": str(invoice.id), "amount_open": str(due)}],
        reason=f"diferença de valor fora da regra: pago {paid}, em aberto {due}",
    )


def _layer1(payment: PaymentData, candidates: list[InvoiceCandidate]) -> InvoiceCandidate | None:
    keys = {k for k in (payment.txid, payment.e2e_id) if k}
    if not keys:
        return None
    hits = [c for c in candidates if c.txid and c.txid in keys]
    return hits[0] if len(hits) == 1 else None


def _layer2(
    payment: PaymentData, candidates: list[InvoiceCandidate], rules: ReconciliationRules
) -> InvoiceCandidate | None:
    hits = [
        c
        for c in candidates
        if document_matches(payment.payer_doc, c.debtor_doc)
        and in_window(payment.paid_on, c.due_date, rules)
        and amount_fits(payment.amount, c.amount_open, rules)
    ]
    return hits[0] if len(hits) == 1 else None


def _layer3(
    payment: PaymentData, candidates: list[InvoiceCandidate], rules: ReconciliationRules
) -> list[dict]:
    suggestions: list[dict] = []

    for c in candidates:
        if not in_window(payment.paid_on, c.due_date, rules):
            continue
        if not amount_fits(payment.amount, c.amount_open, rules):
            continue
        doc_ok = document_matches(payment.payer_doc, c.debtor_doc)
        same_debtor = payment.debtor_id is not None and payment.debtor_id == c.debtor_id
        similarity = name_similarity(payment.payer_name, c.debtor_name)
        if doc_ok or same_debtor or similarity >= rules.name_similarity_min:
            score = 0.95 if doc_ok else 0.9 if same_debtor else similarity * 0.9
            suggestions.append({
                "method": MatchMethod.VALOR_NOME.value,
                "score": round(score, 4),
                "allocations": [{"invoice_id": str(c.id), "amount": str(c.amount_open)}],
            })

    by_debtor: dict[UUID, list[InvoiceCandidate]] = {}
    for c in candidates:
        by_debtor.setdefault(c.debtor_id, []).append(c)

    for debtor_id, invoices in by_debtor.items():
        sample = invoices[0]
        related = (
            payment.debtor_id == debtor_id
            or document_matches(payment.payer_doc, sample.debtor_doc)
            or name_similarity(payment.payer_name, sample.debtor_name) >= rules.name_similarity_min
        )
        if not related or len(invoices) < 2:
            continue
        invoices = sorted(invoices, key=lambda c: c.due_date)
        for size in range(2, min(rules.max_invoices_in_sum, len(invoices)) + 1):
            for combo in combinations(invoices, size):
                if sum((c.amount_open for c in combo), Decimal("0")) == payment.amount:
                    suggestions.append({
                        "method": MatchMethod.SOMA_TITULOS.value,
                        "score": 0.85,
                        "allocations": [
                            {"invoice_id": str(c.id), "amount": str(c.amount_open)} for c in combo
                        ],
                    })

    suggestions.sort(key=lambda s: s["score"], reverse=True)
    return suggestions[:5]


def match_payment(
    payment: PaymentData,
    candidates: list[InvoiceCandidate],
    rules: ReconciliationRules | None = None,
) -> MatchResult:
    rules = rules or ReconciliationRules()
    open_candidates = [c for c in candidates if c.amount_open > 0]

    if hit := _layer1(payment, open_candidates):
        return _settle(payment, hit, 1, MatchMethod.CHAVE_EXATA, rules)

    if hit := _layer2(payment, open_candidates, rules):
        return _settle(payment, hit, 2, MatchMethod.VALOR_DOCUMENTO, rules)

    if suggestions := _layer3(payment, open_candidates, rules):
        return MatchResult(
            Decision.SUGGESTION, 3, MatchMethod(suggestions[0]["method"]),
            suggestions[0]["score"], suggestions=suggestions,
            reason="candidatos com score, aguardando confirmação humana",
        )

    return MatchResult(Decision.UNIDENTIFIED, 4, reason="nenhum título candidato")
