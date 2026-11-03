"""The query pipeline shared by /query and /query/stream.

run_query_pipeline yields (event_type, payload) pairs for each stage: "retrieval", "rank",
"token" (streaming only), and finally "done" with a QueryResponse payload. It raises
PipelineError when the request cannot be answered, so each endpoint can report the failure
in its own format.
"""

import re
from time import perf_counter
from typing import Iterator

from langchain_core.documents import Document

from app.api.schemas import QueryResponse, TimingMetrics
from app.core.config import Settings
from app.core.llm import describe_generation_error
from app.core.logger import log_debug_event, log_event
from app.evaluation.evaluator import log_evaluation
from app.generation.answer import generate_answer, stream_answer
from app.generation.context import compress_context
from app.retrieval.lexical_index import index_building, lexical_index_exists, load_lexical_index
from app.retrieval.retriever import corrective_retrieve, retrieve_adaptive

RETRIEVAL_STRATEGY = "BM25 lexical ranking"
GENERATION_UNAVAILABLE = "Generation unavailable; returning retrieved documents."


class PipelineError(Exception):
    def __init__(self, status_code: int, message: str, error_code: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.error_code = error_code

    def as_payload(self) -> dict:
        return {"status": "error", "message": self.message, "error_code": self.error_code}


def load_index_or_raise(settings: Settings):
    if not lexical_index_exists(settings):
        if index_building():
            raise PipelineError(503, "The knowledge base is warming up. Try again in about 30 seconds.", "index_building")
        raise PipelineError(404, "BM25 index not found. Run /ingest first.", "index_missing")
    return load_lexical_index(settings)


def clean_output_text(text: str) -> str:
    text = re.sub(r"(?m)^\s*[-*]\s*$", "", text)
    text = re.sub(r"(?m)^\s*#{1,6}\s*", "", text)
    text = re.sub(r"\|", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def texts(documents: list[Document]) -> list[str]:
    return [clean_output_text(doc.page_content) for doc in documents]


def scores(documents: list[Document]) -> list[float]:
    return [float(doc.metadata.get("final_fused_score", doc.metadata.get("relevance_score", 0.0))) for doc in documents]


def score_trace(documents: list[Document]) -> list[dict]:
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


def _log_retrieval_debug(settings: Settings, query: str, initial_docs: list[Document], ranked_docs: list[Document]) -> None:
    if not settings.rag_debug_logs:
        return
    log_debug_event(
        settings,
        "retrieval_to_generation_debug",
        {
            "query": query,
            "retrieved_context": texts(initial_docs),
            "ranked_chunks": [
                {
                    "rank": index,
                    "relevance_score": doc.metadata.get("relevance_score"),
                    "source": doc.metadata.get("source"),
                    "content": doc.page_content,
                }
                for index, doc in enumerate(ranked_docs, start=1)
            ],
        },
    )


def _needs_correction(evaluation: dict, settings: Settings) -> bool:
    return (
        evaluation.get("hallucination_risk") == "high"
        or evaluation.get("retrieval_confidence", 1.0) < settings.retrieval_confidence_threshold
    )


def run_query_pipeline(query: str, settings: Settings, *, stream: bool) -> Iterator[tuple[str, dict]]:
    start = perf_counter()
    stage_suffix = "_stream" if stream else ""
    timings = TimingMetrics()
    warnings: list[str] = []

    try:
        lexical_index = load_index_or_raise(settings)
        initial_docs, documents, trace = retrieve_adaptive(query, lexical_index, settings)
        documents, compression = compress_context(documents)
        trace["context_compression"] = compression
    except PipelineError:
        raise
    except Exception as exc:
        log_event(settings, "query_failure", {"status": "error", "stage": "retrieve", "message": "Lexical retrieval failed."})
        raise PipelineError(500, "Lexical retrieval failed.", "retrieval_failed") from exc

    timings.retrieval_ms = float(trace.get("bm25_search_ms", 0.0))
    yield "retrieval", {"timings": timings.model_dump(), "sources": texts(initial_docs)}

    timings.ranking_ms = float(trace.get("ranking_ms", 0.0))
    if not documents:
        warnings.append("No retrieved context available")
    _log_retrieval_debug(settings, query, initial_docs, documents)
    yield "rank", {
        "timings": timings.model_dump(),
        "sources": texts(documents),
        "relevance_scores": scores(documents),
        "retrieval_score_trace": score_trace(documents),
        "retrieval_strategy": RETRIEVAL_STRATEGY,
        "trace": trace,
    }

    generation_start = perf_counter()
    generated = False
    try:
        if stream:
            answer_parts: list[str] = []
            for token in stream_answer(query, documents, settings):
                answer_parts.append(token)
                timings.generation_ms = (perf_counter() - generation_start) * 1000
                yield "token", {"token": token, "timings": timings.model_dump()}
            answer = "".join(answer_parts).strip()
            if not answer:
                # Some compatible gateways can finish a stream without a content delta.
                # Retry once without streaming so the UI receives either an answer or a
                # useful generation error instead of an empty successful response.
                answer = generate_answer(query, documents, settings)
                timings.generation_ms = (perf_counter() - generation_start) * 1000
                yield "token", {"token": answer, "timings": timings.model_dump()}
        else:
            answer = generate_answer(query, documents, settings)
        generated = True
    except Exception as exc:
        error = describe_generation_error(exc, settings)
        log_event(
            settings,
            "generation_failure",
            {"stage": f"generate{stage_suffix}", "error_code": error.code, "message": error.message},
        )
        if stream:
            raise PipelineError(error.status_code, error.message, error.code) from exc
        # A non-streaming caller still gets the retrieved passages, with the error as a warning.
        answer = GENERATION_UNAVAILABLE
        warnings.append(error.message)
    finally:
        timings.generation_ms = (perf_counter() - generation_start) * 1000

    evaluation = None
    if generated:
        evaluation_start = perf_counter()
        try:
            evaluation = log_evaluation(query, documents, answer, settings)
        except Exception as exc:
            warnings.append("Lexical evaluation unavailable")
            log_event(
                settings,
                "evaluation_failure",
                {"stage": f"initial_evaluation{stage_suffix}", "error_type": type(exc).__name__, "error": str(exc)[:300]},
            )
        timings.evaluation_ms = (perf_counter() - evaluation_start) * 1000

    if evaluation and _needs_correction(evaluation, settings):
        correction_start = perf_counter()
        try:
            retry_initial, retry_docs, retry_trace = corrective_retrieve(query, lexical_index, settings, trace)
            retry_docs, retry_compression = compress_context(retry_docs)
            retry_answer = generate_answer(query, retry_docs, settings)
            retry_evaluation = log_evaluation(query, retry_docs, retry_answer, settings)
            trace = retry_trace
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
                    "stage": f"corrective_retrieval_or_generation{stage_suffix}",
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:300],
                },
            )
        timings.correction_ms = (perf_counter() - correction_start) * 1000

    timings.total_ms = (perf_counter() - start) * 1000
    warning = "; ".join(dict.fromkeys(warnings)) if warnings else None
    evaluation_fields = {
        "grounding_score": evaluation.get("grounding_score") if evaluation else None,
        "grounding": evaluation.get("grounding") if evaluation else None,
        "grounded": evaluation.get("grounded") if evaluation else None,
        "hallucination_risk": evaluation.get("hallucination_risk") if evaluation else None,
    }
    response = QueryResponse(
        query=query,
        answer=answer,
        sources=texts(documents),
        initial_sources=texts(initial_docs),
        warning=warning,
        evaluation=evaluation,
        timings=timings,
        relevance_scores=scores(documents),
        retrieval_score_trace=score_trace(documents),
        retrieval_strategy=RETRIEVAL_STRATEGY,
        trace=trace,
        **evaluation_fields,
    )
    log_event(
        settings,
        "query_stream" if stream else "query",
        {
            "status": "warning" if warnings else "success",
            "query": query,
            "latency_ms": timings.total_ms,
            "num_retrieved": len(initial_docs),
            "num_ranked": len(documents),
            "warning": warning,
            "evaluation": evaluation,
            "timings": timings.model_dump(),
            "retrieval_strategy": RETRIEVAL_STRATEGY,
            **evaluation_fields,
        },
    )
    yield "done", response.model_dump()
