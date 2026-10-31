from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from app.api.router import router
from app.core.config import get_settings
from app.core.logger import debug_logger, log_event


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    if settings.rag_debug_logs and not debug_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("[RAG DEBUG] %(message)s"))
        debug_logger.addHandler(handler)
        debug_logger.setLevel(logging.DEBUG)
    if not settings.groq_key_configured:
        log_event(
            settings,
            "startup_warning",
            {"component": "groq", "message": "GROQ_API_KEY is not configured; hosted generation is unavailable."},
        )
    yield


app = FastAPI(
    title="Adaptive RAG System",
    description="A modular FastAPI app for adaptive retrieval-augmented generation.",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(router)


@app.exception_handler(HTTPException)
async def clean_http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    if isinstance(exc.detail, dict):
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(status_code=exc.status_code, content={"status": "error", "message": str(exc.detail)})


@app.get("/", summary="Root endpoint")
def root() -> dict:
    return {"message": "Adaptive RAG System is running."}
