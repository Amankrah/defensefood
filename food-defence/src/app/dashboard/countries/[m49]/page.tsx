"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, Globe, Shield } from "lucide-react";
import { api } from "@/lib/api";
import type {
  CorridorMetric,
  CountryDetail,
  CountryAcep,
  CountryOrpsByCommodity,
} from "@/lib/types";
import { fmt, riskColor, truncate } from "@/lib/utils";
import MetricCard from "@/components/shared/MetricCard";
import DataTable, { type Column } from "@/components/shared/DataTable";

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
        <span className="mr-1 text-[10px] text-slate-400">{r.commodity_hs}</span>
        {truncate(r.commodity_name, 30)}
      </span>
    ),
  },
  {
    key: "his",
    label: "Hazard",
    headerDescription: "Inbound hazard intensity (HIS) for that lane.",
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
    headerDescription: "RASFF notifications on that corridor.",
    type: "number",
    render: (r) => <span className="font-mono">{r.notification_count}</span>,
  },
  {
    key: "severity_total",
    label: "Alert weight",
    headerDescription: "Weighted seriousness of those alerts.",
    type: "number",
    render: (r) => <span className="font-mono">{fmt(r.severity_total, 2)}</span>,
  },
];

export default function CountryProfile() {
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
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" />
      </div>
    );
  }

  if (!detail || "error" in detail) {
    return <p className="text-red-600">Country {m49} not found.</p>;
  }

  return (
    <div className="space-y-5">
      <div className="flex items-start gap-4">
        <Link
          href="/dashboard"
          className="mt-1 p-1.5 rounded-lg hover:bg-gray-100"
        >
          <ArrowLeft size={16} />
        </Link>
        <div>
          <h1 className="text-lg font-bold text-gray-900 flex items-center gap-2">
            <Globe size={18} />
            {detail.name}
          </h1>
          <p className="text-xs text-slate-600">
            Country code {detail.m49}. {detail.is_eu27 ? "EU member state" : "Non-EU"}.
          </p>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <MetricCard
          label="Inbound exposure index (ACEP)"
          value={acep ? fmt(acep.acep) : "N/A"}
          subtext="Total fraud-relevant exposure reaching this country from linked corridors (higher = more combined pressure)"
          icon={Shield}
          color="bg-purple-500"
        />
        <MetricCard
          label="Inbound corridors"
          value={detail.corridors_as_destination}
          subtext="Distinct supplier lanes where this country is the importer"
        />
        <MetricCard
          label="Outbound corridors"
          value={detail.corridors_as_origin}
          subtext="Lanes where this country is the exporter"
        />
        <MetricCard
          label="Sum of inbound hazard (HIS)"
          value={fmt(
            inbound.reduce((s, c) => s + c.his, 0),
            3
          )}
          subtext="Adds hazard intensity across all inbound lanes (not a probability)"
        />
      </div>

      {detail.corridors_as_origin > 0 && orps && orps.commodities.length > 0 && (
        <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
          <h2 className="mb-1 text-sm font-semibold text-slate-900">
            Outbound risk propagation (ORPS) by commodity
          </h2>
          <p className="mb-3 text-xs text-slate-600">
            Framework Sec. 6.2: how much hazard-weighted exposure this origin sends to EU
            destinations for each product. PCC is proxied as 1.0 per destination until consumption
            data is connected; use for ranking, not absolute thresholds.
          </p>
          <ul className="divide-y divide-slate-100 text-sm">
            {orps.commodities.slice(0, 12).map((row) => (
              <li
                key={row.commodity_hs}
                className="flex items-center justify-between py-2 font-mono"
              >
                <span className="text-slate-800">{row.commodity_hs}</span>
                <span className="font-semibold text-slate-900">{fmt(row.orps, 4)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Inbound corridors */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
        <h2 className="mb-3 text-sm font-semibold text-slate-900">
          Inbound lanes (strongest hazard first)
        </h2>
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
      </div>
    </div>
  );
}
