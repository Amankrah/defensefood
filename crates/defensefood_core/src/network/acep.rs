use pyo3::prelude::*;
use std::collections::HashMap;

use crate::network::graph::ExposureNetwork;

/// Attention Country Exposure Profile (Eq. 34):
///   ACEP(i,t) = sum_c sum_j( BDI(c,i,j,t) * HIS(c,i,j,t) * CRS(c,i,t) )
///
/// For an attention country i: what is its total inbound fraud exposure?
/// Countries with high ACEP need more inspection resources, laboratory capacity,
/// and coordination support.
///
/// crs_values: maps (commodity_hs, origin_m49) to CRS value (not commodity alone,
/// because CRS is per commodity per country).
/// Alternatively, pass crs_by_commodity as HashMap<String, f64>.
#[pyfunction]
pub fn compute_acep(
    network: &ExposureNetwork,
    destination_m49: u16,
    crs_by_commodity: HashMap<String, f64>,
) -> f64 {
    let edges = network.get_edges_to(destination_m49);
    edges
        .iter()
        .map(|(_, commodity_hs, _trade, hazard, dep)| {
            let crs = crs_by_commodity.get(commodity_hs).copied().unwrap_or(0.0);
            dep * hazard * crs
        })
        .sum()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_acep_basic() {
        let mut net = ExposureNetwork::new();
        // France -> Belgium (wheat): BDI=0.5, HIS=0.4
        net.add_trade_edge(250, 56, "1001".to_string(), 1000.0, 0.4, 0.5);
        // Germany -> Belgium (rice): BDI=0.3, HIS=0.2
        net.add_trade_edge(276, 56, "1006".to_string(), 500.0, 0.2, 0.3);

        let mut crs = HashMap::new();
        crs.insert("1001".to_string(), 0.8); // wheat CRS for Belgium
        crs.insert("1006".to_string(), 0.6); // rice CRS for Belgium

        let acep = compute_acep(&net, 56, crs);
        // = 0.5*0.4*0.8 + 0.3*0.2*0.6 = 0.16 + 0.036 = 0.196
        assert!((acep - 0.196).abs() < 1e-10);
    }
}
