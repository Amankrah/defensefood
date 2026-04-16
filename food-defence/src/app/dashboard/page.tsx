"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  AlertTriangle,
  Network,
  Shield,
  TrendingUp,
} from "lucide-react";
import { api } from "@/lib/api";
import type {
  CorridorMetric,
  OriginRisk,
  RasffSummary,
  ScoringConfig,
} from "@/lib/types";
import { riskColor, fmt, truncate } from "@/lib/utils";
import MetricCard from "@/components/shared/MetricCard";
import DataTable, { type Column } from "@/components/shared/DataTable";
import HeatmapGrid from "@/components/shared/HeatmapGrid";
import ScoreConfigPanel from "@/components/shared/ScoreConfigPanel";

const CORRIDOR_COLS: Column<CorridorMetric>[] = [
  {
    key: "origin_country",
    label: "Origin",
    headerDescription: "Exporting country for this commodity lane.",
    type: "string",
    render: (r) => (
      <span className="font-medium text-slate-900">{r.origin_country}</span>
    ),
  },
  {
    key: "destination_country",
    label: "Destination",
    headerDescription: "Importing country (often EU member state receiving goods).",
    type: "string",
  },
  {
    key: "commodity_name",
    label: "Commodity",
    headerDescription: "Product category (HS code prefix shown).",
    type: "string",
    render: (r) => (
      <span title={r.commodity_name}>
        <span className="mr-1 text-[10px] text-slate-400">{r.commodity_hs}</span>
        {truncate(r.commodity_name, 25)}
      </span>
    ),
  },
  {
    key: "his",
    label: "Hazard",
    headerDescription:
      "Hazard intensity (HIS): relative strength of RASFF-linked signals on this lane. Higher means more alert-driven concern, not proof of incident.",
    type: "number",
    render: (r) => (
      <span className={`font-mono font-semibold ${riskColor(r.his, 0.5)}`}>
        {fmt(r.his)}
      </span>
    ),
  },
  {
    key: "cvs",
    label: "Priority",
    headerDescription:
      "Combined vulnerability score (CVS), 0 to 1: blends hazard, trade, and structural factors. Higher means review this corridor sooner.",
    type: "number",
    render: (r) => (
      <span className={`font-mono ${riskColor(r.cvs ?? 0, 0.5)}`}>
        {r.cvs != null ? fmt(r.cvs) : "-"}
      </span>
    ),
  },
  {
    key: "notification_count",
    label: "Alerts",
    headerDescription: "Count of RASFF notifications associated with this corridor in the loaded window.",
    type: "number",
    render: (r) => (
      <span className="font-mono text-slate-600">{r.notification_count}</span>
    ),
  },
  {
    key: "severity_total",
    label: "Alert weight",
    headerDescription:
      "Sum of seriousness weights from notifications (classification and risk level). Higher means graver historical alerts, not current compliance.",
    type: "number",
    render: (r) => (
      <span className="font-mono text-slate-600">{fmt(r.severity_total, 2)}</span>
    ),
  },
];

export default function CommandCentre() {
  const router = useRouter();
  const [summary, setSummary] = useState<RasffSummary | null>(null);
  const [corridors, setCorridors] = useState<CorridorMetric[]>([]);
  const [allCorridors, setAllCorridors] = useState<CorridorMetric[]>([]);
  const [networkStats, setNetworkStats] = useState({ node_count: 0, edge_count: 0 });
  const [scoringConfig, setScoringConfig] = useState<ScoringConfig | null>(null);
  const [scoring, setScoring] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [topOrigins, setTopOrigins] = useState<OriginRisk[]>([]);

  useEffect(() => {
    async function load() {
      try {
        const [summ, top, net, cfg, all, origins] = await Promise.all([
          api.hazards.summary(),
          api.corridors.top(20, "his"),
          api.network.summary(),
          api.scoring.config(),
          api.corridors.list("limit=1000"),
          api.network.origins(12),
        ]);
        setSummary(summ);
        setCorridors(top.corridors);
        setNetworkStats(net);
        setScoringConfig(cfg);
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

  async function handleRecalculate(config: ScoringConfig) {
    setScoring(true);
    try {
      const result = await api.scoring.recalculate(config);
      setScoringConfig(config);
      const top = result.corridors.slice(0, 20);
      setCorridors(top);
      setAllCorridors(result.corridors);
      const origins = await api.network.origins(12);
      setTopOrigins(origins.origins);
    } finally {
      setScoring(false);
    }
  }

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
            cd backend && PYTHONPATH=. uvicorn defensefood.api.main:app --port 8000
          </code>
        </p>
      </div>
    );
  }

  const flagged = allCorridors.filter((c) => (c.cvs ?? 0) > 0.3).length;
  const maxCvs = allCorridors.reduce(
    (max, c) => Math.max(max, c.cvs ?? 0),
    0
  );
  const density =
    networkStats.node_count > 0
      ? networkStats.edge_count / (networkStats.node_count * networkStats.node_count)
      : 0;

  return (
    <div className="mx-auto max-w-7xl space-y-8">
      <div className="flex flex-col gap-1 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wider text-blue-600/90">
            Decision overview
          </p>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">Dashboard</h1>
          <p className="mt-1 max-w-xl text-sm text-slate-600">
            You are viewing{" "}
            <span className="font-mono font-semibold text-slate-800">{allCorridors.length}</span>{" "}
            commodity trade corridors. Use the heatmap for patterns, adjust scoring if your risk
            policy shifts, then open a row for full diagnostics.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <MetricCard
          label="Corridors above review threshold"
          value={flagged}
          icon={AlertTriangle}
          color="bg-red-500"
          subtext={`Priority score (CVS) above 0.3, out of ${allCorridors.length} loaded`}
        />
        <MetricCard
          label="Highest priority score in data"
          value={fmt(maxCvs)}
          icon={Shield}
          color="bg-orange-500"
          subtext="Top combined vulnerability (CVS) across all corridors"
        />
        <MetricCard
          label="RASFF alerts in dataset"
          value={summary?.total_notifications ?? 0}
          icon={TrendingUp}
          color="bg-blue-500"
          subtext={`${summary?.notification_objects_built ?? 0} records shaped into corridor objects`}
        />
        <MetricCard
          label="Network connectivity"
          value={fmt(density, 4)}
          icon={Network}
          color="bg-purple-500"
          subtext={`Share of possible country links that exist: ${networkStats.edge_count} active ties among ${networkStats.node_count} countries (higher = busier map)`}
        />
      </div>

      {topOrigins.length > 0 && (
        <div className="rounded-2xl border border-slate-200/90 bg-white p-5 shadow-sm">
          <h2 className="mb-1 text-sm font-semibold text-slate-900">
            Exporting countries with the strongest outbound hazard signals
          </h2>
          <p className="mb-3 text-xs text-slate-600">
            Total hazard intensity (HIS) summed over corridors where each country is the origin.
            Open a country to see ORPS by commodity (framework Sec. 6.2).
          </p>
          <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {topOrigins.map((o) => (
              <li key={o.origin_m49}>
                <button
                  type="button"
                  onClick={() => router.push(`/dashboard/countries/${o.origin_m49}`)}
                  className="flex w-full items-center justify-between rounded-lg border border-slate-100 bg-slate-50/80 px-3 py-2 text-left text-sm transition hover:border-slate-200 hover:bg-slate-50"
                >
                  <span className="font-medium text-slate-900">{o.name || o.origin_m49}</span>
                  <span className="font-mono text-xs text-slate-600">{fmt(o.total_his, 3)}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3 lg:gap-8">
        <div className="rounded-2xl border border-slate-200/90 bg-white p-5 shadow-sm lg:col-span-2">
          <h2 className="mb-1 text-sm font-semibold text-slate-900">
            Where hazard signals concentrate
          </h2>
          <p className="mb-4 text-xs text-slate-500">
            Each cell is an origin country and HS chapter pair. Darker means stronger hazard
            intensity (HIS) in the data. Hover a cell for the exact value.
          </p>
          <HeatmapGrid corridors={allCorridors} maxRows={12} maxCols={10} />
        </div>

        <div className="min-w-0">
          {scoringConfig && (
            <ScoreConfigPanel
              config={scoringConfig}
              onRecalculate={handleRecalculate}
              loading={scoring}
            />
          )}
        </div>
      </div>

      <div className="rounded-2xl border border-slate-200/90 bg-white p-5 shadow-sm">
        <h2 className="mb-1 text-sm font-semibold text-slate-900">
          Corridors with strongest hazard signals
        </h2>
        <p className="mb-4 text-xs text-slate-500">
          Sorted by hazard intensity (HIS). Column headers have short explanations on hover. Click a
          row for trade, dependency, and priority breakdown.
        </p>
        <DataTable
          columns={CORRIDOR_COLS}
          data={corridors}
          onRowClick={(c) =>
            router.push(
              `/dashboard/corridors/${c.commodity_hs}/${c.destination_m49}/${c.origin_m49}`
            )
          }
          pageSize={20}
        />
      </div>
    </div>
  );
}
