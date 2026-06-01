"use client";

import { Suspense, useState } from "react";
import { FlaskConical } from "lucide-react";
import Coverage from "./_panels/Coverage";
import Distributions from "./_panels/Distributions";
import Cohorts from "./_panels/Cohorts";
import TimeSeries from "./_panels/TimeSeries";
import Methodology from "./_panels/Methodology";

type TabKey =
  | "distributions"
  | "cohorts"
  | "time_series"
  | "coverage"
  | "methodology";

const TABS: { key: TabKey; label: string; description: string }[] = [
  {
    key: "distributions",
    label: "Distributions",
    description: "Histograms with percentile markers across every loaded corridor.",
  },
  {
    key: "cohorts",
    label: "Cohorts",
    description: "Group corridors by chapter, region, or provenance; aggregate any metric.",
  },
  {
    key: "time_series",
    label: "Time series",
    description: "Per-period dependency and per-month RASFF activity for a chosen lane.",
  },
  {
    key: "coverage",
    label: "Coverage",
    description: "Data-quality and ingestion completeness diagnostics.",
  },
  {
    key: "methodology",
    label: "Methodology",
    description: "Every metric: formula, inputs, blueprint reference, source.",
  },
];

function LabInner() {
  const [tab, setTab] = useState<TabKey>("distributions");

  const current = TABS.find((t) => t.key === tab)!;

  return (
    <div className="mx-auto max-w-7xl space-y-5">
      <header>
        <p className="text-[11px] font-semibold uppercase tracking-wider text-blue-600/90">
          Research
        </p>
        <h1 className="flex items-center gap-2 text-xl font-bold tracking-tight text-slate-900">
          <FlaskConical size={18} className="text-blue-600" aria-hidden />
          Research workbench
        </h1>
        <p className="mt-1 max-w-2xl text-sm text-slate-600">
          A sandbox for analysts and methodology reviewers. See the population
          shape, slice by cohort, watch metrics move period to period, audit
          coverage, and read the math behind each score.
        </p>
      </header>

      <nav
        className="flex flex-wrap gap-1 rounded-xl border border-slate-200 bg-white p-1 shadow-sm"
        role="tablist"
      >
        {TABS.map((t) => {
          const active = t.key === tab;
          return (
            <button
              key={t.key}
              type="button"
              role="tab"
              aria-selected={active}
              onClick={() => setTab(t.key)}
              className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${
                active
                  ? "bg-blue-600 text-white shadow-sm"
                  : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
              }`}
            >
              {t.label}
            </button>
          );
        })}
      </nav>

      <p className="-mt-3 text-[11px] text-slate-500">{current.description}</p>

      <section role="tabpanel">
        {tab === "distributions" && <Distributions />}
        {tab === "cohorts" && <Cohorts />}
        {tab === "time_series" && <TimeSeries />}
        {tab === "coverage" && <Coverage />}
        {tab === "methodology" && <Methodology />}
      </section>
    </div>
  );
}

export default function Lab() {
  return (
    <Suspense
      fallback={
        <div className="flex h-64 items-center justify-center">
          <div className="h-9 w-9 animate-spin rounded-full border-2 border-slate-200 border-t-blue-600" />
        </div>
      }
    >
      <LabInner />
    </Suspense>
  );
}
