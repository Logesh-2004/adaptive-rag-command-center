import json
import re
from time import perf_counter
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.core.config import get_settings, Settings
from app.core.llm import describe_generation_error
from app.core.logger import log_event
from app.ingestion.loader import ingest_documents
from app.retrieval.lexical_index import indexed_chunk_count, load_lexical_index, lexical_index_exists
from app.generation.context import compress_context
from app.retrieval.retriever import clear_retrieval_cache, corrective_retrieve, retrieve_adaptive
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


def _load_lexical_index_or_404(settings: Settings):
    if not lexical_index_exists(settings):
        raise HTTPException(
            status_code=404,
            detail={"status": "error", "message": "BM25 index not found. Run /ingest first."},
        )
    return load_lexical_index(settings)


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
            "bm25_score": doc.metadata.get("bm25_score"),
            "bm25_norm": doc.metadata.get("bm25_norm"),
            "lexical_overlap": doc.metadata.get("lexical_overlap"),
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


def _log_retrieval_debug(settings: Settings, query: str, initial_docs, ranked_docs) -> None:
    payload = {
        "query": query,
        "retrieved_context": _texts(initial_docs),
        "ranked_chunks": [
            {
                "rank": index,
                "relevance_score": doc.metadata.get("relevance_score"),
                "source": doc.metadata.get("source"),
                "content": doc.page_content,
            }
            for index, doc in enumerate(ranked_docs, start=1)
        ],
    }
    print("[RAG DEBUG] retrieval_to_generation", json.dumps(payload, ensure_ascii=False))
    log_event(settings, "retrieval_to_generation_debug", payload)


@router.get("/status", response_model=StatusResponse)
def status() -> StatusResponse:
    settings = get_settings()
    return StatusResponse(
        status="running",
        generation_provider="Groq",
        generation_provider_configured=settings.generation_provider_configured,
        generation_model=settings.active_generation_model,
        retrieval_strategy="BM25 lexical ranking",
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
        log_event(settings, "ingest_failure", {"status": "error", "message": "Document ingestion failed."})
        raise HTTPException(status_code=500, detail={"status": "error", "message": "Document ingestion failed."})


@router.post("/query", response_model=QueryResponse)
def query(request: QueryRequest, settings: Settings = Depends(get_settings)) -> QueryResponse:
    start = perf_counter()
    timings = TimingMetrics()
    warnings = []
    evaluation = None
    initial_docs = []
    documents = []
    try:
        retrieval_start = perf_counter()
        lexical_index = _load_lexical_index_or_404(settings)
        initial_docs, documents, trace = retrieve_adaptive(request.query, lexical_index, settings)
        documents, compression = compress_context(documents)
        trace["context_compression"] = compression
        timings.retrieval_ms = float(trace.get("bm25_search_ms", (perf_counter() - retrieval_start) * 1000))
    except HTTPException:
        raise
    except Exception as exc:
        error_message = "Lexical retrieval failed."
        log_event(
            settings,
            "query_failure",
            {"status": "error", "stage": "retrieve", "message": error_message},
        )
        raise HTTPException(status_code=500, detail={"status": "error", "message": error_message})

    timings.ranking_ms = float(trace.get("ranking_ms", 0.0))

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
        error = describe_generation_error(exc, settings)
        warnings.append(error.message)
        log_event(
            settings,
            "generation_failure",
            {"stage": "generate_or_grounding", "error_code": error.code, "message": error.message},
        )

    if generated:
        evaluation_start = perf_counter()
        try:
            evaluation = log_evaluation(request.query, documents, answer, settings)
            timings.evaluation_ms = (perf_counter() - evaluation_start) * 1000
        except Exception as exc:
            timings.evaluation_ms = (perf_counter() - evaluation_start) * 1000
            warnings.append("Lexical evaluation unavailable")
            log_event(
                settings,
                "evaluation_failure",
                {
                    "stage": "initial_evaluation",
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:300],
                },
            )

        if evaluation and (
            evaluation.get("hallucination_risk") == "high"
            or evaluation.get("retrieval_confidence", 1.0) < settings.retrieval_confidence_threshold
        ):
            retry_start = perf_counter()
            try:
                retry_initial, retry_docs, trace = corrective_retrieve(request.query, lexical_index, settings, trace)
                timings.retrieval_ms = float(trace.get("bm25_search_ms", timings.retrieval_ms))
                timings.ranking_ms = float(trace.get("ranking_ms", timings.ranking_ms))
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
                warnings.append("Corrective retry unavailable; kept the first answer")
                log_event(
                    settings,
                    "corrective_retry_failure",
                    {
                        "stage": "corrective_retrieval_or_generation",
                        "error_type": type(exc).__name__,
                        "error": str(exc)[:300],
                    },
                )
            finally:
                timings.evaluation_ms += (perf_counter() - retry_start) * 1000

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
            "num_ranked": len(documents),
            "warning": "; ".join(dict.fromkeys(warnings)) if warnings else None,
            "evaluation": evaluation,
            "timings": timings.model_dump(),
            "grounding_score": evaluation.get("grounding_score") if evaluation else None,
            "grounding": evaluation.get("grounding") if evaluation else None,
            "grounded": evaluation.get("grounded") if evaluation else None,
            "hallucination_risk": evaluation.get("hallucination_risk") if evaluation else None,
            "retrieval_strategy": "BM25 lexical ranking",
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
        retrieval_strategy="BM25 lexical ranking",
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

        try:
            retrieval_start = perf_counter()
            lexical_index = _load_lexical_index_or_404(settings)
            initial_docs, documents, trace = retrieve_adaptive(request.query, lexical_index, settings)
            documents, compression = compress_context(documents)
            trace["context_compression"] = compression
            timings.retrieval_ms = float(trace.get("bm25_search_ms", (perf_counter() - retrieval_start) * 1000))
            yield _event("retrieval", {"timings": timings.model_dump(), "sources": _texts(initial_docs)})

            timings.ranking_ms = float(trace.get("ranking_ms", 0.0))
            _log_retrieval_debug(settings, request.query, initial_docs, documents)
            if not documents:
                warnings.append("No retrieved context available")
            yield _event(
                "rank",
                {
                    "timings": timings.model_dump(),
                    "sources": _texts(documents),
                    "relevance_scores": _scores(documents),
                    "retrieval_score_trace": _score_trace(documents),
                    "retrieval_strategy": "BM25 lexical ranking",
                    "trace": trace,
                },
            )
        except HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
            yield _event("error", {"message": detail.get("message", "Lexical retrieval failed."), "error_code": "retrieval_failed"})
            return
        except Exception:
            yield _event("error", {"message": "Lexical retrieval failed.", "error_code": "retrieval_failed"})
            return

        try:
            generation_start = perf_counter()
            for token in stream_answer(request.query, documents, settings):
                answer_parts.append(token)
                timings.generation_ms = (perf_counter() - generation_start) * 1000
                yield _event("token", {"token": token, "timings": timings.model_dump()})
            answer = "".join(answer_parts).strip()
            if not answer:
                # Some compatible gateways can finish a stream without a content delta.
                # Retry once without streaming so the UI receives either an answer or a
                # useful generation error instead of an empty successful response.
                answer = generate_answer(request.query, documents, settings)
                answer_parts.append(answer)
                timings.generation_ms = (perf_counter() - generation_start) * 1000
                yield _event("token", {"token": answer, "timings": timings.model_dump()})
            timings.generation_ms = (perf_counter() - generation_start) * 1000
        except Exception as exc:
            error = describe_generation_error(exc, settings)
            log_event(
                settings,
                "generation_failure",
                {"stage": "stream_generate", "error_code": error.code, "message": error.message},
            )
            yield _event("error", {"message": error.message, "error_code": error.code})
            return

        evaluation = None
        evaluation_start = perf_counter()
        try:
            evaluation = log_evaluation(request.query, documents, answer, settings)
            timings.evaluation_ms = (perf_counter() - evaluation_start) * 1000
        except Exception as exc:
            timings.evaluation_ms = (perf_counter() - evaluation_start) * 1000
            warnings.append("Lexical evaluation unavailable")
            log_event(
                settings,
                "evaluation_failure",
                {
                    "stage": "initial_evaluation_stream",
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:300],
                },
            )

        if evaluation and (
            evaluation.get("hallucination_risk") == "high"
            or evaluation.get("retrieval_confidence", 1.0) < settings.retrieval_confidence_threshold
        ):
            retry_start = perf_counter()
            try:
                retry_initial, retry_docs, trace = corrective_retrieve(request.query, lexical_index, settings, trace)
                timings.retrieval_ms = float(trace.get("bm25_search_ms", timings.retrieval_ms))
                timings.ranking_ms = float(trace.get("ranking_ms", timings.ranking_ms))
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
                warnings.append("Corrective retry unavailable; kept the first answer")
                log_event(
                    settings,
                    "corrective_retry_failure",
                    {
                        "stage": "corrective_retrieval_or_generation_stream",
                        "error_type": type(exc).__name__,
                        "error": str(exc)[:300],
                    },
                )
            finally:
                timings.evaluation_ms += (perf_counter() - retry_start) * 1000

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
            retrieval_strategy="BM25 lexical ranking",
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
                "num_ranked": len(documents),
                "warning": "; ".join(dict.fromkeys(warnings)) if warnings else None,
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
    try:
        retrieval_start = perf_counter()
        lexical_index = _load_lexical_index_or_404(settings)
        initial_docs, ranked_docs, trace = retrieve_adaptive(request.query, lexical_index, settings)
        timings.retrieval_ms = float(trace.get("bm25_search_ms", (perf_counter() - retrieval_start) * 1000))
        timings.ranking_ms = float(trace.get("ranking_ms", 0.0))
        initial_texts = _texts(initial_docs)
        ranked_texts = _texts(ranked_docs)
        relevance_scores = _scores(ranked_docs)
        timings.total_ms = (perf_counter() - start) * 1000
        log_event(
            settings,
            "debug_retrieval",
            {
                "query": request.query,
                "status": "warning" if warning else "success",
                "latency_ms": (perf_counter() - start) * 1000,
                "retrieved_document_count": len(initial_texts),
                "ranked_document_count": len(ranked_texts),
                "timings": timings.model_dump(),
                "warning": warning,
            },
        )
        return RetrievalDebugResponse(
            query=request.query,
            initial_documents=initial_texts,
            ranked_documents=ranked_texts,
           relevance_scores=relevance_scores,
            retrieval_score_trace=_score_trace(ranked_docs),
            retrieval_strategy="BM25 lexical ranking",
            trace=trace,
            timings=timings,
            warning=warning,
        )
    except HTTPException:
        raise
    except Exception as exc:
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
