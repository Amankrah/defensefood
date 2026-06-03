use pyo3::prelude::*;
use std::collections::HashMap;

use crate::network::graph::{EdgeRole, ExposureNetwork};

/// Attention Country Exposure Profile (Eq. 34):
///   ACEP(i,t) = sum_c sum_j( BDI(c,i,j,t) * HIS(c,i,j,t) * CRS(c,i,t) )
///
/// Sums over inbound edges with `EdgeRole::Confirmed` only — those are lanes
/// where RASFF asserts the product is (or may be) on this market per EU SOPs.
/// Edges flagged `Detected` (notifier-only) or `Informational` (attention-only)
/// are excluded by default; callers that want them use `compute_acep_by_role`
/// to get all three role buckets in one pass.
#[pyfunction]
pub fn compute_acep(
    network: &ExposureNetwork,
    destination_m49: u16,
    crs_by_commodity: HashMap<String, f64>,
) -> f64 {
    let edges = network.get_edges_to(destination_m49);
    edges
        .iter()
        .filter(|(_, _, _, _, _, role)| EdgeRole::from_str(role) == EdgeRole::Confirmed)
        .map(|(_, commodity_hs, _trade, hazard, dep, _role)| {
            let crs = crs_by_commodity.get(commodity_hs).copied().unwrap_or(0.0);
            dep * hazard * crs
        })
        .sum()
}

/// Role-split ACEP. Returns a map keyed by the four role strings
/// (``"confirmed"``, ``"detected"``, ``"informational"``, ``"unknown"``);
/// missing keys default to 0 on the Python side.
#[pyfunction]
pub fn compute_acep_by_role(
    network: &ExposureNetwork,
    destination_m49: u16,
    crs_by_commodity: HashMap<String, f64>,
) -> HashMap<String, f64> {
    let mut out: HashMap<String, f64> = HashMap::new();
    for role in ["confirmed", "detected", "informational", "unknown"] {
        out.insert(role.to_string(), 0.0);
    }
    let edges = network.get_edges_to(destination_m49);
    for (_, commodity_hs, _trade, hazard, dep, role) in edges {
        let crs = crs_by_commodity.get(&commodity_hs).copied().unwrap_or(0.0);
        let contrib = dep * hazard * crs;
        *out.entry(role).or_insert(0.0) += contrib;
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_acep_default_filters_to_confirmed() {
        let mut net = ExposureNetwork::new();
        // confirmed lane contributes
        net.add_trade_edge(250, 56, "1001".to_string(), 1000.0, 0.4, 0.5, Some("confirmed"));
        // informational lane MUST be excluded from the default ACEP
        net.add_trade_edge(276, 56, "1006".to_string(), 500.0, 0.2, 0.3, Some("informational"));

        let mut crs = HashMap::new();
        crs.insert("1001".to_string(), 0.8);
        crs.insert("1006".to_string(), 0.6);

        let acep = compute_acep(&net, 56, crs);
        // Only the confirmed edge counts: 0.5 * 0.4 * 0.8 = 0.16
        assert!((acep - 0.16).abs() < 1e-10);
    }

    #[test]
    fn test_acep_by_role_returns_all_three_buckets() {
        let mut net = ExposureNetwork::new();
        net.add_trade_edge(250, 56, "1001".to_string(), 1000.0, 0.4, 0.5, Some("confirmed"));
        net.add_trade_edge(276, 56, "1006".to_string(), 500.0, 0.2, 0.3, Some("informational"));
        net.add_trade_edge(380, 56, "1007".to_string(), 100.0, 0.1, 0.4, Some("detected"));

        let mut crs = HashMap::new();
        crs.insert("1001".to_string(), 0.8);
        crs.insert("1006".to_string(), 0.6);
        crs.insert("1007".to_string(), 1.0);

        let buckets = compute_acep_by_role(&net, 56, crs);
        // confirmed:    0.5 * 0.4 * 0.8 = 0.16
        // informational: 0.3 * 0.2 * 0.6 = 0.036
        // detected:      0.4 * 0.1 * 1.0 = 0.04
        assert!((buckets["confirmed"] - 0.16).abs() < 1e-10);
        assert!((buckets["informational"] - 0.036).abs() < 1e-10);
        assert!((buckets["detected"] - 0.04).abs() < 1e-10);
        assert_eq!(buckets["unknown"], 0.0);
    }
}
