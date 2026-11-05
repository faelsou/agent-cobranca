from functools import lru_cache

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

from app.core.config import get_settings


def _sampling(model: str) -> dict[str, float]:
    # Claude 4.5 recusa temperature: a API responde "Extra inputs are not permitted".
    if "claude-" in model and "-4-5" in model:
        return {}
    return {"temperature": 0}


@lru_cache
def get_chat_model() -> BaseChatModel:
    settings = get_settings()
    kwargs = _sampling(settings.llm_model)
    if settings.llm_api_key:
        kwargs["api_key"] = settings.llm_api_key
    return init_chat_model(settings.llm_model, **kwargs)


def llm_callbacks() -> list:
    """Tracing no Langfuse só com public key e secret key. Sem elas, a lista é vazia."""
    from app.core.observability import llm_callbacks as build_callbacks

    return build_callbacks()
