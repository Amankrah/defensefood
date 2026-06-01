"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "@/lib/api";
import type { CorridorMetric, LaneTimeSeries } from "@/lib/types";
import { fmt, truncate } from "@/lib/utils";

type SubTab = "lane" | "aggregate";

const SERIES_KEYS: { key: string; label: string; color: string }[] = [
  { key: "idr", label: "IDR (import reliance)", color: "#3b82f6" },
  { key: "ocs", label: "OCS (origin share)", color: "#10b981" },
  { key: "hhi", label: "HHI (concentration)", color: "#f97316" },
  { key: "sci", label: "SCI (criticality)", color: "#ef4444" },
];

export default function TimeSeries() {
  const [sub, setSub] = useState<SubTab>("lane");
  const [corridors, setCorridors] = useState<CorridorMetric[]>([]);
  const [pick, setPick] = useState<string>("");
  const [series, setSeries] = useState<LaneTimeSeries | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.corridors
      .top(100, "his")
      .then((r) => setCorridors(r.corridors))
      .catch(() => setCorridors([]));
  }, []);

  useEffect(() => {
    if (!pick) {
      setSeries(null);
      return;
    }
    const [hs, dest, origin] = pick.split("|");
    let cancelled = false;
    setLoading(true);
    setError(null);
    api.corridors
      .timeSeries(hs, parseInt(dest, 10), parseInt(origin, 10))
      .then((r) => {
        if (!cancelled) setSeries(r);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [pick]);

  const depData = useMemo(() => {
    if (!series) return [];
    const periods = Object.keys(series.dependency_by_period).sort();
    return periods.map((p) => {
      const row = series.dependency_by_period[p];
      return {
        period: p,
        idr: typeof row?.idr === "number" ? row.idr : null,
        ocs: typeof row?.ocs === "number" ? row.ocs : null,
        hhi: typeof row?.hhi === "number" ? row.hhi : null,
        sci: typeof row?.sci === "number" ? row.sci : null,
      };
    });
  }, [series]);

  const monthData = useMemo(() => {
    if (!series) return [];
    return Object.entries(series.notifications_by_month)
      .map(([k, v]) => ({ period: k, count: v }))
      .sort((a, b) => a.period.localeCompare(b.period));
  }, [series]);

  return (
    <div className="space-y-4">
      <nav
        className="flex gap-1 rounded-xl border border-slate-200 bg-white p-1 shadow-sm"
        role="tablist"
      >
        <button
          type="button"
          onClick={() => setSub("lane")}
          className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${
            sub === "lane"
              ? "bg-blue-600 text-white"
              : "text-slate-600 hover:bg-slate-50"
          }`}
        >
          Single lane
        </button>
        <button
          type="button"
          onClick={() => setSub("aggregate")}
          className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${
            sub === "aggregate"
              ? "bg-blue-600 text-white"
              : "text-slate-600 hover:bg-slate-50"
          }`}
        >
          Aggregate
        </button>
      </nav>

      {sub === "lane" && (
        <>
          <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
            <label className="block text-[11px] font-medium text-slate-500">
              Pick a lane (top 100 by hazard)
            </label>
            <select
              value={pick}
              onChange={(e) => setPick(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-200 px-2 py-1.5 text-sm"
            >
              <option value="">— select —</option>
              {corridors.map((c) => (
                <option
                  key={`${c.commodity_hs}|${c.destination_m49}|${c.origin_m49}`}
                  value={`${c.commodity_hs}|${c.destination_m49}|${c.origin_m49}`}
                >
                  {c.origin_country} → {c.destination_country} ·{" "}
                  {truncate(c.commodity_name, 30)} (HS {c.commodity_hs})
                </option>
              ))}
            </select>
          </section>

          {error && (
            <p className="rounded-md border border-red-200 bg-red-50 px-3 py-1.5 text-xs text-red-700">
              {error}
            </p>
          )}

          {!pick && (
            <p className="rounded-md border border-dashed border-slate-200 bg-slate-50 px-3 py-3 text-xs text-slate-500">
              Pick a lane above to see its dependency snapshots per trade year and
              its RASFF notification timeline.
            </p>
          )}

          {loading && (
            <p className="text-[10px] text-slate-500 animate-pulse">Loading…</p>
          )}

          {series && (
            <>
              <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
                <h2 className="mb-1 text-sm font-semibold text-slate-900">
                  Dependency metrics by trade year
                </h2>
                <p className="mb-3 text-[11px] text-slate-500">
                  Section 2 pipeline re-run for each available trade year. Lines drop
                  out where a metric is missing for that period.
                </p>
                {depData.length === 0 ? (
                  <p className="text-xs text-slate-500">
                    No dependency snapshots — likely no bilateral trade data for this lane.
                  </p>
                ) : (
                  <ResponsiveContainer width="100%" height={240}>
                    <LineChart data={depData}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                      <XAxis dataKey="period" tick={{ fontSize: 11 }} />
                      <YAxis tick={{ fontSize: 10 }} />
                      <Tooltip
                        formatter={(v) => fmt(Number(v))}
                        contentStyle={{ fontSize: 11 }}
                      />
                      {SERIES_KEYS.map((s) => (
                        <Line
                          key={s.key}
                          type="monotone"
                          dataKey={s.key}
                          name={s.label}
                          stroke={s.color}
                          strokeWidth={2}
                          dot={{ r: 3 }}
                          connectNulls
                        />
                      ))}
                    </LineChart>
                  </ResponsiveContainer>
                )}
                {depData.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-3 text-[11px]">
                    {SERIES_KEYS.map((s) => (
                      <span
                        key={s.key}
                        className="inline-flex items-center gap-1.5 text-slate-600"
                      >
                        <span
                          className="h-2 w-3 rounded-sm"
                          style={{ backgroundColor: s.color }}
                          aria-hidden
                        />
                        {s.label}
                      </span>
                    ))}
                  </div>
                )}
              </section>

              <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
                <h2 className="mb-1 text-sm font-semibold text-slate-900">
                  RASFF notifications by month
                </h2>
                <p className="mb-3 text-[11px] text-slate-500">
                  Count of distinct RASFF references on this lane in each YYYYMM bucket.
                </p>
                {monthData.length === 0 ? (
                  <p className="text-xs text-slate-500">No notifications recorded.</p>
                ) : (
                  <ResponsiveContainer width="100%" height={200}>
                    <BarChart data={monthData}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                      <XAxis dataKey="period" tick={{ fontSize: 10 }} />
                      <YAxis tick={{ fontSize: 10 }} allowDecimals={false} />
                      <Tooltip contentStyle={{ fontSize: 11 }} />
                      <Bar dataKey="count" fill="#ef4444" />
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </section>
            </>
          )}
        </>
      )}

      {sub === "aggregate" && (
        <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <p className="text-xs text-slate-600">
            Aggregate cross-corridor time series is not wired yet — the per-month
            RASFF data is loaded but no endpoint flattens it across every lane.
            Per-lane analysis works above; cohort × time slicing is the next
            obvious extension.
          </p>
        </section>
      )}
    </div>
  );
}
