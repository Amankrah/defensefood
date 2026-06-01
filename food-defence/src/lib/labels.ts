/**
 * Metric label registry — single source of truth.
 *
 * Use `METRIC.idr.long` and `METRIC.idr.short` everywhere instead of
 * hand-writing "Import reliance (IDR)" strings page-by-page. Rendering helper
 * `withAbbr` produces the canonical "Plain label (ABBR)" form.
 */

export type MetricKey =
  | "sci"
  | "sci_norm"
  | "idr"
  | "ocs"
  | "bdi"
  | "hhi"
  | "ssr"
  | "ds_prime"
  | "his"
  | "his_norm"
  | "hdi"
  | "dgi"
  | "cvs"
  | "crs"
  | "crs_norm"
  | "acep"
  | "orps"
  | "z_uv"
  | "mtd"
  | "delta_hhi";

export interface MetricLabel {
  long: string;
  short: string;
  /** One-sentence plain-language definition (used in glossary and tooltips). */
  definition: string;
}

export const METRIC: Record<MetricKey, MetricLabel> = {
  sci: {
    long: "Supply criticality",
    short: "SCI",
    definition:
      "How exposed the destination is to this single origin for this commodity. Combines import reliance, origin share, and supplier concentration. Scale 0–2.",
  },
  sci_norm: {
    long: "Supply criticality (normalised)",
    short: "SCI₀₋₁",
    definition: "Supply criticality rescaled to 0–1 (SCI ÷ 2) for blending into the priority score.",
  },
  idr: {
    long: "Import reliance",
    short: "IDR",
    definition:
      "Share of the destination's apparent supply that comes from imports. 0 = fully self-sufficient; 1 = fully import-dependent; >1 means imports exceed apparent supply (a re-export hub or missing production data).",
  },
  ocs: {
    long: "Origin share",
    short: "OCS",
    definition:
      "Share of the destination's imports of this commodity that comes from this single origin. 0–1.",
  },
  bdi: {
    long: "Bilateral dependency",
    short: "BDI",
    definition:
      "Share of the destination's domestic supply sourced specifically from this origin. 0–1; equals Import reliance × Origin share.",
  },
  hhi: {
    long: "Supplier concentration",
    short: "HHI",
    definition:
      "How concentrated the destination's supplier base is. 0 ≈ many balanced suppliers; 1 = single supplier. ≥0.25 is considered highly concentrated (standard antitrust threshold).",
  },
  ssr: {
    long: "Self-sufficiency",
    short: "SSR",
    definition:
      "Domestic production divided by domestic supply. >1 = net exporter; =1 balanced; <1 means a share of supply must be imported; 0 = no domestic production.",
  },
  ds_prime: {
    long: "Apparent domestic supply",
    short: "DS′",
    definition:
      "Production + imports − exports (+ stock change when known). The denominator of import reliance.",
  },
  his: {
    long: "Hazard intensity",
    short: "HIS",
    definition:
      "Severity-weighted, time-decayed RASFF signal on this lane. Higher means more alert activity weighted toward serious and recent issues.",
  },
  his_norm: {
    long: "Hazard intensity (normalised)",
    short: "HIS₀₋₁",
    definition: "Hazard intensity rescaled to 0–1 by percentile rank, used for the priority score.",
  },
  hdi: {
    long: "Hazard diversity",
    short: "HDI",
    definition:
      "Shannon entropy over six hazard families. 0 = all alerts are the same type; near 1 = alerts span many families.",
  },
  dgi: {
    long: "Detection gap",
    short: "DGI",
    definition:
      "How much the share of notifications on this lane diverges from its share of trade. Helps spot under- or over-reported lanes.",
  },
  cvs: {
    long: "Priority score",
    short: "CVS",
    definition:
      "Combined vulnerability score, 0–1. Blends supply criticality, hazard intensity, and demand pressure (when consumption data is available). Use as a ranking aid; confirm with controls on the ground.",
  },
  crs: {
    long: "Consumption rank",
    short: "CRS",
    definition:
      "Demand-side pressure — how exposed the population is to this commodity (per-capita consumption in destination, rank across destinations). 0–1.",
  },
  crs_norm: {
    long: "Consumption rank (normalised)",
    short: "CRS₀₋₁",
    definition: "Consumption rank rescaled to 0–1.",
  },
  acep: {
    long: "Total inbound exposure",
    short: "ACEP",
    definition:
      "Aggregate corridor exposure — sums hazard-and-dependency-weighted exposure across every lane reaching this country. Higher = more combined pressure.",
  },
  orps: {
    long: "Outbound risk propagation",
    short: "ORPS",
    definition:
      "How much hazard-weighted exposure this origin sends to EU destinations for a commodity. Used to rank origin-country impact.",
  },
  z_uv: {
    long: "Unit-price z-score",
    short: "z(UV)",
    definition:
      "How far this corridor's per-kilogram price sits from typical partner prices. Beyond ±2 is unusual: very low can mean cheap inputs or misclassification; very high can mean premium claims or fraud.",
  },
  mtd: {
    long: "Mirror trade gap",
    short: "MTD",
    definition:
      "Relative disagreement between the reporter's imports and the partner's exports. Large gaps point to reporting issues worth checking.",
  },
  delta_hhi: {
    long: "Concentration change",
    short: "ΔHHI",
    definition:
      "Change in supplier concentration vs the prior period. Positive = consolidating onto fewer suppliers; negative = diversifying.",
  },
};

/** "Import reliance (IDR)" — canonical rendering for headings/labels. */
export function withAbbr(key: MetricKey): string {
  const m = METRIC[key];
  return `${m.long} (${m.short})`;
}

/** Action chip labels surfaced on the priority queue. */
export const ACTION_LABEL = {
  sample: "Sample",
  doc_check: "Documentation check",
  hold: "Hold for testing",
  watch: "Watch",
} as const;

export type ActionKey = keyof typeof ACTION_LABEL;
