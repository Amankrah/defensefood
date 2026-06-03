// ── Corridor Metrics (from /corridors endpoints) ──

export type RasffRole = "notifier" | "distribution" | "followUp" | "attention";

/**
 * RASFF role -> market-presence classification (per EU SOP / Regulation 16/2011):
 *   confirmed     -- distribution and/or followUp: product IS or MAY BE on this market.
 *   detected      -- notifier-only: country detected the hazard; market presence not asserted.
 *   informational -- attention-only: product is NOT on this market (only in notifier,
 *                    no longer on market, or never placed on market).
 *   unknown       -- defensive default.
 */
export type MarketPresence = "confirmed" | "detected" | "informational" | "unknown";

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

export type DataQualityTier = "full" | "hazard_only" | "partial" | "unavailable";

export type SciUnavailableReason =
  | "no_trade_footprint"
  | "ds_prime_error"
  | "zero_destination_imports"
  | "hhi_unavailable"
  | "no_hazard_signal";

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
  /** Market-presence classification derived from RASFF role semantics. */
  market_presence?: MarketPresence;
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
  /** Section 3 per-capita apparent consumption (kg/capita/year). */
  pcc?: number | null;
  /** Section 3 commodity consumption rank within the destination (0-1). */
  crs?: number | null;
  /** Section 3 demand inelasticity over 5-year window (0-1; high = stable). */
  dis?: number | null;
  /** Combined vulnerability score. null when structural inputs are missing. */
  cvs?: number | null;
  /** Which inputs the CVS was built from. */
  cvs_mode?: CvsMode;
  /** Hazard-only CVS fallback when structural data is unavailable. */
  cvs_hazard_only?: number | null;
  /** Which normalised inputs are missing (e.g. ["crs_norm"]). */
  cvs_missing_inputs?: string[];
  /** Amplifier terms that contributed to this lane's CVS (Slice E1). */
  cvs_amplifier_terms?: string[];
  sci_norm?: number | null;
  his_norm?: number | null;
  crs_norm?: number | null;
  /** Section 7 amplifier terms (Slice E2). */
  pas?: number | null;
  pas_norm?: number | null;
  sccs?: number | null;
  sccs_norm?: number | null;
  /** Bilateral unit-value z-score (Section 5.1; populated alongside PAS). */
  z_uv?: number | null;
  /** Why SCI/CVS may be absent (machine-readable). */
  sci_unavailable_reason?: SciUnavailableReason | null;
  /** Human-readable explanation for UI tooltips. */
  sci_unavailable_label?: string | null;
  /** full | hazard_only | partial | unavailable */
  data_quality?: DataQualityTier;
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

// ── Section 3: Consumption ──

export interface ConsumptionMetrics {
  /** Per-capita apparent consumption (kg/capita/year). */
  pcc: number | null;
  /** Commodity consumption rank within the destination (0–1). */
  crs: number | null;
  /** Demand inelasticity over 5-year window (0–1; high = stable). */
  dis: number | null;
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
  /** Volume anomaly z-score (Section 5.2). NaN/null until ≥ k+1 periods of history exist. */
  z_volume?: number | null;
  /** Rolling-window size used by the engine (default 5). */
  z_volume_window_k?: number;
  /** Number of historical periods actually available for this corridor. */
  z_volume_periods_available?: number;
  mtd?: number;
  delta_hhi?: number | null;
  /** Origin share change (Section 5.4). null when only one period is loaded. */
  delta_ocs?: number | null;
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
  market_presence?: MarketPresence;
  dependency?: DependencyMetrics;
  consumption?: ConsumptionMetrics | null;
  hazard?: HazardMetrics;
  trade_flow?: TradeFlowMetrics;
  cvs?: number | null;
  cvs_mode?: CvsMode;
  cvs_hazard_only?: number | null;
  cvs_missing_inputs?: string[];
  sci_unavailable_reason?: SciUnavailableReason | null;
  sci_unavailable_label?: string | null;
  data_quality?: DataQualityTier;
  sci_norm?: number | null;
  his_norm?: number | null;
  crs_norm?: number | null;
  pas_norm?: number | null;
  sccs_norm?: number | null;
  cvs_amplifier_terms?: string[];
  /** Server-side verdicts when /full was requested with ?interpret=true. */
  interpretations?: Record<string, MetricInterpretation>;
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
  /** RASFF market-presence classification of this lane. */
  market_presence?: MarketPresence;
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
  /** ACEP over confirmed edges only (planner-facing default). */
  acep: number;
  /** Role-split ACEP buckets — same edges, partitioned by market-presence. */
  acep_by_role?: Record<MarketPresence, number>;
  /** Number of inbound HS codes whose CRS resolved from the Section 3 lookup. */
  crs_resolved_count?: number;
  /** Number of inbound HS codes that contributed 0 because CRS was unavailable. */
  crs_missing_count?: number;
  /** Sample of HS codes missing CRS (capped at 10 for payload size). */
  crs_missing_hs?: string[];
  /** Number of inbound corridors with no BDI (contributed 0 to the ACEP sum). */
  bdi_missing_inbound?: number;
}

/** ORPS (Sec. 6.2) per commodity for an origin; PCC proxied until consumption data is wired. */
export interface CountryOrpsByCommodity {
  m49: number;
  name: string;
  pcc_proxy: boolean;
  commodities: {
    commodity_hs: string;
    /** ORPS over confirmed destinations only (default). */
    orps: number;
    /** Role-split ORPS buckets for this commodity. */
    orps_by_role?: Record<MarketPresence, number>;
    /** Destinations whose PCC came from FAOSTAT (real consumption). */
    pcc_real_count?: number;
    /** Destinations that fell back to PCC=1.0 (no consumption data). */
    pcc_proxy_count?: number;
  }[];
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
  market_presence_counts?: Record<MarketPresence, number>;
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
  corridors_by_data_quality?: Partial<Record<DataQualityTier, number>>;
  sci_unavailable_by_reason?: Partial<Record<SciUnavailableReason, number>>;
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

export interface MethodologyScaleBand {
  min: number;
  max: number;
  label: string;
  band: "low" | "med" | "high" | "flag";
  advice: string;
}

export interface MethodologyEntry {
  key: string;
  name: string;
  abbr: string;
  section: string;
  blueprint_eq: string;
  formula_latex: string;
  /** Plain-English rewrite of the formula. */
  formula_plain?: string;
  inputs: string[];
  definition: string;
  /** Ordered list of value bands with verdict + advice (single source of truth for interpretation). */
  scale?: MethodologyScaleBand[];
  /** One-sentence note on when this metric drives a decision. */
  when_matters?: string;
  /** Metric keys this one combines with or cross-references. */
  related?: string[];
  source: string;
}

/** Verdict returned by backend's interpret_corridor (mirrors interpret.ts). */
export interface MetricInterpretation {
  verdict: string;
  band: "low" | "med" | "high" | "flag";
  advice: string | null;
  label: string | null;
  ok: boolean;
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

/** Empirical hazard probability (Sec. 6.4 Eq. 35). p_hat is null when ineligible. */
export interface HazardProbabilityResponse {
  commodity_hs: string;
  destination_m49: number;
  origin_m49: number;
  notification_count?: number;
  total_import_kg?: number;
  avg_shipment_kg?: number;
  estimated_shipments?: number;
  p_hat: number | null;
  eligible: boolean;
  eligibility_reason: string | null;
}

export interface LaneTimeSeries {
  commodity_hs: string;
  destination_m49: number;
  origin_m49: number;
  dependency_by_period: Record<string, Record<string, number | string | boolean>>;
  notifications_by_month: Record<string, number>;
}
