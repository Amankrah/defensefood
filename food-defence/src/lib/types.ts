// ── Corridor Metrics (from /corridors endpoints) ──

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

// ── Section 2: Dependency ──

export interface DependencyMetrics {
  ds_prime: number;
  idr: number;
  ocs: number;
  bdi: number;
  hhi: number;
  ssr: number;
  sci: number;
  sci_norm: number;
  error?: string;
}

// ── Section 4: Hazard ──

export interface HazardMetrics {
  his: number;
  hdi: number;
  notification_count: number;
  severity_total: number;
  dgi?: number;
}

// ── Section 5: Trade Flow ──

export interface TradeFlowMetrics {
  unit_value?: number;
  z_uv?: number;
  z_volume?: number;
  mtd?: number;
  delta_hhi?: number;
  delta_ocs?: number;
  peer_unit_values?: { partnerCode: number; unit_value: number; z_uv: number }[];
}

// ── Full Corridor Profile (from /corridors/.../full) ──

export interface CorridorProfile {
  commodity_hs: string;
  commodity_name: string;
  destination_m49: number;
  destination_country: string;
  origin_m49: number;
  origin_country: string;
  dependency?: DependencyMetrics;
  hazard?: HazardMetrics;
  trade_flow?: TradeFlowMetrics;
  cvs?: number;
  sci_norm?: number;
  his_norm?: number;
  crs_norm?: number;
}

// ── Network Graph ──

export interface GraphNode {
  m49: number;
  name: string;
  is_eu27: boolean;
  corridor_count: number;
  total_his: number;
}

export interface GraphEdge {
  origin_m49: number;
  destination_m49: number;
  commodity_hs: string;
  his: number;
  severity_total: number;
}

export interface NetworkGraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
  node_count: number;
  edge_count: number;
}

// ── Country ──

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

export interface CountryExposure {
  m49: number;
  name: string;
  corridor_count: number;
  corridors: CorridorMetric[];
}

export interface CountryAcep {
  m49: number;
  name: string;
  acep: number;
}

/** ORPS (Sec. 6.2) per commodity for an origin; PCC proxied until consumption data is wired. */
export interface CountryOrpsByCommodity {
  m49: number;
  name: string;
  pcc_proxy: boolean;
  commodities: { commodity_hs: string; orps: number }[];
}

// ── Scoring ──

export interface ScoringConfig {
  normalisation_method: string;
  composition_method: string;
  alpha_decay: number;
  w_hazard: number;
  w_price: number;
  w_supply_chain: number;
}

export interface ScoringResult {
  status: string;
  corridors_scored: number;
  corridors: CorridorMetric[];
}

// ── RASFF Summary ──

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

// ── Origin Risk ──

export interface OriginRisk {
  origin_m49: number;
  name: string;
  total_his: number;
  total_severity: number;
  corridor_count: number;
}
