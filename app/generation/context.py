from __future__ import annotations

import re
from copy import deepcopy

from langchain_core.documents import Document


def compress_context(documents: list[Document], max_chars: int = 4200) -> tuple[list[Document], dict]:
    """Deduplicate and trim context while preserving source/chunk boundaries."""
    compressed: list[Document] = []
    seen = set()
    total_chars = 0
    dropped_duplicates = 0
    for doc in documents:
        cleaned = _clean_chunk(doc.page_content)
        fingerprint = re.sub(r"\W+", "", cleaned.lower())[:240]
        if not cleaned:
            continue
        if fingerprint in seen:
            dropped_duplicates += 1
            continue
        if total_chars + len(cleaned) > max_chars and compressed:
            break
        seen.add(fingerprint)
        next_doc = deepcopy(doc)
        next_doc.page_content = cleaned[: max(500, max_chars - total_chars)]
        compressed.append(next_doc)
        total_chars += len(next_doc.page_content)

    return compressed, {
        "input_chunks": len(documents),
        "output_chunks": len(compressed),
        "dropped_duplicates": dropped_duplicates,
        "context_chars": total_chars,
        "token_budget_chars": max_chars,
    }


def _clean_chunk(text: str) -> str:
    text = re.sub(r"(?m)^\s*[-*]\s*$", "", text)
    text = re.sub(r"(?m)^\s*#{1,6}\s*", "", text)
    text = re.sub(r"\|", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
