// ── Corridor Metrics (from /corridors endpoints) ──

export type RasffRole = "notifier" | "distribution" | "followUp" | "attention";

/** The six hazard taxonomy buckets we aggregate RASFF categories into. */
export type HazardBucket =
  | "biological"
  | "chem_pesticides"
  | "chem_heavy_metals"
  | "chem_mycotoxins"
  | "chem_other"
  | "regulatory";

export type HazardBreakdown = Partial<Record<HazardBucket, number>>;

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
  /** Per-category weighted counts used for HDI. */
  hazard_breakdown?: HazardBreakdown;
  /** Distinct RASFF roles that flagged this destination across notifications. */
  destination_roles?: RasffRole[];
  /** How many notifications flagged each role. */
  role_counts?: Partial<Record<RasffRole, number>>;
  /** True if destination has any active role (notifier/distribution/followUp). */
  is_active_destination?: boolean;
  /** Combined vulnerability score. null when structural inputs are missing. */
  cvs?: number | null;
  /** Hazard-only CVS fallback when structural data is unavailable. */
  cvs_hazard_only?: number | null;
  /** Which normalised inputs are missing (e.g. ["sci_norm", "crs_norm"]). */
  cvs_missing_inputs?: string[];
  sci_norm?: number | null;
  his_norm?: number | null;
  crs_norm?: number | null;
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
  hazard_breakdown?: HazardBreakdown;
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
  destination_roles?: RasffRole[];
  role_counts?: Partial<Record<RasffRole, number>>;
  is_active_destination?: boolean;
  dependency?: DependencyMetrics;
  hazard?: HazardMetrics;
  trade_flow?: TradeFlowMetrics;
  cvs?: number | null;
  cvs_hazard_only?: number | null;
  cvs_missing_inputs?: string[];
  sci_norm?: number | null;
  his_norm?: number | null;
  crs_norm?: number | null;
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
  active_corridors?: number;
  unique_origins: number;
  unique_destinations: number;
  unique_commodities: number;
  notification_objects_built: number;
  current_period: number;
  unmapped_origins: string[];
  unmapped_destinations: string[];
  notifications_without_origin?: number;
  notifications_without_destination?: number;
  self_trade_pairs_skipped?: number;
  role_counts?: Record<RasffRole, number>;
}

// ── Origin Risk ──

export interface OriginRisk {
  origin_m49: number;
  name: string;
  total_his: number;
  total_severity: number;
  corridor_count: number;
}
