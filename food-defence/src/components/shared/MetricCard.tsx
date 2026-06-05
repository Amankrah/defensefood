"use client";

import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

interface MetricCardProps {
  label: string;
  value: string | number;
  subtext?: string;
  icon?: LucideIcon;
  /** Semantic tone for the icon badge */
  tone?: "danger" | "warning" | "caution" | "info" | "neutral";
  footer?: ReactNode;
}

const TONE_STYLES = {
  danger: {
    badge: "bg-red-500/10 text-red-600 ring-1 ring-red-500/20",
    value: "text-red-700",
  },
  warning: {
    badge: "bg-orange-500/10 text-orange-600 ring-1 ring-orange-500/20",
    value: "text-orange-700",
  },
  caution: {
    badge: "bg-amber-500/10 text-amber-600 ring-1 ring-amber-500/20",
    value: "text-amber-700",
  },
  info: {
    badge: "bg-blue-500/10 text-blue-600 ring-1 ring-blue-500/20",
    value: "text-slate-900",
  },
  neutral: {
    badge: "bg-slate-500/10 text-slate-600 ring-1 ring-slate-500/15",
    value: "text-slate-900",
  },
} as const;

export default function MetricCard({
  label,
  value,
  subtext,
  icon: Icon,
  tone = "info",
  footer,
}: MetricCardProps) {
  const styles = TONE_STYLES[tone];

  return (
    <div className="df-card df-card-interactive p-4">
      <div className="mb-2 flex items-start justify-between gap-2">
        <span className="text-xs font-medium leading-snug text-slate-500">
          {label}
        </span>
        {Icon && (
          <span
            className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${styles.badge}`}
          >
            <Icon size={15} aria-hidden />
          </span>
        )}
      </div>
      <p
        className={`font-mono text-2xl font-semibold tracking-tight ${styles.value}`}
      >
        {value}
      </p>
      {subtext && (
        <p className="mt-1.5 text-[11px] leading-relaxed text-slate-500">
          {subtext}
        </p>
      )}
      {footer && (
        <p className="mt-2 border-t border-slate-100 pt-2 text-[10px] text-slate-500">
          {footer}
        </p>
      )}
    </div>
  );
}
