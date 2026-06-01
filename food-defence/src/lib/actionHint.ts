/**
 * Suggested follow-up action per corridor — drives the Action chip on the
 * priority queue. Heuristic combining priority band, dominant hazard family,
 * and supplier concentration. Treat as a hint to a human planner, not a rule.
 */

import type { ActionKey } from "./labels";
import type { CorridorMetric, HazardBucket } from "./types";

export interface ActionHint {
  key: ActionKey;
  label: string;
  tone: "high" | "med" | "low";
  reason: string;
}

const LABEL: Record<ActionKey, string> = {
  sample: "Sample",
  doc_check: "Documentation check",
  hold: "Hold for testing",
  watch: "Watch",
};

function dominantHazardKey(c: CorridorMetric): HazardBucket | null {
  const b = c.hazard_breakdown;
  if (!b) return null;
  let bestKey: HazardBucket | null = null;
  let bestVal = 0;
  for (const [k, v] of Object.entries(b) as [HazardBucket, number | undefined][]) {
    const val = v ?? 0;
    if (val > 0 && val > bestVal) {
      bestKey = k;
      bestVal = val;
    }
  }
  return bestKey;
}

export function actionFor(c: CorridorMetric): ActionHint {
  const cvs = c.cvs ?? 0;
  const his = c.his ?? 0;
  const ocs = c.ocs ?? 0;
  const hhi = c.hhi ?? 0;
  const dom = dominantHazardKey(c);

  // Regulatory/labelling — paperwork problem first, not lab.
  if (dom === "regulatory" && (cvs >= 0.5 || his >= 0.5)) {
    return {
      key: "doc_check",
      label: LABEL.doc_check,
      tone: cvs >= 0.75 ? "high" : "med",
      reason: "Recurring labelling or composition flags — review documentation chain.",
    };
  }

  // Top-priority + chemistry/biological — hold and sample.
  if (cvs >= 0.75 || (his >= 0.8 && (cvs === 0 || cvs >= 0.5))) {
    return {
      key: "hold",
      label: LABEL.hold,
      tone: "high",
      reason: "Strong alert pattern with structural exposure — hold a shipment for confirmation testing.",
    };
  }

  // High priority or concentrated single source — sample.
  if (cvs >= 0.5 || (ocs >= 0.7 && his >= 0.3) || (hhi >= 0.5 && his >= 0.3)) {
    return {
      key: "sample",
      label: LABEL.sample,
      tone: "high",
      reason: "Combined hazard and structural exposure justify a targeted sample.",
    };
  }

  // Medium activity or rising concentration — watch.
  if (cvs >= 0.3 || his >= 0.3 || hhi >= 0.5) {
    return {
      key: "watch",
      label: LABEL.watch,
      tone: "med",
      reason: "Monitor for change in alert pattern or supplier mix.",
    };
  }

  return {
    key: "watch",
    label: LABEL.watch,
    tone: "low",
    reason: "Low signal — keep on the watchlist only.",
  };
}
