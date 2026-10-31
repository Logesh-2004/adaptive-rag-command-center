from pathlib import Path
import re
from typing import List, TypedDict
from langchain_core.documents import Document
from pypdf import PdfReader

from app.core.config import Settings
from app.retrieval.lexical_index import BM25Store, invalidate_lexical_index_cache, save_lexical_index


class IngestionSummary(TypedDict):
    indexed_documents: int
    chunks_created: int
    warnings: List[str]


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


def load_raw_documents(raw_data_dir: Path) -> tuple[List[Document], List[str]]:
    """Load plaintext, markdown, and PDF documents from the raw data directory."""
    documents: List[Document] = []
    warnings: List[str] = []
    for path in sorted(raw_data_dir.rglob("*")):
        if path.is_file() and path.suffix.lower() in {".txt", ".md"}:
            text = path.read_text(encoding="utf-8", errors="replace")
            cleaned = clean_document_text(text)
            if cleaned:
                documents.append(Document(page_content=cleaned, metadata={"source": str(path)}))
        elif path.is_file() and path.suffix.lower() == ".pdf":
            try:
                reader = PdfReader(str(path))
            except Exception as exc:
                warnings.append(f"Skipped unreadable PDF {path.name} ({type(exc).__name__}).")
                continue
            for page_number, page in enumerate(reader.pages):
                try:
                    page_text = page.extract_text() or ""
                except Exception as exc:
                    warnings.append(f"Skipped page {page_number + 1} in {path.name} ({type(exc).__name__}).")
                    continue
                cleaned = clean_document_text(page_text)
                if cleaned:
                    documents.append(Document(page_content=cleaned, metadata={"source": str(path), "page": page_number}))
    return documents, warnings


def chunk_documents(documents: List[Document], settings: Settings) -> List[Document]:
    """Chunk source documents using configurable recursive text splitting."""
    cleaned_chunks = []
    separators = ("\n\n", "\n", ". ", "; ", ", ", " ")
    for document in documents:
        for chunk_text in _split_text(document.page_content, settings.chunk_size, settings.chunk_overlap, separators):
            cleaned = clean_document_text(chunk_text)
            if len(cleaned.split()) >= 35:
                cleaned_chunks.append(Document(page_content=cleaned, metadata=dict(document.metadata)))
    return cleaned_chunks


def _split_text(text: str, chunk_size: int, chunk_overlap: int, separators: tuple[str, ...]) -> list[str]:
    """Split text near natural boundaries while keeping a small overlap."""
    if not text.strip():
        return []
    chunks = []
    start = 0
    text_length = len(text)
    while start < text_length:
        end = min(start + chunk_size, text_length)
        if end < text_length:
            minimum_boundary = start + max(1, chunk_size // 2)
            for separator in separators:
                boundary = text.rfind(separator, minimum_boundary, end)
                if boundary >= minimum_boundary:
                    end = boundary + len(separator)
                    break
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= text_length:
            break
        next_start = max(start + 1, end - chunk_overlap)
        while next_start < end and text[next_start].isspace():
            next_start += 1
        start = next_start
    return chunks


def build_lexical_index(chunks: List[Document], settings: Settings) -> BM25Store:
    """Persist text chunks for local BM25 retrieval."""
    return save_lexical_index(chunks, settings)


def ingest_documents(settings: Settings) -> IngestionSummary:
    """Load, clean, split, and persist a local lexical search index."""
    documents, warnings = load_raw_documents(settings.raw_data_dir)
    if not documents:
        raise FileNotFoundError(f"No readable documents found in {settings.raw_data_dir}")

    settings.lexical_index_path.mkdir(parents=True, exist_ok=True)
    chunks = chunk_documents(documents, settings)
    build_lexical_index(chunks, settings)
    invalidate_lexical_index_cache(settings)
    return {"indexed_documents": len(documents), "chunks_created": len(chunks), "warnings": warnings}
