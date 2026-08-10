# Plynomery Prediction Pipeline Plan

Purpose: executable implementation plan for bringing `plynomery` to the same
per-identifier prediction lifecycle already used by `vodomery`, while
preserving gas-specific weather adjustment, expected-zero behavior, outlier
handling, event compatibility, and operational rollback safety.

Status: completed on 2026-07-28. All 25 checklist items passed their targeted
verification and are recorded in `agents/history/SESSION_NOTES.md`.

Related context:

- `agents/plans/prediction/PREDICTION_PIPELINE_PLAN.md`: shared cross-media
  architecture.
- `agents/decisions/DECISIONS.md`: durable prediction and production behavior
  decisions.
- `agents/history/SESSION_NOTES.md`: executable status, verification, and
  handoff history.

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

## Resolved Design Questions

Resolve these during the relevant checklist item and record durable outcomes
in `agents/decisions/DECISIONS.md`:

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

- [x] 1. Freeze the current plynomery baseline with focused tests.
  - Cover candidate definitions, rebuild windows, global selection,
    profile generation, weather-adjusted evaluation, scoring checkpoints,
    expected-zero behavior, and scheduler integration.
  - Record current production aggregate counts without identifiers or raw
    measurements.

- [x] 2. Confirm and test the gas forecast-period contract.
  - Align selection, rolling folds, deploy windows, snapshot validity, and
    scheduler cadence.
  - Record the resulting durable period rule in
    `agents/decisions/DECISIONS.md`.

- [x] 3. Produce per-identifier rolling metrics for every eligible candidate.
  - Reuse shared metric contracts and storage.
  - Preserve gas measurement quality filters and weather-aware evaluation.
  - Include coverage, fold count, WAPE, MAE, RMSE, and bias.

- [x] 4. Build a deployable profile catalog per candidate and identifier.
  - Normalize baseline and weather-adjusted profiles into the shared snapshot
    shape without losing weather coefficients or residual statistics.
  - Prove that every selectable candidate/identifier pair has a usable profile.

### Phase 2 - Selection and snapshot persistence

- [x] 5. Implement per-identifier candidate selection in dry-run mode.
  - Require valid metrics, coverage, folds, and a deployable profile.
  - Keep the global active model as the explicit fallback.
  - Persist fallback and ineligibility reasons for auditability.

- [x] 6. Persist selected-model and profile snapshots atomically.
  - Use `monitoring.prediction_selected_model_snapshots` and
    `monitoring.prediction_profile_snapshots` with `medium_key='plynomery'`.
  - Store the forecast period, selection run, archive metadata, and selection
    mode.
  - Fail before commit when any selected profile is missing.

- [x] 7. Extend the plynomery rebuild report and performance API.
  - Show per-model winner counts, global fallbacks, fallback reasons, missing
    profile failures, selected-vs-global comparison, and worst identifiers.
  - Keep output aggregate-only and free of raw operational values.

- [x] 8. Run and review a production dry-run rebuild.
  - Compare selected-model distribution and error aggregates with the current
    global model.
  - Do not activate production consumption until the result is reviewed.
  - 2026-07-27: the first controlled run failed closed because 13 of 18 recent
    identifiers were newly installed and had insufficient profile history.
    After recording these as intentionally unavailable, selection run 20
    committed 18 audit snapshots, 13 `insufficient_history` states, and five
    selected profile pairs. Production scoring remains unchanged.

### Phase 3 - Production scoring

- [x] 9. Add per-identifier profile lookup behind an explicit selection mode.
  - Resolve the active snapshot for the measurement timestamp.
  - Use deterministic precedence for overlapping periods.
  - Fall back only according to the recorded selection decision.
  - The lookup is disabled by default. `insufficient_history` and a missing
    period-valid snapshot resolve to explicit unavailability, not a silent
    global profile fallback.

- [x] 10. Support mixed baseline and weather-adjusted scoring in one batch.
  - Load only the selected profile versions required by identifiers in the
    batch.
  - Load HDD inputs only for identifiers using weather-adjusted profiles.
  - Preserve checkpoint progress when a measurement has no applicable profile.
  - Persist scores under the global active model version so event and alert
    identity remains compatible.

- [x] 11. Enable active per-identifier production scoring.
  - Retain the global active model version in persisted scores and downstream
    event identity.
  - Verify anomaly, expected-zero, outlier review, event, and alert regression
    coverage before activation.
  - Active selection run 21 contains 18 decisions, 13 intentional
    `insufficient_history` states, and five complete profile pairs. Runtime
    scheduler consumption takes effect only after the supported rollout
    restart in step 24.

- [x] 12. Perform a controlled production scoring verification.
  - Use aggregate counts and model distributions only.
  - Do not send alerts or run unrelated scheduler jobs solely for validation.
  - The live stream had no backlog, so the isolated scoring call was a safe
    no-op. Read-only evaluation of 900 active-week measurements found 50
    baseline, 200 weather-adjusted, and 650 intentional
    `insufficient_history` outcomes, with zero missing profiles or HDD inputs.

### Phase 4 - API and dashboard predictions

- [x] 13. Add authenticated FastAPI measurement/profile endpoints needed by
  plynomery dashboard views.
  - Enforce section and device authorization.
  - Update the explicit API authorization inventory.
  - Current profiles return explicit availability and never silently fall back
    to a global or zero profile.

- [x] 14. Add period-bounded active profile loading.
  - Historical date ranges use active snapshots only and never project the
    current global profile backward.
  - Current no-date reads use the active snapshot valid at the exact current
    Prague time, with a global fallback only when explicitly allowed.
  - Gas does not allow an implicit global fallback: absent decisions and
    profiles remain explicit unavailable states. Mixed historical ranges
    report per-period availability and an aggregate `partial` status.

- [x] 15. Add shared plynomery prediction construction helpers.
  - Support the dashboard's hourly, daily, and monthly granularities.
  - Resolve overlapping snapshot periods deterministically.
  - Support baseline and weather-adjusted expected values.

- [x] 16. Integrate predictions into `Plynomery / Prehled`.
  - Render the prediction across the full selected period.
  - Show `Nedostupné` when the selected period is explicitly marked
    `insufficient_history`; never render a zero prediction.
  - Stop actual and cumulative-actual series at the final real measurement.
  - Preserve responsive layout and existing Czech UI terminology.

- [x] 17. Integrate predictions into `Plynomery / Detail`.
  - Use the same period-valid profile source as the overview.
  - Show the same `Nedostupné` state for insufficient history.
  - Keep device permissions and current detail behavior intact.

### Phase 5 - Reports and downstream closure

- [x] 18. Inventory every plynomery report and downstream profile consumer.
  - Classify each path as prediction-bearing, actual-only, anomaly/event, or
    model-rebuild reporting.
  - Document intentionally actual-only outputs.
  - The reviewed inventory is maintained in
    `agents/inventories/PLYNOMERY_REPORT_CONSUMER_INVENTORY.md`.
  - There is no prediction-bearing plynomery consumption PDF and no scheduled
    daily/weekly/monthly consumption report. The 2026-08-10 manual
    `Fakturacni odecty` billing PDF is actual/billing-only and explicitly
    outside scheduler/email automation. The only gas report email is
    model-rebuild reporting.
  - The overview Excel export, device inventory, measurement/detail tables,
    and alert/outlier/event outputs are intentionally not prediction-bearing.

- [x] 19. Convert approved prediction-bearing report paths to period-valid
  per-identifier snapshots.
  - Weekly/monthly aggregation must use the profile valid for each report
    timestamp.
  - PDF output must print `Nedostupné` for `insufficient_history` and must not
    substitute zero or a stale profile.
  - Do not add recipients or send production email during tests.
  - Confirmed as a no-op on 2026-07-27: no plynomery consumption PDF/report
    existed then, and the user intended to add these reports in the future.
    On 2026-08-10 the added `Fakturacni odecty` billing PDF was accepted as a
    manual actual/billing-only workflow, so it still requires no prediction
    conversion and no scheduler registration.
  - Future prediction-bearing report additions require an intentional
    inventory and contract update.

- [x] 20. Remove or explicitly retain every remaining global-profile read.
  - Keep only documented compatibility fallbacks and non-active candidate
    evaluation paths.
  - Add regression tests for every retained fallback.
  - Active outlier-review repair now uses the same period-valid
    per-identifier selection builder as production scoring.
  - Non-active outlier repair, candidate scoring, and rebuild internals retain
    direct candidate-profile reads for model comparison.
  - User-facing prediction APIs/dashboard paths have no global-profile
    fallback.

### Phase 6 - Verification and rollout closure

- [x] 21. Run the complete targeted regression matrix.
  - Shared prediction contracts, pipeline, backtest, and storage.
  - Plynomery prediction, scoring, imports, expected-zero, outliers, events,
    alerting, API authorization, dashboard helpers, reports, and scheduler.
  - Completed on 2026-07-27 with `423 passed` and no failures.

- [x] 22. Run the complete project test suite.
  - Record exact results and any unrelated accepted baseline failures.
  - Completed on 2026-07-27 with `989 passed` and no failures or accepted
    baseline exceptions.

- [x] 23. Perform read-only production aggregate checks.
  - Confirm snapshot coverage for all active identifiers.
  - Confirm selected profiles exist and cover the active forecast period.
  - Confirm scoring, dashboard, and approved reports consume the expected
    source without printing identifiers or measurements.
  - Read-only check on 2026-07-27 confirmed 18/18 measured identifiers have
    active decisions, five available decisions have five complete 672-row
    profile pairs, 13 `insufficient_history` decisions have no profiles, and
    there are no missing or mismatched profile pairs.
  - The scoring check found six post-snapshot active-identity score rows that
    do not match the archived period-valid selected profile. All six were
    already processed, but none changes anomaly flag or severity under the
    selected-profile recalculation.
  - The initial audit kept step 23 open until the pre-restart runtime drift
    was remediated through an approved controlled score/event operation and
    the aggregate check returned zero mismatches.
  - Completed on 2026-07-27 after the approved score/event reconciliation and
    an independent post-commit audit. After the next normal
    `quarter_hour_job`, 315 expected and persisted active-identity scores had
    zero mismatches, missing scores, unexpected scores, or scores for
    unavailable decisions.

- [x] 24. Complete the supported restart rollout.
  - Write the mandatory dated restart handoff before restarting.
  - After boot, verify processes, listeners, health endpoints, scheduler,
    database preflight, routing, authentication, and gas-specific behavior.
  - The detailed handoff and reconciliation sequence are prepared in
    `agents/runbooks/PLYNOMERY_POST_RESTART_RUNBOOK.md` and the dated
    `agents/history/SESSION_NOTES.md`
    handoff.
  - Do not mark this step complete until score/event reconciliation is
    explicitly approved, applied, and followed by zero-mismatch step 23
    aggregates plus one normal quarter-hour observation.
  - On 2026-07-27 the final reconciliation apply implementation was completed:
    it binds execution to the SHA-256 of an exact reviewed dry-run aggregate,
    acquires the `quarter_hour_job` process lock, rebuilds scores and dependent
    event state in one transaction, suppresses schema/notification side paths,
    and commits only after a zero-mismatch in-transaction audit.
  - Implementation verification passed with 27 focused tests and the complete
    project suite at `998 passed`. At that gate, production apply remained
    pending explicit approval of a fresh dry-run hash.
  - The SHA-256-bound production apply was explicitly approved and completed
    on 2026-07-27. It reconciled 310 active-period scores for five affected
    identifiers and the dependent event state. The in-transaction and
    independent post-commit audits both returned zero score-integrity
    failures.
  - A normal `quarter_hour_job` completed at `2026-07-27 15:35:12 +02:00`.
    Its subsequent aggregate audit covered 1,134 eligible measurements and
    315 expected/persisted scores with zero source mismatches.
  - The authenticated dashboard/API verification was completed through the
    deployed client after the restart.
  - The authenticated browser smoke test on 2026-07-28 found that historical
    overview ranges had no prediction curve and the prediction line was red.
    The line now uses the vodomery light gray (`#dedcd9`).
  - A controlled weekly historical backfill was implemented and completed for
    the range beginning 2026-04-21 through the week ending 2026-07-27. It
    stored 70 active per-identifier decisions, 47,040 selected profile rows,
    and 140 candidate metric rows across 14 weeks and five identifiers.
  - Aggregate verification reports 14 complete weeks, 70 identifier-week
    decisions/profile pairs, and no missing tables. A real historical service
    calculation returned seven complete daily prediction rows for a bounded
    April range.
  - Browser verification confirmed the historical prediction coverage and
    the correct current forecast endpoint on 2026-08-02. The final overview
    parity change adds the light-gray expected curve to both consumption
    charts, draws actual consumption above prediction, adds the vodomery-style
    legend below the charts, and restores the four summary metrics.
  - The refreshed authenticated browser check passed on 2026-07-28: historical
    and current curves, forecast endpoint, light-gray styling, prediction-below-
    actual layer order, cumulative prediction, four metrics, and legend all
    matched the accepted behavior.

- [x] 25. Close the plan.
  - Record final durable decisions and operational state.
  - Mark this plan complete only when no undocumented global production
    profile path remains.
  - Completed on 2026-07-28 after a final tracked-code and consumer-inventory
    audit. Active scoring, active outlier repair, prediction APIs, and
    dashboard consumers use period-valid per-identifier snapshots.
  - Remaining direct candidate-profile reads are explicitly retained only for
    rebuild/backtest work, non-active candidate comparison, or their
    documented repair paths. No undocumented global production fallback
    remains.
  - The focused closure regression matrix passed with 70 tests. The complete
    project suite last passed with 1,008 tests after the final dashboard
    change, and `git diff --check` passed with line-ending warnings only.

## Verification Gates

Every implementation item must pass:

1. focused unit tests for the changed behavior,
2. adjacent plynomery regression tests,
3. `git diff --check`,
4. a review that no secrets, identifiers, raw measurements, or recipient
   addresses were added to output,
5. a short dated entry in `agents/history/SESSION_NOTES.md`.

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

## Follow-up After Completing The Plynomery Pipeline

- [x] Apply the reviewed insufficient-history behavior to vodomery after all
  plynomery pipeline steps are complete.
  - Persist an explicit unavailable state for newly installed water meters
    that do not have enough valid history for a deployable prediction profile.
  - Do not create zero, copied, synthetic, or stale profiles for those meters.
  - Show `Nedostupné` consistently in vodomery dashboard and PDF prediction
    outputs.
  - Preserve hard failures for profiles that are unexpectedly missing from an
    identifier otherwise marked as prediction available.
  - Completed in source on 2026-07-28 with selection, profile persistence,
    active scoring/checkpoint, API, dashboard, and daily/weekly/monthly branch
    PDF coverage. Production activation remains part of the pending supported
    workstation restart.

- [x] Review vodomery outlier handling after all plynomery pipeline steps are
  complete.
  - Verify that score/event rebuilds after an outlier-review change use the
    period-valid per-identifier selected model for the active score identity.
  - Keep non-active candidate recalculation only where it is intentionally
    required for model comparison.
  - Ensure insufficient history, missing selection/profile, or missing
    required inputs do not silently fall back to a global, current, or stale
    water profile.
  - Add regression coverage distinguishing active selected-model repair from
    retained non-active candidate repair.
  - Completed in source on 2026-07-28. Active repair now uses the shared
    period-valid selected-profile score builder; unavailable active periods
    produce no score, missing available profiles fail, and non-active versions
    retain candidate-profile repair. Production activation remains part of the
    pending supported workstation restart.
