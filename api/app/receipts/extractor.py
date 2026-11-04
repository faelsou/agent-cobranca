"""Leitura de comprovante por LLM com saída estruturada. Ponto de IA (a) da regra de ouro."""

import base64
import io

from langchain_core.messages import HumanMessage, SystemMessage
from pypdf import PdfReader

from app.core.llm import get_chat_model, llm_callbacks
from app.receipts.schemas import ReceiptExtraction

SYSTEM_PROMPT = """Você lê comprovantes de pagamento brasileiros (PIX, boleto, TED).
Extraia somente o que está escrito no documento. Não invente nem complete campos.
Se o documento não for um comprovante de pagamento, marque is_payment_receipt=false.
Copie o CPF/CNPJ do pagador exatamente como aparece, incluindo asteriscos de mascaramento.
O valor deve ser o valor efetivamente pago, em reais, com ponto decimal."""


def _pdf_text(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    return "\n".join(page.extract_text() or "" for page in reader.pages[:3])


def extract_receipt(data: bytes, content_type: str) -> ReceiptExtraction:
    model = get_chat_model().with_structured_output(ReceiptExtraction)

    if content_type == "application/pdf":
        text = _pdf_text(data)
        content: list | str = f"Texto extraído do comprovante em PDF:\n\n{text}"
    else:
        encoded = base64.b64encode(data).decode()
        content = [
            {"type": "text", "text": "Leia este comprovante."},
            {"type": "image_url", "image_url": {"url": f"data:{content_type};base64,{encoded}"}},
        ]

    result = model.invoke(
        [SystemMessage(SYSTEM_PROMPT), HumanMessage(content=content)],
        config={"callbacks": llm_callbacks(), "run_name": "receipt_extraction"},
    )
    return result  # type: ignore[return-value]
