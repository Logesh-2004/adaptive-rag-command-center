"use client";

import { FormEvent, useState } from "react";
import { AlertTriangle, Bot, CheckCircle2, Clock3, SendHorizonal, Sparkles, XCircle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import type { QueryResponse } from "@/types/api";

export function ChatConsole({
  response,
  loading,
  latency,
  onSubmit,
}: {
  response?: QueryResponse | null;
  loading: boolean;
  latency?: number | null;
  onSubmit: (query: string) => void;
}) {
  const [query, setQuery] = useState("What is adaptive RAG?");

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!query.trim() || loading) return;
    onSubmit(query.trim());
  }

  return (
    <Card id="chat">
      <CardHeader>
        <div className="flex items-center justify-between gap-3">
          <CardTitle className="flex items-center gap-2">
            <Bot className="h-4 w-4 text-primary" />
            Chat Interface
          </CardTitle>
          {latency != null ? (
            <Badge className="gap-1">
              <Clock3 className="h-3.5 w-3.5" />
              {latency} ms
            </Badge>
          ) : null}
          {loading ? <Badge className="gap-1 text-primary"><Sparkles className="h-3.5 w-3.5 animate-pulse" />Streaming</Badge> : null}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <form onSubmit={submit} className="space-y-3">
          <Textarea
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Ask a question against the indexed knowledge base..."
            className="min-h-[112px]"
          />
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="text-xs text-muted-foreground">Runs retrieval, cross-encoder rerank, streaming generation, and heuristic evaluation.</div>
            <Button type="submit" disabled={loading}>
              {loading ? <Sparkles className="h-4 w-4 animate-pulse" /> : <SendHorizonal className="h-4 w-4" />}
              {loading ? "Running" : "Run Query"}
            </Button>
          </div>
        </form>

        <div className="depth-card p-4">
          <div className="mb-3 flex items-center justify-between gap-3">
            <span className="metric-label">Generated Answer</span>
            <div className="flex flex-wrap items-center gap-2">
              {response?.grounded != null ? (
                <Badge className={response.grounded ? "gap-1 text-primary" : "gap-1 text-amber-300"}>
                  {response.grounded ? <CheckCircle2 className="h-3.5 w-3.5" /> : <XCircle className="h-3.5 w-3.5" />}
                  {response.grounded ? "Grounded" : "Ungrounded"}
                </Badge>
              ) : null}
              {response?.hallucination_risk ? <Badge>Risk: {response.hallucination_risk}</Badge> : null}
              <Badge>{response?.sources?.length ?? 0} sources</Badge>
            </div>
          </div>
          {response ? (
            <div className="space-y-3">
              {response.warning ? (
                <div className="flex items-start gap-2 rounded-md border border-amber-300/20 bg-amber-300/10 p-3 text-sm text-amber-200">
                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                  <span>{response.warning}</span>
                </div>
              ) : null}
              <p className="whitespace-pre-wrap text-sm leading-7 text-slate-100">
                {response.answer}
                {loading ? <span className="ml-1 inline-block h-4 w-1 animate-pulse bg-primary align-middle" /> : null}
              </p>
              {loading && !response.answer ? <div className="h-24 rounded-md shimmer" /> : null}
              {response.timings ? (
                <div className="grid gap-2 pt-2 sm:grid-cols-5">
                  {[
                    ["Retrieval", response.timings.retrieval_ms],
                    ["Rerank", response.timings.rerank_ms],
                    ["Generation", response.timings.generation_ms],
                    ["Evaluation", response.timings.evaluation_ms],
                    ["Total", response.timings.total_ms],
                  ].map(([label, value]) => (
                    <div key={label} className="depth-card p-2">
                      <div className="text-[10px] font-medium uppercase text-muted-foreground">{label}</div>
                      <div className="mt-1 text-sm font-semibold">{Math.round(Number(value))} ms</div>
                    </div>
                  ))}
                </div>
              ) : null}
            </div>
          ) : (
            <div className="grid gap-3 md:grid-cols-3">
              {["What is adaptive RAG?", "How does Adaptive RAG reduce hallucination?", "Compare RAG and corrective RAG."].map((prompt) => (
                <button
                  key={prompt}
                  type="button"
                  onClick={() => onSubmit(prompt)}
                  className="depth-card p-3 text-left text-sm text-muted-foreground hover:text-foreground"
                >
                  {prompt}
                </button>
              ))}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
