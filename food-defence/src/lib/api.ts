const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

async function fetchApi<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`API error: ${res.status} ${res.statusText}`);
  return res.json();
}

export interface CorridorMetric {
  commodity_hs: string;
  commodity_name: string;
  destination_m49: number;
  destination_country: string;
  origin_m49: number;
  origin_country: string;
  his: number;
  hdi: number;
  notification_count: number;
  severity_total: number;
  cvs?: number;
  sci_norm?: number;
  his_norm?: number;
  crs_norm?: number;
}

export interface HealthResponse {
  status: string;
  rust_module: string;
  rust_submodules: string[];
  version: string;
}

export interface CorridorsResponse {
  count: number;
  corridors: CorridorMetric[];
  sort_by?: string;
}

export interface RasffSummary {
  total_notifications: number;
  total_corridors: number;
  unique_origins: number;
  unique_destinations: number;
  unique_commodities: number;
  notification_objects_built: number;
  current_period: number;
  unmapped_origins: string[];
  unmapped_destinations: string[];
}

export interface Country {
  m49: number;
  name: string;
  is_eu27: boolean;
}

export interface CountryDetail {
  m49: number;
  name: string;
  is_eu27: boolean;
  corridors_as_destination: number;
  corridors_as_origin: number;
}

export interface OriginRisk {
  origin_m49: number;
  name: string;
  total_his: number;
  total_severity: number;
  corridor_count: number;
}

export interface ScoringConfig {
  normalisation_method: string;
  composition_method: string;
  alpha_decay: number;
  w_hazard: number;
  w_price: number;
  w_supply_chain: number;
}

export const api = {
  health: () => fetchApi<HealthResponse>("/health"),
  corridors: {
    list: (params?: string) => fetchApi<CorridorsResponse>(`/corridors${params ? `?${params}` : ""}`),
    top: (n = 50, sortBy = "his") =>
      fetchApi<CorridorsResponse>(`/corridors/top?n=${n}&sort_by=${sortBy}`),
    get: (hs: string, dest: number, origin: number) =>
      fetchApi<CorridorMetric>(`/corridors/${hs}/${dest}/${origin}`),
  },
  countries: {
    list: (euOnly = false) =>
      fetchApi<{ count: number; countries: Country[] }>(`/countries?eu_only=${euOnly}`),
    get: (m49: number) => fetchApi<CountryDetail>(`/countries/${m49}`),
    exposure: (m49: number) =>
      fetchApi<{ m49: number; name: string; corridor_count: number; corridors: CorridorMetric[] }>(
        `/countries/${m49}/exposure-profile`
      ),
  },
  hazards: {
    summary: () => fetchApi<RasffSummary>("/hazards/summary"),
  },
  scoring: {
    config: () => fetchApi<ScoringConfig>("/scoring/config"),
    recalculate: () =>
      fetch(`${API_BASE}/scoring/recalculate`, { method: "POST" }).then((r) => r.json()),
  },
  network: {
    summary: () => fetchApi<{ node_count: number; edge_count: number }>("/network/summary"),
    origins: (limit = 20) =>
      fetchApi<{ count: number; origins: OriginRisk[] }>(`/network/origins?limit=${limit}`),
  },
};
