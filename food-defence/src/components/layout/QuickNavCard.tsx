import Link from "next/link";
import type { LucideIcon } from "lucide-react";
import { ArrowRight } from "lucide-react";

interface QuickNavCardProps {
  href: string;
  icon: LucideIcon;
  title: string;
  description: string;
  accent?: "blue" | "violet" | "teal";
}

const ACCENT = {
  blue: {
    icon: "text-blue-600",
    hover: "hover:border-blue-200 hover:bg-blue-50/60",
  },
  violet: {
    icon: "text-violet-600",
    hover: "hover:border-violet-200 hover:bg-violet-50/60",
  },
  teal: {
    icon: "text-teal-600",
    hover: "hover:border-teal-200 hover:bg-teal-50/60",
  },
} as const;

export default function QuickNavCard({
  href,
  icon: Icon,
  title,
  description,
  accent = "blue",
}: QuickNavCardProps) {
  const tone = ACCENT[accent];
  return (
    <Link
      href={href}
      className={`group df-card df-card-interactive flex items-start gap-3 p-4 ${tone.hover}`}
    >
      <span
        className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-slate-50 ${tone.icon} transition group-hover:bg-white`}
      >
        <Icon size={18} aria-hidden />
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-1 text-sm font-semibold text-slate-900">
          {title}
          <ArrowRight
            size={14}
            className="opacity-0 transition group-hover:opacity-100"
            aria-hidden
          />
        </span>
        <span className="mt-0.5 block text-xs leading-snug text-slate-500">
          {description}
        </span>
      </span>
    </Link>
  );
}
