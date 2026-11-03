from pathlib import Path

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


def _path_from_env(value: str) -> Path:
    return Path(value).expanduser()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    groq_api_key: SecretStr | None = Field(None, validation_alias="GROQ_API_KEY")
    groq_model: str = Field("openai/gpt-oss-20b", validation_alias="GROQ_MODEL")
    groq_api_base: str = Field("https://api.groq.com/openai/v1", validation_alias="GROQ_API_BASE")
    lexical_index_path: Path = Field(
        default_factory=lambda: Path("vector_db/bm25_store"),
        validation_alias=AliasChoices("LEXICAL_INDEX_PATH", "VECTOR_DB_PATH"),
    )
    raw_data_dir: Path = Field(default_factory=lambda: Path("data/raw"), validation_alias="RAW_DATA_DIR")
    processed_data_dir: Path = Field(default_factory=lambda: Path("data/processed"), validation_alias="PROCESSED_DATA_DIR")
    query_expansions_path: Path = Field(
        default_factory=lambda: Path("data/query_expansions.json"), validation_alias="QUERY_EXPANSIONS_PATH"
    )
    chunk_size: int = Field(800, validation_alias="CHUNK_SIZE", ge=100)
    chunk_overlap: int = Field(120, validation_alias="CHUNK_OVERLAP", ge=0)
    retrieval_top_k: int = Field(3, validation_alias="RETRIEVAL_TOP_K", ge=1)
    retrieval_top_n: int = Field(2, validation_alias="RETRIEVAL_TOP_N", ge=1)
    llm_temperature: float = Field(0.05, validation_alias="LLM_TEMPERATURE", ge=0.0, le=1.0)
    generation_num_predict: int = Field(512, validation_alias="GENERATION_MAX_TOKENS", ge=32)
    grounding_overlap_threshold: float = Field(0.2, validation_alias="GROUNDING_OVERLAP_THRESHOLD", ge=0.0, le=1.0)
    retrieval_confidence_threshold: float = Field(0.2, validation_alias="RETRIEVAL_CONFIDENCE_THRESHOLD", ge=0.0, le=1.0)
    rag_debug_logs: bool = Field(False, validation_alias="RAG_DEBUG_LOGS")
    log_max_bytes: int = Field(5 * 1024 * 1024, validation_alias="LOG_MAX_BYTES", ge=1024)
    # Public-demo guards (see app/api/security.py); empty or 0 turns each one off.
    proxy_secret: SecretStr | None = Field(None, validation_alias="PROXY_SECRET")
    admin_token: SecretStr | None = Field(None, validation_alias="ADMIN_TOKEN")
    query_rate_limit_per_minute: int = Field(0, validation_alias="QUERY_RATE_LIMIT_PER_MINUTE", ge=0)
    daily_query_limit: int = Field(0, validation_alias="DAILY_QUERY_LIMIT", ge=0)
    build_index_on_startup: bool = Field(True, validation_alias="BUILD_INDEX_ON_STARTUP")

    @property
    def active_generation_model(self) -> str:
        return self.groq_model

    @property
    def groq_key_configured(self) -> bool:
        return bool(self.groq_api_key and self.groq_api_key.get_secret_value().strip())

    @property
    def generation_provider_configured(self) -> bool:
        return self.groq_key_configured

    @property
    def proxy_secret_value(self) -> str | None:
        value = self.proxy_secret.get_secret_value().strip() if self.proxy_secret else ""
        return value or None

    @property
    def admin_token_value(self) -> str | None:
        value = self.admin_token.get_secret_value().strip() if self.admin_token else ""
        return value or None

    @property
    def groq_api_key_value(self) -> str | None:
        if not self.groq_key_configured:
            return None
        return self.groq_api_key.get_secret_value()


def get_settings() -> Settings:
    settings = Settings()
    if settings.chunk_overlap >= settings.chunk_size:
        raise ValueError("CHUNK_OVERLAP must be smaller than CHUNK_SIZE")
    settings.lexical_index_path = _path_from_env(str(settings.lexical_index_path))
    settings.raw_data_dir = _path_from_env(str(settings.raw_data_dir))
    settings.processed_data_dir = _path_from_env(str(settings.processed_data_dir))
    settings.query_expansions_path = _path_from_env(str(settings.query_expansions_path))
    return settings
