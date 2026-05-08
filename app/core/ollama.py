import json
from dataclasses import dataclass
from json import JSONDecodeError
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.core.config import Settings


@dataclass(frozen=True)
class LocalModelErrorInfo:
    status_code: int
    status: str
    message: str
    code: str

    def as_payload(self) -> dict:
        return {"status": self.status, "message": self.message}


def is_ollama_running(settings: Settings, timeout_seconds: float = 1.5) -> bool:
    """Check whether the local Ollama server is reachable."""
    try:
        _ollama_tags(settings, timeout_seconds)
        return True
    except Exception:
        return False


def ollama_model_available(settings: Settings, model_name: str, timeout_seconds: float = 1.5) -> bool:
    """Return whether a model name appears in Ollama's local model list."""
    try:
        tags = _ollama_tags(settings, timeout_seconds)
    except Exception:
        return False
    models = tags.get("models", [])
    names = {str(model.get("name", "")).split(":")[0] for model in models if isinstance(model, dict)}
    full_names = {str(model.get("name", "")) for model in models if isinstance(model, dict)}
    return model_name in names or model_name in full_names


def describe_local_model_error(exc: Exception) -> LocalModelErrorInfo:
    """Convert local Ollama failures into safe API messages."""
    message = str(exc).lower()
    if isinstance(exc, (URLError, ConnectionError, TimeoutError)) or "connection refused" in message:
        return LocalModelErrorInfo(503, "error", "Ollama server unavailable", "ollama_unavailable")
    if isinstance(exc, HTTPError):
        return LocalModelErrorInfo(exc.code, "error", "Ollama request failed", "ollama_http_error")
    if isinstance(exc, (JSONDecodeError, ValueError)) or "json" in message:
        return LocalModelErrorInfo(502, "error", "Ollama returned a malformed response", "malformed_response")
    if "not found" in message or "pull" in message or "model" in message:
        return LocalModelErrorInfo(503, "error", "Required Ollama model unavailable", "ollama_model_unavailable")
    return LocalModelErrorInfo(500, "error", "Local inference failed", "local_inference_failed")


def _ollama_tags(settings: Settings, timeout_seconds: float) -> dict:
    url = settings.ollama_base_url.rstrip("/") + "/api/tags"
    request = Request(url, method="GET")
    with urlopen(request, timeout=timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8"))
