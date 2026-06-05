"""
Pydantic schemas for agent briefs, shared across use cases.

A ``CitedSignal`` is the atomic unit of verifiability: every number the agent
mentions in narrative prose must be paired with one of these so the reflection
pass can re-fetch the value and compare. A ``LaneBrief`` is the structured
output for Phase 1.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

Band = Literal["low", "med", "high", "flag", "unknown"]
Confidence = Literal["low", "med", "high"]


class CitedSignal(BaseModel):
    """A single numerical signal the agent cites in the narrative.

    The reflection pass re-fetches ``value`` by looking up ``source_field`` on
    the corridor record (or invoking the corresponding tool) and flags
    mismatches before the brief is persisted.
    """

    name: str = Field(
        description="Short human label, e.g. 'Supply criticality (SCI)'.",
    )
    source_field: str = Field(
        description=(
            "Exact corridor-record field name. Common: cvs, cvs_mode, sci, his, "
            "hdi, bdi, idr, ocs, hhi, ssr, delta_hhi, delta_ocs, mtd, z_uv, "
            "z_volume, dgi, notification_count, severity_total, market_presence."
        ),
    )
    value: float | int | str | None = Field(
        description="The cited value as it should appear in the narrative.",
    )
    band: Band = Field(
        default="unknown",
        description=(
            "Catalogue scale band at this value, when the metric has bands. "
            "Use 'unknown' for raw counts or strings."
        ),
    )


class LaneBrief(BaseModel):
    """Structured output for the lane forensic brief.

    The agent submits this via the ``submit_lane_brief`` tool. Field shapes
    are kept narrow so the reflection pass can audit each piece.
    """

    headline: str = Field(
        description="One sentence summary — at most ~140 characters.",
        max_length=240,
    )
    body_markdown: str = Field(
        description=(
            "Two to three paragraphs of analyst-style narrative. Every numerical "
            "claim here must appear in key_signals with a matching source_field."
        ),
    )
    key_signals: list[CitedSignal] = Field(
        description="Every cited number. The verifier uses this for grounding.",
        min_length=1,
        max_length=12,
    )
    caveats: list[str] = Field(
        default_factory=list,
        description=(
            "Mandatory bullet phrases when data-quality flags apply (sci_his "
            "fallback, informational market presence, IDR>1, etc)."
        ),
        max_length=8,
    )
    confidence: Confidence = Field(
        description="Researcher-facing confidence label.",
    )

    # Internal — set after the verifier runs.
    verifier_notes: list[str] = Field(
        default_factory=list,
        description="Reflection-pass notes (mismatches found, sentences auto-corrected).",
    )


class CountryBrief(BaseModel):
    """Phase 2 — structured output for the country brief (stub for now)."""

    headline: str
    inbound_markdown: Optional[str] = None
    outbound_markdown: Optional[str] = None
    key_signals: list[CitedSignal] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
    confidence: Confidence = "med"
