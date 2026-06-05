"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, Globe, Shield } from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { api } from "@/lib/api";
import type {
  CorridorMetric,
  CountryDetail,
  CountryAcep,
  CountryOrpsByCommodity,
} from "@/lib/types";
import { fmt, riskColor, truncate } from "@/lib/utils";
import MetricCard from "@/components/shared/MetricCard";
import CountryBriefCard from "@/components/shared/CountryBriefCard";
import DataTable, { type Column } from "@/components/shared/DataTable";
import { MarketPresenceBadge } from "@/components/shared/MarketPresenceBadge";
import { interpretAcep } from "@/lib/interpret";
import { CountrySnapshotSkeleton } from "@/components/shared/LoadingSkeleton";

const INBOUND_COLS: Column<CorridorMetric>[] = [
  {
    key: "origin_country",
    label: "Origin",
    headerDescription: "Partner country shipping into this destination.",
    type: "string",
    render: (r) => <span className="font-medium">{r.origin_country}</span>,
  },
  {
    key: "commodity_name",
    label: "Commodity",
    headerDescription: "Product category for the inbound lane.",
    type: "string",
    render: (r) => (
      <span>
        <span className="mr-1 inline-block rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[10px] text-slate-500">
          {r.commodity_hs}
        </span>
        {truncate(r.commodity_name, 30)}
      </span>
    ),
  },
  {
    key: "his",
    label: "Hazard intensity (HIS)",
    headerDescription: "Inbound hazard intensity for the lane.",
    type: "number",
    render: (r) => (
      <span className={`font-mono font-semibold ${riskColor(r.his, 0.5)}`}>
        {fmt(r.his)}
      </span>
    ),
  },
  {
    key: "notification_count",
    label: "Alerts",
    headerDescription: "RASFF notifications on the lane in the loaded window.",
    type: "number",
    render: (r) => <span className="font-mono">{r.notification_count}</span>,
  },
  {
    key: "severity_total",
    label: "Alert weight",
    headerDescription: "Cumulative seriousness across alerts on the lane.",
    type: "number",
    render: (r) => <span className="font-mono">{fmt(r.severity_total, 2)}</span>,
  },
];

export default function CountrySnapshot() {
  const params = useParams();
  const router = useRouter();
  const m49 = parseInt(params.m49 as string);

  const [detail, setDetail] = useState<CountryDetail | null>(null);
  const [acep, setAcep] = useState<CountryAcep | null>(null);
  const [inbound, setInbound] = useState<CorridorMetric[]>([]);
  const [orps, setOrps] = useState<CountryOrpsByCommodity | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      api.countries.get(m49),
      api.countries.acep(m49).catch(() => null),
      api.countries.exposure(m49),
      api.countries.orpsByCommodity(m49).catch(() => null),
    ]).then(([det, ac, exp, orp]) => {
      setDetail(det);
      setAcep(ac);
      setInbound(exp.corridors);
      setOrps(orp && !("error" in orp) ? orp : null);
      setLoading(false);
    });
  }, [m49]);

  if (loading) {
    return <CountrySnapshotSkeleton m49={m49} />;
  }

  if (!detail || "error" in detail) {
    return <p className="text-red-600">Country {m49} not found.</p>;
  }

  const acepVerdict = acep ? interpretAcep(acep.acep) : null;
  const inboundHisSum = inbound.reduce((s, c) => s + c.his, 0);
  const orpsChartData =
    orps?.commodities.slice(0, 12).map((r) => ({
      hs: r.commodity_hs,
      orps: r.orps,
      pccReal: r.pcc_real_count ?? 0,
      pccProxy: r.pcc_proxy_count ?? 0,
    })) ?? [];

  return (
    <div className="mx-auto max-w-7xl space-y-5">
      <header className="flex items-start gap-4">
        <Link
          href="/dashboard"
          className="mt-1 rounded-lg p-1.5 hover:bg-slate-100"
          title="Back to Today"
        >
          <ArrowLeft size={16} />
        </Link>
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wider text-blue-600/90">
            Country snapshot
          </p>
          <h1 className="flex items-center gap-2 text-xl font-bold tracking-tight text-slate-900">
            <Globe size={18} className="text-blue-600" aria-hidden />
            {detail.name}
          </h1>
          <p className="text-xs text-slate-500">
            M49 {detail.m49} ·{" "}
            {detail.is_eu27 ? (
              <span className="inline-flex items-center gap-1 rounded-full border border-blue-200 bg-blue-50 px-1.5 py-0.5 text-[10px] font-medium text-blue-700">
                EU member
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-slate-50 px-1.5 py-0.5 text-[10px] font-medium text-slate-700">
                Non-EU
              </span>
            )}
          </p>
        </div>
      </header>

      <section className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <MetricCard
          label="Total inbound exposure (ACEP)"
          value={acep ? fmt(acep.acep) : "N/A"}
          subtext={
            acepVerdict?.verdict ??
            "Aggregate hazard- and dependency-weighted exposure reaching this country."
          }
          icon={Shield}
          tone="info"
          footer={
            acep && (acep.crs_resolved_count != null || acep.bdi_missing_inbound != null) ? (
              <span title={
                acep.crs_missing_hs && acep.crs_missing_hs.length > 0
                  ? `CRS missing for HS: ${acep.crs_missing_hs.join(", ")}${
                      (acep.crs_missing_count ?? 0) > acep.crs_missing_hs.length
                        ? ` (+${(acep.crs_missing_count ?? 0) - acep.crs_missing_hs.length} more)`
                        : ""
                    }`
                  : "All inbound HS codes resolved a real CRS value."
              }>
                CRS resolved {acep.crs_resolved_count ?? 0}/
                {(acep.crs_resolved_count ?? 0) + (acep.crs_missing_count ?? 0)}
                {(acep.bdi_missing_inbound ?? 0) > 0
                  ? ` · BDI gap on ${acep.bdi_missing_inbound} lanes`
                  : ""}
              </span>
            ) : null
          }
        />
        <MetricCard
          label="Inbound corridors"
          value={detail.corridors_as_destination}
          subtext="Distinct supplier lanes where this country is the importer."
        />
        <MetricCard
          label="Outbound corridors"
          value={detail.corridors_as_origin}
          subtext="Lanes where this country is the exporter."
        />
        <MetricCard
          label="Sum of inbound hazard"
          value={fmt(inboundHisSum, 3)}
          subtext="Hazard intensity totalled across every inbound lane in the window."
        />
      </section>

      {/* AI country brief — inbound + outbound forensic narrative */}
      <CountryBriefCard m49={detail.m49} />

      {acep?.acep_by_role && (
        <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
            ACEP by RASFF market presence
          </h2>
          <p className="mt-1 text-[11px] text-slate-500">
            Per Pan et al. 2025 (Discover Food), role-aware directed networks
            split exposure by what RASFF actually asserts about each
            destination. The headline number above is the confirmed bucket.
          </p>
          <div className="mt-3 flex flex-wrap gap-3">
            {(["confirmed", "detected", "informational"] as const).map((role) => {
              const v = acep.acep_by_role?.[role] ?? 0;
              return (
                <div key={role} className="min-w-[140px] flex-1">
                  <MarketPresenceBadge presence={role} />
                  <p className="mt-1 font-mono text-lg font-semibold text-slate-900">
                    {fmt(v)}
                  </p>
                </div>
              );
            })}
          </div>
        </section>
      )}

      {detail.corridors_as_origin > 0 && orpsChartData.length > 0 && (
        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="text-sm font-semibold text-slate-900">
            Outbound risk propagation by commodity (ORPS)
          </h2>
          <p className="mb-3 text-xs text-slate-600">
            Blueprint Sec. 6.2 — how much hazard-weighted exposure this origin
            sends to EU destinations per product. PCC comes from the Section 3
            consumption lookup; destinations without FAOSTAT coverage fall back
            to PCC = 1.0. Hover a bar to see the real/proxy split for that HS.
          </p>
          <ResponsiveContainer width="100%" height={Math.max(160, orpsChartData.length * 22)}>
            <BarChart data={orpsChartData} layout="vertical" margin={{ left: 16, right: 16 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
              <XAxis type="number" tick={{ fontSize: 10 }} />
              <YAxis
                type="category"
                dataKey="hs"
                tick={{ fontSize: 10, fontFamily: "monospace" }}
                width={80}
              />
              <Tooltip
                formatter={(v, _name, p) => {
                  const datum = (p?.payload ?? {}) as { pccReal?: number; pccProxy?: number };
                  const real = datum.pccReal ?? 0;
                  const proxy = datum.pccProxy ?? 0;
                  const num = typeof v === "number" ? v : Number(v);
                  return [
                    `${num.toFixed(4)}  (PCC: ${real} real / ${proxy} proxy)`,
                    "ORPS",
                  ];
                }}
              />
              <Bar dataKey="orps" fill="#8b5cf6" />
            </BarChart>
          </ResponsiveContainer>
        </section>
      )}

      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="mb-2 text-sm font-semibold text-slate-900">
          Inbound lanes (strongest hazard first)
        </h2>
        <p className="mb-3 text-xs text-slate-600">
          Click a lane to open the full forensic report.
        </p>
        <DataTable
          columns={INBOUND_COLS}
          data={inbound}
          onRowClick={(c) =>
            router.push(
              `/dashboard/corridors/${c.commodity_hs}/${c.destination_m49}/${c.origin_m49}`
            )
          }
          searchKeys={["origin_country", "commodity_name"]}
          pageSize={25}
        />
      </section>
    </div>
  );
}
