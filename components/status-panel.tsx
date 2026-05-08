import { Activity, BrainCircuit, Cpu, Database, Server } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { StatusResponse } from "@/types/api";

export function StatusPanel({ status, loading }: { status?: StatusResponse | null; loading: boolean }) {
  const items = [
    {
      label: "Ollama",
      value: status?.ollama_running ? "Running" : "Offline",
      icon: Cpu,
      active: Boolean(status?.ollama_running),
    },
    {
      label: "Vector DB",
      value: status?.vector_db_exists ? "Ready" : "Missing",
      icon: Database,
      active: Boolean(status?.vector_db_exists),
    },
    {
      label: "Indexed",
      value: String(status?.indexed_documents ?? 0),
      icon: Activity,
      active: Boolean((status?.indexed_documents ?? 0) > 0),
    },
    {
      label: "Runtime",
      value: status?.status ?? "checking",
      icon: Server,
      active: status?.status === "running",
    },
  ];

  return (
    <Card id="status">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between gap-3">
          <CardTitle className="flex items-center gap-2">
            <BrainCircuit className="h-4 w-4 text-primary" />
            System Status
          </CardTitle>
          <Badge>{loading ? "Polling" : "Live"}</Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {items.map((item) => (
            <div key={item.label} className="depth-card p-4">
              <div className="flex items-center justify-between">
                <span className="metric-label">{item.label}</span>
                <div className="flex items-center gap-2">
                  {item.active ? <span className="status-dot" /> : null}
                  <item.icon className={item.active ? "h-4 w-4 text-primary" : "h-4 w-4 text-muted-foreground"} />
                </div>
              </div>
              <div className="mt-3 text-lg font-semibold">{item.value}</div>
            </div>
          ))}
        </div>
        <div className="grid gap-3 text-sm md:grid-cols-2 xl:grid-cols-4">
          <div className="depth-card p-3">
            <div className="metric-label">Generation Model</div>
            <div className="mt-2 break-words font-mono text-primary">{status?.generation_model ?? "unknown"}</div>
          </div>
          <div className="depth-card p-3">
            <div className="metric-label">Rerank Model</div>
            <div className="mt-2 break-words font-mono text-fuchsia-200">{status?.rerank_model ?? "unknown"}</div>
          </div>
          <div className="depth-card p-3">
            <div className="metric-label">Evaluator Model</div>
            <div className="mt-2 break-words font-mono text-amber-200">{status?.evaluator_model ?? "unknown"}</div>
          </div>
          <div className="depth-card p-3">
            <div className="metric-label">Embedding Model</div>
            <div className="mt-2 break-words font-mono text-sky-300">{status?.embedding_model ?? "unknown"}</div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
