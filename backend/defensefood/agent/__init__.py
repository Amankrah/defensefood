"""
DefenseFood agent subsystem.

An agentic interpretation, briefs, and Q&A layer over the food-fraud diagnostic
corpus. The agent runs tool-use loops against typed Python functions that read
``state.corridor_metrics`` (and friends) directly, returns structured Pydantic
outputs, and is verified by a reflection pass that re-fetches every cited
number before the brief reaches the UI.

Public entry points:
  * ``agent.config.get_config()`` — process-wide AgentConfig singleton.
  * ``agent.runner.run_brief(...)`` — top-level brief generation with caching.
  * ``agent.tools.TOOL_REGISTRY`` — runtime registry of all `@tool` functions.

Implemented in Phase 1; later phases add briefs/, qa/, predictive/ subpackages.
"""

from defensefood.agent.config import AgentConfig, get_config

__all__ = ["AgentConfig", "get_config"]
