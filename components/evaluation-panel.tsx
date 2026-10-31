import { Activity, AlertTriangle, CheckCircle2, Database, Radar, ShieldCheck, Target } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import type { EvaluationPayload } from "@/types/api";

function percent(value?: number | null) {
  return Math.round((value ?? 0) * 100);
}

export function EvaluationPanel({ evaluation, loading }: { evaluation?: EvaluationPayload | null; loading: boolean }) {
  const unavailable = evaluation?.status === "warning" || !evaluation;
  const grounding = percent(evaluation?.grounding ?? evaluation?.grounding_score);
  const metrics = [
    { label: "Faithfulness", value: evaluation?.faithfulness, icon: ShieldCheck },
    { label: "Relevance", value: evaluation?.relevance, icon: Target },
    { label: "Context precision", value: evaluation?.context_precision, icon: Database },
    { label: "Context recall", value: evaluation?.context_recall, icon: Radar },
    { label: "Diversity", value: evaluation?.retrieval_diversity_score, icon: Activity },
  ];
  const risk = evaluation?.hallucination_risk ?? "unknown";
  const grounded = Boolean(evaluation?.grounded);

  return (
    <Card id="evaluation">
      <CardHeader className="flex flex-row items-start justify-between gap-4 pb-4 space-y-0">
        <div>
          <p className="section-kicker">Response signals</p>
          <CardTitle className="mt-1 text-lg">Answer quality</CardTitle>
        </div>
        <Badge className={unavailable ? "gap-2 text-warning" : grounded ? "gap-2 text-success" : "gap-2 text-warning"}>
          {unavailable ? <AlertTriangle aria-hidden="true" className="h-3.5 w-3.5" /> : grounded ? <CheckCircle2 aria-hidden="true" className="h-3.5 w-3.5" /> : <AlertTriangle aria-hidden="true" className="h-3.5 w-3.5" />}
          {loading ? "Evaluating" : `Risk: ${risk}`}
        </Badge>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="quality-lead depth-card p-4 md:p-5">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <p className="metric-label">Grounding score</p>
              <p className="mt-2 font-mono text-4xl font-medium tabular-nums text-foreground">
                {unavailable ? "--" : `${grounding}%`}
              </p>
            </div>
            <div className="w-full max-w-[15rem] pb-1">
              <Progress value={unavailable ? 0 : grounding} className="h-1.5" />
              <p className="mt-2 text-xs leading-5 text-muted-foreground">Lexical overlap with retrieved passages</p>
            </div>
          </div>
        </div>

        <div className="space-y-2">
          {metrics.map((metric) => {
            const score = percent(metric.value);
            const Icon = metric.icon;
            return (
              <div key={metric.label} className="quality-row">
                <Icon aria-hidden="true" className="h-4 w-4 shrink-0 text-accent" />
                <span className="min-w-0 flex-1 text-sm text-muted-foreground">{metric.label}</span>
                <span className="w-11 text-right font-mono text-xs tabular-nums text-foreground">
                  {unavailable ? "--" : `${score}%`}
                </span>
                <Progress value={unavailable ? 0 : score} className="hidden w-20 sm:block" />
              </div>
            );
          })}
        </div>

        <div className="evaluation-note">
          <div className="flex items-center gap-2 text-sm font-medium">
            {unavailable || !grounded ? (
              <AlertTriangle aria-hidden="true" className="h-4 w-4 text-warning" />
            ) : (
              <CheckCircle2 aria-hidden="true" className="h-4 w-4 text-success" />
            )}
            Grounding notes
          </div>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">
            {unavailable
              ? evaluation?.message || "Run a query to score its answer against the retrieved context."
              : evaluation?.summary || evaluation?.explanation || "No evaluation summary was returned."}
          </p>
          {evaluation?.unsupported_sentences?.length ? (
            <div className="mt-3 space-y-2">
              {evaluation.unsupported_sentences.map((sentence) => (
                <div key={sentence} className="rounded-lg border border-warning/25 bg-warning/[0.08] p-3 text-sm leading-6 text-warning">
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
