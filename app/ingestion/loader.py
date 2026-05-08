from pathlib import Path
import re
from typing import List, TypedDict
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.config import Settings
from app.retrieval.vector_store import get_embeddings, invalidate_vector_store_cache


class IngestionSummary(TypedDict):
    indexed_documents: int
    chunks_created: int


def clean_document_text(text: str) -> str:
    """Normalize raw PDF/markdown text into readable natural-language passages."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"(?m)^\s*#{1,6}\s*", "", text)
    text = re.sub(r"(?m)^\s*-{3,}\s*$", "", text)
    text = re.sub(r"(?m)^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?\s*$", "", text)
    text = re.sub(r"\|", " ", text)
    text = re.sub(r"\[[0-9,\-\s]+\]", "", text)
    text = re.sub(r"\((?:Figure|Table|Eq\.?)\s*\d+[a-z]?\)", "", text, flags=re.IGNORECASE)
    text = re.sub(r"(?m)^\s*(?:page\s*)?\d+\s*(?:of\s*\d+)?\s*$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"(?<=\w)-\n(?=\w)", "", text)
    text = re.sub(r"(?<![.!?:;])\n(?!\n)", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    lines = []
    seen_recent: list[str] = []
    for line in (line.strip() for line in text.splitlines()):
        if not line:
            if lines and lines[-1]:
                lines.append("")
            continue
        normalized = re.sub(r"\W+", "", line.lower())
        if normalized and normalized in seen_recent:
            continue
        lines.append(line)
        seen_recent = (seen_recent + [normalized])[-12:]

    return "\n".join(lines).strip()


def load_raw_documents(raw_data_dir: Path) -> List[Document]:
    """Load plaintext, markdown, and PDF documents from the raw data directory."""
    documents: List[Document] = []
    for path in sorted(raw_data_dir.rglob("*")):
        if path.is_file() and path.suffix.lower() in {".txt", ".md"}:
            loader = TextLoader(str(path), encoding="utf-8")
            loaded = loader.load()
            for document in loaded:
                document.metadata["source"] = str(path)
                document.page_content = clean_document_text(document.page_content)
            documents.extend(document for document in loaded if document.page_content)
        elif path.is_file() and path.suffix.lower() == ".pdf":
            loader = PyPDFLoader(str(path))
            loaded = loader.load()
            for document in loaded:
                document.metadata["source"] = str(path)
                document.page_content = clean_document_text(document.page_content)
            documents.extend(document for document in loaded if document.page_content)
    return documents


def chunk_documents(documents: List[Document], settings: Settings) -> List[Document]:
    """Chunk source documents using configurable recursive text splitting."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        separators=["\n\n", "\n", ". ", "; ", ", ", " ", ""],
    )
    chunks = splitter.split_documents(documents)
    cleaned_chunks = []
    for chunk in chunks:
        chunk.page_content = clean_document_text(chunk.page_content)
        word_count = len(chunk.page_content.split())
        if word_count >= 35:
            cleaned_chunks.append(chunk)
    return cleaned_chunks


def build_vector_store(chunks: List[Document], settings: Settings) -> FAISS:
    """Build a FAISS vector store from text chunks and save it to disk."""
    vector_store = FAISS.from_documents(documents=chunks, embedding=get_embeddings(settings))
    vector_store.save_local(str(settings.vector_db_path))
    return vector_store


def ingest_documents(settings: Settings) -> IngestionSummary:
    """Ingest raw documents, create embeddings, and persist the FAISS index."""
    documents = load_raw_documents(settings.raw_data_dir)
    if not documents:
        raise FileNotFoundError(f"No raw text files found in {settings.raw_data_dir}")

    settings.vector_db_path.mkdir(parents=True, exist_ok=True)
    chunks = chunk_documents(documents, settings)
    build_vector_store(chunks, settings)
    invalidate_vector_store_cache(settings)
    return {"indexed_documents": len(documents), "chunks_created": len(chunks)}
