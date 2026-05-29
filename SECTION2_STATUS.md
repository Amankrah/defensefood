# Section 2 — Commodity Dependency Models: Integration Status

Status of the first substantive model block (PDF §2.1–2.7) across the Rust engine,
Python orchestration, API, and frontend. The model is **functionally complete and
integrated end-to-end**, currently running in **trade-only mode** (DS' = M − X). The
remaining work is about *data completeness and fidelity*, not model wiring.

Last verified: 2026-05-28 — 19/19 Rust dependency tests pass, 24/24 Python tests pass,
live API serves populated dependency + CVS.

---

## Verdict by layer

| Layer | Status | Notes |
|-------|--------|-------|
| Rust engine (Eqs. 2–9) | ✅ Complete | All 7 formulas + ΔS; 19 unit tests; matches PDF worked example |
| Python wrapper | ✅ Complete | `DependencyEngine.compute_all` (ΔS wired) |
| Data inputs — trade | ✅ Working | Comtrade all-pairs CSV; auto-fallback load |
| Data inputs — FAOSTAT | ⏳ Plumbed, awaiting files | Loader + concordance done; bulk CSVs not yet on disk |
| Batch pipeline | ✅ Complete | `run_dependency_pipeline` with pre-computed HHI |
| Startup enrichment | ✅ Complete | Every corridor gets SCI/IDR/OCS/BDI/HHI/SSR + CRS |
| Scoring (Section 7 CVS) | ✅ Complete | Relaxed SCI+HIS; full SCI·CRS·HIS when FAOSTAT lands |
| Network (Section 6) | ✅ Real BDI | Computed BDI + bilateral weight (severity fallback) |
| API | ✅ Complete | List/top dependency fields; `sort_by=sci\|bdi\|idr`; `/full` reads pre-computed |
| Frontend | ✅ Renders, ⏳ new flags | Consumes dependency + CVS; `cvs_mode`/`idr_gt_1`/`provenance` not yet typed |

---

## ✅ Implemented & verified

**Rust engine** (`crates/defensefood_core/src/dependency/`)
- All 7 Section 2 formulas: `compute_supply_balance` (DS', with ΔS), `compute_idr`,
  `compute_ocs`, `compute_bdi`, `compute_hhi`, `compute_ssr`, `compute_sci` /
  `compute_sci_normalised`, plus `compute_ocs_shares`.
- Boundary handling: NaN on DS'≤0 and zero denominators.
- 19 unit tests incl. Belgium-flaxseed worked example
  (DS'=11000, IDR≈1.091, OCS≈0.667, HHI≈0.490, SCI≈1.084, SCI_norm≈0.542).

**Python integration** (built in the integration pass)
- ΔS wired through the wrapper — `backend/defensefood/core.py`
  (`DependencyEngine.compute_all(..., delta_stocks_kg=0.0)`).
- Canonical HS/CPC normalization + HS→CPC concordance —
  `backend/defensefood/ingestion/hs_codes.py`
  (`normalize_hs`, `normalize_cpc`, `cpc_for_hs`, `load_hs_cpc_concordance`).
  Zero-pad fix (`30617`→`030617`, CPC `1929`→`01929`) raised RASFF coverage 12/34 → 34/34.
- FAOSTAT bulk loader (QCL production + FBS supply/population, CPC→HS join, unit
  conversion, graceful empty fallback) — `backend/defensefood/ingestion/faostat.py`
  (`load_faostat_store`, `FaostatStore`).
- Trade load fallback to newest all-pairs CSV — `backend/defensefood/ingestion/comtrade.py`
  (`load_merged_trade_data`).
- Batch dependency pipeline + reporter-level HHI pre-computed once + `provenance`
  + `idr_gt_1` flag — `backend/defensefood/pipeline/dependency_pipeline.py`
  (`run_dependency_pipeline`, `TradeAggregates`).
- Consumption / CRS pipeline (Section 3) — `backend/defensefood/pipeline/consumption_pipeline.py`
  (`compute_crs_lookup`).
- Startup enrichment of every corridor — `backend/defensefood/api/dependencies.py`
  (`_enrich_dependency_consumption`); uses the trade YEAR, not the RASFF YYYYMM.
- Relaxed CVS (SCI+HIS base when CRS absent, full SCI·CRS·HIS when present;
  `cvs_mode` tag) — `backend/defensefood/pipeline/scoring_pipeline.py`.
- Real BDI in the network model — `backend/defensefood/pipeline/network_pipeline.py`,
  `backend/defensefood/api/routers/network.py`.
- API surfacing: list/top carry dependency fields, `sort_by=sci|sci_norm|bdi|idr`,
  `/full` reads pre-computed dependency from state — `backend/defensefood/api/routers/corridors.py`.
- All-partners Comtrade fetch (full partner breakdown per reporter+HS → complete
  OCS/HHI denominators) — `backend/script/fetch_comtrade_pipeline.py`
  (`run_all_partners_pipeline`, `fetch_all_partner_trade`, `_clean_all_partners_response`,
  `--all-partners` CLI, separate resume checkpoint). The dependency loader prefers the
  resulting `comtrade_all_partners_*.csv` over the curated pairs file —
  `backend/defensefood/ingestion/comtrade.py`. *Code complete; the actual fetch run is
  pending (needs a Comtrade key + network — see Blocked).*
- Test suite (27 tests, all pass) — `backend/tests/` (HS codes, dependency worked
  example + batch, FAOSTAT loader, consumption, scoring gating, all-partners fetch
  (mocked), live API integration).

---

## ⏳ Pending (code work remaining)

- [x] **All-partners Comtrade pull** — *code complete* in
  `backend/script/fetch_comtrade_pipeline.py` (`--all-partners`). Fetches each EU27
  reporter's full partner breakdown per HS so OCS/HHI denominators are complete; loader
  prefers `comtrade_all_partners_*.csv`. **Still must be RUN** (Comtrade key + network) —
  see Blocked.
- [ ] **HS rollup in trade aggregation** — `dependency_pipeline.py` `TradeAggregates`:
  currently exact normalized-HS match, so a 4-digit corridor (`1006`) won't aggregate
  6-digit trade children (`100630`). Decide a rollup policy and apply consistently to
  imports/exports/HHI.
- [ ] **FAOSTAT period fallback** — `faostat.py` / enrichment: FBS/QCL often lag the
  trade year (trade 2023 vs FAOSTAT 2022). Add nearest-available-year fallback.
- [ ] **ΔS data source** — `delta_stocks_kg` is plumbed but always 0. Map FAOSTAT FBS
  "Stock Variation" element to enable full Eq. 1 (vs Eq. 2 P+M−X).
- [ ] **Dependency manifests** — `backend/script/requirements.txt` only covers the fetch
  pipeline. Add / split: `fastapi`, `uvicorn`, `pydantic`, `maturin` (api) and `pytest`,
  `httpx` (dev).
- [ ] **Frontend types/UX for new fields** — `food-defence/src/lib/types.ts`: add
  `cvs_mode`, `idr_gt_1`, `provenance`; optional UI (IDR>1 badge, "trade-only" label,
  SCI column in the list table). Backend already emits these.
- [ ] **Tests for the above** — all-partners OCS correctness; FAOSTAT period-fallback;
  HS-rollup aggregation.

---

## 🔒 Blocked / needed (external data + ops, not code)

- [ ] **FAOSTAT bulk CSVs** → place QCL ("Crops and livestock products") + FBS ("Food
  Balance Sheets") bulk downloads in `backend/data/faostat/` (or set
  `DEFENSEFOOD_FAOSTAT_DIR`). Flips provenance `trade_only`→`faostat`, activates real
  DS'/SSR/CRS, and upgrades CVS to `sci_crs_his`. The loader logs the exact path it scans.
- [~] **All-partners Comtrade fetch — IN PROGRESS** (see the dedicated section below
  for live status + resume steps). Code is complete and hardened; remaining work is just
  running it across quota windows.

---

## ▶️ All-partners Comtrade fetch — status & resume (2026-05-29)

Fetches each EU27 reporter's FULL import/export partner breakdown per HS code, so the
Section 2 OCS/HHI denominators are complete (not limited to the curated RASFF pairs).
The dependency loader auto-prefers the resulting `comtrade_all_partners_*.csv`.

### Current state

- Checkpoint `output/all_partners_checkpoint.json` (run_id `20260529_052915`): **2022 only**,
  scoped to the **35 RASFF HS codes**, **205 / 945 jobs done, 0 failed**, ~16.5k records in
  `comtrade_all_partners_2022_20260529_052915.csv`.
- With this partial data the loader already lifted corridors-with-SCI/CVS from **63 → 163**,
  and OCS/HHI now span ~209 partners (unbiased), including seafood.
- The older `comtrade_all_partners_2022_2023_20260528_131721.csv` is a pre-fix partial
  (no leading-zero seafood/spice codes); it is **orphaned** — the loader ignores it
  (older mtime). Safe to delete.

### To continue (re-run each time quota replenishes)

```
cd backend/script
python fetch_comtrade_pipeline.py --all-partners --resume
```

- Scope (35 codes) and year (2022) are **sticky in the checkpoint** — no flags needed.
- Skips completed jobs, retries transient `429`s with backoff, stops cleanly on the `403`
  daily-quota cap. Repeat until it prints `COMPLETE`, then restart the API.
- Optional ~2× speedup: add `--combine-flows` (one call per reporter/HS; test once in case
  the tier rejects `flowCode=M,X`).

### Two known limits

- Comtrade enforces a burst `429` (retried automatically) AND a daily call-volume `403`
  (clean stop → `--resume`). A 403 message includes when quota replenishes.
- HS codes MUST be zero-padded for chapters 01–09 (e.g. `030731`, not `30731`) or Comtrade
  returns nothing — handled by `normalize_hs_code` in `hs_codes_loader.py`.

### Extending to 2023 later

A clean run `--all-partners --rasff-hs --years 2022,2023` (years combined into one call)
produces a single both-years file that replaces the 2022-only one (the loader keeps a single
all-partners file; don't mix).

---

## 🔒 Build / CI (ops, not code)

- [ ] **CI / build hygiene** — pin `PYO3_PYTHON` to the venv (the repo's configured
  `Python313` interpreter is gone) and add a workflow: maturin build → `cargo test` →
  `pytest`.

---

## File map

```
crates/defensefood_core/src/dependency/   # Rust: supply_balance, ratios, concentration, criticality
backend/defensefood/core.py                # DependencyEngine wrapper (ΔS wired)
backend/defensefood/ingestion/hs_codes.py  # HS/CPC normalization + concordance
backend/defensefood/ingestion/faostat.py   # FAOSTAT bulk loader (QCL + FBS)
backend/defensefood/ingestion/comtrade.py  # trade load + fallback
backend/defensefood/pipeline/dependency_pipeline.py   # batch Section 2
backend/defensefood/pipeline/consumption_pipeline.py  # Section 3 CRS
backend/defensefood/pipeline/scoring_pipeline.py      # Section 7 CVS (relaxed)
backend/defensefood/pipeline/network_pipeline.py      # Section 6 BDI
backend/defensefood/api/dependencies.py    # startup enrichment
backend/defensefood/api/routers/corridors.py          # list/top/full surfacing
backend/unique_commodities_hs_cpc.csv      # HS→CPC concordance (719 rows)
backend/script/fetch_comtrade_pipeline.py  # all-partners fetch (--all-partners, --rasff-hs)
backend/tests/                             # pytest suite (32 tests)
```

---

## How to run / test

```bash
# Build the Rust extension into the venv (once / after Rust changes)
PYO3_PYTHON=backend/venv/Scripts/python.exe maturin develop

# Rust unit tests
PYO3_PYTHON=backend/venv/Scripts/python.exe cargo test -p defensefood_core dependency

# Python tests (run from backend/)
cd backend && venv/Scripts/python.exe -m pytest

# Serve the API
cd backend && venv/Scripts/python.exe -m uvicorn defensefood.api.main:app --reload
```

## Enabling full FAOSTAT mode

1. Download FAOSTAT bulk CSVs (All Data Normalized): QCL and FBS domains.
2. Place them in `backend/data/faostat/` (filenames containing `production`/`qcl` and
   `food_balance`/`fbs` are auto-detected) or set `DEFENSEFOOD_FAOSTAT_DIR`.
3. Restart the API. Provenance switches to `faostat`, SSR/CRS populate, and CVS upgrades
   to `sci_crs_his`. No code change required.

## CVS modes

- `sci_crs_his` — full hybrid `SCI·CRS·(1 + w_h·HIS)/(1+w_h)` (needs FAOSTAT FBS for CRS).
- `sci_his` — relaxed base `SCI·(1 + w_h·HIS)/(1+w_h)` when CRS is absent (current default
  in trade-only mode).
- `null` — corridor lacks SCI or HIS; left unscored (`cvs_hazard_only` still exposes the
  HIS percentile).
