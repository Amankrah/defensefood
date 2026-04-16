use pyo3::prelude::*;
use std::collections::HashMap;

use crate::network::graph::ExposureNetwork;

/// Origin Risk Propagation Score (Eq. 33):
///   ORPS(j,c,t) = sum_i( BDI(c,i,j,t) * HIS(c,i,j,t) * PCC(c,i,t) )
///
/// Sums across all EU destination countries the product of bilateral dependency,
/// hazard intensity, and per capita consumption. Captures total population-weighted
/// vulnerability exposure created by this origin for this commodity.
///
/// Origins with high ORPS should receive coordinated EU-level action.
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
        .filter(|(_, hs, _, _, _)| hs == commodity_hs)
        .map(|(dest_m49, _, _trade, hazard, dep)| {
            let pcc = pcc_values.get(dest_m49).copied().unwrap_or(0.0);
            dep * hazard * pcc
        })
        .sum()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_orps_basic() {
        let mut net = ExposureNetwork::new();
        // France (250) -> Belgium (56): BDI=0.7, HIS=0.5
        net.add_trade_edge(250, 56, "1001".to_string(), 1000.0, 0.5, 0.7);
        // France (250) -> Germany (276): BDI=0.1, HIS=0.3
        net.add_trade_edge(250, 276, "1001".to_string(), 2000.0, 0.3, 0.1);

        let mut pcc = HashMap::new();
        pcc.insert(56, 10.0);  // Belgium PCC
        pcc.insert(276, 5.0);  // Germany PCC

        let orps = compute_orps(&net, 250, "1001", pcc);
        // = 0.7*0.5*10 + 0.1*0.3*5 = 3.5 + 0.15 = 3.65
        assert!((orps - 3.65).abs() < 1e-10);
    }
}
