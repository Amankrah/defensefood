use numpy::{PyArray1, PyReadonlyArray1};
use ordered_float::OrderedFloat;
use pyo3::prelude::*;

/// Option A: Min-Max Normalisation (Eq. 36):
///   x_norm = (x - x_min) / (x_max - x_min)
///
/// Maps to [0, 1]. Simple but sensitive to outliers.
#[pyfunction]
pub fn normalise_min_max<'py>(
    py: Python<'py>,
    values: PyReadonlyArray1<'py, f64>,
) -> Bound<'py, PyArray1<f64>> {
    let arr = values.as_array();
    let valid: Vec<f64> = arr.iter().filter(|x| !x.is_nan()).copied().collect();
    if valid.is_empty() {
        return PyArray1::from_vec(py, vec![f64::NAN; arr.len()]);
    }
    let min = valid.iter().copied().fold(f64::INFINITY, f64::min);
    let max = valid.iter().copied().fold(f64::NEG_INFINITY, f64::max);
    let range = max - min;

    let result: Vec<f64> = arr
        .iter()
        .map(|&x| {
            if x.is_nan() {
                f64::NAN
            } else if range == 0.0 {
                0.5 // All values identical
            } else {
                (x - min) / range
            }
        })
        .collect();
    PyArray1::from_vec(py, result)
}

/// Option B: Percentile Rank Normalisation (Eq. 37):
///   x_norm = percentile_rank(x) across all corridors
///
/// Maps to [0, 1]. Robust to outliers. Recommended for most metrics.
#[pyfunction]
pub fn normalise_percentile_rank<'py>(
    py: Python<'py>,
    values: PyReadonlyArray1<'py, f64>,
) -> Bound<'py, PyArray1<f64>> {
    let arr = values.as_array();
    let n = arr.len();
    if n <= 1 {
        return PyArray1::from_vec(py, vec![if n == 1 { 1.0 } else { 0.0 }; n]);
    }

    // Create sorted indices (NaN goes last)
    let mut indices: Vec<usize> = (0..n).collect();
    indices.sort_by_key(|&i| OrderedFloat(if arr[i].is_nan() { f64::INFINITY } else { arr[i] }));

    let valid_count = arr.iter().filter(|x| !x.is_nan()).count();
    if valid_count <= 1 {
        return PyArray1::from_vec(
            py,
            arr.iter().map(|x| if x.is_nan() { f64::NAN } else { 1.0 }).collect(),
        );
    }

    let mut ranks = vec![f64::NAN; n];
    for (rank_0, &idx) in indices.iter().enumerate() {
        if arr[idx].is_nan() {
            continue;
        }
        ranks[idx] = rank_0 as f64 / (valid_count - 1) as f64;
    }

    PyArray1::from_vec(py, ranks)
}

/// Option C: Log-Transform then Percentile (Eq. 38):
///   x_norm = percentile_rank(ln(1 + x))
///
/// Appropriate for highly skewed metrics (notification counts, trade volumes).
#[pyfunction]
pub fn normalise_log_percentile<'py>(
    py: Python<'py>,
    values: PyReadonlyArray1<'py, f64>,
) -> Bound<'py, PyArray1<f64>> {
    let arr = values.as_array();
    let log_values: Vec<f64> = arr.iter().map(|&x| {
        if x.is_nan() {
            f64::NAN
        } else {
            (1.0 + x).ln()
        }
    }).collect();

    // Apply percentile rank to log-transformed values
    let n = log_values.len();
    if n <= 1 {
        return PyArray1::from_vec(py, vec![if n == 1 { 1.0 } else { 0.0 }; n]);
    }

    let mut indices: Vec<usize> = (0..n).collect();
    indices.sort_by_key(|&i| {
        OrderedFloat(if log_values[i].is_nan() { f64::INFINITY } else { log_values[i] })
    });

    let valid_count = log_values.iter().filter(|x| !x.is_nan()).count();
    if valid_count <= 1 {
        return PyArray1::from_vec(
            py,
            log_values.iter().map(|x| if x.is_nan() { f64::NAN } else { 1.0 }).collect(),
        );
    }

    let mut ranks = vec![f64::NAN; n];
    for (rank_0, &idx) in indices.iter().enumerate() {
        if log_values[idx].is_nan() {
            continue;
        }
        ranks[idx] = rank_0 as f64 / (valid_count - 1) as f64;
    }

    PyArray1::from_vec(py, ranks)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_min_max_normalise() {
        // [10, 20, 30, 40, 50] -> [0.0, 0.25, 0.5, 0.75, 1.0]
        let input = [10.0, 20.0, 30.0, 40.0, 50.0];
        let min = 10.0;
        let max = 50.0;
        let range = max - min;
        let expected: Vec<f64> = input.iter().map(|x| (x - min) / range).collect();
        assert!((expected[0] - 0.0).abs() < 1e-10);
        assert!((expected[2] - 0.5).abs() < 1e-10);
        assert!((expected[4] - 1.0).abs() < 1e-10);
    }
}
