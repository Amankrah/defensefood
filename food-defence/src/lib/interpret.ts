/**
 * Plain-language verdict generators for blueprint metrics.
 *
 * Each interpreter takes a metric value (and sometimes context) and returns a
 * short sentence plus a four-stop band. Used by MetricTile and VerdictBanner
 * so the UI never asks the user to map a bare number onto a meaning.
 */

export type Band = "low" | "med" | "high" | "flag";

export interface Verdict {
  verdict: string;
  band: Band;
}

const NA: Verdict = { verdict: "Not available.", band: "low" };

function isNum(v: number | null | undefined): v is number {
  return v != null && !Number.isNaN(v);
}

/** Import Reliance (IDR): M / DS′. */
export function interpretIdr(idr: number | null | undefined): Verdict {
  if (!isNum(idr)) return NA;
  if (idr > 1)
    return {
      verdict: "Imports exceed apparent supply — re-export hub, or production data missing.",
      band: "flag",
    };
  if (idr >= 0.75)
    return { verdict: "Heavily import-dependent; little domestic cushion.", band: "high" };
  if (idr >= 0.4) return { verdict: "Partly import-dependent.", band: "med" };
  if (idr > 0.05) return { verdict: "Mostly produced at home.", band: "low" };
  return { verdict: "Fully self-sufficient — no imports.", band: "low" };
}

/** Origin Country Share (OCS): M_ij / M. */
export function interpretOcs(ocs: number | null | undefined): Verdict {
  if (!isNum(ocs)) return NA;
  if (ocs >= 0.9)
    return { verdict: "Dominant origin — almost all imports come from this country.", band: "high" };
  if (ocs >= 0.5)
    return { verdict: "Majority origin — over half of imports come from here.", band: "high" };
  if (ocs >= 0.2)
    return { verdict: "Significant origin — a meaningful slice of the import mix.", band: "med" };
  if (ocs > 0) return { verdict: "Minor origin within a diverse import mix.", band: "low" };
  return { verdict: "No imports from this origin in the period.", band: "low" };
}

/** Herfindahl–Hirschman Index (HHI) over partner shares. */
export function interpretHhi(hhi: number | null | undefined): Verdict {
  if (!isNum(hhi)) return NA;
  if (hhi >= 0.9)
    return { verdict: "Near-monopoly sourcing — one supplier dominates.", band: "high" };
  if (hhi >= 0.5) return { verdict: "Very concentrated — few effective suppliers.", band: "high" };
  if (hhi >= 0.25)
    return { verdict: "Highly concentrated by antitrust standards.", band: "med" };
  if (hhi >= 0.1)
    return { verdict: "Moderately diversified across several suppliers.", band: "low" };
  return { verdict: "Well diversified across many suppliers.", band: "low" };
}

/** Self-Sufficiency Ratio (SSR): P / D. */
export function interpretSsr(ssr: number | null | undefined): Verdict {
  if (!isNum(ssr)) return NA;
  if (ssr >= 1.1) return { verdict: "Net exporter — produces more than it consumes.", band: "low" };
  if (ssr >= 0.9) return { verdict: "Roughly balanced production and supply.", band: "low" };
  if (ssr >= 0.5) return { verdict: "Partly produced locally; the rest is imported.", band: "med" };
  if (ssr > 0)
    return { verdict: "Almost entirely imported — small domestic production.", band: "high" };
  return { verdict: "No domestic production — fully reliant on imports.", band: "high" };
}

/** Supply Criticality Index (SCI), 0–2. */
export function interpretSci(sci: number | null | undefined): Verdict {
  if (!isNum(sci)) return NA;
  if (sci >= 1.5)
    return { verdict: "Critical exposure — concentrated source, weak fallback.", band: "high" };
  if (sci >= 1.0) return { verdict: "High exposure — limited alternatives.", band: "high" };
  if (sci >= 0.5) return { verdict: "Moderate exposure on this lane.", band: "med" };
  if (sci > 0) return { verdict: "Low structural exposure — diversified supply.", band: "low" };
  return { verdict: "Negligible exposure on this lane.", band: "low" };
}

/** Composite Vulnerability Score (CVS), 0–1. */
export function interpretCvs(cvs: number | null | undefined): Verdict {
  if (!isNum(cvs)) return NA;
  if (cvs >= 0.75)
    return { verdict: "Top priority — sample and review this period.", band: "high" };
  if (cvs >= 0.5)
    return { verdict: "High priority — schedule a targeted check.", band: "high" };
  if (cvs >= 0.3) return { verdict: "Watchlist — monitor for changes.", band: "med" };
  return { verdict: "Low priority — no immediate action.", band: "low" };
}

/** Hazard Intensity (HIS), unbounded but typically 0–~2. */
export function interpretHis(his: number | null | undefined): Verdict {
  if (!isNum(his)) return NA;
  if (his >= 1.0) return { verdict: "Strong, recent, severe alert pattern.", band: "high" };
  if (his >= 0.5) return { verdict: "Notable alert activity worth a closer look.", band: "high" };
  if (his >= 0.2) return { verdict: "Some alert activity in the window.", band: "med" };
  if (his > 0) return { verdict: "Light alert activity.", band: "low" };
  return { verdict: "No alerts logged on this lane.", band: "low" };
}

/** Hazard Diversity (HDI), Shannon entropy 0–1. */
export function interpretHdi(hdi: number | null | undefined): Verdict {
  if (!isNum(hdi)) return NA;
  if (hdi >= 0.7) return { verdict: "Alerts span many hazard families.", band: "med" };
  if (hdi >= 0.3) return { verdict: "Mix of a few hazard families.", band: "med" };
  if (hdi > 0)
    return { verdict: "Most alerts share one hazard family — a recurring pattern.", band: "high" };
  return { verdict: "Single hazard family or no alerts.", band: "low" };
}

/** Detection Gap Indicator (Section 4.5) — signed gap roughly [-1, +1]. */
export function interpretDgi(dgi: number | null | undefined): Verdict {
  if (!isNum(dgi)) return NA;
  if (dgi >= 0.4)
    return {
      verdict: "Large trade flow with little alert activity — strong under-detection signal.",
      band: "high",
    };
  if (dgi >= 0.1)
    return {
      verdict: "Trade share exceeds notification share — possibly under-inspected.",
      band: "med",
    };
  if (dgi >= -0.1)
    return { verdict: "Notification share roughly tracks trade share.", band: "low" };
  if (dgi >= -0.4)
    return {
      verdict: "Lane gets more attention than its trade share would predict.",
      band: "med",
    };
  return {
    verdict: "Notification rate far exceeds trade share — already under intense scrutiny.",
    band: "high",
  };
}

/** Unit-price z-score (Section 5). */
export function interpretZuv(z: number | null | undefined): Verdict {
  if (!isNum(z)) return NA;
  if (z <= -2)
    return {
      verdict: "Priced far below peers — verify quality, grading, or undervaluation.",
      band: "flag",
    };
  if (z >= 2)
    return {
      verdict: "Priced far above peers — check premium claims or misclassification.",
      band: "flag",
    };
  if (Math.abs(z) >= 1) return { verdict: "Somewhat outside the typical price range.", band: "med" };
  return { verdict: "Price sits within the typical range for partner peers.", band: "low" };
}

/** Mirror trade discrepancy (MTD) — relative reporting gap. */
export function interpretMtd(mtd: number | null | undefined): Verdict {
  if (!isNum(mtd)) return NA;
  const a = Math.abs(mtd);
  if (a >= 0.5)
    return { verdict: "Reporter and partner volumes diverge sharply — verify both sides.", band: "flag" };
  if (a >= 0.3) return { verdict: "Notable reporting gap between sides.", band: "med" };
  if (a >= 0.1) return { verdict: "Small reporting gap, within usual noise.", band: "low" };
  return { verdict: "Reporter and partner figures align.", band: "low" };
}

/** Volume anomaly z-score on a corridor's own import history (Section 5.2). */
export function interpretVolume(z: number | null | undefined): Verdict {
  if (!isNum(z)) return NA;
  if (z >= 2)
    return {
      verdict: "Trade surge — large jump vs. corridor history; possible re-routing.",
      band: "flag",
    };
  if (z >= 1) return { verdict: "Volume mildly above the corridor's trend.", band: "med" };
  if (z >= -1) return { verdict: "Volume tracks the corridor's historical pattern.", band: "low" };
  if (z >= -2) return { verdict: "Volume below the corridor's trend.", band: "med" };
  return {
    verdict: "Volume collapse vs. history — check for substitution or origin shift.",
    band: "flag",
  };
}

/** Origin share change ΔOCS (Section 5.4) — sign-aware. */
export function interpretDeltaOcs(delta: number | null | undefined): Verdict {
  if (!isNum(delta)) return NA;
  if (delta >= 0.20)
    return { verdict: "Surging share — possible re-routing signal.", band: "high" };
  if (delta >= 0.05) return { verdict: "Origin gaining share in the import mix.", band: "med" };
  if (delta >= -0.05)
    return { verdict: "Origin's contribution to imports roughly unchanged.", band: "low" };
  if (delta >= -0.20)
    return { verdict: "Origin's share modestly declining.", band: "low" };
  return {
    verdict: "Origin losing share fast — note where the share moved.",
    band: "med",
  };
}

/** Concentration change ΔHHI — sign-aware. */
export function interpretDeltaHhi(delta: number | null | undefined): Verdict {
  if (!isNum(delta)) return NA;
  if (delta >= 0.1)
    return { verdict: "Concentrating fast — sourcing onto fewer suppliers.", band: "high" };
  if (delta >= 0.03) return { verdict: "Concentration drifting upward.", band: "med" };
  if (delta <= -0.1)
    return { verdict: "Diversifying — more suppliers entering the mix.", band: "low" };
  if (delta <= -0.03)
    return { verdict: "Mildly diversifying vs the prior window.", band: "low" };
  return { verdict: "Concentration roughly unchanged.", band: "low" };
}

/** Per-capita apparent consumption (kg/capita/year). */
export function interpretPcc(pcc: number | null | undefined): Verdict {
  if (!isNum(pcc)) return NA;
  if (pcc >= 50) return { verdict: "Staple-level consumption per person.", band: "high" };
  if (pcc >= 10) return { verdict: "Notable share of the average diet.", band: "med" };
  if (pcc >= 1) return { verdict: "Modest dietary role.", band: "low" };
  return { verdict: "Niche or minimal consumption.", band: "low" };
}

/** Commodity consumption rank within a country (0-1). */
export function interpretCrs(crs: number | null | undefined): Verdict {
  if (!isNum(crs)) return NA;
  if (crs >= 0.75) return { verdict: "Top-rank staple in this country's diet.", band: "high" };
  if (crs >= 0.50) return { verdict: "Above-median dietary importance.", band: "med" };
  if (crs >= 0.25) return { verdict: "Mid-rank commodity in the local basket.", band: "low" };
  return { verdict: "Low-rank commodity for this destination.", band: "low" };
}

/** Demand inelasticity (0-1; high = stable / culturally entrenched). */
export function interpretDis(dis: number | null | undefined): Verdict {
  if (!isNum(dis)) return NA;
  if (dis >= 0.95) return { verdict: "Highly inelastic — culturally entrenched, maximally exploitable.", band: "high" };
  if (dis >= 0.80) return { verdict: "Stable demand — consumers stick with it through shocks.", band: "high" };
  if (dis >= 0.50) return { verdict: "Moderately stable demand pattern.", band: "med" };
  return { verdict: "Volatile demand — substitutes available, swing-y consumption.", band: "low" };
}

/** ACEP — country-level inbound exposure. Coarse heuristic until we calibrate. */
export function interpretAcep(acep: number | null | undefined): Verdict {
  if (!isNum(acep)) return NA;
  if (acep >= 1.0) return { verdict: "Heavy combined pressure across inbound lanes.", band: "high" };
  if (acep >= 0.3) return { verdict: "Notable inbound exposure to monitor.", band: "med" };
  if (acep > 0) return { verdict: "Light inbound exposure.", band: "low" };
  return { verdict: "Negligible inbound exposure in scope.", band: "low" };
}

/** Map a band to text-colour and background-50 Tailwind classes. */
export function bandClasses(band: Band): { text: string; bg: string; border: string } {
  switch (band) {
    case "high":
      return { text: "text-red-600", bg: "bg-red-50", border: "border-red-200" };
    case "flag":
      return { text: "text-amber-700", bg: "bg-amber-50", border: "border-amber-200" };
    case "med":
      return { text: "text-orange-600", bg: "bg-orange-50", border: "border-orange-200" };
    case "low":
    default:
      return { text: "text-emerald-700", bg: "bg-emerald-50", border: "border-emerald-200" };
  }
}
