"use client";

import { PieChart, Pie, Cell } from "recharts";
import { riskHex } from "@/lib/utils";

interface GaugeChartProps {
  value: number;
  max?: number;
  label: string;
  sublabel?: string;
  size?: number;
}

export default function GaugeChart({
  value,
  max = 1,
  label,
  sublabel,
  size = 140,
}: GaugeChartProps) {
  const clamped = Math.min(Math.max(value, 0), max);
  const ratio = clamped / max;
  const data = [
    { value: ratio },
    { value: 1 - ratio },
  ];
  const color = riskHex(value, max);

  return (
    <div className="flex flex-col items-center">
      <PieChart width={size} height={size / 2 + 10}>
        <Pie
          data={data}
          cx={size / 2}
          cy={size / 2}
          startAngle={180}
          endAngle={0}
          innerRadius={size / 2 - 20}
          outerRadius={size / 2 - 6}
          dataKey="value"
          stroke="none"
        >
          <Cell fill={color} />
          <Cell fill="#f1f5f9" />
        </Pie>
      </PieChart>
      <div className="text-center -mt-2">
        <p className="text-lg font-semibold font-mono text-gray-900">
          {isNaN(value) ? "N/A" : value.toFixed(3)}
        </p>
        <p className="text-xs font-medium text-gray-600">{label}</p>
        {sublabel && (
          <p className="text-[10px] text-gray-400">{sublabel}</p>
        )}
      </div>
    </div>
  );
}
