use pyo3::prelude::*;

/// The 4-tuple corridor key used throughout the framework.
/// A corridor is (commodity, destination_country, origin_country, period).
#[derive(Clone, Debug, Hash, Eq, PartialEq)]
pub struct CorridorKey {
    pub commodity_hs: String,
    pub destination_m49: u16,
    pub origin_m49: u16,
    pub period: u32,
}

/// Trade observation from UN Comtrade.
#[pyclass]
#[derive(Clone, Debug)]
pub struct TradeRecord {
    #[pyo3(get, set)]
    pub commodity_hs: String,
    #[pyo3(get, set)]
    pub reporter_code: u16,
    #[pyo3(get, set)]
    pub partner_code: u16,
    #[pyo3(get, set)]
    pub period: u32,
    #[pyo3(get, set)]
    pub import_qty_kg: f64,
    #[pyo3(get, set)]
    pub import_value_usd: f64,
    #[pyo3(get, set)]
    pub export_qty_kg: f64,
    #[pyo3(get, set)]
    pub export_value_usd: f64,
}

#[pymethods]
impl TradeRecord {
    #[new]
    #[pyo3(signature = (commodity_hs, reporter_code, partner_code, period, import_qty_kg=0.0, import_value_usd=0.0, export_qty_kg=0.0, export_value_usd=0.0))]
    pub fn new(
        commodity_hs: String,
        reporter_code: u16,
        partner_code: u16,
        period: u32,
        import_qty_kg: f64,
        import_value_usd: f64,
        export_qty_kg: f64,
        export_value_usd: f64,
    ) -> Self {
        Self {
            commodity_hs,
            reporter_code,
            partner_code,
            period,
            import_qty_kg,
            import_value_usd,
            export_qty_kg,
            export_value_usd,
        }
    }

    fn __repr__(&self) -> String {
        format!(
            "TradeRecord(hs={}, reporter={}, partner={}, period={}, M={:.0}kg, V=${:.0})",
            self.commodity_hs, self.reporter_code, self.partner_code,
            self.period, self.import_qty_kg, self.import_value_usd
        )
    }
}

/// RASFF notification classification.
#[pyclass(eq, eq_int)]
#[derive(Clone, Debug, Copy, PartialEq, Eq)]
pub enum Classification {
    AlertNotification = 0,
    BorderRejection = 1,
    InfoFollowUp = 2,
    InfoAttention = 3,
}

impl Classification {
    pub fn weight(&self) -> f64 {
        match self {
            Classification::AlertNotification => 1.0,
            Classification::BorderRejection => 0.8,
            Classification::InfoFollowUp => 0.7,
            Classification::InfoAttention => 0.5,
        }
    }
}

/// RASFF risk decision.
#[pyclass(eq, eq_int)]
#[derive(Clone, Debug, Copy, PartialEq, Eq)]
pub enum RiskDecision {
    Serious = 0,
    PotentiallySerious = 1,
    PotentialRisk = 2,
    NotSerious = 3,
}

impl RiskDecision {
    pub fn weight(&self) -> f64 {
        match self {
            RiskDecision::Serious => 1.0,
            RiskDecision::PotentiallySerious => 0.7,
            RiskDecision::PotentialRisk => 0.4,
            RiskDecision::NotSerious => 0.2,
        }
    }
}

/// Hazard type categories from RASFF.
#[pyclass(eq, eq_int)]
#[derive(Clone, Debug, Copy, PartialEq, Eq, Hash)]
pub enum HazardType {
    Biological = 0,
    ChemPesticides = 1,
    ChemHeavyMetals = 2,
    ChemMycotoxins = 3,
    ChemOther = 4,
    Regulatory = 5,
}

/// The total number of hazard type categories.
pub const HAZARD_TYPE_COUNT: usize = 6;

/// RASFF notification mapped to Rust.
#[pyclass]
#[derive(Clone, Debug)]
pub struct RasffNotification {
    #[pyo3(get, set)]
    pub reference: String,
    #[pyo3(get, set)]
    pub commodity_hs: String,
    #[pyo3(get, set)]
    pub origin_m49: u16,
    #[pyo3(get, set)]
    pub affected_countries: Vec<u16>,
    #[pyo3(get, set)]
    pub classification: Classification,
    #[pyo3(get, set)]
    pub risk_decision: RiskDecision,
    #[pyo3(get, set)]
    pub hazard_type: HazardType,
    #[pyo3(get, set)]
    pub period: u32,
}

#[pymethods]
impl RasffNotification {
    #[new]
    pub fn new(
        reference: String,
        commodity_hs: String,
        origin_m49: u16,
        affected_countries: Vec<u16>,
        classification: Classification,
        risk_decision: RiskDecision,
        hazard_type: HazardType,
        period: u32,
    ) -> Self {
        Self {
            reference,
            commodity_hs,
            origin_m49,
            affected_countries,
            classification,
            risk_decision,
            hazard_type,
            period,
        }
    }
}

/// Production and consumption data from FAOSTAT/Eurostat.
#[pyclass]
#[derive(Clone, Debug)]
pub struct ProductionRecord {
    #[pyo3(get, set)]
    pub commodity_hs: String,
    #[pyo3(get, set)]
    pub country_m49: u16,
    #[pyo3(get, set)]
    pub period: u32,
    #[pyo3(get, set)]
    pub production_kg: f64,
    #[pyo3(get, set)]
    pub domestic_supply_kg: f64,
    #[pyo3(get, set)]
    pub population: f64,
}

#[pymethods]
impl ProductionRecord {
    #[new]
    pub fn new(
        commodity_hs: String,
        country_m49: u16,
        period: u32,
        production_kg: f64,
        domestic_supply_kg: f64,
        population: f64,
    ) -> Self {
        Self {
            commodity_hs,
            country_m49,
            period,
            production_kg,
            domestic_supply_kg,
            population,
        }
    }
}
