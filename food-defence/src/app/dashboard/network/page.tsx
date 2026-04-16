"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  Handle,
  Position,
  type Node,
  type Edge,
  type NodeMouseHandler,
  type NodeProps,
  type EdgeMouseHandler,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { api } from "@/lib/api";
import type { NetworkGraph } from "@/lib/types";
import { fmt, riskHex } from "@/lib/utils";

type CountryNodeData = {
  label: string;
  isEu: boolean;
  m49: number;
  corridorCount: number;
  totalHis: number;
};

type FlowEdgeData = { his: number; relHis: number; corridorCount: number };

const nodeTypes = { country: CountryNode };

function CountryNode({ data, selected }: NodeProps) {
  const d = data as CountryNodeData;
  const roleNote =
    "Colour shows EU membership only. This country may appear as importer or exporter depending on the corridor.";
  const title = `${d.label} (M49 ${d.m49})${d.isEu ? " · EU member" : " · Non-EU"}\n${d.corridorCount} corridor row(s) in this view · aggregate HIS ${fmt(d.totalHis, 3)}\n${roleNote}`;

  return (
    <div
      title={title}
      className={`rounded-lg px-2 py-1 text-center text-[10px] font-medium shadow-sm ${
        selected ? "ring-2 ring-blue-500 ring-offset-1" : ""
      }`}
      style={{
        background: d.isEu ? "#dbeafe" : "#fef3c7",
        border: `2px solid ${d.isEu ? "#3b82f6" : "#f59e0b"}`,
        width: "100%",
        height: "100%",
        boxSizing: "border-box",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <Handle type="target" position={Position.Left} className="!bg-slate-400 !h-2 !w-2" />
      <span className="truncate px-0.5">{d.label}</span>
      <Handle type="source" position={Position.Right} className="!bg-slate-400 !h-2 !w-2" />
    </div>
  );
}

/** Stable pseudo-random in [0, span) so layout does not jump on every render. */
function stableOffset(seed: number, span: number): number {
  let s = Math.abs(seed) % 2147483647;
  s = (s * 48271 + 12345) % 2147483647;
  return (s % 10000) / 10000 * span;
}

function buildFlowNodes(graph: NetworkGraph): Node[] {
  const maxHis = Math.max(...graph.nodes.map((n) => n.total_his), 0.001);
  const euNodes = graph.nodes.filter((n) => n.is_eu27);
  const nonEuNodes = graph.nodes.filter((n) => !n.is_eu27);

  const place = (n: (typeof graph.nodes)[0], index: number, isEu: boolean) => {
    const col = isEu
      ? 620 + stableOffset(n.m49 * 17 + index, 260)
      : 40 + stableOffset(n.m49 * 31 + index, 260);
    const row = 24 + (index % 12) * 72 + stableOffset(n.m49 * 7, 48);
    const w = Math.max(72, Math.min(140, 52 + (n.total_his / maxHis) * 70));
    const h = 34;
    return { col, row, w, h };
  };

  const out: Node[] = [];
  nonEuNodes.forEach((n, i) => {
    const { col, row, w, h } = place(n, i, false);
    out.push({
      id: String(n.m49),
      type: "country",
      position: { x: col, y: row },
      data: {
        label: n.name,
        isEu: false,
        m49: n.m49,
        corridorCount: n.corridor_count,
        totalHis: n.total_his,
      } satisfies CountryNodeData,
      width: w,
      height: h,
    });
  });
  euNodes.forEach((n, i) => {
    const { col, row, w, h } = place(n, i, true);
    out.push({
      id: String(n.m49),
      type: "country",
      position: { x: col, y: row },
      data: {
        label: n.name,
        isEu: true,
        m49: n.m49,
        corridorCount: n.corridor_count,
        totalHis: n.total_his,
      } satisfies CountryNodeData,
      width: w,
      height: h,
    });
  });
  return out;
}

function buildFlowEdges(graph: NetworkGraph): Edge<FlowEdgeData>[] {
  const maxHis = Math.max(...graph.edges.map((e) => e.his), 0.001);

  const edgeMap = new Map<string, { his: number; count: number }>();
  for (const e of graph.edges) {
    const key = `${e.origin_m49}-${e.destination_m49}`;
    const existing = edgeMap.get(key);
    if (existing) {
      existing.his += e.his;
      existing.count += 1;
    } else {
      edgeMap.set(key, { his: e.his, count: 1 });
    }
  }

  return Array.from(edgeMap.entries()).map(([key, { his, count }]) => {
    const [source, target] = key.split("-");
    const thickness = Math.max(1, Math.min(5, (his / maxHis) * 4 + 1));
    const relHis = his / maxHis;
    return {
      id: key,
      source,
      target,
      data: { his, relHis, corridorCount: count },
      style: {
        stroke: riskHex(his, maxHis),
        strokeWidth: thickness,
        opacity: 0.12 + relHis * 0.88,
      },
      animated: relHis > 0.5,
      interactionWidth: 16,
    };
  });
}

export default function ExposureNetworkPage() {
  const router = useRouter();
  const [graph, setGraph] = useState<NetworkGraph | null>(null);
  const [commodity, setCommodity] = useState<string>("");
  const [commodities, setCommodities] = useState<{ hs_code: string; names: string[] }[]>([]);
  const [loading, setLoading] = useState(true);
  /** Minimum relative link strength 0–100 (HIS / max HIS in view). Hides weaker links to reduce clutter. */
  const [linkFloorPct, setLinkFloorPct] = useState(0);
  const [edgeHint, setEdgeHint] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      api.network.graph(),
      api.commodities.list(),
    ]).then(([g, c]) => {
      setGraph(g);
      setCommodities(c.commodities);
      setLoading(false);
    });
  }, []);

  useEffect(() => {
    if (!loading) {
      api.network
        .graph(commodity || undefined)
        .then(setGraph);
    }
  }, [commodity, loading]);

  const onNodeClick: NodeMouseHandler = useCallback(
    (_, node) => {
      router.push(`/dashboard/countries/${node.id}`);
    },
    [router]
  );

  const onEdgeMouseEnter: EdgeMouseHandler = useCallback((_, edge) => {
    const d = edge.data as FlowEdgeData | undefined;
    if (d) {
      setEdgeHint(
        `Exporter → importer · merged HIS ${fmt(d.his, 3)} (${fmt(d.relHis * 100, 0)}% of strongest link) · ${d.corridorCount} commodity row(s)`
      );
    }
  }, []);

  const onEdgeMouseLeave = useCallback(() => setEdgeHint(null), []);

  const allEdges = useMemo(
    () => (graph ? buildFlowEdges(graph) : []),
    [graph]
  );

  const visibleEdges = useMemo(() => {
    const floor = linkFloorPct / 100;
    if (floor <= 0) return allEdges;
    return allEdges.filter((e) => (e.data?.relHis ?? 0) >= floor);
  }, [allEdges, linkFloorPct]);

  const nodes = useMemo(
    () => (graph ? buildFlowNodes(graph) : []),
    [graph]
  );

  const visibleEdgeCount = visibleEdges.length;

  if (loading || !graph) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" />
      </div>
    );
  }

  return (
    <div className="flex flex-col" style={{ height: "calc(100vh - 7rem)" }}>
      <div className="mb-3 flex flex-shrink-0 flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-lg font-bold text-slate-900">Trade and hazard network</h1>
          <p className="max-w-2xl text-xs text-slate-600">
            {graph.node_count} countries and {graph.edge_count} corridor links in this view (edges
            point from exporter to importer). Node size reflects aggregate HIS on all rows involving
            that country (as origin or destination). Edge colour and thickness reflect merged hazard
            intensity (HIS) for that country pair. Same country can be both EU and in multiple roles:
            colour only indicates EU membership. Click a country for its profile.
          </p>
        </div>

        <div className="flex flex-shrink-0 flex-col gap-2 sm:items-end">
          <div className="flex items-center gap-2 max-w-xs">
            <label htmlFor="network-commodity-filter" className="text-sm text-gray-600 shrink-0">
              Commodity
            </label>
            <select
              id="network-commodity-filter"
              value={commodity}
              onChange={(e) => setCommodity(e.target.value)}
              className="min-w-0 flex-1 rounded-lg border border-gray-200 px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-400"
            >
              <option value="">All commodities</option>
              {commodities.map((c) => (
                <option key={c.hs_code} value={c.hs_code}>
                  {c.hs_code} - {c.names[0]?.slice(0, 40)}
                </option>
              ))}
            </select>
          </div>
          <div className="flex w-full max-w-xs flex-col gap-1">
            <label htmlFor="network-link-floor" className="text-[11px] font-medium text-slate-600">
              Show links from {linkFloorPct}% of strongest hazard upward ({visibleEdgeCount} links)
            </label>
            <input
              id="network-link-floor"
              type="range"
              min={0}
              max={80}
              step={5}
              value={linkFloorPct}
              onChange={(e) => setLinkFloorPct(Number(e.target.value))}
              className="w-full accent-blue-600"
            />
          </div>
        </div>
      </div>

      <div className="mb-3 flex flex-shrink-0 flex-col gap-2 rounded-lg border border-slate-100 bg-slate-50/80 px-3 py-2 text-[10px] text-slate-600">
        <p className="font-medium text-slate-700">Legend</p>
        <div className="flex flex-wrap gap-x-4 gap-y-2">
          <span className="flex items-center gap-1.5">
            <span className="h-3 w-3 rounded border-2 border-blue-500 bg-blue-100" />
            EU member state
          </span>
          <span className="flex items-center gap-1.5">
            <span className="h-3 w-3 rounded border-2 border-amber-500 bg-amber-50" />
            Non-EU country
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-flex items-center text-slate-500">→</span>
            Trade direction (exporter toward importer), including EU→EU and non-EU→EU
          </span>
          <span className="flex items-center gap-1.5">
            <span className="h-0.5 w-5 bg-emerald-500" />
            Cooler / thinner link: lower merged HIS
          </span>
          <span className="flex items-center gap-1.5">
            <span className="h-0.5 w-5 bg-red-500" />
            Warmer / thicker link: higher merged HIS
          </span>
        </div>
      </div>

      {edgeHint && (
        <p className="mb-2 rounded-md border border-blue-100 bg-blue-50/90 px-3 py-1.5 text-[11px] text-slate-800">
          {edgeHint}
        </p>
      )}

      <div className="min-h-0 flex-1 rounded-xl border border-gray-200 bg-white shadow-sm">
        <div className="h-full w-full">
          <ReactFlow
            nodes={nodes}
            edges={visibleEdges}
            nodeTypes={nodeTypes}
            onNodeClick={onNodeClick}
            onEdgeMouseEnter={onEdgeMouseEnter}
            onEdgeMouseLeave={onEdgeMouseLeave}
            fitView
            minZoom={0.15}
            maxZoom={3}
            attributionPosition="bottom-left"
          >
            <Background gap={20} size={1} color="#f1f5f9" />
            <Controls position="top-left" />
            <MiniMap
              nodeStrokeWidth={2}
              zoomable
              pannable
              style={{ background: "#e2e8f0", width: 180, height: 120 }}
              className="!border !border-slate-300 !rounded-lg !shadow-sm"
              nodeColor={(n) => ((n.data?.isEu as boolean) ? "#3b82f6" : "#f59e0b")}
              nodeStrokeColor={(n) => ((n.data?.isEu as boolean) ? "#1d4ed8" : "#b45309")}
              maskColor="rgba(15, 23, 42, 0.12)"
              position="bottom-right"
            />
          </ReactFlow>
        </div>
      </div>
    </div>
  );
}
