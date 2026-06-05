import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import Link from "next/link";
import { ArrowRight } from "lucide-react";

interface SectionCardProps {
  title: string;
  description?: string;
  icon?: LucideIcon;
  iconClassName?: string;
  /** Link shown in the section header */
  href?: string;
  hrefLabel?: string;
  children: ReactNode;
  className?: string;
  /** Visual emphasis: default | featured | muted */
  variant?: "default" | "featured" | "muted";
}

export default function SectionCard({
  title,
  description,
  icon: Icon,
  iconClassName = "text-blue-600",
  href,
  hrefLabel = "View all",
  children,
  className = "",
  variant = "default",
}: SectionCardProps) {
  const variantClass =
    variant === "featured"
      ? "border-blue-200/60 bg-gradient-to-br from-blue-50/30 to-white"
      : variant === "muted"
        ? "border-slate-200/60 bg-slate-50/50"
        : "border-slate-200/80 bg-white";

  return (
    <section className={`df-card p-5 ${variantClass} ${className}`}>
      <div className="mb-4 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            {Icon && (
              <Icon size={16} className={iconClassName} aria-hidden />
            )}
            <h2 className="text-sm font-semibold text-slate-900">{title}</h2>
          </div>
          {description && (
            <p className="mt-1 text-xs leading-relaxed text-slate-500">
              {description}
            </p>
          )}
        </div>
        {href && (
          <Link
            href={href}
            className="inline-flex shrink-0 items-center gap-1 text-xs font-medium text-blue-600 transition hover:text-blue-800"
          >
            {hrefLabel}
            <ArrowRight size={12} aria-hidden />
          </Link>
        )}
      </div>
      {children}
    </section>
  );
}
