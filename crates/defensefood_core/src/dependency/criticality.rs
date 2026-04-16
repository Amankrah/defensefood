use pyo3::prelude::*;

/// Supply Criticality Index (Eq. 9):
///   SCI(c,i,j,t) = IDR(c,i,t) * OCS(c,i,j,t) * (1 + HHI(c,i,t))
///
/// The (1+HHI) term amplifies vulnerability when the overall import market
/// is concentrated -- fewer alternative suppliers exist.
///
/// Properties:
///   SCI in [0, 2] since IDR in [0,~], OCS in [0,1], HHI in [0,1]
///   For normalisation to [0,1]: SCI_norm = SCI / 2
///   SCI = 0: no dependency on this origin
///   SCI = 2: maximum vulnerability (fully import-dependent, sole supplier, monopoly)
#[pyfunction]
pub fn compute_sci(idr: f64, ocs: f64, hhi: f64) -> f64 {
    idr * ocs * (1.0 + hhi)
}

/// Normalised SCI to [0, 1] range.
#[pyfunction]
pub fn compute_sci_normalised(idr: f64, ocs: f64, hhi: f64) -> f64 {
    compute_sci(idr, ocs, hhi) / 2.0
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_sci_worked_example() {
        // PDF p.9: SCI = 1.091 * 0.667 * (1 + 0.490) = 1.084
        let sci = compute_sci(1.091, 0.667, 0.490);
        assert!((sci - 1.084).abs() < 0.002);
    }

    #[test]
    fn test_sci_normalised_worked_example() {
        // PDF p.10: SCI_norm = 1.084 / 2 = 0.542
        let sci_norm = compute_sci_normalised(1.091, 0.667, 0.490);
        assert!((sci_norm - 0.542).abs() < 0.002);
    }

    #[test]
    fn test_sci_zero_dependency() {
        let sci = compute_sci(0.0, 0.5, 0.3);
        assert!((sci - 0.0).abs() < 1e-10);
    }

    #[test]
    fn test_sci_maximum() {
        // IDR=1, OCS=1, HHI=1 -> SCI = 1 * 1 * 2 = 2
        let sci = compute_sci(1.0, 1.0, 1.0);
        assert!((sci - 2.0).abs() < 1e-10);
    }
}
