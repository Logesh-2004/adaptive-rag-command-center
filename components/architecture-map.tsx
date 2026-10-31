import { Database, FileSearch, Layers3, Monitor, Server, ShieldCheck } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const nodes = [
  { label: "Dashboard", detail: "Next.js client", icon: Monitor },
  { label: "API stream", detail: "FastAPI", icon: Server },
  { label: "Local index", detail: "BM25 passages", icon: Database },
  { label: "Context", detail: "Rank and compress", icon: Layers3 },
  { label: "Generation", detail: "Groq completion", icon: FileSearch },
  { label: "Grounding", detail: "Lexical checks", icon: ShieldCheck },
];

export function ArchitectureMap() {
  return (
    <Card>
      <CardHeader className="pb-4">
        <p className="section-kicker">System map</p>
        <CardTitle className="mt-1">Parts of one request</CardTitle>
      </CardHeader>
      <CardContent>
        <ol className="architecture-grid grid gap-3 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-6" aria-label="Application components">
          {nodes.map((node, index) => (
            <li key={node.label} className="architecture-node depth-card p-4">
              <div className="architecture-icon flex h-11 w-11 items-center justify-center rounded-xl border border-primary/20 bg-primary/[0.08] text-primary">
                <node.icon aria-hidden="true" className="h-4 w-4" />
              </div>
              <div className="architecture-copy mt-4 min-w-0">
                <p className="font-mono text-[11px] tracking-[0.12em] text-muted-foreground">0{index + 1}</p>
                <h3 className="mt-1 text-sm font-semibold text-foreground">{node.label}</h3>
                <p className="mt-1 text-xs leading-5 text-muted-foreground">{node.detail}</p>
              </div>
            </li>
          ))}
        </ol>
      </CardContent>
    </Card>
  );
}
