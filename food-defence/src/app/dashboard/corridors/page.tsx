"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { CorridorMetric, Country } from "@/lib/types";
import { riskColor, fmt, truncate } from "@/lib/utils";
import DataTable, { type Column } from "@/components/shared/DataTable";
import { RolePills } from "@/components/shared/RolePill";

const COLUMNS: Column<CorridorMetric>[] = [
  {
    key: "origin_country",
    label: "Origin",
    headerDescription: "Exporting country for this lane.",
    type: "string",
    render: (r) => <span className="font-medium">{r.origin_country}</span>,
  },
  {
    key: "destination_country",
    label: "Destination",
    headerDescription: "Importing country.",
    type: "string",
  },
  {
    key: "commodity_hs",
    label: "HS code",
    headerDescription: "Harmonised system product code.",
    type: "string",
    render: (r) => <span className="font-mono text-xs">{r.commodity_hs}</span>,
  },
  {
    key: "commodity_name",
    label: "Commodity",
    headerDescription: "Plain language product name.",
    type: "string",
    render: (r) => <span title={r.commodity_name}>{truncate(r.commodity_name, 30)}</span>,
  },
  {
    key: "his",
    label: "Hazard",
    headerDescription:
      "Hazard intensity (HIS): strength of RASFF-linked signals on this lane (higher = more concern).",
    type: "number",
    render: (r) => (
      <span className={`font-mono font-semibold ${riskColor(r.his, 0.5)}`}>
        {fmt(r.his)}
      </span>
    ),
  },
  {
    key: "hdi",
    label: "Diversity",
    headerDescription:
      "Hazard diversity (HDI): spread of hazard types; helps distinguish repeated vs varied issues.",
    type: "number",
  },
  {
    key: "notification_count",
    label: "Alerts",
    headerDescription: "RASFF notifications tied to this corridor in the loaded period.",
    type: "number",
    render: (r) => <span className="font-mono">{r.notification_count}</span>,
  },
  {
    key: "severity_total",
    label: "Alert weight",
    headerDescription: "Cumulative seriousness of those alerts (weighted).",
    type: "number",
    render: (r) => <span className="font-mono">{fmt(r.severity_total, 2)}</span>,
  },
  {
    key: "destination_roles",
    label: "Destination role",
    headerDescription:
      "RASFF role(s) that flagged the destination: notifier (detected), distribution (shipped), follow-up (must investigate), attention (passive).",
    type: "string",
    sortable: false,
    render: (r) => <RolePills roles={r.destination_roles} />,
  },
  {
    key: "cvs",
    label: "Priority",
    headerDescription:
      "Combined vulnerability score (CVS), 0 to 1: higher means review sooner.",
    type: "number",
    render: (r) => (
      <span className={`font-mono font-semibold ${riskColor(r.cvs ?? 0, 0.5)}`}>
        {r.cvs != null ? fmt(r.cvs) : "-"}
      </span>
    ),
  },
];

type CorridorFilters = {
  commodity: string;
  origin: string;
  destination: string;
  role: string;
  activeOnly: boolean;
  minHis: string;
  minNotifications: string;
  minHdi: string;
  minCvs: string;
  hasCvs: string;
  originEu: string;
  destEu: string;
};

const DEFAULT_FILTERS: CorridorFilters = {
  commodity: "",
  origin: "",
  destination: "",
  role: "",
  activeOnly: false,
  minHis: "",
  minNotifications: "",
  minHdi: "",
  minCvs: "",
  hasCvs: "",
  originEu: "",
  destEu: "",
};

const ROLE_OPTIONS: { value: string; label: string }[] = [
  { value: "", label: "Any destination role" },
  { value: "notifier", label: "Notifier" },
  { value: "distribution", label: "Distribution" },
  { value: "followUp", label: "Follow-up" },
  { value: "attention", label: "Attention" },
];

const EU_SCOPE_OPTIONS = [
  { value: "", label: "Any" },
  { value: "eu", label: "EU only" },
  { value: "non", label: "Non-EU only" },
];

function buildListQuery(f: CorridorFilters): string {
  const p = new URLSearchParams();
  p.set("limit", "1000");
  if (f.commodity.trim()) p.set("commodity", f.commodity.trim());
  if (f.origin) p.set("origin", f.origin);
  if (f.destination) p.set("destination", f.destination);
  if (f.role) p.set("role", f.role);
  if (f.activeOnly) p.set("active_only", "true");
  const his = parseFloat(f.minHis);
  if (f.minHis.trim() !== "" && !Number.isNaN(his)) p.set("min_his", String(his));
  const nmin = parseInt(f.minNotifications, 10);
  if (f.minNotifications.trim() !== "" && !Number.isNaN(nmin))
    p.set("min_notification_count", String(nmin));
  const hdi = parseFloat(f.minHdi);
  if (f.minHdi.trim() !== "" && !Number.isNaN(hdi)) p.set("min_hdi", String(hdi));
  const cvs = parseFloat(f.minCvs);
  if (f.minCvs.trim() !== "" && !Number.isNaN(cvs)) p.set("min_cvs", String(cvs));
  if (f.hasCvs === "yes") p.set("has_cvs", "true");
  if (f.hasCvs === "no") p.set("has_cvs", "false");
  if (f.originEu === "eu") p.set("origin_eu", "true");
  if (f.originEu === "non") p.set("origin_eu", "false");
  if (f.destEu === "eu") p.set("dest_eu", "true");
  if (f.destEu === "non") p.set("dest_eu", "false");
  return p.toString();
}

function corridorViewStats(rows: CorridorMetric[]) {
  if (!rows.length) return null;
  const n = rows.length;
  const sumAlerts = rows.reduce((s, r) => s + r.notification_count, 0);
  const sumHis = rows.reduce((s, r) => s + r.his, 0);
  const meanHis = sumHis / n;
  const maxHis = Math.max(...rows.map((r) => r.his));
  const withCvs = rows.filter((r) => r.cvs != null).length;
  const tally = (key: (r: CorridorMetric) => string) => {
    const m = new Map<string, number>();
    for (const r of rows) {
      const k = key(r);
      m.set(k, (m.get(k) ?? 0) + 1);
    }
    return [...m.entries()].sort((a, b) => b[1] - a[1]);
  };
  const topDest = tally((r) => r.destination_country)[0];
  const topOrigin = tally((r) => r.origin_country)[0];
  const topHs = tally((r) => r.commodity_hs)[0];
  return {
    n,
    sumAlerts,
    meanHis,
    maxHis,
    withCvs,
    topDest,
    topOrigin,
    topHs,
  };
}

function escapeCsvCell(v: string): string {
  if (/[",\n]/.test(v)) return `"${v.replace(/"/g, '""')}"`;
  return v;
}

function downloadCorridorCsv(rows: CorridorMetric[]) {
  const headers = [
    "origin_country",
    "destination_country",
    "commodity_hs",
    "commodity_name",
    "his",
    "hdi",
    "notification_count",
    "severity_total",
    "cvs",
    "destination_roles",
  ];
  const lines = [
    headers.join(","),
    ...rows.map((r) =>
      [
        r.origin_country,
        r.destination_country,
        r.commodity_hs,
        r.commodity_name,
        String(r.his),
        String(r.hdi),
        String(r.notification_count),
        String(r.severity_total),
        r.cvs != null ? String(r.cvs) : "",
        (r.destination_roles ?? []).join(";"),
      ]
        .map((x) => escapeCsvCell(String(x)))
        .join(",")
    ),
  ];
  const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `corridors-${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

function AnalyticsStrip({ rows }: { rows: CorridorMetric[] }) {
  const s = corridorViewStats(rows);
  if (!s) {
    return (
      <p className="text-xs text-slate-500">
        No rows in this view. Relax filters or reset to see summary statistics.
      </p>
    );
  }
  return (
    <div className="grid gap-3 text-xs text-slate-700 sm:grid-cols-2 lg:grid-cols-4">
      <div className="rounded-lg border border-slate-100 bg-slate-50/90 px-3 py-2">
        <p className="font-medium text-slate-800">Hazard in view</p>
        <p className="mt-0.5 text-slate-600">
          Mean HIS <span className="font-mono font-semibold">{fmt(s.meanHis)}</span>
          <span className="text-slate-400"> · </span>
          Max <span className="font-mono font-semibold">{fmt(s.maxHis)}</span>
        </p>
      </div>
      <div className="rounded-lg border border-slate-100 bg-slate-50/90 px-3 py-2">
        <p className="font-medium text-slate-800">Alerts</p>
        <p className="mt-0.5 text-slate-600">
          <span className="font-mono font-semibold">{s.sumAlerts}</span> notifications across{" "}
          <span className="font-mono">{s.n}</span> lanes
        </p>
      </div>
      <div className="rounded-lg border border-slate-100 bg-slate-50/90 px-3 py-2">
        <p className="font-medium text-slate-800">Priority score</p>
        <p className="mt-0.5 text-slate-600">
          <span className="font-mono font-semibold">{s.withCvs}</span> of {s.n} rows have CVS
        </p>
      </div>
      <div className="rounded-lg border border-slate-100 bg-slate-50/90 px-3 py-2">
        <p className="font-medium text-slate-800">Top counts in filter</p>
        <p className="mt-0.5 leading-snug text-slate-600">
          Importer: <span className="font-medium">{s.topDest[0]}</span> ({s.topDest[1]} lanes)
          <br />
          Exporter: <span className="font-medium">{s.topOrigin[0]}</span> ({s.topOrigin[1]} lanes)
          <br />
          HS: <span className="font-mono">{s.topHs[0]}</span> ({s.topHs[1]} lanes)
        </p>
      </div>
    </div>
  );
}

export default function CorridorExplorer() {
  const router = useRouter();
  const [countries, setCountries] = useState<Country[]>([]);
  const [commodities, setCommodities] = useState<{ hs_code: string; names: string[] }[]>([]);
  const [corridors, setCorridors] = useState<CorridorMetric[]>([]);
  const [matchCount, setMatchCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [filters, setFilters] = useState<CorridorFilters>(DEFAULT_FILTERS);

  const listQuery = useMemo(() => buildListQuery(filters), [filters]);

  useEffect(() => {
    api.countries
      .list(false)
      .then((r) => setCountries(r.countries))
      .catch(() => setCountries([]));
    api.commodities
      .list()
      .then((r) => setCommodities(r.commodities))
      .catch(() => setCommodities([]));
  }, []);

  useEffect(() => {
    let cancelled = false;
    setRefreshing(true);
    api.corridors
      .list(listQuery)
      .then((r) => {
        if (!cancelled) {
          setCorridors(r.corridors);
          setMatchCount(r.count);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setCorridors([]);
          setMatchCount(0);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
          setRefreshing(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [listQuery]);

  const truncated = matchCount > corridors.length;
  const countryOptions = useMemo(
    () => [...countries].sort((a, b) => a.name.localeCompare(b.name)),
    [countries]
  );

  const applyPreset = (preset: string) => {
    const next = { ...DEFAULT_FILTERS };
    switch (preset) {
      case "high_hazard":
        setFilters({ ...next, minHis: "0.5" });
        break;
      case "active_dest":
        setFilters({ ...next, activeOnly: true });
        break;
      case "notifier":
        setFilters({ ...next, role: "notifier" });
        break;
      case "eu_to_eu":
        setFilters({ ...next, originEu: "eu", destEu: "eu" });
        break;
      case "non_eu_origin_eu_dest":
        setFilters({ ...next, originEu: "non", destEu: "eu" });
        break;
      default:
        break;
    }
  };

  if (loading && !corridors.length) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-bold text-slate-900">Corridor list</h1>
        <p className="text-xs text-slate-600">
          Explore trade lanes with server-side filters (up to 1000 rows by hazard rank in each
          request). Hover column titles for score definitions. Open a row for full diagnostics.
        </p>
      </div>

      <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-sm font-semibold text-slate-800" id="corridor-filters-heading">
            Filters
          </h2>
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[10px] font-medium uppercase tracking-wide text-slate-500">
              Quick views
            </span>
            <button
              type="button"
              onClick={() => applyPreset("high_hazard")}
              className="rounded-md border border-slate-200 bg-white px-2 py-1 text-[11px] text-slate-700 hover:bg-slate-50"
            >
              HIS ≥ 0.5
            </button>
            <button
              type="button"
              onClick={() => applyPreset("active_dest")}
              className="rounded-md border border-slate-200 bg-white px-2 py-1 text-[11px] text-slate-700 hover:bg-slate-50"
            >
              Active destination
            </button>
            <button
              type="button"
              onClick={() => applyPreset("notifier")}
              className="rounded-md border border-slate-200 bg-white px-2 py-1 text-[11px] text-slate-700 hover:bg-slate-50"
            >
              Notifier role
            </button>
            <button
              type="button"
              onClick={() => applyPreset("eu_to_eu")}
              className="rounded-md border border-slate-200 bg-white px-2 py-1 text-[11px] text-slate-700 hover:bg-slate-50"
            >
              EU → EU
            </button>
            <button
              type="button"
              onClick={() => applyPreset("non_eu_origin_eu_dest")}
              className="rounded-md border border-slate-200 bg-white px-2 py-1 text-[11px] text-slate-700 hover:bg-slate-50"
            >
              Non-EU → EU
            </button>
            <button
              type="button"
              onClick={() => setFilters(DEFAULT_FILTERS)}
              className="rounded-md border border-slate-300 bg-slate-50 px-2 py-1 text-[11px] font-medium text-slate-800 hover:bg-slate-100"
            >
              Reset
            </button>
          </div>
        </div>

        <div
          className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4"
          role="group"
          aria-labelledby="corridor-filters-heading"
        >
          <div className="flex flex-col gap-1">
            <label htmlFor="flt-commodity" className="text-[11px] font-medium text-slate-600">
              Commodity (HS)
            </label>
            <select
              id="flt-commodity"
              value={filters.commodity}
              onChange={(e) => setFilters((f) => ({ ...f, commodity: e.target.value }))}
              className="rounded-lg border border-gray-200 px-2 py-1.5 text-sm"
            >
              <option value="">All commodities</option>
              {commodities.map((c) => (
                <option key={c.hs_code} value={c.hs_code}>
                  {c.hs_code} — {c.names[0]?.slice(0, 36) ?? ""}
                </option>
              ))}
            </select>
          </div>
          <div className="flex flex-col gap-1">
            <label htmlFor="flt-origin" className="text-[11px] font-medium text-slate-600">
              Origin
            </label>
            <select
              id="flt-origin"
              value={filters.origin}
              onChange={(e) => setFilters((f) => ({ ...f, origin: e.target.value }))}
              className="rounded-lg border border-gray-200 px-2 py-1.5 text-sm"
            >
              <option value="">Any origin</option>
              {countryOptions.map((c) => (
                <option key={c.m49} value={String(c.m49)}>
                  {c.name}
                </option>
              ))}
            </select>
          </div>
          <div className="flex flex-col gap-1">
            <label htmlFor="flt-destination" className="text-[11px] font-medium text-slate-600">
              Destination
            </label>
            <select
              id="flt-destination"
              value={filters.destination}
              onChange={(e) => setFilters((f) => ({ ...f, destination: e.target.value }))}
              className="rounded-lg border border-gray-200 px-2 py-1.5 text-sm"
            >
              <option value="">Any destination</option>
              {countryOptions.map((c) => (
                <option key={`d-${c.m49}`} value={String(c.m49)}>
                  {c.name}
                </option>
              ))}
            </select>
          </div>
          <div className="flex flex-col gap-1">
            <label htmlFor="flt-role" className="text-[11px] font-medium text-slate-600">
              Destination RASFF role
            </label>
            <select
              id="flt-role"
              value={filters.role}
              onChange={(e) => setFilters((f) => ({ ...f, role: e.target.value }))}
              className="rounded-lg border border-gray-200 px-2 py-1.5 text-sm"
            >
              {ROLE_OPTIONS.map((o) => (
                <option key={o.value || "any"} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>
          <div className="flex flex-col gap-1">
            <label htmlFor="flt-min-his" className="text-[11px] font-medium text-slate-600">
              Minimum HIS
            </label>
            <input
              id="flt-min-his"
              type="number"
              step="0.01"
              min={0}
              placeholder="e.g. 0.35"
              value={filters.minHis}
              onChange={(e) => setFilters((f) => ({ ...f, minHis: e.target.value }))}
              className="rounded-lg border border-gray-200 px-2 py-1.5 text-sm"
            />
          </div>
          <div className="flex flex-col gap-1">
            <label htmlFor="flt-min-n" className="text-[11px] font-medium text-slate-600">
              Min. alert count
            </label>
            <input
              id="flt-min-n"
              type="number"
              min={0}
              step={1}
              placeholder="e.g. 5"
              value={filters.minNotifications}
              onChange={(e) => setFilters((f) => ({ ...f, minNotifications: e.target.value }))}
              className="rounded-lg border border-gray-200 px-2 py-1.5 text-sm"
            />
          </div>
          <div className="flex flex-col gap-1">
            <label htmlFor="flt-min-hdi" className="text-[11px] font-medium text-slate-600">
              Minimum HDI
            </label>
            <input
              id="flt-min-hdi"
              type="number"
              step="0.01"
              min={0}
              placeholder="e.g. 0.2"
              value={filters.minHdi}
              onChange={(e) => setFilters((f) => ({ ...f, minHdi: e.target.value }))}
              className="rounded-lg border border-gray-200 px-2 py-1.5 text-sm"
            />
          </div>
          <div className="flex flex-col gap-1">
            <label htmlFor="flt-min-cvs" className="text-[11px] font-medium text-slate-600">
              Minimum CVS
            </label>
            <input
              id="flt-min-cvs"
              type="number"
              step="0.01"
              min={0}
              max={1}
              placeholder="0–1"
              value={filters.minCvs}
              onChange={(e) => setFilters((f) => ({ ...f, minCvs: e.target.value }))}
              className="rounded-lg border border-gray-200 px-2 py-1.5 text-sm"
            />
          </div>
          <div className="flex flex-col gap-1">
            <label htmlFor="flt-has-cvs" className="text-[11px] font-medium text-slate-600">
              CVS available
            </label>
            <select
              id="flt-has-cvs"
              value={filters.hasCvs}
              onChange={(e) => setFilters((f) => ({ ...f, hasCvs: e.target.value }))}
              className="rounded-lg border border-gray-200 px-2 py-1.5 text-sm"
            >
              <option value="">Any</option>
              <option value="yes">Has CVS</option>
              <option value="no">No CVS</option>
            </select>
          </div>
          <div className="flex flex-col gap-1">
            <label htmlFor="flt-oeu" className="text-[11px] font-medium text-slate-600">
              Origin region
            </label>
            <select
              id="flt-oeu"
              value={filters.originEu}
              onChange={(e) => setFilters((f) => ({ ...f, originEu: e.target.value }))}
              className="rounded-lg border border-gray-200 px-2 py-1.5 text-sm"
            >
              {EU_SCOPE_OPTIONS.map((o) => (
                <option key={`o-${o.value}`} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>
          <div className="flex flex-col gap-1">
            <label htmlFor="flt-deu" className="text-[11px] font-medium text-slate-600">
              Destination region
            </label>
            <select
              id="flt-deu"
              value={filters.destEu}
              onChange={(e) => setFilters((f) => ({ ...f, destEu: e.target.value }))}
              className="rounded-lg border border-gray-200 px-2 py-1.5 text-sm"
            >
              {EU_SCOPE_OPTIONS.map((o) => (
                <option key={`d-${o.value}`} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>
          <div className="flex flex-col justify-end gap-1">
            <label className="flex cursor-pointer items-center gap-2 text-sm text-slate-700">
              <input
                type="checkbox"
                checked={filters.activeOnly}
                onChange={(e) =>
                  setFilters((f) => ({ ...f, activeOnly: e.target.checked }))
                }
                className="rounded border-gray-300"
              />
              Active destination only
            </label>
            <p className="text-[10px] text-slate-500">
              Excludes lanes where the destination was only flagged “attention”.
            </p>
          </div>
        </div>
      </div>

      <div className="rounded-xl border border-indigo-100 bg-indigo-50/40 p-4 shadow-sm">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-sm font-semibold text-slate-800">View summary</h2>
          <div className="flex items-center gap-2 text-[11px] text-slate-600">
            {refreshing && <span className="animate-pulse">Updating…</span>}
            <span>
              Showing <span className="font-mono font-semibold">{corridors.length}</span>
              {truncated ? (
                <>
                  {" "}
                  of <span className="font-mono font-semibold">{matchCount}</span> matching (first
                  1000 by HIS)
                </>
              ) : (
                <> corridors</>
              )}
            </span>
            <button
              type="button"
              disabled={!corridors.length}
              onClick={() => downloadCorridorCsv(corridors)}
              className="ml-2 rounded-md border border-indigo-200 bg-white px-2 py-1 text-[11px] font-medium text-indigo-800 hover:bg-indigo-50 disabled:opacity-40"
            >
              Export CSV
            </button>
          </div>
        </div>
        <AnalyticsStrip rows={corridors} />
      </div>

      <div className="relative bg-white rounded-xl border border-gray-200 shadow-sm p-5">
        {refreshing && (
          <div
            className="pointer-events-none absolute inset-0 z-10 rounded-xl bg-white/40"
            aria-hidden
          />
        )}
        <DataTable
          columns={COLUMNS}
          data={corridors}
          onRowClick={(c) =>
            router.push(
              `/dashboard/corridors/${c.commodity_hs}/${c.destination_m49}/${c.origin_m49}`
            )
          }
          searchKeys={[
            "origin_country",
            "destination_country",
            "commodity_name",
            "commodity_hs",
          ]}
          pageSize={30}
        />
      </div>
    </div>
  );
}
