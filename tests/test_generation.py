import io
import json

import requests
from langchain_core.documents import Document

import app.generation.answer as answer


def _sse_response(events: list[dict]) -> requests.Response:
    body = "".join(f"data: {json.dumps(event, ensure_ascii=False)}\n\n" for event in events) + "data: [DONE]\n\n"
    response = requests.Response()
    response.status_code = 200
    response.raw = io.BytesIO(body.encode("utf-8"))
    # What requests infers for "text/event-stream" without a charset.
    response.encoding = "ISO-8859-1"
    return response


def test_stream_answer_decodes_utf8_tokens(settings, monkeypatch):
    events = [{"choices": [{"delta": {"content": "Collect sensor logs — then compare"}}]}]
    monkeypatch.setattr(answer.requests, "post", lambda *_args, **_kwargs: _sse_response(events))
    documents = [Document(page_content="Collect sensor logs and compare them with known failure patterns.")]
    assert "".join(answer.stream_answer("How?", documents, settings)) == "Collect sensor logs — then compare"
