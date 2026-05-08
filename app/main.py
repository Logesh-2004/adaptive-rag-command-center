from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from app.api.router import router
from app.core.config import get_settings
from app.core.logger import log_event
from app.core.ollama import is_ollama_running, ollama_model_available
from app.retrieval.retriever import get_cross_encoder

app = FastAPI(
    title="Adaptive RAG System",
    description="A modular FastAPI app for adaptive retrieval-augmented generation.",
    version="0.1.0",
)

app.include_router(router)


@app.exception_handler(HTTPException)
async def clean_http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    if isinstance(exc.detail, dict):
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(status_code=exc.status_code, content={"status": "error", "message": str(exc.detail)})


@app.on_event("startup")
def validate_runtime_environment() -> None:
    settings = get_settings()
    if not is_ollama_running(settings):
        log_event(
            settings,
            "startup_warning",
            {"component": "ollama", "message": "Ollama is not reachable; local inference features are degraded."},
        )
        return
    for model_name, role in (
        (settings.generation_model, "generation"),
        (settings.embedding_model, "embedding"),
    ):
        if not ollama_model_available(settings, model_name):
            log_event(
                settings,
                "startup_warning",
                {"component": "ollama", "model_role": role, "message": f"Ollama model '{model_name}' is not pulled."},
            )
    try:
        get_cross_encoder(settings)
        log_event(
            settings,
            "startup",
            {"component": "reranker", "model_role": "rerank", "message": f"CrossEncoder '{settings.rerank_model}' loaded."},
        )
    except Exception as exc:
        log_event(
            settings,
            "startup_warning",
            {"component": "reranker", "model_role": "rerank", "message": str(exc)},
        )


@app.get("/", summary="Root endpoint")
def root() -> dict:
    return {"message": "Adaptive RAG System is running."}
