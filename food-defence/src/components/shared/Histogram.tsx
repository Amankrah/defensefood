"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

interface HistogramProps {
  bins: { x0: number; x1: number; count: number }[];
  /** Vertical reference lines (e.g. P25/P50/P75/P90). */
  markers?: { value: number; label: string; color?: string }[];
  height?: number;
  /** Decimals for x-axis tick formatting. */
  precision?: number;
}

const DEFAULT_MARKER_COLORS = ["#94a3b8", "#3b82f6", "#94a3b8", "#f97316"];

export default function Histogram({
  bins,
  markers = [],
  height = 220,
  precision = 2,
}: HistogramProps) {
  if (!bins.length) {
    return (
      <div className="flex h-32 items-center justify-center rounded-lg border border-dashed border-slate-200 bg-slate-50 text-xs text-slate-500">
        No data available for this distribution.
      </div>
    );
  }

  const data = bins.map((b, i) => ({
    index: i,
    label: b.x0.toFixed(precision),
    midpoint: (b.x0 + b.x1) / 2,
    count: b.count,
    range: `${b.x0.toFixed(precision)}–${b.x1.toFixed(precision)}`,
  }));

  const xMin = bins[0].x0;
  const xMax = bins[bins.length - 1].x1;

  return (
    <div>
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
          <XAxis
            dataKey="midpoint"
            type="number"
            domain={[xMin, xMax]}
            tick={{ fontSize: 10 }}
            tickFormatter={(v) => Number(v).toFixed(precision)}
          />
          <YAxis tick={{ fontSize: 10 }} allowDecimals={false} />
          <Tooltip
            cursor={{ fill: "rgba(59, 130, 246, 0.08)" }}
            formatter={(value) => [value as number, "count"]}
            labelFormatter={(_, payload) => {
              const row = payload?.[0]?.payload as
                | { range: string }
                | undefined;
              return row ? `Range ${row.range}` : "";
            }}
            contentStyle={{ fontSize: 11 }}
          />
          {markers.map((m, i) => (
            <ReferenceLine
              key={`${m.label}-${i}`}
              x={m.value}
              stroke={m.color ?? DEFAULT_MARKER_COLORS[i % DEFAULT_MARKER_COLORS.length]}
              strokeDasharray="4 3"
              label={{
                value: m.label,
                position: "top",
                fontSize: 10,
                fill: m.color ?? DEFAULT_MARKER_COLORS[i % DEFAULT_MARKER_COLORS.length],
              }}
            />
          ))}
          <Bar dataKey="count" fill="#3b82f6">
            {data.map((_, i) => (
              <Cell key={i} fill="#3b82f6" />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
