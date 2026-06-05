"""
Process-wide agent configuration, loaded from environment.

Resolves model ids by tier so call-sites can ask for ``"narrative"`` rather
than the latest model code. Tiers:

* ``route``      — cheap intent parsing / classification / ranking.
* ``narrative``  — primary brief composition (default for most use cases).
* ``heavy``      — escalation tier when the verifier fails twice.

Set via env (or backend/.env via Pydantic Settings):

    ANTHROPIC_API_KEY=...
    OPENAI_API_KEY=...
    DEFENSEFOOD_AGENT_DEFAULT_PROVIDER=anthropic
    DEFENSEFOOD_AGENT_MAX_COST_USD_PER_CALL=0.50
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ProviderName = Literal["anthropic", "openai"]
Tier = Literal["route", "narrative", "heavy"]


class AgentConfig(BaseSettings):
    """Environment-loaded singleton; instantiated once via :func:`get_config`."""

    model_config = SettingsConfigDict(
        env_prefix="DEFENSEFOOD_AGENT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # Keys live under their own env names by convention; map them here.
        env_nested_delimiter="__",
    )

    # API keys — read from env directly (not env_prefix-mangled).
    anthropic_api_key: str = Field(default="", validation_alias="ANTHROPIC_API_KEY")
    openai_api_key: str = Field(default="", validation_alias="OPENAI_API_KEY")

    # Default provider when no per-call override is given.
    default_provider: ProviderName = "anthropic"

    # Model resolution by tier. The plan calls for Claude defaults and OpenAI
    # fallbacks; either value can be overridden via env vars like
    # DEFENSEFOOD_AGENT_ANTHROPIC_NARRATIVE.
    anthropic_route: str = "claude-haiku-4-5-20251001"
    anthropic_narrative: str = "claude-sonnet-4-6"
    anthropic_heavy: str = "claude-opus-4-7"

    openai_route: str = "gpt-5-mini"
    openai_narrative: str = "gpt-5"
    openai_heavy: str = "gpt-5"

    # Cost discipline: agent loops abort and return a graceful stub when the
    # call's cumulative cost crosses this cap. Default is generous for R&D.
    max_cost_usd_per_call: float = 0.50

    # Default verification mode (``strict``, ``fast``, or ``off``); see the
    # reflection pass in agent.runner.
    verify_default: Literal["strict", "fast", "off"] = "strict"

    # Cache TTL for generated briefs, in seconds. 24h matches the plan; longer
    # is safe because the cache key includes a snapshot_hash that changes when
    # the corpus or scoring config changes.
    brief_cache_ttl_seconds: int = 24 * 60 * 60

    # Path to the SQLite database. Relative paths resolve under backend/data/.
    db_path: str = "data/agent.db"

    # Where the agent module's prompt fragments live (markdown).
    prompts_dir: str = "defensefood/agent/prompts"

    def resolve_model(self, provider: ProviderName, tier: Tier) -> str:
        """Return the concrete model id for ``(provider, tier)``."""
        key = f"{provider}_{tier}"
        try:
            return getattr(self, key)
        except AttributeError as exc:  # pragma: no cover — defensive
            raise ValueError(
                f"No model configured for provider={provider!r} tier={tier!r}"
            ) from exc

    def have_anthropic(self) -> bool:
        return bool(self.anthropic_api_key)

    def have_openai(self) -> bool:
        return bool(self.openai_api_key)


@lru_cache(maxsize=1)
def get_config() -> AgentConfig:
    """Module-level singleton accessor."""
    return AgentConfig()  # pyright: ignore[reportCallIssue]


def reset_config_cache() -> None:
    """Clear the lru_cache so tests can rebuild AgentConfig after env mutation."""
    get_config.cache_clear()
