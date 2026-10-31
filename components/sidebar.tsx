"use client";

import { useEffect, useState } from "react";
import { Activity, BarChart3, Database, History, Layers3, MessageSquareText, ShieldCheck } from "lucide-react";
import { cn } from "@/lib/utils";

const nav = [
  { href: "#chat", label: "Query", icon: MessageSquareText },
  { href: "#retrieval", label: "Context trace", icon: Database },
  { href: "#evaluation", label: "Answer quality", icon: ShieldCheck },
  { href: "#status", label: "Runtime", icon: BarChart3 },
  { href: "#logs", label: "Activity", icon: History },
];

export function Sidebar() {
  const [activeSection, setActiveSection] = useState("chat");

  useEffect(() => {
    const sections = nav
      .map((item) => document.querySelector<HTMLElement>(item.href))
      .filter((section): section is HTMLElement => section !== null);
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((left, right) => right.intersectionRatio - left.intersectionRatio)[0];
        if (visible) setActiveSection(visible.target.id);
      },
      { rootMargin: "-18% 0px -68% 0px", threshold: [0, 0.1, 0.35] },
    );
    sections.forEach((section) => observer.observe(section));
    return () => observer.disconnect();
  }, []);

  return (
    <aside className="glass-sidebar z-40 w-full shrink-0 border-b px-4 py-3 lg:sticky lg:top-0 lg:flex lg:h-dvh lg:w-72 lg:flex-col lg:border-b-0 lg:border-r lg:px-4 lg:py-5">
      <div className="sidebar-brand flex items-center gap-3 px-1 py-1">
        <div className="brand-mark flex h-11 w-11 shrink-0 items-center justify-center rounded-xl">
          <Layers3 aria-hidden="true" className="h-5 w-5" />
        </div>
        <div className="min-w-0">
          <div className="text-sm font-semibold tracking-wide text-foreground">Adaptive RAG</div>
          <div className="mt-0.5 text-xs text-muted-foreground">Knowledge console</div>
        </div>
      </div>

      <p className="section-kicker mb-2 mt-8 hidden px-3 lg:block">Workspace</p>
      <nav aria-label="Dashboard sections" className="mt-3 flex gap-1.5 overflow-x-auto pb-1 lg:mt-0 lg:block lg:space-y-1 lg:overflow-visible lg:pb-0">
        {nav.map((item) => (
          <a
            key={item.href}
            href={item.href}
            aria-current={activeSection === item.href.slice(1) ? "location" : undefined}
            onClick={() => setActiveSection(item.href.slice(1))}
            className={cn(
              "sidebar-link group flex min-h-11 shrink-0 cursor-pointer items-center gap-2.5 rounded-xl border border-transparent px-3 text-sm text-muted-foreground transition-colors duration-200 hover:bg-white/[0.045] hover:text-foreground lg:mb-1 lg:gap-3",
              activeSection === item.href.slice(1) && "sidebar-link-active text-foreground",
            )}
          >
            <item.icon aria-hidden="true" className="h-4 w-4 shrink-0 transition-colors group-hover:text-primary" />
            {item.label}
          </a>
        ))}
      </nav>

      <div className="sidebar-foot mt-auto hidden rounded-xl border border-white/[0.1] bg-black/15 p-4 lg:block">
        <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
          <Activity aria-hidden="true" className="h-3.5 w-3.5 text-primary" />
          Retrieval workspace
        </div>
        <p className="mt-2 text-xs leading-5 text-muted-foreground">
          Local BM25 search, Groq generation, and answer grounding in one place.
        </p>
      </div>
    </aside>
  );
}
