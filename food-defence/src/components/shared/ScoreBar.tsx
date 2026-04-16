"use client";

interface ScoreBarProps {
  segments: { label: string; value: number; color: string }[];
  total?: number;
}

export default function ScoreBar({ segments, total }: ScoreBarProps) {
  const sum = total ?? segments.reduce((s, seg) => s + seg.value, 0);
  if (sum <= 0) return <div className="text-xs text-gray-400">No data</div>;

  return (
    <div>
      <div className="flex h-6 rounded-lg overflow-hidden bg-gray-100">
        {segments.map((seg, i) => {
          const pct = (seg.value / sum) * 100;
          if (pct < 0.5) return null;
          return (
            <div
              key={i}
              className="transition-all"
              style={{ width: `${pct}%`, backgroundColor: seg.color }}
              title={`${seg.label}: ${seg.value.toFixed(3)} (${pct.toFixed(1)}%)`}
            />
          );
        })}
      </div>
      <div className="flex flex-wrap gap-3 mt-2">
        {segments.map((seg, i) => (
          <div key={i} className="flex items-center gap-1.5 text-[11px]">
            <div
              className="w-2.5 h-2.5 rounded-sm"
              style={{ backgroundColor: seg.color }}
            />
            <span className="text-gray-600">{seg.label}</span>
            <span className="font-mono text-gray-800">
              {seg.value.toFixed(3)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
