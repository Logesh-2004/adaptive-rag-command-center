import json
from collections import Counter
from pathlib import Path
from typing import List, Tuple
from app.core.config import Settings


def _load_evaluations(evaluation_path: Path) -> List[dict]:
    if not evaluation_path.exists():
        return []

    records = []
    with evaluation_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def _analyze_records(records: List[dict]) -> Tuple[int, Counter, List[str]]:
    weak_count = 0
    weak_reasons = Counter()
    weak_samples = []
    for record in records:
        evaluation = record.get("evaluation", {})
        faithfulness = float(evaluation.get("faithfulness", 0.0))
        relevance = float(evaluation.get("relevance", 0.0))
        if faithfulness < 0.5 or relevance < 0.5:
            weak_count += 1
            weak_samples.append(record)
            if faithfulness < 0.5:
                weak_reasons["faithfulness"] += 1
            if relevance < 0.5:
                weak_reasons["relevance"] += 1
    return weak_count, weak_reasons, [json.dumps(r, ensure_ascii=False) for r in weak_samples[:5]]


def run_improvement_cycle(settings: Settings) -> Tuple[str, int, List[str]]:
    """Generate an offline improvement summary based on evaluation logs."""
    evaluation_path = settings.processed_data_dir / "evaluations.jsonl"
    records = _load_evaluations(evaluation_path)
    weak_count, weak_reasons, sample_records = _analyze_records(records)

    suggestions = []
    if weak_count == 0:
        summary = "No weak evaluation records were found. The system is operating within current thresholds."
        suggestions.append(
            f"Maintain current chunk size ({settings.chunk_size}) and retrieval k ({settings.retrieval_top_k})."
        )
    else:
        summary = (
            f"Detected {weak_count} weak evaluation records. "
            f"Faithfulness issues: {weak_reasons.get('faithfulness', 0)}, "
            f"relevance issues: {weak_reasons.get('relevance', 0)}."
        )
        if weak_reasons.get("faithfulness", 0) > weak_reasons.get("relevance", 0):
            suggestions.append(f"Change chunk size from {settings.chunk_size} to {max(100, settings.chunk_size - 100)}.")
            suggestions.append(f"Change retrieval k from {settings.retrieval_top_k} to {settings.retrieval_top_k + 1}.")
            suggestions.append("Review document quality and ensure relevant passages are present for queries.")
        elif weak_reasons.get("relevance", 0) > weak_reasons.get("faithfulness", 0):
            suggestions.append(f"Change chunk size from {settings.chunk_size} to {max(100, settings.chunk_size - 100)}.")
            suggestions.append(f"Change retrieval k from {settings.retrieval_top_k} to {settings.retrieval_top_k + 1}.")
            suggestions.append("Review BM25 keyword coverage, document filtering, and source quality.")
        else:
            suggestions.append(f"Change retrieval k from {settings.retrieval_top_k} to {settings.retrieval_top_k + 1}.")
            suggestions.append(f"Change chunk size from {settings.chunk_size} to {max(100, settings.chunk_size - 100)}.")
            suggestions.append("Verify that ingestion covers the minimum domain-specific source set.")

    return summary, weak_count, suggestions
