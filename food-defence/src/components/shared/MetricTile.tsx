"use client";

import type { LucideIcon } from "lucide-react";
import { bandClasses, type Band } from "@/lib/interpret";
import MetricHelp from "@/components/shared/MetricHelp";

interface MetricTileProps {
  /** Plain-language primary label, e.g. "Import reliance". */
  label: string;
  /** Optional acronym shown faintly next to label, e.g. "IDR". */
  abbr?: string;
  /** Pre-formatted value string (the caller decides decimals / units). */
  value: string;
  /** Tiny unit suffix like "kg" or "%". Rendered next to value. */
  unit?: string;
  /** Plain-language interpretation, one sentence. */
  verdict?: string;
  /** Band drives colour treatment for value and verdict. */
  band?: Band;
  /** Ratio 0–1 for an optional inline bar under the value. */
  bar?: number;
  /** Optional small icon next to the label. */
  icon?: LucideIcon;
  /** Optional badge ("FAOSTAT", "Trade-only", …) shown in the top-right. */
  badge?: { label: string; tone: "ok" | "warn" };
  /** Optional caption below verdict (raw formula / context). */
  caption?: string;
  /** Metric key (e.g. "idr") — when set, a "?" help icon opens the Glossary entry. */
  metricKey?: string;
}

const VALUE_TONE: Record<Band, string> = {
  low: "text-emerald-700",
  med: "text-orange-600",
  high: "text-red-600",
  flag: "text-amber-700",
};

const BADGE_TONE = {
  ok: "border-emerald-200 bg-emerald-50 text-emerald-700",
  warn: "border-amber-200 bg-amber-50 text-amber-700",
};

export default function MetricTile({
  label,
  abbr,
  value,
  unit,
  verdict,
  band = "low",
  bar,
  icon: Icon,
  badge,
  caption,
  metricKey,
}: MetricTileProps) {
  const c = bandClasses(band);
  const valueColor = VALUE_TONE[band];
  const ratio = bar != null ? Math.max(0, Math.min(1, bar)) : null;

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm transition hover:border-slate-300 hover:shadow-md">
      <div className="mb-1 flex items-start justify-between gap-2">
        <div className="flex items-center gap-1.5">
          {Icon && <Icon size={14} className="text-slate-400" aria-hidden />}
          <p className="text-xs font-semibold text-slate-700">
            {label}
            {abbr && (
              <span className="ml-1 font-normal text-[10px] uppercase tracking-wide text-slate-400">
                ({abbr})
              </span>
            )}
          </p>
          {metricKey && <MetricHelp metricKey={metricKey} label={label} />}
        </div>
        {badge && (
          <span
            className={`shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-medium ${BADGE_TONE[badge.tone]}`}
            title={badge.label}
          >
            {badge.label}
          </span>
        )}
      </div>

      <div className="flex items-baseline gap-1">
        <p className={`font-mono text-2xl font-semibold tracking-tight ${valueColor}`}>{value}</p>
        {unit && <span className="text-xs text-slate-500">{unit}</span>}
      </div>

      {ratio != null && (
        <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
          <div
            className={`${VALUE_TONE[band].replace("text-", "bg-")} h-full transition-all`}
            style={{ width: `${ratio * 100}%` }}
          />
        </div>
      )}

      {verdict && (
        <p
          className={`mt-2 rounded-md border px-2 py-1.5 text-[11px] leading-snug ${c.bg} ${c.border} ${c.text}`}
        >
          {verdict}
        </p>
      )}

      {caption && <p className="mt-2 text-[10px] text-slate-400">{caption}</p>}
    </div>
  );
}
