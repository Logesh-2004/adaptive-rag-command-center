"use client";

import { Fragment, useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { CheckCircle2, ScanSearch, SlidersHorizontal, ThumbsDown, ThumbsUp } from "lucide-react";
import type { ActivityEvent, ImprovementResponse, QueryResponse, RetrievalDebugResponse } from "@/types/api";
import { UNIVERSES, type FlightPhase } from "./flight-path";

export const glass = "rounded-2xl border border-white/[0.12] bg-[rgba(14,18,40,0.55)] backdrop-blur-xl";

const percent = (value?: number | null) => (value == null ? "—" : `${Math.round(value * 100)}%`);
const ms = (value?: number | null) => (value == null ? "—" : value >= 1000 ? `${(value / 1000).toFixed(1)} s` : `${Math.round(value)} ms`);

/** Renders the model's light markdown (bold, numbered and bulleted lists) without injecting HTML. */
function inline(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, index) =>
    part.startsWith("**") && part.endsWith("**") ? <strong key={index} className="font-semibold text-white">{part.slice(2, -2)}</strong> : <Fragment key={index}>{part}</Fragment>,
  );
}

export function AnswerText({ text }: { text: string }) {
  const blocks: ReactNode[] = [];
  let list: { ordered: boolean; items: string[] } | null = null;
  const flush = () => {
    if (!list) return;
    const Tag = list.ordered ? "ol" : "ul";
    blocks.push(
      <Tag key={blocks.length} className={`${list.ordered ? "list-decimal" : "list-disc"} space-y-1 pl-5 marker:text-cyan-300/80`}>
        {list.items.map((item, index) => <li key={index}>{inline(item)}</li>)}
      </Tag>,
    );
    list = null;
  };
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    const ordered = line.match(/^\d+[.)]\s+(.*)$/);
    const bullet = line.match(/^[-*•]\s+(.*)$/);
    if (ordered || bullet) {
      const isOrdered = Boolean(ordered);
      if (list && list.ordered !== isOrdered) flush();
      list = list ?? { ordered: isOrdered, items: [] };
      list.items.push((ordered ?? bullet)![1]);
      continue;
    }
    flush();
    if (line) blocks.push(<p key={blocks.length}>{inline(line)}</p>);
  }
  flush();
  return <div className="space-y-3 text-[15px] leading-7 text-slate-200">{blocks}</div>;
}

function Metric({ label, value, bar, tone = "text-white" }: { label: string; value: string; bar?: number | null; tone?: string }) {
  return (
    <div className={`${glass} px-3 py-2.5`}>
      <div className="text-[11px] font-medium uppercase tracking-[0.14em] text-slate-400">{label}</div>
      <div className={`mt-0.5 font-mono text-lg ${tone}`}>{value}</div>
      {bar != null ? (
        <div className="mt-2 h-1 rounded-full bg-white/10" aria-hidden="true">
          <div className="h-full rounded-full bg-cyan-300" style={{ width: `${Math.round(bar * 100)}%` }} />
        </div>
      ) : null}
    </div>
  );
}

export type ShipStat = {
  key: string;
  label: string;
  value: number;
  kind: "percent" | "seconds" | "count" | "text";
  text?: string;
  tone: "good" | "warn" | "neutral";
};

function formatStat(stat: ShipStat, value: number) {
  if (stat.kind === "percent") return `${Math.round(value * 100)}%`;
  if (stat.kind === "seconds") return `${(value / 1000).toFixed(1)} s`;
  if (stat.kind === "count") return String(Math.round(value));
  return stat.text ?? "";
}

/** One holographic readout beside the landed ship; its number counts up as it appears. */
export function StatCard({ stat, index, align }: { stat: ShipStat; index: number; align: "left" | "right" }) {
  const [shown, setShown] = useState(stat.kind === "text" ? stat.value : 0);
  const frame = useRef(0);
  useEffect(() => {
    if (stat.kind === "text") return;
    const delay = 250 + index * 140;
    const duration = 900;
    let start = 0;
    const tick = (now: number) => {
      if (!start) start = now + delay;
      const t = Math.min(1, Math.max(0, (now - start) / duration));
      setShown(stat.value * (1 - Math.pow(1 - t, 3)));
      if (t < 1) frame.current = requestAnimationFrame(tick);
    };
    frame.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame.current);
  }, [stat.value, stat.kind, index]);

  const tone = stat.tone === "good" ? "text-emerald-300" : stat.tone === "warn" ? "text-amber-300" : "text-white";
  return (
    <div
      className="stat-callout"
      style={{ transform: `translate(${align === "right" ? "-100%" : "0"}, -50%)`, animationDelay: `${index * 140}ms` }}
    >
      <div className="rounded-lg border border-white/20 bg-[rgba(8,12,26,0.55)] px-3 py-2 backdrop-blur-md">
        <div className="whitespace-nowrap font-mono text-[10px] uppercase tracking-[0.22em] text-slate-300">{stat.label}</div>
        <div className={`whitespace-nowrap font-mono text-2xl font-light leading-tight ${tone}`}>{formatStat(stat, shown)}</div>
        {stat.kind === "percent" ? (
          <div className="mt-1 h-[3px] w-28 rounded-full bg-white/15" aria-hidden="true">
            <div className="h-full rounded-full bg-white/80" style={{ width: `${Math.round(shown * 100)}%` }} />
          </div>
        ) : null}
      </div>
    </div>
  );
}

export function AnswerPanel({
  response,
  onFeedback,
  showMetrics = true,
}: {
  response: QueryResponse;
  onFeedback: (rating: number, comment?: string) => Promise<boolean>;
  /** Off when the scores are already shown as call-outs around the landed ship. */
  showMetrics?: boolean;
}) {
  const evaluation = response.evaluation;
  const risk = response.hallucination_risk ?? evaluation?.hallucination_risk;
  const [rating, setRating] = useState<number | null>(null);
  const [state, setState] = useState<"idle" | "sending" | "sent">("idle");
  const [comment, setComment] = useState("");

  useEffect(() => {
    setRating(null);
    setState("idle");
    setComment("");
  }, [response.query, response.answer]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (rating == null || state === "sending") return;
    setState("sending");
    setState((await onFeedback(rating, comment.trim() || undefined)) ? "sent" : "idle");
  }

  return (
    <section aria-label="Answer" className="relay-rise flex flex-col gap-3">
      <div className={showMetrics ? "grid grid-cols-3 gap-2.5" : "sr-only"}>
        <Metric label="Grounding" value={percent(response.grounding_score ?? evaluation?.grounding_score)} bar={response.grounding_score ?? evaluation?.grounding_score} />
        <Metric label="Faithfulness" value={percent(evaluation?.faithfulness)} bar={evaluation?.faithfulness} />
        <Metric label="Relevance" value={percent(evaluation?.relevance)} bar={evaluation?.relevance} />
      </div>

      <article className={`${glass} border-cyan-200/25 bg-[rgba(8,12,30,0.72)] p-5`}>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <p className="min-w-0 truncate text-xs text-slate-400">Landed · {response.query}</p>
          {response.grounded != null ? (
            <span className={`rounded-full border px-2.5 py-1 text-xs font-semibold ${response.grounded ? "border-emerald-400/30 bg-emerald-400/10 text-emerald-300" : "border-amber-400/30 bg-amber-400/10 text-amber-300"}`}>
              {response.grounded ? "Grounded" : "Not grounded"}
            </span>
          ) : null}
        </div>
        {response.warning ? <p className="mb-3 rounded-xl border border-amber-400/25 bg-amber-400/10 p-3 text-sm text-amber-200">{response.warning}</p> : null}
        <div className="max-h-[38vh] overflow-y-auto pr-1 lg:max-h-[34vh]">
          <AnswerText text={response.answer} />
        </div>
      </article>

      <div className={showMetrics ? "grid grid-cols-3 gap-2.5" : "sr-only"}>
        <Metric label="Risk" value={risk ? risk[0].toUpperCase() + risk.slice(1) : "—"} tone={risk === "low" ? "text-emerald-300" : "text-amber-300"} />
        <Metric label="Sources" value={String(response.sources.length)} />
        <Metric label="Round trip" value={ms(response.timings.total_ms)} />
      </div>

      <div role="group" aria-label="Rate this answer" className="flex flex-wrap items-center gap-2">
        {state === "sent" ? (
          <p className="flex items-center gap-2 text-sm text-slate-300"><CheckCircle2 aria-hidden="true" className="h-4 w-4 text-emerald-300" />Thanks, your feedback was saved.</p>
        ) : (
          <>
            <span className="mr-1 text-sm text-slate-400">Was this helpful?</span>
            {[
              { value: 5, label: "Helpful", Icon: ThumbsUp },
              { value: 1, label: "Not helpful", Icon: ThumbsDown },
            ].map(({ value, label, Icon }) => (
              <button
                key={value}
                type="button"
                aria-pressed={rating === value}
                onClick={() => setRating(value)}
                className={`flex min-h-10 items-center gap-2 rounded-xl border px-3 text-sm transition-colors ${rating === value ? "border-cyan-300/50 bg-cyan-300/10 text-white" : "border-white/15 text-slate-300 hover:border-white/30 hover:text-white"}`}
              >
                <Icon aria-hidden="true" className="h-4 w-4" />
                {label}
              </button>
            ))}
            {rating != null ? (
              <form onSubmit={submit} className="flex w-full gap-2">
                <input
                  value={comment}
                  onChange={(event) => setComment(event.target.value)}
                  placeholder="Optional comment"
                  aria-label="Feedback comment"
                  maxLength={1000}
                  className="h-10 min-w-0 flex-1 rounded-xl border border-white/15 bg-black/30 px-3 text-sm text-white placeholder:text-slate-500"
                />
                <button type="submit" disabled={state === "sending"} className="h-10 rounded-xl bg-white px-4 text-sm font-semibold text-slate-900">
                  {state === "sending" ? "Sending" : "Send"}
                </button>
              </form>
            ) : null}
          </>
        )}
      </div>
    </section>
  );
}

export type Telemetry = { retrievalMs?: number; matched?: number; kept?: number; confidence?: number; generationMs?: number; tokens?: number };

export function Hud({ phase, passed, telemetry, error }: { phase: FlightPhase; passed: number; telemetry: Telemetry; error: string | null }) {
  const mode = phase === "idle" ? "Docked" : phase === "arrived" ? "Landed" : phase === "error" ? "Signal lost" : "In flight";
  // The ship is inside universe (passed - 1); it has left every universe before that.
  const currentIndex = phase === "travel" || phase === "landing" ? passed - 1 : -1;
  const current = currentIndex >= 0 ? UNIVERSES[currentIndex] : null;
  const details: Record<string, string> = {
    Retrieve: telemetry.matched != null ? `${telemetry.matched} matched · ${ms(telemetry.retrievalMs)}` : "",
    Rank: telemetry.kept != null ? `${telemetry.kept} kept · ${percent(telemetry.confidence)}` : "",
    Compress: telemetry.kept != null ? "Fits budget" : "",
    Generate: telemetry.tokens ? `${telemetry.tokens} tokens · ${ms(telemetry.generationMs)}` : "",
    Ground: phase === "landing" || phase === "arrived" ? "Checked" : "",
  };

  return (
    <div className={`${glass} w-full max-w-[460px] p-4`}>
      <div className="flex items-center justify-between gap-3">
        <span className="font-mono text-[11px] uppercase tracking-[0.2em] text-slate-400">Mode</span>
        <div className="flex rounded-lg border border-white/15 p-0.5 font-mono text-[11px] uppercase tracking-[0.14em]">
          {["Docked", "In flight", "Landed"].map((label) => (
            <span key={label} className={`rounded-md px-2.5 py-1 ${mode === label ? "bg-white text-slate-900" : "text-slate-400"}`}>{label}</span>
          ))}
        </div>
      </div>
      <ol className="mt-4 space-y-2" aria-label="Universes crossed">
        {UNIVERSES.map((universe, index) => {
          const layer = universe.layer;
          const done = index < currentIndex || phase === "arrived" || (phase === "landing" && index <= currentIndex);
          const active = !done && index === currentIndex;
          return (
            <li key={layer} className="grid grid-cols-[14px_minmax(0,1fr)_auto] items-center gap-2 text-sm">
              <span aria-hidden="true" className={`h-2 w-2 rounded-full ${done ? "bg-slate-200" : active ? "animate-pulse bg-amber-300" : "bg-white/20"}`} />
              <span className={`truncate ${done || active ? "text-white" : "text-slate-500"}`}>
                <span className="font-mono text-[11px] text-slate-400">{universe.numeral}</span> {universe.name}
                <span className="ml-2 font-mono text-[10px] uppercase tracking-[0.14em] text-slate-500">{layer}</span>
              </span>
              <span className="truncate text-right font-mono text-xs text-slate-400">
                {details[layer] || (active ? "…" : "")}
                <span className="sr-only">{done ? " complete" : active ? " in progress" : " pending"}</span>
              </span>
            </li>
          );
        })}
      </ol>
      <p role="status" aria-live="polite" className="mt-3 flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.16em] text-slate-300">
        <span aria-hidden="true" className={`h-1.5 w-1.5 rounded-full ${phase === "error" ? "bg-rose-400" : phase === "idle" ? "bg-slate-400" : "bg-violet-400"}`} />
        {error ?? (current ? `In universe ${current.numeral} · ${current.name}` : phase === "travel" ? "Approaching the wormhole" : phase === "arrived" ? "Landed" : "Ready for launch")}
      </p>
    </div>
  );
}

type EvidenceRow = { text: string; score: number; name: string };

function evidenceRows(response: QueryResponse | null, trace: RetrievalDebugResponse | null): EvidenceRow[] {
  const useTrace = trace && response && trace.query === response.query;
  const texts = useTrace ? trace.ranked_documents : response?.sources ?? [];
  const traceRows = useTrace ? trace.retrieval_score_trace : response?.retrieval_score_trace ?? [];
  const scores = useTrace ? trace.relevance_scores : response?.relevance_scores ?? [];
  return texts.map((text, index) => ({
    text,
    score: traceRows[index]?.final_fused_score ?? scores[index] ?? 0,
    name: String(traceRows[index]?.source ?? "Passage").split(/[\\/]/).pop() ?? "Passage",
  }));
}

const smallButton =
  "inline-flex min-h-9 items-center gap-2 rounded-lg border border-white/15 px-3 font-mono text-[11px] uppercase tracking-[0.16em] text-slate-200 transition-colors hover:border-white/35 hover:text-white disabled:cursor-wait disabled:opacity-50";

export function DetailsGrid({
  response,
  events,
  trace,
  tracing,
  onTrace,
  improvement,
  improving,
  onImprove,
}: {
  response: QueryResponse | null;
  events: ActivityEvent[];
  trace: RetrievalDebugResponse | null;
  tracing: boolean;
  onTrace: () => void;
  improvement: ImprovementResponse | null;
  improving: boolean;
  onImprove: () => void;
}) {
  const evaluation = response?.evaluation;
  const quality: Array<[string, number | null | undefined]> = [
    ["Context precision", evaluation?.context_precision],
    ["Context recall", evaluation?.context_recall],
    ["Retrieval diversity", evaluation?.retrieval_diversity_score],
    ["Retrieval confidence", response?.trace?.retrieval_confidence],
  ];
  const timings = response?.timings;
  const timingRows: Array<[string, number]> = timings
    ? [["Retrieve", timings.retrieval_ms], ["Rank", timings.ranking_ms], ["Generate", timings.generation_ms], ["Evaluate", timings.evaluation_ms], ...(timings.correction_ms ? [["Correct", timings.correction_ms] as [string, number]] : []), ["Total", timings.total_ms]]
    : [];
  const maxTiming = Math.max(1, ...timingRows.map(([, value]) => value));
  const rows = evidenceRows(response, trace);
  const traced = Boolean(trace && response && trace.query === response.query);
  const routeTrace = traced ? trace?.trace : response?.trace;

  return (
    <div className="mx-auto flex max-w-[1360px] flex-col gap-5 px-4 pb-16 md:px-8">
      <div className="flex flex-wrap gap-5">
        <section id="evidence" aria-labelledby="evidence-title" className={`${glass} min-w-0 flex-[2_1_560px] p-5`}>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="min-w-0">
              <h2 id="evidence-title" className="text-base font-semibold text-white">Evidence used</h2>
              {routeTrace ? (
                <p className="mt-1 text-xs text-slate-400">
                  Route {routeTrace.query_type} · channels {routeTrace.retrieval_channels?.join(", ")}
                  {routeTrace.feedback_terms?.length ? ` · feedback terms ${routeTrace.feedback_terms.join(", ")}` : ""}
                  {traced && trace ? ` · re-traced: ${trace.initial_documents.length} found, ${trace.ranked_documents.length} kept` : ""}
                </p>
              ) : null}
            </div>
            <button type="button" onClick={onTrace} disabled={!response || tracing} className={smallButton}>
              <ScanSearch aria-hidden="true" className={`h-3.5 w-3.5 ${tracing ? "animate-pulse" : ""}`} />
              {tracing ? "Tracing" : "Run trace"}
            </button>
          </div>
          <div className="mt-4 space-y-3">
            {rows.length ? (
              rows.map((row, index) => (
                <div key={index} className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
                  <div className="flex justify-between gap-2 text-sm">
                    <span className="truncate font-semibold text-white">{row.name}</span>
                    <span className="font-mono text-cyan-300">{percent(row.score)}</span>
                  </div>
                  <div className="my-2 h-1 rounded-full bg-white/10" aria-hidden="true">
                    <div className="h-full rounded-full bg-cyan-300" style={{ width: `${Math.round(row.score * 100)}%` }} />
                  </div>
                  <p className="line-clamp-3 text-sm leading-6 text-slate-300">{row.text}</p>
                </div>
              ))
            ) : (
              <p className="text-sm text-slate-400">Send a question to see the passages the answer was built from.</p>
            )}
          </div>
        </section>

        <section id="quality" aria-labelledby="quality-title" className={`${glass} min-w-0 flex-[1_1_300px] p-5`}>
          <h2 id="quality-title" className="text-base font-semibold text-white">Quality details</h2>
          <div className="mt-4 space-y-3">
            {quality.map(([label, value]) => (
              <div key={label}>
                <div className="flex justify-between text-sm"><span className="text-slate-300">{label}</span><span className="font-mono text-white">{percent(value)}</span></div>
                <div className="mt-1.5 h-1 rounded-full bg-white/10" aria-hidden="true"><div className="h-full rounded-full bg-violet-400" style={{ width: `${Math.round((value ?? 0) * 100)}%` }} /></div>
              </div>
            ))}
            {evaluation?.unsupported_sentences?.length ? (
              <div className="rounded-xl border border-amber-400/25 bg-amber-400/10 p-3 text-sm text-amber-200">
                {evaluation.unsupported_sentences.length} sentence(s) not supported by the passages.
              </div>
            ) : evaluation ? (
              <p className="text-sm text-emerald-300">No unsupported sentences found.</p>
            ) : null}
            {response?.trace?.corrective_attempts?.length ? (
              <p className="text-sm text-slate-300">Corrective retry ran {response.trace.corrective_attempts.length} time(s) for this answer.</p>
            ) : null}
          </div>
        </section>
      </div>

      <div className="grid gap-5 lg:grid-cols-3">
        <section aria-labelledby="timing-title" className={`${glass} p-5`}>
          <h2 id="timing-title" className="text-base font-semibold text-white">Timing</h2>
          <div className="mt-4 space-y-2.5">
            {timingRows.length ? (
              timingRows.map(([label, value]) => (
                <div key={label} className="grid grid-cols-[80px_minmax(0,1fr)_72px] items-center gap-3 text-sm">
                  <span className="text-slate-300">{label}</span>
                  <div className="h-1.5 rounded-full bg-white/10" aria-hidden="true"><div className="h-full rounded-full bg-violet-400" style={{ width: `${Math.max(2, Math.round((value / maxTiming) * 100))}%` }} /></div>
                  <span className="text-right font-mono text-white">{ms(value)}</span>
                </div>
              ))
            ) : (
              <p className="text-sm text-slate-400">Timings appear after the first landing.</p>
            )}
          </div>
        </section>

        <section id="tuning" aria-labelledby="tuning-title" className={`${glass} p-5`}>
          <div className="flex items-center justify-between gap-3">
            <h2 id="tuning-title" className="text-base font-semibold text-white">Tuning notes</h2>
            <button type="button" onClick={onImprove} disabled={improving} className={smallButton}>
              <SlidersHorizontal aria-hidden="true" className={`h-3.5 w-3.5 ${improving ? "animate-pulse" : ""}`} />
              {improving ? "Reviewing" : "Review tuning"}
            </button>
          </div>
          {improvement ? (
            <div className="mt-4 space-y-2 text-sm text-slate-300">
              <p>{improvement.summary}</p>
              {improvement.suggestions.map((suggestion) => (
                <p key={suggestion} className="rounded-xl border border-white/10 bg-white/[0.03] p-3">{suggestion}</p>
              ))}
            </div>
          ) : (
            <p className="mt-4 text-sm text-slate-400">Scan past answers and user feedback for weak retrieval and get tuning suggestions.</p>
          )}
        </section>

        <section id="activity" aria-labelledby="activity-title" className={`${glass} p-5`}>
          <h2 id="activity-title" className="text-base font-semibold text-white">Activity</h2>
          <ul className="mt-4 space-y-3">
            {events.length ? (
              events.slice(0, 6).map((event) => (
                <li key={event.id} className="flex gap-3 text-sm">
                  <span aria-hidden="true" className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${event.severity === "error" ? "bg-rose-400" : event.severity === "warning" ? "bg-amber-300" : "bg-cyan-300"}`} />
                  <span><span className="text-white">{event.title}</span><span className="block text-xs text-slate-400">{event.time} · {event.detail}</span></span>
                </li>
              ))
            ) : (
              <li className="text-sm text-slate-400">No activity yet.</li>
            )}
          </ul>
        </section>
      </div>
    </div>
  );
}
