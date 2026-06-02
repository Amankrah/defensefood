"use client";

import { useMemo } from "react";
import { useMethodologyCatalogue } from "@/lib/methodology";
import type { MethodologyEntry, MethodologyScaleBand } from "@/lib/types";
import { bandClasses } from "@/lib/interpret";
import FormulaBlock from "@/components/shared/FormulaBlock";

const SECTION_ORDER = [
  { prefix: "2", title: "Section 2 — Commodity dependency" },
  { prefix: "3", title: "Section 3 — Consumption" },
  { prefix: "4", title: "Section 4 — Hazard signal" },
  { prefix: "5", title: "Section 5 — Trade-flow anomalies" },
  { prefix: "6", title: "Section 6 — Network" },
  { prefix: "7", title: "Section 7 — Composite priority score" },
];

// Blueprint's worked example numbers (Sec. 2.7, flaxseed France → Belgium).
const WORKED_EXAMPLE = {
  ds_prime: 11000,
  idr: 1.0909,
  ocs: 0.6667,
  bdi: 0.7273,
  hhi: 0.4896,
  sci: 1.0833,
} as const;

export default function Methodology() {
  const catalogue = useMethodologyCatalogue();

  const bySection = useMemo(() => {
    if (!catalogue) return {} as Record<string, MethodologyEntry[]>;
    const out: Record<string, MethodologyEntry[]> = {};
    for (const e of Object.values(catalogue)) {
      const head = e.section.split(".")[0];
      out[head] = out[head] ?? [];
      out[head].push(e);
    }
    return out;
  }, [catalogue]);

  if (!catalogue) {
    return (
      <div className="flex h-32 items-center justify-center">
        <div className="h-7 w-7 animate-spin rounded-full border-2 border-slate-200 border-t-blue-600" />
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <h2 className="text-sm font-semibold text-slate-900">How to read this page</h2>
        <p className="mt-1 text-xs text-slate-600">
          Each metric in the system is listed below with its blueprint
          reference, the formula in plain English, the math, the scale you
          should read your number against, and a worked example from the
          blueprint where applicable. Numbers in the rest of the UI come
          straight from these formulas — no hidden steps.
        </p>
      </section>

      {SECTION_ORDER.map((s) => {
        const items = bySection[s.prefix];
        if (!items || !items.length) return null;
        return (
          <section
            key={s.prefix}
            className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"
          >
            <h2 className="mb-3 text-sm font-semibold text-slate-900">{s.title}</h2>
            <ul className="space-y-4">
              {items.map((e) => (
                <li
                  key={e.key}
                  className="rounded-lg border border-slate-100 bg-slate-50/60 p-3"
                >
                  <MethodologyCard entry={e} />
                </li>
              ))}
            </ul>
          </section>
        );
      })}
    </div>
  );
}

function MethodologyCard({ entry }: { entry: MethodologyEntry }) {
  const worked =
    entry.key in WORKED_EXAMPLE
      ? (WORKED_EXAMPLE as Record<string, number>)[entry.key]
      : null;

  return (
    <>
      <div className="mb-1 flex flex-wrap items-baseline justify-between gap-2">
        <p className="text-sm font-semibold text-slate-900">
          {entry.name}{" "}
          <span className="ml-1 font-normal text-[10px] uppercase tracking-wide text-slate-400">
            ({entry.abbr})
          </span>
        </p>
        <p className="text-[10px] text-slate-500">
          Blueprint {entry.blueprint_eq} · §{entry.section}
        </p>
      </div>

      <p className="mb-3 text-xs leading-snug text-slate-700">{entry.definition}</p>

      {entry.formula_plain && (
        <div className="mb-3 rounded-md bg-white px-3 py-2">
          <p className="mb-0.5 text-[10px] font-medium uppercase tracking-wide text-slate-500">
            In plain English
          </p>
          <p className="text-[12px] text-slate-700">{entry.formula_plain}</p>
        </div>
      )}

      <FormulaBlock latex={entry.formula_latex} />

      {entry.scale && entry.scale.length > 0 && (
        <ScaleStrip bands={entry.scale} markValue={worked} />
      )}

      <div className="mt-3 grid grid-cols-1 gap-2 text-[11px] sm:grid-cols-2">
        <div>
          <p className="font-medium text-slate-600">Inputs</p>
          <ul className="mt-0.5 list-disc pl-4 text-slate-600">
            {entry.inputs.map((inp) => (
              <li key={inp}>{inp}</li>
            ))}
          </ul>
        </div>
        <div>
          <p className="font-medium text-slate-600">Source</p>
          <p className="mt-0.5 font-mono text-[10px] text-slate-600 break-all">
            {entry.source}
          </p>
        </div>
      </div>

      {entry.when_matters && (
        <p className="mt-3 rounded-md border border-slate-200 bg-white px-3 py-2 text-[11px] text-slate-700">
          <span className="font-medium text-slate-800">When it matters:</span>{" "}
          {entry.when_matters}
        </p>
      )}

      {worked != null && (
        <WorkedExample entry={entry} workedValue={worked} />
      )}
    </>
  );
}

function ScaleStrip({
  bands,
  markValue,
}: {
  bands: MethodologyScaleBand[];
  markValue: number | null;
}) {
  return (
    <div className="mt-3">
      <p className="mb-1 text-[10px] font-medium uppercase tracking-wide text-slate-500">
        Scale
      </p>
      <ul className="space-y-1">
        {bands.map((b, i) => {
          const c = bandClasses(b.band);
          const hit =
            markValue != null && markValue >= b.min && markValue < b.max;
          return (
            <li
              key={`${b.label}-${i}`}
              className={`flex items-center justify-between gap-2 rounded-md border px-2 py-1 text-[11px] ${c.bg} ${c.border} ${
                hit ? "ring-2 ring-blue-300" : ""
              }`}
            >
              <span className="flex items-baseline gap-2">
                <span className="font-mono text-[10px] text-slate-500">
                  {fmtBound(b.min)} – {fmtBound(b.max)}
                </span>
                <span className={`font-semibold ${c.text}`}>{b.label}</span>
              </span>
              <span className="hidden text-slate-600 sm:block">{b.advice}</span>
              {hit && (
                <span className="rounded-full bg-blue-600 px-1.5 py-0.5 text-[9px] font-medium text-white">
                  example
                </span>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function WorkedExample({
  entry,
  workedValue,
}: {
  entry: MethodologyEntry;
  workedValue: number;
}) {
  // Blueprint Sec. 2.7 — France → Belgium flaxseed, RASFF 2026.0129.
  // P = 500t, M = 12000t, X = 1500t, M_FR = 8000t,
  // all-origin import shares = [8000, 2000, 1500, 500]
  const subs: Record<string, string> = {
    ds_prime: "DS' = 500 + 12{,}000 - 1{,}500 = 11{,}000\\;\\text{t}",
    idr: "IDR = \\frac{12{,}000}{11{,}000} = 1.0909",
    ocs: "OCS = \\frac{8{,}000}{12{,}000} = 0.6667",
    bdi: "BDI = 1.0909 \\cdot 0.6667 = 0.7273",
    hhi: "HHI = \\frac{8000^2 + 2000^2 + 1500^2 + 500^2}{12000^2} = 0.4896",
    sci: "SCI = 1.0909 \\cdot 0.6667 \\cdot (1 + 0.4896) = 1.0833",
  };
  const sub = subs[entry.key];
  if (!sub) return null;
  return (
    <div className="mt-3 rounded-md border border-blue-100 bg-blue-50/40 px-3 py-2">
      <p className="mb-1 text-[10px] font-medium uppercase tracking-wide text-blue-700">
        Worked example — blueprint Sec. 2.7
      </p>
      <p className="mb-2 text-[11px] text-slate-700">
        Flaxseed corridor France → Belgium (RASFF 2026.0129). Inputs:
        P = 500 t, M = 12,000 t, X = 1,500 t, M<sub>FR</sub> = 8,000 t.
      </p>
      <FormulaBlock latex={sub} />
      <p className="mt-1 text-[10px] text-slate-500">
        Engine output for this lane: <span className="font-mono">{workedValue}</span>.
      </p>
    </div>
  );
}

function fmtBound(v: number): string {
  if (Math.abs(v) >= 1e9) return v < 0 ? "−∞" : "∞";
  if (Math.abs(v) >= 100) return v.toFixed(0);
  return v.toFixed(2);
}
