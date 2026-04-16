use pyo3::prelude::*;

/// Approach 1: Weighted Linear Combination (Eq. 39):
///   CVS = sum(w_k * x_k_norm) where sum(w_k) = 1
///
/// Compensatory: a high score on one metric compensates for a low score on another.
#[pyfunction]
pub fn score_weighted_linear(normalised_values: Vec<f64>, weights: Vec<f64>) -> f64 {
    normalised_values
        .iter()
        .zip(weights.iter())
        .map(|(v, w)| v * w)
        .sum()
}

/// Approach 2: Geometric Mean (Eq. 40):
///   CVS = product(x_k_norm ^ w_k)
///
/// Non-compensatory: if any component is zero, the composite is zero.
/// More conservative; may miss emerging risks.
#[pyfunction]
pub fn score_geometric_mean(normalised_values: Vec<f64>, weights: Vec<f64>) -> f64 {
    normalised_values
        .iter()
        .zip(weights.iter())
        .map(|(v, w)| v.powf(*w))
        .product()
}

/// Approach 3: Hybrid -- Structural Base with Signal Amplifier (Eq. 41):
///   CVS = SCI_norm * CRS_norm * (1 + w_h*HIS_norm + w_p*PAS_norm + w_sc*SCCS_norm)
///
/// The BASE requires both structural dependency and consumption demand.
/// The AMPLIFIER adds risk weight from hazard history, price anomalies,
/// and supply chain complexity, but cannot create vulnerability where
/// structural conditions do not exist.
///
/// CVS_hybrid in [0, 1*(1+w_h+w_p+w_sc)]
/// Normalise to [0,1] by dividing by (1 + w_h + w_p + w_sc).
#[pyfunction]
#[pyo3(signature = (sci_norm, crs_norm, his_norm=0.0, pas_norm=0.0, sccs_norm=0.0, w_h=1.0, w_p=1.0, w_sc=1.0))]
pub fn score_hybrid(
    sci_norm: f64,
    crs_norm: f64,
    his_norm: f64,
    pas_norm: f64,
    sccs_norm: f64,
    w_h: f64,
    w_p: f64,
    w_sc: f64,
) -> f64 {
    let base = sci_norm * crs_norm;
    let amplifier = 1.0 + w_h * his_norm + w_p * pas_norm + w_sc * sccs_norm;
    let max_amplifier = 1.0 + w_h + w_p + w_sc;
    let raw = base * amplifier;
    // Normalise to [0, 1]
    raw / max_amplifier
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_weighted_linear() {
        let vals = vec![0.8, 0.6, 0.4];
        let wts = vec![0.5, 0.3, 0.2];
        let score = score_weighted_linear(vals, wts);
        // 0.8*0.5 + 0.6*0.3 + 0.4*0.2 = 0.4 + 0.18 + 0.08 = 0.66
        assert!((score - 0.66).abs() < 1e-10);
    }

    #[test]
    fn test_geometric_mean_zero_propagation() {
        let vals = vec![0.8, 0.0, 0.4];
        let wts = vec![0.33, 0.34, 0.33];
        let score = score_geometric_mean(vals, wts);
        assert!((score - 0.0).abs() < 1e-10);
    }

    #[test]
    fn test_hybrid_no_structural_base() {
        // SCI=0 means no vulnerability regardless of hazard signals
        let score = score_hybrid(0.0, 0.8, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0);
        assert!((score - 0.0).abs() < 1e-10);
    }

    #[test]
    fn test_hybrid_no_consumption() {
        // CRS=0 means no market to exploit
        let score = score_hybrid(0.8, 0.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0);
        assert!((score - 0.0).abs() < 1e-10);
    }

    #[test]
    fn test_hybrid_with_signals() {
        let score = score_hybrid(0.5, 0.8, 0.6, 0.3, 0.4, 1.0, 1.0, 1.0);
        // base = 0.5 * 0.8 = 0.4
        // amplifier = 1 + 0.6 + 0.3 + 0.4 = 2.3
        // max = 1 + 1 + 1 + 1 = 4
        // raw = 0.4 * 2.3 = 0.92
        // normalised = 0.92 / 4 = 0.23
        assert!((score - 0.23).abs() < 1e-10);
    }
}
