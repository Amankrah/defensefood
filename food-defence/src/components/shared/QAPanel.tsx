"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Activity,
  Send,
  Sparkles,
  XCircle,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import {
  type CitedSignal,
  type IntentClassification,
  type QAEvent,
  type QAResultResponse,
  type QAStructuredData,
  type QATurn,
  type ToolTrace,
  streamQA,
} from "@/lib/agentApi";

const STARTER_PROMPTS: string[] = [
  "Show corridors where Composite Vulnerability Score (CVS) is in the top band.",
  "Which lanes had the biggest Origin Concentration Share (OCS) shift between 2022 and 2023?",
  "Compare Spain and Italy as origins of food fraud exposure.",
  "Why is the top corridor scored so high?",
  "How is the Composite Vulnerability Score (CVS) computed?",
  "Find lanes where Import Dependency Ratio (IDR) is above 1 and Hazard Intensity Score (HIS) is in the high band.",
];

interface ChatMessage {
  role: "user" | "assistant" | "system";
  // For user messages: the query string. For assistant: the QATurn shape.
  text?: string;
  turn?: QATurn;
  classification?: IntentClassification;
  refused?: boolean;
  toolTrace?: ToolTrace[];
  meta?: {
    model: string;
    latency_ms: number;
    cost_usd: number;
    tokens_in: number;
    tokens_out: number;
  };
}

interface InFlight {
  query: string;
  phase: "routing" | "tools" | "composing" | "done";
  status: string;
  classification?: IntentClassification;
  toolCalls: ToolTrace[];
  verifierNotes: string[];
}

interface PanelState {
  conversationId: string | null;
  messages: ChatMessage[];
  inFlight: InFlight | null;
  errorMessage: string | null;
}

/**
 * Conversational Q&A workbench panel.
 *
 * Chat-style UI over POST /api/v1/agent/qa. Each turn:
 *
 * 1. User types a question (or picks a starter chip).
 * 2. The router classifies it. Out-of-scope queries refuse with a grey
 *    chip and a one-line reason.
 * 3. In-scope queries stream tool calls and the final answer markdown.
 *    Filter / compare answers may carry a structured_data block which
 *    renders as a sortable table beneath the prose.
 * 4. The trace expander shows the intent classification + every tool
 *    call's arguments and result.
 */
export default function QAPanel() {
  const [state, setState] = useState<PanelState>({
    conversationId: null,
    messages: [],
    inFlight: null,
    errorMessage: null,
  });
  const [input, setInput] = useState("");
  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [state.messages, state.inFlight]);

  const submitQuery = (q: string) => {
    const trimmed = q.trim();
    if (!trimmed || state.inFlight) return;
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    setState((prev) => ({
      ...prev,
      messages: [...prev.messages, { role: "user", text: trimmed }],
      inFlight: {
        query: trimmed,
        phase: "routing",
        status: "Routing the question",
        toolCalls: [],
        verifierNotes: [],
      },
      errorMessage: null,
    }));
    setInput("");

    (async () => {
      try {
        for await (const ev of streamQA(trimmed, {
          conversation_id: state.conversationId ?? undefined,
          signal: ctrl.signal,
        })) {
          setState((prev) => reduceEvent(prev, ev));
          if (ev.kind === "final_answer" || ev.kind === "error") break;
        }
      } catch (e) {
        if ((e as { name?: string }).name === "AbortError") return;
        setState((prev) => ({
          ...prev,
          inFlight: null,
          errorMessage: e instanceof Error ? e.message : String(e),
        }));
      }
    })();
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submitQuery(input);
    }
  };

  return (
    <div className="flex h-[calc(100vh-12rem)] min-h-[420px] flex-col rounded-2xl border border-slate-200 bg-white shadow-sm">
      {/* Transcript */}
      <div
        ref={scrollRef}
        className="flex-1 space-y-4 overflow-y-auto px-5 py-4"
      >
        {state.messages.length === 0 && !state.inFlight && (
          <StarterChips onPick={submitQuery} />
        )}

        {state.messages.map((m, i) => (
          <ChatBubble key={i} message={m} />
        ))}

        {state.inFlight && <InFlightBubble live={state.inFlight} />}

        {state.errorMessage && (
          <div className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
            <AlertTriangle size={14} className="mt-0.5 shrink-0" aria-hidden />
            <span>{state.errorMessage}</span>
          </div>
        )}
      </div>

      {/* Composer */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          submitQuery(input);
        }}
        className="border-t border-slate-100 px-4 py-3"
      >
        <div className="flex items-end gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKeyDown}
            disabled={!!state.inFlight}
            rows={1}
            placeholder="Ask a research question…"
            className="flex-1 resize-none rounded-lg border border-slate-200 px-3 py-2 text-sm placeholder:text-slate-400 focus:border-blue-400 focus:outline-none disabled:bg-slate-50"
          />
          <button
            type="submit"
            disabled={!!state.inFlight || !input.trim()}
            className="inline-flex items-center gap-1.5 rounded-lg bg-gradient-to-br from-blue-600 to-indigo-600 px-3 py-2 text-xs font-semibold text-white shadow-sm hover:brightness-110 disabled:opacity-40"
          >
            <Send size={12} aria-hidden /> Ask
          </button>
        </div>
        <p className="mt-1.5 text-[10px] text-slate-400">
          Streams via Server-Sent Events. Out-of-scope questions get a graceful
          refusal without spending Sonnet tokens.
        </p>
      </form>
    </div>
  );
}

/* ──────────────────────────────────────────────────────────────────── */
/* Reducer                                                              */
/* ──────────────────────────────────────────────────────────────────── */

function reduceEvent(prev: PanelState, ev: QAEvent): PanelState {
  switch (ev.kind) {
    case "status": {
      const next = { ...prev };
      if (next.inFlight) {
        next.inFlight = {
          ...next.inFlight,
          phase: "routing",
          status: ev.phase === "routing" ? "Routing the question" : ev.phase,
        };
      }
      if (ev.conversation_id) next.conversationId = ev.conversation_id;
      return next;
    }
    case "intent": {
      if (!prev.inFlight) return prev;
      const cls = ev.classification;
      const phase = cls.in_scope ? "tools" : "done";
      return {
        ...prev,
        inFlight: {
          ...prev.inFlight,
          phase,
          status: cls.in_scope
            ? `Intent: ${cls.intent}; gathering evidence`
            : "Out of scope",
          classification: cls,
        },
      };
    }
    case "tool_call": {
      if (!prev.inFlight) return prev;
      return {
        ...prev,
        inFlight: {
          ...prev.inFlight,
          status: `Calling ${ev.name}`,
          toolCalls: [
            ...prev.inFlight.toolCalls,
            {
              name: ev.name,
              args: ev.args,
              result: { ok: true },
              latency_ms: ev.latency_ms,
            },
          ],
        },
      };
    }
    case "tool_result": {
      if (!prev.inFlight) return prev;
      const idx = [...prev.inFlight.toolCalls]
        .map((t, i) => ({ t, i }))
        .reverse()
        .find((x) => x.t.name === ev.name)?.i;
      if (idx === undefined) return prev;
      const nextCalls = prev.inFlight.toolCalls.slice();
      nextCalls[idx] = { ...nextCalls[idx], result: ev.result };
      return {
        ...prev,
        inFlight: { ...prev.inFlight, toolCalls: nextCalls },
      };
    }
    case "verifier_note": {
      if (!prev.inFlight) return prev;
      return {
        ...prev,
        inFlight: {
          ...prev.inFlight,
          verifierNotes: [...prev.inFlight.verifierNotes, ev.note],
        },
      };
    }
    case "final_answer": {
      const r = ev.response;
      const msg: ChatMessage = {
        role: "assistant",
        turn: r.turn,
        classification: r.classification,
        refused: r.refused,
        toolTrace: r.tool_trace,
        meta: {
          model: r.model,
          latency_ms: r.latency_ms,
          cost_usd: r.cost_usd,
          tokens_in: r.tokens_in,
          tokens_out: r.tokens_out,
        },
      };
      return {
        ...prev,
        conversationId: r.conversation_id,
        messages: [...prev.messages, msg],
        inFlight: null,
      };
    }
    case "error":
      return {
        ...prev,
        inFlight: null,
        errorMessage: ev.message,
      };
    default:
      return prev;
  }
}

/* ──────────────────────────────────────────────────────────────────── */
/* Sub-components                                                       */
/* ──────────────────────────────────────────────────────────────────── */

function StarterChips({ onPick }: { onPick: (q: string) => void }) {
  return (
    <div>
      <p className="mb-2 inline-flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-blue-600">
        <Sparkles size={11} aria-hidden /> Start with one of these
      </p>
      <div className="flex flex-col gap-1.5">
        {STARTER_PROMPTS.map((p) => (
          <button
            key={p}
            type="button"
            onClick={() => onPick(p)}
            className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-left text-xs text-slate-700 hover:border-blue-300 hover:bg-blue-50 hover:text-blue-900"
          >
            {p}
          </button>
        ))}
      </div>
    </div>
  );
}

function ChatBubble({ message }: { message: ChatMessage }) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] rounded-2xl rounded-tr-md bg-gradient-to-br from-blue-600 to-indigo-600 px-3 py-2 text-sm text-white shadow-sm">
          {message.text}
        </div>
      </div>
    );
  }

  // Assistant.
  const refused = message.refused === true;
  const turn = message.turn;
  if (!turn) return null;

  return (
    <div className="flex justify-start">
      <div
        className={`max-w-[88%] space-y-2 rounded-2xl rounded-tl-md border px-3 py-2 text-sm shadow-sm ${
          refused
            ? "border-slate-200 bg-slate-50 text-slate-700"
            : "border-slate-200 bg-white text-slate-800"
        }`}
      >
        {refused && (
          <p className="inline-flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
            <XCircle size={11} aria-hidden /> Out of scope
          </p>
        )}
        {!refused && message.classification && (
          <p className="inline-flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-blue-600">
            <Sparkles size={11} aria-hidden /> Intent: {message.classification.intent}
          </p>
        )}

        <div className="prose prose-sm max-w-none text-slate-800">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>
            {turn.answer_markdown}
          </ReactMarkdown>
        </div>

        {turn.structured_data && (
          <StructuredDataTable data={turn.structured_data} />
        )}

        {turn.caveats.length > 0 && (
          <ul className="space-y-1 rounded-lg border border-amber-100 bg-amber-50/40 p-2 text-[10px] text-amber-900">
            {turn.caveats.map((c, i) => (
              <li key={i} className="flex items-start gap-1.5">
                <AlertTriangle size={10} className="mt-0.5 shrink-0" aria-hidden />
                <span>{c}</span>
              </li>
            ))}
          </ul>
        )}

        <ConfidenceLine confidence={turn.confidence} />

        {message.meta && (
          <p className="text-[10px] text-slate-400">
            {message.meta.latency_ms} ms · ${message.meta.cost_usd.toFixed(4)}
          </p>
        )}

        {(turn.key_signals.length > 0 || (message.toolTrace?.length ?? 0) > 0) && (
          <Evidence
            signals={turn.key_signals}
            toolCalls={message.toolTrace ?? []}
            verifierNotes={turn.verifier_notes}
            classification={message.classification}
          />
        )}
      </div>
    </div>
  );
}

function InFlightBubble({ live }: { live: InFlight }) {
  return (
    <div className="flex justify-start">
      <div className="max-w-[88%] space-y-2 rounded-2xl rounded-tl-md border border-slate-200 bg-white px-3 py-2 text-xs text-slate-600 shadow-sm">
        <p className="inline-flex items-center gap-1.5 font-medium text-slate-700">
          <Activity size={12} className="animate-pulse" aria-hidden />
          {live.status}
        </p>
        {live.classification && (
          <p className="text-[10px] text-slate-500">
            Intent classified as <span className="font-medium">{live.classification.intent}</span>
            {live.classification.in_scope ? "" : " (out of scope)"}
          </p>
        )}
        {live.toolCalls.length > 0 && (
          <ul className="space-y-0.5 font-mono text-[10px] text-slate-500">
            {live.toolCalls.map((t, i) => (
              <li key={i}>
                <span className="text-slate-400">→</span> {t.name}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function ConfidenceLine({ confidence }: { confidence: "low" | "med" | "high" }) {
  const colour =
    confidence === "high"
      ? "text-emerald-700 bg-emerald-100"
      : confidence === "med"
      ? "text-amber-700 bg-amber-100"
      : "text-slate-600 bg-slate-100";
  const Icon = confidence === "low" ? AlertTriangle : CheckCircle2;
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium ${colour}`}
    >
      <Icon size={10} aria-hidden /> Confidence: {confidence}
    </span>
  );
}

function StructuredDataTable({ data }: { data: QAStructuredData }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50/60 p-2">
      <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
        {data.title}
      </p>
      <div className="overflow-x-auto">
        <table className="w-full text-[11px]">
          <thead>
            <tr className="text-[10px] uppercase tracking-wider text-slate-500">
              {data.columns.map((c) => (
                <th
                  key={c.key}
                  className={
                    c.align === "right" ? "py-1 text-right font-medium" : "py-1 text-left font-medium"
                  }
                >
                  {c.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.rows.map((row, i) => {
              const lane_key = data.lane_keys[i];
              return (
                <tr key={i} className="border-t border-slate-100">
                  {data.columns.map((c) => {
                    const cell = row[c.key];
                    const txt = cell == null ? "—" : String(cell);
                    return (
                      <td
                        key={c.key}
                        className={
                          c.align === "right"
                            ? "py-1 pr-2 text-right font-mono"
                            : "py-1 pr-2"
                        }
                      >
                        {c.key === "lane" && lane_key ? (
                          <Link
                            href={`/dashboard/corridors/${lane_key}`}
                            className="text-blue-700 hover:underline"
                          >
                            {txt}
                          </Link>
                        ) : (
                          txt
                        )}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Evidence({
  signals,
  toolCalls,
  verifierNotes,
  classification,
}: {
  signals: CitedSignal[];
  toolCalls: ToolTrace[];
  verifierNotes: string[];
  classification?: IntentClassification;
}) {
  return (
    <details className="group rounded-lg border border-slate-100 bg-slate-50/60">
      <summary className="flex cursor-pointer list-none items-center gap-1.5 px-2 py-1.5 text-[10px] font-semibold text-slate-700 [&::-webkit-details-marker]:hidden">
        <ChevronRight size={11} className="text-slate-500 group-open:hidden" aria-hidden />
        <ChevronDown size={11} className="hidden text-slate-500 group-open:block" aria-hidden />
        Show trace ({signals.length} signal{signals.length === 1 ? "" : "s"} ·{" "}
        {toolCalls.length} tool call{toolCalls.length === 1 ? "" : "s"})
      </summary>
      <div className="space-y-2 border-t border-slate-200 px-2 py-2 text-[10px] text-slate-700">
        {classification && (
          <div>
            <p className="text-[9px] font-semibold uppercase tracking-wider text-slate-500">
              Routing
            </p>
            <p className="font-mono text-[9px] text-slate-600">
              intent={classification.intent} · in_scope={String(classification.in_scope)}
            </p>
          </div>
        )}
        {signals.length > 0 && (
          <table className="w-full">
            <thead>
              <tr className="text-[9px] uppercase tracking-wider text-slate-500">
                <th className="text-left font-medium">Name</th>
                <th className="text-left font-medium">Field</th>
                <th className="text-right font-medium">Value</th>
              </tr>
            </thead>
            <tbody>
              {signals.map((s, i) => (
                <tr key={i} className="border-t border-slate-100">
                  <td className="py-0.5 pr-2">{s.name}</td>
                  <td className="py-0.5 pr-2 font-mono text-[9px] text-slate-500">
                    {s.source_field}
                  </td>
                  <td className="py-0.5 text-right font-mono">
                    {s.value === null ? "—" : String(s.value)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {toolCalls.length > 0 && (
          <ul className="space-y-0.5 font-mono text-[9px] text-slate-600">
            {toolCalls.map((t, i) => (
              <li key={i}>
                <span className="text-slate-400">{String(i + 1).padStart(2, "0")}</span>{" "}
                {t.name} · {t.latency_ms} ms
              </li>
            ))}
          </ul>
        )}
        {verifierNotes.length > 0 && (
          <ul className="space-y-0.5 text-[9px] text-amber-900">
            {verifierNotes.map((n, i) => (
              <li key={i}>· {n}</li>
            ))}
          </ul>
        )}
      </div>
    </details>
  );
}
