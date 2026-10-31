import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langchain_core.documents import Document

from app.core.config import Settings


@dataclass
class BM25Store:
    """Small persisted corpus used by the local BM25 retriever."""

    documents: list[Document]


_STORE_CACHE: dict[str, BM25Store] = {}
_INDEX_FILENAME = "chunks.json"


def index_file_path(settings: Settings) -> Path:
    return Path(settings.lexical_index_path) / _INDEX_FILENAME


def load_lexical_index(settings: Settings) -> BM25Store:
    """Load persisted text chunks without calling an embedding service."""
    store_path = Path(settings.lexical_index_path).resolve()
    index_path = store_path / _INDEX_FILENAME
    if not index_path.is_file():
        raise FileNotFoundError("Lexical index does not exist. Run /ingest first.")

    key = str(store_path)
    cached = _STORE_CACHE.get(key)
    if cached is not None:
        return cached

    with index_path.open("r", encoding="utf-8") as handle:
        records = json.load(handle)
    if not isinstance(records, list):
        raise ValueError("Lexical index has an invalid format.")
    documents = []
    for record in records:
        if not isinstance(record, dict) or not record.get("page_content"):
            continue
        metadata = record.get("metadata", {})
        if not isinstance(metadata, dict):
            metadata = {}
        documents.append(Document(page_content=str(record["page_content"]), metadata=metadata))
    store = BM25Store(documents=documents)
    _STORE_CACHE[key] = store
    return store


def save_lexical_index(documents: list[Document], settings: Settings) -> BM25Store:
    """Persist document chunks for BM25 search."""
    store_path = Path(settings.lexical_index_path)
    store_path.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = [
        {"page_content": doc.page_content, "metadata": doc.metadata}
        for doc in documents
    ]
    with index_file_path(settings).open("w", encoding="utf-8") as handle:
        json.dump(records, handle, ensure_ascii=False, default=str)
    store = BM25Store(documents=list(documents))
    _STORE_CACHE[str(store_path.resolve())] = store
    return store


def invalidate_lexical_index_cache(settings: Settings) -> None:
    _STORE_CACHE.pop(str(Path(settings.lexical_index_path).resolve()), None)


def lexical_index_exists(settings: Settings) -> bool:
    return index_file_path(settings).is_file()


def indexed_chunk_count(settings: Settings) -> int:
    """Return the number of indexed chunks."""
    if not lexical_index_exists(settings):
        return 0
    try:
        return len(load_lexical_index(settings).documents)
    except (OSError, ValueError, TypeError):
        return 0
