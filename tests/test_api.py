import json

import pytest
from fastapi.testclient import TestClient

import app.pipeline as pipeline
from app.core.config import get_settings
from app.main import app

from tests.conftest import make_settings, read_jsonl


class FakeGroqError(Exception):
    def __init__(self, status_code: int):
        super().__init__(f"HTTP {status_code}")
        self.status_code = status_code


def _grounded_answer(query, documents, settings):
    return documents[0].page_content[:300]


@pytest.fixture
def indexed_client(client):
    assert client.post("/ingest").status_code == 200
    return client


def _stream_events(response) -> list[dict]:
    return [json.loads(line) for line in response.text.splitlines() if line.strip()]


def test_status_and_ingest(client):
    status = client.get("/status").json()
    assert status["lexical_index_exists"] is False

    ingest = client.post("/ingest").json()
    assert ingest["status"] == "success" and ingest["chunks_created"] >= 3

    status = client.get("/status").json()
    assert status["lexical_index_exists"] is True
    assert status["indexed_chunks"] == ingest["chunks_created"]


def test_query_without_index_returns_404(client):
    response = client.post("/query", json={"query": "battery fault"})
    assert response.status_code == 404
    assert response.json()["error_code"] == "index_missing"


def test_query_returns_answer_sources_and_initial_sources(indexed_client, monkeypatch, settings):
    monkeypatch.setattr(pipeline, "generate_answer", _grounded_answer)
    body = indexed_client.post("/query", json={"query": "How is a battery fault diagnosed?"}).json()
    assert "battery" in body["answer"].lower()
    assert body["sources"] and body["initial_sources"]
    assert body["evaluation"]["grounded"] is True
    assert body["timings"]["correction_ms"] == 0.0
    events = [event["event_type"] for event in read_jsonl(settings.processed_data_dir / "system_logs.jsonl")]
    assert "query" in events
    assert "retrieval_to_generation_debug" not in events


def test_query_generation_failure_returns_retrieved_passages(indexed_client, monkeypatch):
    def failing(*_args):
        raise FakeGroqError(503)

    monkeypatch.setattr(pipeline, "generate_answer", failing)
    response = indexed_client.post("/query", json={"query": "battery fault"})
    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == pipeline.GENERATION_UNAVAILABLE
    assert "temporarily unavailable" in body["warning"]
    assert body["sources"]


def test_stream_emits_stages_in_order(indexed_client, monkeypatch):
    monkeypatch.setattr(pipeline, "stream_answer", lambda q, docs, s: iter(["Battery ", "degradation ", "is caused by temperature."]))
    monkeypatch.setattr(pipeline, "generate_answer", _grounded_answer)
    events = _stream_events(indexed_client.post("/query/stream", json={"query": "What causes battery degradation?"}))
    types = [event["type"] for event in events]
    assert types[:2] == ["retrieval", "rank"]
    assert types[-1] == "done"
    assert set(types[2:-1]) == {"token"}
    assert events[-1]["initial_sources"]


def test_stream_generation_error_becomes_error_event(indexed_client, monkeypatch):
    def failing(*_args):
        raise FakeGroqError(429)
        yield  # pragma: no cover - makes this a generator

    monkeypatch.setattr(pipeline, "stream_answer", failing)
    events = _stream_events(indexed_client.post("/query/stream", json={"query": "battery fault"}))
    assert events[-1]["type"] == "error"
    assert events[-1]["error_code"] == "groq_rate_limited"


def test_high_risk_answer_triggers_corrective_retry(indexed_client, monkeypatch):
    # Contradicts the indexed passage ("is diagnosed by collecting sensor logs"), so risk is high.
    contradicting = "A battery fault is not diagnosed by collecting sensor logs or analysing voltage anomalies."
    monkeypatch.setattr(pipeline, "generate_answer", lambda *_args: contradicting)
    body = indexed_client.post("/query", json={"query": "How is a battery fault diagnosed?"}).json()
    assert body["timings"]["correction_ms"] > 0
    assert len(body["trace"]["corrective_attempts"]) == 1


def test_debug_logs_written_when_enabled(corpus_dir, monkeypatch):
    debug_settings = make_settings(corpus_dir, RAG_DEBUG_LOGS=True)
    app.dependency_overrides[get_settings] = lambda: debug_settings
    try:
        client = TestClient(app)
        client.post("/ingest")
        monkeypatch.setattr(pipeline, "generate_answer", _grounded_answer)
        client.post("/query", json={"query": "battery fault"})
    finally:
        app.dependency_overrides.clear()
    events = [event["event_type"] for event in read_jsonl(debug_settings.processed_data_dir / "system_logs.jsonl")]
    assert "retrieval_to_generation_debug" in events


def test_feedback_validation_and_improve_summary(indexed_client):
    assert indexed_client.post("/feedback", json={"query": "q", "answer": "a", "rating": 9}).status_code == 422
    assert indexed_client.post("/feedback", json={"query": "battery fault", "answer": "a", "rating": 1}).status_code == 200
    assert indexed_client.post("/feedback", json={"query": "bread", "answer": "a", "rating": 5}).status_code == 200

    improvement = indexed_client.post("/improve").json()
    assert "1 of 2 rated answers marked unhelpful" in improvement["summary"]
    assert any('"battery fault"' in suggestion for suggestion in improvement["suggestions"])


def test_debug_retrieval_endpoint(indexed_client):
    body = indexed_client.post("/debug/retrieval", json={"query": "sourdough bread"}).json()
    assert body["ranked_documents"]
    assert body["trace"]["query_type"] == "factual"
