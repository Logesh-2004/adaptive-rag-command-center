import { BarChart3, BrainCircuit, DatabaseZap, History, MessageSquareText, ShieldCheck } from "lucide-react";
import { cn } from "@/lib/utils";

const nav = [
  { href: "#chat", label: "Chat", icon: MessageSquareText },
  { href: "#retrieval", label: "Retrieval", icon: DatabaseZap },
  { href: "#evaluation", label: "Evaluation", icon: ShieldCheck },
  { href: "#status", label: "Status", icon: BarChart3 },
  { href: "#logs", label: "Logs", icon: History },
];

export function Sidebar() {
  return (
    <aside className="hidden w-72 shrink-0 border-r border-white/10 bg-black/25 px-4 py-5 backdrop-blur-2xl lg:block">
      <div className="depth-card flex items-center gap-3 p-3">
        <div className="flex h-11 w-11 items-center justify-center rounded-lg border border-primary/30 bg-primary/15 shadow-[0_0_32px_rgba(45,212,191,0.18)]">
          <BrainCircuit className="h-5 w-5 text-primary" />
        </div>
        <div>
          <div className="text-sm font-semibold">Adaptive RAG</div>
          <div className="text-xs text-muted-foreground">AI Observability</div>
        </div>
      </div>
      <nav className="mt-8 space-y-1">
        {nav.map((item, index) => (
          <a
            key={item.href}
            href={item.href}
            className={cn(
              "group flex items-center gap-3 rounded-md border border-transparent px-3 py-2.5 text-sm text-muted-foreground transition-all duration-200 hover:translate-x-1 hover:border-primary/20 hover:bg-white/[0.08] hover:text-foreground",
              index === 0 && "border-primary/20 bg-primary/[0.08] text-foreground shadow-[0_0_28px_rgba(45,212,191,0.08)]",
            )}
          >
            <item.icon className="h-4 w-4 transition-colors group-hover:text-primary" />
            {item.label}
          </a>
        ))}
      </nav>
      <div className="absolute bottom-5 left-4 right-4 rounded-lg border border-white/10 bg-white/[0.04] p-3">
        <div className="flex items-center gap-2 text-xs font-medium text-primary">
          <span className="status-dot" />
          Control plane synced
        </div>
        <div className="mt-2 text-xs leading-5 text-muted-foreground">Hybrid retrieval, reranking, and evaluation telemetry online.</div>
      </div>
    </aside>
  );
}
