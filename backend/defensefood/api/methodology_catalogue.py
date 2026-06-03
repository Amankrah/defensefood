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
        "key": "pcc",
        "name": "Per-capita apparent consumption",
        "abbr": "PCC",
        "section": "3.1",
        "blueprint_eq": "Eq. (10)",
        "formula_latex": r"PCC(c,i,t) = \frac{D(c,i,t)}{Pop(i,t)}",
        "formula_plain": "Domestic food-use supply divided by population, in kg/capita/year.",
        "inputs": ["D (food-use domestic supply)", "Pop (population)"],
        "definition": (
            "Raw per-person consumption from FAOSTAT Food Balance Sheets — how "
            "much of this commodity each resident consumes annually. The "
            "absolute scale varies wildly across commodities (a few kg for "
            "spices, hundreds of kg for cereals), so use CRS for cross-commodity "
            "comparison."
        ),
        "scale": [
            {"min": 0.00, "max": 1.0, "label": "Minimal consumption", "band": _LOW,
             "advice": "Less than 1 kg per person per year — niche commodity for this country."},
            {"min": 1.0, "max": 10.0, "label": "Low consumption", "band": _LOW,
             "advice": "Modest dietary role."},
            {"min": 10.0, "max": 50.0, "label": "Moderate consumption", "band": _MED,
             "advice": "Notable share of the average diet."},
            {"min": 50.0, "max": 1e6, "label": "High consumption", "band": _HIGH,
             "advice": "Staple-level role in the country's food system."},
        ],
        "when_matters": (
            "When weighting outbound risk propagation by demand intensity — "
            "ORPS uses PCC directly so origins shipping to high-consumption "
            "destinations get higher scores."
        ),
        "related": ["crs", "dis", "orps"],
        "source": "defensefood_core::consumption::compute_pcc",
    },
    {
        "key": "crs",
        "name": "Commodity consumption rank",
        "abbr": "CRS",
        "section": "3.2",
        "blueprint_eq": "Eq. (11)",
        "formula_latex": r"CRS(c,i,t) = 1 - \frac{\mathrm{Rank}(c,i,t) - 1}{|C| - 1}",
        "formula_plain": (
            "Within a given country, rank commodities by per-capita consumption "
            "(descending); rescale to 0–1 so the most-consumed commodity scores "
            "1 and the least scores 0."
        ),
        "inputs": ["PCC for all commodities in the country"],
        "definition": (
            "Where this commodity sits in the destination country's dietary "
            "basket. Normalised rank > raw PCC because different commodities "
            "operate on vastly different consumption scales (e.g. 200 kg of "
            "cereals vs 2 kg of spices) — both can be a top-rank staple "
            "depending on the country."
        ),
        "scale": [
            {"min": 0.00, "max": 0.25, "label": "Low-rank commodity", "band": _LOW,
             "advice": "Among the less-consumed commodities for this destination."},
            {"min": 0.25, "max": 0.50, "label": "Below-median rank", "band": _LOW,
             "advice": "Moderate dietary importance."},
            {"min": 0.50, "max": 0.75, "label": "Above-median rank", "band": _MED,
             "advice": "An important commodity in the country's diet."},
            {"min": 0.75, "max": 1.01, "label": "Top-rank staple", "band": _HIGH,
             "advice": "Among the most-consumed commodities — disruption hits many people."},
        ],
        "when_matters": (
            "When weighting demand-side exposure for the priority score "
            "(CVS) — lanes carrying a staple commodity rank higher."
        ),
        "related": ["pcc", "dis", "cvs", "orps"],
        "source": "defensefood_core::consumption::compute_crs_batch",
    },
    {
        "key": "dis",
        "name": "Demand inelasticity",
        "abbr": "DIS",
        "section": "3.3",
        "blueprint_eq": "Eq. (12)/(13)",
        "formula_latex": (
            r"CVD = \frac{\sigma_{PCC}}{\mu_{PCC}};\quad "
            r"DIS = 1 - \min(CVD,\,1)"
        ),
        "formula_plain": (
            "Coefficient of variation of per-capita consumption over a "
            "rolling 5-year window, inverted: stable demand (low variance) "
            "gives DIS near 1; volatile demand gives DIS near 0."
        ),
        "inputs": ["PCC time series (5-year window)"],
        "definition": (
            "Captures cultural entrenchment of a commodity. High DIS = "
            "consumers buy this regardless of price or quality scares; the "
            "demand floor is rigid, which makes the market more fraud-"
            "exploitable. Low DIS = swing demand that fraudsters can't rely on."
        ),
        "scale": [
            {"min": 0.00, "max": 0.50, "label": "Volatile demand", "band": _LOW,
             "advice": "Consumption swings widely — substitutes available."},
            {"min": 0.50, "max": 0.80, "label": "Moderately stable demand", "band": _MED,
             "advice": "Some price/quality sensitivity in this market."},
            {"min": 0.80, "max": 0.95, "label": "Stable demand", "band": _HIGH,
             "advice": "Embedded in the diet; consumers stick with it through shocks."},
            {"min": 0.95, "max": 1.01, "label": "Highly inelastic demand", "band": _HIGH,
             "advice": "Culturally entrenched — maximally exploitable for fraud."},
        ],
        "when_matters": (
            "When identifying commodities where fraud has a stable consumer "
            "base — high DIS lanes face sustained incentive pressure."
        ),
        "related": ["pcc", "crs", "cvs"],
        "source": "defensefood_core::consumption::compute_dis",
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
        "name": "Detection gap indicator",
        "abbr": "DGI",
        "section": "4.5",
        "blueprint_eq": "Eq. (19)",
        "formula_latex": (
            r"DGI(c,i,j,t) = \frac{M(c,i,j,t)}{M(c,i,\cdot,t)} - \frac{R(c,i,j,t)}{R(c,i,\cdot,t)}"
        ),
        "formula_plain": (
            "The lane's share of trade minus its share of notifications — a "
            "signed gap in roughly [−1, +1]. Positive = trade share exceeds "
            "notification share (potentially under-inspected); negative = "
            "over-represented in problems relative to trade volume."
        ),
        "inputs": [
            "M_ij (bilateral imports)", "M (total imports for destination)",
            "R_ij (lane notifications)", "R (total notifications for destination)",
        ],
        "definition": (
            "Compares a lane's share of trade volume to its share of RASFF "
            "notifications. A corridor moving large volumes but generating few "
            "alerts may be genuinely cleaner — or under-inspected. Combined "
            "with high Bilateral dependency (BDI) it's a flag for "
            "under-detection on a fragile lane."
        ),
        "scale": [
            {"min": -1.01, "max": -0.40, "label": "Heavily over-reported", "band": _HIGH,
             "advice": "Notification rate far exceeds trade share — already under intense scrutiny."},
            {"min": -0.40, "max": -0.10, "label": "Over-represented in alerts", "band": _MED,
             "advice": "Lane gets more attention than its trade share would predict."},
            {"min": -0.10, "max": 0.10, "label": "Reporting aligned with trade", "band": _LOW,
             "advice": "Notification share roughly tracks trade share."},
            {"min": 0.10, "max": 0.40, "label": "Possibly under-inspected", "band": _MED,
             "advice": "Trade share exceeds notification share — worth a sampling check."},
            {"min": 0.40, "max": 1.01, "label": "Strong inspection gap", "band": _HIGH,
             "advice": "Large trade flow with little alert activity — strong under-detection signal, especially with high BDI."},
        ],
        "when_matters": (
            "When asking 'is this lane really clean, or are we just not "
            "looking?' — combine with BDI to flag under-detection on lanes "
            "with high structural dependency."
        ),
        "related": ["his", "bdi"],
        "source": "defensefood_core::hazard::compute_dgi",
    },
    # ── Section 5: Trade Flow Analysis ──────────────────────────────────
    {
        "key": "z_uv",
        "name": "Unit-price z-score",
        "abbr": "z(UV)",
        "section": "5.1",
        "blueprint_eq": "Eq. (23)",
        "formula_latex": r"z_{UV}(c,i,j,t) = \frac{UV_{ij} - \mu_{UV_{i\cdot}}}{\sigma_{UV_{i\cdot}}}",
        "formula_plain": "How many standard deviations the lane's per-kg price sits from the mean across peer origins.",
        "inputs": ["UV = primaryValue / netWgt", "peer mean / std across origins"],
        "definition": (
            "How far this lane's per-kg import price deviates from peer "
            "partners feeding the same destination. |z| > 2 is unusual. "
            "Z < −2 suggests adulteration / substitution / misdeclaration; "
            "z > +2 suggests premium-claim fraud."
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
        "related": ["his", "mtd"],
        "source": "defensefood_core::trade_flow::compute_unit_value_zscore_batch",
    },
    {
        "key": "z_volume",
        "name": "Volume anomaly z-score",
        "abbr": "z(M)",
        "section": "5.2",
        "blueprint_eq": "Eq. (24-26)",
        "formula_latex": (
            r"z_M(c,i,j,t) = \frac{M(c,i,j,t) - \mu_M(c,i,j)}{\sigma_M(c,i,j)}"
            r"\quad\text{over rolling window of }k\text{ prior periods}"
        ),
        "formula_plain": (
            "How many standard deviations this period's import volume sits "
            "from the corridor's own historical mean. Uses a rolling k-period "
            "window (default k=5)."
        ),
        "inputs": ["M(c,i,j,τ) time series (one value per past period)"],
        "definition": (
            "Detects volume surges or collapses against the corridor's own "
            "trade history. z > +2 indicates a trade surge that warrants "
            "investigation for re-routing, fraudulent volume inflation, or "
            "origin laundering. Requires ≥ k+1 prior periods of data; "
            "returns NaN until enough history is ingested."
        ),
        "scale": [
            {"min": -1e9, "max": -2.0, "label": "Volume collapse", "band": _FLAG,
             "advice": "Large drop vs. corridor history — check for substitution or origin shift elsewhere."},
            {"min": -2.0, "max": -1.0, "label": "Below trend", "band": _MED,
             "advice": "Imports below normal range; possible disruption."},
            {"min": -1.0, "max": 1.0, "label": "Within normal range", "band": _LOW,
             "advice": "Volume tracks the corridor's historical pattern."},
            {"min": 1.0, "max": 2.0, "label": "Above trend", "band": _MED,
             "advice": "Mild surge — note origin and price together."},
            {"min": 2.0, "max": 1e9, "label": "Trade surge", "band": _FLAG,
             "advice": "Large jump vs. history — possible re-routing, volume inflation, or origin laundering."},
        ],
        "when_matters": (
            "When detecting trade-pattern shifts that aren't visible from a "
            "single period's snapshot."
        ),
        "related": ["delta_ocs", "delta_hhi"],
        "source": "defensefood_core::trade_flow::compute_volume_anomaly",
    },
    {
        "key": "mtd",
        "name": "Mirror trade discrepancy",
        "abbr": "MTD",
        "section": "5.3",
        "blueprint_eq": "Eq. (27)",
        "formula_latex": (
            r"MTD(c,i,j,t) = \frac{\left|M_i(c,i,j,t) - X_j(c,j,i,t)\right|}"
            r"{\max\!\left(M_i,\;X_j\right)}"
        ),
        "formula_plain": (
            "Absolute gap between what the destination reports importing and "
            "what the origin reports exporting, divided by the larger of the "
            "two. Bounded in [0, 1]."
        ),
        "inputs": ["M_i (destination reports imports)", "X_j (origin reports exports)"],
        "definition": (
            "Trade data is reported by both sides. Legitimate CIF/FOB and "
            "timing differences typically give 5-15% discrepancy. Gaps "
            "above 30% warrant investigation; persistent large discrepancies "
            "over multiple periods are a strong fraud signal."
        ),
        "scale": [
            {"min": 0.00, "max": 0.10, "label": "Aligned", "band": _LOW,
             "advice": "Reporter and partner figures agree."},
            {"min": 0.10, "max": 0.30, "label": "Small reporting gap", "band": _LOW,
             "advice": "Minor difference within typical CIF/FOB / timing noise."},
            {"min": 0.30, "max": 0.50, "label": "Notable reporting gap", "band": _MED,
             "advice": "Verify which side's figure to trust."},
            {"min": 0.50, "max": 1.01, "label": "Sharp divergence", "band": _FLAG,
             "advice": "Volumes diverge sharply — verify both sides."},
        ],
        "when_matters": (
            "When deciding whether reporter or partner figures look more "
            "reliable for a lane."
        ),
        "related": ["idr", "z_uv"],
        "source": "defensefood_core::trade_flow::compute_mtd",
    },
    {
        "key": "delta_hhi",
        "name": "Concentration change",
        "abbr": "ΔHHI",
        "section": "5.4",
        "blueprint_eq": "Eq. (28)",
        "formula_latex": r"\Delta HHI(c,i,t) = HHI(c,i,t) - HHI(c,i,t-1)",
        "formula_plain": (
            "Change in destination's supplier concentration (HHI) versus the "
            "prior period. Positive = consolidating onto fewer suppliers; "
            "negative = diversifying."
        ),
        "inputs": ["HHI(t) current period", "HHI(t−1) prior period"],
        "definition": (
            "Monitors structural changes in import concentration over time. "
            "A sudden rise in HHI combined with a new or rapidly growing "
            "corridor signals potential re-routing."
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
        "related": ["hhi", "delta_ocs"],
        "source": "defensefood_core::trade_flow::compute_delta_hhi",
    },
    {
        "key": "delta_ocs",
        "name": "Origin share change",
        "abbr": "ΔOCS",
        "section": "5.4",
        "blueprint_eq": "Eq. (29)",
        "formula_latex": r"\Delta OCS(c,i,j,t) = OCS(c,i,j,t) - OCS(c,i,j,t-1)",
        "formula_plain": (
            "Change in this specific origin's share of the destination's "
            "imports versus the prior period. Positive = origin gaining "
            "share; negative = losing share."
        ),
        "inputs": ["OCS(j,t) current period", "OCS(j,t−1) prior period"],
        "definition": (
            "Per-origin counterpart to ΔHHI. A rapid increase in OCS for a "
            "previously minor origin — especially while a traditionally "
            "dominant origin's OCS decreases — is a structural shift "
            "warranting investigation for re-routing or origin laundering."
        ),
        "scale": [
            {"min": -1e9, "max": -0.20, "label": "Losing share fast", "band": _MED,
             "advice": "This origin's role is shrinking sharply — note where the share went."},
            {"min": -0.20, "max": -0.05, "label": "Losing share", "band": _LOW,
             "advice": "Modest decline in this origin's contribution."},
            {"min": -0.05, "max": 0.05, "label": "Stable share", "band": _LOW,
             "advice": "Origin's contribution to imports is roughly unchanged."},
            {"min": 0.05, "max": 0.20, "label": "Gaining share", "band": _MED,
             "advice": "Origin growing in importance — check unit price and notification activity."},
            {"min": 0.20, "max": 1e9, "label": "Surging share", "band": _HIGH,
             "advice": "Origin gaining share rapidly — possible re-routing signal."},
        ],
        "when_matters": (
            "When tracking which origins are gaining or losing share, "
            "especially in concentrated markets."
        ),
        "related": ["ocs", "delta_hhi", "z_volume"],
        "source": "defensefood_core::trade_flow::compute_delta_ocs",
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
            "across every inbound lane reaching this country.\n\n"
            "Role-aware aggregation: Pan et al. 2025 (Discover Food) build "
            "role-aware directed RASFF networks. Following that approach, the "
            "headline ACEP sums only confirmed-market lanes (distribution or "
            "followUp). The API also returns ``acep_by_role`` with the "
            "detected and informational buckets so researchers can see the "
            "full picture without conflating market-presence semantics."
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
        "related": ["sci", "cvs", "corridor_membership"],
        "source": (
            "defensefood_core::network::compute_acep · "
            "Pan et al., 'Role-aware directed networks in food-fraud RASFF data', "
            "Discover Food 2025"
        ),
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
            "for a commodity. Used to rank origin-country impact.\n\n"
            "Role-aware aggregation: the headline ORPS sums only confirmed-market "
            "destinations (distribution or followUp). The API also returns "
            "``orps_by_role`` so the detected and informational buckets stay "
            "visible without inflating the planner-facing number."
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
        "related": ["his", "crs", "corridor_membership"],
        "source": (
            "defensefood_core::network::compute_orps · "
            "Pan et al., 'Role-aware directed networks in food-fraud RASFF data', "
            "Discover Food 2025"
        ),
    },
    {
        "key": "pas",
        "name": "Price anomaly score",
        "abbr": "PAS",
        "section": "7.2.3",
        "blueprint_eq": "Eq. (41) amplifier",
        "formula_latex": r"PAS = \mathrm{percentile}\bigl(\min(|z_{UV}|,\,3)\bigr)",
        "formula_plain": (
            "Magnitude of the lane's unit-value z-score (Section 5.1), clipped at "
            "3σ and percentile-ranked across the corpus."
        ),
        "inputs": ["z_uv (Section 5.1)"],
        "definition": (
            "One of three amplifier terms in the hybrid CVS formula (Eq. 41). "
            "High PAS means the corridor's unit value is far from the mix of its "
            "origin peers — a classic price-substitution / dilution signal. The "
            "raw z-score is clipped at 3σ before percentile-ranking so a single "
            "outlier corridor doesn't pin every other lane to ~0."
        ),
        "scale": [
            {"min": 0.00, "max": 0.50, "label": "Typical pricing", "band": _LOW,
             "advice": "Unit value is close to the peer-origin mix; no price signal."},
            {"min": 0.50, "max": 0.85, "label": "Noticeable spread", "band": _MED,
             "advice": "Unit value sits noticeably away from peers; monitor."},
            {"min": 0.85, "max": 1.01, "label": "Extreme pricing", "band": _HIGH,
             "advice": "Unit value is at the high end of the corpus; investigate "
                       "substitution / dilution / mislabelling."},
        ],
        "when_matters": (
            "When you want a price-based signal to amplify the structural CVS "
            "base — present whenever the lane has at least two origins of trade."
        ),
        "related": ["z_uv", "cvs", "sci"],
        "source": "Built from defensefood_core::trade_flow::unit_value at startup.",
    },
    {
        "key": "sccs",
        "name": "Supply chain complexity score",
        "abbr": "SCCS",
        "section": "7.2.3",
        "blueprint_eq": "Eq. (41) amplifier",
        "formula_latex": r"SCCS = \mathrm{percentile}(1 - OCS)",
        "formula_plain": (
            "Inverse of the origin's share of the destination's import mix, "
            "percentile-ranked across the corpus."
        ),
        "inputs": ["OCS (Section 2.3)"],
        "definition": (
            "One of three amplifier terms in the hybrid CVS formula (Eq. 41). "
            "High SCCS means this origin contributes a small slice of the "
            "destination's imports — i.e. the destination sources from many "
            "places, so the supply chain has more middlemen and more places for "
            "substitution to happen. The blueprint names SCCS as part of Eq. 41 "
            "but does not formalise it; we use (1 − OCS) percentile because OCS "
            "is always available for trade-covered lanes."
        ),
        "scale": [
            {"min": 0.00, "max": 0.50, "label": "Direct supply", "band": _LOW,
             "advice": "This origin is a dominant supplier; the chain is short."},
            {"min": 0.50, "max": 0.85, "label": "Diversified chain", "band": _MED,
             "advice": "Origin shares space with several peers; more handoffs likely."},
            {"min": 0.85, "max": 1.01, "label": "Many-hop chain", "band": _HIGH,
             "advice": "Origin is one of many small suppliers; high complexity."},
        ],
        "when_matters": (
            "When you want a supply-chain-complexity signal to amplify the "
            "structural CVS base — present whenever OCS is available."
        ),
        "related": ["ocs", "cvs", "hhi"],
        "source": "Derived from defensefood_core::dependency::compute_ocs at startup.",
    },
    {
        "key": "hazard_probability",
        "name": "Empirical hazard probability",
        "abbr": "P̂",
        "section": "6.4",
        "blueprint_eq": "Eq. (35)",
        "formula_latex": (
            r"\hat{P}(\text{hazard} \mid c, i, j) = \frac{R(c,i,j,T)}{M(c,i,j,T) / \bar{m}(c)}"
        ),
        "formula_plain": (
            "Notifications divided by estimated number of shipments — read as the "
            "share of shipments that triggered a hazard alert."
        ),
        "inputs": [
            "R (notification count over observation window)",
            "M (total bilateral imports, kg)",
            "m̄(c) (median shipment size per HS-2 chapter, kg)",
        ],
        "definition": (
            "Probability of a hazard being detected on this corridor per estimated "
            "shipment. Eq. (35) requires ≥10 notifications before the ratio is "
            "considered informative — below that, the endpoint returns 'eligible: "
            "false'. P̂ is a lower bound (only detected hazards count) and must be "
            "cross-referenced with the Detection Gap Indicator (§4.5) to distinguish "
            "'more fraud' from 'more detection'. m̄(c) is approximated as the median "
            "Comtrade row net weight within the commodity's HS-2 chapter."
        ),
        "scale": [
            {"min": 0.0, "max": 0.001, "label": "Rare detection", "band": _LOW,
             "advice": "Hazards are rare per shipment; baseline surveillance is fine."},
            {"min": 0.001, "max": 0.01, "label": "Occasional detection", "band": _MED,
             "advice": "A handful of shipments per thousand draw a notification; cross-check DGI."},
            {"min": 0.01, "max": 1.0, "label": "Frequent detection", "band": _HIGH,
             "advice": "More than one shipment in a hundred draws a notification; sustained scrutiny warranted."},
        ],
        "when_matters": (
            "When you want a calibrated detection rate per shipment, not just a "
            "hazard intensity — cross-reference with DGI to distinguish 'more fraud' "
            "from 'more detection'."
        ),
        "related": ["his", "dgi", "z_volume"],
        "source": "defensefood_core::network::compute_hazard_probability",
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
            "Hybrid composite priority score in [0, 1]. Structural base "
            "(SCI × CRS) times a hazard-and-trade amplifier (HIS + PAS + SCCS). "
            "Amplifier terms that are absent for a lane drop out of BOTH the "
            "numerator and the divisor (Slice E1, June 2026) so full-data and "
            "partial-data corridors share the same [0, 1] scale; missing CRS "
            "uses the neutral 0.5 (median percentile) fallback rather than 1.0. "
            "Scale bands re-anchored June 2026 on the live distribution "
            "(cvs_distribution_postE2.json): P75≈0.22, P90≈0.30, P95≈0.35. "
            "Theoretical max is 1.0 but no real corridor approaches it."
        ),
        "scale": [
            {"min": 0.00, "max": 0.22, "label": "Low priority", "band": _LOW,
             "advice": "No immediate action required."},
            {"min": 0.22, "max": 0.30, "label": "Watchlist", "band": _MED,
             "advice": "Monitor for changes in alert pattern or supplier mix."},
            {"min": 0.30, "max": 0.35, "label": "High priority", "band": _HIGH,
             "advice": "Schedule a targeted check this period."},
            {"min": 0.35, "max": 1.01, "label": "Top priority", "band": _HIGH,
             "advice": "Sample and review this period — strong combined signal."},
        ],
        "when_matters": (
            "When ranking lanes for inspection and sampling priority — the "
            "headline number on the Today page."
        ),
        "related": ["sci", "his", "crs", "pas", "sccs"],
        "source": "defensefood_core::scoring::score_hybrid (Slice E1 masking in scoring_pipeline.py)",
    },
    # ── Methodology disclosure: corridor membership semantics ───────────
    # Not a metric — a first-class explanation of how RASFF roles map to
    # Comtrade "destination" and what that join does (and does not) mean.
    {
        "key": "corridor_membership",
        "name": "Corridor membership semantics",
        "abbr": "Membership",
        "section": "Methodology",
        "blueprint_eq": "Sec. 4.1 join rule",
        "formula_latex": (
            r"\text{corridor}(c,i,j) = \{\text{RASFF}_{c,i,j}\} "
            r"\;\bowtie\;\{\text{Comtrade}_{c,i,j}\}"
        ),
        "formula_plain": (
            "A lane is a (commodity, destination, origin) triple. RASFF decides "
            "which lanes exist and what hazard signal they carry. Comtrade is "
            "looked up separately on the same key for structural metrics. We do "
            "not trace a specific RASFF batch through customs."
        ),
        "inputs": [
            "RASFF role columns (notifying_country, distribution, for_followUp, for_attention)",
            "Comtrade bilateral flow (reporter = destination, partner = origin)",
        ],
        "definition": (
            "Per EU RASFF SOPs (Regulation 16/2011) each notification carries up "
            "to four role columns that mean different things about market presence:\n\n"
            "• distribution — product was physically shipped to this country.\n"
            "• for_followUp — product is or may be placed on this country's market; "
            "follow-up notifications mirror alerts in market-presence implication.\n"
            "• notifying_country — country detected/reported the hazard. Often "
            "(not always) the importer that caught it at the border or in market.\n"
            "• for_attention — informational only: product is NOT on this market "
            "(only in the notifying country, no longer on the market, or never "
            "placed on the market).\n\n"
            "The system stamps every corridor with a market_presence label derived "
            "deterministically from its role set:\n\n"
            "• confirmed — at least one of distribution/followUp. Structural "
            "dependency (Section 2) and trade-flow (Section 5) metrics are "
            "meaningful for this lane.\n"
            "• detected — notifier-only. Comtrade dependency may still apply (if "
            "notifier is the importer), but read with caution.\n"
            "• informational — attention-only. Per RASFF, the product is not on "
            "this market; Comtrade lookups on this lane answer a question RASFF "
            "explicitly did not ask. SCI/CVS are shown for transparency but should "
            "not drive priority decisions.\n\n"
            "What this join does NOT prove: we do not match a specific RASFF lot "
            "to a specific customs entry. The corridor is a structural+hazard "
            "shared key, not a supply-chain trace."
        ),
        # No scale bands — this is a categorical disclosure, not a numeric metric.
        "scale": [],
        "when_matters": (
            "Always. Before acting on any structural metric, check the lane's "
            "market_presence — 'informational' lanes should be excluded from "
            "inspection planning and weighted down in research aggregates."
        ),
        "related": ["sci", "bdi", "cvs", "ds_prime"],
        "source": (
            "EU Regulation 16/2011 (RASFF) · BVL Germany RASFF reference · "
            "Pan et al., 'Role-aware directed networks in food-fraud RASFF data', "
            "Discover Food 2025"
        ),
    },
]


METHODOLOGY_BY_KEY: dict[str, dict[str, Any]] = {entry["key"]: entry for entry in METHODOLOGY}
