"use client";

import { useState } from "react";
import { Settings, RefreshCw } from "lucide-react";
import type { ScoringConfig } from "@/lib/types";

interface ScoreConfigPanelProps {
  config: ScoringConfig;
  onRecalculate: (config: ScoringConfig) => Promise<void>;
  loading?: boolean;
}

export default function ScoreConfigPanel({
  config: initial,
  onRecalculate,
  loading = false,
}: ScoreConfigPanelProps) {
  const [config, setConfig] = useState<ScoringConfig>(initial);
  const [open, setOpen] = useState(false);

  function updateField(key: keyof ScoringConfig, value: number | string) {
    setConfig((prev) => ({ ...prev, [key]: value }));
  }

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between p-4 text-sm font-medium text-gray-700 hover:text-gray-900"
      >
        <span className="flex items-center gap-2">
          <Settings size={15} aria-hidden />
          How priority scores are blended
        </span>
        <span className="text-xs text-gray-400">{open ? "Close" : "Open"}</span>
      </button>

      {open && (
        <div className="space-y-3 border-t border-gray-100 px-4 pb-4 pt-3">
          <p className="text-[11px] leading-relaxed text-slate-600">
            These settings change how hazard, trade, and structural inputs feed the combined
            priority score (CVS). Recalculate after edits so tables and heatmaps match your policy.
          </p>
          <div>
            <label
              htmlFor="score-config-blend-mode"
              className="mb-1 block text-[11px] font-medium text-gray-500"
            >
              Blend mode
            </label>
            <select
              id="score-config-blend-mode"
              value={config.composition_method}
              onChange={(e) =>
                updateField("composition_method", e.target.value)
              }
              className="w-full rounded-lg border border-gray-200 px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-400"
            >
              <option value="hybrid">Hybrid (Structural Base + Amplifier)</option>
              <option value="weighted_linear">Weighted Linear</option>
              <option value="geometric_mean">Geometric Mean</option>
            </select>
          </div>

          <div>
            <label
              htmlFor="score-config-normalisation"
              className="mb-1 block text-[11px] font-medium text-gray-500"
            >
              Scale across corridors
            </label>
            <select
              id="score-config-normalisation"
              value={config.normalisation_method}
              onChange={(e) =>
                updateField("normalisation_method", e.target.value)
              }
              className="w-full rounded-lg border border-gray-200 px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-400"
            >
              <option value="percentile_rank">Percentile Rank</option>
              <option value="min_max">Min-Max</option>
              <option value="log_percentile">Log-Percentile</option>
            </select>
          </div>

          <div>
            <label
              htmlFor="score-config-alpha-decay"
              className="mb-1 flex justify-between text-[11px] font-medium text-gray-500"
            >
              <span>How fast older alerts fade (alpha)</span>
              <span className="font-mono">{config.alpha_decay.toFixed(2)}</span>
            </label>
            <input
              id="score-config-alpha-decay"
              type="range"
              min="0.80"
              max="0.99"
              step="0.01"
              value={config.alpha_decay}
              onChange={(e) =>
                updateField("alpha_decay", parseFloat(e.target.value))
              }
              className="w-full"
            />
            <div className="flex justify-between text-[9px] text-gray-400">
              <span>Fast decay (perishable)</span>
              <span>Slow decay (shelf-stable)</span>
            </div>
          </div>

          {/* Weights */}
          {[
            { key: "w_hazard" as const, label: "Weight: hazard signals" },
            { key: "w_price" as const, label: "Weight: price anomalies" },
            { key: "w_supply_chain" as const, label: "Weight: supply chain stress" },
          ].map(({ key, label }) => (
            <div key={key}>
              <label
                htmlFor={`score-config-weight-${key}`}
                className="mb-1 flex justify-between text-[11px] font-medium text-gray-500"
              >
                <span>{label}</span>
                <span className="font-mono">{(config[key] as number).toFixed(1)}</span>
              </label>
              <input
                id={`score-config-weight-${key}`}
                type="range"
                min="0"
                max="3"
                step="0.1"
                value={config[key] as number}
                onChange={(e) =>
                  updateField(key, parseFloat(e.target.value))
                }
                className="w-full"
              />
            </div>
          ))}

          {/* Recalculate */}
          <button
            onClick={() => onRecalculate(config)}
            disabled={loading}
            className="w-full flex items-center justify-center gap-2 bg-blue-600 text-white text-sm font-medium py-2 rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
          >
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
            {loading ? "Recalculating…" : "Recalculate priorities"}
          </button>
        </div>
      )}
    </div>
  );
}
