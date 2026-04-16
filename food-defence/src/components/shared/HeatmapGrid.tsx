"use client";

import { useMemo } from "react";
import { riskHex } from "@/lib/utils";
import type { CorridorMetric } from "@/lib/types";

interface HeatmapGridProps {
  corridors: CorridorMetric[];
  maxRows?: number;
  maxCols?: number;
}

export default function HeatmapGrid({
  corridors,
  maxRows = 15,
  maxCols = 12,
}: HeatmapGridProps) {
  const { origins, commodities, cells } = useMemo(() => {
    // Aggregate: (origin, commodity_chapter) -> max HIS
    const cellMap = new Map<string, number>();
    const originHis = new Map<string, number>();
    const commodityHis = new Map<string, number>();

    for (const c of corridors) {
      const chapter = c.commodity_hs.slice(0, 2);
      const key = `${c.origin_country}|${chapter}`;
      cellMap.set(key, Math.max(cellMap.get(key) ?? 0, c.his));
      originHis.set(
        c.origin_country,
        (originHis.get(c.origin_country) ?? 0) + c.his
      );
      commodityHis.set(chapter, (commodityHis.get(chapter) ?? 0) + c.his);
    }

    // Sort by total HIS, take top N
    const origins = [...originHis.entries()]
      .sort((a, b) => b[1] - a[1])
      .slice(0, maxRows)
      .map(([name]) => name);
    const commodities = [...commodityHis.entries()]
      .sort((a, b) => b[1] - a[1])
      .slice(0, maxCols)
      .map(([ch]) => ch);

    return { origins, commodities, cells: cellMap };
  }, [corridors, maxRows, maxCols]);

  if (origins.length === 0) return null;

  const maxHis = Math.max(
    ...Array.from(cells.values()),
    0.001
  );

  return (
    <div className="overflow-x-auto">
      <table className="text-[10px]">
        <thead>
          <tr>
            <th className="pr-2 pb-1 text-left text-gray-500 font-medium">
              Origin \ HS
            </th>
            {commodities.map((ch) => (
              <th
                key={ch}
                className="px-1 pb-1 text-center text-gray-500 font-medium w-8"
              >
                {ch}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {origins.map((origin) => (
            <tr key={origin}>
              <td className="pr-2 py-0.5 text-gray-700 font-medium whitespace-nowrap max-w-[100px] truncate">
                {origin}
              </td>
              {commodities.map((ch) => {
                const val = cells.get(`${origin}|${ch}`) ?? 0;
                return (
                  <td key={ch} className="px-0.5 py-0.5">
                    <div
                      className="w-7 h-5 rounded-sm"
                      style={{
                        backgroundColor:
                          val > 0 ? riskHex(val, maxHis) : "#f8fafc",
                        opacity: val > 0 ? 0.3 + (val / maxHis) * 0.7 : 1,
                      }}
                      title={`${origin}, HS chapter ${ch}: hazard intensity ${val.toFixed(3)} (higher = stronger signal)`}
                    />
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
