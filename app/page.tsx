"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { ArrowRight, DatabaseZap, SlidersHorizontal } from "lucide-react";
import { ragApi } from "@/lib/api";
import type { ActivityEvent, ImprovementResponse, QueryResponse, RetrievalDebugResponse, StatusResponse } from "@/types/api";
import { UNIVERSES, type FlightPhase } from "@/components/wormhole/flight-path";
import { AnswerPanel, DetailsGrid, Hud, glass, type ShipStat, type Telemetry } from "@/components/wormhole/relay-panels";

const WormholeScene = dynamic(() => import("@/components/wormhole/wormhole-scene").then((module) => module.WormholeScene), {
  ssr: false,
  loading: () => null,
});

const QUICK_STARTS = ["How do I diagnose an EV battery fault?", "What is adaptive RAG?", "What is HyDE?"];

const headerButton =
  "inline-flex min-h-9 items-center gap-2 rounded-lg border border-white/15 bg-black/20 px-3 font-mono text-[11px] uppercase tracking-[0.16em] text-slate-200 backdrop-blur transition-colors hover:border-white/35 hover:text-white disabled:cursor-wait disabled:opacity-60";

const ADMIN_TOKEN_KEY = "rag-admin-token";

/** Remembers the admin token for this browser tab only, so a public visitor's tab never holds it. */
const adminTokenStore = {
  read: () => {
    try {
      return sessionStorage.getItem(ADMIN_TOKEN_KEY);
    } catch {
      return null;
    }
  },
  write: (token: string | null) => {
    try {
      if (token) sessionStorage.setItem(ADMIN_TOKEN_KEY, token);
      else sessionStorage.removeItem(ADMIN_TOKEN_KEY);
    } catch {
      // Storage can be unavailable (private windows); the token is then asked for each time.
    }
  },
};

function supportsWebGL() {
  try {
    const canvas = document.createElement("canvas");
    return Boolean(canvas.getContext("webgl2") || canvas.getContext("webgl"));
  } catch {
    return false;
  }
}

function TitleCard({ kicker, title, subtitle, wide }: { kicker: string; title: string; subtitle: string; wide: boolean }) {
  return (
    <div role="status" aria-live="polite" className={`pointer-events-none absolute inset-x-0 z-30 flex justify-center px-6 ${wide ? "top-[18%]" : "top-6"}`}>
      <div className="universe-title text-center">
        <p className="font-mono text-xs uppercase tracking-[0.5em] text-slate-300">{kicker}</p>
        <p className="mt-3 text-4xl font-extralight tracking-tight text-white md:text-7xl">{title}</p>
        <p className="mt-3 font-mono text-xs uppercase tracking-[0.3em] text-slate-400">{subtitle}</p>
      </div>
    </div>
  );
}

function clock() {
  return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export default function RelayPage() {
  const [query, setQuery] = useState(QUICK_STARTS[0]);
  const [inputError, setInputError] = useState(false);
  const [phase, setPhase] = useState<FlightPhase>("idle");
  const [stage, setStage] = useState(0);
  const [passed, setPassed] = useState(0);
  const [retry, setRetry] = useState(false);
  const [looping, setLooping] = useState(false);
  const [telemetry, setTelemetry] = useState<Telemetry>({});
  const [response, setResponse] = useState<QueryResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [events, setEvents] = useState<ActivityEvent[]>([]);
  const [trace, setTrace] = useState<RetrievalDebugResponse | null>(null);
  const [improvement, setImprovement] = useState<ImprovementResponse | null>(null);
  const [busy, setBusy] = useState({ ingest: false, improve: false, trace: false });
  const [webgl, setWebgl] = useState(true);
  const [reducedMotion, setReducedMotion] = useState(false);
  const [wide, setWide] = useState(true);
  const pending = useRef<QueryResponse | null>(null);
  const scene = useRef<HTMLDivElement>(null);

  const addEvent = useCallback((event: Omit<ActivityEvent, "id" | "time">) => {
    setEvents((current) => [{ ...event, id: crypto.randomUUID(), time: clock() }, ...current].slice(0, 12));
  }, []);

  const refreshStatus = useCallback(async () => {
    try {
      setStatus(await ragApi.status());
    } catch {
      setStatus(null);
    }
  }, []);

  useEffect(() => {
    setWebgl(supportsWebGL());
    const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
    const desktop = window.matchMedia("(min-width: 1024px)");
    const update = () => {
      setReducedMotion(motion.matches);
      // Stat call-outs need room beside the ship; narrow screens keep the scores in the answer panel.
      setWide(desktop.matches);
    };
    update();
    motion.addEventListener("change", update);
    desktop.addEventListener("change", update);
    void refreshStatus();
    return () => {
      motion.removeEventListener("change", update);
      desktop.removeEventListener("change", update);
    };
  }, [refreshStatus]);

  const land = useCallback(() => {
    if (!pending.current) return;
    const landed = pending.current;
    setResponse(landed);
    setLooping(false);
    setPhase("arrived");
    addEvent({
      type: landed.warning ? "warning" : "query",
      title: `Answer landed in ${(landed.timings.total_ms / 1000).toFixed(1)} s`,
      detail: landed.warning ?? `${landed.sources.length} passages · risk ${landed.hallucination_risk ?? "unknown"}`,
      severity: landed.warning ? "warning" : "success",
    });
  }, [addEvent]);

  async function launch(text: string) {
    const question = text.trim();
    if (!question) {
      setInputError(true);
      return;
    }
    if (phase === "travel" || phase === "landing") return;
    setQuery(question);
    setInputError(false);
    setError(null);
    setTelemetry({});
    setPassed(0);
    setRetry(false);
    setLooping(false);
    // Stage counts the pipeline steps that have started; retrieval starts with the launch.
    setStage(1);
    pending.current = null;
    setPhase("travel");
    // On stacked layouts the scene sits above the form: bring it into view to watch the flight.
    if (!wide) scene.current?.scrollIntoView({ behavior: reducedMotion ? "auto" : "smooth", block: "start" });
    let tokens = 0;

    try {
      await ragApi.streamQuery(question, (event) => {
        if (event.type === "retrieval") {
          setTelemetry((current) => ({ ...current, retrievalMs: event.timings?.retrieval_ms, matched: event.sources?.length }));
          setStage((current) => Math.max(current, 2));
        } else if (event.type === "rank") {
          setTelemetry((current) => ({ ...current, kept: event.sources?.length, confidence: event.trace?.retrieval_confidence }));
          // Ranking and compression both finish here; generation starts.
          setStage((current) => Math.max(current, 4));
        } else if (event.type === "token") {
          tokens += 1;
          setTelemetry((current) => ({ ...current, tokens, generationMs: event.timings?.generation_ms }));
        } else if (event.type === "done") {
          pending.current = event;
          setTelemetry((current) => ({ ...current, generationMs: event.timings.generation_ms }));
          setRetry(Boolean(event.trace?.corrective_attempts?.length));
          setStage(5);
          setPhase("landing");
          if (!webgl) land();
        } else if (event.type === "error") {
          throw new Error(event.message);
        }
      });
      if (!pending.current) throw new Error("The answer stream ended without a result.");
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : String(caught);
      setError(message);
      setPhase("error");
      addEvent({ type: "error", title: "Flight aborted", detail: message, severity: "error" });
    }
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void launch(query);
  }

  const submitFeedback = useCallback(
    async (rating: number, comment?: string) => {
      if (!response) return false;
      try {
        await ragApi.feedback(response.query, response.answer, rating, comment);
        addEvent({ type: "system", title: "Feedback saved", detail: `Rated ${rating}/5`, severity: "info" });
        return true;
      } catch (caught) {
        addEvent({ type: "error", title: "Feedback failed", detail: String(caught), severity: "error" });
        return false;
      }
    },
    [addEvent, response],
  );

  const rebuildIndex = useCallback(async () => {
    let token: string | undefined;
    if (status?.admin_required) {
      token = adminTokenStore.read() ?? window.prompt("Rebuilding the index is admin-only on this site. Enter the admin token:")?.trim() ?? undefined;
      if (!token) {
        addEvent({ type: "system", title: "Rebuild cancelled", detail: "Rebuilding the index needs the admin token.", severity: "info" });
        return;
      }
    }
    setBusy((current) => ({ ...current, ingest: true }));
    try {
      const result = await ragApi.ingest(token);
      if (token) adminTokenStore.write(token);
      const warnings = result.warnings.length ? ` ${result.warnings.length} file warning(s): ${result.warnings.slice(0, 2).join(" ")}` : "";
      addEvent({
        type: result.warnings.length ? "warning" : "system",
        title: "Index rebuilt",
        detail: `${result.chunks_created.toLocaleString()} chunks from ${result.indexed_documents.toLocaleString()} documents.${warnings}`,
        severity: result.warnings.length ? "warning" : "success",
      });
      await refreshStatus();
    } catch (caught) {
      // A wrong token should be asked for again next time, not reused.
      if (token) adminTokenStore.write(null);
      addEvent({ type: "error", title: "Index rebuild failed", detail: String(caught), severity: "error" });
    } finally {
      setBusy((current) => ({ ...current, ingest: false }));
    }
  }, [addEvent, refreshStatus, status?.admin_required]);

  const reviewTuning = useCallback(async () => {
    setBusy((current) => ({ ...current, improve: true }));
    try {
      const result = await ragApi.improve();
      setImprovement(result);
      addEvent({ type: "evaluation", title: "Tuning review complete", detail: `${result.weak_records} weak records`, severity: result.weak_records ? "warning" : "success" });
      document.getElementById("tuning")?.scrollIntoView({ behavior: reducedMotion ? "auto" : "smooth", block: "center" });
    } catch (caught) {
      addEvent({ type: "error", title: "Tuning review failed", detail: String(caught), severity: "error" });
    } finally {
      setBusy((current) => ({ ...current, improve: false }));
    }
  }, [addEvent, reducedMotion]);

  const runTrace = useCallback(async () => {
    if (!response) return;
    setBusy((current) => ({ ...current, trace: true }));
    try {
      const result = await ragApi.debugRetrieval(response.query);
      setTrace(result);
      addEvent({
        type: "retrieval",
        title: "Retrieval re-traced",
        detail: `${result.initial_documents.length} found, ${result.ranked_documents.length} kept`,
        severity: "success",
      });
    } catch (caught) {
      addEvent({ type: "error", title: "Trace failed", detail: String(caught), severity: "error" });
    } finally {
      setBusy((current) => ({ ...current, trace: false }));
    }
  }, [addEvent, response]);

  const flying = phase === "travel" || phase === "landing";
  const stats = useMemo<ShipStat[]>(() => {
    if (!response) return [];
    const evaluation = response.evaluation;
    const risk = String(response.hallucination_risk ?? evaluation?.hallucination_risk ?? "unknown");
    return [
      { key: "grounding", label: "Grounding", value: response.grounding_score ?? evaluation?.grounding_score ?? 0, kind: "percent", tone: "neutral" },
      { key: "faithfulness", label: "Faithfulness", value: evaluation?.faithfulness ?? 0, kind: "percent", tone: "neutral" },
      { key: "relevance", label: "Relevance", value: evaluation?.relevance ?? 0, kind: "percent", tone: "neutral" },
      { key: "risk", label: "Hallucination risk", value: 0, kind: "text", text: risk.toUpperCase(), tone: risk === "low" ? "good" : "warn" },
      { key: "sources", label: "Sources", value: response.sources.length, kind: "count", tone: "neutral" },
      { key: "roundtrip", label: "Round trip", value: response.timings.total_ms, kind: "seconds", tone: "neutral" },
    ];
  }, [response]);
  const ready = Boolean(status?.generation_provider_configured && status?.lexical_index_exists);
  const universe = flying && passed > 0 ? UNIVERSES[passed - 1] : null;
  const titleCards = (
    <>
      {universe ? (
        <>
          {reducedMotion ? null : <div key={`flash-${passed}`} aria-hidden="true" className="relay-flash pointer-events-none absolute inset-0 z-20 bg-white mix-blend-screen" />}
          {looping ? null : (
            <TitleCard key={`title-${passed}`} wide={wide} kicker={`Entering universe ${universe.numeral}`} title={universe.name} subtitle={`${universe.layer} · ${universe.tagline}`} />
          )}
        </>
      ) : null}
      {looping && flying ? <TitleCard key="retry" wide={wide} kicker="Corrective retry" title="Looping back" subtitle="Weak first pass · searching again with expanded terms" /> : null}
    </>
  );

  return (
    <main className="min-h-dvh bg-[#03040b] text-slate-100">
      <section aria-label="Query relay" className="relative isolate flex flex-col overflow-hidden lg:min-h-[100svh]">
        {/* Phones and tablets: the scene is its own block under the header. Desktop: it fills the hero behind the panels. */}
        <div ref={scene} className="relative order-2 h-[56svh] min-h-[340px] w-full scroll-mt-2 lg:absolute lg:inset-0 lg:order-none lg:-z-10 lg:h-auto">
          {webgl ? (
            <WormholeScene
              phase={phase}
              stage={stage}
              reducedMotion={reducedMotion}
              onArrived={land}
              onPassed={setPassed}
              retry={retry}
              onRetry={() => {
                setLooping(true);
                addEvent({ type: "evaluation", title: "Corrective retry", detail: "First pass was weak; re-searched with expanded terms.", severity: "info" });
              }}
              stats={stats}
              showStats={wide}
            />
          ) : (
            <div className="flex h-full w-full items-center justify-center bg-[radial-gradient(ellipse_at_60%_35%,rgba(124,92,255,0.35),transparent_60%),#03040b] p-6 text-center">
              <p className="max-w-sm text-sm text-slate-300">
                This browser can&apos;t show the 3D relay. Questions still work here, or use the{" "}
                <Link href="/classic" className="text-cyan-300 underline underline-offset-4">classic dashboard</Link>.
              </p>
            </div>
          )}
          {/* Phones and tablets: title cards sit over the scene block itself. */}
          {wide ? null : titleCards}
        </div>
        <div aria-hidden="true" className={`pointer-events-none absolute inset-y-0 left-0 -z-10 hidden bg-gradient-to-r from-[#03040b]/85 via-[#03040b]/30 to-transparent transition-opacity duration-700 lg:block lg:w-[55%] ${flying ? "opacity-0" : "opacity-100"}`} />
        {wide ? titleCards : null}

        <header className="order-1 flex flex-wrap items-center justify-between gap-3 px-5 py-5 md:px-10">
          <Link href="/" className="font-mono text-sm font-semibold uppercase tracking-[0.35em] text-white">Adaptive RAG</Link>
          <nav aria-label="Sections" className="hidden items-center gap-6 font-mono text-[11px] uppercase tracking-[0.22em] text-slate-400 xl:flex">
            <a href="#evidence" className="hover:text-white">Evidence</a>
            <a href="#quality" className="hover:text-white">Quality</a>
            <a href="#tuning" className="hover:text-white">Tuning</a>
            <a href="#activity" className="hover:text-white">Activity</a>
          </nav>
          <div className="flex flex-wrap items-center gap-2">
            <button type="button" onClick={rebuildIndex} disabled={busy.ingest || flying} className={headerButton}>
              <DatabaseZap aria-hidden="true" className={`h-3.5 w-3.5 ${busy.ingest ? "animate-pulse" : ""}`} />
              {busy.ingest ? "Rebuilding" : "Rebuild index"}
            </button>
            <button type="button" onClick={reviewTuning} disabled={busy.improve} className={headerButton}>
              <SlidersHorizontal aria-hidden="true" className={`h-3.5 w-3.5 ${busy.improve ? "animate-pulse" : ""}`} />
              {busy.improve ? "Reviewing" : "Review tuning"}
            </button>
            <span className={`rounded-full border px-3 py-1 font-mono text-[11px] uppercase tracking-[0.16em] ${ready ? "border-emerald-400/30 text-emerald-300" : "border-amber-400/30 text-amber-300"}`}>
              {status ? `${status.indexed_chunks.toLocaleString()} chunks · ${ready ? "online" : "setup needed"}` : "Connecting"}
            </span>
          </div>
        </header>

        <div className="order-3 flex flex-1 flex-col gap-6 px-5 py-6 md:px-10 lg:flex-row lg:items-end lg:justify-between lg:pt-0">
          <div className={`flex w-full flex-col justify-center gap-6 transition-opacity duration-700 lg:max-w-[480px] ${phase === "arrived" ? "lg:max-w-[380px] lg:self-end" : "lg:self-center"} ${flying ? "lg:opacity-25" : "opacity-100"}`}>
            <div className={phase === "arrived" ? "lg:hidden" : undefined}>
              <p className="font-mono text-[11px] uppercase tracking-[0.3em] text-slate-400">Retrieval · augmented · relay</p>
              <h1 className="mt-4 text-4xl leading-[1.02] tracking-tight text-white md:text-6xl">
                <span className="block font-bold">Ask once.</span>
                <span className="block font-light">Watch it travel.</span>
              </h1>
              <p className="mt-4 max-w-md text-[15px] leading-7 text-slate-300">
                Your question flies through five layers of your local corpus — retrieve, rank, compress, generate, ground — and lands with its evidence.
              </p>
            </div>

            <form onSubmit={submit} className={`${glass} flex flex-col gap-3 p-4`}>
              <label htmlFor="relay-query" className="text-sm font-medium text-white">Your question</label>
              <textarea
                id="relay-query"
                value={query}
                onChange={(event) => {
                  setQuery(event.target.value);
                  setInputError(false);
                }}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    void launch(query);
                  }
                }}
                rows={2}
                placeholder="How do I diagnose an EV battery fault?"
                aria-invalid={inputError}
                aria-describedby={inputError ? "relay-query-error" : undefined}
                className="min-h-[72px] resize-y rounded-xl border border-white/15 bg-black/35 px-3.5 py-3 text-[15px] leading-6 text-white placeholder:text-slate-500"
              />
              {inputError ? <p id="relay-query-error" className="text-sm text-rose-300">Enter a question first.</p> : null}
              <div className="flex flex-wrap items-center gap-3">
                <button
                  type="submit"
                  disabled={flying}
                  className="flex min-h-12 items-center gap-2 rounded-lg bg-white px-5 font-mono text-xs font-semibold uppercase tracking-[0.2em] text-slate-900 transition-transform hover:-translate-y-0.5 disabled:cursor-wait disabled:opacity-70"
                >
                  {flying ? "In flight" : phase === "arrived" ? "Launch again" : "Send query"}
                  <ArrowRight aria-hidden="true" className="h-4 w-4" />
                </button>
                <span className="hidden font-mono text-[11px] uppercase tracking-[0.18em] text-slate-400 sm:inline">Enter to launch</span>
              </div>
              <div className="flex flex-wrap gap-2">
                {QUICK_STARTS.slice(1).map((prompt) => (
                  <button
                    key={prompt}
                    type="button"
                    disabled={flying}
                    onClick={() => void launch(prompt)}
                    className="min-h-9 rounded-full border border-white/15 px-3 text-xs text-slate-300 hover:border-white/35 hover:text-white disabled:opacity-50"
                  >
                    {prompt}
                  </button>
                ))}
              </div>
            </form>
          </div>

          <div className="flex w-full flex-col items-stretch gap-4 lg:max-w-[540px] lg:items-end">
            {phase === "arrived" && response ? (
              <AnswerPanel response={response} onFeedback={submitFeedback} showMetrics={!wide} />
            ) : (
              <Hud phase={phase} passed={passed} telemetry={telemetry} error={error} />
            )}
          </div>
        </div>
      </section>

      <div className="pt-6 lg:pt-10">
        <DetailsGrid
          response={response}
          events={events}
          trace={trace}
          tracing={busy.trace}
          onTrace={runTrace}
          improvement={improvement}
          improving={busy.improve}
          onImprove={reviewTuning}
        />
        <p className="pb-10 text-center text-xs text-slate-500">
          Prefer the flat view? <Link href="/classic" className="text-slate-300 underline underline-offset-4 hover:text-white">Open the classic dashboard</Link>.
        </p>
      </div>
    </main>
  );
}
