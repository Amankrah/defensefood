"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Globe,
  Home,
  LayoutDashboard,
  Network,
  Search,
  Shield,
} from "lucide-react";

const NAV_ITEMS = [
  { href: "/dashboard", label: "Overview", icon: LayoutDashboard },
  { href: "/dashboard/corridors", label: "Corridors", icon: Search },
  { href: "/dashboard/network", label: "Trade network", icon: Network },
];

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="fixed left-0 top-0 bottom-0 z-30 flex w-56 flex-col border-r border-slate-800/60 bg-gradient-to-b from-slate-950 via-slate-900 to-slate-950 text-slate-300 shadow-xl shadow-slate-950/20">
      <Link
        href="/"
        className="flex items-center gap-2.5 border-b border-slate-800/80 px-5 py-5 transition hover:bg-white/5"
      >
        <div className="rounded-xl bg-gradient-to-br from-blue-500 to-indigo-600 p-1.5 shadow-lg shadow-blue-900/40">
          <Shield size={18} className="text-white" aria-hidden />
        </div>
        <div>
          <span className="block text-sm font-semibold leading-tight text-white">
            DefenseFood
          </span>
          <span className="text-[10px] leading-tight text-slate-500">
            Risk and diagnostics
          </span>
        </div>
      </Link>

      <nav className="flex-1 space-y-0.5 overflow-y-auto px-3 py-4">
        <p className="mb-2 px-2 text-[10px] font-semibold uppercase tracking-wider text-slate-600">
          Investigate
        </p>
        {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
          const active =
            pathname === href ||
            (href !== "/dashboard" && pathname.startsWith(href));
          return (
            <Link
              key={href}
              href={href}
              className={`relative flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition-colors ${
                active
                  ? "bg-white/10 text-white"
                  : "text-slate-400 hover:bg-white/5 hover:text-white"
              }`}
            >
              {active && (
                <span
                  className="absolute left-0 top-1/2 h-6 w-0.5 -translate-y-1/2 rounded-full bg-blue-500"
                  aria-hidden
                />
              )}
              <Icon size={16} className={active ? "text-blue-400" : undefined} aria-hidden />
              {label}
            </Link>
          );
        })}

        <p className="mb-2 mt-6 px-2 text-[10px] font-semibold uppercase tracking-wider text-slate-600">
          Reference
        </p>
        <Link
          href="/dashboard/countries/251"
          className="flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm text-slate-400 transition-colors hover:bg-white/5 hover:text-white"
        >
          <Globe size={16} aria-hidden />
          Country profiles
        </Link>
        <Link
          href="/"
          className="mt-2 flex items-center gap-2.5 rounded-lg border border-slate-800/80 px-3 py-2 text-sm text-slate-500 transition-colors hover:border-slate-700 hover:bg-white/5 hover:text-slate-300"
        >
          <Home size={16} aria-hidden />
          Home
        </Link>
      </nav>

      <div className="border-t border-slate-800/80 px-5 py-4 text-[10px] leading-relaxed text-slate-600">
        Scores are guides: confirm with policy, sampling, and lab strategy.
      </div>
    </aside>
  );
}
