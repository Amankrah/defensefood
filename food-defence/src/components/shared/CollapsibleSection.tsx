"use client";

import { useState, type ReactNode } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";

interface CollapsibleSectionProps {
  title: string;
  subtitle?: ReactNode;
  /** Render-prop for content shown in the collapsed header (e.g. active chips). */
  collapsedHeader?: ReactNode;
  /** Right-aligned actions (e.g. reset button) always visible. */
  actions?: ReactNode;
  /** Starts open if true; defaults to false. */
  defaultOpen?: boolean;
  children: ReactNode;
}

export default function CollapsibleSection({
  title,
  subtitle,
  collapsedHeader,
  actions,
  defaultOpen = false,
  children,
}: CollapsibleSectionProps) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <section className="rounded-xl border border-slate-200 bg-white shadow-sm">
      <header className="flex flex-wrap items-center justify-between gap-2 px-4 py-3">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="flex items-center gap-2 text-left"
          aria-expanded={open}
        >
          {open ? (
            <ChevronDown size={16} className="text-slate-500" aria-hidden />
          ) : (
            <ChevronRight size={16} className="text-slate-500" aria-hidden />
          )}
          <span className="text-sm font-semibold text-slate-800">{title}</span>
          {subtitle && (
            <span className="text-[11px] text-slate-500">{subtitle}</span>
          )}
        </button>
        <div className="flex flex-wrap items-center gap-2">
          {!open && collapsedHeader}
          {actions}
        </div>
      </header>
      {open && <div className="border-t border-slate-100 px-4 py-4">{children}</div>}
    </section>
  );
}
