"use client";

import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import type { MethodologyEntry } from "@/lib/types";
import FormulaBlock from "@/components/shared/FormulaBlock";

const SECTION_ORDER = [
  { prefix: "2", title: "Section 2 — Commodity dependency" },
  { prefix: "3", title: "Section 3 — Consumption" },
  { prefix: "4", title: "Section 4 — Hazard signal" },
  { prefix: "5", title: "Section 5 — Trade-flow anomalies" },
  { prefix: "6", title: "Section 6 — Network" },
  { prefix: "7", title: "Section 7 — Composite priority score" },
];

export default function Methodology() {
  const [entries, setEntries] = useState<MethodologyEntry[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.research
      .methodology()
      .then((r) => setEntries(r.entries))
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  const bySection = useMemo(() => {
    const out: Record<string, MethodologyEntry[]> = {};
    for (const e of entries) {
      const head = e.section.split(".")[0];
      out[head] = out[head] ?? [];
      out[head].push(e);
    }
    return out;
  }, [entries]);

  if (error) {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
        {error}
      </div>
    );
  }
  if (!entries.length) {
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
          Each metric the system computes is listed below with its blueprint
          reference, mathematical definition, and the Rust source that
          implements it. Numbers in the rest of the UI come straight from these
          formulas — no hidden steps.
        </p>
      </section>

      {SECTION_ORDER.map((s) => {
        const items = bySection[s.prefix];
        if (!items || !items.length) return null;
        return (
          <section key={s.prefix} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
            <h2 className="mb-3 text-sm font-semibold text-slate-900">{s.title}</h2>
            <ul className="space-y-4">
              {items.map((e) => (
                <li key={e.key} className="rounded-lg border border-slate-100 bg-slate-50/60 p-3">
                  <div className="mb-1 flex flex-wrap items-baseline justify-between gap-2">
                    <p className="text-sm font-semibold text-slate-900">
                      {e.name}{" "}
                      <span className="ml-1 font-normal text-[10px] uppercase tracking-wide text-slate-400">
                        ({e.abbr})
                      </span>
                    </p>
                    <p className="text-[10px] text-slate-500">
                      Blueprint {e.blueprint_eq} · §{e.section}
                    </p>
                  </div>
                  <p className="mb-3 text-xs leading-snug text-slate-700">{e.definition}</p>
                  <FormulaBlock latex={e.formula_latex} />
                  <div className="mt-3 grid grid-cols-1 gap-2 text-[11px] sm:grid-cols-2">
                    <div>
                      <p className="font-medium text-slate-600">Inputs</p>
                      <ul className="mt-0.5 list-disc pl-4 text-slate-600">
                        {e.inputs.map((inp) => (
                          <li key={inp}>{inp}</li>
                        ))}
                      </ul>
                    </div>
                    <div>
                      <p className="font-medium text-slate-600">Source</p>
                      <p className="mt-0.5 font-mono text-[10px] text-slate-600 break-all">
                        {e.source}
                      </p>
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          </section>
        );
      })}
    </div>
  );
}
