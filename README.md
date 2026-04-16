# DefenseFood

**EU Food Fraud Vulnerability Intelligence System**

Quantitative models for commodity dependency, origin-attention country trade relationships, and hazard-trade corridor integration. Implements the [Mathematical Framework v1.0](backend/blueprint/Mathematical_Framework_Food_Fraud_v1.0%20(1).pdf) (43 formulas across 7 model groups).

---

## Architecture

```
┌─────────────────┐     ┌──────────────────────────┐     ┌──────────────┐
│  Next.js Frontend│────▶│  FastAPI (Python)         │────▶│  Rust Engine │
│  (React 19 / TS) │◀────│  Ingestion & Orchestration│◀────│  (PyO3)      │
└─────────────────┘     └──────────────────────────┘     └──────────────┘
        :3000                    :8000                    defensefood_core
```

| Layer | Technology | Responsibility |
|-------|-----------|----------------|
| **Rust Engine** | PyO3 + Maturin | All 43 mathematical formulas, normalisation, graph algorithms |
| **Python Backend** | FastAPI + pandas | Data ingestion (Comtrade, RASFF, FAOSTAT), orchestration, REST API |
| **Frontend** | Next.js 15 + TailwindCSS | Dashboard, corridor explorer, vulnerability visualisation |

### Data Sources

| Source | Provides | Used By |
|--------|----------|---------|
| UN Comtrade | Bilateral trade flows (M, V, X) | Sections 2, 5, 6 |
| RASFF Window | Hazard notifications, classifications | Sections 4, 6 |
| FAOSTAT / Eurostat | Production, consumption, population | Sections 2, 3 |

---

## Project Structure

```
defensefood/
├── Cargo.toml                          # Rust workspace manifest
├── pyproject.toml                      # Maturin build config
│
├── crates/defensefood_core/            # Rust computation engine
│   └── src/
│       ├── lib.rs                      # PyO3 module entry point
│       ├── types.rs                    # TradeRecord, RasffNotification, enums
│       ├── dependency/                 # Section 2: IDR, OCS, BDI, HHI, SSR, SCI
│       ├── consumption/                # Section 3: PCC, CRS, DIS
│       ├── hazard/                     # Section 4: Severity, HIS, HDI, DGI
│       ├── trade_flow/                 # Section 5: UV z-scores, MTD, volume anomaly
│       ├── network/                    # Section 6: Exposure graph, ORPS, ACEP
│       ├── scoring/                    # Section 7: Normalisation, composite CVS
│       └── stats/                      # Shared: z-score, rolling window, entropy
│
├── backend/
│   ├── defensefood/
│   │   ├── core.py                     # Python wrappers over Rust engine
│   │   ├── ingestion/                  # Data loaders: Comtrade, RASFF, FAOSTAT
│   │   ├── models/                     # Pydantic request/response models
│   │   ├── pipeline/                   # Orchestration: data -> Rust -> results
│   │   └── api/                        # FastAPI app + routers
│   └── script/                         # Legacy data-fetching scripts (preserved)
│
└── food-defence/                       # Next.js frontend
    └── src/
        ├── lib/api.ts                  # Typed API client
        └── app/
            ├── dashboard/page.tsx      # Vulnerability dashboard
            └── architecture/page.tsx   # System architecture diagram
```

---

## Mathematical Framework

The system implements 7 model groups from the framework document:

### Section 2 -- Commodity Dependency Models
Measures how structurally dependent a country is on a specific origin for a commodity.

| Metric | Formula | Description |
|--------|---------|-------------|
| DS' | P + M - X | Apparent domestic supply |
| IDR | M / DS' | Import Dependency Ratio |
| OCS | M(c,i,j) / M(c,i,*) | Origin Country Share |
| BDI | M(c,i,j) / DS' | Bilateral Dependency Index (= IDR x OCS) |
| HHI | sum(OCS^2) | Herfindahl-Hirschman concentration index |
| SSR | P / D | Self-Sufficiency Ratio |
| SCI | IDR x OCS x (1+HHI) | Supply Criticality Index |

### Section 3 -- Consumption Demand Modelling
Captures how important a commodity is to a country's food system.

| Metric | Formula | Description |
|--------|---------|-------------|
| PCC | D / Pop | Per Capita Apparent Consumption |
| CRS | 1 - (Rank-1)/(C-1) | Commodity Consumption Rank Score |
| DIS | 1 - min(CV, 1) | Demand Inelasticity Score |

### Section 4 -- Hazard Signal Modelling (RASFF Integration)
Integrates RASFF notification data with trade corridors.

| Metric | Formula | Description |
|--------|---------|-------------|
| S(r) | W_class x W_risk | Notification Severity Weight |
| HIS | sum(S(r) x alpha^(t-t_r)) | Hazard Intensity Score (time-decayed) |
| HDI | -sum(p_h ln p_h) / ln(H) | Hazard Diversity Index (Shannon entropy) |
| DGI | trade_share - notif_share | Detection Gap Indicator |

### Section 5 -- Trade Flow Analysis
Detects anomalies in trade patterns that may indicate fraud.

| Metric | Formula | Description |
|--------|---------|-------------|
| UV | V / M | Unit Value (price proxy) |
| Z_UV | (UV - mean) / std | Price anomaly z-score |
| Z_M | rolling z-score | Volume anomaly detection |
| MTD | \|M_i - X_j\| / max(M_i, X_j) | Mirror Trade Discrepancy |

### Section 6 -- Origin-Attention Country Relationship Model
Network analysis of hazard propagation across the EU trade system.

| Metric | Formula | Description |
|--------|---------|-------------|
| ORPS | sum(BDI x HIS x PCC) | Origin Risk Propagation Score |
| ACEP | sum(BDI x HIS x CRS) | Attention Country Exposure Profile |

### Section 7 -- Composite Vulnerability Scoring
Normalises and combines all sub-scores into a final vulnerability score.

| Approach | Description |
|----------|-------------|
| Weighted Linear | Compensatory: high in one metric offsets low in another |
| Geometric Mean | Non-compensatory: any zero component zeroes the score |
| Hybrid | SCI x CRS x (1 + w_h*HIS + w_p*PAS + w_sc*SCCS) |

---

## Getting Started

### Prerequisites

- **Rust** (stable, 2021 edition) -- [rustup.rs](https://rustup.rs)
- **Python** >= 3.10
- **Node.js** >= 20
- **Maturin** (`pip install maturin`)

### Setup

```bash
# Clone and enter the project
git clone <repo-url>
cd defensefood

# 1. Create Python virtual environment
python3 -m venv backend/.venv
source backend/.venv/bin/activate

# 2. Install Python dependencies
pip install maturin numpy pandas fastapi uvicorn pydantic openpyxl python-dotenv requests

# 3. Build the Rust extension into the venv
maturin develop --release

# 4. Verify the Rust module loads
python -c "import defensefood_core; print(dir(defensefood_core))"

# 5. Install frontend dependencies
cd food-defence && npm install && cd ..
```

### Running

```bash
# Terminal 1: FastAPI backend
source backend/.venv/bin/activate
cd backend
PYTHONPATH=. uvicorn defensefood.api.main:app --reload --port 8000

# Terminal 2: Next.js frontend
cd food-defence
npm run dev
```

- **API docs**: http://localhost:8000/docs
- **Dashboard**: http://localhost:3000/dashboard

---

## API Endpoints

Base URL: `http://localhost:8000/api/v1`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Liveness check, Rust module version |
| GET | `/corridors` | List corridors with filtering |
| GET | `/corridors/top?n=50&sort_by=his` | Top N by vulnerability metric |
| GET | `/corridors/{hs}/{dest}/{origin}` | Full corridor profile |
| GET | `/corridors/{hs}/{dest}/{origin}/hazard` | Hazard metrics only |
| GET | `/countries` | List countries (optional `?eu_only=true`) |
| GET | `/countries/{m49}` | Country detail with corridor counts |
| GET | `/countries/{m49}/exposure-profile` | Inbound corridor exposure |
| GET | `/commodities` | List tracked HS codes |
| GET | `/commodities/{hs_code}` | Corridors for a commodity |
| GET | `/hazards/summary` | RASFF ingestion summary |
| GET | `/hazards/types` | The 6 hazard categories |
| GET | `/scoring/config` | Current scoring parameters |
| PUT | `/scoring/config` | Update scoring parameters |
| POST | `/scoring/recalculate` | Trigger full re-scoring |
| GET | `/network/summary` | Exposure network stats |
| GET | `/network/origins` | Origins ranked by total hazard |

---

## Development

### Rust Tests

```bash
# Run all 75 unit tests
cargo test

# Tests validate against the PDF worked example (p.9):
# DS'=11000, IDR=1.091, OCS=0.667, HHI=0.490, SCI=1.084
```

### Rebuild After Rust Changes

```bash
source backend/.venv/bin/activate
maturin develop --release
```

### Project Statistics

| Component | Count |
|-----------|-------|
| Rust source files | 28 |
| Rust unit tests | 75 |
| Python modules | 22 |
| FastAPI routers | 7 |
| API endpoints | 17 |
| Framework formulas implemented | 43 |
| RASFF notifications processed | 1,746 |
| Trade corridors scored | 638 |
| Exposure network nodes | 60 |

---

## Data Pipeline

```
RASFF Excel ──────▶ extract_corridors() ──▶ build_notifications() ──▶ Rust HIS/HDI/DGI
                                                                          │
UN Comtrade CSV ──▶ load_merged_trade() ──▶ Rust HHI/UV z-scores ◀───────┘
                                                   │
FAOSTAT (future) ─▶ production/consumption ──▶ Rust IDR/OCS/BDI/SCI
                                                   │
                                          normalise_corridor_scores()
                                                   │
                                          compute_composite_scores()
                                                   │
                                              FastAPI ──▶ Next.js Dashboard
```

---

## License

This project is part of the EU Food Fraud Vulnerability Intelligence System research.
