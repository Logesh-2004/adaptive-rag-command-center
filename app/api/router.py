import json
import re
from time import perf_counter
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.core.config import get_settings, Settings
from app.core.logger import log_event
from app.core.ollama import describe_local_model_error, is_ollama_running
from app.ingestion.loader import ingest_documents
from app.retrieval.vector_store import indexed_document_count, load_vector_store, vector_store_exists
from app.generation.context import compress_context
from app.retrieval.retriever import clear_retrieval_cache, corrective_retrieve, retrieve_adaptive, rerank_documents
from app.generation.answer import generate_answer, stream_answer
from app.evaluation.evaluator import log_evaluation, evaluate_answer
from app.improvement.optimizer import run_improvement_cycle
from app.feedback.store import store_feedback
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


def _clean_model_http_error(exc: Exception, settings: Settings, event_type: str) -> HTTPException:
    error = describe_local_model_error(exc)
    log_event(settings, event_type, {"status": "error", "error_code": error.code, "message": error.message})
    return HTTPException(status_code=error.status_code, detail=error.as_payload())


def _load_vector_store_or_404(settings: Settings):
    if not vector_store_exists(settings):
        raise HTTPException(
            status_code=404,
            detail={"status": "error", "message": "Vector store not found. Run /ingest first."},
        )
    return load_vector_store(settings)


def _clean_output_text(text: str) -> str:
    text = re.sub(r"(?m)^\s*[-*]\s*$", "", text)
    text = re.sub(r"(?m)^\s*#{1,6}\s*", "", text)
    text = re.sub(r"\|", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _texts(documents):
    return [_clean_output_text(doc.page_content) for doc in documents]


def _scores(documents):
    return [float(doc.metadata.get("final_fused_score", doc.metadata.get("relevance_score", 0.0))) for doc in documents]


def _score_trace(documents):
    return [
        {
            "source": doc.metadata.get("source"),
            "vector_score": doc.metadata.get("vector_score"),
            "vector_norm": doc.metadata.get("vector_norm"),
            "bm25_score": doc.metadata.get("keyword_score"),
            "bm25_norm": doc.metadata.get("keyword_norm"),
            "rerank_score": doc.metadata.get("rerank_score"),
            "rerank_norm": doc.metadata.get("rerank_norm"),
            "semantic_similarity": doc.metadata.get("semantic_similarity"),
            "metadata_boost": doc.metadata.get("metadata_boost"),
            "intent_boost": doc.metadata.get("intent_boost"),
            "quality_score": doc.metadata.get("quality_score"),
            "final_fused_score": doc.metadata.get("final_fused_score"),
            "retrieval_channels": doc.metadata.get("retrieval_channels", []),
        }
        for doc in documents
    ]


def _event(event_type: str, payload: dict) -> str:
    return json.dumps({"type": event_type, **payload}, ensure_ascii=False) + "\n"


def _log_retrieval_debug(settings: Settings, query: str, initial_docs, reranked_docs) -> None:
    payload = {
        "query": query,
        "retrieved_context": _texts(initial_docs),
        "reranked_chunks": [
            {
                "rank": index,
                "relevance_score": doc.metadata.get("relevance_score"),
                "source": doc.metadata.get("source"),
                "content": doc.page_content,
            }
            for index, doc in enumerate(reranked_docs, start=1)
        ],
    }
    print("[RAG DEBUG] retrieval_to_generation", json.dumps(payload, ensure_ascii=False))
    log_event(settings, "retrieval_to_generation_debug", payload)


def _log_raw_generation_response(settings: Settings, answer: str) -> None:
    payload = {"raw_llm_response": answer}
    print("[RAG DEBUG] raw_llm_response", json.dumps(payload, ensure_ascii=False))
    log_event(settings, "generation_response_debug", payload)


@router.get("/status", response_model=StatusResponse)
def status() -> StatusResponse:
    settings = get_settings()
    ollama_running = is_ollama_running(settings)
    return StatusResponse(
        status="running",
        llm_provider="ollama",
        generation_model=settings.generation_model,
        evaluator_model=settings.evaluator_model,
        rerank_model=settings.rerank_model,
        vector_db_exists=vector_store_exists(settings),
        indexed_documents=indexed_document_count(settings),
        embedding_model=settings.embedding_model,
        ollama_running=ollama_running,
    )


@router.post("/ingest", response_model=IngestResponse)
def ingest(settings: Settings = Depends(get_settings)) -> IngestResponse:
    start = perf_counter()
    if not is_ollama_running(settings):
        log_event(
            settings,
            "ingest_failure",
            {"status": "error", "message": "Ollama server unavailable", "latency_ms": (perf_counter() - start) * 1000},
        )
        raise HTTPException(status_code=503, detail={"status": "error", "message": "Ollama server unavailable"})
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
            },
        )
        return IngestResponse(
            status="success",
            indexed_documents=summary["indexed_documents"],
            chunks_created=summary["chunks_created"],
            ingested_chunks=summary["chunks_created"],
            message="Documents ingested and vector index updated.",
        )
    except FileNotFoundError as exc:
        log_event(settings, "ingest_failure", {"status": "error", "message": str(exc)})
        raise HTTPException(status_code=404, detail={"status": "error", "message": str(exc)})
    except Exception as exc:
        error = describe_local_model_error(exc)
        log_event(settings, "ingest_failure", {"status": "error", "message": error.message, "error_code": error.code})
        raise HTTPException(status_code=error.status_code, detail=error.as_payload())


@router.post("/query", response_model=QueryResponse)
def query(request: QueryRequest, settings: Settings = Depends(get_settings)) -> QueryResponse:
    start = perf_counter()
    timings = TimingMetrics()
    warnings = []
    evaluation = None
    initial_docs = []
    documents = []
    if not is_ollama_running(settings):
        warning = "Ollama server unavailable"
        log_event(
            settings,
            "query",
            {
                "status": "warning",
                "query": request.query,
                "latency_ms": (perf_counter() - start) * 1000,
                "num_retrieved": 0,
                "num_reranked": 0,
                "warning": warning,
            },
        )
        return QueryResponse(
            query=request.query,
            answer="Local inference unavailable; start Ollama and ensure models are pulled.",
            sources=[],
            warning=warning,
            evaluation=None,
            timings=TimingMetrics(total_ms=(perf_counter() - start) * 1000),
            grounding_score=0.0,
            grounding=0.0,
            grounded=False,
            hallucination_risk="high",
            relevance_scores=[],
            rerank_model=settings.rerank_model,
        )
    try:
        retrieval_start = perf_counter()
        vector_store = _load_vector_store_or_404(settings)
        initial_docs, documents, trace = retrieve_adaptive(request.query, vector_store, settings)
        documents, compression = compress_context(documents)
        trace["context_compression"] = compression
        timings.retrieval_ms = (perf_counter() - retrieval_start) * 1000
    except HTTPException:
        raise
    except Exception as exc:
        error = describe_local_model_error(exc)
        log_event(
            settings,
            "query_failure",
            {"status": "error", "stage": "retrieve", "message": error.message, "error_code": error.code},
        )
        raise HTTPException(status_code=error.status_code, detail=error.as_payload())

    timings.rerank_ms = 0.0

    if not documents:
        warnings.append("No retrieved context available")
    _log_retrieval_debug(settings, request.query, initial_docs, documents)

    answer = "Generation unavailable; returning retrieved documents."
    generated = False
    try:
        generation_start = perf_counter()
        answer = generate_answer(request.query, documents, settings)
        timings.generation_ms = (perf_counter() - generation_start) * 1000
        generated = True
    except Exception as exc:
        timings.generation_ms = (perf_counter() - generation_start) * 1000 if "generation_start" in locals() else 0.0
        error = describe_local_model_error(exc)
        warnings.append(error.message)
        log_event(
            settings,
            "ollama_failure",
            {"stage": "generate_or_grounding", "error_code": error.code, "message": error.message},
        )

    if generated:
        try:
            evaluation_start = perf_counter()
            evaluation = log_evaluation(request.query, documents, answer, settings)
            timings.evaluation_ms = (perf_counter() - evaluation_start) * 1000
            if evaluation.get("hallucination_risk") == "high" or evaluation.get("retrieval_confidence", 1.0) < settings.retrieval_confidence_threshold:
                retry_start = perf_counter()
                retry_initial, retry_docs, trace = corrective_retrieve(request.query, vector_store, settings, trace)
                retry_docs, retry_compression = compress_context(retry_docs)
                retry_answer = generate_answer(request.query, retry_docs, settings)
                retry_evaluation = log_evaluation(request.query, retry_docs, retry_answer, settings)
                if retry_evaluation.get("faithfulness", 0.0) >= evaluation.get("faithfulness", 0.0):
                    initial_docs = retry_initial
                    documents = retry_docs
                    answer = retry_answer
                    evaluation = retry_evaluation
                    trace["context_compression"] = retry_compression
                    warnings.append("Corrective retrieval retry improved the answer")
                timings.evaluation_ms += (perf_counter() - retry_start) * 1000
        except Exception as exc:
            timings.evaluation_ms = (perf_counter() - evaluation_start) * 1000 if "evaluation_start" in locals() else 0.0
            error = describe_local_model_error(exc)
            warnings.append("Evaluation unavailable")
            log_event(
                settings,
                "evaluation_failure",
                {"error_code": error.code, "message": error.message},
            )

    latency_ms = (perf_counter() - start) * 1000
    timings.total_ms = latency_ms
    sources = _texts(documents)
    relevance_scores = _scores(documents)
    log_event(
        settings,
        "query",
        {
            "status": "warning" if warnings else "success",
            "query": request.query,
            "latency_ms": latency_ms,
            "num_retrieved": len(initial_docs),
            "num_reranked": len(documents),
            "warning": "; ".join(dict.fromkeys(warnings)) if warnings else None,
            "evaluation": evaluation,
            "timings": timings.model_dump(),
            "grounding_score": evaluation.get("grounding_score") if evaluation else None,
            "grounding": evaluation.get("grounding") if evaluation else None,
            "grounded": evaluation.get("grounded") if evaluation else None,
            "hallucination_risk": evaluation.get("hallucination_risk") if evaluation else None,
            "rerank_model": settings.rerank_model,
        },
    )
    return QueryResponse(
        query=request.query,
        answer=answer,
        sources=sources,
        warning="; ".join(dict.fromkeys(warnings)) if warnings else None,
        evaluation=evaluation,
        timings=timings,
        grounding_score=evaluation.get("grounding_score") if evaluation else None,
        grounding=evaluation.get("grounding") if evaluation else None,
        grounded=evaluation.get("grounded") if evaluation else None,
        hallucination_risk=evaluation.get("hallucination_risk") if evaluation else None,
        relevance_scores=relevance_scores,
        retrieval_score_trace=_score_trace(documents),
        rerank_model=settings.rerank_model,
        trace=trace,
    )


@router.post("/query/stream")
def query_stream(request: QueryRequest, settings: Settings = Depends(get_settings)) -> StreamingResponse:
    def events():
        start = perf_counter()
        timings = TimingMetrics()
        warnings = []
        initial_docs = []
        documents = []
        answer_parts = []

        if not is_ollama_running(settings):
            yield _event("error", {"message": "Ollama server unavailable"})
            return

        try:
            retrieval_start = perf_counter()
            vector_store = _load_vector_store_or_404(settings)
            initial_docs, documents, trace = retrieve_adaptive(request.query, vector_store, settings)
            documents, compression = compress_context(documents)
            trace["context_compression"] = compression
            timings.retrieval_ms = (perf_counter() - retrieval_start) * 1000
            yield _event("retrieval", {"timings": timings.model_dump(), "sources": _texts(initial_docs)})

            rerank_start = perf_counter()
            timings.rerank_ms = (perf_counter() - rerank_start) * 1000
            _log_retrieval_debug(settings, request.query, initial_docs, documents)
            if not documents:
                warnings.append("No retrieved context available")
            yield _event(
                "rerank",
                {
                    "timings": timings.model_dump(),
                    "sources": _texts(documents),
                    "relevance_scores": _scores(documents),
                    "retrieval_score_trace": _score_trace(documents),
                    "rerank_model": settings.rerank_model,
                    "trace": trace,
                },
            )
        except Exception as exc:
            error = describe_local_model_error(exc)
            yield _event("error", {"message": error.message, "error_code": error.code})
            return

        try:
            generation_start = perf_counter()
            for token in stream_answer(request.query, documents, settings):
                answer_parts.append(token)
                timings.generation_ms = (perf_counter() - generation_start) * 1000
                yield _event("token", {"token": token, "timings": timings.model_dump()})
            answer = "".join(answer_parts).strip()
            _log_raw_generation_response(settings, answer)
            timings.generation_ms = (perf_counter() - generation_start) * 1000
        except Exception as exc:
            error = describe_local_model_error(exc)
            yield _event("error", {"message": error.message, "error_code": error.code})
            return

        evaluation = None
        try:
            evaluation_start = perf_counter()
            evaluation = log_evaluation(request.query, documents, answer, settings)
            timings.evaluation_ms = (perf_counter() - evaluation_start) * 1000
            if evaluation.get("hallucination_risk") == "high" or evaluation.get("retrieval_confidence", 1.0) < settings.retrieval_confidence_threshold:
                retry_initial, retry_docs, trace = corrective_retrieve(request.query, vector_store, settings, trace)
                retry_docs, retry_compression = compress_context(retry_docs)
                retry_answer = generate_answer(request.query, retry_docs, settings)
                retry_evaluation = log_evaluation(request.query, retry_docs, retry_answer, settings)
                if retry_evaluation.get("faithfulness", 0.0) >= evaluation.get("faithfulness", 0.0):
                    initial_docs = retry_initial
                    documents = retry_docs
                    answer = retry_answer
                    evaluation = retry_evaluation
                    trace["context_compression"] = retry_compression
                    warnings.append("Corrective retrieval retry improved the answer")
        except Exception as exc:
            warnings.append(f"Evaluation unavailable: {describe_local_model_error(exc).message}")

        timings.total_ms = (perf_counter() - start) * 1000
        response = QueryResponse(
            query=request.query,
            answer=answer,
            sources=_texts(documents),
            warning="; ".join(dict.fromkeys(warnings)) if warnings else None,
            evaluation=evaluation,
            timings=timings,
            grounding_score=evaluation.get("grounding_score") if evaluation else None,
            grounding=evaluation.get("grounding") if evaluation else None,
            grounded=evaluation.get("grounded") if evaluation else None,
            hallucination_risk=evaluation.get("hallucination_risk") if evaluation else None,
            relevance_scores=_scores(documents),
            retrieval_score_trace=_score_trace(documents),
            rerank_model=settings.rerank_model,
            trace=trace,
        )
        log_event(
            settings,
            "query_stream",
            {
                "status": "warning" if warnings else "success",
                "query": request.query,
                "latency_ms": timings.total_ms,
                "num_retrieved": len(initial_docs),
                "num_reranked": len(documents),
                "evaluation": evaluation,
                "timings": timings.model_dump(),
            },
        )
        yield _event("done", response.model_dump())

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
    except Exception as exc:
        error = describe_local_model_error(exc)
        log_event(
            settings,
            "evaluation_failure",
            {
                "status": "warning",
                "latency_ms": (perf_counter() - start) * 1000,
                "error_code": error.code,
                "message": error.message,
            },
        )
        return EvaluationResponse(status="warning", message="Evaluation unavailable")


@router.post("/improve", response_model=ImprovementResponse)
def improve(settings: Settings = Depends(get_settings)) -> ImprovementResponse:
    start = perf_counter()
    try:
        summary, weak_records, suggestions = run_improvement_cycle(settings)
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
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/debug/retrieval", response_model=RetrievalDebugResponse)
def debug_retrieval_endpoint(request: RetrievalDebugRequest, settings: Settings = Depends(get_settings)) -> RetrievalDebugResponse:
    start = perf_counter()
    timings = TimingMetrics()
    warning = None
    if not is_ollama_running(settings):
        warning = "Ollama server unavailable"
        log_event(
            settings,
            "debug_retrieval",
            {
                "query": request.query,
                "status": "warning",
                "latency_ms": (perf_counter() - start) * 1000,
                "retrieved_document_count": 0,
                "reranked_document_count": 0,
                "warning": warning,
            },
        )
        timings.total_ms = (perf_counter() - start) * 1000
        return RetrievalDebugResponse(
            query=request.query,
            initial_documents=[],
            reranked_documents=[],
            relevance_scores=[],
            retrieval_score_trace=[],
            rerank_model=settings.rerank_model,
            timings=timings,
            warning=warning,
        )
    try:
        retrieval_start = perf_counter()
        vector_store = _load_vector_store_or_404(settings)
        initial_docs, reranked_docs, trace = retrieve_adaptive(request.query, vector_store, settings)
        timings.retrieval_ms = (perf_counter() - retrieval_start) * 1000
        timings.rerank_ms = 0.0
        initial_texts = _texts(initial_docs)
        reranked_texts = _texts(reranked_docs)
        relevance_scores = _scores(reranked_docs)
        timings.total_ms = (perf_counter() - start) * 1000
        log_event(
            settings,
            "debug_retrieval",
            {
                "query": request.query,
                "status": "warning" if warning else "success",
                "latency_ms": (perf_counter() - start) * 1000,
                "retrieved_document_count": len(initial_texts),
                "reranked_document_count": len(reranked_texts),
                "timings": timings.model_dump(),
                "warning": warning,
            },
        )
        return RetrievalDebugResponse(
            query=request.query,
            initial_documents=initial_texts,
            reranked_documents=reranked_texts,
           relevance_scores=relevance_scores,
            retrieval_score_trace=_score_trace(reranked_docs),
            rerank_model=settings.rerank_model,
            trace=trace,
            timings=timings,
            warning=warning,
        )
    except HTTPException:
        raise
    except Exception as exc:
        error = describe_local_model_error(exc)
        if error.code != "local_inference_failed":
            raise _clean_model_http_error(exc, settings, "ollama_failure")
        log_event(settings, "debug_retrieval_failure", {"status": "error", "message": "Debug retrieval failed"})
        raise HTTPException(status_code=500, detail={"status": "error", "message": "Debug retrieval failed"})


@router.post("/feedback")
def feedback(request: FeedbackRequest, settings: Settings = Depends(get_settings)) -> dict:
    start = perf_counter()
    try:
        store_feedback(request, settings)
        log_event(
            settings,
            "feedback",
            {"latency_ms": (perf_counter() - start) * 1000, "query": request.query, "rating": request.rating},
        )
        return {"status": "success", "message": "Feedback recorded."}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
