"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Activity, RefreshCw, Route, SlidersHorizontal } from "lucide-react";
import { ChatConsole, type JourneyStage } from "@/components/chat-console";
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
  const [journeyStage, setJourneyStage] = useState<JourneyStage>("idle");
  const [loading, setLoading] = useState({ status: false, query: false, retrieval: false, improve: false });
  const [events, setEvents] = useState<ActivityEvent[]>([]);
  const arrivalTimer = useRef<number | null>(null);
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
        detail: `BM25 index ${payload.lexical_index_exists ? "ready" : "missing"} with ${payload.indexed_chunks} indexed chunks.`,
        severity: payload.lexical_index_exists ? "success" : "warning",
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

  useEffect(() => () => {
    if (arrivalTimer.current !== null) window.clearTimeout(arrivalTimer.current);
  }, []);

  const runRetrievalTrace = useCallback(
    async (query = lastQuery) => {
      setLoading((current) => ({ ...current, retrieval: true }));
      try {
        const payload = await ragApi.debugRetrieval(query);
        setRetrieval(payload);
        addEvent({
          type: payload.warning ? "warning" : "retrieval",
          title: "Retrieval trace complete",
          detail: payload.warning || `${payload.initial_documents.length} retrieved, ${payload.ranked_documents.length} ranked.`,
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
      if (arrivalTimer.current !== null) window.clearTimeout(arrivalTimer.current);
      arrivalTimer.current = null;
      setJourneyStage("launching");
      setLastQuery(query);
      setLoading((current) => ({ ...current, query: true }));
      setLatency(null);
      setEvaluation(null);
      setRetrieval(null);
      const started = performance.now();
      setQueryResponse({
        query,
        answer: "",
        sources: [],
        timings: { retrieval_ms: 0, ranking_ms: 0, generation_ms: 0, evaluation_ms: 0, total_ms: 0 },
        relevance_scores: [],
        retrieval_score_trace: [],
      });
      let receivedDone = false;
      try {
        await ragApi.streamQuery(query, (event) => {
          const elapsed = Math.round(performance.now() - started);
          setLatency(Math.round(event.timings?.total_ms || event.timings?.generation_ms || elapsed));

          if (event.type === "retrieval") {
            setJourneyStage("retrieving");
            setRetrieval({
              query,
              initial_documents: event.sources ?? [],
              ranked_documents: [],
              relevance_scores: [],
              retrieval_score_trace: [],
              timings: event.timings ?? { retrieval_ms: 0, ranking_ms: 0, generation_ms: 0, evaluation_ms: 0, total_ms: 0 },
              warning: null,
            });
          }

          if (event.type === "rank") {
            setJourneyStage("crossing");
            setRetrieval((current) => ({
              query,
              initial_documents: current?.initial_documents ?? event.sources ?? [],
              ranked_documents: event.sources ?? [],
              relevance_scores: event.relevance_scores ?? [],
              retrieval_score_trace: event.retrieval_score_trace ?? [],
              retrieval_strategy: event.retrieval_strategy,
              trace: event.trace,
              timings: event.timings ?? current?.timings ?? { retrieval_ms: 0, ranking_ms: 0, generation_ms: 0, evaluation_ms: 0, total_ms: 0 },
              warning: null,
            }));
          }

          if (event.type === "token") {
            setJourneyStage("generating");
            setQueryResponse((current) => ({
              query,
              answer: `${current?.answer ?? ""}${event.token}`,
              sources: current?.sources ?? [],
              timings: event.timings ?? current?.timings ?? { retrieval_ms: 0, ranking_ms: 0, generation_ms: 0, evaluation_ms: 0, total_ms: 0 },
              relevance_scores: current?.relevance_scores ?? [],
              retrieval_score_trace: current?.retrieval_score_trace ?? [],
              retrieval_strategy: current?.retrieval_strategy,
            }));
          }

          if (event.type === "done") {
            receivedDone = true;
            setJourneyStage("landing");
            arrivalTimer.current = window.setTimeout(() => {
              setJourneyStage("arrived");
              arrivalTimer.current = null;
            }, 750);
            setQueryResponse(event);
            setRetrieval({
              query,
              initial_documents: event.sources,
              ranked_documents: event.sources,
              relevance_scores: event.relevance_scores,
              retrieval_score_trace: event.retrieval_score_trace,
              retrieval_strategy: event.retrieval_strategy,
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
        if (arrivalTimer.current !== null) window.clearTimeout(arrivalTimer.current);
        arrivalTimer.current = null;
        setJourneyStage("error");
        toast({ title: "Query failed", description: String(error), variant: "destructive" });
        addEvent({ type: "error", title: "Query failed", detail: String(error), severity: "error" });
      } finally {
        if (!receivedDone) setJourneyStage("error");
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
    if (!status.lexical_index_exists) return "Index Required";
    if (!status.generation_provider_configured) return "Groq API Key Needed";
    return "Configured";
  }, [status]);

  return (
    <ToastProvider messages={messages} onDismiss={dismiss}>
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[100] focus:rounded-xl focus:bg-primary focus:px-4 focus:py-3 focus:font-semibold focus:text-primary-foreground"
      >
        Skip to main content
      </a>
      <div className="dashboard-shell relative flex min-h-dvh flex-col lg:flex-row">
        <Sidebar />
        <main id="main-content" className="dashboard-main min-w-0 flex-1" tabIndex={-1}>
          <header className="workspace-topbar sticky top-0 z-30 px-4 py-3 md:px-8">
            <div className="mx-auto flex max-w-[1680px] items-center justify-between gap-4">
              <div className="flex min-w-0 items-center gap-3 text-sm">
                <span className="font-mono text-xs tracking-[0.18em] text-primary">AR / 01</span>
                <span className="hidden h-4 w-px bg-white/15 sm:block" />
                <span className="truncate text-muted-foreground">Knowledge workspace</span>
              </div>
              <Badge className={status?.generation_provider_configured && status?.lexical_index_exists ? "gap-2 text-success" : "gap-2 text-warning"}>
                <Activity aria-hidden="true" className="h-3.5 w-3.5" />
                {healthBadge}
              </Badge>
            </div>
          </header>

          <div className="dashboard-content space-y-5 p-4 md:p-6 xl:p-8">
            <section className="workspace-intro">
              <div>
                <p className="section-kicker">Mission control · Knowledge relay</p>
                <h1 className="workspace-title mt-3">Adaptive RAG</h1>
                <p className="mt-3 max-w-2xl text-sm leading-6 text-muted-foreground md:text-base">
                  Launch a question through your local corpus, follow the retrieval layers, and bring a grounded answer back to the dock.
                </p>
              </div>
              <div className="flex shrink-0 flex-wrap gap-2 pt-4 sm:pt-0">
                <Button variant="outline" onClick={refreshStatus} disabled={loading.status}>
                  <RefreshCw aria-hidden="true" className={loading.status ? "h-4 w-4 animate-spin" : "h-4 w-4"} />
                  Refresh
                </Button>
                <Button variant="secondary" onClick={runImprove} disabled={loading.improve}>
                  <SlidersHorizontal aria-hidden="true" className={loading.improve ? "h-4 w-4 animate-pulse" : "h-4 w-4"} />
                  Review tuning
                </Button>
              </div>
            </section>

            <StatusPanel status={status} loading={loading.status} />

            <ChatConsole
              response={queryResponse}
              loading={loading.query}
              latency={latency}
              journeyStage={journeyStage}
              onSubmit={runQuery}
            />

            <div className="grid items-stretch gap-5 xl:grid-cols-[minmax(0,1.15fr)_minmax(300px,0.85fr)]">
              <EvaluationPanel evaluation={evaluation} loading={loading.query} />
              <Card className="h-full">
                <CardHeader className="space-y-0">
                  <p className="section-kicker">Tuning history</p>
                  <div className="flex items-center justify-between gap-3">
                    <CardTitle className="flex items-center gap-2">
                      <Route aria-hidden="true" className="h-4 w-4 text-primary" />
                      Refinement notes
                    </CardTitle>
                    <Badge>{improvement ? `${improvement.weak_records} weak` : "Not run"}</Badge>
                  </div>
                </CardHeader>
                <CardContent className="space-y-3 pt-0 text-sm text-muted-foreground">
                  <p>{improvement?.summary ?? "Review evaluation history for retrieval drift and tuning opportunities."}</p>
                  {improvement?.suggestions?.length ? (
                    <div className="space-y-2">
                      {improvement.suggestions.map((suggestion) => (
                        <div key={suggestion} className="depth-card p-3">
                          {suggestion}
                        </div>
                      ))}
                    </div>
                  ) : null}
                </CardContent>
              </Card>
            </div>

            <PipelineVisualizer active={loading.query} />
            <div className="grid items-start gap-5 2xl:grid-cols-2">
              <RetrievalInspector retrieval={retrieval} loading={loading.retrieval} onRefresh={() => runRetrievalTrace()} />
              <ArchitectureMap />
            </div>
            <LogsViewer events={events} />
          </div>
        </main>
      </div>
    </ToastProvider>
  );
}
