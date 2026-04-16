import Link from "next/link";
import {
  ArrowRight,
  BarChart3,
  Layers,
  Network,
  Shield,
  Sparkles,
} from "lucide-react";

export default function Home() {
  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <div className="pointer-events-none fixed inset-0 overflow-hidden">
        <div
          className="absolute -top-40 right-[-10%] h-[480px] w-[480px] rounded-full bg-blue-500/15 blur-3xl"
          aria-hidden
        />
        <div
          className="absolute top-1/3 left-[-15%] h-[420px] w-[420px] rounded-full bg-indigo-500/10 blur-3xl"
          aria-hidden
        />
        <div
          className="absolute inset-0 bg-[linear-gradient(to_bottom,transparent_0%,rgba(248,250,252,0.7)_40%,#f8fafc_100%)]"
          aria-hidden
        />
      </div>

      <header className="relative z-10 border-b border-slate-200/80 bg-white/70 backdrop-blur-md">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <Link href="/" className="flex items-center gap-2.5">
            <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-blue-600 to-indigo-600 text-white shadow-lg shadow-blue-600/25">
              <Shield size={18} strokeWidth={2.25} aria-hidden />
            </span>
            <span className="text-sm font-semibold tracking-tight">DefenseFood</span>
          </Link>
          <nav className="flex items-center gap-1 text-sm">
            <Link
              href="/dashboard"
              className="inline-flex items-center gap-1.5 rounded-lg bg-slate-900 px-4 py-2 font-medium text-white shadow-sm transition hover:bg-slate-800"
            >
              Dashboard
              <ArrowRight size={14} aria-hidden />
            </Link>
          </nav>
        </div>
      </header>

      <main className="relative z-10">
        <section className="mx-auto max-w-6xl px-6 pb-20 pt-16 sm:pt-24">
          <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-slate-200/80 bg-white/80 px-3 py-1 text-xs font-medium text-slate-600 shadow-sm backdrop-blur">
            <Sparkles size={14} className="text-amber-500" aria-hidden />
            Decision support for EU food risk and trade corridors
          </div>
          <h1 className="max-w-3xl text-4xl font-bold tracking-tight text-slate-900 sm:text-5xl sm:leading-[1.1]">
            See which trade lanes need{" "}
            <span className="bg-gradient-to-r from-blue-600 to-indigo-600 bg-clip-text text-transparent">
              attention first
            </span>
          </h1>
          <p className="mt-6 max-w-2xl text-lg leading-relaxed text-slate-600">
            Bring together RASFF alerts, bilateral trade, and dependency signals so teams can
            prioritise inspections, labs, and supplier checks with clear, explainable scores per
            corridor and country.
          </p>
          <div className="mt-10">
            <Link
              href="/dashboard"
              className="inline-flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 px-6 py-3.5 text-sm font-semibold text-white shadow-lg shadow-blue-600/25 transition hover:brightness-110"
            >
              Open dashboard
              <ArrowRight size={18} aria-hidden />
            </Link>
          </div>
        </section>

        <section className="mx-auto max-w-6xl px-6 pb-24">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <article className="group rounded-2xl border border-slate-200/80 bg-white p-6 shadow-sm transition hover:border-blue-200/80 hover:shadow-md">
              <div className="mb-4 flex h-11 w-11 items-center justify-center rounded-xl bg-blue-50 text-blue-600 transition group-hover:bg-blue-100">
                <Layers size={22} aria-hidden />
              </div>
              <h2 className="text-base font-semibold text-slate-900">Prioritise corridors</h2>
              <p className="mt-2 text-sm leading-relaxed text-slate-600">
                Rank origin-to-destination commodity lanes by hazard heat, economic exposure, and
                combined priority so you know where to dig deeper.
              </p>
            </article>
            <article className="group rounded-2xl border border-slate-200/80 bg-white p-6 shadow-sm transition hover:border-violet-200/80 hover:shadow-md">
              <div className="mb-4 flex h-11 w-11 items-center justify-center rounded-xl bg-violet-50 text-violet-600 transition group-hover:bg-violet-100">
                <Network size={22} aria-hidden />
              </div>
              <h2 className="text-base font-semibold text-slate-900">Map relationships</h2>
              <p className="mt-2 text-sm leading-relaxed text-slate-600">
                Explore how supplier countries connect to EU destinations, with link strength tied
                to hazard signals for faster network-level diagnostics.
              </p>
            </article>
            <article className="group rounded-2xl border border-slate-200/80 bg-white p-6 shadow-sm transition hover:border-emerald-200/80 hover:shadow-md sm:col-span-2 lg:col-span-1">
              <div className="mb-4 flex h-11 w-11 items-center justify-center rounded-xl bg-emerald-50 text-emerald-600 transition group-hover:bg-emerald-100">
                <BarChart3 size={22} aria-hidden />
              </div>
              <h2 className="text-base font-semibold text-slate-900">Explainable scores</h2>
              <p className="mt-2 text-sm leading-relaxed text-slate-600">
                Every headline figure maps to a plain meaning (for example: higher hazard intensity
                means more alert activity on that lane). Adjust weights when your risk policy
                changes, then refresh the dashboard.
              </p>
            </article>
          </div>
        </section>

        <footer className="border-t border-slate-200/80 bg-white/80 py-8 backdrop-blur">
          <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-4 px-6 text-center text-xs text-slate-500 sm:flex-row sm:text-left">
            <p>DefenseFood: operational analytics for food fraud vulnerability.</p>
            <p className="text-[11px] text-slate-400">
              Connects to your DefenseFood API for live corridor and country data.
            </p>
          </div>
        </footer>
      </main>
    </div>
  );
}
