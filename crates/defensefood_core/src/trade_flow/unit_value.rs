use numpy::{PyArray1, PyReadonlyArray1};
use pyo3::prelude::*;

use crate::stats::zscore;

/// Unit Value (Eq. 20):
///   UV(c,i,j,t) = V(c,i,j,t) / M(c,i,j,t) in USD/kg
#[pyfunction]
pub fn compute_unit_value(value_usd: f64, quantity_kg: f64) -> f64 {
    if quantity_kg <= 0.0 || quantity_kg.is_nan() {
        return f64::NAN;
    }
    value_usd / quantity_kg
}

/// Unit Value Z-score (Eq. 23):
///   Z_UV(c,i,j,t) = (UV(c,i,j,t) - mu_UV(c,i,t)) / sigma_UV(c,i,t)
///
/// Z_UV < -2: price well below market (potential adulteration, substitution)
/// Z_UV > +2: price well above market (potential premium fraud)
///
/// Input: numpy arrays of values and quantities (one per origin).
/// Returns: numpy array of z-scores (one per origin).
#[pyfunction]
pub fn compute_unit_value_zscore_batch<'py>(
    py: Python<'py>,
    values_usd: PyReadonlyArray1<'py, f64>,
    quantities_kg: PyReadonlyArray1<'py, f64>,
) -> Bound<'py, PyArray1<f64>> {
    let vals = values_usd.as_array();
    let qtys = quantities_kg.as_array();
    let n = vals.len();

    // Compute unit values
    let uvs: Vec<f64> = (0..n)
        .map(|i| {
            if qtys[i] > 0.0 {
                vals[i] / qtys[i]
            } else {
                f64::NAN
            }
        })
        .collect();

    // Filter valid UVs for mean/std
    let valid_uvs: Vec<f64> = uvs.iter().filter(|x| !x.is_nan()).copied().collect();
    let mean = zscore::mean(&valid_uvs);
    let std = zscore::std_dev(&valid_uvs);

    // Compute z-scores
    let zscores: Vec<f64> = uvs.iter().map(|&uv| zscore::zscore(uv, mean, std)).collect();
    PyArray1::from_vec(py, zscores)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_unit_value_basic() {
        let uv = compute_unit_value(1000.0, 500.0);
        assert!((uv - 2.0).abs() < 1e-10);
    }

    #[test]
    fn test_unit_value_zero_qty() {
        let uv = compute_unit_value(1000.0, 0.0);
        assert!(uv.is_nan());
    }
}
