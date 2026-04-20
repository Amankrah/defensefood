"use client";

import type { RasffRole } from "@/lib/types";

const ROLE_STYLE: Record<RasffRole, { bg: string; text: string; label: string; tip: string }> = {
  notifier: {
    bg: "bg-rose-100",
    text: "text-rose-700",
    label: "Notifier",
    tip: "Detected / reported the hazard",
  },
  distribution: {
    bg: "bg-indigo-100",
    text: "text-indigo-700",
    label: "Distribution",
    tip: "Product was physically shipped here",
  },
  followUp: {
    bg: "bg-amber-100",
    text: "text-amber-800",
    label: "Follow-up",
    tip: "Must actively investigate and report back (ffup)",
  },
  attention: {
    bg: "bg-slate-100",
    text: "text-slate-600",
    label: "Attention",
    tip: "Passively concerned; no active response required (ffa)",
  },
};

const ROLE_ORDER: RasffRole[] = ["notifier", "distribution", "followUp", "attention"];

export function RolePill({ role }: { role: RasffRole }) {
  const s = ROLE_STYLE[role];
  return (
    <span
      title={s.tip}
      className={`inline-flex items-center rounded-full px-1.5 py-0.5 text-[10px] font-medium leading-none ${s.bg} ${s.text}`}
    >
      {s.label}
    </span>
  );
}

export function RolePills({
  roles,
  compact = false,
}: {
  roles?: RasffRole[];
  compact?: boolean;
}) {
  if (!roles || roles.length === 0) return null;
  // Render in canonical order for visual stability
  const ordered = ROLE_ORDER.filter((r) => roles.includes(r));
  return (
    <span className={`inline-flex flex-wrap gap-1 ${compact ? "" : ""}`}>
      {ordered.map((r) => (
        <RolePill key={r} role={r} />
      ))}
    </span>
  );
}
