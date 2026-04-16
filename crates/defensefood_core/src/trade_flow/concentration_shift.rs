use pyo3::prelude::*;

/// Trade Network Concentration Shift (Eq. 28):
///   Delta_HHI(c,i,t) = HHI(c,i,t) - HHI(c,i,t-1)
///
/// A sudden increase in HHI combined with a new or rapidly growing corridor
/// signals potential re-routing.
#[pyfunction]
pub fn compute_delta_hhi(hhi_current: f64, hhi_previous: f64) -> f64 {
    hhi_current - hhi_previous
}

/// Origin Country Share Shift (Eq. 29):
///   Delta_OCS(c,i,j,t) = OCS(c,i,j,t) - OCS(c,i,j,t-1)
///
/// A rapid increase in OCS for a previously minor origin, while a traditionally
/// dominant origin's OCS decreases, is a structural shift warranting investigation.
#[pyfunction]
pub fn compute_delta_ocs(ocs_current: f64, ocs_previous: f64) -> f64 {
    ocs_current - ocs_previous
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_delta_hhi_increase() {
        let delta = compute_delta_hhi(0.45, 0.30);
        assert!((delta - 0.15).abs() < 1e-10);
    }

    #[test]
    fn test_delta_ocs_decrease() {
        let delta = compute_delta_ocs(0.3, 0.5);
        assert!((delta - (-0.2)).abs() < 1e-10);
    }
}
