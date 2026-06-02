"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, FlaskConical, FileText } from "lucide-react";
import { api } from "@/lib/api";
import type {
  CorridorProfile,
  LaneTimeSeries,
  MethodologyEntry,
  RawNotification,
  RawTradeRow,
} from "@/lib/types";
import { fmt, fmtInt, fmtPct } from "@/lib/utils";
import FormulaBlock from "@/components/shared/FormulaBlock";

/** Snapshot keys we expect on `dependency_by_period[year]` rows. */
const PERIOD_KEYS: { key: string; label: string }[] = [
  { key: "idr", label: "IDR" },
  { key: "ocs", label: "OCS" },
  { key: "hhi", label: "HHI" },
  { key: "bdi", label: "BDI" },
  { key: "sci", label: "SCI" },
  { key: "total_imports_kg", label: "Total imports (kg)" },
  { key: "bilateral_import_kg", label: "Bilateral imports (kg)" },
  { key: "production_kg", label: "Production (kg)" },
];

const METRIC_MATRIX_KEYS: {
  group: string;
  metrics: { key: string; raw?: string; norm?: string }[];
}[] = [
  {
    group: "Section 2 — Dependency",
    metrics: [
      { key: "idr" },
      { key: "ocs" },
      { key: "bdi" },
      { key: "hhi" },
      { key: "ssr" },
      { key: "sci", norm: "sci_norm" },
    ],
  },
  {
    group: "Section 3 — Consumption",
    metrics: [{ key: "crs", norm: "crs_norm" }],
  },
  {
    group: "Section 4 — Hazard",
    metrics: [
      { key: "his", norm: "his_norm" },
      { key: "hdi" },
    ],
  },
  {
    group: "Section 7 — Composite",
    metrics: [{ key: "cvs" }],
  },
];

function periodToHuman(p: number): string {
  // YYYYMM month buckets render as YYYY-MM
  if (p >= 100000) {
    const y = Math.floor(p / 100);
    const m = p % 100;
    return `${y}-${String(m).padStart(2, "0")}`;
  }
  return String(p);
}

export default function LabLanePage() {
  const params = useParams();
  const hs = params.hs as string;
  const dest = parseInt(params.dest as string, 10);
  const origin = parseInt(params.origin as string, 10);

  const [profile, setProfile] = useState<CorridorProfile | null>(null);
  const [series, setSeries] = useState<LaneTimeSeries | null>(null);
  const [notifications, setNotifications] = useState<RawNotification[]>([]);
  const [tradeRows, setTradeRows] = useState<RawTradeRow[]>([]);
  const [methodology, setMethodology] = useState<Record<string, MethodologyEntry>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      api.corridors.full(hs, dest, origin),
      api.corridors.timeSeries(hs, dest, origin),
      api.corridors.notifications(hs, dest, origin),
      api.corridors.tradeRows(hs, dest, origin),
      api.research.methodology(),
    ])
      .then(([prof, ts, notifs, trade, meth]) => {
        setProfile(prof);
        setSeries(ts);
        setNotifications(notifs.notifications);
        setTradeRows(trade.rows);
        const m: Record<string, MethodologyEntry> = {};
        for (const e of meth.entries) m[e.key] = e;
        setMethodology(m);
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, [hs, dest, origin]);

  const periodKeys = useMemo(
    () => (series ? Object.keys(series.dependency_by_period).sort() : []),
    [series]
  );

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <div className="h-9 w-9 animate-spin rounded-full border-2 border-slate-200 border-t-blue-600" />
      </div>
    );
  }
  if (error || !profile || "error" in profile) {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
        {error ?? `Lane not found: ${hs} / ${dest} / ${origin}`}
      </div>
    );
  }

  const dep = profile.dependency && !("error" in profile.dependency) ? profile.dependency : null;
  const haz = profile.hazard ?? null;

  // Read live values for matrix and formula substitution
  function rawValue(key: string): number | undefined {
    if (key === "his" || key === "hdi") return (haz as Record<string, number | undefined> | null)?.[key];
    if (key === "cvs") return profile?.cvs ?? undefined;
    if (key === "crs") return undefined;
    if (!dep) return undefined;
    const d = dep as unknown as Record<string, number | undefined>;
    return d[key];
  }
  function normValue(key: string): number | undefined {
    const p = profile as unknown as Record<string, number | undefined>;
    return p[key];
  }

  return (
    <div className="mx-auto max-w-7xl space-y-5">
      <header className="flex items-start gap-4">
        <Link
          href="/dashboard/lab"
          className="mt-1 rounded-lg p-1.5 hover:bg-slate-100"
          title="Back to workbench"
        >
          <ArrowLeft size={16} />
        </Link>
        <div className="min-w-0 flex-1">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-blue-600/90">
            <FlaskConical size={11} className="mr-1 inline" aria-hidden /> Lane raw view
          </p>
          <h1 className="text-xl font-bold tracking-tight text-slate-900">
            {profile.origin_country} → {profile.destination_country}
          </h1>
          <p className="mt-0.5 text-xs text-slate-500">
            <span className="mr-2 inline-block rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[10px] text-slate-600">
              HS {profile.commodity_hs}
            </span>
            {profile.commodity_name}
          </p>
        </div>
        <Link
          href={`/dashboard/corridors/${hs}/${dest}/${origin}`}
          className="inline-flex items-center gap-1 rounded-md border border-slate-200 bg-white px-2 py-1 text-[11px] text-slate-700 hover:bg-slate-50"
          title="Open the planner-mode Lane report"
        >
          <FileText size={12} aria-hidden /> Planner Lane report
        </Link>
      </header>

      {/* 1. Metric matrix */}
      <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <h2 className="text-sm font-semibold text-slate-900">1. Metric matrix</h2>
        <p className="mt-0.5 text-[11px] text-slate-500">
          Every Section 2-7 metric the system computed for this lane, in raw and (where defined)
          normalised form.
        </p>
        <div className="mt-3 space-y-4">
          {METRIC_MATRIX_KEYS.map((group) => (
            <div key={group.group}>
              <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
                {group.group}
              </p>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-slate-200 text-left text-[10px] uppercase tracking-wide text-slate-500">
                      <th className="py-1 pr-3">Metric</th>
                      <th className="py-1 pr-3 text-right">Raw</th>
                      <th className="py-1 pr-3 text-right">Normalised</th>
                      <th className="py-1 pr-3">Blueprint</th>
                    </tr>
                  </thead>
                  <tbody>
                    {group.metrics.map((m) => {
                      const meth = methodology[m.key];
                      const raw = rawValue(m.key);
                      const norm = m.norm ? normValue(m.norm) : undefined;
                      return (
                        <tr key={m.key} className="border-b border-slate-100">
                          <td className="py-1 pr-3">
                            {meth?.name ?? m.key}{" "}
                            <span className="text-[10px] text-slate-400">({meth?.abbr ?? m.key})</span>
                          </td>
                          <td className="py-1 pr-3 text-right font-mono">
                            {raw != null ? fmt(raw) : "—"}
                          </td>
                          <td className="py-1 pr-3 text-right font-mono">
                            {norm != null ? fmt(norm) : "—"}
                          </td>
                          <td className="py-1 pr-3 text-[10px] text-slate-500">
                            {meth ? `${meth.blueprint_eq} · §${meth.section}` : "—"}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* 2. Period comparison */}
      <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <h2 className="text-sm font-semibold text-slate-900">2. Period comparison</h2>
        <p className="mt-0.5 text-[11px] text-slate-500">
          Section 2 pipeline re-run for every available trade year.
        </p>
        {periodKeys.length === 0 ? (
          <p className="mt-3 text-xs text-slate-500">No multi-period data for this lane.</p>
        ) : (
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-slate-200 text-left text-[10px] uppercase tracking-wide text-slate-500">
                  <th className="py-1 pr-3">Metric</th>
                  {periodKeys.map((p) => (
                    <th key={p} className="py-1 pr-3 text-right">
                      {p}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {PERIOD_KEYS.map((m) => (
                  <tr key={m.key} className="border-b border-slate-100">
                    <td className="py-1 pr-3 font-medium text-slate-700">{m.label}</td>
                    {periodKeys.map((p) => {
                      const row = series!.dependency_by_period[p] as
                        | Record<string, number | undefined>
                        | undefined;
                      const v = row?.[m.key];
                      return (
                        <td key={p} className="py-1 pr-3 text-right font-mono text-slate-800">
                          {typeof v === "number" ? fmt(v) : "—"}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* 3. Raw RASFF notifications */}
      <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <h2 className="text-sm font-semibold text-slate-900">
          3. Raw RASFF notifications ({fmtInt(notifications.length)})
        </h2>
        <p className="mt-0.5 text-[11px] text-slate-500">
          Each row is one RASFF reference contributing to HIS on this lane. Severity weight is{" "}
          W_class × W_risk; the actual HIS sum applies a time-decay factor α<sup>t−t_k</sup>.
        </p>
        {notifications.length === 0 ? (
          <p className="mt-3 text-xs text-slate-500">No notifications on this lane.</p>
        ) : (
          <div className="mt-3 max-h-96 overflow-y-auto">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-white">
                <tr className="border-b border-slate-200 text-left text-[10px] uppercase tracking-wide text-slate-500">
                  <th className="py-1 pr-3">Reference</th>
                  <th className="py-1 pr-3">Period</th>
                  <th className="py-1 pr-3">Hazard category</th>
                  <th className="py-1 pr-3">Classification</th>
                  <th className="py-1 pr-3">Risk decision</th>
                  <th className="py-1 pr-3 text-right">Severity</th>
                </tr>
              </thead>
              <tbody>
                {notifications.map((n) => (
                  <tr key={n.reference} className="border-b border-slate-100">
                    <td className="py-1 pr-3 font-mono text-[11px]">{n.reference}</td>
                    <td className="py-1 pr-3 font-mono text-slate-600">
                      {periodToHuman(n.period)}
                    </td>
                    <td className="py-1 pr-3 text-slate-700">{n.hazard_category || "—"}</td>
                    <td className="py-1 pr-3 text-slate-600">{n.classification || "—"}</td>
                    <td className="py-1 pr-3 text-slate-600">{n.risk_decision || "—"}</td>
                    <td className="py-1 pr-3 text-right font-mono">{fmt(n.severity_weight, 2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* 4. Raw Comtrade rows */}
      <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <h2 className="text-sm font-semibold text-slate-900">
          4. Raw Comtrade rows ({fmtInt(tradeRows.length)})
        </h2>
        <p className="mt-0.5 text-[11px] text-slate-500">
          Bilateral import (M) and export (X) rows from Comtrade where the reporter is the
          destination and the partner is this origin.
        </p>
        {tradeRows.length === 0 ? (
          <p className="mt-3 text-xs text-slate-500">No trade rows for this lane.</p>
        ) : (
          <div className="mt-3 max-h-96 overflow-y-auto">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-white">
                <tr className="border-b border-slate-200 text-left text-[10px] uppercase tracking-wide text-slate-500">
                  <th className="py-1 pr-3">Period</th>
                  <th className="py-1 pr-3">Flow</th>
                  <th className="py-1 pr-3">HS</th>
                  <th className="py-1 pr-3 text-right">Value (USD)</th>
                  <th className="py-1 pr-3 text-right">Net weight (kg)</th>
                  <th className="py-1 pr-3 text-right">Qty</th>
                  <th className="py-1 pr-3">Unit</th>
                </tr>
              </thead>
              <tbody>
                {tradeRows.map((r, i) => (
                  <tr key={i} className="border-b border-slate-100">
                    <td className="py-1 pr-3 font-mono">{r.period}</td>
                    <td className="py-1 pr-3 font-mono">{r.flowCode}</td>
                    <td className="py-1 pr-3 font-mono">{r.cmdCode}</td>
                    <td className="py-1 pr-3 text-right font-mono">{fmtInt(r.primaryValue)}</td>
                    <td className="py-1 pr-3 text-right font-mono">{fmtInt(r.netWgt)}</td>
                    <td className="py-1 pr-3 text-right font-mono">{fmtInt(r.qty)}</td>
                    <td className="py-1 pr-3 text-slate-500">{r.qtyUnitAbbr}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* 5. Formula trace */}
      <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <h2 className="text-sm font-semibold text-slate-900">5. Formula trace</h2>
        <p className="mt-0.5 text-[11px] text-slate-500">
          Numerical substitution of this lane&apos;s values into each Section 2 formula.
        </p>
        <div className="mt-3 space-y-4">
          {dep ? (
            <>
              <Trace
                label="Import reliance (IDR)"
                latex={methodology.idr?.formula_latex ?? ""}
                substitution={`IDR = \\frac{${fmtInt(dep.total_imports_kg ?? 0)}}{${
                  dep.ds_prime != null ? fmt(dep.ds_prime, 0) : "?"
                }} = ${fmt(dep.idr)}`}
              />
              <Trace
                label="Origin country share (OCS)"
                latex={methodology.ocs?.formula_latex ?? ""}
                substitution={`OCS = \\frac{${fmtInt(dep.bilateral_import_kg ?? 0)}}{${fmtInt(
                  dep.total_imports_kg ?? 0
                )}} = ${fmt(dep.ocs)}`}
              />
              <Trace
                label="Supplier concentration (HHI)"
                latex={methodology.hhi?.formula_latex ?? ""}
                substitution={`HHI = \\sum OCS_j^2 = ${fmt(dep.hhi)}`}
              />
              <Trace
                label="Supply criticality (SCI)"
                latex={methodology.sci?.formula_latex ?? ""}
                substitution={`SCI = ${fmt(dep.idr)} \\cdot ${fmt(dep.ocs)} \\cdot (1 + ${fmt(
                  dep.hhi
                )}) = ${fmt(dep.sci)}`}
              />
            </>
          ) : (
            <p className="text-xs text-slate-500">
              No dependency snapshot for this lane — bilateral trade data missing.
            </p>
          )}
        </div>
      </section>
    </div>
  );
}

function Trace({
  label,
  latex,
  substitution,
}: {
  label: string;
  latex: string;
  substitution: string;
}) {
  return (
    <div className="rounded-lg border border-slate-100 bg-slate-50/60 p-3">
      <p className="mb-1 text-[11px] font-semibold text-slate-700">{label}</p>
      {latex && (
        <>
          <p className="text-[10px] uppercase tracking-wide text-slate-500">Definition</p>
          <FormulaBlock latex={latex} />
        </>
      )}
      <p className="mt-2 text-[10px] uppercase tracking-wide text-slate-500">Substituted</p>
      <FormulaBlock latex={substitution} />
    </div>
  );
}

// Suppress unused-import warning for fmtPct (kept for parity with planner imports).
void fmtPct;
