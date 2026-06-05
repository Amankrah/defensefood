"use client";

import { useEffect, useRef, useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  Sparkles,
  AlertTriangle,
  CheckCircle2,
  RefreshCw,
  Activity,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import {
  type AgentEvent,
  type CitedSignal,
  type LaneBriefResponse,
  type ToolTrace,
  probeLaneBrief,
  streamLaneBrief,
} from "@/lib/agentApi";
import { BriefSkeleton, phaseFromStatus } from "./LoadingSkeleton";

interface BriefCardProps {
  /** Corridor identity. */
  commodity_hs: string;
  destination_m49: number;
  origin_m49: number;
  /** Default verify mode passed to the agent endpoint. */
  defaultVerify?: "strict" | "fast" | "off";
}

interface LoadState {
  phase: "probing" | "needs_generation" | "streaming" | "ready" | "error";
  status?: string;
  toolCalls: ToolTrace[];
  verifierNotes: string[];
  response?: LaneBriefResponse;
  errorMessage?: string;
}

/**
 * Lane forensic AI brief tile.
 *
 * Renders the streamed brief at the top of the Lane forensic report. Shows
 * progress while the agent runs (tool calls, verifier notes), then the brief
 * markdown plus a collapsible "Show evidence" panel with the cited signals
 * and the tool trace.
 */
export default function BriefCard({
  commodity_hs,
  destination_m49,
  origin_m49,
  defaultVerify = "fast",
}: BriefCardProps) {
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
    setState({
      phase: "streaming",
      status: "Consulting the engine…",
      toolCalls: [],
      verifierNotes: [],
    });
    (async () => {
      try {
        for await (const ev of streamLaneBrief(
          commodity_hs,
          destination_m49,
          origin_m49,
          { verify: defaultVerify, refresh, signal: ctrl.signal }
        )) {
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

  // Mount: cheap cache probe. Only render a stored brief automatically.
  // Generation requires the explicit Generate button to control cost.
  useEffect(() => {
    let cancelled = false;
    setState({ phase: "probing", toolCalls: [], verifierNotes: [] });
    (async () => {
      try {
        const probe = await probeLaneBrief(
          commodity_hs,
          destination_m49,
          origin_m49
        );
        if (cancelled) return;
        if (probe.cached) {
          setState({
            phase: "ready",
            toolCalls: [],
            verifierNotes: probe.response.brief.verifier_notes ?? [],
            response: probe.response,
          });
        } else {
          setState({ phase: "needs_generation", toolCalls: [], verifierNotes: [] });
        }
      } catch (e) {
        if (cancelled) return;
        // Probe failure is non-fatal; treat as "needs generation" so the user
        // can still try. Surface the message only if generation also fails.
        setState({ phase: "needs_generation", toolCalls: [], verifierNotes: [] });
        // eslint-disable-next-line no-console
        console.warn("BriefCard probe failed", e);
      }
    })();
    return () => {
      cancelled = true;
      abortRef.current?.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [commodity_hs, destination_m49, origin_m49]);

  const brief = state.response?.brief;
  const isLoading = state.phase === "streaming";

  return (
    <section
      className={`rounded-2xl border bg-gradient-to-br shadow-sm transition ${
        state.phase === "error"
          ? "border-red-200 from-red-50/50 to-white"
          : "border-blue-200 from-blue-50/50 to-white"
      }`}
    >
      {/* Header row */}
      <div className="flex items-start justify-between gap-3 border-b border-slate-100 px-5 py-3">
        <div className="flex items-center gap-2">
          <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-blue-600 to-indigo-600 text-white shadow-sm">
            <Sparkles size={14} strokeWidth={2.25} aria-hidden />
          </span>
          <span className="text-xs font-semibold uppercase tracking-wider text-blue-700">
            AI forensic brief
          </span>
          {state.response?.cache_hit && (
            <span className="ml-1 rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-600">
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
            <span title={`${state.response.tokens_in}→${state.response.tokens_out} tokens · $${state.response.cost_usd.toFixed(4)}`}>
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

      {/* Body */}
      <div className="space-y-3 px-5 py-4">
        {state.phase === "probing" && (
          <p className="flex items-center gap-2 text-xs text-slate-500">
            <Activity size={12} className="animate-pulse" aria-hidden />
            Checking the brief cache…
          </p>
        )}

        {state.phase === "needs_generation" && (
          <div className="flex items-start justify-between gap-3">
            <div className="text-xs text-slate-600">
              <p className="font-medium text-slate-800">
                No brief on file for this lane yet.
              </p>
              <p className="mt-1 text-[11px] text-slate-500">
                Generating a brief calls the AI subsystem (typical cost a
                fraction of a cent, takes 5 to 15 seconds). Stored after the
                first run so re-visits are free.
              </p>
            </div>
            <button
              type="button"
              onClick={() => run(false)}
              className="shrink-0 rounded-lg bg-gradient-to-br from-blue-600 to-indigo-600 px-3 py-1.5 text-xs font-semibold text-white shadow-sm hover:brightness-110"
            >
              <Sparkles size={12} className="mr-1 inline" aria-hidden />
              Generate brief
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
                : state.status ?? "Reading the engine snapshot"
            }
          />
        )}

        {state.phase === "error" && (
          <div className="flex items-start gap-2 text-sm text-red-700">
            <AlertTriangle size={16} className="mt-0.5 shrink-0" aria-hidden />
            <div>
              <p className="font-semibold">Couldn&apos;t synthesise a brief.</p>
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
            <h2 className="text-base font-semibold text-slate-900">
              {brief.headline}
            </h2>

            <ConfidenceLine
              confidence={brief.confidence}
              cached={state.response?.cache_hit ?? false}
            />

            <div className="prose prose-sm max-w-none text-slate-700">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {brief.body_markdown}
              </ReactMarkdown>
            </div>

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
              toolCalls={state.toolCalls.length > 0 ? state.toolCalls : state.response?.tool_trace ?? []}
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
      // Attach the result to the most recent tool call of that name.
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
    case "final_brief":
      return {
        ...prev,
        phase: "ready",
        status: undefined,
        response: ev.response as LaneBriefResponse,
      };
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
      {cached && (
        <span className="text-slate-500">
          Brief reused from snapshot cache. Click ↻ to regenerate.
        </span>
      )}
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
        Show evidence ({signals.length} signal{signals.length === 1 ? "" : "s"} · {toolCalls.length} tool call
        {toolCalls.length === 1 ? "" : "s"})
      </summary>

      <div className="space-y-3 border-t border-slate-200 px-3 py-3 text-[11px] text-slate-700">
        {/* Signals table */}
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
                  <td className="py-1">
                    <BandPill band={s.band} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Tool trace */}
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
                  {t.result.ok === false && (
                    <span className="ml-1 text-red-600">err: {t.result.error}</span>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Verifier notes */}
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

function BandPill({ band }: { band: CitedSignal["band"] }) {
  const colour: Record<CitedSignal["band"], string> = {
    low: "bg-emerald-100 text-emerald-700",
    med: "bg-amber-100 text-amber-800",
    high: "bg-rose-100 text-rose-700",
    flag: "bg-purple-100 text-purple-700",
    unknown: "bg-slate-100 text-slate-600",
  };
  return (
    <span
      className={`inline-block rounded px-1.5 py-0.5 text-[10px] font-medium ${colour[band]}`}
    >
      {band}
    </span>
  );
}
