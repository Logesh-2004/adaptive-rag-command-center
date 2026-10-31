from app.ingestion.loader import _split_text, clean_document_text, ingest_documents
from app.retrieval.lexical_index import index_file_path, load_lexical_index


def test_clean_document_text_removes_markup_and_page_numbers():
    raw = "# Title\n\n| a | b |\n|---|---|\nSome text [12] here.\n\nPage 3 of 10\n"
    cleaned = clean_document_text(raw)
    assert "#" not in cleaned
    assert "|" not in cleaned
    assert "[12]" not in cleaned
    assert "Page 3" not in cleaned
    assert "Title" in cleaned and "Some text" in cleaned


def test_split_text_respects_size_and_overlaps():
    text = " ".join(f"word{index}." for index in range(400))
    chunks = _split_text(text, chunk_size=200, chunk_overlap=40, separators=(". ", " "))
    assert len(chunks) > 1
    assert all(len(chunk) <= 200 for chunk in chunks)
    assert chunks[-1].endswith("word399.")
    # Consecutive chunks share text because of the overlap.
    assert chunks[0].split()[-1] in chunks[1]


def test_ingest_builds_index_and_reports_unreadable_pdf(settings):
    (settings.raw_data_dir / "broken.pdf").write_bytes(b"not really a pdf")
    summary = ingest_documents(settings)
    assert summary["indexed_documents"] == 3
    assert summary["chunks_created"] >= 3
    assert any("broken.pdf" in warning for warning in summary["warnings"])
    assert index_file_path(settings).is_file()
    assert len(load_lexical_index(settings).documents) == summary["chunks_created"]
