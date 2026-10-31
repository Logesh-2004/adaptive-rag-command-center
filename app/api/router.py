import json
from time import perf_counter
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.core.config import get_settings, Settings
from app.core.logger import log_event
from app.ingestion.loader import ingest_documents
from app.retrieval.lexical_index import indexed_chunk_count, lexical_index_exists
from app.retrieval.retriever import clear_retrieval_cache, retrieve_adaptive
from app.evaluation.evaluator import evaluate_answer
from app.improvement.optimizer import run_improvement_cycle
from app.feedback.store import store_feedback
from app.pipeline import (
    RETRIEVAL_STRATEGY,
    PipelineError,
    load_index_or_raise,
    run_query_pipeline,
    score_trace,
    scores,
    texts,
)
from app.api.schemas import (
    IngestResponse,
    QueryRequest,
    QueryResponse,
    FeedbackRequest,
    StatusResponse,
    EvaluationRequest,
    EvaluationResponse,
    ImprovementResponse,
    RetrievalDebugRequest,
    RetrievalDebugResponse,
    TimingMetrics,
)

router = APIRouter(prefix="", tags=["adaptive-rag"])


def _event(event_type: str, payload: dict) -> str:
    return json.dumps({"type": event_type, **payload}, ensure_ascii=False) + "\n"


@router.get("/status", response_model=StatusResponse)
def status(settings: Settings = Depends(get_settings)) -> StatusResponse:
    return StatusResponse(
        status="running",
        generation_provider="Groq",
        generation_provider_configured=settings.generation_provider_configured,
        generation_model=settings.active_generation_model,
        retrieval_strategy=RETRIEVAL_STRATEGY,
        lexical_index_exists=lexical_index_exists(settings),
        indexed_chunks=indexed_chunk_count(settings),
    )


@router.post("/ingest", response_model=IngestResponse)
def ingest(settings: Settings = Depends(get_settings)) -> IngestResponse:
    start = perf_counter()
    try:
        summary = ingest_documents(settings)
        clear_retrieval_cache()
        latency_ms = (perf_counter() - start) * 1000
        log_event(
            settings,
            "ingest",
            {
                "status": "success",
                "latency_ms": latency_ms,
                "indexed_documents": summary["indexed_documents"],
                "chunks_created": summary["chunks_created"],
                "warnings": summary["warnings"],
            },
        )
        return IngestResponse(
            status="success",
            indexed_documents=summary["indexed_documents"],
            chunks_created=summary["chunks_created"],
            ingested_chunks=summary["chunks_created"],
            message=(
                "Documents ingested and BM25 lexical index updated."
                if not summary["warnings"]
                else f"Documents ingested with {len(summary['warnings'])} unreadable file warning(s)."
            ),
            warnings=summary["warnings"],
        )
    except FileNotFoundError as exc:
        log_event(settings, "ingest_failure", {"status": "error", "message": str(exc)})
        raise HTTPException(status_code=404, detail={"status": "error", "message": str(exc)})
    except Exception as exc:
        log_event(settings, "ingest_failure", {"status": "error", "message": "Document ingestion failed.", "error_type": type(exc).__name__})
        raise HTTPException(status_code=500, detail={"status": "error", "message": "Document ingestion failed."})


@router.post("/query", response_model=QueryResponse)
def query(request: QueryRequest, settings: Settings = Depends(get_settings)) -> QueryResponse:
    try:
        for event_type, payload in run_query_pipeline(request.query, settings, stream=False):
            if event_type == "done":
                return QueryResponse(**payload)
    except PipelineError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_payload())
    raise HTTPException(status_code=500, detail={"status": "error", "message": "Query pipeline ended without an answer."})


@router.post("/query/stream")
def query_stream(request: QueryRequest, settings: Settings = Depends(get_settings)) -> StreamingResponse:
    def events():
        try:
            for event_type, payload in run_query_pipeline(request.query, settings, stream=True):
                yield _event(event_type, payload)
        except PipelineError as exc:
            yield _event("error", {"message": exc.message, "error_code": exc.error_code})

    return StreamingResponse(events(), media_type="application/x-ndjson")


@router.post("/evaluate", response_model=EvaluationResponse)
def evaluate(request: EvaluationRequest, settings: Settings = Depends(get_settings)) -> EvaluationResponse:
    start = perf_counter()
    try:
        evaluation = evaluate_answer(request.query, request.context, request.answer, settings)
        log_event(
            settings,
            "evaluation",
            {
                "query": request.query,
                "status": "success",
                "latency_ms": (perf_counter() - start) * 1000,
                "retrieved_document_count": len(request.context),
                "faithfulness": evaluation.get("faithfulness"),
                "relevance": evaluation.get("relevance"),
                "grounding_score": evaluation.get("grounding_score"),
                "grounding": evaluation.get("grounding"),
                "grounded": evaluation.get("grounded"),
                "hallucination_risk": evaluation.get("hallucination_risk"),
                "evaluation": evaluation,
            },
        )
        return EvaluationResponse(status="success", **evaluation)
    except Exception:
        log_event(
            settings,
            "evaluation_failure",
            {
                "status": "warning",
                "latency_ms": (perf_counter() - start) * 1000,
                "error_code": "evaluation_failed",
                "message": "Lexical evaluation failed.",
            },
        )
        return EvaluationResponse(status="warning", message="Evaluation unavailable")


@router.post("/improve", response_model=ImprovementResponse)
def improve(settings: Settings = Depends(get_settings)) -> ImprovementResponse:
    start = perf_counter()
    try:
        summary, weak_records, suggestions = run_improvement_cycle(settings)
    except Exception as exc:
        log_event(settings, "improvement_failure", {"status": "error", "error_type": type(exc).__name__, "error": str(exc)[:300]})
        raise HTTPException(status_code=500, detail={"status": "error", "message": "Improvement analysis failed."})
    log_event(
        settings,
        "improvement",
        {
            "latency_ms": (perf_counter() - start) * 1000,
            "weak_records": weak_records,
            "suggestions": suggestions,
        },
    )
    return ImprovementResponse(summary=summary, weak_records=weak_records, suggestions=suggestions)


@router.post("/debug/retrieval", response_model=RetrievalDebugResponse)
def debug_retrieval_endpoint(request: RetrievalDebugRequest, settings: Settings = Depends(get_settings)) -> RetrievalDebugResponse:
    start = perf_counter()
    timings = TimingMetrics()
    try:
        lexical_index = load_index_or_raise(settings)
        initial_docs, ranked_docs, trace = retrieve_adaptive(request.query, lexical_index, settings)
    except PipelineError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_payload())
    except Exception:
        log_event(settings, "debug_retrieval_failure", {"status": "error", "message": "Debug retrieval failed"})
        raise HTTPException(status_code=500, detail={"status": "error", "message": "Debug retrieval failed"})

    timings.retrieval_ms = float(trace.get("bm25_search_ms", 0.0))
    timings.ranking_ms = float(trace.get("ranking_ms", 0.0))
    initial_texts = texts(initial_docs)
    ranked_texts = texts(ranked_docs)
    timings.total_ms = (perf_counter() - start) * 1000
    log_event(
        settings,
        "debug_retrieval",
        {
            "query": request.query,
            "status": "success",
            "latency_ms": timings.total_ms,
            "retrieved_document_count": len(initial_texts),
            "ranked_document_count": len(ranked_texts),
            "timings": timings.model_dump(),
        },
    )
    return RetrievalDebugResponse(
        query=request.query,
        initial_documents=initial_texts,
        ranked_documents=ranked_texts,
        relevance_scores=scores(ranked_docs),
        retrieval_score_trace=score_trace(ranked_docs),
        retrieval_strategy=RETRIEVAL_STRATEGY,
        trace=trace,
        timings=timings,
    )


@router.post("/feedback")
def feedback(request: FeedbackRequest, settings: Settings = Depends(get_settings)) -> dict:
    start = perf_counter()
    try:
        store_feedback(request, settings)
    except Exception as exc:
        log_event(settings, "feedback_failure", {"status": "error", "error_type": type(exc).__name__, "error": str(exc)[:300]})
        raise HTTPException(status_code=500, detail={"status": "error", "message": "Feedback could not be saved."})
    log_event(
        settings,
        "feedback",
        {"latency_ms": (perf_counter() - start) * 1000, "query": request.query, "rating": request.rating},
    )
    return {"status": "success", "message": "Feedback recorded."}
