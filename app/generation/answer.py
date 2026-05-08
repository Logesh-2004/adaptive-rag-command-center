import json
from typing import Iterator, List
from urllib.request import Request, urlopen

from app.core.config import Settings
from app.core.logger import log_event
from app.generation.context import compress_context
from langchain_core.documents import Document


FALLBACK_ANSWER = "Insufficient information based on retrieved data"


def generate_answer(query: str, documents: List[Document], settings: Settings) -> str:
    """Generate an answer from the query and retrieved document context."""
    prompt = build_generation_prompt(query, documents)
    if prompt is None:
        return FALLBACK_ANSWER

    _debug_generation(settings, query, documents, prompt)
    payload = {
        "model": settings.generation_model,
        "prompt": prompt,
        "stream": False,
        "keep_alive": "30m",
        "options": {
            "temperature": 0.05,
            "num_predict": settings.generation_num_predict,
        },
    }
    request = Request(
        settings.ollama_base_url.rstrip("/") + "/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=120) as response:
        content = json.loads(response.read().decode("utf-8"))
    answer = str(content.get("response", "")).strip()
    _debug_raw_response(settings, answer)
    return answer


def stream_answer(query: str, documents: List[Document], settings: Settings) -> Iterator[str]:
    """Stream generated answer tokens from the local generation model."""
    prompt = build_generation_prompt(query, documents)
    if prompt is None:
        yield FALLBACK_ANSWER
        return

    _debug_generation(settings, query, documents, prompt)
    payload = {
        "model": settings.generation_model,
        "prompt": prompt,
        "stream": True,
        "keep_alive": "30m",
        "options": {
            "temperature": 0.05,
            "num_predict": settings.generation_num_predict,
        },
    }
    request = Request(
        settings.ollama_base_url.rstrip("/") + "/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=120) as response:
        for raw_line in response:
            if not raw_line.strip():
                continue
            event = json.loads(raw_line.decode("utf-8"))
            token = event.get("response", "")
            if token:
                yield str(token)


def build_generation_prompt(query: str, documents: List[Document]) -> str | None:
    if not documents:
        return None

    compressed_documents, _metrics = compress_context(documents)
    context = build_context(compressed_documents)
    if not context:
        return None

    return f"""
You are a helpful AI assistant.

Answer ONLY using the provided context.

Context:
{context}

Question:
{query}

Answer:
""".strip()


def build_context(documents: List[Document]) -> str:
    """Concatenate top reranked chunks while preserving readable chunk formatting."""
    blocks = []
    for index, doc in enumerate(documents, start=1):
        content = doc.page_content.strip()
        if content:
            blocks.append(f"[Chunk {index}]\n{content}")
    return "\n\n".join(blocks).strip()


def _debug_generation(settings: Settings, query: str, documents: List[Document], prompt: str) -> None:
    context = build_context(documents)
    payload = {
        "query": query,
        "retrieved_context": context,
        "reranked_chunks": [
            {
                "rank": index,
                "relevance_score": doc.metadata.get("relevance_score"),
                "source": doc.metadata.get("source"),
                "content": doc.page_content,
            }
            for index, doc in enumerate(documents, start=1)
        ],
        "final_prompt": prompt,
        "prompt_chars": len(prompt),
    }
    print("[RAG DEBUG] generation_prompt", json.dumps(payload, ensure_ascii=False))
    log_event(settings, "generation_prompt_debug", payload)


def _debug_raw_response(settings: Settings, answer: str) -> None:
    payload = {"raw_llm_response": answer}
    print("[RAG DEBUG] raw_llm_response", json.dumps(payload, ensure_ascii=False))
    log_event(settings, "generation_response_debug", payload)
