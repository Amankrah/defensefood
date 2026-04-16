"use client";

import {
  Radar,
  RadarChart as RechartsRadar,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  ResponsiveContainer,
} from "recharts";

interface RadarChartProps {
  data: { axis: string; value: number }[];
  color?: string;
}

export default function RadarChart({
  data,
  color = "#3b82f6",
}: RadarChartProps) {
  return (
    <ResponsiveContainer width="100%" height={240}>
      <RechartsRadar data={data} cx="50%" cy="50%" outerRadius="75%">
        <PolarGrid stroke="#e2e8f0" />
        <PolarAngleAxis dataKey="axis" tick={{ fontSize: 11, fill: "#6b7280" }} />
        <PolarRadiusAxis
          domain={[0, 1]}
          tick={{ fontSize: 9, fill: "#9ca3af" }}
          tickCount={5}
        />
        <Radar
          dataKey="value"
          stroke={color}
          fill={color}
          fillOpacity={0.2}
          strokeWidth={2}
        />
      </RechartsRadar>
    </ResponsiveContainer>
  );
}
