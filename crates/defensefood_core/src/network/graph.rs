use pyo3::prelude::*;
use petgraph::graph::{DiGraph, NodeIndex};
use petgraph::visit::EdgeRef;
use std::collections::HashMap;

/// Market-presence classification per RASFF SOP semantics. Mirrors the Python
/// `market_presence_from_roles()` helper and lets ACEP/ORPS filter or split
/// by role the way the 2025 Pan et al. *Discover Food* paper recommends.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum EdgeRole {
    /// distribution and/or followUp present — product is/may be on this market.
    Confirmed,
    /// notifier-only — country detected the hazard; market presence not asserted.
    Detected,
    /// attention-only — per RASFF, product is not on this market.
    Informational,
    /// no role recorded (defensive default).
    Unknown,
}

impl EdgeRole {
    /// Parse the same four strings emitted by Python `market_presence_from_roles`.
    pub fn from_str(s: &str) -> Self {
        match s {
            "confirmed" => EdgeRole::Confirmed,
            "detected" => EdgeRole::Detected,
            "informational" => EdgeRole::Informational,
            _ => EdgeRole::Unknown,
        }
    }

    pub fn as_str(self) -> &'static str {
        match self {
            EdgeRole::Confirmed => "confirmed",
            EdgeRole::Detected => "detected",
            EdgeRole::Informational => "informational",
            EdgeRole::Unknown => "unknown",
        }
    }
}

/// Edge weight in the exposure network, carrying commodity-specific metrics.
#[derive(Clone, Debug)]
pub struct EdgeWeight {
    pub commodity_hs: String,
    pub trade_weight: f64,   // M(c,i,j,t)    (Eq. 30)
    pub hazard_weight: f64,  // HIS(c,i,j,t)  (Eq. 31)
    pub dep_weight: f64,     // BDI(c,i,j,t)  (Eq. 32)
    pub role: EdgeRole,      // RASFF market-presence classification
}

/// Exposure Network as a directed weighted graph G = (V, E).
///
/// V = O ∪ N (all origin and destination countries)
/// E ⊆ O × N (directed edges from origin to destination)
///
/// An edge (j → i) exists if origin j has triggered a RASFF notification
/// where country i appeared as notifier, attention, or follow-up country.
#[pyclass]
pub struct ExposureNetwork {
    pub(crate) graph: DiGraph<u16, EdgeWeight>,
    pub(crate) node_indices: HashMap<u16, NodeIndex>,
}

impl ExposureNetwork {
    /// Add or retrieve a node for a country (by M49 code).
    fn ensure_node(&mut self, m49: u16) -> NodeIndex {
        *self.node_indices.entry(m49).or_insert_with(|| self.graph.add_node(m49))
    }
}

#[pymethods]
impl ExposureNetwork {
    #[new]
    pub fn new() -> Self {
        Self {
            graph: DiGraph::new(),
            node_indices: HashMap::new(),
        }
    }

    /// Add a directed edge from origin to destination with commodity-specific weights.
    ///
    /// ``role`` accepts the strings ``"confirmed"`` / ``"detected"`` /
    /// ``"informational"`` (or anything else → ``Unknown``). Defaults to
    /// ``"unknown"`` when callers haven't migrated yet.
    #[pyo3(signature = (origin_m49, destination_m49, commodity_hs, trade_weight, hazard_weight, dep_weight, role=None))]
    pub fn add_trade_edge(
        &mut self,
        origin_m49: u16,
        destination_m49: u16,
        commodity_hs: String,
        trade_weight: f64,
        hazard_weight: f64,
        dep_weight: f64,
        role: Option<&str>,
    ) {
        let origin_idx = self.ensure_node(origin_m49);
        let dest_idx = self.ensure_node(destination_m49);
        let edge_role = role.map(EdgeRole::from_str).unwrap_or(EdgeRole::Unknown);
        self.graph.add_edge(origin_idx, dest_idx, EdgeWeight {
            commodity_hs,
            trade_weight,
            hazard_weight,
            dep_weight,
            role: edge_role,
        });
    }

    /// Get all node M49 codes in the network.
    pub fn get_all_nodes(&self) -> Vec<u16> {
        self.node_indices.keys().copied().collect()
    }

    /// Number of nodes (countries) in the network.
    pub fn node_count(&self) -> usize {
        self.graph.node_count()
    }

    /// Number of edges (corridors) in the network.
    pub fn edge_count(&self) -> usize {
        self.graph.edge_count()
    }

    /// Get all edges from a given origin as
    /// (destination_m49, commodity, trade, hazard, dep, role).
    pub fn get_edges_from(&self, origin_m49: u16) -> Vec<(u16, String, f64, f64, f64, String)> {
        let Some(&idx) = self.node_indices.get(&origin_m49) else {
            return vec![];
        };
        self.graph
            .edges(idx)
            .map(|e| {
                let dest_m49 = self.graph[e.target()];
                let w = e.weight();
                (
                    dest_m49,
                    w.commodity_hs.clone(),
                    w.trade_weight,
                    w.hazard_weight,
                    w.dep_weight,
                    w.role.as_str().to_string(),
                )
            })
            .collect()
    }

    /// Get all edges into a given destination as
    /// (origin_m49, commodity, trade, hazard, dep, role).
    pub fn get_edges_to(&self, destination_m49: u16) -> Vec<(u16, String, f64, f64, f64, String)> {
        let Some(&idx) = self.node_indices.get(&destination_m49) else {
            return vec![];
        };
        self.graph
            .edges_directed(idx, petgraph::Direction::Incoming)
            .map(|e| {
                let origin_m49 = self.graph[e.source()];
                let w = e.weight();
                (
                    origin_m49,
                    w.commodity_hs.clone(),
                    w.trade_weight,
                    w.hazard_weight,
                    w.dep_weight,
                    w.role.as_str().to_string(),
                )
            })
            .collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_build_network() {
        let mut net = ExposureNetwork::new();
        net.add_trade_edge(250, 56, "1001".to_string(), 1000.0, 0.5, 0.3, None);
        net.add_trade_edge(250, 276, "1001".to_string(), 2000.0, 0.3, 0.1, None);
        assert_eq!(net.node_count(), 3);
        assert_eq!(net.edge_count(), 2);
    }

    #[test]
    fn test_get_edges_carries_role() {
        let mut net = ExposureNetwork::new();
        net.add_trade_edge(250, 56, "1001".to_string(), 1000.0, 0.5, 0.3, Some("confirmed"));
        net.add_trade_edge(250, 56, "1002".to_string(), 500.0, 0.4, 0.2, Some("informational"));
        let edges = net.get_edges_from(250);
        assert_eq!(edges.len(), 2);
        // tuple layout: (dest, hs, trade, hazard, dep, role)
        let by_role: std::collections::HashMap<&str, &(u16, String, f64, f64, f64, String)> =
            edges.iter().map(|e| (e.5.as_str(), e)).collect();
        assert!(by_role.contains_key("confirmed"));
        assert!(by_role.contains_key("informational"));
    }

    #[test]
    fn test_role_from_str_unknown_default() {
        assert_eq!(EdgeRole::from_str("confirmed"), EdgeRole::Confirmed);
        assert_eq!(EdgeRole::from_str("detected"), EdgeRole::Detected);
        assert_eq!(EdgeRole::from_str("informational"), EdgeRole::Informational);
        assert_eq!(EdgeRole::from_str("bogus"), EdgeRole::Unknown);
    }
}
