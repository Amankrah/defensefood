import type {
  CohortResponse,
  CorridorMetric,
  CorridorProfile,
  Country,
  CountryAcep,
  CountryOrpsByCommodity,
  CountryDetail,
  CountryExposure,
  CoverageReport,
  DistributionResponse,
  HazardProbabilityResponse,
  LaneTimeSeries,
  MethodologyEntry,
  NetworkGraph,
  OriginRisk,
  RasffSummary,
  RawNotification,
  RawTradeRow,
  ScoringConfig,
  ScoringResult,
  TradeFlowMetrics,
} from "./types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

async function fetchApi<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`);
  return res.json();
}

export const api = {
  health: () =>
    fetchApi<{
      status: string;
      rust_module: string;
      rust_submodules: string[];
      version: string;
      data?: {
        corridor_metrics: number;
        notifications: number;
        trade_rows: number;
        current_period: number;
      };
    }>("/health"),

  corridors: {
    list: (params?: string) =>
      fetchApi<{ count: number; corridors: CorridorMetric[] }>(
        `/corridors${params ? `?${params}` : ""}`
      ),
    top: (n = 50, sortBy = "his") =>
      fetchApi<{ sort_by: string; count: number; corridors: CorridorMetric[] }>(
        `/corridors/top?n=${n}&sort_by=${sortBy}`
      ),
    get: (hs: string, dest: number, origin: number) =>
      fetchApi<CorridorMetric>(`/corridors/${hs}/${dest}/${origin}`),
    full: (hs: string, dest: number, origin: number, opts?: { interpret?: boolean }) =>
      fetchApi<CorridorProfile>(
        `/corridors/${hs}/${dest}/${origin}/full${opts?.interpret ? "?interpret=true" : ""}`
      ),
    hazard: (hs: string, dest: number, origin: number) =>
      fetchApi<CorridorMetric>(`/corridors/${hs}/${dest}/${origin}/hazard`),
    hazardProbability: (hs: string, dest: number, origin: number) =>
      fetchApi<HazardProbabilityResponse>(
        `/corridors/${hs}/${dest}/${origin}/hazard-probability`
      ),
    tradeAnomalies: (hs: string, dest: number, origin: number) =>
      fetchApi<TradeFlowMetrics>(
        `/corridors/${hs}/${dest}/${origin}/trade-anomalies`
      ),
    notifications: (hs: string, dest: number, origin: number) =>
      fetchApi<{ count: number; notifications: RawNotification[] }>(
        `/corridors/${hs}/${dest}/${origin}/notifications`
      ),
    tradeRows: (hs: string, dest: number, origin: number, period?: number) =>
      fetchApi<{ count: number; rows: RawTradeRow[] }>(
        `/corridors/${hs}/${dest}/${origin}/trade-rows${period ? `?period=${period}` : ""}`
      ),
    timeSeries: (hs: string, dest: number, origin: number) =>
      fetchApi<LaneTimeSeries>(
        `/corridors/${hs}/${dest}/${origin}/time-series`
      ),
  },

  countries: {
    list: (euOnly = false) =>
      fetchApi<{ count: number; countries: Country[] }>(
        `/countries?eu_only=${euOnly}`
      ),
    get: (m49: number) => fetchApi<CountryDetail>(`/countries/${m49}`),
    exposure: (m49: number) =>
      fetchApi<CountryExposure>(`/countries/${m49}/exposure-profile`),
    acep: (m49: number) => fetchApi<CountryAcep>(`/countries/${m49}/acep`),
    orpsByCommodity: (m49: number) =>
      fetchApi<CountryOrpsByCommodity>(`/countries/${m49}/orps-by-commodity`),
  },

  commodities: {
    list: () =>
      fetchApi<{ count: number; commodities: { hs_code: string; names: string[] }[] }>(
        "/commodities"
      ),
    get: (hs: string) =>
      fetchApi<{
        hs_code: string;
        names: string[];
        corridor_count: number;
        corridors: CorridorMetric[];
      }>(`/commodities/${hs}`),
  },

  hazards: {
    summary: () => fetchApi<RasffSummary>("/hazards/summary"),
    types: () =>
      fetchApi<{ hazard_types: { index: number; id: string; label: string }[] }>(
        "/hazards/types"
      ),
  },

  scoring: {
    config: () => fetchApi<ScoringConfig>("/scoring/config"),
    updateConfig: (config: ScoringConfig) =>
      fetch(`${API_BASE}/scoring/config`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(config),
      }).then((r) => r.json()),
    recalculate: (config?: ScoringConfig) =>
      fetch(`${API_BASE}/scoring/recalculate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: config ? JSON.stringify(config) : undefined,
      }).then((r) => r.json()) as Promise<ScoringResult>,
  },

  network: {
    summary: () =>
      fetchApi<{ node_count: number; edge_count: number }>("/network/summary"),
    graph: (commodity?: string) =>
      fetchApi<NetworkGraph>(
        `/network/graph${commodity ? `?commodity=${commodity}` : ""}`
      ),
    origins: (limit = 20) =>
      fetchApi<{ count: number; origins: OriginRisk[] }>(
        `/network/origins?limit=${limit}`
      ),
  },

  research: {
    coverage: () => fetchApi<CoverageReport>("/research/coverage"),
    methodology: () =>
      fetchApi<{ count: number; entries: MethodologyEntry[] }>("/research/methodology"),
    distribution: (
      metric: string,
      opts: {
        bins?: number;
        provenance?: "faostat" | "trade_only";
        originEu?: boolean;
        destEu?: boolean;
      } = {}
    ) => {
      const params = new URLSearchParams();
      if (opts.bins != null) params.set("bins", String(opts.bins));
      if (opts.provenance) params.set("provenance", opts.provenance);
      if (opts.originEu != null) params.set("origin_eu", String(opts.originEu));
      if (opts.destEu != null) params.set("dest_eu", String(opts.destEu));
      const q = params.toString();
      return fetchApi<DistributionResponse>(
        `/research/distributions/${metric}${q ? `?${q}` : ""}`
      );
    },
    cohorts: (groupBy: string[], metric = "his", agg = "mean") =>
      fetchApi<CohortResponse>(
        `/research/cohorts?group_by=${encodeURIComponent(groupBy.join(","))}&metric=${metric}&agg=${agg}`
      ),
  },
};
