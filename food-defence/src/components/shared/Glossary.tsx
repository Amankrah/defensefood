"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { BookOpen, X } from "lucide-react";
import { useMethodologyCatalogue } from "@/lib/methodology";
import type { MethodologyEntry, MethodologyScaleBand } from "@/lib/types";
import { bandClasses } from "@/lib/interpret";

interface GlossaryCtx {
  open: (anchorKey?: string) => void;
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

/** Section grouping for the catalogue (matches methodology entry sections). */
const SECTION_GROUPS: { title: string; prefix: string }[] = [
  { title: "Priority score (Section 7)", prefix: "7" },
  { title: "Supply dependency (Section 2)", prefix: "2" },
  { title: "Consumption (Section 3)", prefix: "3" },
  { title: "Hazard signals (Section 4)", prefix: "4" },
  { title: "Trade-flow anomalies (Section 5)", prefix: "5" },
  { title: "Network / country-level (Section 6)", prefix: "6" },
];

function MetricCard({ entry }: { entry: MethodologyEntry }) {
  return (
    <article
      id={`metric-${entry.key}`}
      className="scroll-mt-4 rounded-lg border border-slate-200 bg-white p-4 shadow-sm"
    >
      <header className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
        <h4 className="text-sm font-semibold text-slate-900">
          {entry.name}{" "}
          <span className="ml-1 font-normal text-[10px] uppercase tracking-wide text-slate-400">
            ({entry.abbr})
          </span>
        </h4>
        <p className="text-[10px] text-slate-500">
          Blueprint {entry.blueprint_eq} · §{entry.section}
        </p>
      </header>

      <p className="text-[12px] leading-snug text-slate-700">{entry.definition}</p>

      {entry.formula_plain && (
        <div className="mt-3 rounded-md bg-slate-50 px-3 py-2">
          <p className="mb-0.5 text-[10px] font-medium uppercase tracking-wide text-slate-500">
            How it&apos;s computed
          </p>
          <p className="text-[12px] text-slate-700">{entry.formula_plain}</p>
        </div>
      )}

      {entry.scale && entry.scale.length > 0 && <ScaleLegend bands={entry.scale} />}

      {entry.when_matters && (
        <div className="mt-3">
          <p className="mb-0.5 text-[10px] font-medium uppercase tracking-wide text-slate-500">
            When it matters
          </p>
          <p className="text-[12px] leading-snug text-slate-700">{entry.when_matters}</p>
        </div>
      )}

      {entry.related && entry.related.length > 0 && (
        <RelatedMetrics keys={entry.related} />
      )}
    </article>
  );
}

function ScaleLegend({ bands }: { bands: MethodologyScaleBand[] }) {
  return (
    <div className="mt-3">
      <p className="mb-1 text-[10px] font-medium uppercase tracking-wide text-slate-500">
        How to read your number
      </p>
      <ul className="space-y-1 text-[11px]">
        {bands.map((b, i) => {
          const c = bandClasses(b.band);
          return (
            <li
              key={`${b.label}-${i}`}
              className={`flex items-start gap-2 rounded-md border px-2 py-1 ${c.bg} ${c.border}`}
            >
              <span className={`mt-0.5 inline-block h-2 w-2 shrink-0 rounded-full ${c.text.replace("text-", "bg-")}`} aria-hidden />
              <span className="min-w-0">
                <span className="font-mono text-[10px] text-slate-500">
                  {formatBandRange(b.min, b.max)}
                </span>{" "}
                <span className={`font-semibold ${c.text}`}>{b.label}</span>
                <span className="block text-slate-700">{b.advice}</span>
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function formatBandRange(min: number, max: number): string {
  const lo = Math.abs(min) >= 1e9 ? "−∞" : min.toFixed(2);
  const hi = Math.abs(max) >= 1e9 ? "∞" : max.toFixed(2);
  return `${lo} – ${hi}`;
}

function RelatedMetrics({ keys }: { keys: string[] }) {
  const glossary = useGlossary();
  return (
    <div className="mt-3 flex flex-wrap items-center gap-1.5">
      <span className="text-[10px] font-medium uppercase tracking-wide text-slate-500">
        Related:
      </span>
      {keys.map((k) => (
        <button
          key={k}
          type="button"
          onClick={() => glossary.open(k)}
          className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[11px] font-medium text-slate-700 hover:border-blue-300 hover:bg-blue-50 hover:text-blue-700"
        >
          {k}
        </button>
      ))}
    </div>
  );
}

export function GlossaryProvider({ children }: { children: ReactNode }) {
  const [isOpen, setOpen] = useState(false);
  const [targetKey, setTargetKey] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const catalogue = useMethodologyCatalogue();

  const open = useCallback((key?: string) => {
    setTargetKey(key ?? null);
    setOpen(true);
  }, []);
  const close = useCallback(() => setOpen(false), []);
  const toggle = useCallback(() => setOpen((v) => !v), []);

  // Scroll to the requested metric after the slide-over has rendered.
  useEffect(() => {
    if (!isOpen || !targetKey) return;
    const t = setTimeout(() => {
      const el = scrollRef.current?.querySelector<HTMLElement>(`#metric-${targetKey}`);
      if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 50);
    return () => clearTimeout(t);
  }, [isOpen, targetKey, catalogue]);

  const value: GlossaryCtx = { open, close, toggle };

  // Build grouped sections from the live catalogue.
  const grouped = catalogue
    ? SECTION_GROUPS.map((g) => ({
        title: g.title,
        entries: Object.values(catalogue).filter((e) =>
          e.section.startsWith(g.prefix)
        ),
      })).filter((g) => g.entries.length > 0)
    : [];

  return (
    <ctx.Provider value={value}>
      {children}
      {isOpen && (
        <div className="fixed inset-0 z-50">
          <button
            type="button"
            aria-label="Close glossary"
            onClick={close}
            className="absolute inset-0 bg-slate-950/40 backdrop-blur-sm"
          />
          <aside
            role="dialog"
            aria-label="Glossary of metrics"
            className="absolute right-0 top-0 bottom-0 flex w-full max-w-xl flex-col border-l border-slate-200 bg-white shadow-2xl"
          >
            <header className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
              <div className="flex items-center gap-2">
                <BookOpen size={16} className="text-blue-600" aria-hidden />
                <h2 className="text-sm font-semibold text-slate-900">
                  Methodology &amp; metric glossary
                </h2>
              </div>
              <button
                type="button"
                onClick={close}
                className="rounded-md p-1 text-slate-500 hover:bg-slate-100 hover:text-slate-800"
                aria-label="Close"
              >
                <X size={16} aria-hidden />
              </button>
            </header>
            <div ref={scrollRef} className="flex-1 overflow-y-auto px-5 py-4">
              <p className="mb-4 text-xs text-slate-500">
                Definitions follow the project blueprint. Use the scale legends
                to read your numbers; everything here is a ranking aid, not an
                enforcement threshold.
              </p>
              {!catalogue && (
                <p className="text-xs text-slate-500">Loading methodology…</p>
              )}
              {grouped.map((group) => (
                <section key={group.title} className="mb-6">
                  <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                    {group.title}
                  </h3>
                  <div className="space-y-3">
                    {group.entries.map((entry) => (
                      <MetricCard key={entry.key} entry={entry} />
                    ))}
                  </div>
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
