use pyo3::prelude::*;

/// Detection Gap Indicator (Eq. 19):
///   DGI(c,i,j,t) = M(c,i,j,t)/M(c,i,*,t) - R(c,i,j,t)/R(c,i,*,t)
///
/// i.e., DGI = OCS - notification_share
///
/// DGI > 0: origin supplies larger trade share than notification share -> potentially under-inspected
/// DGI < 0: origin over-represented in notifications relative to trade share
/// DGI > 0 with high BDI: flag for potential under-detection
///
/// Returns NaN when total notifications R(c,i,*,t) = 0 (insufficient data).
#[pyfunction]
pub fn compute_dgi(
    trade_share: f64,
    notification_share: f64,
) -> f64 {
    if notification_share.is_nan() {
        return f64::NAN;
    }
    trade_share - notification_share
}

/// Compute DGI from raw counts.
#[pyfunction]
pub fn compute_dgi_from_counts(
    bilateral_import: f64,
    total_import: f64,
    bilateral_notifications: f64,
    total_notifications: f64,
) -> f64 {
    if total_notifications == 0.0 {
        return f64::NAN;
    }
    if total_import <= 0.0 {
        return f64::NAN;
    }
    let trade_share = bilateral_import / total_import;
    let notif_share = bilateral_notifications / total_notifications;
    trade_share - notif_share
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_dgi_under_inspected() {
        // Trade share 0.6, notification share 0.2 -> DGI = 0.4 (under-inspected)
        let dgi = compute_dgi(0.6, 0.2);
        assert!((dgi - 0.4).abs() < 1e-10);
    }

    #[test]
    fn test_dgi_over_represented() {
        // Trade share 0.2, notification share 0.6 -> DGI = -0.4
        let dgi = compute_dgi(0.2, 0.6);
        assert!((dgi - (-0.4)).abs() < 1e-10);
    }

    #[test]
    fn test_dgi_no_notifications() {
        let dgi = compute_dgi_from_counts(100.0, 500.0, 0.0, 0.0);
        assert!(dgi.is_nan());
    }
}
