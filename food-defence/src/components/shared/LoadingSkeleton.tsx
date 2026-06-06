"use client";

import { useEffect, useState } from "react";

/**
 * Loading skeletons used while the dashboard is fetching data.
 *
 * The default behaviour is a soft pulse on placeholder blocks shaped like
 * the real content. This gives the reader an immediate sense of "the layout
 * is correct, the numbers are arriving" instead of an unanchored spinner.
 *
 * Three variants are exported:
 *
 *   <LaneForensicSkeleton hs="…" dest=… origin=… />
 *   <CountrySnapshotSkeleton m49={…} />
 *   <BriefSkeleton phase="reading" status="…" toolCalls={…} />
 *
 * The skeleton blocks all reuse the same ``Shimmer`` primitive so the pulse
 * cadence stays consistent.
 */

import { Activity, Sparkles, CheckCircle2, Circle } from "lucide-react";

type ShimmerProps = {
  className?: string;
};

/** Single pulsing placeholder block. */
function Shimmer({ className = "" }: ShimmerProps) {
  return (
    <span
      aria-hidden
      className={
        "inline-block animate-pulse rounded bg-gradient-to-r from-slate-100 via-slate-200 to-slate-100 bg-[length:200%_100%] " +
        className
      }
      style={{ animationDuration: "1600ms" }}
    />
  );
}

/** Lane forensic page skeleton: header, priority card, track-record tile. */
export function LaneForensicSkeleton({
  hs,
  dest,
  origin,
}: {
  hs?: string;
  dest?: number | string;
  origin?: number | string;
}) {
  return (
    <div className="mx-auto max-w-7xl space-y-5">
      {/* Header */}
      <header className="flex items-start gap-4">
        <Shimmer className="mt-1 h-8 w-8 rounded-lg" />
        <div className="flex-1 space-y-2">
          <Shimmer className="h-3 w-40 rounded-full" />
          <Shimmer className="h-7 w-72 rounded-md" />
          <div className="flex items-center gap-2 pt-1">
            <Shimmer className="h-4 w-16 rounded-full" />
            <Shimmer className="h-4 w-20 rounded-full" />
            {hs ? (
              <span className="ml-2 inline-flex items-center gap-2 text-[11px] text-slate-500">
                <Activity size={11} className="animate-pulse" aria-hidden />
                Loading lane HS {hs} · M49 {origin} → {dest}…
              </span>
            ) : (
              <Shimmer className="h-4 w-32 rounded-full" />
            )}
          </div>
        </div>
      </header>

      {/* Brief card placeholder */}
      <div className="rounded-2xl border border-blue-100 bg-gradient-to-br from-blue-50/40 to-white p-5 shadow-sm">
        <div className="flex items-center gap-2 border-b border-slate-100 pb-3">
          <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-blue-300 to-indigo-300 text-white">
            <Sparkles size={14} aria-hidden />
          </span>
          <Shimmer className="h-3 w-32 rounded-full" />
        </div>
        <div className="space-y-2 pt-4">
          <Shimmer className="h-5 w-3/4 rounded-md" />
          <Shimmer className="h-3 w-24 rounded-full" />
          <div className="space-y-2 pt-2">
            <Shimmer className="h-3 w-full rounded-md" />
            <Shimmer className="h-3 w-[97%] rounded-md" />
            <Shimmer className="h-3 w-[94%] rounded-md" />
            <Shimmer className="h-3 w-[88%] rounded-md" />
          </div>
        </div>
      </div>

      {/* Priority + track record tiles */}
      <div className="rounded-2xl border border-emerald-100 bg-gradient-to-br from-emerald-50/30 to-white p-5">
        <Shimmer className="h-3 w-24 rounded-full" />
        <div className="mt-2 flex items-baseline gap-3">
          <Shimmer className="h-9 w-24 rounded-md" />
          <Shimmer className="h-3 w-48 rounded-full" />
        </div>
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="mb-3 flex items-center gap-2">
          <Shimmer className="h-6 w-6 rounded-full" />
          <Shimmer className="h-4 w-32 rounded-md" />
        </div>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="rounded-lg border border-slate-100 p-3">
              <Shimmer className="h-3 w-20 rounded-full" />
              <Shimmer className="mt-2 h-7 w-16 rounded-md" />
              <Shimmer className="mt-2 h-2.5 w-28 rounded-full" />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/** Country page skeleton: ACEP card, ORPS chart row, inbound table. */
export function CountrySnapshotSkeleton({ m49 }: { m49?: number | string }) {
  return (
    <div className="mx-auto max-w-7xl space-y-5">
      <header className="flex items-start gap-4">
        <Shimmer className="mt-1 h-8 w-8 rounded-lg" />
        <div className="flex-1 space-y-2">
          <Shimmer className="h-3 w-40 rounded-full" />
          <Shimmer className="h-7 w-64 rounded-md" />
          {m49 ? (
            <p className="flex items-center gap-2 text-[11px] text-slate-500">
              <Activity size={11} className="animate-pulse" aria-hidden />
              Loading country M49 {m49}…
            </p>
          ) : (
            <Shimmer className="h-4 w-48 rounded-full" />
          )}
        </div>
      </header>

      <section className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="rounded-xl border border-slate-200 bg-white p-3">
            <Shimmer className="h-3 w-24 rounded-full" />
            <Shimmer className="mt-2 h-8 w-20 rounded-md" />
            <Shimmer className="mt-1 h-2.5 w-32 rounded-full" />
          </div>
        ))}
      </section>

      <div className="rounded-2xl border border-violet-100 bg-gradient-to-br from-violet-50/40 to-white p-5">
        <div className="flex items-center gap-2 border-b border-slate-100 pb-3">
          <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-violet-300 to-purple-300 text-white">
            <Sparkles size={14} aria-hidden />
          </span>
          <Shimmer className="h-3 w-32 rounded-full" />
        </div>
        <div className="space-y-2 pt-4">
          <Shimmer className="h-5 w-2/3 rounded-md" />
          <Shimmer className="h-3 w-full rounded-md" />
          <Shimmer className="h-3 w-[94%] rounded-md" />
          <Shimmer className="h-3 w-[88%] rounded-md" />
        </div>
      </div>
    </div>
  );
}

/* ──────────────────────────────────────────────────────────────────── */
/* Brief streaming skeleton with a phase stepper                         */
/* ──────────────────────────────────────────────────────────────────── */

/** Phases the BriefCard moves through. */
export type BriefPhase =
  | "reading"
  | "drafting"
  | "verifying"
  | "finalising";

const BRIEF_PHASES: { id: BriefPhase; label: string; hint: string }[] = [
  {
    id: "reading",
    label: "Reading lane data",
    hint: "Pulling corridor profile, alerts, and metric bands.",
  },
  {
    id: "drafting",
    label: "Drafting the analysis",
    hint: "Composing the headline and supporting paragraphs.",
  },
  {
    id: "verifying",
    label: "Verifying citations",
    hint: "Re-checking every cited number against the engine.",
  },
  {
    id: "finalising",
    label: "Polishing the prose",
    hint: "Stripping style violations and assembling the final brief.",
  },
];

/** QA-specific phase labels. Same underlying BriefPhase ids; just nicer
 * wording for the chat surface. */
const QA_PHASES: { id: BriefPhase; label: string; hint: string }[] = [
  {
    id: "reading",
    label: "Routing the question",
    hint: "Classifying intent and extracting entities.",
  },
  {
    id: "drafting",
    label: "Gathering evidence",
    hint: "Calling corpus tools for the data the answer needs.",
  },
  {
    id: "verifying",
    label: "Composing the answer",
    hint: "Drafting the markdown reply with citations.",
  },
  {
    id: "finalising",
    label: "Finalising",
    hint: "Sanitising prose and persisting the turn.",
  },
];

/** Translate the latest SSE event name / status into a phase. */
export function phaseFromStatus(
  status: string | undefined,
  toolCallNames: string[]
): BriefPhase {
  const s = (status ?? "").toLowerCase();
  const last = toolCallNames[toolCallNames.length - 1] ?? "";
  if (s.includes("verif") || s.includes("style")) return "verifying";
  if (last.startsWith("submit_")) return "finalising";
  if (toolCallNames.length === 0 && (s === "" || s.includes("starting"))) {
    return "reading";
  }
  if (toolCallNames.length > 0) return "drafting";
  return "drafting";
}

/**
 * Auto-advance the phase stepper on a timer when a card has no real-time
 * (SSE) signal. The defaults match the typical wall-clock shape of the
 * non-streamed agent endpoints (hypotheses, anomaly): reading is short,
 * drafting is the long phase, verifying / finalising arrive late.
 *
 * Pass `active=false` when not loading; the hook resets to "reading".
 */
export function useTimedBriefPhase(
  active: boolean,
  schedule: { drafting?: number; verifying?: number; finalising?: number } = {}
): BriefPhase {
  const draftingAt = schedule.drafting ?? 2_000;
  const verifyingAt = schedule.verifying ?? 25_000;
  const finalisingAt = schedule.finalising ?? 45_000;

  const [phase, setPhase] = useState<BriefPhase>("reading");

  useEffect(() => {
    if (!active) {
      setPhase("reading");
      return;
    }
    setPhase("reading");
    const timers: ReturnType<typeof setTimeout>[] = [
      setTimeout(() => setPhase("drafting"), draftingAt),
      setTimeout(() => setPhase("verifying"), verifyingAt),
      setTimeout(() => setPhase("finalising"), finalisingAt),
    ];
    return () => {
      timers.forEach(clearTimeout);
    };
  }, [active, draftingAt, verifyingAt, finalisingAt]);

  return phase;
}

/**
 * Animated brief skeleton shown while the SSE stream is producing tokens.
 *
 * Three regions:
 *   - phase stepper at top so the user sees which step is live
 *   - shimmering paragraph placeholders that resemble the final brief shape
 *   - micro-trace of the actual tool calls beneath, for transparency
 */
export function BriefSkeleton({
  phase,
  toolCalls,
  status,
  variant = "brief",
}: {
  phase: BriefPhase;
  toolCalls: { name: string; latency_ms: number }[];
  status?: string;
  /**
   * Tweak the shimmer block layout AND the phase-stepper labels to match
   * the card the skeleton sits in.
   * - "brief": single headline + two paragraph blocks (default).
   * - "hypotheses": a summary line + three stacked hypothesis-row blocks.
   * - "anomaly": verdict line + two paragraph sections + peer line.
   * - "qa": chat-style answer shape: short answer + supporting paragraph.
   */
  variant?: "brief" | "hypotheses" | "anomaly" | "qa";
}) {
  const phaseSet = variant === "qa" ? QA_PHASES : BRIEF_PHASES;
  const currentIdx = phaseSet.findIndex((p) => p.id === phase);
  // When the caller hasn't supplied a status, fall back to the current
  // phase's hint so the loading text always says something meaningful.
  const displayStatus =
    status ?? phaseSet[Math.max(currentIdx, 0)]?.hint ?? "";
  return (
    <div className="space-y-4">
      <PhaseStepper currentIdx={currentIdx} phases={phaseSet} />

      {/* Variant-shaped skeleton blocks */}
      {variant === "hypotheses" ? (
        <HypothesesSkeleton />
      ) : variant === "anomaly" ? (
        <AnomalySkeleton />
      ) : variant === "qa" ? (
        <QASkeleton />
      ) : (
        <DefaultBriefBlocks />
      )}

      {/* Live trace */}
      {(toolCalls.length > 0 || displayStatus) && (
        <div className="rounded-md border border-slate-100 bg-slate-50/60 px-3 py-2 text-[10px]">
          {displayStatus && (
            <p className="flex items-center gap-1 font-medium text-slate-600">
              <Activity size={10} className="animate-pulse" aria-hidden />
              <span>{displayStatus}</span>
            </p>
          )}
          {toolCalls.length > 0 && (
            <ul className="mt-1 grid grid-cols-1 gap-x-3 font-mono text-slate-500 sm:grid-cols-2">
              {toolCalls.slice(-6).map((t, i) => (
                <li key={i} className="truncate">
                  <span className="text-slate-400">→</span> {t.name}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

function DefaultBriefBlocks() {
  return (
    <div className="space-y-2">
      <Shimmer className="h-5 w-[85%] rounded-md" />
      <Shimmer className="h-3 w-24 rounded-full" />
      <div className="space-y-2 pt-2">
        <Shimmer className="h-3 w-full rounded-md" />
        <Shimmer className="h-3 w-[96%] rounded-md" />
        <Shimmer className="h-3 w-[92%] rounded-md" />
        <Shimmer className="h-3 w-[78%] rounded-md" />
      </div>
      <div className="space-y-2 pt-2">
        <Shimmer className="h-3 w-[94%] rounded-md" />
        <Shimmer className="h-3 w-[88%] rounded-md" />
      </div>
    </div>
  );
}

function HypothesesSkeleton() {
  return (
    <div className="space-y-3">
      {/* Pattern summary */}
      <div className="space-y-1.5">
        <Shimmer className="h-3 w-32 rounded-full" />
        <Shimmer className="h-4 w-full rounded-md" />
        <Shimmer className="h-4 w-[88%] rounded-md" />
      </div>
      {/* 3 stacked hypothesis-row placeholders */}
      <div className="space-y-2 pt-1">
        {[0, 1, 2].map((i) => (
          <div
            key={i}
            className="flex items-center gap-2 rounded-lg border border-slate-100 bg-white px-3 py-2"
          >
            <Shimmer className="h-3 w-3 rounded-full" />
            <Shimmer className="h-4 flex-1 rounded-md" />
            <Shimmer className="h-4 w-12 rounded-full" />
          </div>
        ))}
      </div>
    </div>
  );
}

function QASkeleton() {
  return (
    <div className="space-y-2">
      {/* Intent chip placeholder */}
      <Shimmer className="h-3 w-28 rounded-full" />
      {/* Lead sentence (the direct answer) */}
      <Shimmer className="h-5 w-[92%] rounded-md" />
      {/* Supporting paragraph */}
      <div className="space-y-1.5 pt-1">
        <Shimmer className="h-3 w-full rounded-md" />
        <Shimmer className="h-3 w-[96%] rounded-md" />
        <Shimmer className="h-3 w-[88%] rounded-md" />
      </div>
      {/* Potential table outline */}
      <div className="space-y-1.5 pt-2">
        <Shimmer className="h-2.5 w-24 rounded-full" />
        <div className="flex gap-2">
          <Shimmer className="h-3 flex-1 rounded-md" />
          <Shimmer className="h-3 w-16 rounded-md" />
          <Shimmer className="h-3 w-12 rounded-md" />
        </div>
        <div className="flex gap-2">
          <Shimmer className="h-3 flex-1 rounded-md" />
          <Shimmer className="h-3 w-16 rounded-md" />
          <Shimmer className="h-3 w-12 rounded-md" />
        </div>
      </div>
    </div>
  );
}

function AnomalySkeleton() {
  return (
    <div className="space-y-3">
      <Shimmer className="h-3 w-40 rounded-full" />
      <Shimmer className="h-5 w-[80%] rounded-md" />
      {/* Why-this-stands-out section */}
      <div className="space-y-1.5 pt-1">
        <Shimmer className="h-3 w-32 rounded-full" />
        <Shimmer className="h-3 w-full rounded-md" />
        <Shimmer className="h-3 w-[94%] rounded-md" />
        <Shimmer className="h-3 w-[86%] rounded-md" />
      </div>
      {/* Why-not section */}
      <div className="space-y-1.5 pt-1">
        <Shimmer className="h-3 w-44 rounded-full" />
        <Shimmer className="h-3 w-[92%] rounded-md" />
        <Shimmer className="h-3 w-[78%] rounded-md" />
      </div>
      {/* Peer line */}
      <Shimmer className="h-3 w-[70%] rounded-md" />
    </div>
  );
}

function PhaseStepper({
  currentIdx,
  phases = BRIEF_PHASES,
}: {
  currentIdx: number;
  phases?: { id: BriefPhase; label: string; hint: string }[];
}) {
  return (
    <ol className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
      {phases.map((p, i) => {
        const done = i < currentIdx;
        const active = i === currentIdx;
        const Icon = done ? CheckCircle2 : active ? Activity : Circle;
        const colour = done
          ? "text-emerald-600"
          : active
          ? "text-blue-600"
          : "text-slate-300";
        const labelColour = done
          ? "text-emerald-700"
          : active
          ? "text-blue-700"
          : "text-slate-400";
        return (
          <li key={p.id} className="flex items-center gap-1.5 text-[11px]">
            <Icon
              size={12}
              className={`${colour} ${active ? "animate-pulse" : ""}`}
              aria-hidden
            />
            <span className={`font-medium ${labelColour}`}>{p.label}</span>
            {i < phases.length - 1 && (
              <span className="hidden text-slate-300 sm:inline" aria-hidden>
                ›
              </span>
            )}
          </li>
        );
      })}
    </ol>
  );
}
