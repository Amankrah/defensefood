/// Compute z-score: (value - mean) / std.
/// Returns NaN if std is zero.
pub fn zscore(value: f64, mean: f64, std: f64) -> f64 {
    if std == 0.0 || std.is_nan() {
        return f64::NAN;
    }
    (value - mean) / std
}

/// Compute mean of a slice.
pub fn mean(values: &[f64]) -> f64 {
    if values.is_empty() {
        return f64::NAN;
    }
    let sum: f64 = values.iter().sum();
    sum / values.len() as f64
}

/// Compute sample standard deviation (Bessel-corrected, n-1).
pub fn std_dev(values: &[f64]) -> f64 {
    if values.len() < 2 {
        return f64::NAN;
    }
    let m = mean(values);
    let variance: f64 = values.iter().map(|x| (x - m).powi(2)).sum::<f64>()
        / (values.len() - 1) as f64;
    variance.sqrt()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_zscore_basic() {
        let z = zscore(10.0, 5.0, 2.5);
        assert!((z - 2.0).abs() < 1e-10);
    }

    #[test]
    fn test_zscore_zero_std() {
        let z = zscore(10.0, 5.0, 0.0);
        assert!(z.is_nan());
    }

    #[test]
    fn test_mean() {
        let m = mean(&[2.0, 4.0, 6.0]);
        assert!((m - 4.0).abs() < 1e-10);
    }

    #[test]
    fn test_std_dev() {
        let s = std_dev(&[2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0]);
        assert!((s - 2.138089935299395).abs() < 1e-10);
    }
}
