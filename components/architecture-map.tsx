import { Bot, Braces, Cpu, Database, Network, ScanSearch, ServerCog } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const nodes = [
  { label: "Frontend", detail: "React observability", icon: Braces },
  { label: "FastAPI", detail: "Streaming control plane", icon: ServerCog },
  { label: "Retrieval Engine", detail: "Hybrid router", icon: ScanSearch },
  { label: "Vector DB + BM25", detail: "Semantic and lexical", icon: Database },
  { label: "Cross Encoder", detail: "Precision rerank", icon: Network },
  { label: "Ollama LLM", detail: "llama3 generation", icon: Bot },
  { label: "Evaluator", detail: "Heuristic scoring", icon: Cpu },
];

export function ArchitectureMap() {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Network className="h-4 w-4 text-primary" />
          AI Architecture
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-7">
          {nodes.map((node, index) => (
            <div key={node.label} className="relative depth-card p-4">
              <div className="flex items-center gap-3">
                <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-white/10 bg-white/[0.08]">
                  <node.icon className="h-4 w-4 text-primary" />
                </div>
                <div className="min-w-0">
                  <div className="text-sm font-semibold">{node.label}</div>
                  <div className="truncate text-xs text-muted-foreground">{node.detail}</div>
                </div>
              </div>
              {index < nodes.length - 1 ? <div className="glow-line mt-4 h-px w-full" /> : null}
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
