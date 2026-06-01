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

/** Where DS'/SSR came from: trade-only proxy (DS' = M - X) vs FAOSTAT balance sheet. */
export type Provenance = "trade_only" | "faostat";

/** How CVS was composed: full SCI·CRS·HIS vs the relaxed SCI+HIS base. */
export type CvsMode = "sci_crs_his" | "sci_his" | null;

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
  // ── Section 2 dependency (attached at startup; null/absent when no trade) ──
  sci?: number | null;
  idr?: number | null;
  ocs?: number | null;
  bdi?: number | null;
  hhi?: number | null;
  ssr?: number | null;
  ds_prime?: number | null;
  /** True when imports exceed apparent domestic supply (re-export / data-artefact flag). */
  idr_gt_1?: boolean;
  /** Whether dependency used FAOSTAT production or the trade-only DS' proxy. */
  provenance?: Provenance;
  bilateral_import_kg?: number | null;
  total_imports_kg?: number | null;
  production_kg?: number | null;
  /** Section 3 consumption rank (present only when FAOSTAT FBS is loaded). */
  crs?: number | null;
  /** Combined vulnerability score. null when structural inputs are missing. */
  cvs?: number | null;
  /** Which inputs the CVS was built from. */
  cvs_mode?: CvsMode;
  /** Hazard-only CVS fallback when structural data is unavailable. */
  cvs_hazard_only?: number | null;
  /** Which normalised inputs are missing (e.g. ["crs_norm"]). */
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
  /** "faostat" when production was available, else "trade_only" (DS' = M - X). */
  provenance?: Provenance;
  /** True when IDR > 1 (imports exceed apparent domestic supply). */
  idr_gt_1?: boolean;
  production_kg?: number;
  total_imports_kg?: number;
  bilateral_import_kg?: number;
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
  cvs_mode?: CvsMode;
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
  /** Bilateral Dependency Index (Section 2); null for corridors without trade. */
  bdi?: number | null;
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

// ── Research mode ──

export interface CoverageReport {
  corridors_total: number;
  corridors_faostat: number;
  corridors_with_dependency: number;
  corridors_with_crs: number;
  corridors_with_cvs: number;
  corridors_idr_gt_1: number;
  unmapped_origins: string[];
  unmapped_destinations: string[];
  trade_periods: number[];
  rasff_periods_count: number;
  rasff_period_min: number | null;
  rasff_period_max: number | null;
  by_hs_chapter: {
    chapter: string;
    total: number;
    faostat: number;
    trade_only: number;
    no_trade: number;
  }[];
  faostat_available: boolean;
}

export interface MethodologyEntry {
  key: string;
  name: string;
  abbr: string;
  section: string;
  blueprint_eq: string;
  formula_latex: string;
  inputs: string[];
  definition: string;
  source: string;
}

export interface DistributionStats {
  count: number;
  min: number | null;
  max: number | null;
  mean: number | null;
  median: number | null;
  p25: number | null;
  p75: number | null;
  p90: number | null;
  std: number | null;
}

export interface DistributionResponse {
  metric: string;
  bins: { x0: number; x1: number; count: number }[];
  stats: DistributionStats;
  filters: { provenance: string | null; origin_eu: boolean | null; dest_eu: boolean | null };
}

export interface CohortRow {
  group: Record<string, string>;
  count: number;
  value: number;
}

export interface CohortResponse {
  group_by: string[];
  metric: string;
  agg: string;
  count: number;
  rows: CohortRow[];
}

export interface RawNotification {
  reference: string;
  period: number;
  classification: string;
  risk_decision: string;
  hazard_category: string;
  destination_roles: string[];
  severity_weight: number;
}

export interface RawTradeRow {
  period: number;
  reporterCode: number;
  reporterDesc: string;
  partnerCode: number;
  partnerDesc: string;
  cmdCode: string;
  cmdDesc: string;
  flowCode: string;
  flowDesc: string;
  primaryValue: number;
  netWgt: number;
  qty: number;
  qtyUnitAbbr: string;
}

export interface LaneTimeSeries {
  commodity_hs: string;
  destination_m49: number;
  origin_m49: number;
  dependency_by_period: Record<string, Record<string, number | string | boolean>>;
  notifications_by_month: Record<string, number>;
}
