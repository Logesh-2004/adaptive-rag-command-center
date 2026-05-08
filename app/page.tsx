"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Activity, RefreshCw, Route, WandSparkles } from "lucide-react";
import { ChatConsole } from "@/components/chat-console";
import { EvaluationPanel } from "@/components/evaluation-panel";
import { ArchitectureMap } from "@/components/architecture-map";
import { LogsViewer } from "@/components/logs-viewer";
import { PipelineVisualizer } from "@/components/pipeline-visualizer";
import { RetrievalInspector } from "@/components/retrieval-inspector";
import { Sidebar } from "@/components/sidebar";
import { StatusPanel } from "@/components/status-panel";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ToastProvider } from "@/components/ui/toast";
import { useToast } from "@/hooks/use-toast";
import { ragApi } from "@/lib/api";
import type {
  ActivityEvent,
  EvaluationPayload,
  ImprovementResponse,
  QueryResponse,
  RetrievalDebugResponse,
  StatusResponse,
} from "@/types/api";

function now() {
  return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export default function DashboardPage() {
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [queryResponse, setQueryResponse] = useState<QueryResponse | null>(null);
  const [retrieval, setRetrieval] = useState<RetrievalDebugResponse | null>(null);
  const [evaluation, setEvaluation] = useState<EvaluationPayload | null>(null);
  const [improvement, setImprovement] = useState<ImprovementResponse | null>(null);
  const [lastQuery, setLastQuery] = useState("What is adaptive RAG?");
  const [latency, setLatency] = useState<number | null>(null);
  const [loading, setLoading] = useState({ status: false, query: false, retrieval: false, improve: false });
  const [events, setEvents] = useState<ActivityEvent[]>([]);
  const { messages, toast, dismiss } = useToast();

  const addEvent = useCallback((event: Omit<ActivityEvent, "id" | "time">) => {
    setEvents((current) => [
      { ...event, id: crypto.randomUUID(), time: now() },
      ...current,
    ].slice(0, 12));
  }, []);

  const refreshStatus = useCallback(async () => {
    setLoading((current) => ({ ...current, status: true }));
    try {
      const payload = await ragApi.status();
      setStatus(payload);
      addEvent({
        type: "system",
        title: "Status refreshed",
        detail: `Vector DB ${payload.vector_db_exists ? "ready" : "missing"} with ${payload.indexed_documents} indexed chunks.`,
        severity: payload.vector_db_exists ? "success" : "warning",
      });
    } catch (error) {
      toast({ title: "Status request failed", description: String(error), variant: "destructive" });
      addEvent({ type: "error", title: "Status request failed", detail: String(error), severity: "error" });
    } finally {
      setLoading((current) => ({ ...current, status: false }));
    }
  }, [addEvent, toast]);

  useEffect(() => {
    refreshStatus();
  }, [refreshStatus]);

  const runRetrievalTrace = useCallback(
    async (query = lastQuery) => {
      setLoading((current) => ({ ...current, retrieval: true }));
      try {
        const payload = await ragApi.debugRetrieval(query);
        setRetrieval(payload);
        addEvent({
          type: payload.warning ? "warning" : "retrieval",
          title: "Retrieval trace complete",
          detail: payload.warning || `${payload.initial_documents.length} retrieved, ${payload.reranked_documents.length} reranked.`,
          severity: payload.warning ? "warning" : "success",
        });
      } catch (error) {
        toast({ title: "Retrieval trace failed", description: String(error), variant: "destructive" });
        addEvent({ type: "error", title: "Retrieval trace failed", detail: String(error), severity: "error" });
      } finally {
        setLoading((current) => ({ ...current, retrieval: false }));
      }
    },
    [addEvent, lastQuery, toast],
  );

  const runQuery = useCallback(
    async (query: string) => {
      setLastQuery(query);
      setLoading((current) => ({ ...current, query: true }));
      setLatency(null);
      const started = performance.now();
      setQueryResponse({
        query,
        answer: "",
        sources: [],
        timings: { retrieval_ms: 0, rerank_ms: 0, generation_ms: 0, evaluation_ms: 0, total_ms: 0 },
        relevance_scores: [],
        retrieval_score_trace: [],
      });
      try {
        await ragApi.streamQuery(query, (event) => {
          const elapsed = Math.round(performance.now() - started);
          setLatency(Math.round(event.timings?.total_ms || event.timings?.generation_ms || elapsed));

          if (event.type === "retrieval") {
            setRetrieval({
              query,
              initial_documents: event.sources ?? [],
              reranked_documents: [],
              relevance_scores: [],
              retrieval_score_trace: [],
              timings: event.timings ?? { retrieval_ms: 0, rerank_ms: 0, generation_ms: 0, evaluation_ms: 0, total_ms: 0 },
              warning: null,
            });
          }

          if (event.type === "rerank") {
            setRetrieval((current) => ({
              query,
              initial_documents: current?.initial_documents ?? event.sources ?? [],
              reranked_documents: event.sources ?? [],
              relevance_scores: event.relevance_scores ?? [],
              retrieval_score_trace: event.retrieval_score_trace ?? [],
              rerank_model: event.rerank_model,
              trace: event.trace,
              timings: event.timings ?? current?.timings ?? { retrieval_ms: 0, rerank_ms: 0, generation_ms: 0, evaluation_ms: 0, total_ms: 0 },
              warning: null,
            }));
          }

          if (event.type === "token") {
            setQueryResponse((current) => ({
              query,
              answer: `${current?.answer ?? ""}${event.token}`,
              sources: current?.sources ?? [],
              timings: event.timings ?? current?.timings ?? { retrieval_ms: 0, rerank_ms: 0, generation_ms: 0, evaluation_ms: 0, total_ms: 0 },
              relevance_scores: current?.relevance_scores ?? [],
              retrieval_score_trace: current?.retrieval_score_trace ?? [],
              rerank_model: current?.rerank_model,
            }));
          }

          if (event.type === "done") {
            setQueryResponse(event);
            setRetrieval({
              query,
              initial_documents: event.sources,
              reranked_documents: event.sources,
              relevance_scores: event.relevance_scores,
              retrieval_score_trace: event.retrieval_score_trace,
              rerank_model: event.rerank_model,
              trace: event.trace,
              timings: event.timings,
              warning: event.warning || null,
            });
            setEvaluation(event.evaluation ?? (event.warning ? { status: "warning", message: "Evaluation unavailable" } : null));
            addEvent({
              type: event.warning ? "warning" : "query",
              title: "Query pipeline finished",
              detail: event.warning || `Answered with ${event.sources.length} context chunks in ${Math.round(event.timings?.total_ms ?? elapsed)} ms.`,
              severity: event.warning ? "warning" : "success",
            });
            if (event.warning) {
              toast({ title: "Pipeline degraded", description: event.warning });
            }
          }

          if (event.type === "error") {
            throw new Error(event.message);
          }
        });
      } catch (error) {
        toast({ title: "Query failed", description: String(error), variant: "destructive" });
        addEvent({ type: "error", title: "Query failed", detail: String(error), severity: "error" });
      } finally {
        setLoading((current) => ({ ...current, query: false }));
      }
    },
    [addEvent, toast],
  );

  const runImprove = useCallback(async () => {
    setLoading((current) => ({ ...current, improve: true }));
    try {
      const payload = await ragApi.improve();
      setImprovement(payload);
      addEvent({
        type: "evaluation",
        title: "Improvement scan complete",
        detail: `${payload.weak_records} weak records found. ${payload.summary}`,
        severity: payload.weak_records ? "warning" : "success",
      });
    } catch (error) {
      toast({ title: "Improvement scan failed", description: String(error), variant: "destructive" });
      addEvent({ type: "error", title: "Improvement scan failed", detail: String(error), severity: "error" });
    } finally {
      setLoading((current) => ({ ...current, improve: false }));
    }
  }, [addEvent, toast]);

  const healthBadge = useMemo(() => {
    if (!status) return "Connecting";
    if (!status.vector_db_exists) return "Index Required";
    if (!status.ollama_running) return "Ollama Offline";
    return "Operational";
  }, [status]);

  return (
    <ToastProvider messages={messages} onDismiss={dismiss}>
      <div className="relative flex min-h-screen">
        <Sidebar />
        <main className="min-w-0 flex-1">
          <header className="sticky top-0 z-30 border-b border-white/10 bg-background/70 px-4 py-4 backdrop-blur-2xl md:px-6">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <Badge className="text-primary">
                    <Activity className="mr-1 h-3.5 w-3.5" />
                    {healthBadge}
                  </Badge>
                  <Badge>{status?.generation_model ?? "model pending"}</Badge>
                  <Badge>{status?.rerank_model ?? "rerank pending"}</Badge>
                  <Badge>{status?.evaluator_model ?? "evaluator pending"}</Badge>
                </div>
                <h1 className="mt-3 bg-gradient-to-r from-white via-cyan-100 to-slate-400 bg-clip-text text-2xl font-semibold tracking-normal text-transparent md:text-4xl">
                  Adaptive RAG Command Center
                </h1>
                <p className="mt-1 max-w-3xl text-sm leading-6 text-muted-foreground">
                  Observe retrieval quality, LLM degradation, evaluation signals, and index health from one operations surface.
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button variant="outline" onClick={refreshStatus} disabled={loading.status}>
                  <RefreshCw className={loading.status ? "h-4 w-4 animate-spin" : "h-4 w-4"} />
                  Status
                </Button>
                <Button variant="secondary" onClick={runImprove} disabled={loading.improve}>
                  <WandSparkles className={loading.improve ? "h-4 w-4 animate-pulse" : "h-4 w-4"} />
                  Improve
                </Button>
              </div>
            </div>
          </header>

          <div className="space-y-5 p-4 md:p-6">
            <PipelineVisualizer active={loading.query || Boolean(queryResponse?.answer)} />
            <StatusPanel status={status} loading={loading.status} />

            <div className="grid gap-5 xl:grid-cols-[minmax(0,1.15fr)_minmax(360px,0.85fr)]">
              <ChatConsole response={queryResponse} loading={loading.query} latency={latency} onSubmit={runQuery} />
              <div className="space-y-5">
                <EvaluationPanel evaluation={evaluation} loading={loading.query} />
                <Card>
                  <CardHeader>
                    <div className="flex items-center justify-between gap-3">
                      <CardTitle className="flex items-center gap-2">
                        <Route className="h-4 w-4 text-primary" />
                        Improvement Notes
                      </CardTitle>
                      <Badge>{improvement?.weak_records ?? 0} weak</Badge>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-3 text-sm text-muted-foreground">
                    <p>{improvement?.summary ?? "Run an improvement scan to inspect evaluation drift and tuning suggestions."}</p>
                    {improvement?.suggestions?.length ? (
                      <div className="space-y-2">
                        {improvement.suggestions.map((suggestion) => (
                          <div key={suggestion} className="rounded-md border border-white/10 bg-white/[0.04] p-3">
                            {suggestion}
                          </div>
                        ))}
                      </div>
                    ) : null}
                  </CardContent>
                </Card>
              </div>
            </div>

            <RetrievalInspector retrieval={retrieval} loading={loading.retrieval} onRefresh={() => runRetrievalTrace()} />
            <ArchitectureMap />
            <LogsViewer events={events} />
          </div>
        </main>
      </div>
    </ToastProvider>
  );
}
