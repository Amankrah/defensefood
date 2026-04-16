use crate::stats::zscore::{mean, std_dev};

/// Compute the rolling mean of the last `window` elements before the final element.
/// Expects `series` to have at least `window + 1` elements.
pub fn rolling_mean(series: &[f64], window: usize) -> f64 {
    if series.len() < window + 1 {
        return f64::NAN;
    }
    let start = series.len() - 1 - window;
    let end = series.len() - 1;
    mean(&series[start..end])
}

/// Compute the rolling standard deviation of the last `window` elements before the final element.
pub fn rolling_std(series: &[f64], window: usize) -> f64 {
    if series.len() < window + 1 {
        return f64::NAN;
    }
    let start = series.len() - 1 - window;
    let end = series.len() - 1;
    std_dev(&series[start..end])
}

/// Compute the rolling z-score for the last element of the series
/// using the preceding `window` elements as the baseline.
pub fn rolling_zscore(series: &[f64], window: usize) -> f64 {
    if series.len() < window + 1 {
        return f64::NAN;
    }
    let current = series[series.len() - 1];
    let rm = rolling_mean(series, window);
    let rs = rolling_std(series, window);
    crate::stats::zscore::zscore(current, rm, rs)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_rolling_zscore_flat_series() {
        // A flat series should have z-score NaN (std=0) or 0
        let series = vec![10.0, 10.0, 10.0, 10.0, 10.0, 10.0];
        let z = rolling_zscore(&series, 5);
        assert!(z.is_nan()); // std = 0
    }

    #[test]
    fn test_rolling_zscore_spike() {
        let series = vec![100.0, 100.0, 100.0, 100.0, 100.0, 500.0];
        let z = rolling_zscore(&series, 5);
        assert!(z.is_nan()); // std of [100,100,100,100,100] is 0, so NaN
    }

    #[test]
    fn test_rolling_zscore_with_variation() {
        let series = vec![95.0, 100.0, 105.0, 98.0, 102.0, 200.0];
        let z = rolling_zscore(&series, 5);
        assert!(z > 2.0); // 200 is way above the mean of ~100
    }
}
