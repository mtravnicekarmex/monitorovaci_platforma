# Plynomery Prediction Pipeline Plan

Purpose: executable implementation plan for bringing `plynomery` to the same
per-identifier prediction lifecycle already used by `vodomery`, while
preserving gas-specific weather adjustment, expected-zero behavior, outlier
handling, event compatibility, and operational rollback safety.

Status: active plan, opened on 2026-07-27. Complete one checklist item at a
time. Mark an item complete only after its targeted verification passes and
the result is recorded in `SESSION_NOTES.md`.

Related context:

- `PREDICTION_PIPELINE_PLAN.md`: shared cross-media architecture.
- `DECISIONS.md`: durable prediction and production behavior decisions.
- `SESSION_NOTES.md`: executable status, verification, and handoff history.

## Current Baseline

Plynomery already have:

- a shared prediction runner and media adapter,
- global baseline model v1 and weather-adjusted model v2 candidates,
- candidate profile rebuilds and global validation metrics,
- one globally selected active model per rebuild,
- weekly scheduler integration and a model rebuild email,
- existing anomaly scoring, events, expected-zero, outlier review, and
  alerting behavior.

The current production gap is that the selected model and profile are global.
The rebuild does not yet persist deployable per-identifier selected-model and
profile snapshots, and scoring, API, dashboard, and reports do not consume
period-valid per-identifier gas predictions.

## Target Production Invariants

- Each gas identifier may select its own deployable model for a forecast
  period.
- Per-identifier ranking uses rolling validation with the same forecast-period
  shape as production prediction.
- A candidate may be selected only when it has sufficient metrics, coverage,
  and a deployable profile for that identifier.
- If no per-identifier candidate is safely selectable, use the deployable
  global active model and record the fallback reason.
- If no deployable profile exists for an identifier, fail the rebuild before
  persisting active snapshots. Do not silently copy a stale or later profile.
- Selected-model and profile snapshots are persisted atomically with the
  selection run.
- Historical snapshots are period-bounded and immutable under the shared
  conflict rules.
- Production scoring reads the active per-identifier selection, but persisted
  scores retain the global active `model_version` so existing event and alert
  flows remain compatible.
- Non-active candidate scoring remains pure per-candidate scoring for
  comparison and must not mix per-identifier production selections.
- Expected-zero, measurement-quality, reset, synthetic-row, timezone, weather,
  outlier, event, and alert semantics remain unchanged unless a later explicit
  decision says otherwise.
- Dashboard and report prediction curves are built independently across the
  full requested period. Actual consumption ends at the last real
  measurement and is not extended with future zeros.
- Browser-facing reads use authenticated FastAPI boundaries where new API
  capability is required.

## Open Design Questions

Resolve these during the relevant checklist item and record durable outcomes
in `DECISIONS.md`:

- Confirm the production gas forecast-period definition. The current rebuild
  uses shared period metadata, but the period must be explicitly verified
  against scheduler cadence, weather forecast availability, and dashboard
  needs before active snapshot rollout.
- Define how weather-adjusted future profiles handle missing forecast HDD
  inputs for part of a requested period.
- Decide whether future gas candidates need a challenger-margin policy similar
  to vodomery models 4 and 5. Models v1 and v2 should initially retain the
  existing eligibility policy unless evidence supports a change.
- Confirm whether any gas consumption PDF or branch report should render
  predictions. Do not invent a new production report recipient or delivery
  without explicit approval.

## Implementation Checklist

### Phase 1 - Contracts, metrics, and deployable profiles

- [ ] 1. Freeze the current plynomery baseline with focused tests.
  - Cover candidate definitions, rebuild windows, global selection,
    profile generation, weather-adjusted evaluation, scoring checkpoints,
    expected-zero behavior, and scheduler integration.
  - Record current production aggregate counts without identifiers or raw
    measurements.

- [ ] 2. Confirm and test the gas forecast-period contract.
  - Align selection, rolling folds, deploy windows, snapshot validity, and
    scheduler cadence.
  - Record the resulting durable period rule in `DECISIONS.md`.

- [ ] 3. Produce per-identifier rolling metrics for every eligible candidate.
  - Reuse shared metric contracts and storage.
  - Preserve gas measurement quality filters and weather-aware evaluation.
  - Include coverage, fold count, WAPE, MAE, RMSE, and bias.

- [ ] 4. Build a deployable profile catalog per candidate and identifier.
  - Normalize baseline and weather-adjusted profiles into the shared snapshot
    shape without losing weather coefficients or residual statistics.
  - Prove that every selectable candidate/identifier pair has a usable profile.

### Phase 2 - Selection and snapshot persistence

- [ ] 5. Implement per-identifier candidate selection in dry-run mode.
  - Require valid metrics, coverage, folds, and a deployable profile.
  - Keep the global active model as the explicit fallback.
  - Persist fallback and ineligibility reasons for auditability.

- [ ] 6. Persist selected-model and profile snapshots atomically.
  - Use `monitoring.prediction_selected_model_snapshots` and
    `monitoring.prediction_profile_snapshots` with `medium_key='plynomery'`.
  - Store the forecast period, selection run, archive metadata, and selection
    mode.
  - Fail before commit when any selected profile is missing.

- [ ] 7. Extend the plynomery rebuild report and performance API.
  - Show per-model winner counts, global fallbacks, fallback reasons, missing
    profile failures, selected-vs-global comparison, and worst identifiers.
  - Keep output aggregate-only and free of raw operational values.

- [ ] 8. Run and review a production dry-run rebuild.
  - Compare selected-model distribution and error aggregates with the current
    global model.
  - Do not activate production consumption until the result is reviewed.

### Phase 3 - Production scoring

- [ ] 9. Add per-identifier profile lookup behind an explicit selection mode.
  - Resolve the active snapshot for the measurement timestamp.
  - Use deterministic precedence for overlapping periods.
  - Fall back only according to the recorded selection decision.

- [ ] 10. Support mixed baseline and weather-adjusted scoring in one batch.
  - Load only the selected profile versions required by identifiers in the
    batch.
  - Load HDD inputs only for identifiers using weather-adjusted profiles.
  - Preserve checkpoint progress when a measurement has no applicable profile.

- [ ] 11. Enable active per-identifier production scoring.
  - Retain the global active model version in persisted scores and downstream
    event identity.
  - Verify anomaly, expected-zero, outlier review, event, and alert regression
    coverage before activation.

- [ ] 12. Perform a controlled production scoring verification.
  - Use aggregate counts and model distributions only.
  - Do not send alerts or run unrelated scheduler jobs solely for validation.

### Phase 4 - API and dashboard predictions

- [ ] 13. Add authenticated FastAPI measurement/profile endpoints needed by
  plynomery dashboard views.
  - Enforce section and device authorization.
  - Update the explicit API authorization inventory.

- [ ] 14. Add period-bounded active profile loading.
  - Historical date ranges use active snapshots only and never project the
    current global profile backward.
  - Current no-date reads use the active snapshot valid at the exact current
    Prague time, with a global fallback only when explicitly allowed.

- [ ] 15. Add shared plynomery prediction construction helpers.
  - Support the dashboard's hourly, daily, and monthly granularities.
  - Resolve overlapping snapshot periods deterministically.
  - Support baseline and weather-adjusted expected values.

- [ ] 16. Integrate predictions into `Plynomery / Prehled`.
  - Render the prediction across the full selected period.
  - Stop actual and cumulative-actual series at the final real measurement.
  - Preserve responsive layout and existing Czech UI terminology.

- [ ] 17. Integrate predictions into `Plynomery / Detail`.
  - Use the same period-valid profile source as the overview.
  - Keep device permissions and current detail behavior intact.

### Phase 5 - Reports and downstream closure

- [ ] 18. Inventory every plynomery report and downstream profile consumer.
  - Classify each path as prediction-bearing, actual-only, anomaly/event, or
    model-rebuild reporting.
  - Document intentionally actual-only outputs.

- [ ] 19. Convert approved prediction-bearing report paths to period-valid
  per-identifier snapshots.
  - Weekly/monthly aggregation must use the profile valid for each report
    timestamp.
  - Do not add recipients or send production email during tests.

- [ ] 20. Remove or explicitly retain every remaining global-profile read.
  - Keep only documented compatibility fallbacks and non-active candidate
    evaluation paths.
  - Add regression tests for every retained fallback.

### Phase 6 - Verification and rollout closure

- [ ] 21. Run the complete targeted regression matrix.
  - Shared prediction contracts, pipeline, backtest, and storage.
  - Plynomery prediction, scoring, imports, expected-zero, outliers, events,
    alerting, API authorization, dashboard helpers, reports, and scheduler.

- [ ] 22. Run the complete project test suite.
  - Record exact results and any unrelated accepted baseline failures.

- [ ] 23. Perform read-only production aggregate checks.
  - Confirm snapshot coverage for all active identifiers.
  - Confirm selected profiles exist and cover the active forecast period.
  - Confirm scoring, dashboard, and approved reports consume the expected
    source without printing identifiers or measurements.

- [ ] 24. Complete the supported restart rollout.
  - Write the mandatory dated restart handoff before restarting.
  - After boot, verify processes, listeners, health endpoints, scheduler,
    database preflight, routing, authentication, and gas-specific behavior.

- [ ] 25. Close the plan.
  - Record final durable decisions and operational state.
  - Mark this plan complete only when no undocumented global production
    profile path remains.

## Verification Gates

Every implementation item must pass:

1. focused unit tests for the changed behavior,
2. adjacent plynomery regression tests,
3. `git diff --check`,
4. a review that no secrets, identifiers, raw measurements, or recipient
   addresses were added to output,
5. a short dated entry in `SESSION_NOTES.md`.

Database-writing rebuilds, scheduler jobs, report delivery, alert delivery,
and workstation restarts require their existing explicit operational
safeguards. A passing unit test does not authorize those actions.

## Session Entry Template

```text
### YYYY-MM-DD - Plynomery pipeline step N

Scope:
- ...

Changed:
- ...

Verified:
- ...

Not verified:
- ...

Decisions/notes:
- ...

Follow-up:
- Step N+1: ...
```
