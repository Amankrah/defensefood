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


class CountryHalf(BaseModel):
    """A single sub-agent's contribution (inbound OR outbound)."""

    markdown: str = Field(
        description="One short paragraph of analyst prose for this half.",
    )
    signals: list[CitedSignal] = Field(
        description="Every numerical claim in markdown, paired with a source field.",
        max_length=8,
    )
    notable_lanes: list[str] = Field(
        default_factory=list,
        description=(
            "Up to three lane keys 'hs/dest/origin' that anchor the narrative; "
            "consumed by the synthesiser so the final brief points readers at them."
        ),
        max_length=5,
    )


class CountryBrief(BaseModel):
    """Structured output for the country brief.

    Two parallel sub-agents produce inbound/outbound halves; a synthesiser
    merges them into this shape. ``inbound_markdown`` or ``outbound_markdown``
    may be empty when the country has no corridors on that side.
    """

    headline: str = Field(
        description="One sentence summary covering both halves.",
        max_length=240,
    )
    inbound_markdown: str = Field(
        default="",
        description=(
            "Inbound exposure narrative: ACEP role split, top bottleneck "
            "commodities, dominant origins. Empty if the country has no "
            "inbound footprint."
        ),
    )
    outbound_markdown: str = Field(
        default="",
        description=(
            "Outbound propagation narrative: top ORPS commodities, which "
            "destinations carry the most exposure from this origin. Empty if "
            "the country has no outbound footprint."
        ),
    )
    key_signals: list[CitedSignal] = Field(
        default_factory=list,
        description="All numerical claims across both halves.",
        max_length=16,
    )
    notable_lanes: list[str] = Field(
        default_factory=list,
        description=(
            "Pointer lane keys 'hs/dest/origin' that the brief references; "
            "the UI can render these as clickable chips."
        ),
        max_length=8,
    )
    caveats: list[str] = Field(default_factory=list, max_length=8)
    confidence: Confidence = "med"
    verifier_notes: list[str] = Field(default_factory=list)
    sub_agent_notes: list[str] = Field(
        default_factory=list,
        description=(
            "Trace of which sub-agents ran. Internal; the UI can hide this "
            "behind the 'Show evidence' expander."
        ),
    )


# ── Phase 3: period-shift diagnostic ──────────────────────────────────────


Direction = Literal["rising", "falling", "stable"]


class PeriodMover(BaseModel):
    """A single corridor that moved between the two periods.

    The agent picks 3 to 6 of these per category (risers / fallers / broken
    stable) from the pre-loaded compare_corpus_periods output and references
    them in the narrative.
    """

    lane_key: str = Field(
        description="'hs/dest/origin' string. Used by the UI to make this clickable.",
    )
    label: str = Field(
        description="Human label, e.g. 'Spain mussels into France'.",
    )
    cvs_a: Optional[float] = None
    cvs_b: Optional[float] = None
    cvs_delta: Optional[float] = Field(
        default=None,
        description="Signed CVS movement between period_a and period_b.",
    )
    notif_delta: Optional[int] = None
    direction: Direction = "stable"
    explanation: str = Field(
        default="",
        description=(
            "One short sentence on what changed and why it matters. Plain "
            "analyst voice, no em-dashes, no essay scaffolding."
        ),
    )


class PeriodCluster(BaseModel):
    """A group of corridors that moved together between the two periods."""

    cluster_label: str = Field(
        description=(
            "Human label, e.g. 'Mussels into France' (commodity chapter + "
            "destination) or 'Indian rice exports'."
        ),
    )
    lane_count: int
    mean_movement: float = Field(
        description="Average signed movement across the cluster's lanes.",
    )
    criterion: str = Field(
        description="Which delta defined the cluster: cvs_delta / notif_delta / etc.",
    )
    lane_keys: list[str] = Field(
        default_factory=list,
        description="Up to 5 'hs/dest/origin' anchors.",
        max_length=5,
    )
    explanation: str = Field(
        default="",
        description="One sentence on what the cluster represents.",
    )


class PeriodShiftBrief(BaseModel):
    """Structured output for the corpus-wide period-shift diagnostic.

    Compares the latest loaded period against the prior period and surfaces
    the corridors and clusters that moved. The dashboard tile renders this
    plus a clickable list of movers; the priority queue stays below it.
    """

    headline: str = Field(
        description=(
            "One sentence summary of the period shift, under 30 words. "
            "Example: 'Comparing 2023 to 2022, 47 corridors moved up and 33 down, "
            "with mussels into France the strongest emerging cluster.'"
        ),
        max_length=300,
    )
    body_markdown: str = Field(
        description=(
            "Two short paragraphs: first paragraph is the corpus-level summary "
            "(totals, median delta, broad direction). Second paragraph names "
            "the strongest single mover or cluster and explains the change."
        ),
    )
    period_a: int
    period_b: int
    top_risers: list[PeriodMover] = Field(
        default_factory=list,
        description="Corridors with the largest positive CVS deltas.",
        max_length=6,
    )
    top_fallers: list[PeriodMover] = Field(
        default_factory=list,
        description="Corridors with the largest negative CVS deltas.",
        max_length=6,
    )
    emerging_clusters: list[PeriodCluster] = Field(
        default_factory=list,
        description="Commodity-origin clusters that moved together.",
        max_length=4,
    )
    key_signals: list[CitedSignal] = Field(
        default_factory=list,
        description=(
            "Every numerical claim in the body, paired with a source field. "
            "For corpus aggregates use source_field='corpus_total' / "
            "'corpus_median' / 'corpus_risers' etc."
        ),
        max_length=10,
    )
    caveats: list[str] = Field(default_factory=list, max_length=6)
    confidence: Confidence = "med"
    verifier_notes: list[str] = Field(default_factory=list)


# ── Phase 5: hypothesis generator + anomaly explainer ─────────────────────


class FalsifyingTest(BaseModel):
    """A structured description of how to test (falsify) a hypothesis.

    Not executable directly; the UI shows it so the researcher can run it
    themselves, and a future ``test_hypothesis`` runner can use it. Keep
    the shape simple to make it model-friendly.
    """

    description: str = Field(
        description=(
            "One sentence describing what would falsify the hypothesis, e.g. "
            "'Compare 2022 and 2023 origin shares and confirm the second-largest "
            "supplier dropped to zero.'"
        ),
    )
    suggested_tools: list[str] = Field(
        default_factory=list,
        description=(
            "Tool names the runner would invoke. Examples: 'compare_periods', "
            "'get_trade_anomalies', 'country_inbound_exposure'."
        ),
        max_length=4,
    )


class Hypothesis(BaseModel):
    """A single candidate explanation for an observed pattern on a target."""

    headline: str = Field(
        description=(
            "One short sentence stating the hypothesis. Example: 'The second-"
            "largest supplier exited the lane, concentrating imports on the "
            "remaining majority origin.'"
        ),
        max_length=240,
    )
    narrative: str = Field(
        description=(
            "One to two paragraphs explaining the mechanism and the evidence "
            "in the corpus that supports or contradicts it."
        ),
    )
    confidence: Confidence = Field(
        default="med",
        description=(
            "How well the existing corpus supports this hypothesis. 'high' = "
            "evidence directly supports it; 'med' = circumstantial; 'low' = "
            "speculative or contradicted."
        ),
    )
    supporting_signals: list[CitedSignal] = Field(
        default_factory=list,
        description="Cited values from the corpus that support the hypothesis.",
        max_length=6,
    )
    contradicting_signals: list[CitedSignal] = Field(
        default_factory=list,
        description="Cited values that argue against the hypothesis.",
        max_length=4,
    )
    falsifying_test: FalsifyingTest = Field(
        description="What would settle the question if we ran it.",
    )
    next_data: str = Field(
        default="",
        description=(
            "What additional data outside the corpus would clinch the answer. "
            "Example: 'Shipping-route lineage data from a logistics provider'."
        ),
    )


class HypothesisSet(BaseModel):
    """The agent's set of candidate explanations for a target lane.

    Submitted via the ``submit_hypotheses`` forced tool.
    """

    target_label: str = Field(
        description=(
            "Human label for the target, e.g. 'Spain mussels into France'."
        ),
    )
    pattern_summary: str = Field(
        description=(
            "One sentence summarising the observed pattern the hypotheses are "
            "trying to explain. Plain analyst voice, no em-dashes."
        ),
        max_length=300,
    )
    hypotheses: list[Hypothesis] = Field(
        description="Two to four candidate explanations, sorted by confidence.",
        min_length=1,
        max_length=4,
    )
    caveats: list[str] = Field(default_factory=list, max_length=6)
    verifier_notes: list[str] = Field(default_factory=list)


# ── Anomaly explainer ─────────────────────────────────────────────────────


AnomalyVerdict = Literal["anomalous", "borderline", "not_anomalous"]


class AnomalyExplanation(BaseModel):
    """Deeper-than-a-brief diagnostic of why a lane reads as anomalous.

    Compared to ``LaneBrief``, this one explicitly weighs the evidence on
    both sides: "what makes this stand out" + "what would convince me it
    is not anomalous". Designed so a researcher can use the structured
    output as a labelling input for the future predictive subsystem.
    """

    target_label: str = Field(
        description="Human label, e.g. 'Croatia corn into Slovenia'.",
    )
    verdict: AnomalyVerdict = Field(
        description=(
            "anomalous = the lane stands out across multiple axes; "
            "borderline = stands out on one axis but counter-evidence exists; "
            "not_anomalous = looks like a typical lane in its peer group."
        ),
    )
    headline: str = Field(
        description="One sentence stating the verdict and the strongest cue.",
        max_length=300,
    )
    why_anomalous: str = Field(
        description=(
            "One paragraph naming the specific deviations from peer behaviour "
            "(magnitude, sustained vs spike, structural vs hazard, cross-period "
            "drift). Every numerical claim appears in supporting_signals."
        ),
    )
    why_not: str = Field(
        default="",
        description=(
            "One paragraph stating the strongest counter-evidence: data "
            "quality limits, plausible non-anomalous interpretations, or "
            "missing context. Empty when the verdict is 'anomalous' AND no "
            "counter-evidence exists in the corpus."
        ),
    )
    supporting_signals: list[CitedSignal] = Field(
        default_factory=list,
        description=(
            "Every numerical value cited in why_anomalous or why_not. The "
            "verifier re-fetches each."
        ),
        max_length=12,
    )
    peer_comparison: str = Field(
        default="",
        description=(
            "One sentence comparing the lane to its catalogue-defined peers "
            "(same commodity chapter, similar destination role). Empty when "
            "peers are not informative."
        ),
    )
    confidence: Confidence = "med"
    caveats: list[str] = Field(default_factory=list, max_length=6)
    verifier_notes: list[str] = Field(default_factory=list)
