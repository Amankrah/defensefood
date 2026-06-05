# Predictive subsystem (scaffold)

This package is a placeholder for the predictive epic that follows the
agent subsystem build-out. Nothing here trains a model yet; the modules
exist so the rest of the agent stack can reference stable type contracts
while the epic is designed and built.

## Where the inputs come from

The agent subsystem already produces structured labels that the predictive
model will consume:

- **Anomaly explainer** (Phase 5.3) — every `AnomalyExplanation` carries a
  three-class verdict (`anomalous` / `borderline` / `not_anomalous`) plus
  `supporting_signals`. Verdicts become training labels; signals become
  feature anchors for the explainer side.
- **Hypothesis generator** (Phase 5.1) — `Hypothesis.confidence` and
  `supporting_signals` / `contradicting_signals` give the model a notion
  of "which lanes had a well-grounded explanation" vs "which had only
  speculative ones". Useful for an active-learning loop.
- **Period-shift diagnostic** (Phase 3) — corpus-wide deltas the model
  can use as auto-labelled examples of risers / fallers.

The `feature_extractor.CorridorFeatureVector` shape mirrors the
`dependency_history` snapshot so the extractor stays a thin wrapper over
the engine's existing per-period output. Engineered features (rolling
means, period-over-period deltas, peer-relative z-scores) live in
`CorridorFeatureVector.derived` so the schema doesn't churn each time
the epic adds one.

## Where the outputs go

- The **anomaly explainer** can, once a forecaster exists, cite a model
  prediction in its narrative ("the model put next-period CVS at 0.42,
  but the actual was 0.65"). Useful for surfacing model misses.
- The **research workbench Q&A** (Phase 4) gains a new intent
  (`forecast_next_period`) and a new tool wrapping the forecaster's
  `predict()` method.
- An **admin/eval dashboard** (Phase 6) renders `BackTestResult`
  summaries so methodology reviewers can audit model drift period to
  period.

## Module overview

| Module | Purpose | Status |
|---|---|---|
| `feature_extractor.py` | Build `CorridorFeatureVector` from state. | Skeleton implemented; `derived` is empty. |
| `forecaster.py` | `Forecaster` Protocol + `ForecastInput` / `ForecastOutput`. | Interface only. |
| `eval_harness.py` | `run_backtest()` over historical periods. | Raises `NotImplementedError`. |

## What's deliberately out of scope here

- Training infrastructure (data loading, splits, hyperparameter sweeps).
- Model serving (live endpoints, batched prediction).
- Drift monitoring (a job watching the back-test MAE over time).
- Counterfactual replay (Phase 5.2). The scoring config override path
  needs a deep-copy isolation step; deferred until after the predictive
  scaffold is fleshed out so both can share the same in-memory swap
  pattern.
