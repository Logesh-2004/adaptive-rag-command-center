from pathlib import Path

from langchain_core.documents import Document

from app.retrieval.hybrid import feedback_terms, keyword_search, reciprocal_rank_fusion
from app.retrieval.lexical_index import BM25Store, load_lexical_index
from app.retrieval.retriever import _metadata_boost, query_phrases, retrieve_adaptive
from app.retrieval.text import tokenize


def _source_name(doc: Document) -> str:
    return Path(str(doc.metadata["source"])).name


def test_inverted_index_matches_corpus():
    docs = [Document(page_content="battery battery fault"), Document(page_content="sourdough bread")]
    stats = BM25Store(documents=docs).stats
    assert stats.postings["battery"] == [(0, 2)]
    assert stats.document_frequency("bread") == 1
    assert stats.doc_lengths == [3, 2]


def test_keyword_search_ranks_matching_document_first(indexed_settings):
    index = load_lexical_index(indexed_settings)
    results = keyword_search(index, "battery fault temperature", k=3)
    assert _source_name(results[0]) == "ev_diagnostics.txt"
    assert results[0].metadata["retrieval_channels"] == ["bm25"]


def test_retrieval_works_for_non_rag_topics(indexed_settings):
    index = load_lexical_index(indexed_settings)
    _initial, ranked, trace = retrieve_adaptive("How long should sourdough dough proof?", index, indexed_settings)
    assert _source_name(ranked[0]) == "bread_baking.md"
    assert "priority_source" not in trace["retrieval_channels"]


def test_ev_question_prefers_ev_document(indexed_settings):
    index = load_lexical_index(indexed_settings)
    _initial, ranked, trace = retrieve_adaptive("How do I diagnose an EV battery fault?", index, indexed_settings)
    assert _source_name(ranked[0]) == "ev_diagnostics.txt"
    assert any("electric vehicle" in rewrite for rewrite in trace["rewritten_queries"])


def test_metadata_boost_uses_file_name_words():
    adaptive = Document(page_content="", metadata={"source": "data/raw/adaptive_rag.txt"})
    unrelated = Document(page_content="", metadata={"source": "data/raw/bread_baking.md"})
    assert _metadata_boost({"adaptive", "rag"}, adaptive) == 0.25
    assert _metadata_boost({"adaptive", "rag"}, unrelated) == 0.0


def test_query_phrases_skip_stopword_pairs():
    assert query_phrases("Compare self-RAG and corrective RAG") == {"compare self rag", "corrective rag"}


def test_feedback_terms_exclude_query_terms(indexed_settings):
    index = load_lexical_index(indexed_settings)
    top = keyword_search(index, "battery", k=3)
    terms = feedback_terms(index, top, exclude=set(tokenize("battery")))
    assert "battery" not in terms


def test_feedback_list_does_not_inflate_bm25_strength():
    strong = Document(page_content="alpha", metadata={"source": "a", "bm25_score": 10.0, "retrieval_channels": ["bm25"]})
    weak = Document(page_content="beta", metadata={"source": "b", "bm25_score": 2.0, "retrieval_channels": ["bm25"]})
    # The feedback list scores "beta" very highly because its longer query matched more terms.
    weak_in_feedback = Document(page_content="beta", metadata={"source": "b", "bm25_score": 50.0, "retrieval_channels": ["feedback"]})
    fused = {doc.page_content: doc for doc in reciprocal_rank_fusion([[strong, weak], [weak_in_feedback]], k=5)}
    assert fused["alpha"].metadata["bm25_norm"] == 1.0
    assert fused["beta"].metadata["bm25_norm"] < 1.0
    assert fused["beta"].metadata["retrieval_channels"] == ["bm25", "feedback"]
