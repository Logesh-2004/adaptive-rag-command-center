export type StatusResponse = {
  status: string;
  llm_provider: string;
  generation_model: string;
  evaluator_model: string;
  rerank_model: string;
  vector_db_exists: boolean;
  indexed_documents: number;
  embedding_model: string;
  ollama_running: boolean;
};

export type QueryResponse = {
  query: string;
  answer: string;
  sources: string[];
  warning?: string | null;
  evaluation?: EvaluationPayload | null;
  timings: TimingMetrics;
  grounding_score?: number | null;
  grounding?: number | null;
  grounded?: boolean | null;
  hallucination_risk?: string | null;
  relevance_scores: number[];
  retrieval_score_trace: RetrievalScoreTrace[];
  rerank_model?: string | null;
  trace?: AdaptiveTrace | null;
};

export type AdaptiveTrace = {
  query_type?: string;
  complexity?: number;
  multi_hop?: boolean;
  top_k?: number;
  rerank_top_n?: number;
  rewritten_queries?: string[];
  retrieval_confidence?: number;
  retrieval_channels?: string[];
  corrective_attempts?: Array<Record<string, unknown>>;
  context_compression?: Record<string, number>;
};

export type RetrievalScoreTrace = {
  source?: string | null;
  vector_score?: number | null;
  vector_norm?: number | null;
  bm25_score?: number | null;
  bm25_norm?: number | null;
  rerank_score?: number | null;
  rerank_norm?: number | null;
  semantic_similarity?: number | null;
  metadata_boost?: number | null;
  intent_boost?: number | null;
  quality_score?: number | null;
  final_fused_score?: number | null;
  retrieval_channels?: string[];
};

export type TimingMetrics = {
  retrieval_ms: number;
  rerank_ms: number;
  generation_ms: number;
  evaluation_ms: number;
  total_ms: number;
};

export type EvaluationPayload = {
  status?: string;
  message?: string | null;
  faithfulness?: number | null;
  relevance?: number | null;
  grounding_score?: number | null;
  grounding?: number | null;
  grounded?: boolean | null;
  hallucination_risk?: "low" | "medium" | "high" | string | null;
  answer_relevance?: number | null;
  context_precision?: number | null;
  context_recall?: number | null;
  hallucination_score?: number | null;
  semantic_grounding_score?: number | null;
  retrieval_diversity_score?: number | null;
  unsupported_sentences?: string[];
  repair_recommended?: boolean;
  summary?: string | null;
  explanation?: string | null;
};

export type EvaluationResponse = EvaluationPayload;

export type RetrievalDebugResponse = {
  query: string;
  initial_documents: string[];
  reranked_documents: string[];
  relevance_scores: number[];
  retrieval_score_trace: RetrievalScoreTrace[];
  rerank_model?: string | null;
  trace?: AdaptiveTrace | null;
  timings: TimingMetrics;
  warning?: string | null;
};

export type ImprovementResponse = {
  summary: string;
  weak_records: number;
  suggestions: string[];
};

export type ActivityEvent = {
  id: string;
  time: string;
  type: "query" | "retrieval" | "evaluation" | "system" | "warning" | "error";
  title: string;
  detail: string;
  severity: "success" | "warning" | "error" | "info";
};
