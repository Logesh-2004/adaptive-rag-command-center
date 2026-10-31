"use client";

import { FormEvent, useState } from "react";
import { AlertTriangle, BadgeCheck, CheckCircle2, Clock3, Orbit, Rocket, SendHorizontal, Sparkles, XCircle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import type { QueryResponse } from "@/types/api";

export type JourneyStage = "idle" | "launching" | "retrieving" | "crossing" | "generating" | "landing" | "arrived" | "error";

const journeyCopy: Record<JourneyStage, { title: string; detail: string }> = {
  idle: { title: "Relay standing by", detail: "Your question will cross the local retrieval layers and return with its evidence." },
  launching: { title: "Signal launched", detail: "Your question is entering the knowledge field." },
  retrieving: { title: "Scanning the archive", detail: "Collecting relevant passages from the local index." },
  crossing: { title: "Crossing the ranking layer", detail: "The strongest context is being carried toward the answer model." },
  generating: { title: "Answer forming beyond the portal", detail: "The model is shaping a response from the retrieved context." },
  landing: { title: "Preparing to dock", detail: "The response and its quality checks are landing." },
  arrived: { title: "Docked at the answer station", detail: "The answer has landed with its evidence and quality signals." },
  error: { title: "Signal interrupted", detail: "Edit the question or resend it to start a new journey." },
};

const promptSuggestions = ["Explain adaptive RAG", "Reduce unsupported answers", "Compare RAG methods"];

function formatScore(value?: number | null) {
  return value == null ? "—" : `${Math.round(value * 100)}%`;
}

function ShipModel() {
  return (
    <div className="ship-model">
      <svg viewBox="0 0 260 170" role="img" aria-label="A faceted silver and violet spacecraft">
        <defs>
          <linearGradient id="ship-hull-top" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="#effbff" />
            <stop offset="0.35" stopColor="#a7c4ef" />
            <stop offset="0.72" stopColor="#7f81d7" />
            <stop offset="1" stopColor="#d9dcff" />
          </linearGradient>
          <linearGradient id="ship-hull-side" x1="0" y1="0" x2="1" y2="0.9">
            <stop offset="0" stopColor="#58719d" />
            <stop offset="0.48" stopColor="#293d68" />
            <stop offset="1" stopColor="#161d3f" />
          </linearGradient>
          <linearGradient id="ship-wing" x1="0" y1="0" x2="0.9" y2="1">
            <stop offset="0" stopColor="#d7dcff" />
            <stop offset="0.38" stopColor="#8f8bea" />
            <stop offset="1" stopColor="#373f82" />
          </linearGradient>
          <linearGradient id="ship-wing-shadow" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="#788bd0" />
            <stop offset="1" stopColor="#222c5d" />
          </linearGradient>
          <linearGradient id="ship-cockpit" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="#e2ffff" />
            <stop offset="0.2" stopColor="#69e4ff" />
            <stop offset="0.7" stopColor="#507bea" />
            <stop offset="1" stopColor="#28275b" />
          </linearGradient>
          <linearGradient id="ship-engine" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0" stopColor="#8b63ff" stopOpacity="0" />
            <stop offset="0.65" stopColor="#bd8aff" stopOpacity="0.72" />
            <stop offset="1" stopColor="#9cf3ff" />
          </linearGradient>
        </defs>
        <ellipse cx="137" cy="139" rx="94" ry="11" fill="#020718" fillOpacity="0.65" />
        <path d="M9 83h67" stroke="url(#ship-engine)" strokeWidth="13" strokeLinecap="round" opacity="0.74" />
        <path d="M28 83h52" stroke="#a6f2ff" strokeWidth="3" strokeLinecap="round" opacity="0.72" />
        <path d="M110 67 62 19 73 70 102 89Z" fill="url(#ship-wing)" stroke="#dce4ff" strokeOpacity="0.52" strokeWidth="1.2" />
        <path d="m62 19 28 47 14 23-31-19Z" fill="#697ac1" fillOpacity="0.66" />
        <path d="m109 101-47 49 11-52 29-18Z" fill="url(#ship-wing-shadow)" stroke="#aeb8fa" strokeOpacity="0.42" strokeWidth="1.2" />
        <path d="m62 150 28-47 14-23-31 18Z" fill="#252f66" fillOpacity="0.82" />
        <path d="m73 71-22-13 15 25-15 22 24-10Z" fill="#7c75cc" stroke="#b9c5ff" strokeOpacity="0.5" strokeWidth="1" />
        <path d="m49 84 57-29 86 8 54 21-52 18-90 18-55-22Z" fill="url(#ship-hull-top)" stroke="#e9f4ff" strokeOpacity="0.58" strokeWidth="1.5" />
        <path d="m49 84 55 14 90 4 52-18-52 34-91 14-49-29Z" fill="url(#ship-hull-side)" stroke="#8da8e5" strokeOpacity="0.36" strokeWidth="1.2" />
        <path d="m190 63 52 21-51 17 17-17Z" fill="#f4fdff" fillOpacity="0.76" />
        <path d="m104 98 90 4-47 16-51 4-29-16Z" fill="#142347" fillOpacity="0.7" />
        <path d="m115 68 40 1 27 10-30 11-39-8Z" fill="#313e76" stroke="#d9e5ff" strokeOpacity="0.7" strokeWidth="1.4" />
        <path d="m118 69 35 1 19 8-23 8-31-7Z" fill="url(#ship-cockpit)" />
        <path d="m122 71 11 1-4 12-11-3Z" fill="#fff" fillOpacity="0.46" />
        <path d="m89 75 26-11 4 8-28 13Z" fill="#f2fbff" fillOpacity="0.88" />
        <path d="m90 96 27 8 3 7-25-6Z" fill="#8e9fe1" fillOpacity="0.66" />
        <path d="m55 84 12-6 4 8-13 4Z" fill="#bfebff" fillOpacity="0.86" />
        <circle cx="57" cy="84" r="4.2" fill="#a7f6ff" />
        <circle cx="57" cy="84" r="8" fill="none" stroke="#bd91ff" strokeOpacity="0.76" />
        <path d="m155 68 33 4" stroke="#fff" strokeOpacity="0.54" strokeWidth="1.4" />
      </svg>
    </div>
  );
}

export function ChatConsole({
  response,
  loading,
  latency,
  journeyStage = "idle",
  onSubmit,
}: {
  response?: QueryResponse | null;
  loading: boolean;
  latency?: number | null;
  journeyStage?: JourneyStage;
  onSubmit: (query: string) => void;
}) {
  const [query, setQuery] = useState("What is adaptive RAG?");
  const stage = journeyCopy[journeyStage];
  const isMoving = ["launching", "retrieving", "crossing", "generating", "landing"].includes(journeyStage);
  const hasQuery = Boolean(response?.query);
  const hasAnswer = Boolean(response?.answer);
  const groundingScore = response?.grounding_score ?? response?.grounding ?? response?.evaluation?.grounding_score ?? response?.evaluation?.grounding;
  const stageStatus = journeyStage === "arrived" ? "Docked" : journeyStage === "error" ? "Signal lost" : isMoving ? "In transit" : "Awaiting signal";

  function useSuggestion(prompt: string) {
    setQuery(prompt);
    if (!loading) onSubmit(prompt);
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!query.trim() || loading) return;
    onSubmit(query.trim());
  }

  return (
    <Card id="chat" className="query-journey-card">
      <CardHeader className="query-journey-head space-y-0">
        <div className="query-journey-heading">
          <div className="journey-heading-icon"><Orbit aria-hidden="true" className="h-5 w-5" /></div>
          <div>
            <p className="section-kicker">The wormhole relay · live trace</p>
            <CardTitle className="mt-2 text-xl sm:text-2xl">A question travels. Evidence comes back.</CardTitle>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">Watch your query cross the local knowledge layers and land beside a checked answer.</p>
          </div>
        </div>
        <Badge className={journeyStage === "arrived" ? "journey-status journey-status-ready" : journeyStage === "error" ? "journey-status journey-status-error" : isMoving ? "journey-status journey-status-active" : "journey-status"}>
          {journeyStage === "arrived" ? <BadgeCheck aria-hidden="true" className="h-3.5 w-3.5" /> : <Orbit aria-hidden="true" className="h-3.5 w-3.5" />}
          {stageStatus}
        </Badge>
      </CardHeader>

      <CardContent className="query-journey-content pt-5">
        <div className="query-journey-grid">
          <section className="launch-panel" aria-labelledby="launch-title">
            <div className="station-heading">
              <span className="station-index">01</span>
              <div>
                <p className="metric-label">Departure · local corpus</p>
                <h3 id="launch-title" className="mt-1 text-lg font-semibold text-foreground">Send your question</h3>
              </div>
            </div>

            <form onSubmit={submit} className="launch-form">
              <label htmlFor="rag-query" className="block text-sm font-medium text-foreground">Your question</label>
              <Textarea
                id="rag-query"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="What would you like to find in your documents?"
                aria-describedby="rag-query-help"
                className="query-textarea min-h-[132px] resize-y"
              />
              <div className="launch-action-row">
                <p id="rag-query-help" className="launch-helper"><span className="helper-signal" aria-hidden="true" />Grounded in retrieved passages from your local index.</p>
                <Button type="submit" disabled={loading || !query.trim()} className="launch-button">
                  {loading ? <Rocket aria-hidden="true" className="h-4 w-4" /> : <SendHorizontal aria-hidden="true" className="h-4 w-4" />}
                  {loading ? "In transit" : "Send query"}
                </Button>
              </div>
            </form>

            {!hasQuery ? (
              <div className="prompt-suggestions">
                <p className="metric-label">Quick starts</p>
                <div className="prompt-suggestion-list">
                  {promptSuggestions.map((prompt) => (
                    <button key={prompt} type="button" onClick={() => useSuggestion(prompt)} disabled={loading} className="prompt-suggestion">
                      <Sparkles aria-hidden="true" className="h-3.5 w-3.5 shrink-0" />
                      <span>{prompt}</span>
                    </button>
                  ))}
                </div>
              </div>
            ) : null}
          </section>

          <div className="wormhole-column">
            <p className="wormhole-label"><span className="helper-signal" aria-hidden="true" />Transit lane</p>
            <div className="wormhole-scene" data-moving={isMoving} data-stage={journeyStage} aria-hidden="true">
              <span className="wormhole-streak" />
              <div className="wormhole-portal">
                <span className="portal-ring portal-ring-outer" />
                <span className="portal-ring portal-ring-inner" />
                <span className="portal-light" />
                <Sparkles className="portal-spark" />
              </div>
              <div className="flight-track">
                <span className="flight-path">
                  <span className="flight-ship"><ShipModel /></span>
                </span>
              </div>
              <span className="portal-endpoint portal-endpoint-start" />
              <span className="portal-endpoint portal-endpoint-end" />
            </div>
            <div className="warp-phase-list" aria-hidden="true">
              <span><i />Local archive</span>
              <span><i />Ranking layer</span>
              <span><i />Answer model</span>
            </div>
          </div>

          <section className="answer-dock" aria-labelledby="answer-title" aria-busy={loading} data-landed={journeyStage === "arrived"}>
            <div className="station-heading answer-heading">
              <span className="station-index station-index-arrival">02</span>
              <div className="answer-heading-copy">
                <p className="metric-label">Arrival · evidence checked</p>
                <h3 id="answer-title" className="mt-1 text-lg font-semibold text-foreground">Answer dock</h3>
              </div>
              <div className="answer-badges">
                {response?.grounded != null ? (
                  <Badge className={response.grounded ? "gap-1 text-success" : "gap-1 text-warning"}>
                    {response.grounded ? <CheckCircle2 aria-hidden="true" className="h-3.5 w-3.5" /> : <XCircle aria-hidden="true" className="h-3.5 w-3.5" />}
                    {response.grounded ? "Grounded" : "Ungrounded"}
                  </Badge>
                ) : null}
                {response?.hallucination_risk ? <Badge className={response.hallucination_risk === "low" ? "text-success" : "text-warning"}>Risk: {response.hallucination_risk}</Badge> : null}
              </div>
            </div>

            {hasQuery ? (
              <div className="incoming-query">
                <span className="metric-label">Incoming signal</span>
                <p className="mt-1 break-words text-xs leading-5 text-muted-foreground">{response?.query}</p>
              </div>
            ) : null}

            <div className="answer-body">
              {response?.warning ? (
                <div className="mb-3 flex items-start gap-2 rounded-xl border border-warning/25 bg-warning/[0.08] p-3 text-sm text-warning">
                  <AlertTriangle aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0" />
                  <span>{response.warning}</span>
                </div>
              ) : null}
              {hasAnswer ? (
                <div className="answer-content">
                  <p className="break-words whitespace-pre-wrap text-sm leading-7 text-foreground">
                    {response?.answer}
                    {loading ? <span className="ml-1 inline-block h-4 w-1 bg-primary align-middle" /> : null}
                  </p>
                </div>
              ) : loading ? (
                <div className="answer-loading" aria-label="The answer is crossing the wormhole">
                  <span className="answer-skeleton-line h-3 w-4/5 rounded-full" />
                  <span className="answer-skeleton-line h-3 w-full rounded-full" />
                  <span className="answer-skeleton-line h-3 w-3/5 rounded-full" />
                  <p className="mt-2 text-xs text-muted-foreground">The ship is carrying context through the reasoning field…</p>
                </div>
              ) : journeyStage === "error" ? (
                <div className="answer-empty answer-empty-error">
                  <AlertTriangle aria-hidden="true" className="h-6 w-6 text-warning" />
                  <p className="mt-3 text-sm font-medium text-foreground">The signal did not return</p>
                  <p className="mt-1 text-xs leading-5 text-muted-foreground">Try the same question again or make it more specific.</p>
                </div>
              ) : hasQuery ? (
                <div className="answer-empty answer-empty-error">
                  <AlertTriangle aria-hidden="true" className="h-6 w-6 text-warning" />
                  <p className="mt-3 text-sm font-medium text-foreground">No answer text returned</p>
                  <p className="mt-1 text-xs leading-5 text-muted-foreground">Try a more specific question or check the retrieved passages below.</p>
                </div>
              ) : (
                <div className="answer-empty">
                  <span className="answer-orbit-mark"><Orbit aria-hidden="true" className="h-6 w-6" /></span>
                  <p className="mt-3 text-sm font-medium text-foreground">Waiting for first transmission</p>
                  <p className="mt-1 max-w-xs text-xs leading-5 text-muted-foreground">Your answer, evidence, and quality signals will dock here.</p>
                </div>
              )}
            </div>

            {hasAnswer ? (
              <>
                <div className="answer-signal-strip" role="group" aria-label="Answer summary metrics">
                  <div><span>Grounding</span><strong>{formatScore(groundingScore)}</strong></div>
                  <div><span>Sources</span><strong>{response?.sources?.length ?? 0}</strong></div>
                  <div><span>Round trip</span><strong>{Math.round(Number(latency ?? response?.timings?.total_ms ?? 0))} ms</strong></div>
                </div>
                {response?.timings ? (
                  <div className="answer-timings" role="group" aria-label="Pipeline timings">
                    {[
                      ["Retrieve", response.timings.retrieval_ms],
                      ["Rank", response.timings.ranking_ms],
                      ["Generate", response.timings.generation_ms],
                      ["Evaluate", response.timings.evaluation_ms],
                      ["Total", response.timings.total_ms],
                    ].map(([label, value]) => (
                      <div key={label} className="timing-chip">
                        <span>{label}</span>
                        <strong>{Math.round(Number(value))} ms</strong>
                      </div>
                    ))}
                  </div>
                ) : null}
              </>
            ) : null}
          </section>
        </div>

        <div className="journey-readout" role="status" aria-live="polite" aria-atomic="true">
          <span className={isMoving ? "journey-readout-dot is-active" : journeyStage === "arrived" ? "journey-readout-dot is-ready" : "journey-readout-dot"} aria-hidden="true" />
          <div>
            <p className="journey-readout-title">{stage.title}</p>
            <p className="journey-readout-detail">{stage.detail}</p>
          </div>
          {latency != null && hasQuery ? <span className="journey-latency"><Clock3 aria-hidden="true" className="h-3.5 w-3.5" />{latency} ms</span> : null}
        </div>
      </CardContent>
    </Card>
  );
}
