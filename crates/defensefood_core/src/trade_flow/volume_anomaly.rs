use pyo3::prelude::*;

use crate::stats::rolling::rolling_zscore;

/// Volume Anomaly Score (Eq. 24-26):
///   Z_M(c,i,j,t) = (M(c,i,j,t) - mu_M) / sigma_M
///
/// Over a k-period rolling window using the corridor's own history.
/// Z_M > 2: trade surge warranting investigation for re-routing, fraudulent volume
/// inflation, or origin laundering.
///
/// Input: time series of import quantities and window size k.
/// Returns z-score for the most recent (last) element.
#[pyfunction]
#[pyo3(signature = (quantity_series, window_k=5))]
pub fn compute_volume_anomaly(quantity_series: Vec<f64>, window_k: usize) -> f64 {
    rolling_zscore(&quantity_series, window_k)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_volume_anomaly_with_variation() {
        let series = vec![95.0, 100.0, 105.0, 98.0, 102.0, 200.0];
        let z = compute_volume_anomaly(series, 5);
        assert!(z > 2.0);
    }

    #[test]
    fn test_volume_anomaly_insufficient_data() {
        let series = vec![100.0, 200.0];
        let z = compute_volume_anomaly(series, 5);
        assert!(z.is_nan());
    }
}
