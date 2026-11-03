import { Activity, Database, DatabaseZap, Server } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { StatusResponse } from "@/types/api";

export function StatusPanel({
  status,
  loading,
  rebuilding,
  onRebuild,
}: {
  status?: StatusResponse | null;
  loading: boolean;
  rebuilding: boolean;
  onRebuild: () => void;
}) {
  const items = [
    {
      label: "Generation",
      value: status?.generation_provider_configured ? "Groq connected" : "API key required",
      detail: status?.generation_model ?? "Waiting for model status",
      icon: Server,
      active: Boolean(status?.generation_provider_configured),
    },
    {
      label: "Retrieval",
      value: status?.lexical_index_exists ? "BM25 index ready" : "Index not built",
      detail: status?.retrieval_strategy ?? "Local lexical search",
      icon: Activity,
      active: Boolean(status?.lexical_index_exists),
    },
    {
      label: "Corpus",
      value: `${(status?.indexed_chunks ?? 0).toLocaleString()} chunks`,
      detail: "Passages available locally",
      icon: Database,
      active: Boolean((status?.indexed_chunks ?? 0) > 0),
    },
  ];

  const configured = Boolean(status?.generation_provider_configured && status?.lexical_index_exists);

  return (
    <Card id="status" className="runtime-panel">
      <CardHeader className="flex flex-row items-center justify-between gap-4 pb-4 space-y-0">
        <div>
          <p className="section-kicker">System health</p>
          <CardTitle className="mt-1">Runtime</CardTitle>
        </div>
        <div className="flex flex-wrap items-center justify-end gap-2">
          <Button variant="outline" size="sm" onClick={onRebuild} disabled={rebuilding || !status}>
            <DatabaseZap aria-hidden="true" className={rebuilding ? "h-4 w-4 animate-pulse" : "h-4 w-4"} />
            {rebuilding ? "Rebuilding" : "Rebuild index"}
          </Button>
          <Badge className={configured ? "gap-2 text-success" : "gap-2 text-warning"}>
            <span className={configured ? "status-dot" : "h-2 w-2 rounded-full bg-warning"} aria-hidden="true" />
            {loading ? "Checking" : configured ? "Configured" : status ? "Action needed" : "Waiting"}
          </Badge>
        </div>
      </CardHeader>
      <CardContent>
        <div className="grid gap-3 sm:grid-cols-3">
          {items.map((item) => (
            <div key={item.label} className="runtime-tile depth-card flex min-w-0 items-start justify-between gap-3 p-4 md:p-5">
              <div className="min-w-0">
                <p className="metric-label">{item.label}</p>
                <p className="mt-3 text-base font-semibold leading-6 text-foreground md:text-lg">{item.value}</p>
                <p className="mt-1 break-words text-xs leading-5 text-muted-foreground">{item.detail}</p>
              </div>
              <span className={item.active ? "runtime-icon text-primary" : "runtime-icon text-muted-foreground"}>
                <item.icon aria-hidden="true" className="h-4 w-4" />
              </span>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
