"use client";

import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import { X, BookOpen } from "lucide-react";
import { METRIC, type MetricKey } from "@/lib/labels";

interface GlossaryCtx {
  open: () => void;
  close: () => void;
  toggle: () => void;
}

const ctx = createContext<GlossaryCtx>({
  open: () => {},
  close: () => {},
  toggle: () => {},
});

export function useGlossary() {
  return useContext(ctx);
}

/** Order entries by blueprint section for predictable reading. */
const SECTION_ORDER: { title: string; keys: MetricKey[] }[] = [
  {
    title: "Priority score",
    keys: ["cvs"],
  },
  {
    title: "Supply dependency (Section 2)",
    keys: ["sci", "sci_norm", "idr", "ocs", "bdi", "hhi", "ssr", "ds_prime"],
  },
  {
    title: "Consumption demand (Section 3)",
    keys: ["crs", "crs_norm"],
  },
  {
    title: "Hazard signals (Section 4)",
    keys: ["his", "his_norm", "hdi", "dgi"],
  },
  {
    title: "Trade-flow anomalies (Section 5)",
    keys: ["z_uv", "mtd", "delta_hhi"],
  },
  {
    title: "Country-level (Section 6)",
    keys: ["acep", "orps"],
  },
];

export function GlossaryProvider({ children }: { children: ReactNode }) {
  const [isOpen, setOpen] = useState(false);
  const value: GlossaryCtx = {
    open: useCallback(() => setOpen(true), []),
    close: useCallback(() => setOpen(false), []),
    toggle: useCallback(() => setOpen((v) => !v), []),
  };

  return (
    <ctx.Provider value={value}>
      {children}
      {isOpen && (
        <div className="fixed inset-0 z-50">
          <button
            type="button"
            aria-label="Close glossary"
            onClick={value.close}
            className="absolute inset-0 bg-slate-950/40 backdrop-blur-sm"
          />
          <aside
            role="dialog"
            aria-label="Glossary of metrics"
            className="absolute right-0 top-0 bottom-0 flex w-full max-w-md flex-col border-l border-slate-200 bg-white shadow-2xl"
          >
            <header className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
              <div className="flex items-center gap-2">
                <BookOpen size={16} className="text-blue-600" aria-hidden />
                <h2 className="text-sm font-semibold text-slate-900">Glossary</h2>
              </div>
              <button
                type="button"
                onClick={value.close}
                className="rounded-md p-1 text-slate-500 hover:bg-slate-100 hover:text-slate-800"
                aria-label="Close"
              >
                <X size={16} aria-hidden />
              </button>
            </header>
            <div className="flex-1 overflow-y-auto px-5 py-4 text-sm">
              <p className="mb-4 text-xs text-slate-500">
                Definitions follow the project blueprint. Numbers in this app are ranking aids,
                not enforcement thresholds.
              </p>
              {SECTION_ORDER.map((section) => (
                <section key={section.title} className="mb-5">
                  <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                    {section.title}
                  </h3>
                  <dl className="space-y-2">
                    {section.keys.map((k) => {
                      const m = METRIC[k];
                      return (
                        <div
                          key={k}
                          className="rounded-md border border-slate-100 bg-slate-50/70 px-3 py-2"
                        >
                          <dt className="text-xs font-semibold text-slate-800">
                            {m.long}{" "}
                            <span className="font-normal text-[10px] uppercase tracking-wide text-slate-400">
                              ({m.short})
                            </span>
                          </dt>
                          <dd className="mt-0.5 text-[12px] leading-snug text-slate-600">
                            {m.definition}
                          </dd>
                        </div>
                      );
                    })}
                  </dl>
                </section>
              ))}
            </div>
            <footer className="border-t border-slate-100 px-5 py-3 text-[10px] text-slate-400">
              For full mathematical definitions, see the project blueprint PDF.
            </footer>
          </aside>
        </div>
      )}
    </ctx.Provider>
  );
}
