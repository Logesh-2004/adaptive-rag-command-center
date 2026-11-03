import json
from pathlib import Path

import pytest

from app.core.config import Settings
from app.retrieval.retriever import clear_retrieval_cache

SAMPLE_DOCUMENTS = {
    "adaptive_rag.txt": (
        "Adaptive RAG is a retrieval augmented generation architecture that adjusts its retrieval strategy "
        "to the complexity of each question. Simple factual questions may skip retrieval entirely, while "
        "complex multi hop questions trigger iterative retrieval and reranking. Adaptive retrieval combines "
        "a query classifier, corrective retrieval when evidence is weak, and self evaluation of the generated "
        "answer so that unsupported claims can be repaired before they reach the user."
    ),
    "ev_diagnostics.txt": (
        "Electric vehicle diagnostics focus on the battery pack, motor controllers, and embedded software. "
        "Battery degradation is often caused by high temperature and repeated fast charging. A battery fault "
        "is diagnosed by collecting sensor logs, analysing voltage anomalies across cells, and comparing the "
        "readings with known failure patterns. Predictive maintenance models use historical sensor data to "
        "detect a failing battery cell before the vehicle loses range or power."
    ),
    "bread_baking.md": (
        "# Bread baking basics\n\n"
        "Sourdough bread needs flour, water, salt, and an active starter. The dough is mixed, rested, and "
        "folded several times so that gluten develops and the crumb becomes open and airy. Proofing the dough "
        "overnight in a cool place builds flavour. Bake the loaf in a very hot oven with steam for the first "
        "twenty minutes, then lower the temperature so the crust browns without burning the bread."
    ),
}

SAMPLE_EXPANSIONS = {
    "_comment": "test expansions",
    "rag": "retrieval augmented generation",
    "ev": ["electric vehicle"],
}


def make_settings(root: Path, **overrides) -> Settings:
    values = {
        "GROQ_API_KEY": "test-key",
        "RAW_DATA_DIR": str(root / "raw"),
        "PROCESSED_DATA_DIR": str(root / "processed"),
        "LEXICAL_INDEX_PATH": str(root / "index"),
        "QUERY_EXPANSIONS_PATH": str(root / "query_expansions.json"),
        "RAG_DEBUG_LOGS": False,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.fixture
def corpus_dir(tmp_path: Path) -> Path:
    raw = tmp_path / "raw"
    raw.mkdir()
    for name, text in SAMPLE_DOCUMENTS.items():
        (raw / name).write_text(text, encoding="utf-8")
    (tmp_path / "query_expansions.json").write_text(json.dumps(SAMPLE_EXPANSIONS), encoding="utf-8")
    return tmp_path


@pytest.fixture
def settings(corpus_dir: Path) -> Settings:
    clear_retrieval_cache()
    return make_settings(corpus_dir)


@pytest.fixture
def indexed_settings(settings: Settings) -> Settings:
    from app.ingestion.loader import ingest_documents

    ingest_documents(settings)
    return settings


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
