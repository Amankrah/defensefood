use pyo3::prelude::*;

use crate::types::RasffNotification;

/// Hazard Intensity Score (Eq. 15):
///   HIS(c,i,j,t) = sum( S(r) * alpha^(t - t_r) ) for all notifications r in corridor (c,i,j)
///
/// Where alpha in (0,1) is the temporal decay parameter.
/// Half-life: t_1/2 = -ln(2) / ln(alpha)  (Eq. 16)
///   alpha=0.95 -> ~13.5 months
///   alpha=0.90 -> ~6.6 months (general-purpose default)
///   alpha=0.85 -> ~4.3 months (perishable commodities)
///
/// `current_period` and `n.period` are YYYYMM (year-month) integers. We convert
/// them to absolute month indices before subtracting, otherwise year rollovers
/// produce a jump of 88 "units" instead of 1 month and the decay crushes any
/// notification that isn't in the same calendar year.
///
/// Period 0 (unknown) is treated as "extremely old" and contributes ~0.
///
/// The HIS is intentionally unbounded -- normalisation happens at the composite scoring stage.
#[pyfunction]
#[pyo3(signature = (notifications, commodity_hs, destination_m49, origin_m49, current_period, alpha=0.90))]
pub fn compute_his(
    notifications: Vec<PyRef<RasffNotification>>,
    commodity_hs: &str,
    destination_m49: u16,
    origin_m49: u16,
    current_period: u32,
    alpha: f64,
) -> f64 {
    notifications
        .iter()
        .filter(|n| {
            n.commodity_hs == commodity_hs
                && n.origin_m49 == origin_m49
                && n.affected_countries.contains(&destination_m49)
        })
        .map(|n| {
            let s = n.classification.weight() * n.risk_decision.weight();
            let dt = months_between_yyyymm(current_period, n.period);
            s * alpha.powf(dt)
        })
        .sum()
}

/// Absolute month distance between two YYYYMM integers.
/// Returns 0 when `earlier >= current` and handles invalid / zero periods.
pub fn months_between_yyyymm(current: u32, earlier: u32) -> f64 {
    if earlier == 0 || current == 0 {
        // Unknown period -- treat as far in the past so alpha^dt ~ 0.
        return f64::from(u16::MAX);
    }
    let cur_total = (current / 100).saturating_mul(12) + (current % 100);
    let ear_total = (earlier / 100).saturating_mul(12) + (earlier % 100);
    cur_total.saturating_sub(ear_total) as f64
}

/// Compute the half-life in periods for a given alpha.
#[pyfunction]
pub fn compute_half_life(alpha: f64) -> f64 {
    if alpha <= 0.0 || alpha >= 1.0 {
        return f64::NAN;
    }
    -(2.0_f64.ln()) / alpha.ln()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_half_life_default() {
        let hl = compute_half_life(0.90);
        assert!((hl - 6.5788).abs() < 0.01);
    }

    #[test]
    fn test_half_life_slow_decay() {
        let hl = compute_half_life(0.95);
        assert!((hl - 13.5134).abs() < 0.01);
    }

    #[test]
    fn test_months_between_same_period() {
        assert_eq!(months_between_yyyymm(202612, 202612), 0.0);
    }

    #[test]
    fn test_months_between_one_month() {
        assert_eq!(months_between_yyyymm(202601, 202512), 1.0);
        assert_eq!(months_between_yyyymm(202612, 202611), 1.0);
    }

    #[test]
    fn test_months_between_one_year() {
        assert_eq!(months_between_yyyymm(202612, 202512), 12.0);
    }

    #[test]
    fn test_months_between_two_years() {
        assert_eq!(months_between_yyyymm(202612, 202412), 24.0);
    }

    #[test]
    fn test_months_between_unknown_period() {
        // Period 0 -> treat as far in the past
        assert!(months_between_yyyymm(202612, 0) > 1000.0);
    }
}
