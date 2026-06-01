/**
 * One-sentence "why this lane matters" for the priority queue table.
 *
 * Combines dominant hazard family, alert count, supplier concentration, and
 * import reliance into a single decision-oriented prose line. Falls back
 * gracefully when dependency or hazard data is missing.
 */

import type { CorridorMetric, HazardBreakdown, HazardBucket } from "./types";

const HAZARD_FAMILY_LABEL: Record<HazardBucket, string> = {
  biological: "microbial",
  chem_pesticides: "pesticide",
  chem_heavy_metals: "heavy-metal",
  chem_mycotoxins: "mycotoxin",
  chem_other: "chemical",
  regulatory: "labelling/regulatory",
};

function dominantFamily(b?: HazardBreakdown): { label: string; share: number } | null {
  if (!b) return null;
  const entries = (Object.entries(b) as [HazardBucket, number | undefined][]).filter(
    ([, v]) => (v ?? 0) > 0
  );
  if (!entries.length) return null;
  const total = entries.reduce((s, [, v]) => s + (v ?? 0), 0);
  entries.sort((a, b) => (b[1] ?? 0) - (a[1] ?? 0));
  const [key, val] = entries[0];
  return { label: HAZARD_FAMILY_LABEL[key], share: total > 0 ? (val ?? 0) / total : 0 };
}

function pct(x: number): string {
  return `${Math.round(x * 100)}%`;
}

/** Returns a short prose sentence; never undefined. */
export function whyLine(c: CorridorMetric): string {
  const parts: string[] = [];

  // Hazard pillar
  if (c.notification_count > 0) {
    const fam = dominantFamily(c.hazard_breakdown);
    if (fam && fam.share >= 0.5) {
      parts.push(
        `${c.notification_count} alerts (mostly ${fam.label})`
      );
    } else if (fam) {
      parts.push(`${c.notification_count} alerts (${fam.label} leading)`);
    } else {
      parts.push(`${c.notification_count} alerts on this lane`);
    }
  } else if (c.his > 0) {
    parts.push("recent alert activity");
  }

  // Dependency pillar — only when we have a dependency profile
  const hasDep = c.sci != null;
  if (hasDep) {
    if (c.idr_gt_1) {
      parts.push("imports exceed apparent supply (transit hub or no production data)");
    } else if ((c.ocs ?? 0) >= 0.9) {
      parts.push(`almost all imports from this origin (${pct(c.ocs ?? 0)})`);
    } else if ((c.ocs ?? 0) >= 0.5 && (c.hhi ?? 0) >= 0.25) {
      parts.push(
        `${pct(c.ocs ?? 0)} from this origin, suppliers concentrated`
      );
    } else if ((c.hhi ?? 0) >= 0.5) {
      parts.push("supplier base concentrated");
    } else if ((c.idr ?? 0) >= 0.75) {
      parts.push("heavily import-dependent");
    }

    if ((c.ssr ?? null) != null && (c.ssr ?? 1) < 0.1 && !c.idr_gt_1) {
      parts.push("no domestic production");
    }
  }

  // CVS framing if available — adds the urgency cue.
  if (c.cvs != null) {
    if (c.cvs >= 0.75) parts.unshift("top-priority");
    else if (c.cvs >= 0.5) parts.unshift("high-priority");
  }

  if (!parts.length) {
    if (hasDep) return "Low hazard signal; diversified supply.";
    return "Awaiting dependency data — ranked on hazard alone.";
  }

  // Capitalise first letter, join with commas, ensure trailing period.
  const sentence = parts
    .join(", ")
    .replace(/^./, (m) => m.toUpperCase());
  return sentence.endsWith(".") ? sentence : sentence + ".";
}
