"use client";

import { ChevronDown, ChevronRight, Calculator } from "lucide-react";
import FormulaBlock from "@/components/shared/FormulaBlock";
import { fmt, fmtInt } from "@/lib/utils";
import type { DependencyMetrics } from "@/lib/types";

interface LaneWalkthroughProps {
  /** Section 2 metrics for the corridor (from /full -> dependency block). */
  dependency: DependencyMetrics | null;
  /** Optional CVS so the walk-through can show the final score. */
  cvs?: number | null;
}

/**
 * Step-by-step "How we computed this lane's score" panel.
 *
 * Renders the Section 2 formula chain with this corridor's actual numbers
 * substituted, so the user can trace P + M − X → DS′ → IDR → … → SCI
 * exactly the way the blueprint walks through the flaxseed example.
 *
 * Collapsed by default — non-experts can ignore it; researchers can expand.
 */
export default function LaneWalkthrough({ dependency, cvs }: LaneWalkthroughProps) {
  if (!dependency || "error" in dependency) {
    return null;
  }

  const dep = dependency;
  const p = dep.production_kg ?? 0;
  const m = dep.total_imports_kg ?? 0;
  const x =
    dep.production_kg != null &&
    dep.total_imports_kg != null &&
    dep.ds_prime != null
      ? p + m - dep.ds_prime  // X = P + M - DS'
      : null;
  const mij = dep.bilateral_import_kg ?? 0;
  const dsPrime = dep.ds_prime ?? 0;

  return (
    <details className="group rounded-2xl border border-slate-200 bg-white shadow-sm">
      <summary className="flex w-full cursor-pointer list-none items-center justify-between px-5 py-3 text-left [&::-webkit-details-marker]:hidden">
        <div className="flex items-center gap-2">
          <ChevronRight
            size={16}
            className="text-slate-500 group-open:hidden"
            aria-hidden
          />
          <ChevronDown
            size={16}
            className="hidden text-slate-500 group-open:block"
            aria-hidden
          />
          <Calculator size={15} className="text-blue-600" aria-hidden />
          <span className="text-sm font-semibold text-slate-900">
            How we computed this score
          </span>
        </div>
        <span className="text-[11px] text-slate-500 group-open:hidden">
          Show step-by-step math
        </span>
        <span className="hidden text-[11px] text-slate-500 group-open:inline">
          Hide step-by-step math
        </span>
      </summary>

      <div className="space-y-4 border-t border-slate-100 px-5 py-4">
          <p className="text-[11px] text-slate-600">
            Each step below uses this lane&apos;s actual values. The formulas
            match Section&nbsp;2 of the blueprint.
          </p>

          {/* Step 1: DS' */}
          <Step
            label="Step 1 — Apparent domestic supply"
            abbr="DS′"
          >
            <FormulaBlock latex={"DS' = P + M - X"} />
            <FormulaBlock
              latex={`DS' = ${fmtInt(p)} + ${fmtInt(m)} - ${
                x != null ? fmtInt(x) : "X"
              } = ${fmtInt(dsPrime)}\\;\\text{kg}`}
            />
            <p className="mt-1 text-[11px] text-slate-600">
              Apparent supply = how much of this commodity is theoretically
              available in {dep.production_kg != null ? "the destination" : "this market"}{" "}
              after counting domestic production and net trade.
            </p>
          </Step>

          {/* Step 2: IDR */}
          <Step label="Step 2 — Import reliance" abbr="IDR">
            <FormulaBlock latex={"IDR = \\frac{M}{DS'}"} />
            <FormulaBlock
              latex={`IDR = \\frac{${fmtInt(m)}}{${fmtInt(dsPrime)}} = ${fmt(dep.idr ?? 0)}`}
            />
            <p className="mt-1 text-[11px] text-slate-600">
              Share of apparent supply that comes from imports.
              {dep.idr_gt_1 && (
                <>
                  {" "}
                  IDR &gt; 1 means imports exceed apparent supply — this lane
                  is either a transit hub or its production data is missing.
                </>
              )}
            </p>
          </Step>

          {/* Step 3: OCS */}
          <Step label="Step 3 — Origin country share" abbr="OCS">
            <FormulaBlock latex={"OCS = \\frac{M_{ij}}{M}"} />
            <FormulaBlock
              latex={`OCS = \\frac{${fmtInt(mij)}}{${fmtInt(m)}} = ${fmt(dep.ocs ?? 0)}`}
            />
            <p className="mt-1 text-[11px] text-slate-600">
              {((dep.ocs ?? 0) * 100).toFixed(1)}% of this destination&apos;s
              imports come from this single origin.
            </p>
          </Step>

          {/* Step 4: BDI */}
          <Step label="Step 4 — Bilateral dependency" abbr="BDI">
            <FormulaBlock latex={"BDI = IDR \\cdot OCS"} />
            <FormulaBlock
              latex={`BDI = ${fmt(dep.idr ?? 0)} \\cdot ${fmt(dep.ocs ?? 0)} = ${fmt(dep.bdi ?? 0)}`}
            />
            <p className="mt-1 text-[11px] text-slate-600">
              Share of apparent supply sourced specifically from this origin.
            </p>
          </Step>

          {/* Step 5: HHI */}
          <Step label="Step 5 — Supplier concentration" abbr="HHI">
            <FormulaBlock latex={"HHI = \\sum_{j} OCS_j^2"} />
            <FormulaBlock latex={`HHI = ${fmt(dep.hhi ?? 0)}`} />
            <p className="mt-1 text-[11px] text-slate-600">
              {(dep.hhi ?? 0) >= 0.25
                ? "Above the 0.25 antitrust threshold — supplier base is concentrated."
                : "Below the 0.25 antitrust threshold — supplier base is diversified."}
            </p>
          </Step>

          {/* Step 6: SCI */}
          <Step label="Step 6 — Supply criticality" abbr="SCI">
            <FormulaBlock latex={"SCI = IDR \\cdot OCS \\cdot (1 + HHI)"} />
            <FormulaBlock
              latex={`SCI = ${fmt(dep.idr ?? 0)} \\cdot ${fmt(dep.ocs ?? 0)} \\cdot (1 + ${fmt(dep.hhi ?? 0)}) = ${fmt(dep.sci ?? 0)}`}
            />
            <p className="mt-1 text-[11px] text-slate-600">
              SCI sits in [0, 2]. Higher means more structurally exposed; the
              (1 + HHI) factor amplifies when the wider supplier market is also
              concentrated.
            </p>
          </Step>

          {cvs != null && (
            <Step label="Step 7 — Priority score" abbr="CVS">
              <FormulaBlock
                latex={
                  "CVS = \\mathrm{norm}(SCI) \\cdot \\mathrm{norm}(CRS) \\cdot (\\text{hazard amplifier})"
                }
              />
              <FormulaBlock latex={`CVS = ${fmt(cvs)}`} />
              <p className="mt-1 text-[11px] text-slate-600">
                Final ranking number, rescaled to 0–1. Blends supply
                criticality, consumption demand, and hazard signals.
              </p>
            </Step>
          )}
        </div>
    </details>
  );
}

function Step({
  label,
  abbr,
  children,
}: {
  label: string;
  abbr: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-lg border border-slate-100 bg-slate-50/60 p-3">
      <p className="mb-2 text-xs font-semibold text-slate-700">
        {label}{" "}
        <span className="ml-1 font-normal text-[10px] uppercase tracking-wide text-slate-400">
          ({abbr})
        </span>
      </p>
      {children}
    </div>
  );
}
