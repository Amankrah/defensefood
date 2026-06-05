# AI Subsystem — Agentic interpretation, briefs, and Q&A for the food fraud diagnostic corpus

## Context

DefenseFood is a **blueprint, diagnostic, and forensic tool** for studying food fraud vulnerability across the EU trade graph. The data corpus lags reality by 1 to 2 years (Comtrade publishes 2023 well into 2024-2025; FAOSTAT FBS lags similarly), so this is not an "operational this week" platform. The audience is **researchers and analysts** doing comparative, hypothesis-driven analysis across the loaded years (currently 2018-2023), with a future epic to add predictive capability on top.

Today the engine produces 17 metrics across Sections 2 to 7 of the v1.0 mathematical framework, plus a normalised CVS priority score per corridor. The dashboard renders the numbers in tiles and walk-throughs, and a methodology catalogue ties every metric to its formula, scale bands, and plain-English explanation. What's missing is **narrative**: a researcher looking at a Spanish-mussels-into-France lane sees SCI 1.3, HIS 0.7, ΔHHI +0.04, MTD 0.19, but the story that connects those numbers (and what it means) lives only in their head.

This plan introduces an agentic AI subsystem that fills that gap. It is **not** "an LLM prompt with the metric values stuffed in". It is a tool-using agent pipeline with structured outputs, prompt caching, citation verification, and a reflection pass that catches hallucinated numbers before they reach the UI. Provider abstraction (Claude default, OpenAI fallback) keeps us swap-friendly per use case.

The four use cases the user prioritised:

1. **Lane forensic brief** — 2 to 3 paragraph diagnostic on a specific corridor, anchored to the lane's own metrics.
2. **Country brief** — inbound exposure (ACEP) + outbound propagation (ORPS by commodity), highlighting the top 2 to 3 bottlenecks.
3. **Period-shift diagnostic** — replaces the "today digest" framing. Compares the latest loaded period vs prior periods (e.g. 2022 → 2023) to surface lanes that moved up or down in priority and commodity-origin clusters with material drift.
4. **Conversational Q&A** — research workbench. Inspector or researcher asks "show me corridors where ΔHHI rose more than 0.1 and CVS is in the top band"; the agent translates intent to typed tool calls, runs them, and renders a card-style answer with the underlying numbers.

Ship order **Phase 1 → 2 → 3 → 4 → 5 → 6**. Each phase is independently shippable; the user can stop after any of them and still have a usable subsystem.

## Existing surface to reuse

- [backend/defensefood/api/dependencies.py::AppState](backend/defensefood/api/dependencies.py) — already caches the entire corpus in memory at startup: `corridor_metrics`, `notifications`, `trade_df`, `pcc/crs/dis_lookup`, `avg_shipment_lookup`, `scoring_config`. Agents read state directly; no HTTP roundtrip per tool call.
- [backend/defensefood/api/methodology_catalogue.py](backend/defensefood/api/methodology_catalogue.py) — 17 metric entries with `formula_latex`, `formula_plain`, `scale` bands with `advice`, `when_matters`, `related`, `source`. Single best source for the agent's domain priors.
- [backend/defensefood/pipeline/interpretation.py::interpret_metric](backend/defensefood/pipeline/interpretation.py) — already produces `{verdict, band, advice}` from a value. Agents wrap this for citation, not replace it.
- [backend/defensefood/api/routers/](backend/defensefood/api/routers/) — 18 read-only cached endpoints (corridors, countries, commodities, hazards, network, research). Many become tool wrappers, but tools call the underlying Python directly for speed.
- [food-defence/src/components/shared/VerdictBanner.tsx](food-defence/src/components/shared/VerdictBanner.tsx) — existing pattern for synthesised narrative tiles (`trackRecordVerdict`, `supplyVerdict`). New `BriefCard` reuses the same shape (title, body, band-coloured stripe).
- [food-defence/src/components/shared/LaneWalkthrough.tsx](food-defence/src/components/shared/LaneWalkthrough.tsx) and [CvsComposition.tsx](food-defence/src/components/shared/CvsComposition.tsx) — collapsible explainer pattern. New "Evidence" expander on each brief follows the same shape (show the cited tool calls + raw numbers when opened).
- [food-defence/src/lib/api.ts::fetchApi](food-defence/src/lib/api.ts) — current `fetch + JSON` client. A new `streamApi` helper handles SSE for streaming briefs without disrupting existing callers.

---

## Architectural decisions

These are the cross-cutting choices that apply to all phases.

### Where it lives

A new top-level package `backend/defensefood/agent/` parallel to `pipeline/`, `ingestion/`, `api/`. The agent module imports `AppState` and the catalogue directly so tool calls are in-process function calls, not HTTP roundtrips. A thin `backend/defensefood/api/routers/agent.py` exposes the user-facing endpoints (briefs, Q&A, audit log) under `/api/v1/agent`.

### Provider abstraction

`agent/provider.py` defines a single `LLMProvider` Protocol with `chat(...)`, `tool_use_loop(...)`, and `structured_output(...)` methods. Two concrete implementations — `AnthropicProvider` (default) and `OpenAIProvider` (fallback) — wrap the official SDKs. Each use case names its preferred model tier (`sonnet`, `haiku`, `opus`, `gpt-5`, `gpt-5-mini`); the provider resolves the actual model id at call time. Anthropic is the default for narrative + tool use; OpenAI is used for fallback when rate-limited and for cheap routing / intent parsing.

### Tools as typed Python functions

`agent/tools.py` decorates plain Python functions with `@tool` and `@requires_state`. The decorator:

1. Inspects the function's Pydantic argument model and produces a JSON Schema compatible with both Anthropic's `tools=[...]` and OpenAI's `tools=[...{type: "function"}]` formats.
2. Validates incoming tool call arguments against the schema before invoking.
3. Stamps each result with the tool name, latency, and the SHA-256 of the corpus snapshot used (corridor count + scoring_config hash) so downstream verifiers can detect stale data.

Tool functions read from `AppState` directly — no HTTP, no JSON serialisation cost beyond what crosses the LLM boundary. Examples: `get_corridor_profile(hs, dest, origin)`, `list_top_corridors(by, n, filter)`, `get_methodology(metric_key)`, `country_inbound_exposure(m49)`, `network_neighbours(m49, direction)`, `compare_periods(corridors, period_a, period_b)`.

### Structured outputs

Every brief returns a Pydantic model, not free text. `LaneBrief` has fields `headline`, `key_signals: list[CitedSignal]`, `body_markdown`, `caveats: list[str]`, `confidence: Literal["low","med","high"]`. A `CitedSignal` is `{name, value, source_field, lane_or_country_key, band}` — every number the agent mentions in `body_markdown` must appear in `key_signals` with a matching source field. The reflection pass (next item) enforces this.

### Reflection / verification pass

After the primary agent returns a draft brief, a separate verifier call:

1. Re-fetches every `CitedSignal.value` via the corresponding tool (lookup by `source_field`) and compares against the engine's actual number.
2. Flags numerical hallucinations (value mismatches), unlinked claims (numbers in body_markdown not in `key_signals`), and out-of-band claims (verdict text that contradicts the metric's scale band).
3. Either auto-corrects (replaces a hallucinated number with the verified one) or re-runs the primary agent with the verifier's critique appended.

This is the difference between "agentic" and "decorated prompt". The reflection pass is gated behind a `?verify=strict|fast|off` query so internal R&D can skip it for speed.

### Prompt caching

The system prompt includes (a) the full methodology catalogue, (b) the active scoring config, (c) the data-coverage snapshot. These rarely change per request and dominate token count. Both Anthropic and OpenAI now support prompt caching; the provider abstraction marks these spans with `cache_control={"type": "ephemeral"}` (Anthropic) or `cache_key` (OpenAI). Expected cost reduction: 60-80% on briefs after the first call in a 5-minute window.

### Persistence and audit

SQLite at `backend/data/agent.db` with three tables:

- `briefs(id, use_case, target_key, brief_json, snapshot_hash, model, cost_usd, latency_ms, created_at)` — cached generated briefs, looked up by `(use_case, target_key, snapshot_hash)` so the same lane returns the same brief until the corpus or config changes.
- `audit_log(id, brief_id, role, content_json, tool_calls_json, tokens_in, tokens_out, created_at)` — every turn of every agentic loop. The frontend "show evidence" expander reads this so researchers can audit what the agent saw.
- `cost_ledger(date, use_case, provider, model, tokens_in, tokens_out, usd)` — daily aggregates for the cost dashboard.

### Streaming

FastAPI `StreamingResponse` with `text/event-stream`. Each chunk is a JSON-encoded `AgentEvent` (one of `tool_call`, `tool_result`, `partial_text`, `verifier_note`, `final_brief`). The frontend's new `lib/agentApi.ts` wraps `fetch` with an `EventSource`-like reader that yields these events to React state, so the UI can show "consulting hazard tool…", "verifying citations…", and the prose as it streams.

### Cost discipline

Three model tiers, named by purpose:

- **`route` (Haiku 4.5 / GPT-5 mini, ~$0.30 / $1.00 per M tokens)** — intent parsing, ranker, classifier.
- **`narrative` (Sonnet 4.6 / GPT-5, ~$3 / $10 per M tokens, prompt-cached)** — primary brief generation, Q&A composition.
- **`heavy` (Opus 4.7, ~$15 / $75 per M tokens)** — only when the verifier escalates after two failed self-corrections.

Per-use-case budget cap in the config (`max_cost_usd_per_call`); the agent loop aborts and returns a graceful "couldn't synthesise" stub if the cap is hit.

---

## Phase 1 — Foundation + Lane forensic brief (correctness; ship first)

**Goal**: Every lane forensic report gets a 2 to 3 paragraph AI brief at the top, with verified citations, behind a streaming endpoint. The brief reads as if a domain expert wrote it.

### P1.1 Foundation (one-time infra)

- Add dependencies in [backend/pyproject.toml](backend/pyproject.toml): `anthropic`, `openai`, `httpx`, `tenacity` (retry), `pydantic-settings` (env-loaded config).
- New module `agent/` with `provider.py`, `tools.py`, `runner.py`, `cache.py`, `audit.py`, `prompts/` (system prompt fragments as `.md` files).
- New `agent.config.AgentConfig` (Pydantic Settings): `anthropic_api_key`, `openai_api_key`, `default_provider`, `models: dict[tier, model_id]`, `max_cost_usd_per_call`, `verify_default`.
- SQLite schema migration in `agent/cache.py::init_db()`; called from FastAPI's `lifespan` after the existing data load.
- 12 to 15 tools registered, covering corridor metrics, methodology lookup, country/network reads, and the period-shift comparator (used by Phase 3).

### P1.2 Lane brief

- New `agent/briefs/lane_brief.py::generate_lane_brief(hs, dest, origin, *, verify="strict") -> LaneBrief`.
- System prompt (`agent/prompts/lane_brief.md`): role is "diagnostic analyst writing for an EU food fraud researcher"; rules cover citation, voice, caveats; explicitly forbids speculative language without grounding ("possibly fraudulent" requires HIS or DGI evidence).
- Tool plan: agent always calls `get_corridor_profile` first, then conditionally `get_methodology` for any metric not yet in the brief's vocabulary, `country_inbound_exposure` if the destination's broader context matters, `compare_periods` when multi-year ΔHHI or ΔOCS are non-trivial.
- Reflection pass: verifier re-fetches every `CitedSignal` and either auto-corrects or escalates to `heavy` tier (Opus) for a rewrite.

### P1.3 API endpoint

`GET /api/v1/agent/lane-brief/{hs}/{dest}/{origin}?stream=true&verify=strict` returns SSE events; without `stream=true` returns the final JSON. Cache lookup by `(use_case="lane_brief", target_key="hs/dest/origin", snapshot_hash)`; if hit and within 24h, return the cached brief instantly.

### P1.4 Frontend tile

- Add `react-markdown` + `streamdown` + `remark-gfm` to `food-defence/package.json`.
- New `food-defence/src/lib/agentApi.ts::streamAgentBrief(useCase, key, opts)` — SSE reader.
- New `food-defence/src/components/shared/BriefCard.tsx` — renders the streaming brief plus a "Show evidence" expander that lists the tool calls + cited signals (reads from the same SSE stream's `tool_call` and `tool_result` events).
- Mount on the Lane forensic report ([corridors/[hs]/[dest]/[origin]/page.tsx](food-defence/src/app/dashboard/corridors/[hs]/[dest]/[origin]/page.tsx)) immediately after the headline priority card, before the Step 1 VerdictBanner.

### P1.5 Tests + eval

- Unit tests in `backend/tests/test_agent_tools.py`: each tool runs in-process against a fixture corpus, schema validation kicks in on bad inputs.
- New `backend/tests/eval/lane_briefs.jsonl` — 10 golden lanes spanning data-rich (`sci_crs_his`), data-poor (`sci_his`), informational-only, and trade-only-fallback modes. Each row has the lane key plus required signals the brief must mention (e.g. lane FR<-IT mussels must cite HIS, the alert count, and the multi-year ΔHHI).
- `backend/tests/test_lane_brief_eval.py` runs each golden case end to end, asserts (a) `LaneBrief` parses, (b) every `key_signals[*]` matches the engine's actual value within float tolerance, (c) the required signals appear in `key_signals`, (d) total cost is below the per-call cap.

### Phase 1 milestone

Open `/dashboard/corridors/30771/380/724` in a browser. A streaming brief appears within ~500ms of page load (cached path) or ~3-6s (first call), reading something like:

> "Spanish mussels into France carry **moderate structural pressure** (SCI 0.42, top-quartile in the corpus). Across 2018-2023, ΔHHI rose by +0.04 while mirror trade discrepancy held at 0.19, consistent with origin diversification by French importers without sourcing transparency improving. Hazard signal is **steady-low** (HIS 0.18, no alerts since 2022) so the priority sits in the watchlist band rather than top. The 19% mirror-trade gap is the open question worth pursuing if you have the data lineage to chase it."

Below the brief, "Show evidence" reveals 4 tool calls with raw responses, each cited number colour-coded green (verified) or red (mismatch, which should never appear after the reflection pass).

---

## Phase 2 — Country brief + reflection hardening

**Goal**: Same brief pattern on country pages, and the verification subsystem catches subtler failures (out-of-band claims, missing caveats).

### P2.1 Country brief

- `agent/briefs/country_brief.py::generate_country_brief(m49) -> CountryBrief` — separate Pydantic schema with inbound and outbound halves.
- System prompt covers role-aware ACEP (confirmed vs detected vs informational), the country's top 3 inbound bottlenecks by ACEP contribution, top 3 outbound commodities by ORPS, and whether the country is primarily an importer, exporter, or both.
- Tool plan: `country_inbound_exposure`, `country_outbound_orps`, `top_corridors(filter={"destination_m49": m49})`, `network_neighbours(m49, "incoming")`.

### P2.2 Two-specialist composition (multi-agent)

For countries with both inbound and outbound footprints, split into two parallel sub-agents:

- **Inbound specialist** runs `country_inbound_exposure` plus per-commodity `get_corridor_profile` and writes the inbound half.
- **Outbound specialist** runs `country_outbound_orps` and writes the outbound half.
- A **synthesiser** call merges them into a single `CountryBrief`, deduping signals and reconciling tone.

This is the first use of parallel sub-agents; the pattern generalises to Phase 3 and 5.

### P2.3 Reflection upgrades

- **Out-of-band claim detection**: every metric the agent mentions is checked against its `methodology_catalogue` `scale` band. If the agent says "extremely high CVS" for a `low` band value, the verifier flags it and rewrites that sentence.
- **Required-caveat injection**: when the brief references a metric that is in `data_quality` reasons (e.g. `cvs_mode == "sci_his"`), the verifier ensures a caveat appears ("CVS computed without consumption demand because FAOSTAT FBS is unavailable for this country-commodity"). If absent, the verifier appends it.

### P2.4 Frontend mount

Mount `<BriefCard />` on the country page ([countries/[m49]/page.tsx](food-defence/src/app/dashboard/countries/[m49]/page.tsx)) immediately after the ACEP MetricCard. Same SSE streaming pattern. The "Show evidence" expander reveals both specialist tool traces (annotated by sub-agent).

### Phase 2 milestone

Open `/dashboard/countries/380` (Italy). A brief renders covering Italy's inbound exposure (which commodities and origins drive ACEP) and outbound footprint (which commodities propagate ORPS). The brief mentions multi-year trends where applicable and respects the latest-period framing (no "this week" language).

---

## Phase 3 — Period-shift diagnostic (replaces "today" framing)

**Goal**: Replace the operational "today digest" with a research-mode "period shift" report that compares the latest loaded period vs prior periods.

### P3.1 Period shift report generator

- `agent/briefs/period_shift.py::generate_period_shift_brief(period_b, period_a=None, top_n=20) -> PeriodShiftBrief` — defaults compare latest two years.
- `compare_periods(corridors, period_a, period_b)` tool returns, for each corridor: `cvs_delta`, `bdi_delta`, `hhi_delta`, `ocs_delta`, `notification_count_delta`, `direction: rising|falling|stable`.
- The agent then surfaces:
  - **Top risers** (positive CVS delta with confirmation from BDI or HIS deltas).
  - **Top fallers** (negative CVS delta with concrete cause cited).
  - **Emerging clusters** (commodity-origin pairs where multiple lanes moved together).
  - **Long-stable lanes that broke** (low-variance corridors with a sudden delta > 2σ).

### P3.2 Cluster detector tool

New `agent/tools.py::detect_clusters(criterion, top_k)` reads multiple corridor records and groups by (commodity_chapter, origin_m49). Returns clusters whose aggregate metric movement is in the top decile. Cheap to compute; agent uses this before composing the cluster section to avoid having to scan all 1059 lanes itself.

### P3.3 Dashboard mount

The existing "Today" page becomes "Latest period diagnostic". A `<BriefCard variant="digest" />` tile occupies the top of the page, summarising the period shift. The existing priority queue and metric aggregates stay below.

For the URL: `GET /api/v1/agent/period-shift?period_b=2023&period_a=2022` and the page wires the latest two periods automatically when the user opens the dashboard.

### Phase 3 milestone

`/dashboard` shows a brief at top:

> "Comparing 2023 to 2022, **47 corridors moved up** in the CVS priority queue (median delta +0.04) and 33 moved down. The strongest emerging cluster is **mussels into France**, where three origins (Spain, Italy, Ireland) all gained 0.05+ in CVS driven by mirror-trade discrepancy widening rather than new alerts. A second cluster, **rice into Belgium**, broke a 4-year stable pattern with a +0.08 ΔOCS swing toward Indian origin..."

Below: the priority queue and the existing tiles.

---

## Phase 4 — Conversational Q&A (research workbench)

**Goal**: A free-form chat interface where researchers ask questions about the corpus and the agent runs typed tool calls to answer.

### P4.1 Q&A agent loop

- `agent/qa/runner.py::handle_query(query, conversation_id)` — multi-turn loop with conversation memory persisted to SQLite.
- Three-stage pipeline:
  1. **Intent parser** (`route` tier, GPT-5 mini): classifies the query into one of `lookup`, `filter`, `compare`, `explain`, `narrative_freeform`, `methodology`, or `out_of_scope`. Extracts canonical entities (commodity HS, country M49, metric name, period).
  2. **Planner** (`narrative` tier, Sonnet): given the classified intent and entities, produces a tool-call plan (which tools, what arguments, in what order). The plan is a Pydantic structure the runner validates before any tool execution.
  3. **Executor** runs the plan, then composes a response. Out-of-scope queries return a graceful "this isn't something the corpus can answer" plus suggestions for what it can.

### P4.2 Conversation memory

`conversations(id, started_at, last_used_at, summary)` and `messages(id, conversation_id, role, content_json, tool_calls_json, created_at)` tables. On long conversations (>10 turns), the runner triggers an automatic summarisation pass that compacts earlier turns into a single "context so far" message to keep within the token budget.

### P4.3 Q&A endpoint and UI

`POST /api/v1/agent/qa` accepts `{conversation_id?, query, mode: "research"|"strict"}` and streams the response. The "Research" tab on the lab page ([lab/page.tsx](food-defence/src/app/dashboard/lab/page.tsx)) gets a new `<QAPanel />` component with chat-style messages, inline rendered tables for filter results, and a "trace" toggle showing the planner's plan + tool call results.

### P4.4 Pre-baked starter prompts

The QA panel ships with 6 to 8 starter chips ("Compare Spain and Italy as origins", "Why is the top corridor scored so high?", "Show lanes where price anomaly is high but hazard is low") so first-time users have an entry point.

### Phase 4 milestone

Ask "show me corridors where ΔHHI grew over 0.05 between 2022 and 2023 and CVS is in the top band". The agent's planner produces a plan: `compare_periods` → filter on delta > 0.05 → join with current CVS band → render as a sortable table. The response includes both the table and a 2-sentence summary of the pattern. The "trace" expander shows the plan and tool outputs.

---

## Phase 5 — Hypothesis generation + predictive foundation

**Goal**: Move from "describe what's there" to "propose why" and lay the groundwork for the future predictive epic.

### P5.1 Hypothesis generator

For any lane or cluster, the agent proposes 2 to 4 candidate explanations for the observed pattern (e.g. "ΔHHI widened because the second-largest supplier exited the market"). Each hypothesis comes with:

- A **falsifying query**: the tool call sequence that would test it.
- A **confidence**: how strongly the existing data supports vs contradicts.
- A **next data**: what additional data would settle it (e.g. "shipping-route lineage data from a logistics provider").

Tool: `propose_hypotheses(target, evidence)` runs `narrative` tier with a hypothesis-mining prompt. Optional follow-up: `test_hypothesis(target, hypothesis_id)` runs the falsifying query and updates the confidence.

### P5.2 Counterfactual replay

`POST /api/v1/agent/counterfactual` accepts a scoring config override and asks the agent to explain which lanes would change rank the most. The runner re-scores the corpus in memory (using `run_scoring_pipeline` with the override config), computes deltas, and the agent narrates the top movers without persisting the alternate state.

### P5.3 Anomaly explainer

`GET /api/v1/agent/explain-anomaly/{lane_key}` runs deeper than a regular brief: pulls multi-period dependency history, cross-references the catalogue's `when_matters` text, and synthesises a "why this is anomalous and what would convince me it isn't" narrative. This is the foundation for the predictive epic — anomaly explanations become training labels.

### P5.4 Predictive subsystem foundation

Stub `agent/predictive/` with three placeholder modules ready for the future epic:

- `feature_extractor.py` — extracts per-corridor multi-period feature vectors.
- `forecaster.py` — interface for a model that predicts next-period CVS / HIS / cluster formation.
- `eval_harness.py` — back-test framework using historical periods as ground truth.

No implementation in this phase; just the file scaffolding and an `agent/predictive/README.md` documenting how the existing tooling (hypothesis generator, anomaly explainer) feeds the future model.

### Phase 5 milestone

For any corridor in the "top movers" of Phase 3, click a "Why is this moving?" button on the brief. A new card slides out with 3 hypotheses, each with a confidence and a "test this hypothesis" button. Click one and the agent runs the falsifying query, updates the confidence, and explains the result.

---

## Phase 6 — Evaluation, safety, exportable reports

**Goal**: Make the AI subsystem reproducible, auditable, and usable for academic / committee output.

### P6.1 Comprehensive eval harness

- Extend the golden-lane set to ~50 corridors and ~15 countries covering all `cvs_mode` values, all market_presence values, and edge cases (zero notifications, IDR > 1, etc.).
- A second eval set for Q&A: 25 reference questions with required tool calls and minimum-mention key terms in the answer.
- `backend/script/eval_agent.py` runs the suite and writes `backend/script/output/agent_eval_YYYYMMDD.json` with per-case pass/fail, latency, cost, and a CSV ready for a "Did the agent regress?" review.

### P6.2 Hallucination dashboard

Admin UI tab `/dashboard/admin/agent` shows:

- Daily cost ledger by provider, model, use case.
- Verifier failure rate over time (and which use case is regressing).
- Top failing eval cases for the last 7 days.
- A "rerun selected briefs" button to manually invalidate cached outputs.

### P6.3 Exportable briefs

- "Export as PDF" button on every BriefCard. Renders via `react-pdf` or a server-side puppeteer; choice deferred until UX review.
- Includes the brief body, the cited signals as a table, and a footer with the snapshot hash, model id, and timestamp.
- Suitable for inclusion in a researcher's paper or committee briefing.

### P6.4 Public methodology page

A new `/dashboard/lab/agent` page documents the AI subsystem itself: which tools the agent has, what prompts it uses, how reflection works, how costs are managed. Pulls from the same markdown files that define the system prompts so the doc never drifts from the implementation.

### Phase 6 milestone

Run `python -m script.eval_agent` and get a green report: all 50 lane briefs and 15 country briefs pass verification, Q&A eval passes 22 of 25 reference questions, total cost is under $0.50. The admin dashboard shows zero verifier failures over the last 24h.

---

## Files touched

**Backend** (`backend/defensefood/`):

- `pyproject.toml` — Phase 1 adds `anthropic`, `openai`, `httpx`, `tenacity`, `pydantic-settings`.
- `agent/` — new package (provider, tools, runner, cache, audit, prompts/). Phases 1-5 land sub-modules: `briefs/lane_brief.py`, `briefs/country_brief.py`, `briefs/period_shift.py`, `qa/runner.py`, `predictive/` scaffold.
- `api/routers/agent.py` — new router. Phase 1 adds `lane-brief` and `evidence` endpoints; later phases add `country-brief`, `period-shift`, `qa`, `counterfactual`, `explain-anomaly`.
- `api/main.py` — register the new router with the existing `app.include_router(agent.router, prefix="/api/v1")` pattern.
- `api/dependencies.py` — call `agent.cache.init_db()` from the FastAPI `lifespan` after the existing data load.

**Frontend** (`food-defence/`):

- `package.json` — Phase 1 adds `react-markdown`, `streamdown`, `remark-gfm`.
- `src/lib/agentApi.ts` — new SSE client.
- `src/components/shared/BriefCard.tsx` — new component, used by all brief mounts.
- `src/components/shared/QAPanel.tsx` — Phase 4.
- `src/components/shared/HypothesisCard.tsx` — Phase 5.
- `src/app/dashboard/corridors/[hs]/[dest]/[origin]/page.tsx` — Phase 1 mount.
- `src/app/dashboard/countries/[m49]/page.tsx` — Phase 2 mount.
- `src/app/dashboard/page.tsx` — Phase 3 mount.
- `src/app/dashboard/lab/page.tsx` — Phase 4 (Q&A tab) and Phase 6 (admin tab).

**Database**: `backend/data/agent.db` (SQLite). Schema in `agent/cache.py`; migrations follow plain `CREATE TABLE IF NOT EXISTS` pattern.

**Tests** (`backend/tests/`):

- `test_agent_tools.py` — Phase 1. Tool schemas and execution.
- `test_lane_brief_eval.py` — Phase 1, extended each phase. End-to-end against golden corpus.
- `test_provider.py` — Phase 1. Mock both SDKs and assert provider abstraction parity.
- `eval/` — JSONL golden sets growing each phase.

---

## Verification

**Phase 1**:

- `pytest tests/test_agent_tools.py tests/test_lane_brief_eval.py` — all green; eval cases pass within 60s combined.
- `curl 'http://localhost:8000/api/v1/agent/lane-brief/30771/380/724?stream=false' | jq '.headline, .key_signals[0]'` — verified `CitedSignal` with `value` matching the engine.
- Manual: open the Lane forensic report, brief streams in under 6s on first call and under 500ms on cache hit.

**Phase 2**:

- `pytest tests/test_country_brief_eval.py` — all green.
- Manual: country page brief covers both inbound and outbound halves; "Show evidence" reveals both sub-agent traces.

**Phase 3**:

- `curl 'http://localhost:8000/api/v1/agent/period-shift?period_b=2023&period_a=2022' | jq '.top_risers | length'` — non-empty.
- Manual: `/dashboard` shows the period shift brief above the priority queue; framing is research / diagnostic, no "this week" language.

**Phase 4**:

- TestClient: POST a research question to `/api/v1/agent/qa`, the response carries a typed `plan`, executed tool results, and a composed answer. Conversation memory persists across two follow-up POSTs.
- Manual: ask the seven starter prompts; each returns a coherent answer with the trace expander populated.

**Phase 5**:

- Manual: from any period-shift "top mover", click "Why is this moving?", get 3 hypotheses; click "test" on one and see the confidence update.
- `curl 'http://localhost:8000/api/v1/agent/counterfactual' --json '{"alpha_decay": 0.7}'` — narrates top 10 movers.

**Phase 6**:

- `python -m script.eval_agent` — all golden cases pass verification, total cost ≤ $1.00.
- Manual: admin dashboard shows zero verifier failures; export-as-PDF produces a valid file with citations.

**End-to-end smoke** (run after every phase):

- `cd food-defence && npx tsc --noEmit` → zero errors.
- `cd backend && python -m pytest tests/` → all green.
- Live: open the dashboard, exercise the new tile, confirm cost ledger updated.

---

## Out of scope (or future epics)

- **Predictive subsystem implementation**. Phase 5 scaffolds the package and feeds it labels through hypothesis testing, but training and deploying a forecaster is its own epic.
- **Multilingual briefs**. English only; localisation is non-trivial because the catalogue's `advice` and `when_matters` text would also need translation.
- **Real-time alerting**. The corpus lags reality by 1 to 2 years; nothing in this plan is operational.
- **Fine-tuning a custom model**. Off-the-shelf Claude and GPT-5 with tool use cover the use cases. Revisit only if eval shows systematic regressions on a recurring pattern that prompt engineering cannot fix.
- **Voice / dictation interfaces**. Browser text UI only.
- **Cross-corpus reasoning**. Each agent call is scoped to the loaded snapshot (the EU food fraud corpus). Comparing to non-RASFF data (e.g. USDA fraud cases) is out of scope.
- **Public API**. The agent endpoints are intended for the dashboard frontend and authenticated researchers. Exposing them to third-party API consumers requires a rate-limit and auth layer beyond this plan.

