import json

from app.retrieval.query_classifier import classify_query, expand_query, load_query_expansions


def test_comparison_queries_get_deeper_retrieval():
    plan = classify_query("Compare self-RAG versus corrective RAG", base_top_k=3, base_retrieval_top_n=2)
    assert plan.query_type == "agentic_multi_hop"
    assert plan.top_k == 8 and plan.retrieval_top_n == 4


def test_factual_query_keeps_base_depth():
    plan = classify_query("What is HyDE?", base_top_k=3, base_retrieval_top_n=2)
    assert plan.query_type == "factual"
    assert (plan.top_k, plan.retrieval_top_n) == (3, 2)


def test_expansions_match_whole_words_and_plurals():
    expansions = {"rag": ["retrieval augmented generation"], "hallucination": ["grounding"]}
    assert len(expand_query("How do RAG pipelines work?", expansions)) == 2
    assert expand_query("How much drag does a car have?", expansions) == ["How much drag does a car have?"]
    assert expand_query("Why do hallucinations happen?", expansions)[-1].endswith("grounding")


def test_load_query_expansions(tmp_path):
    path = tmp_path / "expansions.json"
    path.write_text(json.dumps({"_comment": "ignored", "EV": "electric vehicle", "rag": ["a", "b", ""]}), encoding="utf-8")
    assert load_query_expansions(path) == {"ev": ["electric vehicle"], "rag": ["a", "b"]}
    assert load_query_expansions(tmp_path / "missing.json") == {}
