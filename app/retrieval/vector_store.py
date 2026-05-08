from pathlib import Path
from typing import List
import faiss
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_ollama import OllamaEmbeddings

from app.core.config import Settings

_EMBEDDING_CACHE: dict[tuple[str, str], OllamaEmbeddings] = {}
_VECTOR_STORE_CACHE: dict[tuple[str, str], FAISS] = {}


def get_embeddings(settings: Settings) -> OllamaEmbeddings:
    """Create local Ollama embeddings."""
    key = (settings.ollama_base_url, settings.embedding_model)
    if key not in _EMBEDDING_CACHE:
        _EMBEDDING_CACHE[key] = OllamaEmbeddings(
            model=settings.embedding_model,
            base_url=settings.ollama_base_url,
        )
    return _EMBEDDING_CACHE[key]


def load_vector_store(settings: Settings) -> FAISS:
    """Load the persisted FAISS vector store from disk."""
    store_path = Path(settings.vector_db_path)
    if (
        not store_path.exists()
        or not (store_path / "index.faiss").exists()
        or not (store_path / "index.pkl").exists()
    ):
        raise FileNotFoundError("Vector store path does not exist.")

    key = (str(store_path.resolve()), settings.embedding_model)
    if key not in _VECTOR_STORE_CACHE:
        _VECTOR_STORE_CACHE[key] = FAISS.load_local(
            str(store_path),
            get_embeddings(settings),
            allow_dangerous_deserialization=True,
        )
    return _VECTOR_STORE_CACHE[key]


def invalidate_vector_store_cache(settings: Settings) -> None:
    store_path = Path(settings.vector_db_path).resolve()
    for key in list(_VECTOR_STORE_CACHE):
        if key[0] == str(store_path):
            _VECTOR_STORE_CACHE.pop(key, None)


def vector_store_exists(settings: Settings) -> bool:
    store_path = Path(settings.vector_db_path)
    return (store_path / "index.faiss").exists() and (store_path / "index.pkl").exists()


def indexed_document_count(settings: Settings) -> int:
    """Read FAISS vector count without loading embeddings or deserializing metadata."""
    index_path = Path(settings.vector_db_path) / "index.faiss"
    if not index_path.exists():
        return 0
    try:
        return int(faiss.read_index(str(index_path)).ntotal)
    except Exception:
        return 0


def query_vector_store(vector_store: FAISS, query: str, k: int = 5) -> List[Document]:
    """Retrieve the most relevant chunks for a user query."""
    docs_with_scores = vector_store.similarity_search_with_score(query=query, k=k)
    documents: List[Document] = []
    for doc, distance in docs_with_scores:
        doc.metadata["vector_distance"] = float(distance)
        doc.metadata["vector_score"] = 1.0 / (1.0 + max(0.0, float(distance)))
        documents.append(doc)
    return documents
