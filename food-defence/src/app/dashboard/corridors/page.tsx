"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { CorridorMetric } from "@/lib/types";
import { riskColor, fmt, truncate } from "@/lib/utils";
import DataTable, { type Column } from "@/components/shared/DataTable";

const COLUMNS: Column<CorridorMetric>[] = [
  {
    key: "origin_country",
    label: "Origin",
    headerDescription: "Exporting country for this lane.",
    type: "string",
    render: (r) => <span className="font-medium">{r.origin_country}</span>,
  },
  {
    key: "destination_country",
    label: "Destination",
    headerDescription: "Importing country.",
    type: "string",
  },
  {
    key: "commodity_hs",
    label: "HS code",
    headerDescription: "Harmonised system product code.",
    type: "string",
    render: (r) => <span className="font-mono text-xs">{r.commodity_hs}</span>,
  },
  {
    key: "commodity_name",
    label: "Commodity",
    headerDescription: "Plain language product name.",
    type: "string",
    render: (r) => <span title={r.commodity_name}>{truncate(r.commodity_name, 30)}</span>,
  },
  {
    key: "his",
    label: "Hazard",
    headerDescription:
      "Hazard intensity (HIS): strength of RASFF-linked signals on this lane (higher = more concern).",
    type: "number",
    render: (r) => (
      <span className={`font-mono font-semibold ${riskColor(r.his, 0.5)}`}>
        {fmt(r.his)}
      </span>
    ),
  },
  {
    key: "hdi",
    label: "Diversity",
    headerDescription:
      "Hazard diversity (HDI): spread of hazard types; helps distinguish repeated vs varied issues.",
    type: "number",
  },
  {
    key: "notification_count",
    label: "Alerts",
    headerDescription: "RASFF notifications tied to this corridor in the loaded period.",
    type: "number",
    render: (r) => <span className="font-mono">{r.notification_count}</span>,
  },
  {
    key: "severity_total",
    label: "Alert weight",
    headerDescription: "Cumulative seriousness of those alerts (weighted).",
    type: "number",
    render: (r) => <span className="font-mono">{fmt(r.severity_total, 2)}</span>,
  },
  {
    key: "cvs",
    label: "Priority",
    headerDescription:
      "Combined vulnerability score (CVS), 0 to 1: higher means review sooner.",
    type: "number",
    render: (r) => (
      <span className={`font-mono font-semibold ${riskColor(r.cvs ?? 0, 0.5)}`}>
        {r.cvs != null ? fmt(r.cvs) : "-"}
      </span>
    ),
  },
];

export default function CorridorExplorer() {
  const router = useRouter();
  const [corridors, setCorridors] = useState<CorridorMetric[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.corridors
      .list("limit=1000")
      .then((r) => setCorridors(r.corridors))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-bold text-slate-900">Corridor list</h1>
        <p className="text-xs text-slate-600">
          {corridors.length} lanes loaded. Hover column titles for what each score means. Open a row
          for full diagnostics.
        </p>
      </div>

      <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
        <DataTable
          columns={COLUMNS}
          data={corridors}
          onRowClick={(c) =>
            router.push(
              `/dashboard/corridors/${c.commodity_hs}/${c.destination_m49}/${c.origin_m49}`
            )
          }
          searchKeys={[
            "origin_country",
            "destination_country",
            "commodity_name",
            "commodity_hs",
          ]}
          pageSize={30}
        />
      </div>
    </div>
  );
}
