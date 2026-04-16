use pyo3::prelude::*;

use crate::types::{Classification, RiskDecision};

/// Notification Severity Weight (Eq. 14):
///   S(r) = W_class(r) * W_risk(r)
///
/// Yields S(r) in [0.1, 1.0].
#[pyfunction]
pub fn compute_severity(classification: Classification, risk_decision: RiskDecision) -> f64 {
    classification.weight() * risk_decision.weight()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_severity_max() {
        let s = compute_severity(Classification::AlertNotification, RiskDecision::Serious);
        assert!((s - 1.0).abs() < 1e-10);
    }

    #[test]
    fn test_severity_min() {
        let s = compute_severity(Classification::InfoAttention, RiskDecision::NotSerious);
        assert!((s - 0.1).abs() < 1e-10);
    }

    #[test]
    fn test_severity_border_potentially() {
        let s = compute_severity(Classification::BorderRejection, RiskDecision::PotentiallySerious);
        assert!((s - 0.56).abs() < 1e-10); // 0.8 * 0.7
    }
}
