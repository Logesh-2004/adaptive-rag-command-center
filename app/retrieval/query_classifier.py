from dataclasses import dataclass
import re


@dataclass(frozen=True)
class QueryPlan:
    query_type: str
    complexity: float
    top_k: int
    retrieval_top_n: int
    multi_hop: bool
    rewritten_queries: list[str]


def classify_query(query: str, base_top_k: int, base_retrieval_top_n: int) -> QueryPlan:
    """Classify query intent with deterministic routing rules."""
    text = query.lower().strip()
    words = re.findall(r"[a-zA-Z0-9_-]+", text)
    asks_why_how = any(term in text for term in ("why", "how", "explain", "reason", "cause", "impact"))
    comparison = any(term in text for term in ("compare", "versus", " vs ", "difference", "compared to", "better than"))
    summarization = any(term in text for term in ("summarize", "summary", "overview", "key points"))
    multi_hop = comparison or len([term for term in ("and", "then", "across", "relationship", "tradeoff") if term in text]) >= 2

    if multi_hop:
        query_type = "agentic_multi_hop"
    elif comparison:
        query_type = "comparison"
    elif summarization:
        query_type = "summarization"
    elif asks_why_how or len(words) > 10:
        query_type = "reasoning"
    else:
        query_type = "factual"

    complexity = min(1.0, (len(words) / 18.0) + (0.25 if asks_why_how else 0.0) + (0.25 if multi_hop else 0.0))
    top_k = base_top_k
    retrieval_top_n = base_retrieval_top_n
    if query_type in {"reasoning", "summarization"}:
        top_k = max(base_top_k, 6)
        retrieval_top_n = max(base_retrieval_top_n, 3)
    if query_type in {"comparison", "agentic_multi_hop"}:
        top_k = max(base_top_k, 8)
        retrieval_top_n = max(base_retrieval_top_n, 4)

    rewritten_queries = expand_query(query)
    return QueryPlan(query_type, round(complexity, 3), top_k, retrieval_top_n, multi_hop, rewritten_queries)


def expand_query(query: str) -> list[str]:
    """Expand queries with deterministic lexical terms for retrieval."""
    rewrites = [query]
    lower = query.lower()
    if "adaptive rag" in lower:
        rewrites.append("adaptive retrieval augmented generation")
        rewrites.append("corrective rag self reflective rag dynamic retrieval rag")
        rewrites.append(query + " adaptive retrieval feedback reranking evaluation corrective self-reflective")
    elif "rag" in lower:
        rewrites.append(query + " retrieval augmented generation grounding hallucination mitigation")
    if "hallucination" in lower:
        rewrites.append(query + " unsupported claims grounding faithfulness corrective retrieval")
    return list(dict.fromkeys(rewrites))
