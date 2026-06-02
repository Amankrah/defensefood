"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeft,
  AlertTriangle,
  Boxes,
  Scale,
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
import type {
  CorridorProfile,
  HazardBreakdown,
  HazardBucket,
  TradeFlowMetrics,
} from "@/lib/types";
import { fmt, fmtInt, fmtPct } from "@/lib/utils";
import {
  interpretCvs,
  interpretHdi,
  interpretHhi,
  interpretHis,
  interpretIdr,
  interpretOcs,
  interpretSci,
  interpretSsr,
  interpretZuv,
  interpretVolume,
  interpretMtd,
  interpretDeltaHhi,
  interpretDeltaOcs,
  interpretDgi,
  interpretPcc,
  interpretCrs,
  interpretDis,
  bandClasses,
  type Band,
} from "@/lib/interpret";
import { actionFor } from "@/lib/actionHint";
import MetricTile from "@/components/shared/MetricTile";
import VerdictBanner from "@/components/shared/VerdictBanner";
import { RolePills } from "@/components/shared/RolePill";
import { MarketPresenceBadge } from "@/components/shared/MarketPresenceBadge";
import LaneWalkthrough from "@/components/shared/LaneWalkthrough";

const HAZARD_CATS: {
  key: HazardBucket;
  label: string;
  color: string;
}[] = [
  { key: "biological", label: "Microbial", color: "#10b981" },
  { key: "chem_pesticides", label: "Pesticide", color: "#84cc16" },
  { key: "chem_heavy_metals", label: "Heavy metals", color: "#f59e0b" },
  { key: "chem_mycotoxins", label: "Mycotoxins", color: "#f97316" },
  { key: "chem_other", label: "Other chemical", color: "#ef4444" },
  { key: "regulatory", label: "Labelling / regulatory", color: "#8b5cf6" },
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
        Hazard family mix across {total.toFixed(total >= 10 ? 0 : 1)} categorised alerts
      </p>
      <div className="flex h-5 overflow-hidden rounded-lg bg-slate-100">
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

const STEP_BADGE = "inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-blue-100 px-1.5 text-[10px] font-semibold text-blue-700";

function StepHeader({
  step,
  title,
  description,
  icon: Icon,
  iconColor = "text-blue-500",
}: {
  step: number;
  title: string;
  description: string;
  icon: typeof Shield;
  iconColor?: string;
}) {
  return (
    <header className="mb-3 flex items-start gap-3">
      <span className={STEP_BADGE}>{step}</span>
      <div className="flex-1">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-900">
          <Icon size={15} className={iconColor} aria-hidden />
          {title}
        </h2>
        <p className="text-[11px] text-slate-600">{description}</p>
      </div>
    </header>
  );
}

function tonnes(kg: number | null | undefined): string {
  if (kg == null || Number.isNaN(kg)) return "—";
  if (kg >= 1_000_000_000) return `${(kg / 1_000_000_000).toFixed(2)} Mt`;
  if (kg >= 1_000_000) return `${(kg / 1_000_000).toFixed(2)} kt`;
  if (kg >= 1_000) return `${(kg / 1_000).toFixed(1)} t`;
  return `${kg.toFixed(0)} kg`;
}

export default function LaneReport() {
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

  const dep = profile?.dependency;
  const haz = profile?.hazard;

  // Hazard verdict synthesis
  const trackRecordVerdict = useMemo(() => {
    if (!haz) return null;
    const his = interpretHis(haz.his);
    const hdi = interpretHdi(haz.hdi);
    const count = haz.notification_count ?? 0;
    if (count === 0)
      return {
        title: "Quiet so far",
        body: "No RASFF notifications recorded on this exact corridor in the loaded period.",
        band: "low" as Band,
      };
    const familyTop = haz.hazard_breakdown
      ? HAZARD_CATS.map((c) => ({ ...c, v: haz.hazard_breakdown?.[c.key] ?? 0 })).sort(
          (a, b) => b.v - a.v
        )[0]
      : null;
    const familyTotal = haz.hazard_breakdown
      ? Object.values(haz.hazard_breakdown).reduce((s, v) => s + (v ?? 0), 0)
      : 0;
    const famPart =
      familyTop && familyTotal > 0
        ? `${familyTop.label.toLowerCase()} ${familyTop.v >= familyTotal * 0.5 ? "dominates" : "leads"} the mix`
        : null;
    const body = [
      `${count} alert${count === 1 ? "" : "s"} on this lane`,
      famPart,
      hdi.verdict.toLowerCase().replace(/\.$/, ""),
    ]
      .filter(Boolean)
      .join("; ");
    return {
      title:
        his.band === "high" || hdi.band === "high"
          ? "Active history"
          : "Some history",
      body: `${body[0].toUpperCase()}${body.slice(1)}.`,
      band: his.band,
    };
  }, [haz]);

  // Supply verdict synthesis
  const supplyVerdict = useMemo(() => {
    if (!dep || "error" in dep) return null;
    const idr = interpretIdr(dep.idr);
    const ocs = interpretOcs(dep.ocs);
    const hhi = interpretHhi(dep.hhi);
    const ssr = interpretSsr(dep.ssr);
    const bandList = [idr.band, ocs.band, hhi.band, ssr.band] as const;
    const worst: Band = bandList.includes("high")
      ? "high"
      : bandList.includes("flag")
        ? "flag"
        : bandList.includes("med")
          ? "med"
          : "low";
    const originCountry = profile?.origin_country ?? "this origin";
    const destCountry = profile?.destination_country ?? "the destination";
    const sentences: string[] = [];
    if ((dep.ocs ?? 0) >= 0.5) {
      sentences.push(
        `${originCountry} supplies ${fmtPct(dep.ocs)} of ${destCountry}'s imports of this commodity.`
      );
    } else if ((dep.ocs ?? 0) > 0) {
      sentences.push(
        `${originCountry} contributes ${fmtPct(dep.ocs)} of ${destCountry}'s imports.`
      );
    }
    if ((dep.ssr ?? 1) < 0.1 && !dep.idr_gt_1) {
      sentences.push(`${destCountry} produces essentially none of it locally.`);
    } else if (dep.idr_gt_1) {
      sentences.push(
        `Imports exceed apparent domestic supply — either ${destCountry} is a transit hub or production data is missing.`
      );
    }
    if ((dep.hhi ?? 0) >= 0.5) {
      sentences.push(`The supplier base is very concentrated (HHI ${fmt(dep.hhi)}).`);
    } else if ((dep.hhi ?? 0) >= 0.25) {
      sentences.push(`Supplier base is concentrated (HHI ${fmt(dep.hhi)}).`);
    }
    if (!sentences.length) sentences.push("Lane shows diversified supply with no concentration alarm.");
    const title =
      worst === "high"
        ? "Concentrated dependency"
        : worst === "flag"
          ? "Data caveat — read with care"
          : worst === "med"
            ? "Some structural exposure"
            : "Diversified supply";
    return {
      title,
      body: sentences.join(" "),
      band: worst,
    };
  }, [dep, profile?.origin_country, profile?.destination_country]);

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <div className="h-9 w-9 animate-spin rounded-full border-2 border-slate-200 border-t-blue-600" />
      </div>
    );
  }

  if (!profile || "error" in profile) {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 p-6">
        <p className="text-red-700">
          Corridor not found: {hs} / {dest} / {origin}
        </p>
      </div>
    );
  }

  // Adapter: actionFor reads (cvs, his, ocs, hhi, hazard_breakdown) from a CorridorMetric.
  // Build a minimal record that satisfies those reads from this profile.
  const action = actionFor({
    commodity_hs: profile.commodity_hs,
    commodity_name: profile.commodity_name,
    destination_m49: profile.destination_m49,
    destination_country: profile.destination_country,
    origin_m49: profile.origin_m49,
    origin_country: profile.origin_country,
    his: haz?.his ?? 0,
    hdi: haz?.hdi ?? 0,
    notification_count: haz?.notification_count ?? 0,
    severity_total: haz?.severity_total ?? 0,
    hazard_breakdown: haz?.hazard_breakdown,
    ocs: dep && !("error" in dep) ? dep.ocs : null,
    hhi: dep && !("error" in dep) ? dep.hhi : null,
    cvs: profile.cvs ?? null,
  });

  const cvsVerdict = interpretCvs(profile.cvs ?? null);
  const cvsBandClasses = bandClasses(cvsVerdict.band);

  // Score breakdown — only show spokes that have data.
  const breakdown = [
    { key: "sci", label: "Supply criticality", value: profile.sci_norm, color: "#3b82f6" },
    { key: "his", label: "Hazard intensity", value: profile.his_norm, color: "#ef4444" },
    { key: "crs", label: "Consumption rank", value: profile.crs_norm, color: "#8b5cf6" },
  ].filter((b) => b.value != null && !Number.isNaN(b.value)) as {
    key: string;
    label: string;
    value: number;
    color: string;
  }[];
  const breakdownTotal = breakdown.reduce((s, b) => s + b.value, 0) || 1;

  const peerUVs = (tradeFlow?.peer_unit_values ?? []).map((p) => ({
    partner: p.partnerCode,
    uv: p.unit_value,
    z: p.z_uv,
    isThis: p.partnerCode === origin,
  }));

  return (
    <div className="mx-auto max-w-7xl space-y-5">
      {/* Hero — headline + priority score */}
      <header className="flex items-start gap-4">
        <Link
          href="/dashboard"
          className="mt-1 rounded-lg p-1.5 hover:bg-slate-100"
          title="Back to Today"
        >
          <ArrowLeft size={16} />
        </Link>
        <div className="min-w-0 flex-1">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-blue-600/90">
            Lane forensic report
          </p>
          <h1 className="text-xl font-bold tracking-tight text-slate-900">
            {profile.origin_country} <span className="text-slate-400">→</span>{" "}
            {profile.destination_country}
          </h1>
          <p className="mt-0.5 text-xs text-slate-500">
            <span className="mr-2 inline-block rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[10px] text-slate-600">
              HS {profile.commodity_hs}
            </span>
            {profile.commodity_name}
          </p>
          {profile.destination_roles && profile.destination_roles.length > 0 && (
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <span className="text-[10px] font-medium uppercase tracking-wider text-slate-400">
                Destination role
              </span>
              <RolePills roles={profile.destination_roles} />
              <MarketPresenceBadge presence={profile.market_presence} />
            </div>
          )}
          {profile.market_presence === "informational" && (
            <p className="mt-2 max-w-2xl rounded border border-slate-200 bg-slate-50 px-2 py-1.5 text-[11px] leading-snug text-slate-600">
              <strong className="text-slate-700">Informational lane.</strong> Per EU RASFF SOPs,
              the product is not on this country&apos;s market. Structural metrics (SCI, BDI,
              CVS) are shown below for transparency but should not drive inspection priority
              for this lane.
            </p>
          )}
        </div>
      </header>

      {/* Headline priority card */}
      <section
        className={`rounded-2xl border p-5 shadow-sm ${cvsBandClasses.bg} ${cvsBandClasses.border}`}
      >
        <div className="grid grid-cols-1 gap-4 md:grid-cols-[auto_1fr_auto] md:items-center">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">
              Priority score
            </p>
            <p className={`font-mono text-4xl font-bold tracking-tight ${cvsBandClasses.text}`}>
              {profile.cvs != null
                ? fmt(profile.cvs)
                : profile.cvs_hazard_only != null
                  ? fmt(profile.cvs_hazard_only)
                  : "—"}
            </p>
            <p className="text-[10px] text-slate-500">
              {profile.cvs != null
                ? "out of 1.000 (CVS)"
                : "hazard-only fallback (CVS unavailable)"}
            </p>
          </div>
          <div className="min-w-0">
            <p className={`text-xs font-semibold uppercase tracking-wide ${cvsBandClasses.text}`}>
              {cvsVerdict.verdict}
            </p>
            <p className="mt-1 text-sm text-slate-800">
              {profile.cvs != null
                ? profile.cvs_mode === "sci_crs_his"
                  ? "Score blends supply criticality, hazard intensity, and consumption rank."
                  : "Score blends supply criticality and hazard intensity (consumption data pending)."
                : "Structural inputs are missing for this lane, so we fall back to a hazard-only signal. Use with caution."}
            </p>
          </div>
          <div className="text-center md:text-right">
            <p className="text-[10px] font-medium uppercase tracking-wider text-slate-500">
              Suggested action
            </p>
            <span
              className={`mt-1 inline-flex rounded-full border px-3 py-1 text-xs font-medium ${
                action.tone === "high"
                  ? "border-red-200 bg-white text-red-700"
                  : action.tone === "med"
                    ? "border-orange-200 bg-white text-orange-700"
                    : "border-slate-200 bg-white text-slate-700"
              }`}
              title={action.reason}
            >
              {action.label}
            </span>
            <p className="mt-1 max-w-[180px] text-[10px] text-slate-500">{action.reason}</p>
          </div>
        </div>
      </section>

      {profile.cvs == null && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-800">
          <span className="font-semibold">CVS unavailable.</span>{" "}
          {profile.sci_unavailable_label ? (
            <span>{profile.sci_unavailable_label}</span>
          ) : (
            <>
              Missing inputs:{" "}
              <span className="font-mono">
                {(profile.cvs_missing_inputs ?? ["sci_norm"]).join(", ")}
              </span>
            </>
          )}
          {profile.cvs_hazard_only != null ? (
            <>
              {" "}
              Hazard-only fallback score:{" "}
              <span className="font-mono font-semibold">
                {profile.cvs_hazard_only.toFixed(3)}
              </span>
            </>
          ) : null}
          . The structural picture below is still worth reading when trade data exists.
        </div>
      )}

      {/* Step 1 — Track record (Hazard) */}
      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <StepHeader
          step={1}
          title="The track record"
          description="What official RASFF notifications say about this lane."
          icon={AlertTriangle}
          iconColor="text-red-500"
        />

        {haz ? (
          <>
            {trackRecordVerdict && (
              <VerdictBanner
                title={trackRecordVerdict.title}
                body={trackRecordVerdict.body}
                band={trackRecordVerdict.band}
                icon={AlertTriangle}
              />
            )}
            <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <MetricTile
                label="Alerts logged"
                value={fmtInt(haz.notification_count)}
                band={haz.notification_count >= 20 ? "high" : haz.notification_count >= 5 ? "med" : "low"}
                verdict={
                  haz.notification_count >= 20
                    ? "Many alerts on record — sustained attention from RASFF."
                    : haz.notification_count >= 5
                      ? "A meaningful cluster of alerts to consider."
                      : haz.notification_count > 0
                        ? "A small number of alerts on record."
                        : "No alerts on record in window."
                }
              />
              <MetricTile
                label="Cumulative seriousness"
                value={fmt(haz.severity_total, 2)}
                band={haz.severity_total >= 10 ? "high" : haz.severity_total >= 3 ? "med" : "low"}
                verdict="Sum of severity weights (classification × risk decision) across every alert."
              />
              <MetricTile
                label="Hazard intensity"
                abbr="HIS"
                metricKey="his"
                value={fmt(haz.his)}
                band={interpretHis(haz.his).band}
                bar={Math.min(haz.his / 1.5, 1)}
                verdict={interpretHis(haz.his).verdict}
              />
              <MetricTile
                label="Hazard diversity"
                abbr="HDI"
                metricKey="hdi"
                value={fmt(haz.hdi)}
                band={interpretHdi(haz.hdi).band}
                bar={haz.hdi}
                verdict={interpretHdi(haz.hdi).verdict}
              />
            </div>
            {haz.dgi != null && (
              <div className="mt-3">
                <MetricTile
                  label="Detection gap"
                  abbr="DGI"
                  metricKey="dgi"
                  value={fmt(haz.dgi)}
                  band={interpretDgi(haz.dgi).band}
                  bar={Math.min(Math.max((haz.dgi + 1) / 2, 0), 1)}
                  verdict={interpretDgi(haz.dgi).verdict}
                  caption="Lane's share of trade minus its share of notifications (≈ [−1, +1])."
                />
              </div>
            )}
            {haz.hazard_breakdown && (
              <HazardBreakdownBar breakdown={haz.hazard_breakdown} />
            )}
          </>
        ) : (
          <p className="text-sm italic text-slate-400">No hazard data available.</p>
        )}
      </section>

      {/* Step 2 — Supply picture (Dependency) */}
      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <StepHeader
          step={2}
          title="The supply picture"
          description="How much of the destination's supply rides on this origin, and how replaceable that supply is."
          icon={Boxes}
          iconColor="text-blue-500"
        />

        {dep && !("error" in dep) ? (
          <>
            {supplyVerdict && (
              <VerdictBanner
                title={supplyVerdict.title}
                body={supplyVerdict.body}
                band={supplyVerdict.band}
                icon={Boxes}
                chip={{
                  label:
                    dep.provenance === "faostat"
                      ? "FAOSTAT balance sheet"
                      : "Trade-only estimate",
                  tone: dep.provenance === "faostat" ? "low" : "med",
                }}
              />
            )}
            {dep.idr_gt_1 && (
              <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[11px] text-amber-800">
                <span className="font-semibold">Imports exceed supply.</span> Either{" "}
                {profile.destination_country} re-exports this commodity (trade hub) or its
                production data is not yet ingested. Treat self-sufficiency below with care.
              </div>
            )}
            <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <MetricTile
                label="Import reliance"
                abbr="IDR"
                metricKey="idr"
                value={fmt(dep.idr)}
                band={interpretIdr(dep.idr).band}
                bar={Math.min((dep.idr ?? 0) / 1.5, 1)}
                verdict={interpretIdr(dep.idr).verdict}
                caption="Share of apparent supply that comes from imports."
              />
              <MetricTile
                label="Share from this origin"
                abbr="OCS"
                metricKey="ocs"
                value={fmtPct(dep.ocs ?? 0)}
                band={interpretOcs(dep.ocs).band}
                bar={dep.ocs ?? 0}
                verdict={interpretOcs(dep.ocs).verdict}
                caption="Slice of total imports that come from this single origin."
              />
              <MetricTile
                label="Supplier concentration"
                abbr="HHI"
                metricKey="hhi"
                value={fmt(dep.hhi)}
                band={interpretHhi(dep.hhi).band}
                bar={dep.hhi ?? 0}
                verdict={interpretHhi(dep.hhi).verdict}
                caption="0 = many balanced suppliers, 1 = single supplier. ≥0.25 is concentrated."
              />
              <MetricTile
                label="Self-sufficiency"
                abbr="SSR"
                metricKey="ssr"
                value={fmt(dep.ssr)}
                band={interpretSsr(dep.ssr).band}
                bar={Math.min(dep.ssr ?? 0, 1)}
                verdict={interpretSsr(dep.ssr).verdict}
                caption={
                  dep.production_kg != null && dep.production_kg > 0
                    ? `Domestic production ≈ ${tonnes(dep.production_kg)}.`
                    : "Domestic production data not available."
                }
                badge={
                  dep.provenance === "faostat"
                    ? undefined
                    : { label: "trade-only", tone: "warn" }
                }
              />
            </div>
            <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-3">
              <MetricTile
                label="Bilateral dependency"
                abbr="BDI"
                metricKey="bdi"
                value={fmt(dep.bdi)}
                band={(dep.bdi ?? 0) >= 0.5 ? "high" : (dep.bdi ?? 0) >= 0.25 ? "med" : "low"}
                verdict="How much of the destination's domestic supply comes specifically from this origin."
                caption="Equals Import reliance × Origin share."
              />
              <MetricTile
                label="Supply criticality"
                abbr="SCI"
                metricKey="sci"
                value={fmt(dep.sci)}
                band={interpretSci(dep.sci).band}
                bar={Math.min((dep.sci ?? 0) / 2, 1)}
                verdict={interpretSci(dep.sci).verdict}
                caption="The headline lane exposure number, 0–2."
              />
              <MetricTile
                label="Apparent domestic supply"
                metricKey="ds_prime"
                abbr="DS′"
                value={tonnes(dep.production_kg && dep.total_imports_kg
                  ? (dep.production_kg + dep.total_imports_kg)
                  : null)}
                verdict="Production + imports − exports for the period."
                caption="Denominator of import reliance."
              />
            </div>
          </>
        ) : (
          <p className="text-sm italic text-slate-400">
            Dependency metrics need bilateral import statistics and production context for this
            corridor. They will appear here once that data is loaded in the API.
          </p>
        )}
      </section>

      {/* Step 2.5 — Demand picture (consumption) */}
      {profile.consumption &&
        (profile.consumption.pcc != null ||
          profile.consumption.crs != null ||
          profile.consumption.dis != null) && (
          <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <StepHeader
              step={3}
              title="The demand picture"
              description="How important this commodity is to the destination's food system — drives the fraud-exploitability ceiling."
              icon={Boxes}
              iconColor="text-purple-500"
            />
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              {profile.consumption.pcc != null && (
                <MetricTile
                  label="Per-capita consumption"
                  abbr="PCC"
                  metricKey="pcc"
                  value={`${fmt(profile.consumption.pcc, 1)}`}
                  unit="kg/yr"
                  band={interpretPcc(profile.consumption.pcc).band}
                  verdict={interpretPcc(profile.consumption.pcc).verdict}
                  caption="FAOSTAT Food Balance Sheet supply ÷ population."
                />
              )}
              {profile.consumption.crs != null && (
                <MetricTile
                  label="Consumption rank"
                  abbr="CRS"
                  metricKey="crs"
                  value={fmt(profile.consumption.crs)}
                  band={interpretCrs(profile.consumption.crs).band}
                  bar={profile.consumption.crs}
                  verdict={interpretCrs(profile.consumption.crs).verdict}
                  caption="Where this commodity sits in the destination's dietary basket (0 = lowest, 1 = top)."
                />
              )}
              {profile.consumption.dis != null && (
                <MetricTile
                  label="Demand inelasticity"
                  abbr="DIS"
                  metricKey="dis"
                  value={fmt(profile.consumption.dis)}
                  band={interpretDis(profile.consumption.dis).band}
                  bar={profile.consumption.dis}
                  verdict={interpretDis(profile.consumption.dis).verdict}
                  caption="1 − coefficient of variation of PCC over a 5-year window."
                />
              )}
            </div>
          </section>
        )}

      {/* Step 3 — Trade pattern check */}
      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <StepHeader
          step={3}
          title="Trade-pattern check"
          description="Price and volume patterns compared with usual trade. Anomalies are leads, not proof."
          icon={TrendingUp}
          iconColor="text-amber-500"
        />

        {tradeFlow && !("error" in tradeFlow) ? (
          <>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <MetricTile
                label="Unit price"
                value={
                  tradeFlow.unit_value != null && !Number.isNaN(tradeFlow.unit_value)
                    ? `$${fmt(tradeFlow.unit_value, 2)}`
                    : "—"
                }
                unit="/kg"
                verdict="Approximate price per kilogram from declared value over quantity."
              />
              <MetricTile
                label="Price vs peers"
                abbr="z(UV)"
                metricKey="z_uv"
                value={
                  tradeFlow.z_uv != null && !Number.isNaN(tradeFlow.z_uv)
                    ? fmt(tradeFlow.z_uv)
                    : "—"
                }
                band={interpretZuv(tradeFlow.z_uv).band}
                verdict={interpretZuv(tradeFlow.z_uv).verdict}
              />
              <MetricTile
                label="Mirror trade gap"
                abbr="MTD"
                metricKey="mtd"
                value={
                  tradeFlow.mtd != null && !Number.isNaN(tradeFlow.mtd)
                    ? fmtPct(tradeFlow.mtd)
                    : "—"
                }
                band={interpretMtd(tradeFlow.mtd).band}
                verdict={interpretMtd(tradeFlow.mtd).verdict}
              />
              <MetricTile
                label="Concentration change"
                abbr="ΔHHI"
                metricKey="delta_hhi"
                value={tradeFlow.delta_hhi != null ? fmt(tradeFlow.delta_hhi) : "—"}
                band={interpretDeltaHhi(tradeFlow.delta_hhi).band}
                verdict={interpretDeltaHhi(tradeFlow.delta_hhi).verdict}
              />
            </div>

            {/* Section 5.2 + 5.4b — additional trade-flow tiles */}
            <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
              {(() => {
                const hasVol =
                  tradeFlow.z_volume != null && !Number.isNaN(tradeFlow.z_volume);
                const need = (tradeFlow.z_volume_window_k ?? 5) + 1;
                const have = tradeFlow.z_volume_periods_available ?? 0;
                return (
                  <MetricTile
                    label="Volume anomaly"
                    abbr="z(M)"
                    metricKey="z_volume"
                    value={hasVol ? fmt(tradeFlow.z_volume as number) : "—"}
                    band={hasVol ? interpretVolume(tradeFlow.z_volume).band : "low"}
                    verdict={
                      hasVol
                        ? interpretVolume(tradeFlow.z_volume).verdict
                        : `Needs longer trade history (≥${need} periods; have ${have}).`
                    }
                    caption="Rolling-window z-score on the corridor's own import volume."
                    badge={hasVol ? undefined : { label: "history pending", tone: "warn" }}
                  />
                );
              })()}
              <MetricTile
                label="Origin share change"
                abbr="ΔOCS"
                metricKey="delta_ocs"
                value={
                  tradeFlow.delta_ocs != null && !Number.isNaN(tradeFlow.delta_ocs)
                    ? fmt(tradeFlow.delta_ocs)
                    : "—"
                }
                band={interpretDeltaOcs(tradeFlow.delta_ocs).band}
                verdict={interpretDeltaOcs(tradeFlow.delta_ocs).verdict}
                caption="This origin's share of imports vs prior period."
              />
            </div>

            {peerUVs.length > 0 && (
              <div className="mt-4">
                <p className="mb-2 text-xs font-medium text-slate-600">
                  Unit prices by origin — this corridor highlighted in blue
                </p>
                <ResponsiveContainer width="100%" height={180}>
                  <BarChart data={peerUVs}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                    <XAxis dataKey="partner" tick={{ fontSize: 10 }} />
                    <YAxis tick={{ fontSize: 10 }} />
                    <Tooltip formatter={(v) => `$${Number(v).toFixed(2)}/kg`} />
                    <Bar dataKey="uv">
                      {peerUVs.map((entry, i) => (
                        <Cell key={i} fill={entry.isThis ? "#3b82f6" : "#cbd5e1"} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </>
        ) : (
          <p className="text-sm italic text-slate-400">
            Trade-pattern metrics need bilateral import records for this corridor in the API.
          </p>
        )}
      </section>

      {/* Lane-specific walkthrough — formula chain with this lane's actual numbers */}
      <LaneWalkthrough
        dependency={dep && !("error" in dep) ? dep : null}
        cvs={profile.cvs}
      />

      {/* Step 4 — Score transparency */}
      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <StepHeader
          step={4}
          title="How we got this score"
          description="Transparency for the priority score above. Each component is the lane's percentile rank on that factor."
          icon={Scale}
          iconColor="text-purple-500"
        />

        {breakdown.length === 0 ? (
          <p className="text-sm italic text-slate-400">
            No normalised components available yet.
          </p>
        ) : (
          <div className="grid grid-cols-1 gap-5 md:grid-cols-[1fr_1fr]">
            <div>
              <p className="mb-2 text-[11px] font-medium text-slate-600">
                Contribution by factor
              </p>
              <ul className="space-y-3">
                {breakdown.map((b) => {
                  const pct = (b.value / breakdownTotal) * 100;
                  return (
                    <li key={b.key}>
                      <div className="mb-1 flex items-center justify-between text-xs">
                        <span className="flex items-center gap-2 text-slate-700">
                          <span
                            className="inline-block h-2 w-2 rounded-sm"
                            style={{ backgroundColor: b.color }}
                            aria-hidden
                          />
                          {b.label}
                        </span>
                        <span className="font-mono text-[11px] text-slate-500">
                          {fmt(b.value)} ({pct.toFixed(0)}%)
                        </span>
                      </div>
                      <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100">
                        <div
                          className="h-full rounded-full"
                          style={{
                            width: `${b.value * 100}%`,
                            backgroundColor: b.color,
                          }}
                        />
                      </div>
                    </li>
                  );
                })}
              </ul>
            </div>
            <div>
              <p className="mb-2 text-[11px] font-medium text-slate-600">Final priority score</p>
              <p className={`font-mono text-3xl font-semibold ${cvsBandClasses.text}`}>
                {profile.cvs != null
                  ? fmt(profile.cvs)
                  : profile.cvs_hazard_only != null
                    ? fmt(profile.cvs_hazard_only)
                    : "—"}
                <span className="ml-1 text-xs font-normal text-slate-400">
                  / 1.000
                </span>
              </p>
              <p className="mt-2 text-[11px] text-slate-500">
                Basis:{" "}
                {profile.cvs_mode === "sci_crs_his"
                  ? "supply criticality × hazard intensity × consumption rank."
                  : profile.cvs_mode === "sci_his"
                    ? "supply criticality × hazard intensity (consumption rank pending FAOSTAT food balance sheets)."
                    : "hazard-only fallback (structural inputs missing)."}
              </p>
              <p className="mt-2 text-[10px] text-slate-400">
                Producer-attribution (PAS) and supply-chain-complexity (SCCS) factors from
                blueprint sections 4.4/4.5 are not yet wired and have been omitted from this
                breakdown.
              </p>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
