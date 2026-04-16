use pyo3::prelude::*;

/// Empirical Hazard Probability (Eq. 35):
///   P_hat(hazard | c,i,j) = R(c,i,j,T) / (M(c,i,j,T) / m_bar(c))
///
/// Where T is the total observation period, R is total notification count,
/// M is total import quantity, and m_bar is estimated average shipment size.
///
/// This is inherently a lower bound -- it only captures detected hazards.
/// Cross-reference with DGI (Eq. 19) to distinguish "more fraud" from "more detection".
///
/// Requires sufficient RASFF history (>= 10 notifications over 5 years).
#[pyfunction]
pub fn compute_hazard_probability(
    total_notifications: f64,
    total_import_qty: f64,
    avg_shipment_size: f64,
) -> f64 {
    if total_import_qty <= 0.0 || avg_shipment_size <= 0.0 {
        return f64::NAN;
    }
    let estimated_shipments = total_import_qty / avg_shipment_size;
    if estimated_shipments <= 0.0 {
        return f64::NAN;
    }
    total_notifications / estimated_shipments
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_hazard_probability_basic() {
        // 20 notifications, 10,000 tonnes imported, avg shipment 25 tonnes
        // = 20 / (10000/25) = 20/400 = 0.05
        let p = compute_hazard_probability(20.0, 10_000_000.0, 25_000.0);
        assert!((p - 0.05).abs() < 1e-10);
    }

    #[test]
    fn test_hazard_probability_zero_import() {
        let p = compute_hazard_probability(10.0, 0.0, 25_000.0);
        assert!(p.is_nan());
    }
}
