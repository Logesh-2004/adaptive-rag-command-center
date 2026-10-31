from dataclasses import dataclass

from app.core.config import Settings


@dataclass(frozen=True)
class GenerationErrorInfo:
    status_code: int
    status: str
    message: str
    code: str

    def as_payload(self) -> dict[str, str]:
        return {"status": self.status, "message": self.message, "error_code": self.code}


def describe_generation_error(exc: Exception, settings: Settings) -> GenerationErrorInfo:
    """Convert Groq failures into safe, user-facing API errors."""
    if not settings.groq_key_configured:
        return GenerationErrorInfo(503, "error", "Add GROQ_API_KEY to the backend environment to use Groq.", "groq_api_key_missing")

    response = getattr(exc, "response", None)
    status_code = getattr(exc, "status_code", None) or getattr(response, "status_code", None)
    if status_code == 429:
        return GenerationErrorInfo(429, "error", "Groq rate limit reached. Please try again later.", "groq_rate_limited")
    if status_code in (401, 403):
        return GenerationErrorInfo(503, "error", "Groq rejected the API key or model access. Check GROQ_API_KEY and GROQ_MODEL.", "groq_auth_error")
    if status_code == 400:
        return GenerationErrorInfo(502, "error", "Groq rejected the request. Check GROQ_MODEL and the generation settings.", "groq_request_error")
    if isinstance(status_code, int) and status_code >= 500:
        return GenerationErrorInfo(503, "error", "Groq is temporarily unavailable. Please try again shortly.", "groq_unavailable")
    return GenerationErrorInfo(502, "error", "Groq generation failed. Check the provider configuration and try again.", "groq_generation_failed")
