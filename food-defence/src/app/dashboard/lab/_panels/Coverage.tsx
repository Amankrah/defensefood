"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { CoverageReport } from "@/lib/types";
import { fmtInt } from "@/lib/utils";

function Pct({ num, den }: { num: number; den: number }) {
  if (den <= 0) return <span className="text-slate-400">—</span>;
  return <span className="text-slate-500"> ({((num / den) * 100).toFixed(0)}%)</span>;
}

export default function Coverage() {
  const [data, setData] = useState<CoverageReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.research
      .coverage()
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  if (error) {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
        {error}
      </div>
    );
  }
  if (!data) {
    return (
      <div className="flex h-32 items-center justify-center">
        <div className="h-7 w-7 animate-spin rounded-full border-2 border-slate-200 border-t-blue-600" />
      </div>
    );
  }

  const total = data.corridors_total || 1;

  const stats: { label: string; value: string; suffix?: React.ReactNode; tone?: string }[] = [
    {
      label: "Corridors loaded",
      value: fmtInt(data.corridors_total),
    },
    {
      label: "FAOSTAT-backed",
      value: fmtInt(data.corridors_faostat),
      suffix: <Pct num={data.corridors_faostat} den={data.corridors_total} />,
    },
    {
      label: "Dependency (SCI) populated",
      value: fmtInt(data.corridors_with_dependency),
      suffix: <Pct num={data.corridors_with_dependency} den={data.corridors_total} />,
    },
    {
      label: "Consumption rank (CRS) populated",
      value: fmtInt(data.corridors_with_crs),
      suffix: <Pct num={data.corridors_with_crs} den={total} />,
    },
    {
      label: "Priority score (CVS) populated",
      value: fmtInt(data.corridors_with_cvs),
      suffix: <Pct num={data.corridors_with_cvs} den={total} />,
    },
    {
      label: "Lanes with imports > supply (IDR > 1)",
      value: fmtInt(data.corridors_idr_gt_1),
      suffix: <Pct num={data.corridors_idr_gt_1} den={total} />,
      tone: "text-amber-700",
    },
  ];

  return (
    <div className="space-y-5">
      <section className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-3">
        {stats.map((s) => (
          <div
            key={s.label}
            className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"
          >
            <p className="text-[11px] font-medium text-slate-500">{s.label}</p>
            <p
              className={`mt-1 font-mono text-xl font-semibold tracking-tight ${
                s.tone ?? "text-slate-900"
              }`}
            >
              {s.value}
              {s.suffix && (
                <span className="ml-1 text-xs font-normal">{s.suffix}</span>
              )}
            </p>
          </div>
        ))}
      </section>

      <section className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <h2 className="mb-1 text-sm font-semibold text-slate-900">
            Periods present in source data
          </h2>
          <dl className="mt-2 grid grid-cols-2 gap-3 text-xs">
            <div>
              <dt className="text-slate-500">Trade (Comtrade) years</dt>
              <dd className="mt-0.5 font-mono text-slate-800">
                {data.trade_periods.length
                  ? data.trade_periods.join(", ")
                  : "—"}
              </dd>
            </div>
            <div>
              <dt className="text-slate-500">RASFF months</dt>
              <dd className="mt-0.5 font-mono text-slate-800">
                {data.rasff_periods_count} distinct
                {data.rasff_period_min && data.rasff_period_max ? (
                  <>
                    <br />
                    <span className="text-[11px] text-slate-500">
                      {data.rasff_period_min} → {data.rasff_period_max}
                    </span>
                  </>
                ) : null}
              </dd>
            </div>
            <div>
              <dt className="text-slate-500">FAOSTAT store loaded</dt>
              <dd className="mt-0.5 font-mono text-slate-800">
                {data.faostat_available ? "yes" : "no"}
              </dd>
            </div>
          </dl>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <h2 className="mb-1 text-sm font-semibold text-slate-900">
            Country name mapping gaps
          </h2>
          <p className="mb-3 text-[11px] text-slate-500">
            Names in RASFF that don&apos;t resolve to a UN M49 code — these notifications are
            silently dropped from the corridor set.
          </p>
          <div className="grid grid-cols-2 gap-3 text-xs">
            <div>
              <p className="font-medium text-slate-700">
                Origins ({data.unmapped_origins.length})
              </p>
              <ul className="mt-1 max-h-40 space-y-0.5 overflow-y-auto pr-1 text-slate-600">
                {data.unmapped_origins.slice(0, 30).map((o) => (
                  <li key={o} className="font-mono text-[11px]">
                    {o}
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <p className="font-medium text-slate-700">
                Destinations ({data.unmapped_destinations.length})
              </p>
              <ul className="mt-1 max-h-40 space-y-0.5 overflow-y-auto pr-1 text-slate-600">
                {data.unmapped_destinations.slice(0, 30).map((d) => (
                  <li key={d} className="font-mono text-[11px]">
                    {d}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      </section>

      <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <h2 className="mb-1 text-sm font-semibold text-slate-900">
          FAOSTAT coverage by HS chapter
        </h2>
        <p className="mb-3 text-[11px] text-slate-500">
          For each commodity chapter, how many corridors got production data
          from FAOSTAT vs. fell back to the trade-only DS&prime; proxy vs.
          have no bilateral trade footprint at all.
        </p>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-slate-200 text-left text-[10px] uppercase tracking-wide text-slate-500">
                <th className="py-1.5 pr-3">Chapter</th>
                <th className="py-1.5 pr-3 text-right">Corridors</th>
                <th className="py-1.5 pr-3 text-right">FAOSTAT</th>
                <th className="py-1.5 pr-3 text-right">Trade-only</th>
                <th className="py-1.5 pr-3 text-right">No trade</th>
                <th className="py-1.5 pr-3">Mix</th>
              </tr>
            </thead>
            <tbody>
              {data.by_hs_chapter.map((row) => {
                const total = row.total || 1;
                const fa = (row.faostat / total) * 100;
                const tr = (row.trade_only / total) * 100;
                const nt = (row.no_trade / total) * 100;
                return (
                  <tr key={row.chapter} className="border-b border-slate-100">
                    <td className="py-1.5 pr-3 font-mono">{row.chapter}</td>
                    <td className="py-1.5 pr-3 text-right font-mono">{row.total}</td>
                    <td className="py-1.5 pr-3 text-right font-mono text-emerald-700">
                      {row.faostat}
                    </td>
                    <td className="py-1.5 pr-3 text-right font-mono text-amber-700">
                      {row.trade_only}
                    </td>
                    <td className="py-1.5 pr-3 text-right font-mono text-slate-500">
                      {row.no_trade}
                    </td>
                    <td className="py-1.5 pr-3">
                      <div className="flex h-2 w-32 overflow-hidden rounded-full bg-slate-100">
                        <div
                          className="bg-emerald-500"
                          style={{ width: `${fa}%` }}
                          title={`FAOSTAT ${fa.toFixed(0)}%`}
                        />
                        <div
                          className="bg-amber-400"
                          style={{ width: `${tr}%` }}
                          title={`Trade-only ${tr.toFixed(0)}%`}
                        />
                        <div
                          className="bg-slate-300"
                          style={{ width: `${nt}%` }}
                          title={`No trade ${nt.toFixed(0)}%`}
                        />
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
