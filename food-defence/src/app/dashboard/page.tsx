"use client";

import { useEffect, useState } from "react";
import {
  api,
  type CorridorMetric,
  type RasffSummary,
  type OriginRisk,
} from "@/lib/api";
import {
  AlertTriangle,
  BarChart3,
  Network,
  Shield,
  TrendingUp,
} from "lucide-react";

function StatCard({
  label,
  value,
  icon: Icon,
  color,
}: {
  label: string;
  value: string | number;
  icon: React.ElementType;
  color: string;
}) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
      <div className="flex items-center gap-3 mb-2">
        <div className={`rounded-lg p-2 ${color}`}>
          <Icon size={18} className="text-white" />
        </div>
        <span className="text-sm text-gray-500">{label}</span>
      </div>
      <p className="text-2xl font-semibold text-gray-900">{value}</p>
    </div>
  );
}

function CorridorTable({ corridors }: { corridors: CorridorMetric[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-200 text-left text-gray-500">
            <th className="pb-3 pr-4 font-medium">Corridor</th>
            <th className="pb-3 pr-4 font-medium">Commodity</th>
            <th className="pb-3 pr-4 font-medium text-right">HIS</th>
            <th className="pb-3 pr-4 font-medium text-right">HDI</th>
            <th className="pb-3 pr-4 font-medium text-right">Notifications</th>
            <th className="pb-3 font-medium text-right">Severity</th>
          </tr>
        </thead>
        <tbody>
          {corridors.map((c, i) => (
            <tr
              key={`${c.commodity_hs}-${c.origin_m49}-${c.destination_m49}-${i}`}
              className="border-b border-gray-100 hover:bg-gray-50"
            >
              <td className="py-3 pr-4">
                <span className="font-medium text-gray-900">
                  {c.origin_country}
                </span>
                <span className="text-gray-400 mx-1">&rarr;</span>
                <span className="text-gray-700">{c.destination_country}</span>
              </td>
              <td className="py-3 pr-4">
                <span className="text-gray-600 text-xs">{c.commodity_hs}</span>{" "}
                <span className="text-gray-800">
                  {c.commodity_name?.slice(0, 40)}
                  {(c.commodity_name?.length ?? 0) > 40 ? "..." : ""}
                </span>
              </td>
              <td className="py-3 pr-4 text-right font-mono">
                <span
                  className={
                    c.his > 0.3
                      ? "text-red-600 font-semibold"
                      : c.his > 0.1
                      ? "text-amber-600"
                      : "text-gray-600"
                  }
                >
                  {c.his.toFixed(3)}
                </span>
              </td>
              <td className="py-3 pr-4 text-right font-mono text-gray-600">
                {c.hdi.toFixed(3)}
              </td>
              <td className="py-3 pr-4 text-right font-mono text-gray-600">
                {c.notification_count}
              </td>
              <td className="py-3 text-right font-mono text-gray-600">
                {c.severity_total.toFixed(2)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function OriginTable({ origins }: { origins: OriginRisk[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-200 text-left text-gray-500">
            <th className="pb-3 pr-4 font-medium">Origin Country</th>
            <th className="pb-3 pr-4 font-medium text-right">Total HIS</th>
            <th className="pb-3 pr-4 font-medium text-right">Total Severity</th>
            <th className="pb-3 font-medium text-right">Corridors</th>
          </tr>
        </thead>
        <tbody>
          {origins.map((o) => (
            <tr
              key={o.origin_m49}
              className="border-b border-gray-100 hover:bg-gray-50"
            >
              <td className="py-3 pr-4 font-medium text-gray-900">
                {o.name}
              </td>
              <td className="py-3 pr-4 text-right font-mono text-gray-600">
                {o.total_his.toFixed(3)}
              </td>
              <td className="py-3 pr-4 text-right font-mono text-gray-600">
                {o.total_severity.toFixed(2)}
              </td>
              <td className="py-3 text-right font-mono text-gray-600">
                {o.corridor_count}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function DashboardPage() {
  const [summary, setSummary] = useState<RasffSummary | null>(null);
  const [topCorridors, setTopCorridors] = useState<CorridorMetric[]>([]);
  const [origins, setOrigins] = useState<OriginRisk[]>([]);
  const [networkStats, setNetworkStats] = useState({ node_count: 0, edge_count: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const [summ, corr, net, orig] = await Promise.all([
          api.hazards.summary(),
          api.corridors.top(20, "his"),
          api.network.summary(),
          api.network.origins(10),
        ]);
        setSummary(summ);
        setTopCorridors(corr.corridors);
        setNetworkStats(net);
        setOrigins(orig.origins);
      } catch (e) {
        setError(
          e instanceof Error ? e.message : "Failed to connect to API"
        );
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="text-center">
          <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-blue-600 mx-auto mb-4" />
          <p className="text-gray-500">Loading vulnerability data...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="bg-white rounded-xl shadow-sm border border-red-200 p-8 max-w-md">
          <AlertTriangle className="text-red-500 mb-3" size={32} />
          <h2 className="text-lg font-semibold text-gray-900 mb-2">
            API Connection Error
          </h2>
          <p className="text-gray-600 text-sm mb-4">{error}</p>
          <p className="text-gray-400 text-xs">
            Make sure the FastAPI backend is running on port 8000:
            <br />
            <code className="bg-gray-100 px-2 py-1 rounded mt-1 inline-block">
              cd backend && PYTHONPATH=. uvicorn defensefood.api.main:app --port
              8000
            </code>
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 px-6 py-4">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-gray-900">
              DefenseFood
            </h1>
            <p className="text-sm text-gray-500">
              EU Food Fraud Vulnerability Intelligence System
            </p>
          </div>
          <div className="flex items-center gap-2 text-xs text-gray-400">
            <Shield size={14} />
            <span>
              Period: {summary?.current_period ?? "N/A"}
            </span>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-6 space-y-6">
        {/* Stats Grid */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard
            label="RASFF Notifications"
            value={summary?.total_notifications ?? 0}
            icon={AlertTriangle}
            color="bg-red-500"
          />
          <StatCard
            label="Trade Corridors"
            value={summary?.total_corridors ?? 0}
            icon={TrendingUp}
            color="bg-blue-500"
          />
          <StatCard
            label="Network Nodes"
            value={networkStats.node_count}
            icon={Network}
            color="bg-purple-500"
          />
          <StatCard
            label="Unique Commodities"
            value={summary?.unique_commodities ?? 0}
            icon={BarChart3}
            color="bg-emerald-500"
          />
        </div>

        {/* Two-column layout */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Top Corridors -- takes 2/3 */}
          <div className="lg:col-span-2 bg-white rounded-xl border border-gray-200 shadow-sm p-5">
            <h2 className="text-base font-semibold text-gray-900 mb-4">
              Top Corridors by Hazard Intensity
            </h2>
            <CorridorTable corridors={topCorridors} />
          </div>

          {/* Origin Risk -- takes 1/3 */}
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
            <h2 className="text-base font-semibold text-gray-900 mb-4">
              Highest-Risk Origins
            </h2>
            <OriginTable origins={origins} />
          </div>
        </div>

        {/* Data Coverage */}
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
          <h2 className="text-base font-semibold text-gray-900 mb-3">
            Data Coverage
          </h2>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4 text-sm">
            <div>
              <p className="text-gray-500">Origin Countries</p>
              <p className="font-semibold text-gray-900">
                {summary?.unique_origins ?? 0}
              </p>
            </div>
            <div>
              <p className="text-gray-500">Destination Countries</p>
              <p className="font-semibold text-gray-900">
                {summary?.unique_destinations ?? 0}
              </p>
            </div>
            <div>
              <p className="text-gray-500">Rust Notifications</p>
              <p className="font-semibold text-gray-900">
                {summary?.notification_objects_built ?? 0}
              </p>
            </div>
            <div>
              <p className="text-gray-500">Network Edges</p>
              <p className="font-semibold text-gray-900">
                {networkStats.edge_count}
              </p>
            </div>
            <div>
              <p className="text-gray-500">Unmapped Origins</p>
              <p className="font-semibold text-gray-900">
                {summary?.unmapped_origins?.length ?? 0}
              </p>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
