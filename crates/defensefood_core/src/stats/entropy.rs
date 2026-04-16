/// Compute Shannon entropy: -sum(p_i * ln(p_i)) for non-zero proportions.
/// Input: a slice of non-negative counts or proportions.
/// If raw counts are provided, they are normalised internally.
pub fn shannon_entropy(counts: &[f64]) -> f64 {
    let total: f64 = counts.iter().sum();
    if total == 0.0 {
        return 0.0;
    }

    let mut entropy = 0.0;
    for &c in counts {
        if c > 0.0 {
            let p = c / total;
            entropy -= p * p.ln();
        }
    }
    entropy
}

/// Compute normalised Shannon entropy (H / ln(k)) where k is the number of categories.
/// Returns a value in [0, 1].
pub fn normalised_entropy(counts: &[f64], num_categories: usize) -> f64 {
    if num_categories <= 1 {
        return 0.0;
    }
    let h = shannon_entropy(counts);
    let h_max = (num_categories as f64).ln();
    if h_max == 0.0 {
        return 0.0;
    }
    h / h_max
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_all_same_type() {
        // All notifications are one type -> entropy = 0
        let counts = [10.0, 0.0, 0.0, 0.0, 0.0, 0.0];
        let h = normalised_entropy(&counts, 6);
        assert!((h - 0.0).abs() < 1e-10);
    }

    #[test]
    fn test_uniform_distribution() {
        // Equal distribution -> normalised entropy = 1
        let counts = [10.0, 10.0, 10.0, 10.0, 10.0, 10.0];
        let h = normalised_entropy(&counts, 6);
        assert!((h - 1.0).abs() < 1e-10);
    }

    #[test]
    fn test_empty() {
        let counts = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0];
        let h = normalised_entropy(&counts, 6);
        assert!((h - 0.0).abs() < 1e-10);
    }
}
