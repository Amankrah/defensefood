use numpy::{PyArray1, PyReadonlyArray1};
use pyo3::prelude::*;

/// Commodity Consumption Rank Score (Eq. 11):
///   CRS(c,i,t) = 1 - (Rank(c,i,t) - 1) / (|C| - 1)
///
/// Where Rank is the position of commodity c when all commodities are ordered
/// by PCC descending. CRS = 1 for the highest-consumed commodity, CRS = 0 for
/// the lowest.
///
/// Input: scalar rank (1-based, where 1 = highest PCC) and total commodity count.
#[pyfunction]
pub fn compute_crs(rank: usize, total_commodities: usize) -> f64 {
    if total_commodities <= 1 {
        return 1.0; // Only one commodity
    }
    1.0 - (rank as f64 - 1.0) / (total_commodities as f64 - 1.0)
}

/// Batch compute CRS from a numpy array of PCC values.
/// Returns a numpy array of CRS scores in the same order as the input PCC values.
/// Internally ranks PCC descending and applies Eq. 11.
#[pyfunction]
pub fn compute_crs_batch<'py>(
    py: Python<'py>,
    pcc_values: PyReadonlyArray1<'py, f64>,
) -> Bound<'py, PyArray1<f64>> {
    let arr = pcc_values.as_array();
    let n = arr.len();
    if n == 0 {
        return PyArray1::from_vec(py, vec![]);
    }
    if n == 1 {
        return PyArray1::from_vec(py, vec![1.0]);
    }

    // Create indices sorted by PCC descending
    let mut indices: Vec<usize> = (0..n).collect();
    indices.sort_by(|&a, &b| {
        arr[b]
            .partial_cmp(&arr[a])
            .unwrap_or(std::cmp::Ordering::Equal)
    });

    // Assign ranks (1-based, where rank 1 = highest PCC)
    let mut crs = vec![0.0; n];
    for (rank_0based, &idx) in indices.iter().enumerate() {
        let rank = rank_0based + 1;
        crs[idx] = 1.0 - (rank as f64 - 1.0) / (n as f64 - 1.0);
    }

    PyArray1::from_vec(py, crs)
}

/// Internal batch CRS from a plain slice (for testing).
pub fn crs_batch_from_slice(pcc_values: &[f64]) -> Vec<f64> {
    let n = pcc_values.len();
    if n == 0 {
        return vec![];
    }
    if n == 1 {
        return vec![1.0];
    }

    let mut indices: Vec<usize> = (0..n).collect();
    indices.sort_by(|&a, &b| {
        pcc_values[b]
            .partial_cmp(&pcc_values[a])
            .unwrap_or(std::cmp::Ordering::Equal)
    });

    let mut crs = vec![0.0; n];
    for (rank_0based, &idx) in indices.iter().enumerate() {
        let rank = rank_0based + 1;
        crs[idx] = 1.0 - (rank as f64 - 1.0) / (n as f64 - 1.0);
    }
    crs
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_crs_highest() {
        let crs = compute_crs(1, 10);
        assert!((crs - 1.0).abs() < 1e-10);
    }

    #[test]
    fn test_crs_lowest() {
        let crs = compute_crs(10, 10);
        assert!((crs - 0.0).abs() < 1e-10);
    }

    #[test]
    fn test_crs_middle() {
        // Rank 3 of 5: CRS = 1 - 2/4 = 0.5
        let crs = compute_crs(3, 5);
        assert!((crs - 0.5).abs() < 1e-10);
    }

    #[test]
    fn test_crs_batch() {
        // PCC values: [10, 30, 20, 40, 5]
        // Sorted desc: 40(idx3), 30(idx1), 20(idx2), 10(idx0), 5(idx4)
        // Ranks:        1,        2,        3,        4,        5
        // CRS:         1.0,      0.75,     0.5,      0.25,     0.0
        let pcc = [10.0, 30.0, 20.0, 40.0, 5.0];
        let crs = crs_batch_from_slice(&pcc);
        assert!((crs[0] - 0.25).abs() < 1e-10); // PCC=10, rank 4
        assert!((crs[1] - 0.75).abs() < 1e-10); // PCC=30, rank 2
        assert!((crs[2] - 0.5).abs() < 1e-10);  // PCC=20, rank 3
        assert!((crs[3] - 1.0).abs() < 1e-10);  // PCC=40, rank 1
        assert!((crs[4] - 0.0).abs() < 1e-10);  // PCC=5, rank 5
    }
}
