"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Activity } from "lucide-react";

export default function DashboardHeader() {
  const [period, setPeriod] = useState<number>(0);
  const [status, setStatus] = useState<"ok" | "error">("ok");
  const [corridorCount, setCorridorCount] = useState<number | null>(null);

  useEffect(() => {
    Promise.all([api.hazards.summary(), api.health()])
      .then(([s, h]) => {
        setPeriod(s.current_period);
        setStatus("ok");
        setCorridorCount(h.data?.corridor_metrics ?? null);
      })
      .catch(() => setStatus("error"));
  }, []);

  const periodLabel = period
    ? `${Math.floor(period / 100)}-${String(period % 100).padStart(2, "0")}`
    : "…";

  return (
    <header className="sticky top-0 z-20 flex h-14 items-center justify-between border-b border-slate-200/90 bg-white/85 px-6 backdrop-blur-md">
      <p className="text-xs font-medium text-slate-500">
        Priorities, diagnostics, and live data
      </p>
      <div className="flex items-center gap-3">
        {corridorCount != null && (
          <span className="hidden rounded-lg border border-slate-200/90 bg-slate-50 px-2.5 py-1 text-[11px] text-slate-600 sm:inline">
            <span className="font-mono font-semibold text-slate-800">{corridorCount}</span>{" "}
            corridors loaded
          </span>
        )}
        <span
          className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium ${
            status === "ok"
              ? "border-emerald-200/90 bg-emerald-50 text-emerald-800"
              : "border-red-200/90 bg-red-50 text-red-800"
          }`}
        >
          <Activity size={12} className={status === "ok" ? "text-emerald-500" : "text-red-500"} aria-hidden />
          API {status === "ok" ? "live" : "offline"}
        </span>
        <span className="hidden h-4 w-px bg-slate-200 sm:block" aria-hidden />
        <span className="text-xs tabular-nums text-slate-500">
          Period <span className="font-medium text-slate-800">{periodLabel}</span>
        </span>
      </div>
    </header>
  );
}
