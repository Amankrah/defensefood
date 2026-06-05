"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  AlertTriangle,
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
import PeriodShiftCard from "@/components/shared/PeriodShiftCard";
import PageHeader from "@/components/layout/PageHeader";
import SectionCard from "@/components/layout/SectionCard";
import QuickNavCard from "@/components/layout/QuickNavCard";
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

function StatChip({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg border border-slate-200/80 bg-white px-3 py-2 text-right shadow-sm">
      <p className="font-mono text-lg font-semibold text-slate-900">{value}</p>
      <p className="text-[10px] font-medium uppercase tracking-wide text-slate-500">
        {label}
      </p>
    </div>
  );
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
      <div className="df-card border-red-200/90 bg-red-50/50 p-6">
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
    <div className="space-y-8">
      <PageHeader
        eyebrow="Research diagnostic"
        title="Latest period overview"
        description="Corpus-wide view of lane priorities, period-over-period movement, and hazard rollups. Trade and FAOSTAT data lag 1–2 years — a research and forensic tool, not an operational planner."
        meta={
          <>
            <StatChip label="Corridors" value={allCorridors.length} />
            <StatChip
              label="RASFF alerts"
              value={fmtInt(summary?.total_notifications ?? 0)}
            />
          </>
        }
      />

      {/* KPI strip — scan first */}
      <section aria-label="Key indicators">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <MetricCard
            label={
              cvsAvailable
                ? "Lanes above review threshold"
                : "High-hazard lanes (HIS ≥ 0.5)"
            }
            value={
              cvsAvailable
                ? highPriority
                : allCorridors.filter((c) => c.his >= 0.5).length
            }
            icon={AlertTriangle}
            tone="danger"
            subtext={
              cvsAvailable
                ? "Priority score ≥ 0.5 — warrant closer inspection this period."
                : "Alert pattern strong enough to warrant follow-up regardless of supply context."
            }
          />
          <MetricCard
            label="Single-source lanes"
            value={concentrated}
            icon={Network}
            tone="warning"
            subtext={`Supplier concentration ≥ 0.25 — limited fallback. Out of ${depCorridors.length} with a dependency profile.`}
          />
          <MetricCard
            label="No domestic cushion"
            value={noFallback}
            icon={Boxes}
            tone="caution"
            subtext="Imports exceed apparent supply, or local production is near zero."
          />
        </div>
      </section>

      {/* AI period-shift narrative */}
      <PeriodShiftCard />

      {!cvsAvailable && (
        <div
          role="status"
          className="rounded-xl border border-amber-200/80 bg-amber-50/80 px-4 py-3 text-xs text-amber-900"
        >
          <span className="font-semibold">Hazard-only ranking.</span> Combined
          priority (CVS) blends supply criticality, consumption rank, and hazard
          intensity. Until bilateral trade data loads for every lane, the queue
          sorts by hazard intensity alone.
        </div>
      )}

      {/* Priority queue — primary action surface */}
      <SectionCard
        title="Top priority lanes"
        description={`Ranked by ${cvsAvailable ? "combined priority (CVS)" : "hazard intensity (HIS)"} · top ${priorityRows.length} of ${allCorridors.length} · click a row for the full forensic report.`}
        href="/dashboard/corridors"
        hrefLabel="All corridors"
        variant="featured"
      >
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
      </SectionCard>

      {/* Context panels */}
      <section className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <SectionCard
          title="Structural exposure"
          description="How exposed supply would be if a lane were disrupted — independent of RASFF flags."
          icon={Boxes}
          iconClassName="text-blue-600"
          href="/dashboard/corridors?sort_by=sci"
          hrefLabel="Sort by criticality"
        >
          {topSci.length === 0 ? (
            <p className="rounded-lg border border-dashed border-slate-200 bg-slate-50 px-3 py-4 text-xs text-slate-500">
              Dependency metrics need bilateral trade data. Run the all-partners
              Comtrade fetch and restart the API to populate this section.
            </p>
          ) : (
            <ul className="divide-y divide-slate-100">
              {topSci.map((c) => (
                <li key={`${c.commodity_hs}-${c.destination_m49}-${c.origin_m49}`}>
                  <button
                    type="button"
                    onClick={() =>
                      router.push(
                        `/dashboard/corridors/${c.commodity_hs}/${c.destination_m49}/${c.origin_m49}`
                      )
                    }
                    className="grid w-full grid-cols-[1fr_auto] items-baseline gap-3 rounded-lg py-2.5 text-left transition hover:bg-slate-50"
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
                      <p
                        className={`font-mono text-sm font-semibold ${riskColor(c.sci ?? 0, 1.5)}`}
                      >
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
          )}
        </SectionCard>

        <SectionCard
          title="Hazard activity"
          description="What official RASFF notifications are saying in the loaded window."
          icon={AlertTriangle}
          iconClassName="text-red-500"
        >
          {hazardFamilies.length === 0 ? (
            <p className="text-xs text-slate-500">
              No categorised RASFF data in window.
            </p>
          ) : (
            <>
              <p className="mb-3 text-[11px] font-medium text-slate-600">
                Hazard families across{" "}
                {fmtInt(summary?.total_notifications ?? 0)} alerts
              </p>
              <ul className="mb-5 space-y-2">
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
                      <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
                        <div
                          className="h-full rounded-full bg-gradient-to-r from-red-400 to-red-500"
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
                          className="flex w-full items-center justify-between gap-2 rounded-lg border border-slate-100 bg-slate-50/80 px-2.5 py-2 text-left text-xs transition hover:border-slate-200 hover:bg-white"
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
        </SectionCard>
      </section>

      {/* Exploration shortcuts */}
      <section>
        <p className="df-eyebrow mb-3">Explore further</p>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <QuickNavCard
            href="/dashboard/corridors"
            icon={Search}
            title="Investigate corridors"
            description="Filter every lane, export to CSV"
            accent="blue"
          />
          <QuickNavCard
            href="/dashboard/patterns"
            icon={Sparkles}
            title="Patterns"
            description="Heatmap and scoring weights"
            accent="violet"
          />
          <QuickNavCard
            href="/dashboard/network"
            icon={Globe}
            title="Trade network"
            description="Country exposure graph"
            accent="teal"
          />
        </div>
      </section>
    </div>
  );
}
