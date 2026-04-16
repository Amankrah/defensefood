use pyo3::prelude::*;

use crate::stats::entropy::normalised_entropy;
use crate::types::HAZARD_TYPE_COUNT;

/// Hazard Diversity Index (Eq. 17-18):
///   HDI(c,i,j) = -sum( p_h * ln(p_h) ) for h in H
///   HDI_norm(c,i,j) = HDI(c,i,j) / ln(|H|)
///
/// Where p_h is the proportion of notifications for corridor (c,i,j) with hazard type h.
/// |H| = 6 (biological, chem_pesticides, chem_heavy_metals, chem_mycotoxins, chem_other, regulatory)
///
/// HDI_norm = 0: all notifications have the same hazard type (no diversity)
/// HDI_norm = 1: all hazard types equally represented (maximum diversity)
///
/// Input: array of 6 counts (one per hazard type).
#[pyfunction]
pub fn compute_hdi(hazard_type_counts: Vec<f64>) -> f64 {
    normalised_entropy(&hazard_type_counts, HAZARD_TYPE_COUNT)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_hdi_single_type() {
        let hdi = compute_hdi(vec![10.0, 0.0, 0.0, 0.0, 0.0, 0.0]);
        assert!((hdi - 0.0).abs() < 1e-10);
    }

    #[test]
    fn test_hdi_uniform() {
        let hdi = compute_hdi(vec![5.0, 5.0, 5.0, 5.0, 5.0, 5.0]);
        assert!((hdi - 1.0).abs() < 1e-10);
    }

    #[test]
    fn test_hdi_partial() {
        // Two types equally: entropy = ln(2), normalised = ln(2)/ln(6) ≈ 0.387
        let hdi = compute_hdi(vec![10.0, 10.0, 0.0, 0.0, 0.0, 0.0]);
        assert!((hdi - 0.387).abs() < 0.001);
    }
}
