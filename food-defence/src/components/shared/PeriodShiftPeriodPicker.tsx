"use client";

interface PeriodShiftPeriodPickerProps {
  available: number[];
  valueA?: number;
  valueB?: number;
  disabled: boolean;
  onChange: (a: number | undefined, b: number | undefined) => void;
}

export default function PeriodShiftPeriodPicker({
  available,
  valueA,
  valueB,
  disabled,
  onChange,
}: PeriodShiftPeriodPickerProps) {
  const selA =
    valueA != null && available.includes(valueA) ? valueA : (valueA ?? "");
  const selB =
    valueB != null && available.includes(valueB) ? valueB : (valueB ?? "");

  return (
    <fieldset
      className="df-fieldset-inline inline-flex min-w-0 items-center gap-1 rounded-full border border-slate-200 bg-white px-1.5 py-0.5"
      aria-label="Period comparison"
    >
      <legend className="sr-only">Period comparison</legend>
      <div className="inline-flex min-w-0 items-center gap-0.5">
        <label
          htmlFor="period-shift-baseline"
          className="text-[9px] font-medium uppercase tracking-wide text-slate-400"
        >
          Base
        </label>
        <select
          title="Baseline period"
          id="period-shift-baseline"
          name="period-shift-baseline"
          aria-label="Baseline period"
          disabled={disabled}
          value={selA}
          onChange={(e) => onChange(parseInt(e.target.value), valueB)}
          className="rounded bg-transparent px-1 font-mono text-[10px] text-slate-700 focus:outline-none disabled:opacity-50"
        >
          {available.map((y) => (
            <option key={y} value={y}>
              {y}
            </option>
          ))}
          {valueA != null && !available.includes(valueA) && (
            <option value={valueA}>{valueA} *</option>
          )}
        </select>
      </div>
      <span className="text-[10px] text-slate-400" aria-hidden>
        →
      </span>
      <div className="inline-flex min-w-0 items-center gap-0.5">
        <label
          htmlFor="period-shift-comparison"
          className="text-[9px] font-medium uppercase tracking-wide text-slate-400"
        >
          Compare
        </label>
        <select
          title="Comparison period"
          id="period-shift-comparison"
          name="period-shift-comparison"
          aria-label="Comparison period"
          disabled={disabled}
          value={selB}
          onChange={(e) => onChange(valueA, parseInt(e.target.value))}
          className="rounded bg-transparent px-1 font-mono text-[10px] text-slate-700 focus:outline-none disabled:opacity-50"
        >
          {available.map((y) => (
            <option key={y} value={y}>
              {y}
            </option>
          ))}
          {valueB != null && !available.includes(valueB) && (
            <option value={valueB}>{valueB} *</option>
          )}
        </select>
      </div>
    </fieldset>
  );
}
