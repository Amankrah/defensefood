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

// ── country brief (Phase 2) ───────────────────────────────────────────────

export interface CountryBrief {
  headline: string;
  inbound_markdown: string;
  outbound_markdown: string;
  key_signals: CitedSignal[];
  notable_lanes: string[];
  caveats: string[];
  confidence: Confidence;
  verifier_notes: string[];
  sub_agent_notes: string[];
}

export interface CountryBriefResponse {
  brief: CountryBrief;
  m49: number;
  provider: string;
  model: string;
  tokens_in: number;
  tokens_out: number;
  cost_usd: number;
  latency_ms: number;
  cache_hit: boolean;
  tool_trace: (ToolTrace & { phase?: string })[];
}

// ── SSE event types ───────────────────────────────────────────────────────

/**
 * One streaming event from any brief endpoint. ``final_brief`` carries the
 * provider-specific response (lane or country); callers narrow with a runtime
 * shape check (e.g. ``"corridor_key" in response``).
 */
export type AgentEvent =
  | { kind: "status"; phase: string; target_key?: string; snapshot?: string }
  | {
      kind: "tool_call";
      name: string;
      args: Record<string, unknown>;
      latency_ms: number;
      phase?: string;
    }
  | { kind: "tool_result"; name: string; result: ToolTrace["result"] }
  | { kind: "verifier_note"; note: string }
  | {
      kind: "final_brief";
      response:
        | (LaneBriefResponse & { cache_hit?: boolean })
        | (CountryBriefResponse & { cache_hit?: boolean })
        | (PeriodShiftResponse & { cache_hit?: boolean });
    }
  | { kind: "error"; message: string; code: number };

// ── cache-only probe ──────────────────────────────────────────────────────

/**
 * Result of a cache-only probe. Either a cached brief is returned, or the
 * server indicates one would need to be generated. The probe never invokes
 * the LLM, so it is safe to call on every page mount.
 */
export type LaneBriefProbe =
  | { cached: true; response: LaneBriefResponse }
  | { cached: false; needs_generation: true; target_key: string; snapshot_hash: string };

export type CountryBriefProbe =
  | { cached: true; response: CountryBriefResponse }
  | { cached: false; needs_generation: true; target_key: string; snapshot_hash: string };

export async function probeLaneBrief(
  hs: string,
  dest: number,
  origin: number
): Promise<LaneBriefProbe> {
  const url = `${API_BASE}/agent/lane-brief/${encodeURIComponent(
    hs
  )}/${dest}/${origin}?only_cached=true`;
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`Lane brief probe ${res.status}: ${res.statusText}`);
  const body = (await res.json()) as Record<string, unknown>;
  if (body.cache_hit === false && body.needs_generation === true) {
    return {
      cached: false,
      needs_generation: true,
      target_key: String(body.target_key ?? ""),
      snapshot_hash: String(body.snapshot_hash ?? ""),
    };
  }
  return { cached: true, response: body as unknown as LaneBriefResponse };
}

export async function probeCountryBrief(m49: number): Promise<CountryBriefProbe> {
  const url = `${API_BASE}/agent/country-brief/${m49}?only_cached=true`;
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`Country brief probe ${res.status}: ${res.statusText}`);
  const body = (await res.json()) as Record<string, unknown>;
  if (body.cache_hit === false && body.needs_generation === true) {
    return {
      cached: false,
      needs_generation: true,
      target_key: String(body.target_key ?? ""),
      snapshot_hash: String(body.snapshot_hash ?? ""),
    };
  }
  return { cached: true, response: body as unknown as CountryBriefResponse };
}

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
        phase: obj.phase as string | undefined,
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

// ── period shift (Phase 3) ────────────────────────────────────────────────

export type Direction = "rising" | "falling" | "stable";

export interface PeriodMover {
  lane_key: string;
  label: string;
  cvs_a: number | null;
  cvs_b: number | null;
  cvs_delta: number | null;
  notif_delta: number | null;
  direction: Direction;
  explanation: string;
}

export interface PeriodCluster {
  cluster_label: string;
  lane_count: number;
  mean_movement: number;
  criterion: string;
  lane_keys: string[];
  explanation: string;
}

export interface PeriodShiftBrief {
  headline: string;
  body_markdown: string;
  period_a: number;
  period_b: number;
  top_risers: PeriodMover[];
  top_fallers: PeriodMover[];
  emerging_clusters: PeriodCluster[];
  key_signals: CitedSignal[];
  caveats: string[];
  confidence: Confidence;
  verifier_notes: string[];
}

export interface PeriodShiftResponse {
  brief: PeriodShiftBrief;
  period_a: number;
  period_b: number;
  provider: string;
  model: string;
  tokens_in: number;
  tokens_out: number;
  cost_usd: number;
  latency_ms: number;
  cache_hit: boolean;
  tool_trace: ToolTrace[];
}

export type PeriodShiftProbe =
  | {
      cached: true;
      response: PeriodShiftResponse;
      available_periods: number[];
    }
  | {
      cached: false;
      needs_generation: true;
      target_key: string;
      snapshot_hash: string;
      period_a: number;
      period_b: number;
      available_periods: number[];
    };

export async function probePeriodShift(opts?: {
  period_a?: number;
  period_b?: number;
}): Promise<PeriodShiftProbe> {
  const params = new URLSearchParams();
  params.set("only_cached", "true");
  if (opts?.period_a) params.set("period_a", String(opts.period_a));
  if (opts?.period_b) params.set("period_b", String(opts.period_b));
  const res = await fetch(
    `${API_BASE}/agent/period-shift?${params.toString()}`,
    { cache: "no-store" }
  );
  if (!res.ok) throw new Error(`Period shift probe ${res.status}: ${res.statusText}`);
  const body = (await res.json()) as Record<string, unknown>;
  const available_periods = Array.isArray(body.available_periods)
    ? (body.available_periods as number[])
    : [];
  if (body.cache_hit === false && body.needs_generation === true) {
    return {
      cached: false,
      needs_generation: true,
      target_key: String(body.target_key ?? ""),
      snapshot_hash: String(body.snapshot_hash ?? ""),
      period_a: Number(body.period_a ?? 0),
      period_b: Number(body.period_b ?? 0),
      available_periods,
    };
  }
  return {
    cached: true,
    response: body as unknown as PeriodShiftResponse,
    available_periods,
  };
}

export async function fetchPeriodShift(opts?: {
  period_a?: number;
  period_b?: number;
  verify?: VerifyMode;
  refresh?: boolean;
}): Promise<PeriodShiftResponse> {
  const params = new URLSearchParams();
  if (opts?.period_a) params.set("period_a", String(opts.period_a));
  if (opts?.period_b) params.set("period_b", String(opts.period_b));
  if (opts?.verify) params.set("verify", opts.verify);
  if (opts?.refresh) params.set("refresh", "true");
  const qs = params.toString();
  const url = `${API_BASE}/agent/period-shift${qs ? `?${qs}` : ""}`;
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      /* ignore */
    }
    throw new Error(`Period shift ${res.status}: ${detail}`);
  }
  return res.json();
}

// ── hypotheses + anomaly explainer (Phase 5) ──────────────────────────────

export type AnomalyVerdict = "anomalous" | "borderline" | "not_anomalous";

export interface FalsifyingTest {
  description: string;
  suggested_tools: string[];
}

export interface Hypothesis {
  headline: string;
  narrative: string;
  confidence: Confidence;
  supporting_signals: CitedSignal[];
  contradicting_signals: CitedSignal[];
  falsifying_test: FalsifyingTest;
  next_data: string;
}

export interface HypothesisSet {
  target_label: string;
  pattern_summary: string;
  hypotheses: Hypothesis[];
  caveats: string[];
  verifier_notes: string[];
}

export interface HypothesisResponse {
  hset: HypothesisSet;
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

export interface AnomalyExplanation {
  target_label: string;
  verdict: AnomalyVerdict;
  headline: string;
  why_anomalous: string;
  why_not: string;
  supporting_signals: CitedSignal[];
  peer_comparison: string;
  confidence: Confidence;
  caveats: string[];
  verifier_notes: string[];
}

export interface AnomalyResponse {
  explanation: AnomalyExplanation;
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

export type HypothesisProbe =
  | { cached: true; response: HypothesisResponse }
  | { cached: false; needs_generation: true };

export type AnomalyProbe =
  | { cached: true; response: AnomalyResponse }
  | { cached: false; needs_generation: true };

export async function probeHypotheses(
  hs: string,
  dest: number,
  origin: number
): Promise<HypothesisProbe> {
  const url = `${API_BASE}/agent/hypotheses/${encodeURIComponent(
    hs
  )}/${dest}/${origin}?only_cached=true`;
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`Hypotheses probe ${res.status}: ${res.statusText}`);
  const body = (await res.json()) as Record<string, unknown>;
  if (body.cache_hit === false && body.needs_generation === true) {
    return { cached: false, needs_generation: true };
  }
  return { cached: true, response: body as unknown as HypothesisResponse };
}

export async function fetchHypotheses(
  hs: string,
  dest: number,
  origin: number,
  opts?: { refresh?: boolean }
): Promise<HypothesisResponse> {
  const params = new URLSearchParams();
  if (opts?.refresh) params.set("refresh", "true");
  const qs = params.toString();
  const url = `${API_BASE}/agent/hypotheses/${encodeURIComponent(
    hs
  )}/${dest}/${origin}${qs ? `?${qs}` : ""}`;
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const b = (await res.json()) as { detail?: string };
      if (b.detail) detail = b.detail;
    } catch {
      /* ignore */
    }
    throw new Error(`Hypotheses ${res.status}: ${detail}`);
  }
  return res.json();
}

export async function probeAnomaly(
  hs: string,
  dest: number,
  origin: number
): Promise<AnomalyProbe> {
  const url = `${API_BASE}/agent/explain-anomaly/${encodeURIComponent(
    hs
  )}/${dest}/${origin}?only_cached=true`;
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`Anomaly probe ${res.status}: ${res.statusText}`);
  const body = (await res.json()) as Record<string, unknown>;
  if (body.cache_hit === false && body.needs_generation === true) {
    return { cached: false, needs_generation: true };
  }
  return { cached: true, response: body as unknown as AnomalyResponse };
}

export async function fetchAnomalyExplanation(
  hs: string,
  dest: number,
  origin: number,
  opts?: { refresh?: boolean }
): Promise<AnomalyResponse> {
  const params = new URLSearchParams();
  if (opts?.refresh) params.set("refresh", "true");
  const qs = params.toString();
  const url = `${API_BASE}/agent/explain-anomaly/${encodeURIComponent(
    hs
  )}/${dest}/${origin}${qs ? `?${qs}` : ""}`;
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const b = (await res.json()) as { detail?: string };
      if (b.detail) detail = b.detail;
    } catch {
      /* ignore */
    }
    throw new Error(`Anomaly ${res.status}: ${detail}`);
  }
  return res.json();
}

// ── conversational Q&A (Phase 4) ──────────────────────────────────────────

export type QAIntent =
  | "lookup"
  | "filter"
  | "compare"
  | "explain"
  | "methodology"
  | "narrative_freeform"
  | "out_of_scope";

export interface QueryEntities {
  commodity_hs: string[];
  country_m49: number[];
  metric_keys: string[];
  period_a: number | null;
  period_b: number | null;
  direction: "rising" | "falling" | "any" | null;
  threshold: number | null;
}

export interface IntentClassification {
  intent: QAIntent;
  in_scope: boolean;
  refusal_reason: string | null;
  entities: QueryEntities;
}

export interface QATableColumn {
  key: string;
  label: string;
  align: "left" | "right";
}

export interface QAStructuredData {
  title: string;
  columns: QATableColumn[];
  rows: Record<string, unknown>[];
  lane_keys: string[];
}

export interface QATurn {
  answer_markdown: string;
  key_signals: CitedSignal[];
  structured_data: QAStructuredData | null;
  caveats: string[];
  confidence: Confidence;
  verifier_notes: string[];
}

export interface QAResultResponse {
  conversation_id: string;
  turn: QATurn;
  classification: IntentClassification;
  refused: boolean;
  provider: string;
  model: string;
  tokens_in: number;
  tokens_out: number;
  cost_usd: number;
  latency_ms: number;
  tool_trace: ToolTrace[];
}

export interface ConversationMessage {
  id: number;
  role: "user" | "assistant" | "system" | "tool";
  content: Record<string, unknown>;
  tool_calls: { name: string; args: unknown; latency_ms: number }[] | null;
  tokens_in: number | null;
  tokens_out: number | null;
  cost_usd: number | null;
  created_at: number;
}

export interface ConversationDetail {
  id: string;
  started_at: number;
  last_used_at: number;
  title: string | null;
  summary: string | null;
  messages: ConversationMessage[];
}

export interface ConversationHeader {
  id: string;
  started_at: number;
  last_used_at: number;
  title: string | null;
  summary: string | null;
  message_count: number;
}

export type QAEvent =
  | { kind: "status"; phase: string; conversation_id?: string | null }
  | { kind: "intent"; classification: IntentClassification }
  | {
      kind: "tool_call";
      name: string;
      args: Record<string, unknown>;
      latency_ms: number;
    }
  | { kind: "tool_result"; name: string; result: ToolTrace["result"] }
  | { kind: "verifier_note"; note: string }
  | { kind: "final_answer"; response: QAResultResponse }
  | { kind: "error"; message: string; code: number };

export async function fetchQA(
  query: string,
  conversation_id?: string
): Promise<QAResultResponse> {
  const res = await fetch(`${API_BASE}/agent/qa`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, conversation_id: conversation_id ?? null }),
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      /* ignore */
    }
    throw new Error(`QA ${res.status}: ${detail}`);
  }
  return res.json();
}

export async function* streamQA(
  query: string,
  opts: {
    conversation_id?: string;
    signal?: AbortSignal;
  } = {}
): AsyncGenerator<QAEvent, void, void> {
  const res = await fetch(`${API_BASE}/agent/qa?stream=true`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify({
      query,
      conversation_id: opts.conversation_id ?? null,
    }),
    cache: "no-store",
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
      let idx: number;
      while ((idx = buffer.indexOf("\n\n")) !== -1) {
        const raw = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);
        const parsed = parseQaSseFrame(raw);
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

function parseQaSseFrame(raw: string): QAEvent | null {
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
        conversation_id: (obj.conversation_id as string | null) ?? null,
      };
    case "intent":
      return {
        kind: "intent",
        classification: obj as unknown as IntentClassification,
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
    case "final_answer":
      return {
        kind: "final_answer",
        response: obj as unknown as QAResultResponse,
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

export async function listConversations(
  limit = 20
): Promise<{ rows: ConversationHeader[] }> {
  const res = await fetch(
    `${API_BASE}/agent/conversations?limit=${limit}`,
    { cache: "no-store" }
  );
  if (!res.ok) throw new Error(`Conversations ${res.status}`);
  return res.json();
}

export async function fetchConversation(
  id: string
): Promise<ConversationDetail> {
  const res = await fetch(
    `${API_BASE}/agent/conversations/${encodeURIComponent(id)}`,
    { cache: "no-store" }
  );
  if (!res.ok) throw new Error(`Conversation ${res.status}: ${res.statusText}`);
  return res.json();
}

export async function* streamPeriodShift(
  opts: {
    period_a?: number;
    period_b?: number;
    verify?: VerifyMode;
    refresh?: boolean;
    signal?: AbortSignal;
  } = {}
): AsyncGenerator<AgentEvent, void, void> {
  const params = new URLSearchParams();
  params.set("stream", "true");
  if (opts.period_a) params.set("period_a", String(opts.period_a));
  if (opts.period_b) params.set("period_b", String(opts.period_b));
  if (opts.verify) params.set("verify", opts.verify);
  if (opts.refresh) params.set("refresh", "true");
  const url = `${API_BASE}/agent/period-shift?${params.toString()}`;

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

// ── country brief streamer + fetch ────────────────────────────────────────

export async function fetchCountryBrief(
  m49: number,
  opts?: { verify?: VerifyMode; refresh?: boolean }
): Promise<CountryBriefResponse> {
  const params = new URLSearchParams();
  if (opts?.verify) params.set("verify", opts.verify);
  if (opts?.refresh) params.set("refresh", "true");
  const qs = params.toString();
  const url = `${API_BASE}/agent/country-brief/${m49}${qs ? `?${qs}` : ""}`;
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      /* ignore */
    }
    throw new Error(`Country brief ${res.status}: ${detail}`);
  }
  return res.json();
}

export async function* streamCountryBrief(
  m49: number,
  opts: { verify?: VerifyMode; refresh?: boolean; signal?: AbortSignal } = {}
): AsyncGenerator<AgentEvent, void, void> {
  const params = new URLSearchParams();
  params.set("stream", "true");
  if (opts.verify) params.set("verify", opts.verify);
  if (opts.refresh) params.set("refresh", "true");
  const url = `${API_BASE}/agent/country-brief/${m49}?${params.toString()}`;

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
