import Link from "next/link";
import { Shield, BarChart3, Network, ArrowRight } from "lucide-react";

export default function Home() {
  return (
    <main className="min-h-screen bg-gray-50 flex items-center justify-center">
      <div className="max-w-2xl mx-auto px-6 py-16 text-center">
        <div className="flex justify-center mb-6">
          <div className="bg-blue-600 rounded-2xl p-4">
            <Shield size={40} className="text-white" />
          </div>
        </div>
        <h1 className="text-3xl font-bold text-gray-900 mb-3">
          DefenseFood
        </h1>
        <p className="text-lg text-gray-500 mb-8">
          EU Food Fraud Vulnerability Intelligence System
        </p>
        <p className="text-sm text-gray-400 mb-10 max-w-md mx-auto">
          Quantitative models for commodity dependency, origin-attention country
          trade relationships, and hazard-trade corridor integration.
        </p>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-10">
          <div className="bg-white rounded-xl border border-gray-200 p-4">
            <BarChart3 size={24} className="text-blue-500 mx-auto mb-2" />
            <p className="text-sm font-medium text-gray-700">43 Formulas</p>
            <p className="text-xs text-gray-400">7 model groups</p>
          </div>
          <div className="bg-white rounded-xl border border-gray-200 p-4">
            <Network size={24} className="text-purple-500 mx-auto mb-2" />
            <p className="text-sm font-medium text-gray-700">Rust + PyO3</p>
            <p className="text-xs text-gray-400">High-perf engine</p>
          </div>
          <div className="bg-white rounded-xl border border-gray-200 p-4">
            <Shield size={24} className="text-emerald-500 mx-auto mb-2" />
            <p className="text-sm font-medium text-gray-700">RASFF + Comtrade</p>
            <p className="text-xs text-gray-400">Live data sources</p>
          </div>
        </div>

        <div className="flex flex-col sm:flex-row gap-3 justify-center">
          <Link
            href="/dashboard"
            className="inline-flex items-center justify-center gap-2 bg-blue-600 text-white px-6 py-3 rounded-lg font-medium hover:bg-blue-700 transition-colors"
          >
            Open Dashboard
            <ArrowRight size={16} />
          </Link>
          <Link
            href="/architecture"
            className="inline-flex items-center justify-center gap-2 bg-white text-gray-700 border border-gray-200 px-6 py-3 rounded-lg font-medium hover:bg-gray-50 transition-colors"
          >
            System Architecture
          </Link>
        </div>
      </div>
    </main>
  );
}
