use numpy::{PyArray1, PyReadonlyArray1};
use pyo3::prelude::*;

/// Herfindahl-Hirschman Index (Eq. 7):
///   HHI(c,i,t) = sum(OCS(c,i,j,t)^2) for all origins j
///
/// Properties:
///   HHI = 1/n for n equal suppliers (perfectly diversified)
///   HHI = 1.0 for a single-supplier monopoly
///   HHI > 0.25 is highly concentrated (standard antitrust threshold)
///
/// Input: numpy array of origin country shares (OCS values).
/// Each share should be in [0, 1] and they should sum to ~1.0.
#[pyfunction]
pub fn compute_hhi<'py>(
    _py: Python<'py>,
    shares: PyReadonlyArray1<'py, f64>,
) -> f64 {
    let arr = shares.as_array();
    arr.iter().map(|s| s * s).sum()
}

/// Compute HHI from a plain Rust slice (for internal use by other modules).
pub fn hhi_from_slice(shares: &[f64]) -> f64 {
    shares.iter().map(|s| s * s).sum()
}

/// Compute OCS shares from raw import quantities and return them as a numpy array.
/// Input: numpy array of bilateral import quantities M(c,i,j,t) for each origin j.
/// Output: numpy array of OCS values (each quantity / total).
#[pyfunction]
pub fn compute_ocs_shares<'py>(
    py: Python<'py>,
    bilateral_imports: PyReadonlyArray1<'py, f64>,
) -> Bound<'py, PyArray1<f64>> {
    let arr = bilateral_imports.as_array();
    let total: f64 = arr.iter().sum();
    if total <= 0.0 {
        return PyArray1::from_vec(py, vec![f64::NAN; arr.len()]);
    }
    let shares: Vec<f64> = arr.iter().map(|&m| m / total).collect();
    PyArray1::from_vec(py, shares)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_hhi_worked_example() {
        // PDF p.9: OCS shares = [0.667, 0.167, 0.125, 0.042]
        // HHI = 0.667^2 + 0.167^2 + 0.125^2 + 0.042^2
        //     = 0.444889 + 0.027889 + 0.015625 + 0.001764 = 0.490167
        let shares = [0.667, 0.167, 0.125, 0.042];
        let hhi = hhi_from_slice(&shares);
        assert!((hhi - 0.490).abs() < 0.001);
    }

    #[test]
    fn test_hhi_monopoly() {
        let shares = [1.0];
        let hhi = hhi_from_slice(&shares);
        assert!((hhi - 1.0).abs() < 1e-10);
    }

    #[test]
    fn test_hhi_perfectly_diversified() {
        // 4 equal suppliers: HHI = 4 * (0.25)^2 = 0.25
        let shares = [0.25, 0.25, 0.25, 0.25];
        let hhi = hhi_from_slice(&shares);
        assert!((hhi - 0.25).abs() < 1e-10);
    }

    #[test]
    fn test_hhi_two_suppliers() {
        let shares = [0.5, 0.5];
        let hhi = hhi_from_slice(&shares);
        assert!((hhi - 0.5).abs() < 1e-10);
    }

    #[test]
    fn test_hhi_empty() {
        let shares: [f64; 0] = [];
        let hhi = hhi_from_slice(&shares);
        assert!((hhi - 0.0).abs() < 1e-10);
    }
}
