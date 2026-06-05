"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  ChevronDown,
  ChevronRight,
  Sparkles,
  AlertTriangle,
  CheckCircle2,
  RefreshCw,
  Activity,
  TrendingUp,
  TrendingDown,
  Layers,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import {
  type AgentEvent,
  type CitedSignal,
  type PeriodShiftResponse,
  type PeriodMover,
  type PeriodCluster,
  type ToolTrace,
  probePeriodShift,
  streamPeriodShift,
} from "@/lib/agentApi";
import { BriefSkeleton, phaseFromStatus } from "./LoadingSkeleton";

interface PeriodShiftCardProps {
  /** Optional explicit period override; otherwise the backend picks the latest two. */
  period_b?: number;
  period_a?: number;
  defaultVerify?: "strict" | "fast" | "off";
}

interface LoadState {
  phase: "probing" | "needs_generation" | "streaming" | "ready" | "error";
  status?: string;
  toolCalls: ToolTrace[];
  verifierNotes: string[];
  response?: PeriodShiftResponse;
  errorMessage?: string;
  resolvedPeriods?: { period_a: number; period_b: number };
  availablePeriods?: number[];
}

/**
 * Corpus-wide period-shift diagnostic tile.
 *
 * Renders a streamed two-paragraph diagnostic that compares the latest
 * loaded period against the prior period. The body is followed by stacked
 * lane chips for the strongest risers/fallers and a cluster list. Each
 * lane chip links to the per-lane forensic page.
 */
export default function PeriodShiftCard({
  period_b,
  period_a,
  defaultVerify = "fast",
}: PeriodShiftCardProps) {
  // User-selected overrides (independent of the props so the dropdowns
  // re-probe without remounting the component).
  const [selectedA, setSelectedA] = useState<number | undefined>(period_a);
  const [selectedB, setSelectedB] = useState<number | undefined>(period_b);

  const [state, setState] = useState<LoadState>({
    phase: "probing",
    toolCalls: [],
    verifierNotes: [],
  });
  const abortRef = useRef<AbortController | null>(null);

  const run = (refresh = false) => {
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setState((prev) => ({
      ...prev,
      phase: "streaming",
      status: "Reading the corpus snapshot",
      toolCalls: [],
      verifierNotes: [],
    }));
    (async () => {
      try {
        for await (const ev of streamPeriodShift({
          period_a: selectedA,
          period_b: selectedB,
          verify: defaultVerify,
          refresh,
          signal: ctrl.signal,
        })) {
          setState((prev) => reduceEvent(prev, ev));
          if (ev.kind === "final_brief" || ev.kind === "error") break;
        }
      } catch (e) {
        if ((e as { name?: string }).name === "AbortError") return;
        setState({
          phase: "error",
          toolCalls: [],
          verifierNotes: [],
          errorMessage: e instanceof Error ? e.message : String(e),
        });
      }
    })();
  };

  useEffect(() => {
    let cancelled = false;
    setState({ phase: "probing", toolCalls: [], verifierNotes: [] });
    (async () => {
      try {
        const probe = await probePeriodShift({
          period_a: selectedA,
          period_b: selectedB,
        });
        if (cancelled) return;
        if (probe.cached) {
          setState({
            phase: "ready",
            toolCalls: [],
            verifierNotes: probe.response.brief.verifier_notes ?? [],
            response: probe.response,
            resolvedPeriods: {
              period_a: probe.response.brief.period_a,
              period_b: probe.response.brief.period_b,
            },
            availablePeriods: probe.available_periods,
          });
        } else {
          setState({
            phase: "needs_generation",
            toolCalls: [],
            verifierNotes: [],
            availablePeriods: probe.available_periods,
            resolvedPeriods: {
              period_a: probe.period_a,
              period_b: probe.period_b,
            },
          });
        }
      } catch (e) {
        if (cancelled) return;
        setState({ phase: "needs_generation", toolCalls: [], verifierNotes: [] });
        // eslint-disable-next-line no-console
        console.warn("PeriodShiftCard probe failed", e);
      }
    })();
    return () => {
      cancelled = true;
      abortRef.current?.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedA, selectedB]);

  const brief = state.response?.brief;
  const isLoading = state.phase === "streaming";
  const rp = state.resolvedPeriods;
  const available = state.availablePeriods ?? [];

  return (
    <section
      className={`rounded-2xl border bg-gradient-to-br shadow-sm transition ${
        state.phase === "error"
          ? "border-red-200 from-red-50/50 to-white"
          : "border-amber-200 from-amber-50/40 to-white"
      }`}
    >
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 px-5 py-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-amber-500 to-orange-600 text-white shadow-sm">
            <Sparkles size={14} strokeWidth={2.25} aria-hidden />
          </span>
          <span className="text-xs font-semibold uppercase tracking-wider text-orange-700">
            Period-shift diagnostic
          </span>
          {available.length >= 2 ? (
            <PeriodPicker
              available={available}
              valueA={rp?.period_a}
              valueB={rp?.period_b}
              disabled={isLoading}
              onChange={(a, b) => {
                setSelectedA(a);
                setSelectedB(b);
              }}
            />
          ) : (
            rp && (
              <span className="rounded-full border border-slate-200 bg-white px-2 py-0.5 font-mono text-[10px] text-slate-600">
                {rp.period_a} → {rp.period_b}
              </span>
            )
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
              streaming
            </span>
          )}
          {state.response && (
            <span
              title={`${state.response.tokens_in}→${state.response.tokens_out} tokens · $${state.response.cost_usd.toFixed(4)}`}
            >
              {state.response.model} · {state.response.latency_ms} ms
            </span>
          )}
          <button
            type="button"
            onClick={() => run(true)}
            disabled={isLoading}
            className="rounded p-1 text-slate-500 hover:bg-slate-100 hover:text-slate-700 disabled:opacity-40"
            title="Regenerate brief"
          >
            <RefreshCw size={12} aria-hidden />
          </button>
        </div>
      </div>

      <div className="space-y-4 px-5 py-4">
        {state.phase === "probing" && (
          <p className="flex items-center gap-2 text-xs text-slate-500">
            <Activity size={12} className="animate-pulse" aria-hidden />
            Checking the diagnostic cache…
          </p>
        )}

        {state.phase === "needs_generation" && (
          <div className="flex items-start justify-between gap-3">
            <div className="text-xs text-slate-600">
              <p className="font-medium text-slate-800">
                No diagnostic on file for{" "}
                {rp ? `${rp.period_a} → ${rp.period_b}` : "this comparison"} yet.
              </p>
              <p className="mt-1 text-[11px] text-slate-500">
                Generating runs the corpus-wide comparison, picks the strongest
                movers and clusters, and drafts the diagnostic. Cached after
                the first run.
              </p>
            </div>
            <button
              type="button"
              onClick={() => run(false)}
              className="shrink-0 rounded-lg bg-gradient-to-br from-amber-500 to-orange-600 px-3 py-1.5 text-xs font-semibold text-white shadow-sm hover:brightness-110"
            >
              <Sparkles size={12} className="mr-1 inline" aria-hidden />
              Generate diagnostic
            </button>
          </div>
        )}

        {state.phase === "streaming" && !brief && (
          <BriefSkeleton
            phase={phaseFromStatus(
              state.status,
              state.toolCalls.map((t) => t.name)
            )}
            toolCalls={state.toolCalls.map((t) => ({
              name: t.name,
              latency_ms: t.latency_ms,
            }))}
            status={
              state.toolCalls.length > 0
                ? `Step ${state.toolCalls.length}: ${
                    state.toolCalls[state.toolCalls.length - 1].name
                  }`
                : state.status ?? "Reading the corpus snapshot"
            }
          />
        )}

        {state.phase === "error" && (
          <div className="flex items-start gap-2 text-sm text-red-700">
            <AlertTriangle size={16} className="mt-0.5 shrink-0" aria-hidden />
            <div>
              <p className="font-semibold">Couldn&apos;t synthesise a diagnostic.</p>
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

        {brief && (
          <>
            <h2 className="text-base font-semibold text-slate-900">{brief.headline}</h2>

            <ConfidenceLine
              confidence={brief.confidence}
              cached={state.response?.cache_hit ?? false}
            />

            <div className="prose prose-sm df-prose max-w-none text-slate-700">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {brief.body_markdown}
              </ReactMarkdown>
            </div>

            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              <MoverColumn
                title="Top risers"
                icon={TrendingUp}
                colour="rose"
                movers={brief.top_risers}
              />
              <MoverColumn
                title="Top fallers"
                icon={TrendingDown}
                colour="emerald"
                movers={brief.top_fallers}
              />
            </div>

            {brief.emerging_clusters.length > 0 && (
              <ClusterList clusters={brief.emerging_clusters} />
            )}

            {brief.caveats.length > 0 && (
              <ul className="space-y-1 rounded-lg border border-amber-100 bg-amber-50/50 p-3 text-[11px] text-amber-900">
                {brief.caveats.map((c, i) => (
                  <li key={i} className="flex items-start gap-1.5">
                    <AlertTriangle size={12} className="mt-0.5 shrink-0" aria-hidden />
                    <span>{c}</span>
                  </li>
                ))}
              </ul>
            )}

            <Evidence
              signals={brief.key_signals}
              toolCalls={
                state.toolCalls.length > 0
                  ? state.toolCalls
                  : state.response?.tool_trace ?? []
              }
              verifierNotes={brief.verifier_notes}
            />
          </>
        )}
      </div>
    </section>
  );
}

/* ──────────────────────────────────────────────────────────────────── */
/* Reducer                                                              */
/* ──────────────────────────────────────────────────────────────────── */

function reduceEvent(prev: LoadState, ev: AgentEvent): LoadState {
  switch (ev.kind) {
    case "status":
      return { ...prev, status: ev.phase };
    case "tool_call":
      return {
        ...prev,
        status: `consulting ${ev.name}…`,
        toolCalls: [
          ...prev.toolCalls,
          { name: ev.name, args: ev.args, result: { ok: true }, latency_ms: ev.latency_ms },
        ],
      };
    case "tool_result": {
      const idx = [...prev.toolCalls]
        .map((t, i) => ({ t, i }))
        .reverse()
        .find((x) => x.t.name === ev.name)?.i;
      if (idx === undefined) return prev;
      const next = prev.toolCalls.slice();
      next[idx] = { ...next[idx], result: ev.result };
      return { ...prev, toolCalls: next };
    }
    case "verifier_note":
      return { ...prev, verifierNotes: [...prev.verifierNotes, ev.note] };
    case "final_brief": {
      const resp = ev.response as PeriodShiftResponse;
      if ("brief" in resp && "period_b" in resp) {
        return {
          ...prev,
          phase: "ready",
          status: undefined,
          response: resp,
          resolvedPeriods: {
            period_a: resp.period_a,
            period_b: resp.period_b,
          },
        };
      }
      return prev;
    }
    case "error":
      return {
        ...prev,
        phase: "error",
        status: undefined,
        errorMessage: ev.message,
      };
    default:
      return prev;
  }
}

/* ──────────────────────────────────────────────────────────────────── */
/* Sub-components                                                       */
/* ──────────────────────────────────────────────────────────────────── */

function PeriodPicker({
  available,
  valueA,
  valueB,
  disabled,
  onChange,
}: {
  available: number[];
  valueA?: number;
  valueB?: number;
  disabled: boolean;
  onChange: (a: number | undefined, b: number | undefined) => void;
}) {
  // Keep value rendering deterministic: if the current pick isn't in the
  // available list (e.g. the resolver fell back), show it anyway with a star.
  const renderOption = (y: number) => (
    <option key={y} value={y}>
      {y}
    </option>
  );

  const selA = valueA != null && available.includes(valueA) ? valueA : (valueA ?? "");
  const selB = valueB != null && available.includes(valueB) ? valueB : (valueB ?? "");

  return (
    <div className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white px-1.5 py-0.5">
      <select
        aria-label="Baseline year"
        title="Baseline year"
        disabled={disabled}
        className="rounded bg-transparent px-1 font-mono text-[10px] text-slate-700 focus:outline-none disabled:opacity-50"
        value={selA}
        onChange={(e) => onChange(parseInt(e.target.value), valueB)}
      >
        {available.map(renderOption)}
        {valueA != null && !available.includes(valueA) && (
          <option key="custom-a" value={valueA}>
            {valueA} *
          </option>
        )}
      </select>
      <span className="text-[10px] text-slate-400" aria-hidden>
        →
      </span>
      <select
        aria-label="Comparison year"
        title="Comparison year"
        disabled={disabled}
        className="rounded bg-transparent px-1 font-mono text-[10px] text-slate-700 focus:outline-none disabled:opacity-50"
        value={selB}
        onChange={(e) => onChange(valueA, parseInt(e.target.value))}
      >
        {available.map(renderOption)}
        {valueB != null && !available.includes(valueB) && (
          <option key="custom-b" value={valueB}>
            {valueB} *
          </option>
        )}
      </select>
    </div>
  );
}

function MoverColumn({
  title,
  icon: Icon,
  colour,
  movers,
}: {
  title: string;
  icon: typeof TrendingUp;
  colour: "rose" | "emerald";
  movers: PeriodMover[];
}) {
  if (movers.length === 0) {
    return (
      <div className="rounded-lg border border-slate-100 bg-slate-50/60 p-3 text-[11px] text-slate-500">
        <p className="mb-1 inline-flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
          <Icon size={11} aria-hidden /> {title}
        </p>
        <p>No movers in this category.</p>
      </div>
    );
  }
  const ring =
    colour === "rose"
      ? "border-rose-100 bg-rose-50/40"
      : "border-emerald-100 bg-emerald-50/40";
  const text = colour === "rose" ? "text-rose-700" : "text-emerald-700";
  const deltaSign = colour === "rose" ? "+" : "";
  return (
    <div className={`rounded-lg border p-3 ${ring}`}>
      <p
        className={`mb-2 inline-flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider ${text}`}
      >
        <Icon size={11} aria-hidden /> {title}
      </p>
      <ul className="space-y-2">
        {movers.map((m) => (
          <li key={m.lane_key} className="text-[11px]">
            <Link
              href={`/dashboard/corridors/${m.lane_key}`}
              className="block rounded border border-slate-200 bg-white p-2 hover:border-blue-300 hover:bg-blue-50"
            >
              <div className="flex items-baseline justify-between gap-2">
                <span className="font-medium text-slate-800">{m.label}</span>
                <span className={`font-mono text-[10px] ${text}`}>
                  {m.cvs_delta != null
                    ? `${deltaSign}${m.cvs_delta.toFixed(3)}`
                    : "—"}
                </span>
              </div>
              {m.explanation && (
                <p className="mt-1 text-[10px] text-slate-600">{m.explanation}</p>
              )}
              <p className="mt-1 font-mono text-[9px] text-slate-400">
                CVS {m.cvs_a?.toFixed(3) ?? "—"} → {m.cvs_b?.toFixed(3) ?? "—"}
                {m.notif_delta != null
                  ? ` · alerts ${m.notif_delta >= 0 ? "+" : ""}${m.notif_delta}`
                  : ""}
              </p>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}

function ClusterList({ clusters }: { clusters: PeriodCluster[] }) {
  return (
    <div className="rounded-lg border border-violet-100 bg-violet-50/40 p-3">
      <p className="mb-2 inline-flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-violet-700">
        <Layers size={11} aria-hidden /> Emerging clusters
      </p>
      <ul className="space-y-2">
        {clusters.map((c, i) => (
          <li key={i} className="rounded border border-slate-200 bg-white p-2 text-[11px]">
            <div className="flex items-baseline justify-between gap-2">
              <span className="font-medium text-slate-800">{c.cluster_label}</span>
              <span className="font-mono text-[10px] text-violet-700">
                {c.lane_count} lanes · {c.mean_movement >= 0 ? "+" : ""}
                {c.mean_movement.toFixed(3)}
              </span>
            </div>
            {c.explanation && (
              <p className="mt-1 text-[10px] text-slate-600">{c.explanation}</p>
            )}
            {c.lane_keys.length > 0 && (
              <div className="mt-1.5 flex flex-wrap gap-1">
                {c.lane_keys.map((k) => (
                  <Link
                    key={k}
                    href={`/dashboard/corridors/${k}`}
                    className="rounded border border-slate-200 bg-slate-50 px-1.5 py-0.5 font-mono text-[9px] text-slate-600 hover:bg-blue-50 hover:text-blue-700"
                  >
                    {k}
                  </Link>
                ))}
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

function ConfidenceLine({
  confidence,
  cached,
}: {
  confidence: "low" | "med" | "high";
  cached: boolean;
}) {
  const colour =
    confidence === "high"
      ? "text-emerald-700 bg-emerald-100"
      : confidence === "med"
      ? "text-amber-700 bg-amber-100"
      : "text-slate-600 bg-slate-100";
  const Icon = confidence === "low" ? AlertTriangle : CheckCircle2;
  return (
    <div className="flex items-center gap-2 text-[11px]">
      <span
        className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 font-medium ${colour}`}
      >
        <Icon size={11} aria-hidden /> Confidence: {confidence}
      </span>
      {cached && <span className="text-slate-500">Reused from snapshot cache.</span>}
    </div>
  );
}

function Evidence({
  signals,
  toolCalls,
  verifierNotes,
}: {
  signals: CitedSignal[];
  toolCalls: ToolTrace[];
  verifierNotes: string[];
}) {
  return (
    <details className="group rounded-lg border border-slate-100 bg-slate-50/70">
      <summary className="flex cursor-pointer list-none items-center gap-1.5 px-3 py-2 text-[11px] font-semibold text-slate-700 [&::-webkit-details-marker]:hidden">
        <ChevronRight size={12} className="text-slate-500 group-open:hidden" aria-hidden />
        <ChevronDown size={12} className="hidden text-slate-500 group-open:block" aria-hidden />
        Show evidence ({signals.length} signal{signals.length === 1 ? "" : "s"} ·{" "}
        {toolCalls.length} tool call{toolCalls.length === 1 ? "" : "s"})
      </summary>

      <div className="space-y-3 border-t border-slate-200 px-3 py-3 text-[11px] text-slate-700">
        <div>
          <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
            Cited signals
          </p>
          <table className="w-full">
            <thead>
              <tr className="text-[10px] uppercase tracking-wider text-slate-500">
                <th className="text-left font-medium">Name</th>
                <th className="text-left font-medium">Field</th>
                <th className="text-right font-medium">Value</th>
              </tr>
            </thead>
            <tbody>
              {signals.map((s, i) => (
                <tr key={i} className="border-t border-slate-100">
                  <td className="py-1 pr-2">{s.name}</td>
                  <td className="py-1 pr-2 font-mono text-[10px] text-slate-500">
                    {s.source_field}
                  </td>
                  <td className="py-1 text-right font-mono">
                    {s.value === null ? "—" : String(s.value)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {toolCalls.length > 0 && (
          <div>
            <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
              Tool trace
            </p>
            <ul className="space-y-1 font-mono text-[10px] text-slate-600">
              {toolCalls.map((t, i) => (
                <li key={i}>
                  <span className="text-slate-400">{String(i + 1).padStart(2, "0")}</span>{" "}
                  {t.name}
                  <span className="text-slate-400"> · {t.latency_ms} ms</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {verifierNotes.length > 0 && (
          <div>
            <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
              Verifier notes
            </p>
            <ul className="space-y-0.5 text-[10px] text-amber-900">
              {verifierNotes.map((n, i) => (
                <li key={i}>· {n}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </details>
  );
}
