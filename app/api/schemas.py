from pydantic import BaseModel, Field
from typing import List, Optional


class IngestResponse(BaseModel):
    status: str
    indexed_documents: int
    chunks_created: int
    ingested_chunks: int
    message: Optional[str] = None


class QueryRequest(BaseModel):
    query: str


class TimingMetrics(BaseModel):
    retrieval_ms: float = 0.0
    rerank_ms: float = 0.0
    generation_ms: float = 0.0
    evaluation_ms: float = 0.0
    total_ms: float = 0.0


class QueryResponse(BaseModel):
    query: str
    answer: str
    sources: List[str]
    warning: Optional[str] = None
    evaluation: Optional[dict] = None
    timings: TimingMetrics = Field(default_factory=TimingMetrics)
    grounding_score: Optional[float] = None
    grounding: Optional[float] = None
    grounded: Optional[bool] = None
    hallucination_risk: Optional[str] = None
    relevance_scores: List[float] = Field(default_factory=list)
    retrieval_score_trace: List[dict] = Field(default_factory=list)
    rerank_model: Optional[str] = None
    trace: Optional[dict] = None


class EvaluationRequest(BaseModel):
    query: str
    answer: str
    context: List[str]


class EvaluationResponse(BaseModel):
    status: str = "success"
    message: Optional[str] = None
    faithfulness: Optional[float] = None
    relevance: Optional[float] = None
    grounding_score: Optional[float] = None
    grounding: Optional[float] = None
    grounded: Optional[bool] = None
    hallucination_risk: Optional[str] = None
    answer_relevance: Optional[float] = None
    context_precision: Optional[float] = None
    context_recall: Optional[float] = None
    hallucination_score: Optional[float] = None
    semantic_grounding_score: Optional[float] = None
    retrieval_diversity_score: Optional[float] = None
    unsupported_sentences: List[str] = Field(default_factory=list)
    repair_recommended: Optional[bool] = None
    summary: Optional[str] = None
    explanation: Optional[str] = None


class ImprovementResponse(BaseModel):
    summary: str
    weak_records: int
    suggestions: List[str]


class RetrievalDebugRequest(BaseModel):
    query: str


class RetrievalDebugResponse(BaseModel):
    query: str
    initial_documents: List[str]
    reranked_documents: List[str]
    relevance_scores: List[float] = Field(default_factory=list)
    retrieval_score_trace: List[dict] = Field(default_factory=list)
    rerank_model: Optional[str] = None
    trace: Optional[dict] = None
    timings: TimingMetrics = Field(default_factory=TimingMetrics)
    warning: Optional[str] = None


class FeedbackRequest(BaseModel):
    query: str
    answer: str
    rating: int
    comment: Optional[str] = None


class StatusResponse(BaseModel):
    status: str
    llm_provider: str
    generation_model: str
    evaluator_model: str
    rerank_model: str
    vector_db_exists: bool
    indexed_documents: int
    embedding_model: str
    ollama_running: bool
