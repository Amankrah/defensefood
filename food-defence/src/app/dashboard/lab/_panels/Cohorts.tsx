"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { CohortResponse } from "@/lib/types";
import { fmt, fmtInt } from "@/lib/utils";

const GROUP_BY_OPTIONS: { key: string; label: string }[] = [
  { key: "hs_chapter", label: "HS chapter" },
  { key: "origin_eu", label: "Origin EU/non-EU" },
  { key: "dest_eu", label: "Destination EU/non-EU" },
  { key: "origin_country", label: "Origin country" },
  { key: "destination_country", label: "Destination country" },
  { key: "provenance", label: "Provenance" },
];

const METRIC_OPTIONS: { key: string; label: string }[] = [
  { key: "his", label: "Hazard intensity (HIS)" },
  { key: "sci", label: "Supply criticality (SCI)" },
  { key: "idr", label: "Import reliance (IDR)" },
  { key: "ocs", label: "Origin share (OCS)" },
  { key: "hhi", label: "Supplier concentration (HHI)" },
  { key: "bdi", label: "Bilateral dependency (BDI)" },
  { key: "ssr", label: "Self-sufficiency (SSR)" },
  { key: "cvs", label: "Priority score (CVS)" },
  { key: "hdi", label: "Hazard diversity (HDI)" },
  { key: "notification_count", label: "Alert count" },
  { key: "severity_total", label: "Alert weight" },
];

const AGG_OPTIONS: { key: string; label: string }[] = [
  { key: "mean", label: "mean" },
  { key: "median", label: "median" },
  { key: "max", label: "max" },
  { key: "min", label: "min" },
  { key: "sum", label: "sum" },
  { key: "count", label: "count (non-null rows)" },
];

export default function Cohorts() {
  const [groupBy, setGroupBy] = useState<string[]>(["hs_chapter"]);
  const [metric, setMetric] = useState("his");
  const [agg, setAgg] = useState("mean");
  const [data, setData] = useState<CohortResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (groupBy.length === 0) {
      setData(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    api.research
      .cohorts(groupBy, metric, agg)
      .then((r) => {
        if (!cancelled) setData(r);
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
  }, [groupBy, metric, agg]);

  function toggleGroup(key: string) {
    setGroupBy((prev) =>
      prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]
    );
  }

  const maxValue = data?.rows.length ? Math.max(...data.rows.map((r) => Math.abs(r.value))) : 0;

  return (
    <div className="space-y-4">
      <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <h2 className="text-sm font-semibold text-slate-900">Group-by builder</h2>
        <p className="mt-0.5 text-[11px] text-slate-500">
          Pick one or more grouping keys, a metric, and an aggregation.
          Null values are skipped from the aggregation (except in count mode).
        </p>

        <div className="mt-3">
          <p className="mb-1 text-[11px] font-medium text-slate-600">Group by</p>
          <div className="flex flex-wrap gap-1.5">
            {GROUP_BY_OPTIONS.map((g) => {
              const active = groupBy.includes(g.key);
              return (
                <button
                  key={g.key}
                  type="button"
                  onClick={() => toggleGroup(g.key)}
                  className={`rounded-full border px-2.5 py-1 text-[11px] font-medium transition ${
                    active
                      ? "border-blue-300 bg-blue-50 text-blue-700"
                      : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50"
                  }`}
                >
                  {g.label}
                </button>
              );
            })}
          </div>
        </div>

        <div className="mt-3 flex flex-wrap items-end gap-3">
          <div>
            <label className="block text-[11px] font-medium text-slate-500">Metric</label>
            <select
              value={metric}
              onChange={(e) => setMetric(e.target.value)}
              className="mt-1 rounded-lg border border-slate-200 px-2 py-1.5 text-sm"
            >
              {METRIC_OPTIONS.map((m) => (
                <option key={m.key} value={m.key}>
                  {m.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-[11px] font-medium text-slate-500">Aggregation</label>
            <select
              value={agg}
              onChange={(e) => setAgg(e.target.value)}
              className="mt-1 rounded-lg border border-slate-200 px-2 py-1.5 text-sm"
            >
              {AGG_OPTIONS.map((a) => (
                <option key={a.key} value={a.key}>
                  {a.label}
                </option>
              ))}
            </select>
          </div>
        </div>
      </section>

      <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="mb-1 flex items-baseline justify-between gap-2">
          <h2 className="text-sm font-semibold text-slate-900">Result</h2>
          {loading && <span className="text-[10px] text-slate-500 animate-pulse">Loading…</span>}
        </div>
        {error && (
          <p className="rounded-md border border-red-200 bg-red-50 px-3 py-1.5 text-xs text-red-700">
            {error}
          </p>
        )}

        {groupBy.length === 0 ? (
          <p className="rounded-md border border-dashed border-slate-200 bg-slate-50 px-3 py-3 text-xs text-slate-500">
            Pick at least one grouping key.
          </p>
        ) : !data || data.rows.length === 0 ? (
          <p className="text-xs text-slate-500">No rows match.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-slate-200 text-left text-[10px] uppercase tracking-wide text-slate-500">
                  {groupBy.map((g) => (
                    <th key={g} className="py-1.5 pr-3">
                      {GROUP_BY_OPTIONS.find((o) => o.key === g)?.label ?? g}
                    </th>
                  ))}
                  <th className="py-1.5 pr-3 text-right">Count</th>
                  <th className="py-1.5 pr-3 text-right">
                    {agg} {metric}
                  </th>
                  <th className="py-1.5 pr-3">Magnitude</th>
                </tr>
              </thead>
              <tbody>
                {data.rows.map((r, idx) => {
                  const ratio = maxValue > 0 ? Math.abs(r.value) / maxValue : 0;
                  return (
                    <tr key={idx} className="border-b border-slate-100">
                      {groupBy.map((g) => (
                        <td key={g} className="py-1.5 pr-3 font-medium text-slate-800">
                          {r.group[g] ?? "—"}
                        </td>
                      ))}
                      <td className="py-1.5 pr-3 text-right font-mono text-slate-600">
                        {fmtInt(r.count)}
                      </td>
                      <td className="py-1.5 pr-3 text-right font-mono font-semibold text-slate-900">
                        {fmt(r.value, agg === "count" ? 0 : 3)}
                      </td>
                      <td className="py-1.5 pr-3">
                        <div className="h-2 w-32 overflow-hidden rounded-full bg-slate-100">
                          <div
                            className="h-full bg-blue-500"
                            style={{ width: `${ratio * 100}%` }}
                          />
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
