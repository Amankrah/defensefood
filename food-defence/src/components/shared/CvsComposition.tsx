"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight, Calculator } from "lucide-react";
import FormulaBlock from "@/components/shared/FormulaBlock";
import { fmt } from "@/lib/utils";
import type { CorridorProfile } from "@/lib/types";

interface CvsCompositionProps {
  /** Full corridor profile from /corridors/.../full. */
  profile: CorridorProfile;
  /** Optional weights from ScoringConfig (default 1,1,1). */
  weights?: { w_h?: number; w_p?: number; w_sc?: number };
}

/**
 * Walks through the Slice E1 masked-hybrid CVS for this corridor:
 *
 *   base = SCI_norm × CRS_norm  (or × 0.5 fallback when CRS missing)
 *   amp  = 1 + Σ_active w·v     where active terms ⊆ {HIS, PAS, SCCS}
 *   max  = 1 + Σ_active w
 *   CVS  = base × amp / max
 *
 * Inactive amplifier terms are shown struck-through with an "absent" tag so
 * the user sees why the divisor shrank. The arithmetic substitutes the
 * lane's own normalised values; the final result matches the displayed CVS
 * to within numerical precision.
 */
export default function CvsComposition({
  profile,
  weights,
}: CvsCompositionProps) {
  const [open, setOpen] = useState(false);

  const sciNorm = profile.sci_norm;
  const crsNorm = profile.crs_norm;
  const hisNorm = profile.his_norm;
  // pas_norm / sccs_norm aren't in the CorridorProfile type yet — read defensively.
  const dynamic = profile as unknown as {
    pas_norm?: number | null;
    sccs_norm?: number | null;
  };
  const pasNorm = dynamic.pas_norm ?? null;
  const sccsNorm = dynamic.sccs_norm ?? null;

  if (sciNorm == null || hisNorm == null) {
    return null;
  }

  const wH = weights?.w_h ?? 1.0;
  const wP = weights?.w_p ?? 1.0;
  const wSc = weights?.w_sc ?? 1.0;

  const hasCrs = crsNorm != null;
  const crsFactor = hasCrs ? crsNorm! : 0.5;
  const base = sciNorm * crsFactor;

  const terms = [
    { key: "his", label: "Hazard intensity (HIS)", value: hisNorm, weight: wH, active: true },
    {
      key: "pas",
      label: "Price anomaly (PAS)",
      value: pasNorm,
      weight: wP,
      active: pasNorm != null,
    },
    {
      key: "sccs",
      label: "Supply chain complexity (SCCS)",
      value: sccsNorm,
      weight: wSc,
      active: sccsNorm != null,
    },
  ];

  const activeNum = terms
    .filter((t) => t.active)
    .reduce((s, t) => s + t.weight * (t.value as number), 0);
  const activeWeightSum = terms
    .filter((t) => t.active)
    .reduce((s, t) => s + t.weight, 0);
  const amp = 1 + activeNum;
  const maxAmp = 1 + activeWeightSum;
  const cvsComputed = maxAmp > 0 ? (base * amp) / maxAmp : 0;

  return (
    <section className="rounded-2xl border border-slate-200 bg-white shadow-sm">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between px-5 py-3 text-left"
        aria-expanded={open}
      >
        <div className="flex items-center gap-2">
          {open ? (
            <ChevronDown size={16} className="text-slate-500" aria-hidden />
          ) : (
            <ChevronRight size={16} className="text-slate-500" aria-hidden />
          )}
          <Calculator size={15} className="text-purple-600" aria-hidden />
          <span className="text-sm font-semibold text-slate-900">
            How this CVS was built
          </span>
        </div>
        <span className="text-[11px] text-slate-500">
          {open ? "Hide composition math" : "Show composition math"}
        </span>
      </button>

      {open && (
        <div className="space-y-3 border-t border-slate-100 px-5 py-4">
          <p className="text-[11px] text-slate-600">
            CVS = (SCI<sub>norm</sub> × CRS<sub>norm</sub>) × (1 + Σ w·signal) / (1 + Σ w).
            Terms whose normalised value is missing for this lane drop out of
            both the numerator and the divisor (Slice E1 fix).
          </p>

          <div className="rounded-lg border border-slate-100 bg-slate-50/60 p-3">
            <p className="mb-2 text-xs font-semibold text-slate-700">Base</p>
            <FormulaBlock
              latex={`\\text{base} = \\mathrm{SCI}_{\\text{norm}} \\times \\mathrm{CRS}_{\\text{norm}}`}
            />
            <p className="mt-1 font-mono text-[11px] text-slate-700">
              = {fmt(sciNorm)} × {hasCrs ? fmt(crsNorm!) : "0.5 (CRS absent — neutral fallback)"}
              {" = "}
              <span className="font-semibold">{fmt(base)}</span>
            </p>
          </div>

          <div className="rounded-lg border border-slate-100 bg-slate-50/60 p-3">
            <p className="mb-2 text-xs font-semibold text-slate-700">
              Amplifier (active terms only)
            </p>
            <ul className="space-y-1 text-[11px]">
              {terms.map((t) => (
                <li
                  key={t.key}
                  className={
                    t.active
                      ? "font-mono text-slate-700"
                      : "font-mono text-slate-400 line-through"
                  }
                >
                  {t.label} · w = {fmt(t.weight)} ·{" "}
                  {t.active ? (
                    <>value = {fmt(t.value as number)}</>
                  ) : (
                    <>value absent → dropped from numerator AND divisor</>
                  )}
                </li>
              ))}
            </ul>
            <p className="mt-2 font-mono text-[11px] text-slate-700">
              amp = 1 + {fmt(activeNum)} = <span className="font-semibold">{fmt(amp)}</span>
              {" · "}
              max = 1 + {fmt(activeWeightSum)} ={" "}
              <span className="font-semibold">{fmt(maxAmp)}</span>
            </p>
          </div>

          <div className="rounded-lg border border-purple-100 bg-purple-50/60 p-3">
            <p className="mb-1 text-xs font-semibold text-slate-700">Final</p>
            <FormulaBlock
              latex={`\\mathrm{CVS} = \\text{base} \\times \\text{amp} / \\text{max}`}
            />
            <p className="mt-1 font-mono text-[11px] text-slate-700">
              = {fmt(base)} × {fmt(amp)} / {fmt(maxAmp)} ={" "}
              <span className="font-semibold text-purple-700">{fmt(cvsComputed)}</span>
            </p>
            {profile.cvs != null &&
              Math.abs(cvsComputed - profile.cvs) > 1e-3 && (
                <p className="mt-2 text-[10px] italic text-amber-700">
                  Note: server-side CVS = {fmt(profile.cvs)}; rounded difference is
                  expected for missing-norm terms or alternate composition modes.
                </p>
              )}
          </div>
        </div>
      )}
    </section>
  );
}
