from app.core.logger import append_jsonl, log_debug_event, log_event, utc_timestamp

from tests.conftest import make_settings, read_jsonl


def test_utc_timestamp_uses_z_suffix():
    assert utc_timestamp().endswith("Z")


def test_append_jsonl_rotates_when_file_is_full(tmp_path):
    path = tmp_path / "events.jsonl"
    append_jsonl(path, {"n": 1, "padding": "x" * 200}, max_bytes=100)
    append_jsonl(path, {"n": 2}, max_bytes=100)
    assert read_jsonl(path) == [{"n": 2}]
    assert read_jsonl(tmp_path / "events.1.jsonl")[0]["n"] == 1


def test_debug_events_are_written_only_when_enabled(tmp_path):
    disabled = make_settings(tmp_path)
    log_debug_event(disabled, "generation_prompt_debug", {"final_prompt": "secret context"})
    log_event(disabled, "query", {"status": "success"})
    assert [event["event_type"] for event in read_jsonl(tmp_path / "processed" / "system_logs.jsonl")] == ["query"]

    enabled = make_settings(tmp_path, RAG_DEBUG_LOGS=True)
    log_debug_event(enabled, "generation_prompt_debug", {"final_prompt": "secret context"})
    assert read_jsonl(tmp_path / "processed" / "system_logs.jsonl")[-1]["event_type"] == "generation_prompt_debug"
