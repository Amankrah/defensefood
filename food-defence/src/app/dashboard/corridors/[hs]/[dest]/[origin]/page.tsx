"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeft,
  AlertTriangle,
  Package,
  Shield,
  TrendingUp,
} from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";
import { api } from "@/lib/api";
import type { CorridorProfile, TradeFlowMetrics } from "@/lib/types";
import { fmt, fmtPct } from "@/lib/utils";
import type { HazardBreakdown } from "@/lib/types";
import MetricCard from "@/components/shared/MetricCard";
import GaugeChart from "@/components/shared/GaugeChart";
import RadarChart from "@/components/shared/RadarChart";
import ScoreBar from "@/components/shared/ScoreBar";
import { RolePills } from "@/components/shared/RolePill";

/** Inline component: 6-category bar showing which hazard families dominate a corridor. */
const HAZARD_CATS: {
  key: keyof HazardBreakdown;
  label: string;
  color: string;
}[] = [
  { key: "biological", label: "Biological", color: "#10b981" },
  { key: "chem_pesticides", label: "Pesticides", color: "#84cc16" },
  { key: "chem_heavy_metals", label: "Heavy metals", color: "#f59e0b" },
  { key: "chem_mycotoxins", label: "Mycotoxins", color: "#f97316" },
  { key: "chem_other", label: "Other chem.", color: "#ef4444" },
  { key: "regulatory", label: "Regulatory", color: "#8b5cf6" },
];

function HazardBreakdownBar({ breakdown }: { breakdown: HazardBreakdown }) {
  const total = HAZARD_CATS.reduce((s, c) => s + (breakdown[c.key] ?? 0), 0);
  if (total <= 0) {
    return (
      <div className="mt-4 rounded-lg border border-dashed border-slate-200 bg-slate-50 p-3 text-[11px] text-slate-500">
        No categorised hazards on this corridor yet.
      </div>
    );
  }
  return (
    <div className="mt-4">
      <p className="mb-2 text-xs font-medium text-slate-500">
        Hazard mix (how {haztotal(total)} categorised alerts split across families)
      </p>
      <div className="flex h-6 overflow-hidden rounded-lg bg-slate-100">
        {HAZARD_CATS.map((c) => {
          const v = breakdown[c.key] ?? 0;
          if (v <= 0) return null;
          const pct = (v / total) * 100;
          return (
            <div
              key={c.key}
              className="transition"
              style={{ width: `${pct}%`, backgroundColor: c.color }}
              title={`${c.label}: ${v.toFixed(2)} alerts (${pct.toFixed(1)}%)`}
            />
          );
        })}
      </div>
      <div className="mt-2 flex flex-wrap gap-3 text-[11px]">
        {HAZARD_CATS.map((c) => {
          const v = breakdown[c.key] ?? 0;
          if (v <= 0) return null;
          return (
            <span key={c.key} className="inline-flex items-center gap-1.5">
              <span
                className="h-2.5 w-2.5 rounded-sm"
                style={{ backgroundColor: c.color }}
                aria-hidden
              />
              <span className="text-slate-600">{c.label}</span>
              <span className="font-mono text-slate-800">{v.toFixed(2)}</span>
            </span>
          );
        })}
      </div>
    </div>
  );
}

function haztotal(v: number): string {
  return v.toFixed(v >= 10 ? 0 : 1);
}

export default function CorridorDeepDive() {
  const params = useParams();
  const hs = params.hs as string;
  const dest = parseInt(params.dest as string);
  const origin = parseInt(params.origin as string);

  const [profile, setProfile] = useState<CorridorProfile | null>(null);
  const [tradeFlow, setTradeFlow] = useState<TradeFlowMetrics | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      api.corridors.full(hs, dest, origin).catch(() => null),
      api.corridors.tradeAnomalies(hs, dest, origin).catch(() => null),
    ]).then(([prof, tf]) => {
      setProfile(prof);
      setTradeFlow(tf);
      setLoading(false);
    });
  }, [hs, dest, origin]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" />
      </div>
    );
  }

  if (!profile || "error" in profile) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-xl p-6">
        <p className="text-red-700">Corridor not found: {hs} / {dest} / {origin}</p>
      </div>
    );
  }

  const dep = profile.dependency;
  const haz = profile.hazard;

  // Radar data for composite score
  const radarData = [
    { axis: "SCI", value: profile.sci_norm ?? 0 },
    { axis: "HIS", value: profile.his_norm ?? 0 },
    { axis: "CRS", value: profile.crs_norm ?? 0 },
    { axis: "PAS", value: 0 },
    { axis: "SCCS", value: 0 },
  ];

  // Score breakdown bar
  const scoreSegments = [
    { label: "SCI", value: profile.sci_norm ?? 0, color: "#3b82f6" },
    { label: "HIS", value: profile.his_norm ?? 0, color: "#ef4444" },
    { label: "CRS", value: profile.crs_norm ?? 0, color: "#8b5cf6" },
  ];

  // Peer unit values for bar chart
  const peerUVs = (tradeFlow?.peer_unit_values ?? []).map((p) => ({
    partner: p.partnerCode,
    uv: p.unit_value,
    z: p.z_uv,
    isThis: p.partnerCode === origin,
  }));

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-start gap-4">
        <Link
          href="/dashboard/corridors"
          className="mt-1 p-1.5 rounded-lg hover:bg-gray-100"
        >
          <ArrowLeft size={16} />
        </Link>
        <div>
          <h1 className="text-lg font-bold text-gray-900">
            {profile.origin_country} &rarr; {profile.destination_country}
          </h1>
          <p className="text-sm text-gray-500">
            <span className="font-mono text-xs bg-gray-100 px-1.5 py-0.5 rounded mr-2">
              HS {profile.commodity_hs}
            </span>
            {profile.commodity_name}
          </p>
          {profile.destination_roles && profile.destination_roles.length > 0 && (
            <div className="mt-2 flex items-center gap-2">
              <span className="text-[10px] font-medium uppercase tracking-wider text-slate-400">
                Destination role
              </span>
              <RolePills roles={profile.destination_roles} />
              {profile.is_active_destination === false && (
                <span className="text-[10px] italic text-slate-400">
                  (passive mention only &mdash; no active response required)
                </span>
              )}
            </div>
          )}
        </div>
      </div>

      <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
        <h2 className="mb-1 text-sm font-semibold text-gray-900 flex items-center gap-2">
          <Package size={15} className="text-blue-500" aria-hidden />
          Supply dependency
        </h2>
        <p className="mb-4 text-xs text-slate-600">
          How much this destination relies on this origin for the commodity, and how concentrated
          sourcing is. Use for lab planning and supplier oversight, not as a verdict on quality.
        </p>
        {dep && !("error" in dep) ? (
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
            <GaugeChart
              value={dep.idr}
              max={2}
              label="IDR"
              sublabel="Share of imports from this partner"
            />
            <GaugeChart value={dep.ocs} max={1} label="OCS" sublabel="Partner share of supply" />
            <GaugeChart value={dep.hhi} max={1} label="HHI" sublabel="Market concentration" />
            <MetricCard
              label="BDI"
              value={fmt(dep.bdi)}
              subtext="Bilateral dependency: economic pull of this specific lane"
            />
            <MetricCard
              label="SSR"
              value={fmt(dep.ssr)}
              subtext="Self-sufficiency ratio for the product in the destination"
            />
            <MetricCard
              label="SCI"
              value={fmt(dep.sci)}
              subtext={`Structural criticality index, scaled to ${fmtPct(dep.sci_norm)} after normalisation`}
              icon={Shield}
              color="bg-blue-500"
            />
          </div>
        ) : (
          <p className="text-sm italic text-gray-400">
            Dependency metrics need bilateral import statistics and production context for this
            corridor. They will appear here once that data is loaded in the API.
          </p>
        )}
      </div>

      <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
        <h2 className="mb-1 text-sm font-semibold text-gray-900 flex items-center gap-2">
          <AlertTriangle size={15} className="text-red-500" aria-hidden />
          Hazard signals (RASFF)
        </h2>
        <p className="mb-4 text-xs text-slate-600">
          What official food safety notifications say about this lane. Higher values mean more
          alert activity or weight; they support triage, not automatic enforcement.
        </p>
        {haz ? (
          <>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <MetricCard
                label="Hazard intensity (HIS)"
                value={fmt(haz.his)}
                subtext="Severity-weighted, time-decayed RASFF signal on this lane"
                icon={AlertTriangle}
                color="bg-red-500"
              />
              <MetricCard
                label="Hazard diversity (HDI)"
                value={fmt(haz.hdi)}
                subtext="Shannon entropy over 6 categories (0 = single type, 1 = uniform mix)"
              />
              <MetricCard
                label="Alert count"
                value={haz.notification_count}
                subtext="Distinct RASFF notifications on this corridor"
              />
              <MetricCard
                label="Cumulative alert weight"
                value={fmt(haz.severity_total, 2)}
                subtext="W_class x W_risk summed across every alert"
              />
            </div>
            {haz.hazard_breakdown && (
              <HazardBreakdownBar breakdown={haz.hazard_breakdown} />
            )}
          </>
        ) : (
          <p className="text-sm text-gray-400 italic">No hazard data available.</p>
        )}
      </div>

      <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
        <h2 className="mb-1 text-sm font-semibold text-gray-900 flex items-center gap-2">
          <TrendingUp size={15} className="text-amber-500" aria-hidden />
          Trade anomalies
        </h2>
        <p className="mb-4 text-xs text-slate-600">
          Price and volume patterns compared with usual trade. Use to spot lanes worth a targeted
          check; anomalies are not proof of fraud.
        </p>
        {tradeFlow && !("error" in tradeFlow) ? (
          <div className="space-y-4">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <MetricCard
                label="Unit value"
                value={isNaN(tradeFlow.unit_value ?? NaN) ? "N/A" : `$${fmt(tradeFlow.unit_value!, 2)}/kg`}
                subtext="Approximate price per kg from declared value over quantity"
              />
              <MetricCard
                label="Price vs peers (z-score)"
                value={isNaN(tradeFlow.z_uv ?? NaN) ? "N/A" : fmt(tradeFlow.z_uv!)}
                subtext={
                  (tradeFlow.z_uv ?? 0) < -2
                    ? "Far below typical prices: check quality and documentation"
                    : (tradeFlow.z_uv ?? 0) > 2
                    ? "Far above typical prices: check misclassification or premium claims"
                    : "Near typical range for partner peers"
                }
                icon={AlertTriangle}
                color={
                  Math.abs(tradeFlow.z_uv ?? 0) > 2 ? "bg-red-500" : "bg-gray-400"
                }
              />
              <MetricCard
                label="Mirror trade gap (MTD)"
                value={isNaN(tradeFlow.mtd ?? NaN) ? "N/A" : fmtPct(tradeFlow.mtd!)}
                subtext={
                  (tradeFlow.mtd ?? 0) > 0.3
                    ? "Partner reported volumes differ strongly: verify reporting"
                    : "Reporter and partner figures broadly align"
                }
              />
              <MetricCard
                label="Concentration change (delta HHI)"
                value={tradeFlow.delta_hhi != null ? fmt(tradeFlow.delta_hhi) : "N/A"}
                subtext="How much supplier concentration moved in the window"
              />
            </div>

            {/* Peer UV bar chart */}
            {peerUVs.length > 0 && (
              <div>
                <p className="mb-2 text-xs text-gray-500">
                  Unit prices by origin (this corridor highlighted)
                </p>
                <ResponsiveContainer width="100%" height={180}>
                  <BarChart data={peerUVs}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                    <XAxis dataKey="partner" tick={{ fontSize: 10 }} />
                    <YAxis tick={{ fontSize: 10 }} />
                    <Tooltip formatter={(v) => `$${Number(v).toFixed(2)}/kg`} />
                    <Bar dataKey="uv">
                      {peerUVs.map((entry, i) => (
                        <Cell
                          key={i}
                          fill={entry.isThis ? "#3b82f6" : "#cbd5e1"}
                        />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>
        ) : (
          <p className="text-sm italic text-gray-400">
            Trade anomaly metrics need bilateral import records for this corridor in the API.
          </p>
        )}
      </div>

      <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
        <h2 className="mb-1 text-sm font-semibold text-gray-900 flex items-center gap-2">
          <Shield size={15} className="text-purple-500" aria-hidden />
          Combined priority score
        </h2>
        <p className="mb-4 text-xs text-slate-600">
          CVS (0 to 1) merges structural reliance (SCI), hazard heat (HIS), and demand pressure
          (CRS) after normalisation. Treat it as a ranking aid; confirm with controls on the
          ground.
        </p>

        {profile.cvs == null && (
          <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[11px] text-amber-800">
            <span className="font-semibold">CVS unavailable for this corridor.</span>{" "}
            Missing:{" "}
            <span className="font-mono">
              {(profile.cvs_missing_inputs ?? ["sci_norm", "crs_norm"]).join(", ")}
            </span>
            . Structural inputs (bilateral imports, domestic production, consumption ranking) are
            not yet connected. The hazard-only view below reflects what we can see from RASFF
            alone.
          </div>
        )}

        <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
          <div>
            <p className="mb-2 text-xs text-gray-500">Shape of the score (each spoke 0 to 1)</p>
            <RadarChart data={radarData} />
            <p className="mt-2 text-[10px] leading-relaxed text-slate-500">
              SCI: structural reliance. HIS: hazard signal. CRS: consumption-related demand
              pressure. PAS and SCCS are placeholders until those inputs are wired.
            </p>
          </div>
          <div>
            <p className="mb-2 text-xs text-gray-500">
              {profile.cvs != null
                ? "How much each factor contributes"
                : "Hazard-only signal (structural factors missing)"}
            </p>
            <div className="mb-4">
              <span className="font-mono text-3xl font-bold text-gray-900">
                {profile.cvs != null
                  ? fmt(profile.cvs)
                  : profile.cvs_hazard_only != null
                    ? fmt(profile.cvs_hazard_only)
                    : "N/A"}
              </span>
              <span className="ml-2 text-sm text-gray-400">
                {profile.cvs != null ? "out of 1.000 (CVS)" : "out of 1.000 (HIS percentile)"}
              </span>
            </div>
            <ScoreBar segments={scoreSegments} total={1} />
          </div>
        </div>
      </div>
    </div>
  );
}
