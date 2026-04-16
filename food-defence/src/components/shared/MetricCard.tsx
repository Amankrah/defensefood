"use client";

import type { LucideIcon } from "lucide-react";

interface MetricCardProps {
  label: string;
  value: string | number;
  subtext?: string;
  icon?: LucideIcon;
  color?: string; // Tailwind bg class
}

export default function MetricCard({
  label,
  value,
  subtext,
  icon: Icon,
  color = "bg-blue-500",
}: MetricCardProps) {
  return (
    <div className="rounded-2xl border border-slate-200/90 bg-white p-4 shadow-sm transition hover:border-slate-300/90 hover:shadow-md">
      <div className="mb-1.5 flex items-center gap-2.5">
        {Icon && (
          <div className={`rounded-lg p-1.5 shadow-sm ${color}`}>
            <Icon size={14} className="text-white" />
          </div>
        )}
        <span className="text-xs font-medium text-slate-500">{label}</span>
      </div>
      <p className="font-mono text-xl font-semibold tracking-tight text-slate-900">{value}</p>
      {subtext && (
        <p className="mt-0.5 text-[11px] text-slate-400">{subtext}</p>
      )}
    </div>
  );
}
