"""Pydantic models for network graph serialisation."""

from pydantic import BaseModel


class GraphNode(BaseModel):
    """A node in the exposure network (a country)."""
    m49: int
    name: str = ""
    is_eu27: bool = False
    acep: float = 0.0


class GraphEdge(BaseModel):
    """An edge in the exposure network (a corridor)."""
    origin_m49: int
    destination_m49: int
    commodity_hs: str
    trade_weight: float = 0.0
    hazard_weight: float = 0.0
    dep_weight: float = 0.0


class NetworkSummary(BaseModel):
    """Serialised exposure network for the frontend."""
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    node_count: int
    edge_count: int
