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
            let dt = current_period.saturating_sub(n.period) as f64;
            s * alpha.powf(dt)
        })
        .sum()
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
}
