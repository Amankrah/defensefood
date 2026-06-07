"use client";

import { useEffect, useState } from "react";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Crosshair,
  Minus,
  RefreshCw,
  TrendingDown,
  TrendingUp,
} from "lucide-react";
import {
  type ForecastResponse,
  fetchForecast,
} from "@/lib/agentApi";

interface ForecastCardProps {
  commodity_hs: string;
  destination_m49: number;
  origin_m49: number;
}

interface LoadState {
  phase: "loading" | "ready" | "error";
  response?: ForecastResponse;
  errorMessage?: string;
}

const CVS_FMT = new Intl.NumberFormat("en-US", {
  minimumFractionDigits: 3,
  maximumFractionDigits: 3,
});

const DIRECTION_STYLE = {
  rising: {
    label: "Rising",
    icon: TrendingUp,
    pill: "bg-rose-100 text-rose-700",
    accent: "border-rose-200 from-rose-50/40 to-white",
  },
  falling: {
    label: "Falling",
    icon: TrendingDown,
    pill: "bg-emerald-100 text-emerald-700",
    accent: "border-emerald-200 from-emerald-50/40 to-white",
  },
  stable: {
    label: "Stable",
    icon: Minus,
    pill: "bg-slate-100 text-slate-700",
    accent: "border-slate-200 from-slate-50/40 to-white",
  },
} as const;

const CONFIDENCE_STYLE = {
  high: "bg-emerald-100 text-emerald-700",
  med: "bg-amber-100 text-amber-800",
  low: "bg-slate-100 text-slate-600",
} as const;

/**
 * Forecast card for the lane forensic page.
 *
 * Fast, no-LLM tile: hits the server-side ``predict_lane_next_period``
 * tool which reads a model trained at startup. No SSE, no opt-in button —
 * the forecast is cheap enough to fetch automatically on mount.
 *
 * Renders three states:
 *
 * - **loading**: a small spinner while the request is in flight.
 * - **unavailable**: a "model not available" notice with the server's
 *   reason (model not trained, no history, etc.). Not an error — the lane
 *   is just out of the model's reach.
 * - **ready**: observed CVS, predicted CVS with 80% interval, direction,
 *   confidence, top drivers.
 */
export default function ForecastCard({
  commodity_hs,
  destination_m49,
  origin_m49,
}: ForecastCardProps) {
  const [state, setState] = useState<LoadState>({ phase: "loading" });

  const load = () => {
    setState({ phase: "loading" });
    fetchForecast(commodity_hs, destination_m49, origin_m49)
      .then((response) => setState({ phase: "ready", response }))
      .catch((e) =>
        setState({
          phase: "error",
          errorMessage: e instanceof Error ? e.message : String(e),
        })
      );
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [commodity_hs, destination_m49, origin_m49]);

  if (state.phase === "loading") {
    return (
      <section className="rounded-2xl border border-blue-100 bg-white p-5 shadow-sm">
        <Header />
        <p className="mt-3 flex items-center gap-2 text-xs text-slate-500">
          <Activity size={12} className="animate-pulse" aria-hidden />
          Running next-period forecast…
        </p>
      </section>
    );
  }

  if (state.phase === "error") {
    return (
      <section className="rounded-2xl border border-red-200 bg-red-50/30 p-5 shadow-sm">
        <Header />
        <div className="mt-3 flex items-start gap-2 text-sm text-red-700">
          <AlertTriangle size={14} className="mt-0.5 shrink-0" aria-hidden />
          <div>
            <p className="font-semibold">Couldn&apos;t fetch the forecast.</p>
            <p className="mt-0.5 text-xs text-red-600">{state.errorMessage}</p>
            <button
              type="button"
              onClick={load}
              className="mt-2 inline-flex items-center gap-1 rounded border border-red-200 px-2 py-1 text-xs text-red-700 hover:bg-red-50"
            >
              <RefreshCw size={12} aria-hidden /> Try again
            </button>
          </div>
        </div>
      </section>
    );
  }

  const r = state.response!;
  if (!r.ok) {
    return (
      <section className="rounded-2xl border border-slate-200 bg-slate-50/40 p-5 shadow-sm">
        <Header />
        <p className="mt-3 text-xs text-slate-600">
          <span className="font-medium text-slate-800">
            Model forecast not available for this lane.
          </span>{" "}
          <span className="text-slate-500">{r.reason}</span>
        </p>
      </section>
    );
  }

  const direction = DIRECTION_STYLE[r.direction];
  const DirectionIcon = direction.icon;
  const observedCvs = r.observed.cvs;
  const point = r.cvs_point;
  const delta =
    observedCvs != null && point != null ? point - observedCvs : null;

  return (
    <section
      className={`rounded-2xl border bg-gradient-to-br p-5 shadow-sm ${direction.accent}`}
    >
      <Header />

      <div className="mt-3 grid grid-cols-1 gap-4 md:grid-cols-3">
        <Tile label={`Observed (${r.as_of_period})`}>
          <p className="font-mono text-2xl font-semibold text-slate-900">
            {observedCvs != null ? CVS_FMT.format(observedCvs) : "—"}
          </p>
          <p className="mt-0.5 text-[10px] text-slate-500">CVS most recent</p>
        </Tile>

        <Tile label={`Forecast (${r.target_period})`}>
          <p className="font-mono text-2xl font-semibold text-slate-900">
            {point != null ? CVS_FMT.format(point) : "—"}
          </p>
          {r.cvs_low != null && r.cvs_high != null && (
            <p className="mt-0.5 font-mono text-[10px] text-slate-500">
              80% interval [{CVS_FMT.format(r.cvs_low)}, {CVS_FMT.format(r.cvs_high)}]
            </p>
          )}
        </Tile>

        <Tile label="Direction">
          <p className="flex items-center gap-2">
            <span
              className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ${direction.pill}`}
            >
              <DirectionIcon size={11} aria-hidden /> {direction.label}
            </span>
            {delta != null && (
              <span className="font-mono text-[11px] text-slate-500">
                Δ{delta >= 0 ? "+" : ""}
                {CVS_FMT.format(delta)}
              </span>
            )}
          </p>
          <p className="mt-1">
            <span
              className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium ${CONFIDENCE_STYLE[r.confidence]}`}
            >
              <Crosshair size={10} aria-hidden /> Confidence: {r.confidence}
            </span>
          </p>
        </Tile>
      </div>

      {r.drivers.length > 0 && (
        <div className="mt-3 rounded-lg border border-slate-100 bg-white/80 p-3">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">
            Drivers
          </p>
          <ul className="mt-1 grid grid-cols-1 gap-x-3 gap-y-0.5 font-mono text-[11px] text-slate-700 sm:grid-cols-3">
            {r.drivers.slice(0, 6).map((d, i) => (
              <li key={i} className="truncate">
                <span className="text-slate-400">·</span> {d}
              </li>
            ))}
          </ul>
        </div>
      )}

      {r.notes.length > 0 && (
        <p className="mt-2 text-[10px] italic text-slate-500">
          {r.notes.join(" · ")}
        </p>
      )}

      <p className="mt-3 text-[10px] text-slate-400">
        Forecast trained at server startup on every loaded period except the
        latest. The 80% interval is calibrated against training residuals.
        Model is a peer voice, not an oracle.
      </p>
    </section>
  );
}

function Header() {
  return (
    <div className="flex items-center gap-2">
      <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-blue-500 to-indigo-600 text-white shadow-sm">
        <CheckCircle2 size={14} strokeWidth={2.25} aria-hidden />
      </span>
      <span className="text-xs font-semibold uppercase tracking-wider text-blue-700">
        Next-period forecast
      </span>
    </div>
  );
}

function Tile({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-lg border border-slate-100 bg-white/70 p-3">
      <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">
        {label}
      </p>
      <div className="mt-1">{children}</div>
    </div>
  );
}
