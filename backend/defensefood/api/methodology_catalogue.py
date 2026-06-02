"""
Static catalogue of blueprint metrics exposed via /api/v1/research/methodology.

Each entry carries:
  * ``key, name, abbr, section`` — identification and blueprint reference
  * ``formula_latex``    — exact mathematical definition for KaTeX rendering
  * ``formula_plain``    — same formula in plain English
  * ``definition``       — one-paragraph plain-language description
  * ``inputs``           — variables the formula consumes
  * ``scale``            — ordered list of bands with thresholds and advice;
                           drives both the frontend MetricTile verdict line
                           and the backend ``interpret_metric`` function
  * ``when_matters``     — one sentence on the decision question this metric
                           answers
  * ``related``          — list of metric keys this one combines with or
                           cross-references
  * ``source``           — Rust function path that implements it

The frontend Methodology tab and the Glossary slide-over render this verbatim
— no recomputation, no parsing required. The pipeline ``interpret_metric``
function consumes the same scale tables so dashboard and API see the same
plain-language verdicts.

Scale band semantics:
  ``min`` inclusive, ``max`` exclusive. ``band`` ∈ {"low","med","high","flag"}
  drives the colour the UI uses. ``flag`` is reserved for data-quality /
  exceptional conditions (e.g. IDR > 1 trade-hub).
"""

from typing import Any

# Convenience alias — closes-over the band literals so the catalogue stays scannable.
_LOW = "low"
_MED = "med"
_HIGH = "high"
_FLAG = "flag"


METHODOLOGY: list[dict[str, Any]] = [
    # ── Section 2: Commodity Dependency ─────────────────────────────────
    {
        "key": "ds_prime",
        "name": "Apparent domestic supply",
        "abbr": "DS'",
        "section": "2.1",
        "blueprint_eq": "Eq. (2)",
        "formula_latex": r"DS'(c,i,t) = P(c,i,t) + M(c,i,\cdot,t) - X(c,i,\cdot,t)",
        "formula_plain": "Production + Imports − Exports (+ Stock change when known).",
        "inputs": ["P (production)", "M (total imports)", "X (total exports)"],
        "definition": (
            "Apparent domestic supply for the commodity in the destination. "
            "Denominator of every downstream dependency metric. The 'apparent' "
            "qualifier reflects that stock change is set to zero when FBS doesn't "
            "report it for this commodity-year."
        ),
        "scale": [
            # DS' is a kg quantity, not a 0-1 ratio. Render as raw with a context
            # note instead of bands. Frontend renders this as 'magnitude only'.
            {"min": 0, "max": 1e15, "label": "Apparent supply in kg", "band": _LOW,
             "advice": "Read as raw volume; compare to imports to gauge fraction sourced abroad."},
        ],
        "when_matters": (
            "When you need to know whether a country could absorb a trade shock "
            "with domestic supply alone."
        ),
        "related": ["idr", "ssr"],
        "source": "defensefood_core::dependency::compute_supply_balance",
    },
    {
        "key": "idr",
        "name": "Import dependency ratio",
        "abbr": "IDR",
        "section": "2.2",
        "blueprint_eq": "Eq. (3)",
        "formula_latex": r"IDR(c,i,t) = \frac{M(c,i,\cdot,t)}{DS'(c,i,t)}",
        "formula_plain": "Imports divided by apparent domestic supply.",
        "inputs": ["M (total imports)", "DS' (apparent supply)"],
        "definition": (
            "Share of apparent supply that comes from imports. 0 = self-sufficient, "
            "1 = fully import-dependent, >1 = re-export hub / missing production data."
        ),
        "scale": [
            {"min": 0.00, "max": 0.05, "label": "Fully self-sufficient", "band": _LOW,
             "advice": "All supply is domestic; imports negligible."},
            {"min": 0.05, "max": 0.40, "label": "Mostly produced at home", "band": _LOW,
             "advice": "Imports fill a modest gap; domestic production dominates."},
            {"min": 0.40, "max": 0.75, "label": "Partly import-dependent", "band": _MED,
             "advice": "Roughly half of supply comes from imports — note origin concentration."},
            {"min": 0.75, "max": 1.00, "label": "Heavily import-dependent", "band": _HIGH,
             "advice": "Little domestic cushion; supply shocks transmit quickly."},
            {"min": 1.00, "max": 1e9, "label": "Imports exceed supply (re-export hub)", "band": _FLAG,
             "advice": "Either a trade hub re-exporting most of what arrives, or production data is missing."},
        ],
        "when_matters": (
            "When evaluating how much of a country's supply could be disrupted by "
            "a single trade shock."
        ),
        "related": ["ds_prime", "sci", "ssr"],
        "source": "defensefood_core::dependency::compute_idr",
    },
    {
        "key": "ocs",
        "name": "Origin country share",
        "abbr": "OCS",
        "section": "2.3",
        "blueprint_eq": "Eq. (4)",
        "formula_latex": r"OCS(c,i,j,t) = \frac{M(c,i,j,t)}{M(c,i,\cdot,t)}",
        "formula_plain": "Imports from this origin divided by total imports.",
        "inputs": ["M_ij (bilateral imports)", "M (total imports)"],
        "definition": "Share of total imports that comes from this single origin. 0 to 1.",
        "scale": [
            {"min": 0.00, "max": 0.05, "label": "Negligible origin", "band": _LOW,
             "advice": "This origin contributes very little of the import mix."},
            {"min": 0.05, "max": 0.20, "label": "Minor origin", "band": _LOW,
             "advice": "Minor slice within a diverse import mix."},
            {"min": 0.20, "max": 0.50, "label": "Significant origin", "band": _MED,
             "advice": "A meaningful slice — worth tracking but not dominant."},
            {"min": 0.50, "max": 0.90, "label": "Majority origin", "band": _HIGH,
             "advice": "Over half of imports come from here; fallback options shrink."},
            {"min": 0.90, "max": 1.01, "label": "Dominant origin", "band": _HIGH,
             "advice": "Almost all imports come from this single country."},
        ],
        "when_matters": (
            "When deciding whether to diversify a lane's sourcing or treat it "
            "as concentrated."
        ),
        "related": ["hhi", "sci", "bdi"],
        "source": "defensefood_core::dependency::compute_ocs",
    },
    {
        "key": "bdi",
        "name": "Bilateral dependency index",
        "abbr": "BDI",
        "section": "2.4",
        "blueprint_eq": "Eq. (5) / (6)",
        "formula_latex": r"BDI(c,i,j,t) = \frac{M(c,i,j,t)}{DS'(c,i,t)} = IDR \cdot OCS",
        "formula_plain": "Imports from this origin divided by apparent supply (equivalent to Import reliance × Origin share).",
        "inputs": ["IDR", "OCS"],
        "definition": "Share of domestic supply sourced specifically from this origin.",
        "scale": [
            {"min": 0.00, "max": 0.05, "label": "Negligible bilateral dependency", "band": _LOW,
             "advice": "This origin contributes a tiny fraction of supply."},
            {"min": 0.05, "max": 0.25, "label": "Modest bilateral dependency", "band": _LOW,
             "advice": "A noticeable but bounded slice of supply."},
            {"min": 0.25, "max": 0.50, "label": "Substantial bilateral dependency", "band": _MED,
             "advice": "A meaningful portion of supply rides on this single origin."},
            {"min": 0.50, "max": 0.90, "label": "Majority bilateral dependency", "band": _HIGH,
             "advice": "Most of supply comes specifically from this origin — concentrated risk."},
            {"min": 0.90, "max": 10.0, "label": "Near-total bilateral dependency", "band": _HIGH,
             "advice": "Almost all supply rides on this single origin."},
        ],
        "when_matters": (
            "When ranking lanes by direct sourcing exposure to a specific origin."
        ),
        "related": ["idr", "ocs"],
        "source": "defensefood_core::dependency::compute_bdi",
    },
    {
        "key": "hhi",
        "name": "Herfindahl-Hirschman concentration",
        "abbr": "HHI",
        "section": "2.5",
        "blueprint_eq": "Eq. (7)",
        "formula_latex": r"HHI(c,i,t) = \sum_{j \in O} OCS(c,i,j,t)^2",
        "formula_plain": "Sum of squared origin shares across all suppliers.",
        "inputs": ["OCS_j (origin shares)"],
        "definition": (
            "Supplier concentration across origins. 1/n for n equal suppliers, "
            "1 for a single supplier. ≥0.25 is highly concentrated by the "
            "standard antitrust threshold."
        ),
        "scale": [
            {"min": 0.00, "max": 0.10, "label": "Well diversified", "band": _LOW,
             "advice": "Many balanced suppliers; loss of any one is absorbable."},
            {"min": 0.10, "max": 0.25, "label": "Moderately diversified", "band": _LOW,
             "advice": "Several suppliers with varying weight; reasonable resilience."},
            {"min": 0.25, "max": 0.50, "label": "Highly concentrated", "band": _MED,
             "advice": "Antitrust 'concentrated market' threshold — a few origins dominate."},
            {"min": 0.50, "max": 0.90, "label": "Very concentrated", "band": _HIGH,
             "advice": "Few effective suppliers; loss of one has outsized impact."},
            {"min": 0.90, "max": 1.01, "label": "Near-monopoly sourcing", "band": _HIGH,
             "advice": "One supplier essentially controls this lane."},
        ],
        "when_matters": (
            "When evaluating market-wide vulnerability — even lanes with low "
            "Origin share can fail when the wider supplier market is concentrated."
        ),
        "related": ["ocs", "sci"],
        "source": "defensefood_core::dependency::compute_hhi",
    },
    {
        "key": "ssr",
        "name": "Self-sufficiency ratio",
        "abbr": "SSR",
        "section": "2.6",
        "blueprint_eq": "Eq. (8)",
        "formula_latex": r"SSR(c,i,t) = \frac{P(c,i,t)}{D(c,i,t)}",
        "formula_plain": "Production divided by domestic food-use supply.",
        "inputs": ["P (production)", "D (food-use domestic supply)"],
        "definition": (
            "Net exporter when >1, balanced at 1, imports fill the gap when <1, "
            "zero when there's no domestic production."
        ),
        "scale": [
            {"min": 0.00, "max": 0.001, "label": "No domestic production", "band": _HIGH,
             "advice": "Fully reliant on imports — no fallback if a lane is disrupted."},
            {"min": 0.001, "max": 0.50, "label": "Almost entirely imported", "band": _HIGH,
             "advice": "Small domestic production; most supply arrives from abroad."},
            {"min": 0.50, "max": 0.90, "label": "Partly produced locally", "band": _MED,
             "advice": "Imports fill the gap; partial cushion against disruption."},
            {"min": 0.90, "max": 1.10, "label": "Roughly balanced", "band": _LOW,
             "advice": "Production matches consumption; modest import dependency."},
            {"min": 1.10, "max": 1e9, "label": "Net exporter", "band": _LOW,
             "advice": "Produces more than it consumes; structural exposure is low."},
        ],
        "when_matters": (
            "When deciding if production capacity is a real fallback in a supply "
            "disruption."
        ),
        "related": ["idr", "ds_prime"],
        "source": "defensefood_core::dependency::compute_ssr",
    },
    {
        "key": "sci",
        "name": "Supply criticality index",
        "abbr": "SCI",
        "section": "2.7",
        "blueprint_eq": "Eq. (9)",
        "formula_latex": r"SCI(c,i,j,t) = IDR \cdot OCS \cdot (1 + HHI)",
        "formula_plain": "Import reliance × Origin share × (1 + Supplier concentration).",
        "inputs": ["IDR", "OCS", "HHI"],
        "definition": (
            "Core corridor-specific dependency score in [0,2]. The (1+HHI) factor "
            "amplifies vulnerability when the wider supplier market is also "
            "concentrated."
        ),
        "scale": [
            {"min": 0.00, "max": 0.25, "label": "Negligible exposure", "band": _LOW,
             "advice": "Diversified supply with no concentration alarm."},
            {"min": 0.25, "max": 0.50, "label": "Low exposure", "band": _LOW,
             "advice": "Some dependency, but easily replaced from other origins."},
            {"min": 0.50, "max": 1.00, "label": "Moderate exposure", "band": _MED,
             "advice": "Worth tracking — combined reliance and concentration is notable."},
            {"min": 1.00, "max": 1.50, "label": "High exposure", "band": _HIGH,
             "advice": "Concentrated dependency — limited fallback if this lane fails."},
            {"min": 1.50, "max": 2.01, "label": "Critical exposure", "band": _HIGH,
             "advice": "Near-maximum structural vulnerability — single source, weak market alternatives."},
        ],
        "when_matters": (
            "When ranking lanes that need sampling / inspection capacity this period."
        ),
        "related": ["idr", "ocs", "hhi"],
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
        "formula_plain": "Percentile rank of per-capita consumption across destinations.",
        "inputs": ["PCC (per-capita consumption)"],
        "definition": (
            "Population-exposure ranking across destinations for the commodity. "
            "Demand-side amplifier for the priority score: high CRS means many "
            "people would be affected if a lane fails."
        ),
        "scale": [
            {"min": 0.00, "max": 0.25, "label": "Low consumption rank", "band": _LOW,
             "advice": "This destination consumes relatively little of the commodity."},
            {"min": 0.25, "max": 0.50, "label": "Below-median consumption", "band": _LOW,
             "advice": "Moderate consumption — average demand pressure."},
            {"min": 0.50, "max": 0.75, "label": "Above-median consumption", "band": _MED,
             "advice": "Higher-than-average per-capita consumption."},
            {"min": 0.75, "max": 1.01, "label": "Top-quartile consumption", "band": _HIGH,
             "advice": "Among the heaviest consumers — disruption affects many people."},
        ],
        "when_matters": (
            "When weighting demand-side exposure — lanes affecting more people "
            "get higher priority."
        ),
        "related": ["cvs", "orps"],
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
        "formula_plain": "Severity-weighted sum across RASFF notifications, with older alerts decayed.",
        "inputs": ["RASFF notifications", "α (decay parameter)"],
        "definition": (
            "Severity-weighted, time-decayed RASFF signal on the lane. Recent "
            "and serious notifications dominate over older or less-serious ones."
        ),
        "scale": [
            {"min": 0.00, "max": 0.05, "label": "Quiet", "band": _LOW,
             "advice": "No or trivial alert activity on this lane."},
            {"min": 0.05, "max": 0.20, "label": "Light alert activity", "band": _LOW,
             "advice": "Some history but nothing recent or severe."},
            {"min": 0.20, "max": 0.50, "label": "Some alert activity", "band": _MED,
             "advice": "Notable history; worth a closer look at categories."},
            {"min": 0.50, "max": 1.00, "label": "Notable alert pattern", "band": _HIGH,
             "advice": "Recent or serious activity — prioritise sampling."},
            {"min": 1.00, "max": 1e9, "label": "Strong, recent, severe alerts", "band": _HIGH,
             "advice": "Sustained serious alert pattern — top priority for inspection."},
        ],
        "when_matters": (
            "When prioritising lanes with active alert patterns rather than "
            "structural risk alone."
        ),
        "related": ["hdi", "dgi", "cvs"],
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
        "formula_plain": "Shannon entropy across six hazard families, normalised to 0–1.",
        "inputs": ["Hazard category counts"],
        "definition": (
            "0 = all alerts share one hazard family (a recurring single-issue "
            "pattern). Near 1 = alerts span many families (broad-spectrum problem)."
        ),
        "scale": [
            {"min": 0.00, "max": 0.01, "label": "Single hazard family or no alerts", "band": _LOW,
             "advice": "Either a clean lane or a one-issue pattern."},
            {"min": 0.01, "max": 0.30, "label": "One dominant family", "band": _HIGH,
             "advice": "Most alerts share one family — a recurring, specific problem."},
            {"min": 0.30, "max": 0.70, "label": "Mix of a few families", "band": _MED,
             "advice": "Several hazard families surface; mixed concerns."},
            {"min": 0.70, "max": 1.01, "label": "Spans many families", "band": _MED,
             "advice": "Alert activity is broad-spectrum; lane has heterogeneous issues."},
        ],
        "when_matters": (
            "When distinguishing one-issue lanes from broad-spectrum problem lanes."
        ),
        "related": ["his"],
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
        "formula_plain": "Notification share of a lane divided by its trade share.",
        "inputs": ["Notification share", "Trade share"],
        "definition": (
            "<1 = under-reported relative to trade volume; >1 = over-reported. "
            "Helps detect lanes where inspection signals don't match trade flow."
        ),
        "scale": [
            {"min": 0.00, "max": 0.50, "label": "Under-reported", "band": _MED,
             "advice": "Notification share is well below trade share — possible inspection gap."},
            {"min": 0.50, "max": 1.50, "label": "Reporting aligned", "band": _LOW,
             "advice": "Notification share tracks trade share roughly."},
            {"min": 1.50, "max": 1e9, "label": "Over-reported", "band": _HIGH,
             "advice": "Notification rate exceeds trade share — concentrated attention."},
        ],
        "when_matters": (
            "When checking whether a lane is under- or over-reported relative "
            "to its trade volume."
        ),
        "related": ["his"],
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
        "formula_plain": "How many standard deviations the lane's unit price is from peer mean.",
        "inputs": ["UV = primaryValue / netWgt", "peer mean / std"],
        "definition": (
            "How far this lane's per-kg price deviates from peer partners on the "
            "same import market. |z| > 2 is unusual."
        ),
        "scale": [
            {"min": -1e9, "max": -2.0, "label": "Priced far below peers", "band": _FLAG,
             "advice": "Verify quality, grading, or undervaluation."},
            {"min": -2.0, "max": -1.0, "label": "Priced somewhat below", "band": _MED,
             "advice": "Mild downward outlier; check for promotion or batch effects."},
            {"min": -1.0, "max": 1.0, "label": "Within typical range", "band": _LOW,
             "advice": "Price sits in the normal partner range."},
            {"min": 1.0, "max": 2.0, "label": "Priced somewhat above", "band": _MED,
             "advice": "Mild upward outlier; possible premium claim."},
            {"min": 2.0, "max": 1e9, "label": "Priced far above peers", "band": _FLAG,
             "advice": "Check premium claims or misclassification."},
        ],
        "when_matters": (
            "When spotting lanes worth a targeted price-fraud check."
        ),
        "related": ["his"],
        "source": "defensefood_core::trade_flow::compute_unit_value_zscore_batch",
    },
    {
        "key": "mtd",
        "name": "Mirror trade discrepancy",
        "abbr": "MTD",
        "section": "5.2",
        "blueprint_eq": "Sec. 5.2",
        "formula_latex": r"MTD = \frac{M_{reported} - X_{reported}}{(M_{reported} + X_{reported}) / 2}",
        "formula_plain": "Symmetric relative gap between reporter and partner reported volumes.",
        "inputs": ["M (reporter imports)", "X (partner exports)"],
        "definition": (
            "Symmetric relative gap between reporter and partner reported volumes. "
            "Large gaps point to reporting issues worth checking."
        ),
        "scale": [
            {"min": 0.00, "max": 0.10, "label": "Aligned", "band": _LOW,
             "advice": "Reporter and partner figures agree."},
            {"min": 0.10, "max": 0.30, "label": "Small reporting gap", "band": _LOW,
             "advice": "Minor difference within typical noise."},
            {"min": 0.30, "max": 0.50, "label": "Notable reporting gap", "band": _MED,
             "advice": "Verify which side's figure to trust."},
            {"min": 0.50, "max": 1e9, "label": "Sharp divergence", "band": _FLAG,
             "advice": "Volumes diverge sharply — verify both sides."},
        ],
        "when_matters": (
            "When deciding whether reporter or partner figures look more "
            "reliable for a lane."
        ),
        "related": ["idr"],
        "source": "defensefood_core::trade_flow::compute_mtd",
    },
    {
        "key": "delta_hhi",
        "name": "Concentration change",
        "abbr": "ΔHHI",
        "section": "5.3",
        "blueprint_eq": "Sec. 5.3",
        "formula_latex": r"\Delta HHI = HHI_t - HHI_{t-1}",
        "formula_plain": "Change in supplier concentration vs the prior period.",
        "inputs": ["HHI current period", "HHI prior period"],
        "definition": (
            "Positive = consolidating onto fewer suppliers; negative = diversifying."
        ),
        "scale": [
            {"min": -1e9, "max": -0.10, "label": "Diversifying", "band": _LOW,
             "advice": "More suppliers entering the mix; resilience improving."},
            {"min": -0.10, "max": -0.03, "label": "Mildly diversifying", "band": _LOW,
             "advice": "Slight reduction in concentration."},
            {"min": -0.03, "max": 0.03, "label": "Roughly unchanged", "band": _LOW,
             "advice": "Concentration stable across periods."},
            {"min": 0.03, "max": 0.10, "label": "Concentration drifting upward", "band": _MED,
             "advice": "Supply consolidating; worth monitoring."},
            {"min": 0.10, "max": 1e9, "label": "Concentrating fast", "band": _HIGH,
             "advice": "Rapid consolidation onto fewer suppliers."},
        ],
        "when_matters": (
            "When detecting market consolidation that increases lane-level vulnerability."
        ),
        "related": ["hhi"],
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
        "formula_plain": "Sum of (Bilateral dependency × Hazard intensity × Consumption rank) across every inbound lane.",
        "inputs": ["BDI", "HIS", "CRS"],
        "definition": (
            "Country-level: sum of hazard-and-dependency-weighted exposure "
            "across every inbound lane reaching this country."
        ),
        "scale": [
            {"min": 0.00, "max": 0.10, "label": "Negligible inbound exposure", "band": _LOW,
             "advice": "Aggregate cross-lane exposure is low for this country."},
            {"min": 0.10, "max": 0.30, "label": "Light inbound exposure", "band": _LOW,
             "advice": "Some exposure; nothing alarming."},
            {"min": 0.30, "max": 1.00, "label": "Notable inbound exposure", "band": _MED,
             "advice": "Worth monitoring across lanes."},
            {"min": 1.00, "max": 1e9, "label": "Heavy combined pressure", "band": _HIGH,
             "advice": "Aggregate exposure from inbound lanes is high."},
        ],
        "when_matters": (
            "When ranking destinations by aggregate inbound exposure."
        ),
        "related": ["sci", "cvs"],
        "source": "defensefood_core::network::compute_acep",
    },
    {
        "key": "orps",
        "name": "Outbound risk propagation",
        "abbr": "ORPS",
        "section": "6.2",
        "blueprint_eq": "Sec. 6.2",
        "formula_latex": r"ORPS(j, c) = \sum_{i \in EU} BDI(c,i,j) \cdot HIS(c,i,j) \cdot PCC(c,i)",
        "formula_plain": "Sum of (Bilateral dependency × Hazard intensity × Per-capita consumption) across EU destinations.",
        "inputs": ["BDI", "HIS", "PCC"],
        "definition": (
            "How much hazard-weighted exposure this origin sends to EU destinations "
            "for a commodity. Used to rank origin-country impact."
        ),
        "scale": [
            {"min": 0.00, "max": 0.10, "label": "Low outbound impact", "band": _LOW,
             "advice": "This origin sends little weighted exposure to EU destinations."},
            {"min": 0.10, "max": 0.50, "label": "Moderate outbound impact", "band": _MED,
             "advice": "Notable exposure routed via this origin."},
            {"min": 0.50, "max": 1e9, "label": "High outbound impact", "band": _HIGH,
             "advice": "Significant share of EU exposure flows through this origin."},
        ],
        "when_matters": (
            "When ranking origins by outbound exposure they send to EU destinations."
        ),
        "related": ["his", "crs"],
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
        "formula_plain": (
            "Structural base (Supply criticality × Consumption rank) "
            "amplified by hazard and trade-anomaly signals; rescaled to 0–1."
        ),
        "inputs": [
            "SCI (structural)", "CRS (consumption)", "HIS (hazard)",
            "PAS (price)", "SCCS (chain)",
        ],
        "definition": (
            "Hybrid composite priority score in 0-1. Structural base (SCI × CRS) "
            "times a hazard-and-trade amplifier. Falls back to SCI × HIS when CRS "
            "is unavailable."
        ),
        "scale": [
            {"min": 0.00, "max": 0.30, "label": "Low priority", "band": _LOW,
             "advice": "No immediate action required."},
            {"min": 0.30, "max": 0.50, "label": "Watchlist", "band": _MED,
             "advice": "Monitor for changes in alert pattern or supplier mix."},
            {"min": 0.50, "max": 0.75, "label": "High priority", "band": _HIGH,
             "advice": "Schedule a targeted check this period."},
            {"min": 0.75, "max": 1.01, "label": "Top priority", "band": _HIGH,
             "advice": "Sample and review this period — strong combined signal."},
        ],
        "when_matters": (
            "When ranking lanes for inspection and sampling priority — the "
            "headline number on the Today page."
        ),
        "related": ["sci", "his", "crs"],
        "source": "defensefood_core::scoring::score_hybrid",
    },
]


METHODOLOGY_BY_KEY: dict[str, dict[str, Any]] = {entry["key"]: entry for entry in METHODOLOGY}
