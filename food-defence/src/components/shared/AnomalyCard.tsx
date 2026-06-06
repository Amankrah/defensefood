"use client";

import { useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  Activity,
  RefreshCw,
  ShieldQuestion,
  ChevronDown,
  ChevronRight,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import {
  type AnomalyResponse,
  type AnomalyVerdict,
  type CitedSignal,
  fetchAnomalyExplanation,
  probeAnomaly,
} from "@/lib/agentApi";
import { BriefSkeleton, useTimedBriefPhase } from "./LoadingSkeleton";

interface Props {
  commodity_hs: string;
  destination_m49: number;
  origin_m49: number;
}

interface LoadState {
  phase: "probing" | "needs_generation" | "loading" | "ready" | "error";
  response?: AnomalyResponse;
  errorMessage?: string;
}

const VERDICT_STYLE: Record<
  AnomalyVerdict,
  { label: string; pill: string; tone: string }
> = {
  anomalous: {
    label: "Anomalous",
    pill: "bg-rose-100 text-rose-700",
    tone: "border-rose-200 from-rose-50/40 to-white",
  },
  borderline: {
    label: "Borderline",
    pill: "bg-amber-100 text-amber-800",
    tone: "border-amber-200 from-amber-50/30 to-white",
  },
  not_anomalous: {
    label: "Not anomalous",
    pill: "bg-emerald-100 text-emerald-700",
    tone: "border-emerald-200 from-emerald-50/30 to-white",
  },
};

/**
 * Anomaly explainer tile for the lane forensic page.
 *
 * Lives below the AI brief and the hypotheses. Renders the verdict
 * (anomalous / borderline / not_anomalous) plus the agent's "why" and
 * "why not" paragraphs, supporting signals, and a peer comparison.
 */
export default function AnomalyCard({
  commodity_hs,
  destination_m49,
  origin_m49,
}: Props) {
  const [state, setState] = useState<LoadState>({ phase: "probing" });
  const cancelRef = useRef<boolean>(false);

  const run = async (refresh: boolean) => {
    setState({ phase: "loading" });
    try {
      const r = await fetchAnomalyExplanation(
        commodity_hs,
        destination_m49,
        origin_m49,
        { refresh }
      );
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
        const p = await probeAnomaly(commodity_hs, destination_m49, origin_m49);
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
        console.warn("AnomalyCard probe failed", e);
      }
    })();
    return () => {
      cancelRef.current = true;
    };
  }, [commodity_hs, destination_m49, origin_m49]);

  const expl = state.response?.explanation;
  const verdictStyle = expl ? VERDICT_STYLE[expl.verdict] : VERDICT_STYLE.borderline;
  const isLoading = state.phase === "loading";
  // Anomaly check usually lands in 30 to 90 seconds; faster timer than
  // hypotheses since the schema is simpler and the verdict converges quickly.
  const livePhase = useTimedBriefPhase(isLoading, {
    drafting: 3_000,
    verifying: 35_000,
    finalising: 65_000,
  });

  return (
    <section
      className={`rounded-2xl border bg-gradient-to-br shadow-sm ${
        state.phase === "error"
          ? "border-red-200 from-red-50/40 to-white"
          : expl
          ? verdictStyle.tone
          : "border-slate-200 from-slate-50/30 to-white"
      }`}
    >
      <div className="flex items-center justify-between gap-3 border-b border-slate-100 px-5 py-3">
        <div className="flex items-center gap-2">
          <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-slate-600 to-slate-800 text-white shadow-sm">
            <ShieldQuestion size={14} strokeWidth={2.25} aria-hidden />
          </span>
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-700">
            Anomaly check
          </span>
          {expl && (
            <span
              className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${verdictStyle.pill}`}
            >
              {verdictStyle.label}
            </span>
          )}
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
              checking
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
              title="Re-run anomaly check"
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
            Checking the anomaly cache…
          </p>
        )}

        {state.phase === "needs_generation" && (
          <div className="flex items-start justify-between gap-3">
            <div className="text-xs text-slate-600">
              <p className="font-medium text-slate-800">
                No anomaly check on file yet.
              </p>
              <p className="mt-1 text-[11px] text-slate-500">
                The agent looks at multi-period drift, hazard cadence, and
                peer lanes in the same chapter and role, then renders a
                verdict with both supporting and counter-evidence.
              </p>
            </div>
            <button
              type="button"
              onClick={() => run(false)}
              className="shrink-0 rounded-lg bg-gradient-to-br from-slate-700 to-slate-900 px-3 py-1.5 text-xs font-semibold text-white shadow-sm hover:brightness-110"
            >
              <ShieldQuestion size={12} className="mr-1 inline" aria-hidden />
              Run check
            </button>
          </div>
        )}

        {state.phase === "loading" && (
          <BriefSkeleton
            phase={livePhase}
            toolCalls={[]}
            variant="anomaly"
            status={
              livePhase === "reading"
                ? "Reading lane profile and peer behaviour"
                : livePhase === "drafting"
                ? "Weighing anomaly evidence on both sides"
                : livePhase === "verifying"
                ? "Cross-checking peers and per-period drift"
                : "Polishing the final read"
            }
          />
        )}

        {state.phase === "error" && (
          <div className="flex items-start gap-2 text-sm text-red-700">
            <AlertTriangle size={16} className="mt-0.5 shrink-0" aria-hidden />
            <div>
              <p className="font-semibold">Couldn&apos;t run the anomaly check.</p>
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

        {expl && (
          <>
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                {expl.target_label}
              </p>
              <h3 className="mt-1 text-base font-semibold text-slate-900">
                {expl.headline}
              </h3>
            </div>

            <Section title="Why this stands out" body={expl.why_anomalous} />
            {expl.why_not && expl.why_not.trim().length > 0 && (
              <Section title="What would convince me otherwise" body={expl.why_not} />
            )}
            {expl.peer_comparison && expl.peer_comparison.trim().length > 0 && (
              <p className="rounded-md border border-slate-100 bg-slate-50/60 px-3 py-2 text-[11px] text-slate-700">
                <span className="font-semibold">Peer comparison: </span>
                {expl.peer_comparison}
              </p>
            )}

            {expl.caveats.length > 0 && (
              <ul className="space-y-1 rounded-lg border border-amber-100 bg-amber-50/40 p-3 text-[11px] text-amber-900">
                {expl.caveats.map((c, i) => (
                  <li key={i} className="flex items-start gap-1.5">
                    <AlertTriangle size={12} className="mt-0.5 shrink-0" aria-hidden />
                    <span>{c}</span>
                  </li>
                ))}
              </ul>
            )}

            {expl.supporting_signals.length > 0 && (
              <SignalsExpander signals={expl.supporting_signals} />
            )}
          </>
        )}
      </div>
    </section>
  );
}

function Section({ title, body }: { title: string; body: string }) {
  return (
    <div>
      <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">
        {title}
      </p>
      <div className="prose prose-sm mt-1 max-w-none text-slate-700">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{body}</ReactMarkdown>
      </div>
    </div>
  );
}

function SignalsExpander({ signals }: { signals: CitedSignal[] }) {
  return (
    <details className="group rounded-lg border border-slate-100 bg-slate-50/60">
      <summary className="flex cursor-pointer list-none items-center gap-1.5 px-3 py-2 text-[11px] font-semibold text-slate-700 [&::-webkit-details-marker]:hidden">
        <ChevronRight size={12} className="text-slate-500 group-open:hidden" aria-hidden />
        <ChevronDown size={12} className="hidden text-slate-500 group-open:block" aria-hidden />
        Supporting signals ({signals.length})
      </summary>
      <div className="border-t border-slate-200 px-3 py-2">
        <table className="w-full text-[11px]">
          <thead>
            <tr className="text-[10px] uppercase tracking-wider text-slate-500">
              <th className="text-left font-medium">Name</th>
              <th className="text-left font-medium">Field</th>
              <th className="text-right font-medium">Value</th>
              <th className="text-left font-medium">Band</th>
            </tr>
          </thead>
          <tbody>
            {signals.map((s, i) => (
              <tr key={i} className="border-t border-slate-100">
                <td className="py-1 pr-2">{s.name}</td>
                <td className="py-1 pr-2 font-mono text-[10px] text-slate-500">
                  {s.source_field}
                </td>
                <td className="py-1 pr-2 text-right font-mono">
                  {s.value === null ? "—" : String(s.value)}
                </td>
                <td className="py-1 font-mono text-[10px] text-slate-600">{s.band}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}
