import { Cpu, Database, FileSearch, Layers2, MessageSquareText, ShieldCheck } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const stages = [
  { label: "Question", detail: "Your prompt", icon: MessageSquareText },
  { label: "Retrieve", detail: "Local BM25", icon: Database },
  { label: "Rank", detail: "Best passages", icon: FileSearch },
  { label: "Compress", detail: "Focused context", icon: Layers2 },
  { label: "Generate", detail: "Groq response", icon: Cpu },
  { label: "Ground", detail: "Lexical checks", icon: ShieldCheck },
];

export function PipelineVisualizer({ active }: { active?: boolean }) {
  return (
    <Card className={active ? "pipeline-active" : undefined}>
      <CardHeader className="flex flex-row items-center justify-between gap-4 pb-4 space-y-0">
        <div>
          <p className="section-kicker">Request path</p>
          <CardTitle className="mt-1">From question to checked answer</CardTitle>
        </div>
        <Badge className={active ? "text-primary" : "text-muted-foreground"}>{active ? "In progress" : "6 stages"}</Badge>
      </CardHeader>
      <CardContent>
        <ol className="pipeline-track" aria-label="RAG request stages">
          {stages.map((stage) => (
            <li key={stage.label} className="pipeline-step flex flex-col items-start">
              <span className="pipeline-node text-primary">
                <stage.icon aria-hidden="true" className="h-4 w-4" />
              </span>
              <span className="mt-2 text-sm font-semibold leading-5 text-foreground">{stage.label}</span>
              <span className="text-xs leading-5 text-muted-foreground">{stage.detail}</span>
            </li>
          ))}
        </ol>
      </CardContent>
    </Card>
  );
}
