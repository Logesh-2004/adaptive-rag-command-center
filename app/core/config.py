from pathlib import Path

from pydantic_settings import BaseSettings
from pydantic_settings import SettingsConfigDict
from pydantic import Field


def _path_from_env(value: str) -> Path:
    return Path(value).expanduser()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    ollama_base_url: str = Field("http://127.0.0.1:11434", validation_alias="OLLAMA_BASE_URL")
    generation_model: str = Field("llama3", validation_alias="GENERATION_MODEL")
    evaluator_model: str = Field("heuristic", validation_alias="EVALUATOR_MODEL")
    rerank_model: str = Field("cross-encoder/ms-marco-MiniLM-L-6-v2", validation_alias="RERANK_MODEL")
    embedding_model: str = Field("nomic-embed-text", validation_alias="EMBEDDING_MODEL")
    vector_db_path: Path = Field(
        default_factory=lambda: Path("vector_db/faiss_store"),
        validation_alias="VECTOR_DB_PATH",
    )
    raw_data_dir: Path = Field(
        default_factory=lambda: Path("data/raw"),
        validation_alias="RAW_DATA_DIR",
    )
    processed_data_dir: Path = Field(
        default_factory=lambda: Path("data/processed"),
        validation_alias="PROCESSED_DATA_DIR",
    )
    chunk_size: int = Field(800, validation_alias="CHUNK_SIZE", ge=100)
    chunk_overlap: int = Field(120, validation_alias="CHUNK_OVERLAP", ge=0)
    retrieval_top_k: int = Field(3, validation_alias="RETRIEVAL_TOP_K", ge=1)
    rerank_top_n: int = Field(2, validation_alias="RERANK_TOP_N", ge=1)
    llm_temperature: float = Field(0.1, validation_alias="LLM_TEMPERATURE", ge=0.0, le=1.0)
    generation_num_predict: int = Field(180, validation_alias="GENERATION_NUM_PREDICT", ge=32)
    evaluator_num_predict: int = Field(120, validation_alias="EVALUATOR_NUM_PREDICT", ge=16)
    grounding_similarity_threshold: float = Field(0.2, validation_alias="GROUNDING_SIMILARITY_THRESHOLD", ge=0.0, le=1.0)
    grounding_overlap_threshold: float = Field(0.2, validation_alias="GROUNDING_OVERLAP_THRESHOLD", ge=0.0, le=1.0)
    retrieval_confidence_threshold: float = Field(0.2, validation_alias="RETRIEVAL_CONFIDENCE_THRESHOLD", ge=0.0, le=1.0)


def get_settings() -> Settings:
    settings = Settings()
    if settings.chunk_overlap >= settings.chunk_size:
        raise ValueError("CHUNK_OVERLAP must be smaller than CHUNK_SIZE")
    settings.vector_db_path = _path_from_env(str(settings.vector_db_path))
    settings.raw_data_dir = _path_from_env(str(settings.raw_data_dir))
    settings.processed_data_dir = _path_from_env(str(settings.processed_data_dir))
    return settings
