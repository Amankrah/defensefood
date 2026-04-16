use pyo3::prelude::*;

/// Mirror Trade Discrepancy (Eq. 27):
///   MTD(c,i,j,t) = |M_i(c,i,j,t) - X_j(c,j,i,t)| / max(M_i, X_j)
///
/// Where M_i is what country i reports importing from j,
/// and X_j is what country j reports exporting to i.
///
/// Typical legitimate discrepancy (CIF/FOB valuation, timing): 5-15%.
/// Discrepancies exceeding 30% warrant investigation.
/// Persistent large discrepancies over multiple periods = strong fraud signal.
#[pyfunction]
pub fn compute_mtd(m_reported: f64, x_reported: f64) -> f64 {
    let max_val = m_reported.max(x_reported);
    if max_val <= 0.0 {
        return f64::NAN;
    }
    (m_reported - x_reported).abs() / max_val
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_mtd_symmetric() {
        // Identical reports -> MTD = 0
        let mtd = compute_mtd(1000.0, 1000.0);
        assert!((mtd - 0.0).abs() < 1e-10);
    }

    #[test]
    fn test_mtd_large_discrepancy() {
        // M=1000, X=500 -> MTD = 500/1000 = 0.5
        let mtd = compute_mtd(1000.0, 500.0);
        assert!((mtd - 0.5).abs() < 1e-10);
    }

    #[test]
    fn test_mtd_zero_trade() {
        let mtd = compute_mtd(0.0, 0.0);
        assert!(mtd.is_nan());
    }

    #[test]
    fn test_mtd_range() {
        // MTD should always be in [0, 1]
        let mtd = compute_mtd(100.0, 1.0);
        assert!(mtd >= 0.0 && mtd <= 1.0);
    }
}
