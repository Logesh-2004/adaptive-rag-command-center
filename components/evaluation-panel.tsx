import { AlertTriangle, Database, Network, Radar, ShieldCheck, Sparkles, Target, Waves } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import type { EvaluationPayload } from "@/types/api";

function percent(value?: number | null) {
  return Math.round((value ?? 0) * 100);
}

export function EvaluationPanel({ evaluation, loading }: { evaluation?: EvaluationPayload | null; loading: boolean }) {
  const faithfulness = percent(evaluation?.faithfulness);
  const relevance = percent(evaluation?.relevance);
  const grounding = percent(evaluation?.grounding ?? evaluation?.grounding_score);
  const precision = percent(evaluation?.context_precision);
  const recall = percent(evaluation?.context_recall);
  const diversity = percent(evaluation?.retrieval_diversity_score);
  const unavailable = evaluation?.status === "warning" || !evaluation;
  const hallucinationWarning = unavailable || !evaluation?.grounded;
  const risk = evaluation?.hallucination_risk ?? "unknown";

  return (
    <Card id="evaluation">
      <CardHeader>
        <div className="flex items-center justify-between gap-3">
          <CardTitle className="flex items-center gap-2">
            <ShieldCheck className="h-4 w-4 text-primary" />
            Evaluation Panel
          </CardTitle>
          <Badge className={hallucinationWarning ? "text-amber-300" : "text-primary"}>
            {loading ? "Scoring" : `Risk: ${risk}`}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-3 xl:grid-cols-6">
          <div className="depth-card p-4">
            <div className="flex items-center justify-between">
              <span className="metric-label">Faithfulness</span>
              <ShieldCheck className="h-4 w-4 text-primary" />
            </div>
            <div className="mt-3 text-2xl font-semibold">{unavailable ? "--" : `${faithfulness}%`}</div>
            <Progress value={unavailable ? 0 : faithfulness} className="mt-3" />
          </div>
          <div className="depth-card p-4">
            <div className="flex items-center justify-between">
              <span className="metric-label">Relevance</span>
              <Target className="h-4 w-4 text-sky-300" />
            </div>
            <div className="mt-3 text-2xl font-semibold">{unavailable ? "--" : `${relevance}%`}</div>
            <Progress value={unavailable ? 0 : relevance} className="mt-3" />
          </div>
          <div className="depth-card p-4">
            <div className="flex items-center justify-between">
              <span className="metric-label">Grounding</span>
              <Waves className={evaluation?.grounded ? "h-4 w-4 text-primary" : "h-4 w-4 text-amber-300"} />
            </div>
            <div className="mt-3 text-2xl font-semibold">{unavailable ? "--" : `${grounding}%`}</div>
            <Progress value={unavailable ? 0 : grounding} className="mt-3" />
          </div>
          <div className="depth-card p-4">
            <div className="flex items-center justify-between">
            <span className="metric-label">Context Precision</span>
              <Database className="h-4 w-4 text-cyan-300" />
            </div>
            <div className="mt-3 text-2xl font-semibold">{unavailable ? "--" : `${precision}%`}</div>
            <Progress value={unavailable ? 0 : precision} className="mt-3" />
          </div>
          <div className="depth-card p-4">
            <div className="flex items-center justify-between">
            <span className="metric-label">Context Recall</span>
              <Radar className="h-4 w-4 text-fuchsia-200" />
            </div>
            <div className="mt-3 text-2xl font-semibold">{unavailable ? "--" : `${recall}%`}</div>
            <Progress value={unavailable ? 0 : recall} className="mt-3" />
          </div>
          <div className="depth-card p-4">
            <div className="flex items-center justify-between">
            <span className="metric-label">Diversity</span>
              <Network className="h-4 w-4 text-indigo-200" />
            </div>
            <div className="mt-3 text-2xl font-semibold">{unavailable ? "--" : `${diversity}%`}</div>
            <Progress value={unavailable ? 0 : diversity} className="mt-3" />
          </div>
        </div>
        <div className="depth-card p-4">
          <div className="flex items-center gap-2 text-sm font-medium">
            {hallucinationWarning ? (
              <AlertTriangle className="h-4 w-4 text-amber-300" />
            ) : (
              <Sparkles className="h-4 w-4 text-primary" />
            )}
            Heuristic Evaluation
          </div>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">
            {unavailable
              ? evaluation?.message || "Evaluation has not run yet."
              : evaluation?.summary || evaluation?.explanation || "No judge summary returned."}
          </p>
          {evaluation?.unsupported_sentences?.length ? (
            <div className="mt-3 space-y-2">
              {evaluation.unsupported_sentences.map((sentence) => (
                <div key={sentence} className="rounded-md border border-amber-300/20 bg-amber-300/10 p-2 text-sm text-amber-100">
                  {sentence}
                </div>
              ))}
            </div>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}
