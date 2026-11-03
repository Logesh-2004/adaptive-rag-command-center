import json
import math
import threading
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from langchain_core.documents import Document

from app.core.config import Settings
from app.retrieval.text import tokenize


@dataclass
class BM25Stats:
    """Inverted index over the corpus: term -> [(document index, term frequency)]."""

    postings: dict[str, list[tuple[int, int]]]
    doc_lengths: list[int]
    average_length: float

    @property
    def total_docs(self) -> int:
        return len(self.doc_lengths)

    def document_frequency(self, term: str) -> int:
        return len(self.postings.get(term, ()))

    def idf(self, term: str) -> float:
        df = self.document_frequency(term)
        return math.log(1.0 + (self.total_docs - df + 0.5) / (df + 0.5))


@dataclass
class BM25Store:
    """Small persisted corpus used by the local BM25 retriever."""

    documents: list[Document]
    _stats: BM25Stats | None = field(default=None, repr=False, compare=False)

    @property
    def stats(self) -> BM25Stats:
        """Build the inverted index once, on first use, and reuse it for every query."""
        if self._stats is None:
            self._stats = build_bm25_stats(self.documents)
        return self._stats


def build_bm25_stats(documents: list[Document]) -> BM25Stats:
    postings: dict[str, list[tuple[int, int]]] = {}
    doc_lengths: list[int] = []
    for index, doc in enumerate(documents):
        tokens = tokenize(doc.page_content)
        doc_lengths.append(len(tokens))
        for term, frequency in Counter(tokens).items():
            postings.setdefault(term, []).append((index, frequency))
    average_length = sum(doc_lengths) / max(1, len(doc_lengths))
    return BM25Stats(postings=postings, doc_lengths=doc_lengths, average_length=average_length)


_STORE_CACHE: dict[str, BM25Store] = {}
_INDEX_FILENAME = "chunks.json"
# Set while the startup rebuild runs, so callers can say "warming up" instead of "missing".
_BUILDING = threading.Event()


def set_index_building(building: bool) -> None:
    if building:
        _BUILDING.set()
    else:
        _BUILDING.clear()


def index_building() -> bool:
    return _BUILDING.is_set()


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
