from typing import Optional

from langchain_ollama import ChatOllama

from app.core.config import Settings

_MODEL_CACHE: dict[tuple[str, str, float, int], ChatOllama] = {}


def _get_model(settings: Settings, model: str, temperature: float, num_predict: int) -> ChatOllama:
    key = (settings.ollama_base_url, model, temperature, num_predict)
    if key not in _MODEL_CACHE:
        _MODEL_CACHE[key] = ChatOllama(
            model=model,
        temperature=temperature,
        base_url=settings.ollama_base_url,
        num_predict=num_predict,
        keep_alive="30m",
    )
    return _MODEL_CACHE[key]


def get_generation_model(settings: Settings, temperature: Optional[float] = None) -> ChatOllama:
    """Return the cached llama3 client used only for final answer generation."""
    return _get_model(
        settings,
        settings.generation_model,
        settings.llm_temperature if temperature is None else temperature,
        settings.generation_num_predict,
    )


def get_evaluator_model(settings: Settings, temperature: float = 0.0) -> ChatOllama:
    """Return the cached phi3:mini client used for reranking and evaluation."""
    return _get_model(settings, settings.evaluator_model, temperature, settings.evaluator_num_predict)


def get_chat_model(settings: Settings, temperature: Optional[float] = None) -> ChatOllama:
    """Backward-compatible generation model accessor."""
    return get_generation_model(settings, temperature)
