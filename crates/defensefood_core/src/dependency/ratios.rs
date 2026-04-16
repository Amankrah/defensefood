use pyo3::prelude::*;

/// Import Dependency Ratio (Eq. 3):
///   IDR(c,i,t) = M(c,i,*,t) / DS'(c,i,t)
///
/// IDR = 0: fully self-sufficient
/// IDR = 1: fully import-dependent
/// IDR > 1: trade hub (re-exports exceed production)
#[pyfunction]
pub fn compute_idr(total_imports_kg: f64, domestic_supply_kg: f64) -> f64 {
    if domestic_supply_kg <= 0.0 || domestic_supply_kg.is_nan() {
        return f64::NAN;
    }
    total_imports_kg / domestic_supply_kg
}

/// Origin Country Share (Eq. 4):
///   OCS(c,i,j,t) = M(c,i,j,t) / M(c,i,*,t)
///
/// The proportion of country i's imports of commodity c from origin j.
/// By construction, sum(OCS) over all origins = 1.0 and OCS in [0,1].
#[pyfunction]
pub fn compute_ocs(bilateral_import_kg: f64, total_imports_kg: f64) -> f64 {
    if total_imports_kg <= 0.0 || total_imports_kg.is_nan() {
        return f64::NAN;
    }
    bilateral_import_kg / total_imports_kg
}

/// Bilateral Dependency Index (Eq. 5):
///   BDI(c,i,j,t) = M(c,i,j,t) / DS'(c,i,t)
///
/// Decomposes as BDI = IDR * OCS (Eq. 6).
/// The share of total domestic supply sourced specifically from origin j.
#[pyfunction]
pub fn compute_bdi(bilateral_import_kg: f64, domestic_supply_kg: f64) -> f64 {
    if domestic_supply_kg <= 0.0 || domestic_supply_kg.is_nan() {
        return f64::NAN;
    }
    bilateral_import_kg / domestic_supply_kg
}

/// Self-Sufficiency Ratio (Eq. 8):
///   SSR(c,i,t) = P(c,i,t) / D(c,i,t)
///
/// SSR > 1: net exporter. SSR = 0: no domestic production.
#[pyfunction]
pub fn compute_ssr(production_kg: f64, domestic_consumption_kg: f64) -> f64 {
    if domestic_consumption_kg <= 0.0 || domestic_consumption_kg.is_nan() {
        return f64::NAN;
    }
    production_kg / domestic_consumption_kg
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_idr_worked_example() {
        // PDF p.9: IDR = 12000/11000 = 1.091
        let idr = compute_idr(12_000.0, 11_000.0);
        assert!((idr - 1.0909090909).abs() < 1e-6);
    }

    #[test]
    fn test_ocs_worked_example() {
        // PDF p.9: OCS = 8000/12000 = 0.667
        let ocs = compute_ocs(8_000.0, 12_000.0);
        assert!((ocs - 0.6666666667).abs() < 1e-6);
    }

    #[test]
    fn test_bdi_worked_example() {
        // BDI = 8000/11000 = 0.7272...
        let bdi = compute_bdi(8_000.0, 11_000.0);
        assert!((bdi - 0.7272727273).abs() < 1e-6);
    }

    #[test]
    fn test_bdi_decomposition() {
        // BDI = IDR * OCS
        let idr = compute_idr(12_000.0, 11_000.0);
        let ocs = compute_ocs(8_000.0, 12_000.0);
        let bdi = compute_bdi(8_000.0, 11_000.0);
        assert!((bdi - idr * ocs).abs() < 1e-10);
    }

    #[test]
    fn test_ssr_net_exporter() {
        let ssr = compute_ssr(2000.0, 1000.0);
        assert!((ssr - 2.0).abs() < 1e-10);
    }

    #[test]
    fn test_ssr_no_production() {
        let ssr = compute_ssr(0.0, 1000.0);
        assert!((ssr - 0.0).abs() < 1e-10);
    }

    #[test]
    fn test_zero_denominator_returns_nan() {
        assert!(compute_idr(100.0, 0.0).is_nan());
        assert!(compute_ocs(100.0, 0.0).is_nan());
        assert!(compute_bdi(100.0, 0.0).is_nan());
        assert!(compute_ssr(100.0, 0.0).is_nan());
    }
}
