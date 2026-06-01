"use client";

import type { LucideIcon } from "lucide-react";
import { bandClasses, type Band } from "@/lib/interpret";

interface VerdictBannerProps {
  /** Headline (1–2 words) describing the verdict, e.g. "Top priority". */
  title: string;
  /** Multi-sentence synthesis paragraph in plain language. */
  body: string;
  band?: Band;
  icon?: LucideIcon;
  /** Optional right-aligned chip (e.g. action hint, score badge). */
  chip?: { label: string; tone?: "high" | "med" | "low" };
}

const CHIP_TONE = {
  high: "border-red-200 bg-red-50 text-red-700",
  med: "border-orange-200 bg-orange-50 text-orange-700",
  low: "border-slate-200 bg-slate-50 text-slate-700",
};

export default function VerdictBanner({
  title,
  body,
  band = "med",
  icon: Icon,
  chip,
}: VerdictBannerProps) {
  const c = bandClasses(band);
  return (
    <div
      className={`flex items-start gap-3 rounded-xl border px-4 py-3 ${c.bg} ${c.border}`}
    >
      {Icon && (
        <div className="mt-0.5 shrink-0 rounded-lg bg-white/70 p-1.5 shadow-sm">
          <Icon size={14} className={c.text} aria-hidden />
        </div>
      )}
      <div className="min-w-0 flex-1">
        <p className={`text-xs font-semibold uppercase tracking-wide ${c.text}`}>{title}</p>
        <p className="mt-1 text-sm leading-snug text-slate-800">{body}</p>
      </div>
      {chip && (
        <span
          className={`shrink-0 rounded-full border px-2.5 py-1 text-[11px] font-medium ${CHIP_TONE[chip.tone ?? "low"]}`}
        >
          {chip.label}
        </span>
      )}
    </div>
  );
}
