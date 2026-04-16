use pyo3::prelude::*;

use crate::stats::zscore::{mean, std_dev};

/// Demand Inelasticity Score (Eq. 12-13):
///   CV_D(c,i) = sigma[PCC(c,i,t)] / mu[PCC(c,i,t)]  over t in {t-5, ..., t}
///   DIS(c,i) = 1 - min(CV_D(c,i), 1)
///
/// DIS = 1: perfectly stable demand (maximum exploitability)
/// DIS = 0: highly volatile demand
///
/// Input: a time series of PCC values (at least 2 periods needed).
#[pyfunction]
pub fn compute_dis(pcc_series: Vec<f64>) -> f64 {
    if pcc_series.len() < 2 {
        return f64::NAN;
    }
    let mu = mean(&pcc_series);
    if mu <= 0.0 || mu.is_nan() {
        return f64::NAN;
    }
    let sigma = std_dev(&pcc_series);
    if sigma.is_nan() {
        return f64::NAN;
    }
    let cv = sigma / mu;
    1.0 - cv.min(1.0)
}

/// Compute just the coefficient of variation (CV_D).
#[pyfunction]
pub fn compute_cv(pcc_series: Vec<f64>) -> f64 {
    if pcc_series.len() < 2 {
        return f64::NAN;
    }
    let mu = mean(&pcc_series);
    if mu <= 0.0 || mu.is_nan() {
        return f64::NAN;
    }
    let sigma = std_dev(&pcc_series);
    if sigma.is_nan() {
        return f64::NAN;
    }
    sigma / mu
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_dis_stable_demand() {
        // Very stable consumption: [10.0, 10.0, 10.0, 10.0, 10.0]
        // CV = 0, DIS = 1
        let dis = compute_dis(vec![10.0, 10.0, 10.0, 10.0, 10.0]);
        assert!((dis - 1.0).abs() < 1e-10);
    }

    #[test]
    fn test_dis_volatile_demand() {
        // Very volatile: [1.0, 100.0, 1.0, 100.0, 1.0]
        // CV will be > 1, so DIS = 1 - 1 = 0
        let dis = compute_dis(vec![1.0, 100.0, 1.0, 100.0, 1.0]);
        assert!((dis - 0.0).abs() < 1e-10);
    }

    #[test]
    fn test_dis_moderate() {
        // Moderate variation: [8, 10, 12, 9, 11]
        // mean = 10, std ≈ 1.58, CV ≈ 0.158
        // DIS = 1 - 0.158 = 0.842
        let dis = compute_dis(vec![8.0, 10.0, 12.0, 9.0, 11.0]);
        assert!(dis > 0.8 && dis < 0.9);
    }

    #[test]
    fn test_dis_insufficient_data() {
        let dis = compute_dis(vec![10.0]);
        assert!(dis.is_nan());
    }

    #[test]
    fn test_cv_basic() {
        let cv = compute_cv(vec![10.0, 10.0, 10.0]);
        assert!((cv - 0.0).abs() < 1e-10);
    }
}
