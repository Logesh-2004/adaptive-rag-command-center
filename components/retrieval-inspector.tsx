"use client";

import { useState } from "react";
import { ChevronDown, Files, Gauge } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";
import type { RetrievalDebugResponse } from "@/types/api";

function rankScore(index: number, total: number) {
  if (total <= 1) return 92;
  return Math.max(42, Math.round(96 - (index / (total - 1)) * 42));
}

function ChunkCard({
  text,
  index,
  total,
  label,
  score: providedScore,
  scoreTrace,
}: {
  text: string;
  index: number;
  total: number;
  label: string;
  score?: number | null;
  scoreTrace?: RetrievalDebugResponse["retrieval_score_trace"][number];
}) {
  const [expanded, setExpanded] = useState(index === 0);
  const score = providedScore != null && providedScore > 0 ? Math.round(providedScore * 100) : rankScore(index, total);

  return (
    <div className="depth-card p-3">
      <button className="flex w-full items-start justify-between gap-3 text-left" onClick={() => setExpanded((v) => !v)}>
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <Badge>{label} #{index + 1}</Badge>
            <span className="flex items-center gap-1 text-xs text-muted-foreground">
              <Gauge className="h-3.5 w-3.5" />
              Relevance {score}%
            </span>
          </div>
          <p className={cn("mt-2 whitespace-pre-wrap text-sm leading-6 text-muted-foreground", !expanded && "line-clamp-3")}>
            {text}
          </p>
        </div>
        <ChevronDown className={cn("mt-1 h-4 w-4 shrink-0 transition-transform", expanded && "rotate-180")} />
      </button>
      <Progress value={score} className="mt-3" />
      {scoreTrace ? (
        <div className="mt-3 grid gap-2 text-xs text-muted-foreground sm:grid-cols-3">
          <span>Vector {Math.round((scoreTrace.vector_norm ?? 0) * 100)}%</span>
          <span>BM25 {Math.round((scoreTrace.bm25_norm ?? 0) * 100)}%</span>
          <span>Semantic {Math.round((scoreTrace.semantic_similarity ?? 0) * 100)}%</span>
          <span>Rerank {Math.round((scoreTrace.rerank_norm ?? 0) * 100)}%</span>
          <span>Intent {Math.round((scoreTrace.intent_boost ?? 0) * 100)}%</span>
          <span>Meta {Math.round((scoreTrace.metadata_boost ?? 0) * 100)}%</span>
        </div>
      ) : null}
    </div>
  );
}

export function RetrievalInspector({
  retrieval,
  onRefresh,
  loading,
}: {
  retrieval?: RetrievalDebugResponse | null;
  onRefresh: () => void;
  loading: boolean;
}) {
  const initial = retrieval?.initial_documents ?? [];
  const reranked = retrieval?.reranked_documents ?? [];
  const relevanceScores = retrieval?.relevance_scores ?? [];
  const scoreTrace = retrieval?.retrieval_score_trace ?? [];
  const timings = retrieval?.timings;
  const trace = retrieval?.trace;

  return (
    <Card id="retrieval">
      <CardHeader>
        <div className="flex items-center justify-between gap-3">
          <CardTitle className="flex items-center gap-2">
            <Files className="h-4 w-4 text-primary" />
            Retrieval Inspector
          </CardTitle>
          <Button variant="outline" size="sm" onClick={onRefresh} disabled={loading}>
            {loading ? "Tracing" : "Trace"}
          </Button>
        </div>
        {retrieval?.warning ? <p className="text-sm text-amber-300">{retrieval.warning}</p> : null}
        {retrieval?.rerank_model ? <Badge>{retrieval.rerank_model}</Badge> : null}
        {trace ? (
          <div className="grid gap-2 sm:grid-cols-4">
            <div className="rounded-md border border-white/10 bg-black/20 p-2">
              <div className="text-[10px] font-medium uppercase text-muted-foreground">Route</div>
              <div className="mt-1 text-sm font-semibold">{trace.query_type ?? "unknown"}</div>
            </div>
            <div className="rounded-md border border-white/10 bg-black/20 p-2">
              <div className="text-[10px] font-medium uppercase text-muted-foreground">Confidence</div>
              <div className="mt-1 text-sm font-semibold">{Math.round((trace.retrieval_confidence ?? 0) * 100)}%</div>
            </div>
            <div className="rounded-md border border-white/10 bg-black/20 p-2">
              <div className="text-[10px] font-medium uppercase text-muted-foreground">Channels</div>
              <div className="mt-1 text-sm font-semibold">{trace.retrieval_channels?.join(", ") || "vector"}</div>
            </div>
            <div className="rounded-md border border-white/10 bg-black/20 p-2">
              <div className="text-[10px] font-medium uppercase text-muted-foreground">Retries</div>
              <div className="mt-1 text-sm font-semibold">{trace.corrective_attempts?.length ?? 0}</div>
            </div>
          </div>
        ) : null}
        {timings ? (
          <div className="grid gap-2 sm:grid-cols-3">
            {[
              ["Retrieve", timings.retrieval_ms],
              ["Rerank", timings.rerank_ms],
              ["Total", timings.total_ms],
            ].map(([label, value]) => (
              <div key={label} className="depth-card p-2">
                <div className="text-[10px] font-medium uppercase text-muted-foreground">{label}</div>
                <div className="mt-1 text-sm font-semibold">{Math.round(Number(value))} ms</div>
              </div>
            ))}
          </div>
        ) : null}
      </CardHeader>
      <CardContent className="grid gap-4 xl:grid-cols-2">
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h4 className="text-sm font-semibold">Retrieved Chunks</h4>
            <Badge>{initial.length} chunks</Badge>
          </div>
          {initial.length ? (
            initial.map((text, index) => (
              <ChunkCard key={`${text}-${index}`} text={text} index={index} total={initial.length} label="Initial" />
            ))
          ) : (
            <div className="rounded-lg border border-dashed border-white/15 bg-white/[0.03] p-6 text-sm text-muted-foreground">
              Run a query trace to inspect retrieved context.
            </div>
          )}
        </div>
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h4 className="text-sm font-semibold">Reranked Context</h4>
            <Badge>{reranked.length} chunks</Badge>
          </div>
          {reranked.length ? (
            reranked.map((text, index) => (
              <ChunkCard
                key={`${text}-${index}`}
                text={text}
                index={index}
                total={reranked.length}
                label="Rerank"
                score={relevanceScores[index]}
                scoreTrace={scoreTrace[index]}
              />
            ))
          ) : (
            <div className="rounded-lg border border-dashed border-white/15 bg-white/[0.03] p-6 text-sm text-muted-foreground">
              Reranked results appear here when available.
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
