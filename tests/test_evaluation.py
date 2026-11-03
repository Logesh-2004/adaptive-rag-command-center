from langchain_core.documents import Document

from app.evaluation.evaluator import evaluate_answer
from app.generation.context import compress_context

CONTEXT = [
    Document(
        page_content=(
            "Battery degradation is often caused by high temperature and repeated fast charging. "
            "Sensor logs are analysed to find voltage anomalies across battery cells."
        ),
        metadata={"relevance_score": 0.9},
    )
]


def test_grounded_answer_is_low_risk(settings):
    answer = "Battery degradation is caused by high temperature and repeated fast charging."
    evaluation = evaluate_answer("What causes battery degradation?", CONTEXT, answer, settings)
    assert evaluation["grounded"] is True
    assert evaluation["hallucination_risk"] == "low"


def test_unrelated_answer_is_not_grounded(settings):
    answer = "The Eiffel Tower was completed in Paris for the world exhibition of eighteen eighty nine."
    evaluation = evaluate_answer("What causes battery degradation?", CONTEXT, answer, settings)
    assert evaluation["grounded"] is False
    assert evaluation["unsupported_sentences"]


def test_contradiction_is_flagged_high_risk(settings):
    context = [Document(page_content="The battery cooling system is enabled during fast charging sessions.", metadata={"relevance_score": 0.9})]
    answer = "The battery cooling system is disabled during fast charging sessions."
    evaluation = evaluate_answer("Is battery cooling used when fast charging?", context, answer, settings)
    assert evaluation["contradiction_detected"] is True
    assert evaluation["hallucination_risk"] == "high"


def test_compress_context_drops_duplicates_and_respects_budget():
    text = "Battery cells are monitored for voltage anomalies. " * 20
    docs = [
        Document(page_content=text),
        Document(page_content=text),
        Document(page_content="Short second passage about cell balancing."),
        Document(page_content="Other passage " * 400),
    ]
    compressed, metrics = compress_context(docs, max_chars=1500)
    assert metrics["dropped_duplicates"] == 1
    assert metrics["context_chars"] <= 1500
    # The duplicate is skipped and the oversized last passage stops the context at the budget.
    assert [doc.page_content[:5] for doc in compressed] == ["Batte", "Short"]
