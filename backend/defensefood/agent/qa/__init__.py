"""Q&A subsystem (Phase 4)."""

from defensefood.agent.qa.runner import handle_query, QAResult
from defensefood.agent.qa.schemas import (
    IntentClassification,
    QATurn,
    QueryEntities,
)

__all__ = [
    "IntentClassification",
    "QATurn",
    "QueryEntities",
    "QAResult",
    "handle_query",
]
