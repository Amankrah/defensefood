"use client";

import type { MarketPresence } from "@/lib/types";

const PRESENCE_STYLE: Record<MarketPresence, {
  bg: string;
  text: string;
  ring: string;
  dot: string;
  label: string;
  caption: string;
  tip: string;
}> = {
  confirmed: {
    bg: "bg-emerald-50",
    text: "text-emerald-800",
    ring: "ring-emerald-200",
    dot: "bg-emerald-500",
    label: "On market",
    caption: "Confirmed market presence",
    tip:
      "RASFF flagged this destination with distribution or follow-up: the product is or may be placed on this market. " +
      "Structural dependency and trade-flow metrics are meaningful for this lane.",
  },
  detected: {
    bg: "bg-sky-50",
    text: "text-sky-800",
    ring: "ring-sky-200",
    dot: "bg-sky-500",
    label: "Detected here",
    caption: "Notifier-only (no distribution evidence)",
    tip:
      "Only the notifier role flagged this country. It is often (but not always) the importer that caught the hazard. " +
      "Comtrade dependency may apply — read with caution.",
  },
  informational: {
    bg: "bg-slate-50",
    text: "text-slate-700",
    ring: "ring-slate-200",
    dot: "bg-slate-400",
    label: "Informational only",
    caption: "Not on this market (per RASFF)",
    tip:
      "RASFF for_attention only: per EU SOPs, the product is not on this country's market — it is only in the notifying " +
      "country, no longer on market, or was never placed on market. Structural metrics shown for transparency are not " +
      "meaningful for ranking this lane.",
  },
  unknown: {
    bg: "bg-slate-50",
    text: "text-slate-500",
    ring: "ring-slate-200",
    dot: "bg-slate-300",
    label: "Unclassified",
    caption: "No RASFF role recorded",
    tip: "No RASFF role was recorded for this corridor. Investigate the source data.",
  },
};

export function MarketPresenceBadge({
  presence,
  variant = "pill",
}: {
  presence?: MarketPresence | null;
  variant?: "pill" | "block";
}) {
  const key: MarketPresence = presence ?? "unknown";
  const s = PRESENCE_STYLE[key];
  if (variant === "block") {
    return (
      <div
        className={`inline-flex items-start gap-2 rounded-md px-2 py-1.5 ring-1 ${s.bg} ${s.ring}`}
        title={s.tip}
      >
        <span className={`mt-1 h-2 w-2 shrink-0 rounded-full ${s.dot}`} />
        <span className="flex flex-col leading-tight">
          <span className={`text-xs font-semibold ${s.text}`}>{s.label}</span>
          <span className="text-[10px] text-slate-500">{s.caption}</span>
        </span>
      </div>
    );
  }
  return (
    <span
      title={s.tip}
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ${s.bg} ${s.text} ${s.ring}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${s.dot}`} />
      {s.label}
    </span>
  );
}

export const MARKET_PRESENCE_LABELS: Record<MarketPresence, string> = {
  confirmed: "On market (confirmed)",
  detected: "Detected here (notifier-only)",
  informational: "Informational only (not on market)",
  unknown: "Unclassified",
};
