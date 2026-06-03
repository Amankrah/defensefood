import Link from "next/link";
import {
  ArrowRight,
  BookOpen,
  Compass,
  FlaskConical,
  Globe2,
  Layers,
  Network,
  Scale,
  Shield,
  ShieldCheck,
  TrendingUp,
} from "lucide-react";

export default function Home() {
  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <BackgroundGlow />

      <SiteHeader />

      <main className="relative z-10">
        <Hero />
        <Snapshot />
        <UseCases />
        <HowItWorks />
        <FrameworkSections />
        <Footer />
      </main>
    </div>
  );
}

/* ──────────────────────────────────────────────────────────────────── */
/* Header                                                                */
/* ──────────────────────────────────────────────────────────────────── */

function SiteHeader() {
  return (
    <header className="relative z-10 border-b border-slate-200/80 bg-white/70 backdrop-blur-md">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
        <Link href="/" className="flex items-center gap-2.5">
          <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-blue-600 to-indigo-600 text-white shadow-lg shadow-blue-600/25">
            <Shield size={18} strokeWidth={2.25} aria-hidden />
          </span>
          <span className="text-sm font-semibold tracking-tight">DefenseFood</span>
        </Link>
        <nav className="flex items-center gap-2 text-sm">
          <Link
            href="/dashboard/lab"
            className="hidden rounded-lg px-3 py-2 font-medium text-slate-600 transition hover:bg-slate-100 hover:text-slate-900 sm:inline-flex"
          >
            Methodology
          </Link>
          <Link
            href="/dashboard"
            className="inline-flex items-center gap-1.5 rounded-lg bg-slate-900 px-4 py-2 font-medium text-white shadow-sm transition hover:bg-slate-800"
          >
            Open dashboard
            <ArrowRight size={14} aria-hidden />
          </Link>
        </nav>
      </div>
    </header>
  );
}

/* ──────────────────────────────────────────────────────────────────── */
/* Hero                                                                  */
/* ──────────────────────────────────────────────────────────────────── */

function Hero() {
  return (
    <section className="mx-auto max-w-6xl px-6 pb-16 pt-16 sm:pt-24">
      <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-slate-200/80 bg-white/80 px-3 py-1 text-xs font-medium text-slate-600 shadow-sm backdrop-blur">
        <ShieldCheck size={14} className="text-emerald-500" aria-hidden />
        Built on the EU Food Fraud Vulnerability Mathematical Framework, v1.0
      </div>

      <h1 className="max-w-3xl text-4xl font-bold tracking-tight text-slate-900 sm:text-5xl sm:leading-[1.1]">
        Where should food fraud inspectors look{" "}
        <span className="bg-gradient-to-r from-blue-600 to-indigo-600 bg-clip-text text-transparent">
          this week
        </span>
        ?
      </h1>

      <p className="mt-6 max-w-2xl text-lg leading-relaxed text-slate-600">
        DefenseFood scores every commodity, destination, origin lane in your
        data by combining RASFF hazard alerts, UN Comtrade bilateral trade, and
        FAOSTAT food balance sheets. You get a ranked priority queue. Click any
        row to see how the score was built, term by term.
      </p>

      <div className="mt-10 flex flex-wrap items-center gap-3">
        <Link
          href="/dashboard"
          className="inline-flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 px-6 py-3.5 text-sm font-semibold text-white shadow-lg shadow-blue-600/25 transition hover:brightness-110"
        >
          Open the priority queue
          <ArrowRight size={18} aria-hidden />
        </Link>
        <Link
          href="/dashboard/lab"
          className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-300 bg-white px-6 py-3.5 text-sm font-semibold text-slate-700 shadow-sm transition hover:border-slate-400 hover:bg-slate-50"
        >
          Read the methodology
          <BookOpen size={16} aria-hidden />
        </Link>
      </div>

      <p className="mt-6 max-w-2xl text-sm leading-relaxed text-slate-500">
        Designed for EU food safety planners, sampling teams, and food fraud
        researchers. Every headline number maps to a published equation in the
        framework, with the inputs and value bands shown alongside the score.
      </p>
    </section>
  );
}

/* ──────────────────────────────────────────────────────────────────── */
/* Snapshot strip                                                        */
/* ──────────────────────────────────────────────────────────────────── */

function Snapshot() {
  const items = [
    { label: "Framework sections", value: "7", note: "Sections 2 through 7 of the v1.0 framework" },
    { label: "Documented metrics", value: "22", note: "Each with a formula, scale bands, and inputs" },
    { label: "Hazard families", value: "6", note: "Biological, mycotoxins, pesticides, metals, other chemical, regulatory" },
    { label: "RASFF roles", value: "4", note: "notifier, distribution, follow-up, attention" },
  ];

  return (
    <section className="mx-auto max-w-6xl px-6 pb-20">
      <div className="grid grid-cols-2 gap-px overflow-hidden rounded-2xl border border-slate-200 bg-slate-200 sm:grid-cols-4">
        {items.map((it) => (
          <div key={it.label} className="bg-white p-5">
            <p className="font-mono text-3xl font-semibold text-slate-900">{it.value}</p>
            <p className="mt-1 text-xs font-semibold uppercase tracking-wider text-slate-500">
              {it.label}
            </p>
            <p className="mt-1.5 text-[11px] leading-snug text-slate-500">{it.note}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

/* ──────────────────────────────────────────────────────────────────── */
/* What you can do (use cases)                                           */
/* ──────────────────────────────────────────────────────────────────── */

function UseCases() {
  const cards = [
    {
      icon: Compass,
      title: "Plan inspections",
      href: "/dashboard/corridors",
      hrefLabel: "Browse corridors",
      iconBg: "bg-blue-50",
      iconText: "text-blue-600",
      iconHover: "group-hover:bg-blue-100",
      border: "hover:border-blue-200/80",
      body: (
        <>
          Sort lanes by combined vulnerability (CVS) and filter by destination,
          origin, hazard family, or market presence. The default view hides
          informational only RASFF mentions, so the queue reflects lanes that
          are actually on EU markets per the SOPs.
        </>
      ),
    },
    {
      icon: Globe2,
      title: "Trace exposure across the network",
      href: "/dashboard/network",
      hrefLabel: "Open the network view",
      iconBg: "bg-violet-50",
      iconText: "text-violet-600",
      iconHover: "group-hover:bg-violet-100",
      border: "hover:border-violet-200/80",
      body: (
        <>
          Country pages show inbound exposure (ACEP) and outbound propagation
          (ORPS), split by RASFF role. The exposure graph colours confirmed
          market lanes by hazard intensity and distinguishes them from
          informational mentions.
        </>
      ),
    },
    {
      icon: FlaskConical,
      title: "Verify the math",
      href: "/dashboard/lab",
      hrefLabel: "See the glossary",
      iconBg: "bg-emerald-50",
      iconText: "text-emerald-600",
      iconHover: "group-hover:bg-emerald-100",
      border: "hover:border-emerald-200/80",
      body: (
        <>
          Every metric has its own glossary card with the blueprint formula, a
          plain English rewrite, scale bands, and which inputs went in. Open
          any lane to see how its CVS was built, with each amplifier term
          struck through when the input is missing.
        </>
      ),
    },
  ];

  return (
    <section className="mx-auto max-w-6xl px-6 pb-24">
      <div className="mb-8">
        <p className="text-xs font-semibold uppercase tracking-wider text-blue-600">
          What you can do here
        </p>
        <h2 className="mt-2 text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">
          Three workflows, one corpus
        </h2>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {cards.map((c) => {
          const Icon = c.icon;
          return (
            <article
              key={c.title}
              className={`group rounded-2xl border border-slate-200/80 bg-white p-6 shadow-sm transition hover:shadow-md ${c.border}`}
            >
              <div
                className={`mb-4 flex h-11 w-11 items-center justify-center rounded-xl ${c.iconBg} ${c.iconText} transition ${c.iconHover}`}
              >
                <Icon size={22} aria-hidden />
              </div>
              <h3 className="text-base font-semibold text-slate-900">{c.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-slate-600">{c.body}</p>
              <Link
                href={c.href}
                className="mt-4 inline-flex items-center gap-1.5 text-sm font-medium text-slate-900 hover:text-blue-600"
              >
                {c.hrefLabel}
                <ArrowRight size={14} aria-hidden />
              </Link>
            </article>
          );
        })}
      </div>
    </section>
  );
}

/* ──────────────────────────────────────────────────────────────────── */
/* How it works                                                          */
/* ──────────────────────────────────────────────────────────────────── */

function HowItWorks() {
  const steps = [
    {
      n: 1,
      icon: Layers,
      title: "Ingest",
      body: "RASFF Window exports for hazard alerts. UN Comtrade for bilateral trade. FAOSTAT for production and consumption. The merged trade corpus is prepared ahead of time so requests stay fast.",
    },
    {
      n: 2,
      icon: Scale,
      title: "Compute",
      body: "A Rust engine evaluates the seven sections of the framework on every corridor at startup: dependency, consumption demand, hazard intensity, trade flow anomalies, network propagation, and composite scoring.",
    },
    {
      n: 3,
      icon: TrendingUp,
      title: "Explain",
      body: "Each score on the dashboard links back to its bands, its formula, and the inputs that drove it. When data is partial, the system says so instead of hiding the gap.",
    },
  ];

  return (
    <section className="border-t border-slate-200/80 bg-white/60 py-20 backdrop-blur-sm">
      <div className="mx-auto max-w-6xl px-6">
        <div className="mb-10">
          <p className="text-xs font-semibold uppercase tracking-wider text-blue-600">
            How it works
          </p>
          <h2 className="mt-2 text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">
            Three stages, end to end
          </h2>
        </div>

        <ol className="grid gap-6 sm:grid-cols-3">
          {steps.map(({ n, icon: Icon, title, body }) => (
            <li
              key={n}
              className="relative rounded-2xl border border-slate-200/80 bg-white p-6 shadow-sm"
            >
              <div className="mb-4 flex items-center gap-3">
                <span className="flex h-8 w-8 items-center justify-center rounded-full bg-slate-900 text-xs font-mono font-semibold text-white">
                  {n}
                </span>
                <Icon size={18} className="text-slate-400" aria-hidden />
              </div>
              <h3 className="text-base font-semibold text-slate-900">{title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-slate-600">{body}</p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}

/* ──────────────────────────────────────────────────────────────────── */
/* Framework sections                                                    */
/* ──────────────────────────────────────────────────────────────────── */

function FrameworkSections() {
  const sections = [
    { tag: "§2", title: "Commodity dependency", body: "IDR, OCS, BDI, HHI, SCI: how reliant a destination is on an origin for a given commodity." },
    { tag: "§3", title: "Consumption demand", body: "PCC, CRS, DIS: how culturally entrenched the commodity is in the destination's diet." },
    { tag: "§4", title: "Hazard signal", body: "HIS, HDI, DGI: severity weighted, time decayed alert pressure with detection gap diagnostics." },
    { tag: "§5", title: "Trade flow anomalies", body: "Unit value z scores, volume anomalies, mirror trade discrepancies, year on year concentration shifts." },
    { tag: "§6", title: "Origin attention network", body: "ORPS, ACEP, empirical hazard probability. Role aware aggregation following Pan et al. (2025)." },
    { tag: "§7", title: "Composite scoring", body: "Hybrid CVS with masked amplifier terms (Slice E1), neutral CRS fallback, percentile re anchored bands." },
  ];

  return (
    <section className="mx-auto max-w-6xl px-6 py-20">
      <div className="mb-8">
        <p className="text-xs font-semibold uppercase tracking-wider text-blue-600">
          What is in the engine
        </p>
        <h2 className="mt-2 max-w-2xl text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">
          Six sections of the framework, live on every corridor
        </h2>
        <p className="mt-3 max-w-2xl text-sm leading-relaxed text-slate-600">
          Sections 2 through 7 of the v1.0 mathematical framework are computed
          at startup. The methodology view documents the formula, inputs,
          scale bands, and Rust function for each metric.
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {sections.map((s) => (
          <div
            key={s.tag}
            className="rounded-xl border border-slate-200/80 bg-white p-5 shadow-sm"
          >
            <div className="flex items-center gap-2">
              <span className="font-mono text-xs font-semibold text-blue-600">
                {s.tag}
              </span>
              <h3 className="text-sm font-semibold text-slate-900">{s.title}</h3>
            </div>
            <p className="mt-2 text-xs leading-relaxed text-slate-600">{s.body}</p>
          </div>
        ))}
      </div>

      <div className="mt-8 flex flex-wrap items-center gap-3">
        <Link
          href="/dashboard/lab"
          className="inline-flex items-center gap-1.5 rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-slate-800"
        >
          See all 22 metrics
          <ArrowRight size={14} aria-hidden />
        </Link>
        <Link
          href="/dashboard/research"
          className="inline-flex items-center gap-1.5 text-sm font-medium text-slate-700 hover:text-blue-600"
        >
          Research mode and raw endpoints
          <Network size={14} aria-hidden />
        </Link>
      </div>
    </section>
  );
}

/* ──────────────────────────────────────────────────────────────────── */
/* Footer                                                                */
/* ──────────────────────────────────────────────────────────────────── */

function Footer() {
  return (
    <footer className="border-t border-slate-200/80 bg-white/80 py-10 backdrop-blur">
      <div className="mx-auto flex max-w-6xl flex-col gap-6 px-6 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-sm font-semibold text-slate-900">DefenseFood</p>
          <p className="mt-1 text-xs text-slate-500">
            Operational analytics for EU food fraud vulnerability, grounded in the
            published v1.0 mathematical framework.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-xs text-slate-500">
          <Link href="/dashboard" className="hover:text-slate-900">
            Dashboard
          </Link>
          <Link href="/dashboard/corridors" className="hover:text-slate-900">
            Corridors
          </Link>
          <Link href="/dashboard/network" className="hover:text-slate-900">
            Network
          </Link>
          <Link href="/dashboard/lab" className="hover:text-slate-900">
            Methodology
          </Link>
          <Link href="/dashboard/research" className="hover:text-slate-900">
            Research
          </Link>
        </div>
      </div>
    </footer>
  );
}

/* ──────────────────────────────────────────────────────────────────── */
/* Background                                                            */
/* ──────────────────────────────────────────────────────────────────── */

function BackgroundGlow() {
  return (
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
  );
}
