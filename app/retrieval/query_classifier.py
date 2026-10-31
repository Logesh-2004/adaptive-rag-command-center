from dataclasses import dataclass
import json
from pathlib import Path
import re


@dataclass(frozen=True)
class QueryPlan:
    query_type: str
    complexity: float
    top_k: int
    retrieval_top_n: int
    multi_hop: bool
    rewritten_queries: list[str]


QueryExpansions = dict[str, list[str]]

_EXPANSION_CACHE: dict[str, tuple[float, QueryExpansions]] = {}


def classify_query(
    query: str,
    base_top_k: int,
    base_retrieval_top_n: int,
    expansions: QueryExpansions | None = None,
) -> QueryPlan:
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

    rewritten_queries = expand_query(query, expansions or {})
    return QueryPlan(query_type, round(complexity, 3), top_k, retrieval_top_n, multi_hop, rewritten_queries)


def expand_query(query: str, expansions: QueryExpansions) -> list[str]:
    """Add one rewrite per configured expansion whose phrase appears in the query."""
    rewrites = [query]
    lower = query.lower()
    for phrase, additions in expansions.items():
        # Whole-word match, allowing a plural "s" ("hallucinations" matches "hallucination").
        if re.search(rf"(?<![a-z0-9]){re.escape(phrase)}s?(?![a-z0-9])", lower):
            rewrites.extend(f"{query} {addition}" for addition in additions)
    return list(dict.fromkeys(rewrites))


def load_query_expansions(path: Path) -> QueryExpansions:
    """Read the phrase -> expansion terms map, reloading only when the file changes."""
    try:
        modified = path.stat().st_mtime
    except OSError:
        return {}
    key = str(path.resolve())
    cached = _EXPANSION_CACHE.get(key)
    if cached is not None and cached[0] == modified:
        return cached[1]

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    expansions: QueryExpansions = {}
    if isinstance(raw, dict):
        for phrase, value in raw.items():
            if str(phrase).startswith("_"):
                continue
            values = value if isinstance(value, list) else [value]
            cleaned = [str(item).strip() for item in values if str(item).strip()]
            if cleaned:
                expansions[str(phrase).lower().strip()] = cleaned
    _EXPANSION_CACHE[key] = (modified, expansions)
    return expansions
