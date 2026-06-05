"""
Pydantic schemas for the conversational Q&A workbench.

Two stages produce structured outputs:

1. **IntentClassification** — from a cheap routing call (Haiku / GPT-5 mini).
   Distinguishes in-scope research queries from out-of-scope ones, and
   extracts canonical entity hints (HS codes, M49 codes, metric keys,
   period bounds) the second stage can use.

2. **QATurn** — the final, audit-friendly answer the Sonnet composition pass
   submits. Carries narrative markdown, cited signals, an optional
   structured data block (for filter-style queries that should render as a
   table), and a worse-of-two confidence label.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from defensefood.agent.briefs.schemas import CitedSignal, Confidence

# Intents the router can emit. ``out_of_scope`` short-circuits the pipeline.
Intent = Literal[
    "lookup",
    "filter",
    "compare",
    "explain",
    "methodology",
    "narrative_freeform",
    "out_of_scope",
]


class QueryEntities(BaseModel):
    """Canonical entity hints extracted by the intent router.

    All fields are optional — the router only fills what it confidently
    extracts. The composer uses these as guidance, not as constraints.
    """

    commodity_hs: list[str] = Field(
        default_factory=list,
        description="HS codes mentioned or implied, e.g. ['30771', '100630'].",
        max_length=8,
    )
    country_m49: list[int] = Field(
        default_factory=list,
        description="UN M49 country codes mentioned or implied.",
        max_length=8,
    )
    metric_keys: list[str] = Field(
        default_factory=list,
        description="Catalogue metric keys, e.g. ['cvs', 'sci', 'his'].",
        max_length=8,
    )
    period_a: Optional[int] = Field(
        default=None, description="Baseline trade year if the query implies one."
    )
    period_b: Optional[int] = Field(
        default=None, description="Comparison trade year if the query implies one."
    )
    direction: Optional[Literal["rising", "falling", "any"]] = None
    threshold: Optional[float] = Field(
        default=None,
        description=(
            "Optional numeric threshold the query references, e.g. for a "
            "'CVS > 0.5' filter the value 0.5 ends up here."
        ),
    )


class IntentClassification(BaseModel):
    """Output of stage 1 (routing).

    The router decides whether the query is something the corpus can answer
    (``in_scope=True``) and tags it with a coarse intent so the composer can
    pick the right voice.
    """

    intent: Intent = Field(
        description=(
            "Coarse intent. Use 'out_of_scope' for anything the corpus cannot "
            "answer (e.g. weather, generic chat, requests to take action)."
        ),
    )
    in_scope: bool = Field(
        description="False when the query is unanswerable from the corpus.",
    )
    refusal_reason: Optional[str] = Field(
        default=None,
        description=(
            "One short sentence shown to the user when in_scope is False. "
            "Explain what the corpus can and cannot answer."
        ),
    )
    entities: QueryEntities = Field(default_factory=QueryEntities)


# ── final answer schema ─────────────────────────────────────────────────────


class QATableColumn(BaseModel):
    """Schema for a single column in a structured-data answer."""

    key: str
    label: str
    align: Literal["left", "right"] = "left"


class QAStructuredData(BaseModel):
    """Optional table block the UI can render alongside the prose.

    Used when the answer is naturally tabular (filter / compare queries).
    The narrative still leads; the table is the supporting evidence.

    All fields are intentionally permissive: the model occasionally produces
    partial drafts (empty columns while still composing, mixed-type cell
    values, slightly over-cap row counts) and we'd rather render whatever it
    gives us than fail the entire turn.
    """

    title: str = ""
    columns: list[QATableColumn] = Field(default_factory=list, max_length=12)
    rows: list[dict[str, Any]] = Field(default_factory=list, max_length=100)
    lane_keys: list[str] = Field(
        default_factory=list,
        description=(
            "Optional 'hs/dest/origin' anchors for the rows; the UI can wire "
            "them as clickable links to the lane forensic page."
        ),
        max_length=100,
    )


class QATurn(BaseModel):
    """The composer's final structured output for a single turn."""

    answer_markdown: str = Field(
        description=(
            "Markdown answer. Lead with the answer in one short sentence, then "
            "supporting evidence in 1 to 3 short paragraphs."
        ),
    )
    key_signals: list[CitedSignal] = Field(
        default_factory=list,
        description=(
            "Every numerical claim, paired with source_field. Empty when the "
            "answer is purely qualitative (explain / methodology intents)."
        ),
        max_length=20,
    )
    structured_data: Optional[QAStructuredData] = Field(
        default=None,
        description="Optional table block for filter / compare answers.",
    )
    caveats: list[str] = Field(default_factory=list, max_length=10)
    confidence: Confidence = "med"
    verifier_notes: list[str] = Field(default_factory=list)
