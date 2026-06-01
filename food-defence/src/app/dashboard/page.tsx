"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  AlertTriangle,
  ArrowRight,
  Boxes,
  Globe,
  Network,
  Search,
  Sparkles,
} from "lucide-react";
import { api } from "@/lib/api";
import type {
  CorridorMetric,
  HazardBucket,
  OriginRisk,
  RasffSummary,
} from "@/lib/types";
import { fmt, fmtInt, riskColor, truncate } from "@/lib/utils";
import MetricCard from "@/components/shared/MetricCard";
import DataTable, { type Column } from "@/components/shared/DataTable";
import { whyLine } from "@/lib/whyLine";
import { actionFor } from "@/lib/actionHint";

const ACTION_CHIP_TONE = {
  high: "border-red-200 bg-red-50 text-red-700",
  med: "border-orange-200 bg-orange-50 text-orange-700",
  low: "border-slate-200 bg-slate-50 text-slate-600",
} as const;

const PROVENANCE_TICK = "FAOSTAT supply data used — full balance-sheet calculation.";
const PROVENANCE_TRADE = "Trade-only estimate — domestic production not yet ingested.";

const HAZARD_FAMILY_LABEL: Record<HazardBucket, string> = {
  biological: "Microbial",
  chem_pesticides: "Pesticide",
  chem_heavy_metals: "Heavy metals",
  chem_mycotoxins: "Mycotoxins",
  chem_other: "Other chemical",
  regulatory: "Labelling / regulatory",
};

const PRIORITY_COLS: Column<CorridorMetric>[] = [
  {
    key: "lane",
    label: "Lane",
    headerDescription: "Origin (exporter) → Destination (importer).",
    type: "string",
    render: (r) => (
      <div className="leading-tight">
        <p className="text-sm font-semibold text-slate-900">
          {r.origin_country} <span className="text-slate-400">→</span>{" "}
          {r.destination_country}
        </p>
        <p className="text-[10px] text-slate-400">
          {r.is_active_destination ? "Active destination" : "Passive mention"}
        </p>
      </div>
    ),
  },
  {
    key: "commodity_name",
    label: "Commodity",
    headerDescription: "Product category at this HS prefix.",
    type: "string",
    render: (r) => (
      <span className="text-xs text-slate-700">
        <span className="mr-1 inline-block rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[10px] text-slate-500">
          {r.commodity_hs}
        </span>
        {truncate(r.commodity_name, 22)}
      </span>
    ),
  },
  {
    key: "why",
    label: "Why this lane",
    headerDescription:
      "Plain-language synthesis of the hazard and supply signals on this lane.",
    type: "string",
    sortable: false,
    render: (r) => (
      <p className="max-w-md text-xs leading-snug text-slate-700">{whyLine(r)}</p>
    ),
  },
  {
    key: "cvs",
    label: "Priority score",
    headerDescription:
      "Combined priority (CVS), 0–1. Blends supply criticality, hazard intensity, and demand pressure. Higher = act sooner.",
    type: "number",
    render: (r) => {
      const tickProv =
        r.cvs == null
          ? null
          : r.provenance === "faostat"
            ? PROVENANCE_TICK
            : PROVENANCE_TRADE;
      return (
        <div className="text-right">
          <span
            className={`font-mono text-sm font-semibold ${riskColor(r.cvs ?? 0, 0.75)}`}
            title={tickProv ?? "Hazard-only fallback — structural inputs missing"}
          >
            {r.cvs != null ? fmt(r.cvs) : "—"}
          </span>
          {r.cvs != null && r.provenance !== "faostat" && (
            <p className="text-[9px] text-slate-400">trade-only</p>
          )}
        </div>
      );
    },
  },
  {
    key: "action",
    label: "Suggested action",
    headerDescription:
      "Heuristic hint based on score band, dominant hazard family, and supplier concentration. A planner's prompt — not a directive.",
    type: "string",
    sortable: false,
    render: (r) => {
      const a = actionFor(r);
      return (
        <span
          className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium ${ACTION_CHIP_TONE[a.tone]}`}
          title={a.reason}
        >
          {a.label}
        </span>
      );
    },
  },
];

function aggregateHazardFamilies(rows: CorridorMetric[]): {
  key: HazardBucket;
  label: string;
  count: number;
}[] {
  const tally = new Map<HazardBucket, number>();
  for (const r of rows) {
    const b = r.hazard_breakdown;
    if (!b) continue;
    (Object.entries(b) as [HazardBucket, number | undefined][]).forEach(
      ([k, v]) => {
        if ((v ?? 0) > 0) tally.set(k, (tally.get(k) ?? 0) + (v ?? 0));
      }
    );
  }
  return [...tally.entries()]
    .map(([k, v]) => ({ key: k, label: HAZARD_FAMILY_LABEL[k], count: v }))
    .sort((a, b) => b.count - a.count);
}

export default function Today() {
  const router = useRouter();
  const [summary, setSummary] = useState<RasffSummary | null>(null);
  const [allCorridors, setAllCorridors] = useState<CorridorMetric[]>([]);
  const [topOrigins, setTopOrigins] = useState<OriginRisk[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const [summ, all, origins] = await Promise.all([
          api.hazards.summary(),
          api.corridors.list("limit=1000"),
          api.network.origins(10),
        ]);
        setSummary(summ);
        setAllCorridors(all.corridors);
        setTopOrigins(origins.origins);
      } catch (e) {
        setError(e instanceof Error ? e.message : "API connection failed");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const cvsAvailable = useMemo(
    () => allCorridors.some((c) => c.cvs != null),
    [allCorridors]
  );

  const priorityRows = useMemo(() => {
    const sorted = [...allCorridors].sort((a, b) => {
      const av = (cvsAvailable ? a.cvs : a.his) ?? 0;
      const bv = (cvsAvailable ? b.cvs : b.his) ?? 0;
      return bv - av;
    });
    return sorted.slice(0, 25);
  }, [allCorridors, cvsAvailable]);

  const hazardFamilies = useMemo(
    () => aggregateHazardFamilies(allCorridors).slice(0, 5),
    [allCorridors]
  );

  const totalFamilyCount =
    hazardFamilies.reduce((s, x) => s + x.count, 0) || 1;

  const depCorridors = allCorridors.filter((c) => c.sci != null);
  const concentrated = depCorridors.filter((c) => (c.hhi ?? 0) >= 0.25).length;
  const noFallback = depCorridors.filter(
    (c) => c.idr_gt_1 || (c.ssr != null && (c.ssr ?? 1) < 0.1)
  ).length;
  const highPriority = allCorridors.filter((c) => (c.cvs ?? 0) >= 0.5).length;
  const topSci = [...depCorridors]
    .sort((a, b) => (b.sci ?? 0) - (a.sci ?? 0))
    .slice(0, 5);

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <div className="h-9 w-9 animate-spin rounded-full border-2 border-slate-200 border-t-blue-600" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-2xl border border-red-200/90 bg-red-50/90 p-6 shadow-sm backdrop-blur">
        <AlertTriangle className="mb-2 text-red-500" size={24} aria-hidden />
        <p className="font-medium text-red-900">API connection error</p>
        <p className="mt-1 text-sm text-red-700">{error}</p>
        <p className="mt-4 rounded-lg bg-white/60 px-3 py-2 text-xs text-red-600">
          Start the backend:{" "}
          <code className="rounded bg-red-100/80 px-1.5 py-0.5 font-mono text-[11px] text-red-800">
            cd backend && uvicorn defensefood.api.main:app --port 8000
          </code>
        </p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-1 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wider text-blue-600/90">
            Inspection planner
          </p>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">
            Today
          </h1>
          <p className="mt-1 max-w-xl text-sm text-slate-600">
            The lanes that should get your sampling and inspection capacity this
            period. Each row carries a plain-language reason and a suggested
            next step — confirm with your own controls before acting.
          </p>
        </div>
        <div className="text-right text-[11px] text-slate-500">
          <p>
            <span className="font-mono font-semibold text-slate-700">
              {allCorridors.length}
            </span>{" "}
            corridors loaded
          </p>
          <p>
            <span className="font-mono font-semibold text-slate-700">
              {fmtInt(summary?.total_notifications ?? 0)}
            </span>{" "}
            RASFF alerts in window
          </p>
        </div>
      </div>

      {!cvsAvailable && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-800">
          <span className="font-semibold">Hazard-only ranking.</span> The
          combined priority score (CVS) blends supply criticality (SCI) and
          consumption rank (CRS) with hazard intensity (HIS). Until bilateral
          trade and consumption data are loaded for every lane, the queue is
          sorted by hazard intensity alone.
        </div>
      )}

      {/* KPI tiles — three numbers a planner cares about. */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <MetricCard
          label={cvsAvailable ? "Lanes above review threshold" : "High-hazard lanes (HIS ≥ 0.5)"}
          value={cvsAvailable ? highPriority : allCorridors.filter((c) => c.his >= 0.5).length}
          icon={AlertTriangle}
          color="bg-red-500"
          subtext={
            cvsAvailable
              ? "Priority score ≥ 0.5 — these should get a closer look this period."
              : "Alert pattern strong enough to warrant follow-up regardless of supply context."
          }
        />
        <MetricCard
          label="Single-source lanes"
          value={concentrated}
          icon={Network}
          color="bg-orange-500"
          subtext={`Supplier concentration ≥ 0.25 — limited fallback if one supplier fails. Out of ${depCorridors.length} with a dependency profile.`}
        />
        <MetricCard
          label="No domestic cushion"
          value={noFallback}
          icon={Boxes}
          color="bg-amber-500"
          subtext="Imports exceed apparent supply, or local production is essentially zero. Disruption-sensitive."
        />
      </div>

      {/* Priority queue (hero). */}
      <section className="rounded-2xl border border-slate-200/90 bg-white p-5 shadow-sm">
        <div className="mb-3 flex items-baseline justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold text-slate-900">
              Top priority lanes this period
            </h2>
            <p className="mt-0.5 text-xs text-slate-500">
              Ranked by{" "}
              {cvsAvailable ? "combined priority score (CVS)" : "hazard intensity (HIS)"}{" "}
              · top {priorityRows.length} of {allCorridors.length} · click a row
              for the full forensic report.
            </p>
          </div>
          <Link
            href="/dashboard/corridors"
            className="inline-flex items-center gap-1 text-xs font-medium text-blue-600 hover:text-blue-800"
          >
            See all corridors <ArrowRight size={12} aria-hidden />
          </Link>
        </div>
        <DataTable
          columns={PRIORITY_COLS}
          data={priorityRows}
          onRowClick={(c) =>
            router.push(
              `/dashboard/corridors/${c.commodity_hs}/${c.destination_m49}/${c.origin_m49}`
            )
          }
          pageSize={10}
        />
      </section>

      {/* Two-column summary: structural exposure + hazard activity. */}
      <section className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        {/* Structural exposure */}
        <div className="rounded-2xl border border-slate-200/90 bg-white p-5 shadow-sm">
          <div className="mb-1 flex items-center gap-2">
            <Boxes size={15} className="text-blue-600" aria-hidden />
            <h2 className="text-sm font-semibold text-slate-900">
              Structural exposure
            </h2>
          </div>
          <p className="mb-4 text-[11px] text-slate-500">
            How exposed supply would be if a lane were disrupted — independent
            of whether RASFF has flagged anything.
          </p>

          {topSci.length === 0 ? (
            <p className="rounded-lg border border-dashed border-slate-200 bg-slate-50 px-3 py-3 text-xs text-slate-500">
              Dependency metrics need bilateral trade data. Run the all-partners
              Comtrade fetch and restart the API to populate this section.
            </p>
          ) : (
            <>
              <ul className="divide-y divide-slate-100 text-sm">
                {topSci.map((c) => (
                  <li key={`${c.commodity_hs}-${c.destination_m49}-${c.origin_m49}`}>
                    <button
                      type="button"
                      onClick={() =>
                        router.push(
                          `/dashboard/corridors/${c.commodity_hs}/${c.destination_m49}/${c.origin_m49}`
                        )
                      }
                      className="grid w-full grid-cols-[1fr_auto] items-baseline gap-3 py-2 text-left hover:bg-slate-50"
                    >
                      <div className="min-w-0">
                        <p className="truncate text-xs font-medium text-slate-800">
                          {c.origin_country} → {c.destination_country}
                        </p>
                        <p className="truncate text-[10px] text-slate-500">
                          {truncate(c.commodity_name, 36)}
                        </p>
                      </div>
                      <div className="text-right">
                        <p className={`font-mono text-sm font-semibold ${riskColor(c.sci ?? 0, 1.5)}`}>
                          {fmt(c.sci ?? 0)}
                        </p>
                        <p className="text-[9px] uppercase tracking-wide text-slate-400">
                          criticality
                        </p>
                      </div>
                    </button>
                  </li>
                ))}
              </ul>
              <Link
                href="/dashboard/corridors?sort_by=sci"
                className="mt-3 inline-flex items-center gap-1 text-xs font-medium text-blue-600 hover:text-blue-800"
              >
                Sort all corridors by criticality <ArrowRight size={12} aria-hidden />
              </Link>
            </>
          )}
        </div>

        {/* Hazard activity */}
        <div className="rounded-2xl border border-slate-200/90 bg-white p-5 shadow-sm">
          <div className="mb-1 flex items-center gap-2">
            <AlertTriangle size={15} className="text-red-500" aria-hidden />
            <h2 className="text-sm font-semibold text-slate-900">
              Hazard activity
            </h2>
          </div>
          <p className="mb-4 text-[11px] text-slate-500">
            What official RASFF notifications are saying right now.
          </p>

          {hazardFamilies.length === 0 ? (
            <p className="text-xs text-slate-500">No categorised RASFF data in window.</p>
          ) : (
            <>
              <p className="mb-2 text-[11px] font-medium text-slate-600">
                Hazard families across {fmtInt(summary?.total_notifications ?? 0)} alerts
              </p>
              <ul className="mb-4 space-y-1.5">
                {hazardFamilies.map((f) => {
                  const pct = (f.count / totalFamilyCount) * 100;
                  return (
                    <li key={f.key}>
                      <div className="flex items-center justify-between gap-3 text-xs">
                        <span className="text-slate-700">{f.label}</span>
                        <span className="font-mono text-[11px] text-slate-500">
                          {fmt(f.count, 0)} ({pct.toFixed(0)}%)
                        </span>
                      </div>
                      <div className="mt-0.5 h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
                        <div
                          className="h-full bg-red-400"
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    </li>
                  );
                })}
              </ul>

              {topOrigins.length > 0 && (
                <>
                  <p className="mb-2 text-[11px] font-medium text-slate-600">
                    Top exporters by outbound hazard signal
                  </p>
                  <ul className="grid gap-1.5 sm:grid-cols-2">
                    {topOrigins.slice(0, 6).map((o) => (
                      <li key={o.origin_m49}>
                        <button
                          type="button"
                          onClick={() =>
                            router.push(`/dashboard/countries/${o.origin_m49}`)
                          }
                          className="flex w-full items-center justify-between gap-2 rounded-md border border-slate-100 bg-slate-50/80 px-2 py-1.5 text-left text-xs transition hover:border-slate-200 hover:bg-slate-50"
                        >
                          <span className="truncate text-slate-800">
                            {o.name || o.origin_m49}
                          </span>
                          <span className="font-mono text-[11px] text-slate-500">
                            {fmt(o.total_his, 2)}
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </>
          )}
        </div>
      </section>

      {/* Deeper exploration links */}
      <section className="rounded-2xl border border-slate-200/70 bg-slate-50/50 px-5 py-4">
        <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
          Look deeper
        </p>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
          <Link
            href="/dashboard/corridors"
            className="flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs text-slate-700 hover:border-blue-300 hover:bg-blue-50"
          >
            <Search size={14} className="text-blue-600" aria-hidden />
            <span>
              <span className="block font-medium text-slate-900">
                Investigate corridors
              </span>
              <span className="text-[10px] text-slate-500">
                Filter every lane, export to CSV
              </span>
            </span>
          </Link>
          <Link
            href="/dashboard/patterns"
            className="flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs text-slate-700 hover:border-blue-300 hover:bg-blue-50"
          >
            <Sparkles size={14} className="text-blue-600" aria-hidden />
            <span>
              <span className="block font-medium text-slate-900">Patterns</span>
              <span className="text-[10px] text-slate-500">
                Heatmap and scoring weights
              </span>
            </span>
          </Link>
          <Link
            href="/dashboard/network"
            className="flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs text-slate-700 hover:border-blue-300 hover:bg-blue-50"
          >
            <Globe size={14} className="text-blue-600" aria-hidden />
            <span>
              <span className="block font-medium text-slate-900">
                Trade network
              </span>
              <span className="text-[10px] text-slate-500">
                Country graph
              </span>
            </span>
          </Link>
        </div>
      </section>
    </div>
  );
}
