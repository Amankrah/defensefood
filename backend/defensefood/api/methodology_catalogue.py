"""
Static catalogue of blueprint metrics exposed via /api/v1/research/methodology.

Each entry carries the plain-language label, abbreviation, LaTeX formula,
blueprint section reference, and the source file/function that implements it.
The frontend Methodology tab renders this verbatim — no recomputation, no
parsing required.
"""

from typing import Any

# Order is deliberate — sections follow the blueprint structure.
METHODOLOGY: list[dict[str, Any]] = [
    # ── Section 2: Commodity Dependency ─────────────────────────────────
    {
        "key": "ds_prime",
        "name": "Apparent domestic supply",
        "abbr": "DS'",
        "section": "2.1",
        "blueprint_eq": "Eq. (2)",
        "formula_latex": r"DS'(c,i,t) = P(c,i,t) + M(c,i,\cdot,t) - X(c,i,\cdot,t)",
        "inputs": ["P (production)", "M (total imports)", "X (total exports)"],
        "definition": (
            "Apparent domestic supply for the commodity in the destination. "
            "Denominator of every downstream dependency metric."
        ),
        "source": "defensefood_core::dependency::compute_supply_balance",
    },
    {
        "key": "idr",
        "name": "Import dependency ratio",
        "abbr": "IDR",
        "section": "2.2",
        "blueprint_eq": "Eq. (3)",
        "formula_latex": r"IDR(c,i,t) = \frac{M(c,i,\cdot,t)}{DS'(c,i,t)}",
        "inputs": ["M (total imports)", "DS' (apparent supply)"],
        "definition": (
            "Share of apparent supply that comes from imports. 0 = self-sufficient, "
            "1 = fully import-dependent, >1 = re-export hub / missing production data."
        ),
        "source": "defensefood_core::dependency::compute_idr",
    },
    {
        "key": "ocs",
        "name": "Origin country share",
        "abbr": "OCS",
        "section": "2.3",
        "blueprint_eq": "Eq. (4)",
        "formula_latex": r"OCS(c,i,j,t) = \frac{M(c,i,j,t)}{M(c,i,\cdot,t)}",
        "inputs": ["M_ij (bilateral imports)", "M (total imports)"],
        "definition": "Share of total imports that comes from this single origin. 0 to 1.",
        "source": "defensefood_core::dependency::compute_ocs",
    },
    {
        "key": "bdi",
        "name": "Bilateral dependency index",
        "abbr": "BDI",
        "section": "2.4",
        "blueprint_eq": "Eq. (5) / (6)",
        "formula_latex": r"BDI(c,i,j,t) = \frac{M(c,i,j,t)}{DS'(c,i,t)} = IDR \cdot OCS",
        "inputs": ["IDR", "OCS"],
        "definition": "Share of domestic supply sourced specifically from this origin.",
        "source": "defensefood_core::dependency::compute_bdi",
    },
    {
        "key": "hhi",
        "name": "Herfindahl-Hirschman concentration",
        "abbr": "HHI",
        "section": "2.5",
        "blueprint_eq": "Eq. (7)",
        "formula_latex": r"HHI(c,i,t) = \sum_{j \in O} OCS(c,i,j,t)^2",
        "inputs": ["OCS_j (origin shares)"],
        "definition": (
            "Supplier concentration across origins. 1/n for n equal suppliers, 1 for a "
            "single supplier. >= 0.25 = highly concentrated."
        ),
        "source": "defensefood_core::dependency::compute_hhi",
    },
    {
        "key": "ssr",
        "name": "Self-sufficiency ratio",
        "abbr": "SSR",
        "section": "2.6",
        "blueprint_eq": "Eq. (8)",
        "formula_latex": r"SSR(c,i,t) = \frac{P(c,i,t)}{D(c,i,t)}",
        "inputs": ["P (production)", "D (food-use domestic supply)"],
        "definition": (
            ">1 net exporter, =1 balanced, <1 imports fill the gap, 0 no domestic production."
        ),
        "source": "defensefood_core::dependency::compute_ssr",
    },
    {
        "key": "sci",
        "name": "Supply criticality index",
        "abbr": "SCI",
        "section": "2.7",
        "blueprint_eq": "Eq. (9)",
        "formula_latex": r"SCI(c,i,j,t) = IDR \cdot OCS \cdot (1 + HHI)",
        "inputs": ["IDR", "OCS", "HHI"],
        "definition": (
            "Core corridor-specific dependency score in [0,2]. The (1+HHI) factor "
            "amplifies vulnerability when the wider supplier market is also concentrated."
        ),
        "source": "defensefood_core::dependency::compute_sci",
    },
    # ── Section 3: Consumption ──────────────────────────────────────────
    {
        "key": "crs",
        "name": "Consumption rank",
        "abbr": "CRS",
        "section": "3",
        "blueprint_eq": "Sec. 3",
        "formula_latex": r"CRS(c,i,t) = \mathrm{rank}_i\left(\mathrm{PCC}(c,i,t)\right)",
        "inputs": ["PCC (per-capita consumption)"],
        "definition": (
            "Population-exposure ranking across destinations for the commodity. "
            "Demand-side amplifier for the priority score."
        ),
        "source": "defensefood_core::consumption::compute_crs_batch",
    },
    # ── Section 4: Hazard ──────────────────────────────────────────────
    {
        "key": "his",
        "name": "Hazard intensity",
        "abbr": "HIS",
        "section": "4.1",
        "blueprint_eq": "Sec. 4.1",
        "formula_latex": (
            r"HIS(c,i,j,t) = \sum_{k} W_{class}(k) \cdot W_{risk}(k) \cdot \alpha^{t - t_k}"
        ),
        "inputs": ["RASFF notifications", "alpha (decay)"],
        "definition": (
            "Severity-weighted, time-decayed RASFF signal on the lane. Recent and serious "
            "notifications dominate."
        ),
        "source": "defensefood_core::hazard::compute_his",
    },
    {
        "key": "hdi",
        "name": "Hazard diversity",
        "abbr": "HDI",
        "section": "4.2",
        "blueprint_eq": "Sec. 4.2",
        "formula_latex": (
            r"HDI = -\sum_{k=1}^{6} p_k \log p_k \big/ \log 6"
        ),
        "inputs": ["Hazard category counts"],
        "definition": "Shannon entropy over six hazard families, normalised to 0-1.",
        "source": "defensefood_core::hazard::compute_hdi",
    },
    {
        "key": "dgi",
        "name": "Detection gap",
        "abbr": "DGI",
        "section": "4.3",
        "blueprint_eq": "Sec. 4.3",
        "formula_latex": (
            r"DGI = \frac{N_{ij}/N_{i\cdot}}{M_{ij}/M_{i\cdot}}"
        ),
        "inputs": ["Notification share", "Trade share"],
        "definition": (
            "Ratio of a lane's notification share to its trade share. <1 = under-reported, >1 over."
        ),
        "source": "defensefood_core::hazard::compute_dgi",
    },
    # ── Section 5: Trade Flow ───────────────────────────────────────────
    {
        "key": "z_uv",
        "name": "Unit-price z-score",
        "abbr": "z(UV)",
        "section": "5.1",
        "blueprint_eq": "Sec. 5.1",
        "formula_latex": r"z_{UV}(c,i,j,t) = \frac{UV_{ij} - \mu_{UV_{i\cdot}}}{\sigma_{UV_{i\cdot}}}",
        "inputs": ["UV = primaryValue / netWgt", "peer mean/std"],
        "definition": (
            "How far this lane's per-kg price deviates from peer partners on the same import market. "
            "|z| > 2 is unusual."
        ),
        "source": "defensefood_core::trade_flow::compute_unit_value_zscore_batch",
    },
    {
        "key": "mtd",
        "name": "Mirror trade discrepancy",
        "abbr": "MTD",
        "section": "5.2",
        "blueprint_eq": "Sec. 5.2",
        "formula_latex": r"MTD = \frac{M_{reported} - X_{reported}}{(M_{reported} + X_{reported}) / 2}",
        "inputs": ["M (reporter imports)", "X (partner exports)"],
        "definition": "Symmetric relative gap between reporter and partner reported volumes.",
        "source": "defensefood_core::trade_flow::compute_mtd",
    },
    {
        "key": "delta_hhi",
        "name": "Concentration change",
        "abbr": "delta HHI",
        "section": "5.3",
        "blueprint_eq": "Sec. 5.3",
        "formula_latex": r"\Delta HHI = HHI_t - HHI_{t-1}",
        "inputs": ["HHI current period", "HHI prior period"],
        "definition": (
            "Period-over-period change in supplier concentration. Positive = consolidating."
        ),
        "source": "defensefood_core::trade_flow::compute_delta_hhi",
    },
    # ── Section 6: Network ──────────────────────────────────────────────
    {
        "key": "acep",
        "name": "Aggregate corridor exposure",
        "abbr": "ACEP",
        "section": "6.1",
        "blueprint_eq": "Sec. 6.1",
        "formula_latex": r"ACEP(i) = \sum_{c, j} BDI(c,i,j) \cdot HIS(c,i,j) \cdot CRS(c,i)",
        "inputs": ["BDI", "HIS", "CRS"],
        "definition": "Sum of hazard- and dependency-weighted exposure across every inbound lane.",
        "source": "defensefood_core::network::compute_acep",
    },
    {
        "key": "orps",
        "name": "Outbound risk propagation",
        "abbr": "ORPS",
        "section": "6.2",
        "blueprint_eq": "Sec. 6.2",
        "formula_latex": r"ORPS(j, c) = \sum_{i \in EU} BDI(c,i,j) \cdot HIS(c,i,j) \cdot PCC(c,i)",
        "inputs": ["BDI", "HIS", "PCC"],
        "definition": (
            "How much hazard-weighted exposure this origin sends to EU destinations, per commodity."
        ),
        "source": "defensefood_core::network::compute_orps",
    },
    # ── Section 7: Composite ────────────────────────────────────────────
    {
        "key": "cvs",
        "name": "Composite vulnerability score",
        "abbr": "CVS",
        "section": "7",
        "blueprint_eq": "Sec. 7",
        "formula_latex": (
            r"CVS = \mathrm{norm}(SCI) \cdot \mathrm{norm}(CRS) \cdot (w_h \cdot \mathrm{norm}(HIS) + "
            r"w_p \cdot \mathrm{norm}(PAS) + w_{sc} \cdot \mathrm{norm}(SCCS))"
        ),
        "inputs": [
            "SCI (structural)", "CRS (consumption)", "HIS (hazard)", "PAS (price)", "SCCS (chain)",
        ],
        "definition": (
            "Hybrid composite priority score in 0-1. Structural base (SCI*CRS) times a hazard-and-trade "
            "amplifier. Falls back to SCI*HIS when CRS is unavailable."
        ),
        "source": "defensefood_core::scoring::score_hybrid",
    },
]


METHODOLOGY_BY_KEY: dict[str, dict[str, Any]] = {entry["key"]: entry for entry in METHODOLOGY}
