import { Bot, DatabaseZap, Filter, GitBranch, Radar, ShieldCheck, Sparkles } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

const stages = [
  { label: "Query", icon: Sparkles },
  { label: "Hybrid Retrieval", icon: DatabaseZap },
  { label: "Semantic Filter", icon: Filter },
  { label: "Reranker", icon: Radar },
  { label: "Generator", icon: Bot },
  { label: "Evaluator", icon: ShieldCheck },
  { label: "Grounded Answer", icon: GitBranch },
];

export function PipelineVisualizer({ active }: { active?: boolean }) {
  return (
    <Card>
      <CardHeader className="pb-4">
        <CardTitle className="flex items-center gap-2">
          <GitBranch className="h-4 w-4 text-primary" />
          Retrieval Pipeline
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid gap-3 lg:grid-cols-7">
          {stages.map((stage, index) => (
            <div key={stage.label} className="relative">
              <div
                className={cn(
                  "depth-card flex min-h-24 flex-col items-center justify-center gap-2 p-3 text-center",
                  active && index < 5 && "border-primary/30 bg-primary/[0.055]",
                )}
              >
                <div className="flex h-10 w-10 items-center justify-center rounded-lg border border-primary/25 bg-primary/10 shadow-[0_0_26px_rgba(45,212,191,0.13)]">
                  <stage.icon className="h-4 w-4 text-primary" />
                </div>
                <div className="text-xs font-semibold">{stage.label}</div>
              </div>
              {index < stages.length - 1 ? (
                <div className="glow-line absolute left-[calc(100%+2px)] top-1/2 hidden h-px w-8 -translate-y-1/2 lg:block" />
              ) : null}
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
