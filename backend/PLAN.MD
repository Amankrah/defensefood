# DefenseFood: Rust + PyO3/Maturin Architecture Plan

## Context

The EU Food Fraud Vulnerability Intelligence System needs to implement a 24-page mathematical framework (v1.0, ~43 formulas across 7 model groups) that scores trade corridors for fraud vulnerability. The current codebase has Python scripts fetching UN Comtrade data and running basic analytics, plus a bare Next.js frontend. The goal is to build a **Rust computation engine** (via PyO3/Maturin) for all math, with **Python handling data ingestion/orchestration** and **FastAPI serving the Next.js frontend**.

---

## 1. Monorepo Directory Structure

```
defensefood/
├── Cargo.toml                              # Workspace manifest
├── pyproject.toml                          # Maturin build config
│
├── crates/
│   └── defensefood_core/                   # Rust PyO3 crate
│       ├── Cargo.toml
│       ├── src/
│       │   ├── lib.rs                      # #[pymodule] entry point
│       │   ├── types.rs                    # CorridorKey, TradeRecord, RasffNotification, etc.
│       │   ├── error.rs                    # Error types -> Python exceptions
│       │   ├── dependency/                 # Sec 2: DS', IDR, OCS, BDI, HHI, SSR, SCI
│       │   │   ├── mod.rs
│       │   │   ├── supply_balance.rs       # Eq. 1-2
│       │   │   ├── ratios.rs              # Eq. 3-6, 8
│       │   │   ├── concentration.rs       # Eq. 7 (HHI)
│       │   │   └── criticality.rs         # Eq. 9 (SCI)
│       │   ├── consumption/               # Sec 3: PCC, CRS, DIS
│       │   │   ├── mod.rs
│       │   │   ├── apparent.rs            # Eq. 10
│       │   │   ├── rank.rs               # Eq. 11
│       │   │   └── inelasticity.rs        # Eq. 12-13
│       │   ├── hazard/                    # Sec 4: Severity, HIS, HDI, DGI
│       │   │   ├── mod.rs
│       │   │   ├── severity.rs            # Eq. 14
│       │   │   ├── intensity.rs           # Eq. 15-16 (temporal decay)
│       │   │   ├── diversity.rs           # Eq. 17-18 (Shannon entropy)
│       │   │   └── detection_gap.rs       # Eq. 19
│       │   ├── trade_flow/                # Sec 5: UV z-scores, volume anomaly, MTD, shifts
│       │   │   ├── mod.rs
│       │   │   ├── unit_value.rs          # Eq. 20-23
│       │   │   ├── volume_anomaly.rs      # Eq. 24-26
│       │   │   ├── mirror.rs             # Eq. 27
│       │   │   └── concentration_shift.rs # Eq. 28-29
│       │   ├── network/                   # Sec 6: Exposure graph, ORPS, ACEP
│       │   │   ├── mod.rs
│       │   │   ├── graph.rs              # petgraph DiGraph (Eq. 30-32)
│       │   │   ├── orps.rs              # Eq. 33
│       │   │   ├── acep.rs              # Eq. 34
│       │   │   └── probability.rs        # Eq. 35
│       │   ├── scoring/                   # Sec 7: Normalisation, composition, weights
│       │   │   ├── mod.rs
│       │   │   ├── normalisation.rs       # Eq. 36-38
│       │   │   ├── composition.rs         # Eq. 39-41
│       │   │   └── weights.rs            # Eq. 42-43
│       │   └── stats/                     # Shared utilities
│       │       ├── mod.rs
│       │       ├── zscore.rs
│       │       ├── rolling.rs
│       │       └── entropy.rs
│       └── tests/
│           ├── test_dependency.rs         # Validates against PDF worked example (p.9)
│           ├── test_hazard.rs
│           ├── test_trade_flow.rs
│           ├── test_network.rs
│           └── test_scoring.rs
│
├── backend/
│   ├── pyproject.toml                     # Python package config
│   ├── defensefood/
│   │   ├── __init__.py
│   │   ├── core.py                        # Python wrappers: DependencyEngine, HazardEngine, etc.
│   │   ├── ingestion/                     # Data loading (refactored from script/)
│   │   │   ├── __init__.py
│   │   │   ├── comtrade.py               # From comtrade_fetcher.py
│   │   │   ├── rasff.py                  # RASFF Excel -> corridor extraction
│   │   │   ├── faostat.py                # Production & consumption data
│   │   │   ├── hs_codes.py              # From hs_codes_loader.py
│   │   │   └── countries.py             # From country_loader.py (M49 mappings)
│   │   ├── models/                        # Pydantic request/response models
│   │   │   ├── trade.py
│   │   │   ├── rasff.py
│   │   │   ├── scores.py
│   │   │   └── network.py
│   │   ├── pipeline/                      # Orchestration: data -> Rust -> results
│   │   │   ├── dependency_pipeline.py
│   │   │   ├── hazard_pipeline.py
│   │   │   ├── trade_flow_pipeline.py
│   │   │   ├── network_pipeline.py
│   │   │   └── scoring_pipeline.py
│   │   └── api/                           # FastAPI app
│   │       ├── main.py
│   │       ├── dependencies.py
│   │       └── routers/
│   │           ├── corridors.py           # /api/v1/corridors/*
│   │           ├── commodities.py         # /api/v1/commodities/*
│   │           ├── countries.py           # /api/v1/countries/*
│   │           ├── hazards.py             # /api/v1/hazards/*
│   │           ├── scores.py             # /api/v1/scores/*
│   │           ├── network.py            # /api/v1/network/*
│   │           └── health.py
│   ├── script/                            # Existing scripts (preserved, untouched)
│   └── tests/
│
├── food-defence/                          # Existing Next.js frontend
└── docs/
```

---

## 2. Rust Crate Design (`defensefood_core`)

### Dependencies
```toml
pyo3 = { version = "0.22", features = ["extension-module"] }
numpy = "0.22"          # Zero-copy numpy array interop
ndarray = "0.16"         # Matrix operations
petgraph = "0.6"         # Directed graph for exposure network
ordered-float = "4.0"    # Sortable floats for percentile rank
thiserror = "2.0"        # Error types
```

### Data Transfer Patterns (Python <-> Rust)

| Pattern | When | Example |
|---------|------|---------|
| **Scalar f64** | Single corridor metrics | `compute_sci(idr, ocs, hhi) -> f64` |
| **Numpy arrays** | Batch normalisation, z-scores | `normalise_percentile_rank(values: PyReadonlyArray1<f64>) -> PyArray1<f64>` |
| **PyO3 structs** | Notification lists for HIS | `compute_his(notifications: Vec<RasffNotification>, ...)` |
| **Opaque Rust object** | Exposure network graph | `ExposureNetwork` wraps petgraph, queried via methods |

### Key Design Decision
**Aggregation stays in Python (pandas groupby), formulas live in Rust.** Python pre-computes M(c,i,*,t) from raw records and passes the scalar to Rust's `compute_idr()`. This avoids reimplementing groupby in Rust.

---

## 3. PyO3 Module Structure

Python sees: `defensefood_core.dependency`, `.consumption`, `.hazard`, `.trade_flow`, `.network`, `.scoring`

Each submodule exposes `#[pyfunction]` entries. The `network` submodule also exposes `ExposureNetwork` as a `#[pyclass]` with `#[pymethods]` for `add_trade_edge()`, `compute_orps()`, `compute_acep()`.

Python wrapper (`backend/defensefood/core.py`) provides engine classes:
- `DependencyEngine` -- `compute_all(P, M_total, X_total, M_bilateral) -> dict`
- `ConsumptionEngine` -- `compute_pcc()`, `compute_crs_batch()`, `compute_dis()`
- `HazardEngine` -- `compute_his()`, `compute_hdi()`, `compute_dgi()`
- `TradeFlowEngine` -- `unit_value_zscores()`, `volume_anomaly()`, `mirror_discrepancy()`
- `NetworkEngine` -- wraps `ExposureNetwork` creation and queries
- `ScoringEngine` -- `normalise()`, `composite_score()`

---

## 4. FastAPI Endpoints

Base: `http://localhost:8000/api/v1`

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Liveness + Rust module version |
| `GET /corridors?commodity=&country=&min_score=` | List corridors with filters |
| `GET /corridors/{hs}/{dest}/{origin}` | Full corridor profile (all metrics) |
| `GET /corridors/{hs}/{dest}/{origin}/dependency` | Section 2 metrics |
| `GET /corridors/{hs}/{dest}/{origin}/hazard` | Section 4 metrics |
| `GET /corridors/{hs}/{dest}/{origin}/trade-anomalies` | Section 5 metrics |
| `GET /corridors/top?n=50&sort_by=cvs` | Top N by vulnerability score |
| `GET /countries/{m49}/exposure-profile` | ACEP |
| `GET /origins/{m49}/risk-propagation` | ORPS |
| `GET /commodities/{hs}/dependency-map` | IDR, HHI, SSR across EU |
| `GET /network/graph` | Serialized network for frontend viz |
| `GET /scoring/config` | Current weights/normalisation |
| `PUT /scoring/config` | Update scoring params |
| `POST /scoring/recalculate` | Trigger full re-scoring |
| `POST /ingest/comtrade` | Trigger data fetch |
| `POST /ingest/rasff` | Upload RASFF data |

---

## 5. Implementation Phases

### Phase 1: Foundation (scaffold + first formula end-to-end)
1. Create `Cargo.toml` workspace + `crates/defensefood_core/Cargo.toml`
2. Implement minimal `lib.rs` with `#[pymodule]`
3. Implement `types.rs` with `TradeRecord` as `#[pyclass]`
4. Implement `dependency/concentration.rs` -- `compute_hhi()` (Eq. 7)
5. Write root `pyproject.toml` for maturin
6. Run `maturin develop`, verify `import defensefood_core` works
7. **Validate**: `compute_hhi([0.667, 0.167, 0.125, 0.042])` returns ~0.490 (PDF p.9)

### Phase 2: Dependency + Consumption Models (Sections 2-3)
1. Complete `dependency/` module (supply_balance, ratios, criticality)
2. Implement `consumption/` module (apparent, rank, inelasticity)
3. Implement `stats/` utilities (zscore, rolling, entropy)
4. **Validate**: Worked example from PDF p.9: DS'=11000, IDR=1.091, OCS=0.667, SCI=1.084
5. Create `backend/defensefood/core.py` with DependencyEngine + ConsumptionEngine
6. Refactor ingestion modules from existing scripts

### Phase 3: Hazard Signal Models (Section 4)
1. Implement `hazard/` module (severity, intensity, diversity, detection_gap)
2. Create `ingestion/rasff.py` with corridor extraction + hazard type parsing
3. Create HazardEngine wrapper
4. Write `pipeline/hazard_pipeline.py`
5. **Validate**: Against `updated_data_rasff_window.xlsx` data

### Phase 4: Trade Flow Analysis (Section 5)
1. Implement `trade_flow/` module (unit_value, volume_anomaly, mirror, concentration_shift)
2. Create TradeFlowEngine wrapper
3. Write `pipeline/trade_flow_pipeline.py`
4. **Validate**: UV z-scores against existing `analyze_merged_trade.py` unit value output

### Phase 5: Network Model + FastAPI (Section 6 + API)
1. Implement `network/` module with petgraph (graph, orps, acep, probability)
2. Create ExposureNetwork pyclass
3. Write `pipeline/network_pipeline.py`
4. Set up FastAPI app with all routers
5. Wire data sources to endpoints

### Phase 6: Composite Scoring + Frontend (Section 7 + UI)
1. Implement `scoring/` module (normalisation, composition, weights)
2. Write `pipeline/scoring_pipeline.py`
3. Implement scoring API endpoints
4. Update Next.js frontend with dashboard, corridor table, country drilldown

---

## 6. Testing Strategy

### Rust Unit Tests
- **test_dependency.rs**: PDF worked example (p.9) as ground truth
- **test_hazard.rs**: Severity lookups, HIS temporal decay, HDI boundary cases
- **test_trade_flow.rs**: Known z-scores, MTD symmetry, volume spikes
- **test_scoring.rs**: Min-max on [10,20,30,40,50], geometric mean zero-propagation

### Mathematical Invariants (property-based with `proptest`)
- `sum(OCS) == 1.0`, `HHI in [1/n, 1.0]`, `BDI == IDR * OCS`
- `SCI in [0, 2]`, `HDI_norm in [0, 1]`, `DIS in [0, 1]`, `MTD in [0, 1]`

### Cross-Validation
- Compare Rust HHI output against existing `analyze_merged_trade.py` HHI on `merged_trade_data.csv`
- Compare unit values against `table_unit_values_by_commodity_year.csv`

### Python Integration Tests
- Ingestion: CSV/Excel parsing produces expected records
- Pipeline: End-to-end data -> Rust -> results for one corridor
- API: FastAPI TestClient tests for each router

---

## 7. Build Commands

```bash
# Build Rust extension into Python venv
maturin develop --release

# Verify
python -c "import defensefood_core; print(dir(defensefood_core))"

# Rust tests
cargo test --manifest-path crates/defensefood_core/Cargo.toml

# Python tests
cd backend && pytest tests/

# Run API
uvicorn defensefood.api.main:app --reload --port 8000

# Run frontend
cd food-defence && npm run dev
```

---

## Critical Files

| File | Role |
|------|------|
| `backend/script/analyze_merged_trade.py` | Existing HHI + unit value calcs (validation baseline) |
| `backend/script/comtrade_fetcher.py` | Comtrade API client to refactor |
| `backend/script/country_loader.py` | RASFF parser + M49 codes to refactor |
| `backend/unique_commodities_hs_cpc.csv` | HS code <-> commodity mapping |
| `backend/updated_data_rasff_window.xlsx` | RASFF notification source data |
| `backend/script/output/merged_trade_data.csv` | Existing merged trade data for testing |