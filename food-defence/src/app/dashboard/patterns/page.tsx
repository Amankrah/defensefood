"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle, ArrowLeft, Sparkles } from "lucide-react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { CorridorMetric, ScoringConfig } from "@/lib/types";
import HeatmapGrid from "@/components/shared/HeatmapGrid";
import ScoreConfigPanel from "@/components/shared/ScoreConfigPanel";

export default function Patterns() {
  const router = useRouter();
  const [corridors, setCorridors] = useState<CorridorMetric[]>([]);
  const [config, setConfig] = useState<ScoringConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [recalcing, setRecalcing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const [all, cfg] = await Promise.all([
          api.corridors.list("limit=1000"),
          api.scoring.config(),
        ]);
        setCorridors(all.corridors);
        setConfig(cfg);
      } catch (e) {
        setError(e instanceof Error ? e.message : "API unreachable");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  async function handleRecalculate(next: ScoringConfig) {
    setRecalcing(true);
    try {
      await api.scoring.recalculate(next);
      setConfig(next);
      // Bounce back to Today so the user sees the rescored queue immediately.
      router.push("/dashboard");
    } finally {
      setRecalcing(false);
    }
  }

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <div className="h-9 w-9 animate-spin rounded-full border-2 border-slate-200 border-t-blue-600" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-2xl border border-red-200 bg-red-50 p-6">
        <AlertTriangle className="mb-2 text-red-500" size={20} aria-hidden />
        <p className="text-sm text-red-700">{error}</p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-7xl space-y-5">
      <header className="flex items-start gap-4">
        <Link
          href="/dashboard"
          className="mt-1 rounded-lg p-1.5 hover:bg-slate-100"
          title="Back to Today"
        >
          <ArrowLeft size={16} />
        </Link>
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wider text-blue-600/90">
            Exploration
          </p>
          <h1 className="flex items-center gap-2 text-xl font-bold tracking-tight text-slate-900">
            <Sparkles size={18} className="text-blue-600" aria-hidden />
            Patterns
          </h1>
          <p className="mt-1 max-w-2xl text-sm text-slate-600">
            Where hazard activity clusters across origins and product chapters,
            plus the scoring weights that drive the priority queue. Treat this
            as an exploration view — the actionable queue lives on Today.
          </p>
        </div>
      </header>

      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="text-sm font-semibold text-slate-900">
          Where hazard signals concentrate
        </h2>
        <p className="mb-4 text-xs text-slate-600">
          Each cell is an origin country × HS chapter pair. Darker = stronger
          hazard intensity (HIS) in the loaded data. Hover a cell for the
          numeric value.
        </p>
        <HeatmapGrid corridors={corridors} maxRows={20} maxCols={14} />
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="text-sm font-semibold text-slate-900">
          Priority score weights
        </h2>
        <p className="mb-4 text-xs text-slate-600">
          Adjust how hazard signals, price anomalies, and supply-chain stress
          feed the combined priority score. After recalculating, you will be
          taken back to Today to see the new ranking.
        </p>
        {config && (
          <ScoreConfigPanel
            config={config}
            onRecalculate={handleRecalculate}
            loading={recalcing}
          />
        )}
      </section>
    </div>
  );
}
