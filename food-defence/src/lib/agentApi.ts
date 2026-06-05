/**
 * Agent subsystem API client.
 *
 * The backend exposes briefs at /api/v1/agent/lane-brief/{hs}/{dest}/{origin}
 * with optional ?stream=true Server-Sent Events. This module provides:
 *
 *   - typed JSON fetch helpers for the non-streaming path,
 *   - a small SSE reader (no extra deps) for the streaming path,
 *   - typed events the React UI can switch on.
 *
 * No third-party SSE library: native fetch() with a ReadableStream reader is
 * enough for our shape and keeps the bundle small.
 */

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

// ── types ─────────────────────────────────────────────────────────────────

export type Band = "low" | "med" | "high" | "flag" | "unknown";
export type Confidence = "low" | "med" | "high";
export type VerifyMode = "strict" | "fast" | "off";

export interface CitedSignal {
  name: string;
  source_field: string;
  value: number | string | null;
  band: Band;
}

export interface LaneBrief {
  headline: string;
  body_markdown: string;
  key_signals: CitedSignal[];
  caveats: string[];
  confidence: Confidence;
  verifier_notes: string[];
}

export interface ToolTrace {
  name: string;
  args: Record<string, unknown>;
  result: { ok: boolean; result?: unknown; error?: string };
  latency_ms: number;
}

export interface LaneBriefResponse {
  brief: LaneBrief;
  corridor_key: string;
  provider: string;
  model: string;
  tokens_in: number;
  tokens_out: number;
  cost_usd: number;
  latency_ms: number;
  cache_hit: boolean;
  tool_trace: ToolTrace[];
}

// ── SSE event types ───────────────────────────────────────────────────────

export type AgentEvent =
  | { kind: "status"; phase: string; target_key?: string; snapshot?: string }
  | { kind: "tool_call"; name: string; args: Record<string, unknown>; latency_ms: number }
  | { kind: "tool_result"; name: string; result: ToolTrace["result"] }
  | { kind: "verifier_note"; note: string }
  | { kind: "final_brief"; response: LaneBriefResponse & { cache_hit?: boolean } }
  | { kind: "error"; message: string; code: number };

// ── non-streaming fetch ───────────────────────────────────────────────────

export async function fetchLaneBrief(
  hs: string,
  dest: number,
  origin: number,
  opts?: { verify?: VerifyMode; refresh?: boolean }
): Promise<LaneBriefResponse> {
  const params = new URLSearchParams();
  if (opts?.verify) params.set("verify", opts.verify);
  if (opts?.refresh) params.set("refresh", "true");
  const qs = params.toString();
  const url = `${API_BASE}/agent/lane-brief/${encodeURIComponent(
    hs
  )}/${dest}/${origin}${qs ? `?${qs}` : ""}`;
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      /* ignore json parse error */
    }
    throw new Error(`Lane brief ${res.status}: ${detail}`);
  }
  return res.json();
}

// ── SSE reader ────────────────────────────────────────────────────────────

/**
 * Stream a lane brief as a sequence of typed AgentEvents.
 *
 * Usage:
 *
 *   const ctrl = new AbortController();
 *   for await (const ev of streamLaneBrief(hs, dest, origin, { signal: ctrl.signal })) {
 *     switch (ev.kind) { ... }
 *   }
 */
export async function* streamLaneBrief(
  hs: string,
  dest: number,
  origin: number,
  opts: { verify?: VerifyMode; refresh?: boolean; signal?: AbortSignal } = {}
): AsyncGenerator<AgentEvent, void, void> {
  const params = new URLSearchParams();
  params.set("stream", "true");
  if (opts.verify) params.set("verify", opts.verify);
  if (opts.refresh) params.set("refresh", "true");
  const url = `${API_BASE}/agent/lane-brief/${encodeURIComponent(
    hs
  )}/${dest}/${origin}?${params.toString()}`;

  const res = await fetch(url, {
    cache: "no-store",
    headers: { Accept: "text/event-stream" },
    signal: opts.signal,
  });
  if (!res.ok || !res.body) {
    yield {
      kind: "error",
      message: `HTTP ${res.status}: ${res.statusText}`,
      code: res.status,
    };
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // SSE messages end with a blank line; each message may have event: and data: lines.
      let idx: number;
      while ((idx = buffer.indexOf("\n\n")) !== -1) {
        const raw = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);
        const parsed = parseSseFrame(raw);
        if (parsed) yield parsed;
      }
    }
  } catch (e) {
    if ((e as { name?: string }).name === "AbortError") return;
    throw e;
  } finally {
    try {
      reader.releaseLock();
    } catch {
      /* noop */
    }
  }
}

function parseSseFrame(raw: string): AgentEvent | null {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of raw.split("\n")) {
    if (!line) continue;
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
  }
  if (dataLines.length === 0) return null;
  let data: unknown;
  try {
    data = JSON.parse(dataLines.join("\n"));
  } catch {
    return null;
  }
  const obj = (data as Record<string, unknown>) ?? {};
  switch (event) {
    case "status":
      return {
        kind: "status",
        phase: String(obj.phase ?? ""),
        target_key: obj.target_key as string | undefined,
        snapshot: obj.snapshot as string | undefined,
      };
    case "tool_call":
      return {
        kind: "tool_call",
        name: String(obj.name ?? ""),
        args: (obj.args as Record<string, unknown>) ?? {},
        latency_ms: Number(obj.latency_ms ?? 0),
      };
    case "tool_result":
      return {
        kind: "tool_result",
        name: String(obj.name ?? ""),
        result: (obj.result as ToolTrace["result"]) ?? { ok: false },
      };
    case "verifier_note":
      return { kind: "verifier_note", note: String(obj.note ?? "") };
    case "final_brief":
      return {
        kind: "final_brief",
        response: obj as unknown as LaneBriefResponse & { cache_hit?: boolean },
      };
    case "error":
      return {
        kind: "error",
        message: String(obj.message ?? ""),
        code: Number(obj.code ?? 500),
      };
    default:
      return null;
  }
}

// ── cost dashboard ────────────────────────────────────────────────────────

export interface CostLedgerRow {
  use_case: string;
  provider: string;
  model: string;
  tokens_in: number;
  tokens_out: number;
  usd: number;
}

export async function fetchTodayCosts(): Promise<{ rows: CostLedgerRow[] }> {
  const res = await fetch(`${API_BASE}/agent/costs/today`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Costs ${res.status}`);
  return res.json();
}
