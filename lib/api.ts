import type {
  EvaluationResponse,
  FeedbackResponse,
  ImprovementResponse,
  IngestResponse,
  QueryResponse,
  RetrievalDebugResponse,
  StatusResponse,
} from "@/types/api";

const API_BASE = "/rag-api";

export type StreamEvent =
  | { type: "retrieval"; timings?: QueryResponse["timings"]; sources?: string[] }
  | { type: "rank"; timings?: QueryResponse["timings"]; sources?: string[]; relevance_scores?: number[]; retrieval_score_trace?: QueryResponse["retrieval_score_trace"]; retrieval_strategy?: string; trace?: QueryResponse["trace"] }
  | { type: "token"; token: string; timings?: QueryResponse["timings"] }
  | ({ type: "done" } & QueryResponse)
  | { type: "error"; message: string; error_code?: string; timings?: QueryResponse["timings"] };

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });

  const text = await response.text();
  const payload = text ? safeJson(text) : null;
  if (!response.ok) {
    const message =
      payload?.message ||
      payload?.detail?.message ||
      payload?.detail ||
      text ||
      `Backend request failed with HTTP ${response.status}`;
    throw new Error(String(message));
  }

  return payload as T;
}

function safeJson(text: string) {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

export const ragApi = {
  status: () => request<StatusResponse>("/status"),
  query: (query: string) =>
    request<QueryResponse>("/query", {
      method: "POST",
      body: JSON.stringify({ query }),
    }),
  streamQuery: async (query: string, onEvent: (event: StreamEvent) => void) => {
    const response = await fetch(`${API_BASE}/query/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
    });
    if (!response.ok || !response.body) {
      const text = await response.text();
      throw new Error(text || `Backend request failed with HTTP ${response.status}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";
      for (const line of lines) {
        if (!line.trim()) continue;
        onEvent(JSON.parse(line) as StreamEvent);
      }
    }
    if (buffer.trim()) {
      onEvent(JSON.parse(buffer) as StreamEvent);
    }
  },
  evaluate: (query: string, context: string[], answer: string) =>
    request<EvaluationResponse>("/evaluate", {
      method: "POST",
      body: JSON.stringify({ query, context, answer }),
    }),
  debugRetrieval: (query: string) =>
    request<RetrievalDebugResponse>("/debug/retrieval", {
      method: "POST",
      body: JSON.stringify({ query }),
    }),
  improve: () =>
    request<ImprovementResponse>("/improve", {
      method: "POST",
      body: JSON.stringify({}),
    }),
  ingest: (adminToken?: string) =>
    request<IngestResponse>("/ingest", {
      method: "POST",
      body: JSON.stringify({}),
      headers: adminToken ? { "X-Admin-Token": adminToken } : undefined,
    }),
  feedback: (query: string, answer: string, rating: number, comment?: string) =>
    request<FeedbackResponse>("/feedback", {
      method: "POST",
      body: JSON.stringify({ query, answer, rating, comment: comment || null }),
    }),
};
