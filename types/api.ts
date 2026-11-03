export type StatusResponse = {
  status: string;
  generation_provider: string;
  generation_provider_configured: boolean;
  generation_model: string;
  retrieval_strategy: string;
  lexical_index_exists: boolean;
  indexed_chunks: number;
  /** True when this deployment needs an admin token to rebuild the index. */
  admin_required?: boolean;
};

export type QueryResponse = {
  query: string;
  answer: string;
  sources: string[];
  initial_sources?: string[];
  warning?: string | null;
  evaluation?: EvaluationPayload | null;
  timings: TimingMetrics;
  grounding_score?: number | null;
  grounding?: number | null;
  grounded?: boolean | null;
  hallucination_risk?: string | null;
  relevance_scores: number[];
  retrieval_score_trace: RetrievalScoreTrace[];
  retrieval_strategy?: string | null;
  trace?: AdaptiveTrace | null;
};

export type AdaptiveTrace = {
  query_type?: string;
  complexity?: number;
  multi_hop?: boolean;
  top_k?: number;
  retrieval_top_n?: number;
  rewritten_queries?: string[];
  feedback_terms?: string[];
  retrieval_confidence?: number;
  retrieval_channels?: string[];
  corrective_attempts?: Array<Record<string, unknown>>;
  context_compression?: Record<string, number>;
};

export type RetrievalScoreTrace = {
  source?: string | null;
  bm25_score?: number | null;
  bm25_norm?: number | null;
  lexical_overlap?: number | null;
  metadata_boost?: number | null;
  intent_boost?: number | null;
  quality_score?: number | null;
  final_fused_score?: number | null;
  retrieval_channels?: string[];
};

export type TimingMetrics = {
  retrieval_ms: number;
  ranking_ms: number;
  generation_ms: number;
  evaluation_ms: number;
  correction_ms?: number;
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
  lexical_grounding_score?: number | null;
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
  ranked_documents: string[];
  relevance_scores: number[];
  retrieval_score_trace: RetrievalScoreTrace[];
  retrieval_strategy?: string | null;
  trace?: AdaptiveTrace | null;
  timings: TimingMetrics;
  warning?: string | null;
};

export type IngestResponse = {
  status: string;
  indexed_documents: number;
  chunks_created: number;
  ingested_chunks: number;
  message?: string | null;
  warnings: string[];
};

export type FeedbackResponse = {
  status: string;
  message: string;
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
