use pyo3::prelude::*;

pub mod error;
pub mod types;

pub mod stats;

pub mod consumption;
pub mod dependency;
pub mod hazard;
pub mod network;
pub mod scoring;
pub mod trade_flow;

/// EU Food Fraud Vulnerability Intelligence System -- Rust computation engine.
///
/// Implements the mathematical framework (v1.0) covering:
/// - Commodity Dependency Models (Section 2)
/// - Consumption Demand Modelling (Section 3)
/// - Hazard Signal Modelling (Section 4)
/// - Trade Flow Analysis Models (Section 5)
/// - Origin-Attention Country Relationship Model (Section 6)
/// - Composite Vulnerability Scoring (Section 7)
#[pymodule]
fn defensefood_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    // -- Register shared types --
    m.add_class::<types::TradeRecord>()?;
    m.add_class::<types::RasffNotification>()?;
    m.add_class::<types::ProductionRecord>()?;
    m.add_class::<types::Classification>()?;
    m.add_class::<types::RiskDecision>()?;
    m.add_class::<types::HazardType>()?;

    // -- Section 2: Commodity Dependency Models --
    let dep = PyModule::new(m.py(), "dependency")?;
    dep.add_function(wrap_pyfunction!(dependency::supply_balance::compute_supply_balance, &dep)?)?;
    dep.add_function(wrap_pyfunction!(dependency::ratios::compute_idr, &dep)?)?;
    dep.add_function(wrap_pyfunction!(dependency::ratios::compute_ocs, &dep)?)?;
    dep.add_function(wrap_pyfunction!(dependency::ratios::compute_bdi, &dep)?)?;
    dep.add_function(wrap_pyfunction!(dependency::ratios::compute_ssr, &dep)?)?;
    dep.add_function(wrap_pyfunction!(dependency::concentration::compute_hhi, &dep)?)?;
    dep.add_function(wrap_pyfunction!(dependency::concentration::compute_ocs_shares, &dep)?)?;
    dep.add_function(wrap_pyfunction!(dependency::criticality::compute_sci, &dep)?)?;
    dep.add_function(wrap_pyfunction!(dependency::criticality::compute_sci_normalised, &dep)?)?;
    m.add_submodule(&dep)?;

    // -- Section 3: Consumption Demand Modelling --
    let cons = PyModule::new(m.py(), "consumption")?;
    cons.add_function(wrap_pyfunction!(consumption::apparent::compute_pcc, &cons)?)?;
    cons.add_function(wrap_pyfunction!(consumption::rank::compute_crs, &cons)?)?;
    cons.add_function(wrap_pyfunction!(consumption::rank::compute_crs_batch, &cons)?)?;
    cons.add_function(wrap_pyfunction!(consumption::inelasticity::compute_dis, &cons)?)?;
    cons.add_function(wrap_pyfunction!(consumption::inelasticity::compute_cv, &cons)?)?;
    m.add_submodule(&cons)?;

    // -- Section 4: Hazard Signal Modelling --
    let haz = PyModule::new(m.py(), "hazard")?;
    haz.add_function(wrap_pyfunction!(hazard::severity::compute_severity, &haz)?)?;
    haz.add_function(wrap_pyfunction!(hazard::intensity::compute_his, &haz)?)?;
    haz.add_function(wrap_pyfunction!(hazard::intensity::compute_half_life, &haz)?)?;
    haz.add_function(wrap_pyfunction!(hazard::diversity::compute_hdi, &haz)?)?;
    haz.add_function(wrap_pyfunction!(hazard::detection_gap::compute_dgi, &haz)?)?;
    haz.add_function(wrap_pyfunction!(hazard::detection_gap::compute_dgi_from_counts, &haz)?)?;
    m.add_submodule(&haz)?;

    // -- Section 5: Trade Flow Analysis --
    let tf = PyModule::new(m.py(), "trade_flow")?;
    tf.add_function(wrap_pyfunction!(trade_flow::unit_value::compute_unit_value, &tf)?)?;
    tf.add_function(wrap_pyfunction!(trade_flow::unit_value::compute_unit_value_zscore_batch, &tf)?)?;
    tf.add_function(wrap_pyfunction!(trade_flow::volume_anomaly::compute_volume_anomaly, &tf)?)?;
    tf.add_function(wrap_pyfunction!(trade_flow::mirror::compute_mtd, &tf)?)?;
    tf.add_function(wrap_pyfunction!(trade_flow::concentration_shift::compute_delta_hhi, &tf)?)?;
    tf.add_function(wrap_pyfunction!(trade_flow::concentration_shift::compute_delta_ocs, &tf)?)?;
    m.add_submodule(&tf)?;

    // -- Section 6: Origin-Attention Country Relationship Model --
    let net = PyModule::new(m.py(), "network")?;
    net.add_class::<network::graph::ExposureNetwork>()?;
    net.add_function(wrap_pyfunction!(network::orps::compute_orps, &net)?)?;
    net.add_function(wrap_pyfunction!(network::acep::compute_acep, &net)?)?;
    net.add_function(wrap_pyfunction!(network::probability::compute_hazard_probability, &net)?)?;
    m.add_submodule(&net)?;

    // -- Section 7: Composite Vulnerability Scoring --
    let sc = PyModule::new(m.py(), "scoring")?;
    sc.add_function(wrap_pyfunction!(scoring::normalisation::normalise_min_max, &sc)?)?;
    sc.add_function(wrap_pyfunction!(scoring::normalisation::normalise_percentile_rank, &sc)?)?;
    sc.add_function(wrap_pyfunction!(scoring::normalisation::normalise_log_percentile, &sc)?)?;
    sc.add_function(wrap_pyfunction!(scoring::composition::score_weighted_linear, &sc)?)?;
    sc.add_function(wrap_pyfunction!(scoring::composition::score_geometric_mean, &sc)?)?;
    sc.add_function(wrap_pyfunction!(scoring::composition::score_hybrid, &sc)?)?;
    sc.add_function(wrap_pyfunction!(scoring::weights::equal_weights, &sc)?)?;
    m.add_submodule(&sc)?;

    Ok(())
}
