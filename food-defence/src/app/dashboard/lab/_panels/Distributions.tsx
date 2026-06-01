"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { DistributionResponse } from "@/lib/types";
import { fmt, fmtInt } from "@/lib/utils";
import Histogram from "@/components/shared/Histogram";

const METRICS: { key: string; label: string; abbr: string; precision: number }[] = [
  { key: "sci", label: "Supply criticality", abbr: "SCI", precision: 2 },
  { key: "idr", label: "Import reliance", abbr: "IDR", precision: 2 },
  { key: "ocs", label: "Origin share", abbr: "OCS", precision: 2 },
  { key: "hhi", label: "Supplier concentration", abbr: "HHI", precision: 2 },
  { key: "bdi", label: "Bilateral dependency", abbr: "BDI", precision: 2 },
  { key: "ssr", label: "Self-sufficiency", abbr: "SSR", precision: 2 },
  { key: "his", label: "Hazard intensity", abbr: "HIS", precision: 2 },
  { key: "hdi", label: "Hazard diversity", abbr: "HDI", precision: 2 },
  { key: "cvs", label: "Priority score", abbr: "CVS", precision: 2 },
  { key: "notification_count", label: "Alert count", abbr: "n", precision: 0 },
];

type Filter = {
  provenance: "" | "faostat" | "trade_only";
  origin_eu: "" | "true" | "false";
  dest_eu: "" | "true" | "false";
  bins: number;
};

const DEFAULT_FILTER: Filter = {
  provenance: "",
  origin_eu: "",
  dest_eu: "",
  bins: 20,
};

export default function Distributions() {
  const [metricKey, setMetricKey] = useState("sci");
  const [filter, setFilter] = useState<Filter>(DEFAULT_FILTER);
  const [data, setData] = useState<DistributionResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const metric = METRICS.find((m) => m.key === metricKey)!;

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    api.research
      .distribution(metricKey, {
        bins: filter.bins,
        provenance: filter.provenance || undefined,
        originEu:
          filter.origin_eu === "true"
            ? true
            : filter.origin_eu === "false"
              ? false
              : undefined,
        destEu:
          filter.dest_eu === "true"
            ? true
            : filter.dest_eu === "false"
              ? false
              : undefined,
      })
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
  }, [metricKey, filter]);

  const stats = data?.stats;
  const markers =
    stats && stats.count > 0
      ? [
          { value: stats.p25 ?? 0, label: "P25", color: "#94a3b8" },
          { value: stats.median ?? 0, label: "P50", color: "#3b82f6" },
          { value: stats.p75 ?? 0, label: "P75", color: "#94a3b8" },
          { value: stats.p90 ?? 0, label: "P90", color: "#f97316" },
        ]
      : [];

  return (
    <div className="space-y-4">
      <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div className="flex flex-wrap items-end gap-3">
            <div>
              <label className="block text-[11px] font-medium text-slate-500">Metric</label>
              <select
                value={metricKey}
                onChange={(e) => setMetricKey(e.target.value)}
                className="mt-1 rounded-lg border border-slate-200 px-2 py-1.5 text-sm"
              >
                {METRICS.map((m) => (
                  <option key={m.key} value={m.key}>
                    {m.label} ({m.abbr})
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-[11px] font-medium text-slate-500">Bins</label>
              <input
                type="number"
                min={2}
                max={100}
                value={filter.bins}
                onChange={(e) =>
                  setFilter((f) => ({
                    ...f,
                    bins: Math.max(2, Math.min(100, parseInt(e.target.value, 10) || 20)),
                  }))
                }
                className="mt-1 w-20 rounded-lg border border-slate-200 px-2 py-1.5 text-sm"
              />
            </div>
            <div>
              <label className="block text-[11px] font-medium text-slate-500">Provenance</label>
              <select
                value={filter.provenance}
                onChange={(e) =>
                  setFilter((f) => ({ ...f, provenance: e.target.value as Filter["provenance"] }))
                }
                className="mt-1 rounded-lg border border-slate-200 px-2 py-1.5 text-sm"
              >
                <option value="">Any</option>
                <option value="faostat">FAOSTAT only</option>
                <option value="trade_only">Trade-only</option>
              </select>
            </div>
            <div>
              <label className="block text-[11px] font-medium text-slate-500">Origin EU</label>
              <select
                value={filter.origin_eu}
                onChange={(e) =>
                  setFilter((f) => ({ ...f, origin_eu: e.target.value as Filter["origin_eu"] }))
                }
                className="mt-1 rounded-lg border border-slate-200 px-2 py-1.5 text-sm"
              >
                <option value="">Any</option>
                <option value="true">EU origin</option>
                <option value="false">Non-EU origin</option>
              </select>
            </div>
            <div>
              <label className="block text-[11px] font-medium text-slate-500">Destination EU</label>
              <select
                value={filter.dest_eu}
                onChange={(e) =>
                  setFilter((f) => ({ ...f, dest_eu: e.target.value as Filter["dest_eu"] }))
                }
                className="mt-1 rounded-lg border border-slate-200 px-2 py-1.5 text-sm"
              >
                <option value="">Any</option>
                <option value="true">EU destination</option>
                <option value="false">Non-EU destination</option>
              </select>
            </div>
          </div>
          <button
            type="button"
            onClick={() => setFilter(DEFAULT_FILTER)}
            className="rounded-md border border-slate-200 bg-white px-2 py-1 text-[11px] text-slate-700 hover:bg-slate-50"
          >
            Reset filters
          </button>
        </div>
      </section>

      <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="mb-1 flex items-baseline justify-between gap-2">
          <h2 className="text-sm font-semibold text-slate-900">
            {metric.label} <span className="text-xs font-normal text-slate-400">({metric.abbr})</span>
          </h2>
          {loading && (
            <span className="text-[10px] text-slate-500 animate-pulse">Loading…</span>
          )}
        </div>

        {error && (
          <p className="rounded-md border border-red-200 bg-red-50 px-3 py-1.5 text-xs text-red-700">
            {error}
          </p>
        )}

        {data && (
          <>
            <Histogram
              bins={data.bins}
              markers={markers}
              precision={metric.precision}
              height={260}
            />
            <div className="mt-3 grid grid-cols-2 gap-2 text-[11px] sm:grid-cols-4 lg:grid-cols-6">
              {[
                ["n", fmtInt(stats?.count ?? 0)],
                ["mean", fmt(stats?.mean ?? NaN, metric.precision)],
                ["median", fmt(stats?.median ?? NaN, metric.precision)],
                ["std", fmt(stats?.std ?? NaN, metric.precision)],
                ["min", fmt(stats?.min ?? NaN, metric.precision)],
                ["max", fmt(stats?.max ?? NaN, metric.precision)],
                ["p25", fmt(stats?.p25 ?? NaN, metric.precision)],
                ["p75", fmt(stats?.p75 ?? NaN, metric.precision)],
                ["p90", fmt(stats?.p90 ?? NaN, metric.precision)],
              ].map(([label, value]) => (
                <div
                  key={label}
                  className="rounded-md border border-slate-100 bg-slate-50/80 px-2 py-1.5"
                >
                  <p className="text-[10px] uppercase tracking-wide text-slate-500">{label}</p>
                  <p className="font-mono text-xs font-semibold text-slate-800">{value}</p>
                </div>
              ))}
            </div>
            <p className="mt-3 text-[10px] text-slate-500">
              Dashed markers: <span className="font-mono">P25/P50/P75</span> in slate/blue/slate,{" "}
              <span className="font-mono text-orange-600">P90</span> in orange — the long-tail
              boundary.
            </p>
          </>
        )}
      </section>
    </div>
  );
}
