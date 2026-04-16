use pyo3::prelude::*;

/// Option B: Equal Weights (Eq. 42):
///   w_k = 1/K for all k
///
/// Most transparent and least assumption-laden.
#[pyfunction]
pub fn equal_weights(k: usize) -> Vec<f64> {
    if k == 0 {
        return vec![];
    }
    vec![1.0 / k as f64; k]
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_equal_weights() {
        let w = equal_weights(4);
        assert_eq!(w.len(), 4);
        for &wi in &w {
            assert!((wi - 0.25).abs() < 1e-10);
        }
        let sum: f64 = w.iter().sum();
        assert!((sum - 1.0).abs() < 1e-10);
    }

    #[test]
    fn test_equal_weights_zero() {
        let w = equal_weights(0);
        assert!(w.is_empty());
    }
}
