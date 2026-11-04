"""Classificação de intenção por LLM. Ponto de IA (b) da regra de ouro."""

from datetime import date
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from app.agent.prompts import CHOICE_SYSTEM, INTENT_SYSTEM
from app.core.llm import get_chat_model, llm_callbacks
from app.models.enums import Intent

WEEKDAYS = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]


class IntentResult(BaseModel):
    intent: Intent
    promised_date: date | None = Field(None, description="Data prometida, só para vou_pagar")
    confidence: float = Field(description="Confiança de 0 a 1")


class ChoiceResult(BaseModel):
    decision: Literal["aceita", "recusa", "fora_da_politica", "outro"]
    option_id: str | None = None


def classify_intent(text: str, today: date) -> IntentResult:
    model = get_chat_model().with_structured_output(IntentResult)
    system = INTENT_SYSTEM.format(today=today.isoformat(), weekday=WEEKDAYS[today.weekday()])
    return model.invoke(
        [SystemMessage(system), HumanMessage(text)],
        config={"callbacks": llm_callbacks(), "run_name": "intent_classification"},
    )


def interpret_choice(text: str, options: list[dict]) -> ChoiceResult:
    listing = "\n".join(f"- id={o['id']}: {o['label']}" for o in options)
    model = get_chat_model().with_structured_output(ChoiceResult)
    return model.invoke(
        [SystemMessage(CHOICE_SYSTEM.format(options=listing)), HumanMessage(text)],
        config={"callbacks": llm_callbacks(), "run_name": "negotiation_choice"},
    )
