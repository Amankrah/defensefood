"use client";

import { useEffect, useMemo, useState } from "react";
import { usePathname } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import { Activity, ChevronRight, Menu } from "lucide-react";

const PAGE_TITLES: Record<string, string> = {
  "/dashboard": "Today",
  "/dashboard/corridors": "Corridors",
  "/dashboard/patterns": "Patterns",
  "/dashboard/network": "Network",
  "/dashboard/lab": "Research workbench",
};

function resolveTitle(pathname: string): string {
  if (PAGE_TITLES[pathname]) return PAGE_TITLES[pathname];
  if (pathname.startsWith("/dashboard/corridors/")) return "Lane report";
  if (pathname.startsWith("/dashboard/countries/")) return "Country snapshot";
  if (pathname.startsWith("/dashboard/lab/")) return "Lane lab";
  return "Dashboard";
}

function resolveBreadcrumb(pathname: string): { label: string; href?: string }[] {
  if (pathname === "/dashboard") return [{ label: "Today" }];
  const segments = pathname.replace("/dashboard", "").split("/").filter(Boolean);
  const crumbs: { label: string; href?: string }[] = [
    { label: "Dashboard", href: "/dashboard" },
  ];
  let path = "/dashboard";
  for (const seg of segments) {
    path += `/${seg}`;
    crumbs.push({
      label: resolveTitle(path),
      href: path === pathname ? undefined : path,
    });
  }
  return crumbs;
}

interface DashboardHeaderProps {
  onMenuClick?: () => void;
}

export default function DashboardHeader({ onMenuClick }: DashboardHeaderProps) {
  const pathname = usePathname();
  const [period, setPeriod] = useState<number>(0);
  const [status, setStatus] = useState<"ok" | "error">("ok");
  const [corridorCount, setCorridorCount] = useState<number | null>(null);

  useEffect(() => {
    Promise.all([api.hazards.summary(), api.health()])
      .then(([s, h]) => {
        setPeriod(s.current_period);
        setStatus("ok");
        setCorridorCount(h.data?.corridor_metrics ?? null);
      })
      .catch(() => setStatus("error"));
  }, []);

  const periodLabel = period
    ? `${Math.floor(period / 100)}-${String(period % 100).padStart(2, "0")}`
    : "…";

  const title = useMemo(() => resolveTitle(pathname), [pathname]);
  const breadcrumbs = useMemo(() => resolveBreadcrumb(pathname), [pathname]);

  return (
    <header className="sticky top-0 z-30 flex h-14 items-center justify-between gap-4 border-b border-slate-200/80 bg-white/90 px-4 backdrop-blur-md sm:px-6">
      <div className="flex min-w-0 items-center gap-3">
        <button
          type="button"
          onClick={onMenuClick}
          className="rounded-lg border border-slate-200 p-2 text-slate-600 transition hover:bg-slate-50 lg:hidden"
          aria-label="Open navigation"
        >
          <Menu size={18} />
        </button>
        <div className="min-w-0">
          <nav
            aria-label="Breadcrumb"
            className="hidden items-center gap-1 text-[11px] text-slate-500 sm:flex"
          >
            {breadcrumbs.map((crumb, i) => (
              <span key={i} className="inline-flex items-center gap-1">
                {i > 0 && (
                  <ChevronRight size={12} className="text-slate-300" aria-hidden />
                )}
                {crumb.href ? (
                  <Link
                    href={crumb.href}
                    className="transition hover:text-slate-800"
                  >
                    {crumb.label}
                  </Link>
                ) : (
                  <span className="font-medium text-slate-700">{crumb.label}</span>
                )}
              </span>
            ))}
          </nav>
          <p className="truncate text-sm font-semibold text-slate-900 sm:mt-0.5">
            {title}
          </p>
        </div>
      </div>

      <div className="flex shrink-0 items-center gap-2 sm:gap-3">
        {corridorCount != null && (
          <span className="hidden rounded-lg border border-slate-200/80 bg-slate-50 px-2.5 py-1 text-[11px] text-slate-600 md:inline">
            <span className="font-mono font-semibold text-slate-800">
              {corridorCount.toLocaleString()}
            </span>{" "}
            corridors
          </span>
        )}
        <span
          className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium ${
            status === "ok"
              ? "border-emerald-200/90 bg-emerald-50 text-emerald-800"
              : "border-red-200/90 bg-red-50 text-red-800"
          }`}
        >
          <Activity
            size={12}
            className={status === "ok" ? "text-emerald-500" : "text-red-500"}
            aria-hidden
          />
          <span className="hidden sm:inline">API</span>{" "}
          {status === "ok" ? "live" : "offline"}
        </span>
        <span className="hidden h-4 w-px bg-slate-200 sm:block" aria-hidden />
        <span className="text-xs tabular-nums text-slate-500">
          <span className="hidden sm:inline">Period </span>
          <span className="font-medium text-slate-800">{periodLabel}</span>
        </span>
      </div>
    </header>
  );
}
