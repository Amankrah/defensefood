"use client";

import { useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  Lightbulb,
  RefreshCw,
  Activity,
  CheckCircle2,
  XCircle,
  ChevronDown,
  ChevronRight,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import {
  type Hypothesis,
  type HypothesisResponse,
  fetchHypotheses,
  probeHypotheses,
} from "@/lib/agentApi";

interface Props {
  commodity_hs: string;
  destination_m49: number;
  origin_m49: number;
}

interface LoadState {
  phase: "probing" | "needs_generation" | "loading" | "ready" | "error";
  response?: HypothesisResponse;
  errorMessage?: string;
}

/**
 * Hypothesis tile for the lane forensic page.
 *
 * Opt-in: probes the cache on mount. Cached set renders immediately;
 * otherwise a "Generate hypotheses" button gates the LLM call.
 */
export default function HypothesisCard({
  commodity_hs,
  destination_m49,
  origin_m49,
}: Props) {
  const [state, setState] = useState<LoadState>({ phase: "probing" });
  const cancelRef = useRef<boolean>(false);

  const run = async (refresh: boolean) => {
    setState({ phase: "loading" });
    try {
      const r = await fetchHypotheses(commodity_hs, destination_m49, origin_m49, {
        refresh,
      });
      if (cancelRef.current) return;
      setState({ phase: "ready", response: r });
    } catch (e) {
      if (cancelRef.current) return;
      setState({
        phase: "error",
        errorMessage: e instanceof Error ? e.message : String(e),
      });
    }
  };

  useEffect(() => {
    cancelRef.current = false;
    setState({ phase: "probing" });
    (async () => {
      try {
        const p = await probeHypotheses(commodity_hs, destination_m49, origin_m49);
        if (cancelRef.current) return;
        if (p.cached) {
          setState({ phase: "ready", response: p.response });
        } else {
          setState({ phase: "needs_generation" });
        }
      } catch (e) {
        if (cancelRef.current) return;
        setState({ phase: "needs_generation" });
        // eslint-disable-next-line no-console
        console.warn("HypothesisCard probe failed", e);
      }
    })();
    return () => {
      cancelRef.current = true;
    };
  }, [commodity_hs, destination_m49, origin_m49]);

  const hset = state.response?.hset;
  const isLoading = state.phase === "loading";

  return (
    <section className="rounded-2xl border border-amber-200 bg-gradient-to-br from-amber-50/40 to-white shadow-sm">
      <div className="flex items-center justify-between gap-3 border-b border-slate-100 px-5 py-3">
        <div className="flex items-center gap-2">
          <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-amber-500 to-orange-600 text-white shadow-sm">
            <Lightbulb size={14} strokeWidth={2.25} aria-hidden />
          </span>
          <span className="text-xs font-semibold uppercase tracking-wider text-orange-700">
            Candidate explanations
          </span>
          {state.response?.cache_hit && (
            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-600">
              cached
            </span>
          )}
        </div>
        <div className="flex items-center gap-2 text-[10px] text-slate-500">
          {isLoading && (
            <span className="inline-flex items-center gap-1">
              <Activity size={12} className="animate-pulse" aria-hidden />
              generating
            </span>
          )}
          {state.response && (
            <span
              title={`${state.response.tokens_in}→${state.response.tokens_out} tokens · $${state.response.cost_usd.toFixed(4)}`}
            >
              {state.response.latency_ms} ms
            </span>
          )}
          {state.response && (
            <button
              type="button"
              onClick={() => run(true)}
              disabled={isLoading}
              title="Regenerate hypotheses"
              className="rounded p-1 text-slate-500 hover:bg-slate-100 hover:text-slate-700 disabled:opacity-40"
            >
              <RefreshCw size={12} aria-hidden />
            </button>
          )}
        </div>
      </div>

      <div className="space-y-3 px-5 py-4">
        {state.phase === "probing" && (
          <p className="flex items-center gap-2 text-xs text-slate-500">
            <Activity size={12} className="animate-pulse" aria-hidden />
            Checking the hypothesis cache…
          </p>
        )}

        {state.phase === "needs_generation" && (
          <div className="flex items-start justify-between gap-3">
            <div className="text-xs text-slate-600">
              <p className="font-medium text-slate-800">
                No hypotheses on file for this lane yet.
              </p>
              <p className="mt-1 text-[11px] text-slate-500">
                The agent reads the lane profile, multi-period snapshots, and
                methodology hints, then proposes 2 to 4 candidate explanations
                with confidence labels and falsifying tests.
              </p>
            </div>
            <button
              type="button"
              onClick={() => run(false)}
              className="shrink-0 rounded-lg bg-gradient-to-br from-amber-500 to-orange-600 px-3 py-1.5 text-xs font-semibold text-white shadow-sm hover:brightness-110"
            >
              <Lightbulb size={12} className="mr-1 inline" aria-hidden />
              Generate hypotheses
            </button>
          </div>
        )}

        {state.phase === "loading" && (
          <p className="text-xs text-slate-600">
            <Activity size={12} className="mr-1 inline animate-pulse" aria-hidden />
            Drafting candidate explanations…
          </p>
        )}

        {state.phase === "error" && (
          <div className="flex items-start gap-2 text-sm text-red-700">
            <AlertTriangle size={16} className="mt-0.5 shrink-0" aria-hidden />
            <div>
              <p className="font-semibold">Couldn&apos;t generate hypotheses.</p>
              <p className="mt-0.5 text-xs text-red-600">{state.errorMessage}</p>
              <button
                type="button"
                onClick={() => run(true)}
                className="mt-2 inline-flex items-center gap-1 rounded border border-red-200 px-2 py-1 text-xs text-red-700 hover:bg-red-50"
              >
                <RefreshCw size={12} aria-hidden /> Try again
              </button>
            </div>
          </div>
        )}

        {hset && (
          <>
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                {hset.target_label}
              </p>
              <p className="mt-1 text-sm text-slate-800">{hset.pattern_summary}</p>
            </div>

            <div className="space-y-2">
              {hset.hypotheses.map((h, i) => (
                <HypothesisRow key={i} hypothesis={h} index={i + 1} />
              ))}
            </div>

            {hset.caveats.length > 0 && (
              <ul className="space-y-1 rounded-lg border border-amber-100 bg-amber-50/50 p-3 text-[11px] text-amber-900">
                {hset.caveats.map((c, i) => (
                  <li key={i} className="flex items-start gap-1.5">
                    <AlertTriangle size={12} className="mt-0.5 shrink-0" aria-hidden />
                    <span>{c}</span>
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </div>
    </section>
  );
}

function HypothesisRow({
  hypothesis,
  index,
}: {
  hypothesis: Hypothesis;
  index: number;
}) {
  const colour =
    hypothesis.confidence === "high"
      ? "border-emerald-200 bg-emerald-50/30"
      : hypothesis.confidence === "med"
      ? "border-amber-200 bg-amber-50/30"
      : "border-slate-200 bg-white";
  const pill =
    hypothesis.confidence === "high"
      ? "bg-emerald-100 text-emerald-700"
      : hypothesis.confidence === "med"
      ? "bg-amber-100 text-amber-800"
      : "bg-slate-100 text-slate-600";
  return (
    <details className={`group rounded-lg border px-3 py-2 ${colour}`}>
      <summary className="flex cursor-pointer list-none items-start gap-2 [&::-webkit-details-marker]:hidden">
        <ChevronRight
          size={14}
          className="mt-0.5 shrink-0 text-slate-400 group-open:hidden"
          aria-hidden
        />
        <ChevronDown
          size={14}
          className="mt-0.5 hidden shrink-0 text-slate-400 group-open:block"
          aria-hidden
        />
        <span className="text-[10px] font-mono text-slate-400">
          H{index}
        </span>
        <span className="flex-1 text-sm font-medium text-slate-800">
          {hypothesis.headline}
        </span>
        <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium ${pill}`}>
          {hypothesis.confidence}
        </span>
      </summary>

      <div className="mt-2 space-y-2 border-t border-slate-100 pt-2 text-xs text-slate-700">
        <div className="prose prose-sm max-w-none text-slate-700">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>
            {hypothesis.narrative}
          </ReactMarkdown>
        </div>

        {hypothesis.supporting_evidence.length > 0 && (
          <EvidenceBlock
            label="Supporting"
            icon={CheckCircle2}
            colour="text-emerald-700"
            items={hypothesis.supporting_evidence}
          />
        )}
        {hypothesis.contradicting_evidence.length > 0 && (
          <EvidenceBlock
            label="Contradicting"
            icon={XCircle}
            colour="text-rose-700"
            items={hypothesis.contradicting_evidence}
          />
        )}

        {hypothesis.falsifying_test && (
          <div className="rounded-md border border-slate-100 bg-slate-50/60 p-2">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">
              How to falsify
            </p>
            <p className="mt-1 text-[11px] text-slate-700">
              {hypothesis.falsifying_test}
            </p>
          </div>
        )}

        {hypothesis.next_data && (
          <p className="text-[11px] italic text-slate-600">
            <span className="font-medium not-italic">Outside data needed:</span>{" "}
            {hypothesis.next_data}
          </p>
        )}
      </div>
    </details>
  );
}

function EvidenceBlock({
  label,
  icon: Icon,
  colour,
  items,
}: {
  label: string;
  icon: typeof CheckCircle2;
  colour: string;
  items: string[];
}) {
  return (
    <div>
      <p className={`inline-flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider ${colour}`}>
        <Icon size={10} aria-hidden /> {label}
      </p>
      <ul className="mt-0.5 space-y-0.5 text-[11px] text-slate-700">
        {items.map((it, i) => (
          <li key={i}>
            <span className="text-slate-400">·</span> {it}
          </li>
        ))}
      </ul>
    </div>
  );
}
