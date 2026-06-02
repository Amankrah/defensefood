"use client";

import { HelpCircle } from "lucide-react";
import { useGlossary } from "@/components/shared/Glossary";

interface MetricHelpProps {
  /** Metric key (matches methodology catalogue's `key`, e.g. "idr", "sci"). */
  metricKey: string;
  /** Optional fallback label shown in the title tooltip. */
  label?: string;
  /** Pixel size of the icon. Default 12. */
  size?: number;
  /** Optional extra class names. */
  className?: string;
}

/**
 * Small "?" icon that opens the Glossary slide-over scrolled to this metric.
 *
 * Drop next to any metric abbreviation:
 *   <MetricHelp metricKey="idr" label="Import reliance" />
 */
export default function MetricHelp({
  metricKey,
  label,
  size = 12,
  className = "",
}: MetricHelpProps) {
  const glossary = useGlossary();
  const tip = label ? `What is ${label}?` : "What does this metric mean?";
  return (
    <button
      type="button"
      onClick={(e) => {
        e.stopPropagation();
        glossary.open(metricKey);
      }}
      title={tip}
      aria-label={tip}
      className={`inline-flex items-center justify-center rounded-full text-slate-400 transition hover:bg-slate-100 hover:text-slate-700 ${className}`}
      style={{ width: size + 4, height: size + 4 }}
    >
      <HelpCircle size={size} aria-hidden />
    </button>
  );
}
