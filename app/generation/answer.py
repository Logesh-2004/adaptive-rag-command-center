import json
from typing import Iterator, List

import requests
from langchain_core.documents import Document

from app.core.config import Settings
from app.core.logger import log_event
from app.generation.context import compress_context


FALLBACK_ANSWER = "Insufficient information based on retrieved data"


def generate_answer(query: str, documents: List[Document], settings: Settings) -> str:
    """Generate an answer with Groq's OpenAI-compatible chat completions API."""
    messages = build_generation_messages(query, documents)
    if messages is None:
        return FALLBACK_ANSWER
    _debug_generation(settings, query, documents, messages)
    response = requests.post(_completion_url(settings), headers=_headers(settings), json=_request_body(settings, messages), timeout=(10, 90))
    response.raise_for_status()
    payload = response.json()
    answer = (payload["choices"][0]["message"].get("content") or "").strip()
    if not answer:
        raise RuntimeError("Groq returned an empty answer")
    _debug_raw_response(settings, answer)
    return answer


def stream_answer(query: str, documents: List[Document], settings: Settings) -> Iterator[str]:
    """Stream answer text from Groq's chat completions endpoint."""
    messages = build_generation_messages(query, documents)
    if messages is None:
        yield FALLBACK_ANSWER
        return
    _debug_generation(settings, query, documents, messages)
    body = _request_body(settings, messages)
    body["stream"] = True
    answer_parts: list[str] = []
    with requests.post(
        _completion_url(settings),
        headers=_headers(settings),
        json=body,
        timeout=(10, 120),
        stream=True,
    ) as response:
        response.raise_for_status()
        for line in response.iter_lines(decode_unicode=True):
            if not line:
                continue
            if isinstance(line, bytes):
                line = line.decode("utf-8", errors="ignore")
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            event = json.loads(data)
            if event.get("error"):
                raise RuntimeError("Groq returned an error while streaming the answer")
            choices = event.get("choices") or []
            if not choices:
                continue
            token = choices[0].get("delta", {}).get("content") or ""
            if token:
                answer_parts.append(token)
                yield token
    streamed_answer = "".join(answer_parts).strip()
    if streamed_answer:
        _debug_raw_response(settings, streamed_answer)


def _completion_url(settings: Settings) -> str:
    return f"{settings.groq_api_base.rstrip('/')}/chat/completions"


def _headers(settings: Settings) -> dict[str, str]:
    api_key = settings.groq_api_key_value
    if not api_key:
        raise ValueError("GROQ_API_KEY is required for generation")
    return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}


def _request_body(settings: Settings, messages: list[dict[str, str]]) -> dict:
    body = {
        "model": settings.groq_model,
        "messages": messages,
        "temperature": settings.llm_temperature,
        "max_completion_tokens": settings.generation_num_predict,
        "include_reasoning": False,
    }
    if settings.groq_model.startswith("openai/gpt-oss-"):
        body["reasoning_effort"] = "low"
    return body


def build_generation_messages(query: str, documents: List[Document]) -> list[dict[str, str]] | None:
    if not documents:
        return None
    compressed_documents, _metrics = compress_context(documents)
    context = build_context(compressed_documents)
    if not context:
        return None
    return [
        {"role": "system", "content": "You are a helpful assistant. Answer only from the supplied context. If the context does not contain enough information, say so clearly. Do not invent facts."},
        {"role": "user", "content": f"Context:\n{context}\n\nQuestion:\n{query}\n\nAnswer:"},
    ]


def build_context(documents: List[Document]) -> str:
    """Concatenate top ranked chunks while preserving readable boundaries."""
    blocks = []
    for index, doc in enumerate(documents, start=1):
        content = doc.page_content.strip()
        if content:
            blocks.append(f"[Chunk {index}]\n{content}")
    return "\n\n".join(blocks).strip()


def _debug_generation(settings: Settings, query: str, documents: List[Document], messages: list[dict[str, str]]) -> None:
    context = build_context(documents)
    prompt = "\n\n".join(message["content"] for message in messages)
    payload = {
        "provider": "groq",
        "model": settings.groq_model,
        "query": query,
        "retrieved_context": context,
        "ranked_chunks": [
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
    payload = {"provider": "groq", "raw_llm_response": answer}
    print("[RAG DEBUG] raw_llm_response", json.dumps(payload, ensure_ascii=False))
    log_event(settings, "generation_response_debug", payload)
