use pyo3::prelude::*;

/// Per Capita Apparent Consumption (Eq. 10):
///   PCC(c,i,t) = D(c,i,t) / Pop(i,t)
///
/// Expressed in kg/capita/year. FAOSTAT Food Balance Sheets provide this directly
/// for many commodity-country pairs.
#[pyfunction]
pub fn compute_pcc(domestic_supply_kg: f64, population: f64) -> f64 {
    if population <= 0.0 || population.is_nan() {
        return f64::NAN;
    }
    domestic_supply_kg / population
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_pcc_basic() {
        // 1,000,000 kg for 100,000 people = 10 kg/capita
        let pcc = compute_pcc(1_000_000.0, 100_000.0);
        assert!((pcc - 10.0).abs() < 1e-10);
    }

    #[test]
    fn test_pcc_zero_population() {
        let pcc = compute_pcc(1000.0, 0.0);
        assert!(pcc.is_nan());
    }
}
