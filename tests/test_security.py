import pytest
from fastapi.testclient import TestClient

import app.pipeline as pipeline
from app.api.security import limiter
from app.core.config import get_settings
from app.ingestion.loader import ingest_documents
from app.main import app

from tests.conftest import make_settings

PROXY = {"X-Proxy-Secret": "proxy-secret"}


@pytest.fixture(autouse=True)
def fresh_limiter():
    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture
def guarded(corpus_dir, monkeypatch):
    settings = make_settings(
        corpus_dir,
        PROXY_SECRET="proxy-secret",
        ADMIN_TOKEN="admin-token",
        QUERY_RATE_LIMIT_PER_MINUTE=2,
        DAILY_QUERY_LIMIT=3,
    )
    ingest_documents(settings)
    monkeypatch.setattr(pipeline, "generate_answer", lambda query, documents, settings: documents[0].page_content[:200])
    app.dependency_overrides[get_settings] = lambda: settings
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_status_stays_open_and_reports_admin_mode(guarded):
    body = guarded.get("/status").json()
    assert body["admin_required"] is True


def test_requests_without_the_proxy_secret_are_refused(guarded):
    assert guarded.post("/query", json={"query": "battery fault"}).status_code == 403
    assert guarded.post("/feedback", json={"query": "q", "answer": "a", "rating": 5}).status_code == 403
    assert guarded.post("/query", json={"query": "battery fault"}, headers={"X-Proxy-Secret": "wrong"}).status_code == 403
    assert guarded.post("/query", json={"query": "battery fault"}, headers=PROXY).status_code == 200


def test_rebuild_needs_the_admin_token(guarded):
    assert guarded.post("/ingest", headers=PROXY).status_code == 401
    assert guarded.post("/ingest", headers={**PROXY, "X-Admin-Token": "nope"}).status_code == 401
    assert guarded.post("/ingest", headers={**PROXY, "X-Admin-Token": "admin-token"}).status_code == 200


def test_rate_limit_is_per_visitor(guarded):
    first = {**PROXY, "X-Client-IP": "203.0.113.1"}
    second = {**PROXY, "X-Client-IP": "203.0.113.2"}
    assert guarded.post("/query", json={"query": "battery"}, headers=first).status_code == 200
    assert guarded.post("/query", json={"query": "battery"}, headers=first).status_code == 200
    limited = guarded.post("/query", json={"query": "battery"}, headers=first)
    assert limited.status_code == 429
    assert limited.json()["error_code"] == "rate_limited"
    assert guarded.post("/query", json={"query": "battery"}, headers=second).status_code == 200


def test_daily_limit_covers_the_whole_site(guarded):
    for index in range(3):
        headers = {**PROXY, "X-Client-IP": f"198.51.100.{index}"}
        assert guarded.post("/query", json={"query": "battery"}, headers=headers).status_code == 200
    capped = guarded.post("/query", json={"query": "battery"}, headers={**PROXY, "X-Client-IP": "198.51.100.9"})
    assert capped.status_code == 429
    assert capped.json()["error_code"] == "daily_limit"


def test_guards_are_off_without_settings(client):
    # The default test settings set no secrets or limits, as in local development.
    client.post("/ingest")
    for _ in range(5):
        assert client.post("/debug/retrieval", json={"query": "battery"}).status_code == 200


def test_startup_builds_a_missing_index(corpus_dir, monkeypatch):
    import time

    from app.retrieval.lexical_index import lexical_index_exists

    for name, value in {
        "RAW_DATA_DIR": corpus_dir / "raw",
        "PROCESSED_DATA_DIR": corpus_dir / "processed",
        "LEXICAL_INDEX_PATH": corpus_dir / "index",
        "QUERY_EXPANSIONS_PATH": corpus_dir / "query_expansions.json",
    }.items():
        monkeypatch.setenv(name, str(value))
    settings = make_settings(corpus_dir)
    assert not lexical_index_exists(settings)
    with TestClient(app):
        for _ in range(50):
            if lexical_index_exists(settings):
                break
            time.sleep(0.1)
    assert lexical_index_exists(settings)
