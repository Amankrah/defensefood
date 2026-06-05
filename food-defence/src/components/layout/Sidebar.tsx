"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BookOpen,
  FlaskConical,
  Globe,
  Home,
  LayoutDashboard,
  Network,
  Search,
  Sparkles,
  X,
} from "lucide-react";
import LogoMark from "@/components/shared/LogoMark";
import { useGlossary } from "@/components/shared/Glossary";

const NAV_ITEMS = [
  {
    href: "/dashboard",
    label: "Today",
    icon: LayoutDashboard,
    hint: "Priority queue and rollups",
  },
  {
    href: "/dashboard/corridors",
    label: "Corridors",
    icon: Search,
    hint: "Filter every lane",
  },
  {
    href: "/dashboard/patterns",
    label: "Patterns",
    icon: Sparkles,
    hint: "Heatmap and scoring config",
  },
  {
    href: "/dashboard/network",
    label: "Network",
    icon: Network,
    hint: "Country graph",
  },
];

const RESEARCH_ITEMS = [
  {
    href: "/dashboard/lab",
    label: "Workbench",
    icon: FlaskConical,
    hint: "Distributions, cohorts, methodology",
  },
];

interface SidebarProps {
  open?: boolean;
  onClose?: () => void;
}

export default function Sidebar({ open = false, onClose }: SidebarProps) {
  const pathname = usePathname();
  const glossary = useGlossary();

  const handleNav = () => onClose?.();

  return (
    <aside
      className={`fixed left-0 top-0 bottom-0 z-50 flex w-60 flex-col border-r border-[var(--sidebar-border)] bg-[var(--sidebar-bg)] text-[var(--sidebar-text)] shadow-2xl transition-transform duration-200 ease-out lg:translate-x-0 ${
        open ? "translate-x-0" : "-translate-x-full lg:translate-x-0"
      }`}
    >
      <div className="flex items-center justify-between border-b border-[var(--sidebar-border)] px-4 py-4">
        <Link
          href="/"
          onClick={handleNav}
          className="flex min-w-0 items-center gap-2.5 rounded-lg transition hover:bg-white/5"
        >
          <LogoMark size={32} />
          <div className="min-w-0">
            <span className="block truncate text-sm font-semibold leading-tight text-white">
              DefenseFood
            </span>
            <span className="text-[10px] leading-tight text-slate-500">
              Inspection planner
            </span>
          </div>
        </Link>
        <button
          type="button"
          onClick={onClose}
          className="rounded-lg p-1.5 text-slate-400 transition hover:bg-white/10 hover:text-white lg:hidden"
          aria-label="Close navigation"
        >
          <X size={18} />
        </button>
      </div>

      <nav className="flex-1 space-y-0.5 overflow-y-auto px-3 py-4">
        <NavGroup label="Investigate">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.href}
              {...item}
              pathname={pathname}
              onNavigate={handleNav}
            />
          ))}
        </NavGroup>

        <NavGroup label="Research">
          {RESEARCH_ITEMS.map((item) => (
            <NavLink
              key={item.href}
              {...item}
              pathname={pathname}
              onNavigate={handleNav}
            />
          ))}
        </NavGroup>

        <NavGroup label="Reference">
          <Link
            href="/dashboard/countries/251"
            onClick={handleNav}
            className="flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm text-slate-400 transition-colors hover:bg-white/5 hover:text-white"
            title="Country snapshots (sample: Germany)"
          >
            <Globe size={16} aria-hidden />
            Countries
          </Link>
          <button
            type="button"
            onClick={() => {
              glossary.open();
              onClose?.();
            }}
            className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left text-sm text-slate-400 transition-colors hover:bg-white/5 hover:text-white"
            title="What do these terms mean?"
          >
            <BookOpen size={16} aria-hidden />
            Glossary
          </button>
          <Link
            href="/"
            onClick={handleNav}
            className="mt-1 flex items-center gap-2.5 rounded-lg border border-white/5 px-3 py-2 text-sm text-slate-500 transition-colors hover:border-white/10 hover:bg-white/5 hover:text-slate-300"
          >
            <Home size={16} aria-hidden />
            Home
          </Link>
        </NavGroup>
      </nav>

      <div className="border-t border-[var(--sidebar-border)] px-4 py-4 text-[10px] leading-relaxed text-slate-600">
        Scores guide inspection focus — confirm with sampling and lab strategy.
      </div>
    </aside>
  );
}

function NavGroup({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="mb-1">
      <p className="mb-2 px-2 text-[10px] font-semibold uppercase tracking-wider text-slate-600">
        {label}
      </p>
      <div className="space-y-0.5">{children}</div>
    </div>
  );
}

function NavLink({
  href,
  label,
  icon: Icon,
  hint,
  pathname,
  onNavigate,
}: {
  href: string;
  label: string;
  icon: typeof LayoutDashboard;
  hint: string;
  pathname: string;
  onNavigate: () => void;
}) {
  const active =
    pathname === href ||
    (href !== "/dashboard" && pathname.startsWith(href));

  return (
    <Link
      href={href}
      onClick={onNavigate}
      title={hint}
      className={`relative flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition-colors ${
        active
          ? "bg-white/10 font-medium text-[var(--sidebar-text-active)]"
          : "text-slate-400 hover:bg-white/5 hover:text-white"
      }`}
    >
      {active && (
        <span
          className="absolute left-0 top-1/2 h-5 w-0.5 -translate-y-1/2 rounded-full bg-[var(--sidebar-accent)]"
          aria-hidden
        />
      )}
      <Icon
        size={16}
        className={active ? "text-blue-400" : undefined}
        aria-hidden
      />
      {label}
    </Link>
  );
}
