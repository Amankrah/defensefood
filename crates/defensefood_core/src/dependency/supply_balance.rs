use pyo3::prelude::*;

/// Compute apparent domestic supply (Eq. 2):
///   DS'(c,i,t) = P(c,i,t) + M(c,i,*,t) - X(c,i,*,t)
///
/// When stock change data is unavailable, delta_s = 0.
/// Returns NaN if DS' <= 0 (data quality issue per framework boundary condition).
#[pyfunction]
#[pyo3(signature = (production_kg, total_imports_kg, total_exports_kg, delta_stocks_kg=0.0))]
pub fn compute_supply_balance(
    production_kg: f64,
    total_imports_kg: f64,
    total_exports_kg: f64,
    delta_stocks_kg: f64,
) -> f64 {
    let ds = production_kg + total_imports_kg - total_exports_kg + delta_stocks_kg;
    if ds <= 0.0 {
        f64::NAN
    } else {
        ds
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_supply_balance_worked_example() {
        // PDF p.9: P=500t, M=12000t, X=1500t => DS'=11000t
        let ds = compute_supply_balance(500_000.0, 12_000_000.0, 1_500_000.0, 0.0);
        assert!((ds - 11_000_000.0).abs() < 1e-6);
    }

    #[test]
    fn test_supply_balance_negative() {
        // DS' <= 0 should return NaN
        let ds = compute_supply_balance(0.0, 100.0, 200.0, 0.0);
        assert!(ds.is_nan());
    }

    #[test]
    fn test_supply_balance_zero() {
        let ds = compute_supply_balance(0.0, 100.0, 100.0, 0.0);
        assert!(ds.is_nan()); // DS' = 0 is boundary condition
    }
}
