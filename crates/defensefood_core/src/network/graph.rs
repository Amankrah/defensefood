use pyo3::prelude::*;
use petgraph::graph::{DiGraph, NodeIndex};
use petgraph::visit::EdgeRef;
use std::collections::HashMap;

/// Edge weight in the exposure network, carrying commodity-specific metrics.
#[derive(Clone, Debug)]
pub struct EdgeWeight {
    pub commodity_hs: String,
    pub trade_weight: f64,   // M(c,i,j,t)    (Eq. 30)
    pub hazard_weight: f64,  // HIS(c,i,j,t)  (Eq. 31)
    pub dep_weight: f64,     // BDI(c,i,j,t)  (Eq. 32)
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
    pub fn add_trade_edge(
        &mut self,
        origin_m49: u16,
        destination_m49: u16,
        commodity_hs: String,
        trade_weight: f64,
        hazard_weight: f64,
        dep_weight: f64,
    ) {
        let origin_idx = self.ensure_node(origin_m49);
        let dest_idx = self.ensure_node(destination_m49);
        self.graph.add_edge(origin_idx, dest_idx, EdgeWeight {
            commodity_hs,
            trade_weight,
            hazard_weight,
            dep_weight,
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

    /// Get all edges from a given origin as (destination_m49, commodity, trade, hazard, dep).
    pub fn get_edges_from(&self, origin_m49: u16) -> Vec<(u16, String, f64, f64, f64)> {
        let Some(&idx) = self.node_indices.get(&origin_m49) else {
            return vec![];
        };
        self.graph
            .edges(idx)
            .map(|e| {
                let dest_m49 = self.graph[e.target()];
                let w = e.weight();
                (dest_m49, w.commodity_hs.clone(), w.trade_weight, w.hazard_weight, w.dep_weight)
            })
            .collect()
    }

    /// Get all edges into a given destination as (origin_m49, commodity, trade, hazard, dep).
    pub fn get_edges_to(&self, destination_m49: u16) -> Vec<(u16, String, f64, f64, f64)> {
        let Some(&idx) = self.node_indices.get(&destination_m49) else {
            return vec![];
        };
        self.graph
            .edges_directed(idx, petgraph::Direction::Incoming)
            .map(|e| {
                let origin_m49 = self.graph[e.source()];
                let w = e.weight();
                (origin_m49, w.commodity_hs.clone(), w.trade_weight, w.hazard_weight, w.dep_weight)
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
        net.add_trade_edge(250, 56, "1001".to_string(), 1000.0, 0.5, 0.3);
        net.add_trade_edge(250, 276, "1001".to_string(), 2000.0, 0.3, 0.1);
        assert_eq!(net.node_count(), 3);
        assert_eq!(net.edge_count(), 2);
    }

    #[test]
    fn test_get_edges() {
        let mut net = ExposureNetwork::new();
        net.add_trade_edge(250, 56, "1001".to_string(), 1000.0, 0.5, 0.3);
        let edges = net.get_edges_from(250);
        assert_eq!(edges.len(), 1);
        assert_eq!(edges[0].0, 56);
    }
}
