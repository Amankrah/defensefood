use pyo3::prelude::*;
use std::collections::HashMap;

use crate::network::graph::{EdgeRole, ExposureNetwork};

/// Origin Risk Propagation Score (Eq. 33):
///   ORPS(j,c,t) = sum_i( BDI(c,i,j,t) * HIS(c,i,j,t) * PCC(c,i,t) )
///
/// Sums over outbound edges with `EdgeRole::Confirmed` only — those are the
/// destinations where RASFF asserts the product reaches the market. Detected /
/// Informational edges are excluded by default; `compute_orps_by_role` returns
/// all role buckets in one pass.
#[pyfunction]
pub fn compute_orps(
    network: &ExposureNetwork,
    origin_m49: u16,
    commodity_hs: &str,
    pcc_values: HashMap<u16, f64>,
) -> f64 {
    let edges = network.get_edges_from(origin_m49);
    edges
        .iter()
        .filter(|(_, hs, _, _, _, _)| hs == commodity_hs)
        .filter(|(_, _, _, _, _, role)| EdgeRole::from_str(role) == EdgeRole::Confirmed)
        .map(|(dest_m49, _, _trade, hazard, dep, _role)| {
            let pcc = pcc_values.get(dest_m49).copied().unwrap_or(0.0);
            dep * hazard * pcc
        })
        .sum()
}

/// Role-split ORPS. Returns a map keyed by the four role strings.
#[pyfunction]
pub fn compute_orps_by_role(
    network: &ExposureNetwork,
    origin_m49: u16,
    commodity_hs: &str,
    pcc_values: HashMap<u16, f64>,
) -> HashMap<String, f64> {
    let mut out: HashMap<String, f64> = HashMap::new();
    for role in ["confirmed", "detected", "informational", "unknown"] {
        out.insert(role.to_string(), 0.0);
    }
    let edges = network.get_edges_from(origin_m49);
    for (dest_m49, hs, _trade, hazard, dep, role) in edges {
        if hs != commodity_hs {
            continue;
        }
        let pcc = pcc_values.get(&dest_m49).copied().unwrap_or(0.0);
        let contrib = dep * hazard * pcc;
        *out.entry(role).or_insert(0.0) += contrib;
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_orps_default_filters_to_confirmed() {
        let mut net = ExposureNetwork::new();
        net.add_trade_edge(250, 56, "1001".to_string(), 1000.0, 0.5, 0.7, Some("confirmed"));
        net.add_trade_edge(250, 276, "1001".to_string(), 2000.0, 0.3, 0.1, Some("informational"));

        let mut pcc = HashMap::new();
        pcc.insert(56, 10.0);
        pcc.insert(276, 5.0);

        let orps = compute_orps(&net, 250, "1001", pcc);
        // Only confirmed edge: 0.7 * 0.5 * 10 = 3.5
        assert!((orps - 3.5).abs() < 1e-10);
    }

    #[test]
    fn test_orps_by_role_splits_buckets() {
        let mut net = ExposureNetwork::new();
        net.add_trade_edge(250, 56, "1001".to_string(), 1000.0, 0.5, 0.7, Some("confirmed"));
        net.add_trade_edge(250, 276, "1001".to_string(), 2000.0, 0.3, 0.1, Some("informational"));
        net.add_trade_edge(250, 380, "1001".to_string(), 500.0, 0.4, 0.2, Some("detected"));

        let mut pcc = HashMap::new();
        pcc.insert(56, 10.0);
        pcc.insert(276, 5.0);
        pcc.insert(380, 8.0);

        let by_role = compute_orps_by_role(&net, 250, "1001", pcc);
        assert!((by_role["confirmed"] - 3.5).abs() < 1e-10);          // 0.7*0.5*10
        assert!((by_role["informational"] - 0.15).abs() < 1e-10);     // 0.1*0.3*5
        assert!((by_role["detected"] - 0.64).abs() < 1e-10);          // 0.2*0.4*8
        assert_eq!(by_role["unknown"], 0.0);
    }
}
