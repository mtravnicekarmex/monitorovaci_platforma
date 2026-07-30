# Kalorimetry Prediction Pipeline Plan

Purpose: executable implementation plan for bringing `kalorimetry` to the
complete normalized import, per-identifier prediction, historical backfill,
scoring, API, dashboard, and downstream-consumer lifecycle already established
for `vodomery` and `plynomery`, while preserving heat-meter semantics.

Status: active, opened on 2026-07-29. Implement one checklist item at a time
and mark it complete only after targeted verification.

Related context:

- `PREDICTION_PIPELINE_PLAN.md`: shared cross-media architecture.
- `PLYNOMERY_PREDICTION_PIPELINE_PLAN.md`: completed weekly, weather-aware
  reference implementation.
- `DECISIONS.md`: durable production and forecast-period decisions.
- `SESSION_NOTES.md`: implementation history and operational handoffs.

## Current Baseline

Kalorimetry already have:

- an incremental MSSQL-to-PostgreSQL import from `dbo.Mereni_Kalorimetr` into
  `monitoring."Mereni_kalorimetry_vse"`,
- normalized Prague/UTC time semantics and 15-minute source slots,
- cumulative energy and volume readings, energy deltas, reset detection,
  bounded gap interpolation, synthetic-row flags, validity flags, and
  outlier-review persistence,
- Streamlit overview, device list, and detail pages,
- admin-only FastAPI outlier-review endpoints,
- device and section permissions,
- focused import and time-semantics tests.

Kalorimetry do not yet have:

- a prediction media adapter or candidate catalog,
- deployable consumption profiles,
- rolling per-identifier candidate metrics,
- selected-model/profile snapshots,
- historical profile backfill,
- anomaly scoring/events/alerts based on predictions,
- device-scoped measurement/profile/prediction-series API endpoints,
- prediction curves in overview/detail dashboards,
- a reviewed prediction-bearing downstream-consumer inventory.

## Heat-Meter Invariants

- The predicted consumption quantity is the non-negative interval increment of
  cumulative `spotreba_energie`, represented by the normalized `delta`.
- `objem` is a separate cumulative diagnostic quantity and must not silently
  replace energy consumption in training, scoring, or dashboard predictions.
- Invalid, reset, unresolved-gap, confirmed-outlier, and otherwise unusable
  rows must retain their current import semantics and be excluded according to
  an explicit adapter quality contract.
- Synthetic gap rows must remain distinguishable. Whether they are eligible
  for training, scoring, or only continuity display must be decided and tested
  before model activation.
- Production forecast snapshots use the shared half-open Prague calendar week:
  Monday 00:00 inclusive through the following Monday 00:00 exclusive.
- Historical reads must use the snapshot valid for each timestamp. They must
  never project a current/global profile backward.
- Missing history, profile, selection, or required weather input remains
  explicitly unavailable; no global, stale, copied, synthetic, or zero profile
  may hide the gap.
- Actual measurements stop at the latest real measurement. Future actual
  series must not be extended with zeros.
- Browser-facing reads and privileged writes use authenticated FastAPI with
  both section and device authorization.

## Design Questions to Resolve with Evidence

- Confirm the physical unit and scaling of `spotreba_energie` for every active
  device/source before profile labels and thresholds are fixed.
- Quantify actual source cadence, missing intervals, reset frequency, history
  depth, and identifier coverage using aggregate-only production diagnostics.
- Decide whether synthetic gap rows are eligible for model training and
  backtests, and whether they may ever receive anomaly scores.
- Determine whether a baseline calendar profile is sufficient or whether an
  HDD/outdoor-temperature candidate materially improves rolling validation.
- If a weather candidate is adopted, define the weather station/mapping,
  temperature or HDD horizon, missing-weather behavior, and leakage-safe
  historical backtest inputs.
- Confirm whether heat demand needs explicit heating-season, shutdown,
  weekday/holiday, or expected-zero semantics.
- Inventory reports and other consumers before adding predictions to any
  scheduled output. Do not invent recipients or email delivery.

## Implementation Checklist

### Phase 1 - Baseline and contracts

- [x] 1. Freeze the current kalorimetry baseline with focused tests.
  - Cover import checkpoints, time semantics, delta/reset/gap/outlier behavior,
    dashboard measurement preparation, permissions, and scheduler integration.
  - Record aggregate-only production cadence, coverage, and history findings.
  - Completed on 2026-07-29: the existing baseline matrix passed with
    `238 passed`; the scheduler/import/time subset after the scheduler fix
    passed with `66 passed`.
  - PostgreSQL contains 782,092 rows for 14 identifiers, all at a 15-minute
    cadence, from 2024-03-15 through 2026-05-18. It includes 746,482 valid,
    18,668 synthetic, 17,459 reset, 4,173 gap, and 735,165 delta-bearing rows,
    with zero negative persisted deltas.
  - MSSQL contains current source data through 2026-07-29. The stale
    PostgreSQL endpoint was caused by the kalorimetry import not being wired
    into the scheduler.
  - Added the idempotent kalorimetry import to `quarter_hour_job` and its
    locked internal manual-run registry. Runtime activation requires the
    supported workstation restart; no backlog import was run.

- [x] 2. Define and test the kalorimetry observation-quality contract.
  - Specify eligibility of valid, synthetic, reset, gap, zero, negative, and
    reviewed-outlier rows for training, backtests, profiles, and scoring.
  - Preserve the cumulative state independently from interval consumption.
  - Completed on 2026-07-29 in
    `moduly/mereni/kalorimetry/observation_quality.py` with explicit purposes
    and exclusion reasons; `34 passed`.
  - Meter-state display retains finite cumulative states even for invalid,
    reset, or delta-missing rows. Consumption display requires a valid,
    non-reset, finite non-negative delta and may retain gap continuity rows.
    Model input and scoring additionally exclude both synthetic and
    `gap_detected` rows.
  - Zero delta is a valid observation. Production aggregates contain 531,517
    zero-delta rows, so heating-season/shutdown semantics must be modeled
    explicitly rather than deleting zeros.
  - Aggregate-only history contains 735,164 consumption-display-eligible and
    712,323 model/scoring-eligible rows. Existing synthetic rows do not carry
    `gap_detected`, proving both flags must be checked independently.

- [x] 3. Confirm and test the shared Prague calendar-week forecast contract.
  - Reuse `build_calendar_week_forecast_period`.
  - Align selection, profile validity, folds, scheduler cadence, API ranges,
    and dashboard buckets.
  - Completed on 2026-07-29 in
    `moduly/mereni/kalorimetry/kalorimetry_prediction.py`.
  - The kalorimetry wrapper normalizes timezone-aware references to Prague
    wall time and delegates the actual Monday-to-Monday construction to the
    shared builder.
  - Normal weeks, the Sunday/Monday boundary, UTC-to-Prague conversion, both
    DST transitions, and the default Prague clock passed together with shared,
    water, and gas period regressions: `84 passed`.

- [x] 4. Implement the shared-pipeline kalorimetry media adapter.
  - Load normalized observations without database names leaking into the
    shared core.
  - Define stable medium key, identifier, cadence, quality filters, and
    profile persistence hooks.
  - Completed on 2026-07-29 in
    `moduly/mereni/kalorimetry/prediction_adapter.py`.
  - The SQL loader prefilters DEC-078 quality flags, date windows, and optional
    identifiers. The serialization boundary reuses the pure quality
    classifier so non-finite or otherwise inconsistent rows fail closed.
  - Added dedicated ORM contracts for candidate profiles and global selection
    metadata. No production tables or rows were created in this step.
  - Kalorimetry adapter, quality, period, import, and shared prediction
    regressions passed with `93 passed`; Python compilation and
    `git diff --check` passed.

### Phase 2 - Candidates, profiles, and selection

- [x] 5. Implement a deployable calendar baseline candidate.
  - Produce per-identifier 15-minute weekly profiles from leakage-safe
    historical data.
  - Preserve explicit insufficient-history outcomes.
  - Completed on 2026-07-29 in
    `moduly/mereni/kalorimetry/calendar_baseline.py`.
  - Model 1 uses a 12-month training window and exact weekday/15-minute slot
    statistics. Every one of the 672 weekly points requires at least eight
    historical observations; an identifier with any missing slot publishes no
    partial profile and remains `insufficient_history`.
  - Zero observations remain in the profile. Non-finite, negative,
    non-15-minute, and malformed observations cannot satisfy coverage.
    Expected profile statistics are clamped to non-negative energy.
  - Added an idempotent, check-first bootstrap for only the reviewed
    kalorimetry profile and selection-run tables.
  - The targeted matrix passed with `101 passed`; compilation and
    `git diff --check` passed.
  - Aggregate-only dry-run of the current 12-month window found all 14
    identifiers complete at 672 covered slots. No production table or profile
    was created and no candidate was activated.

- [x] 6. Evaluate and, only if supported by evidence, implement a
  weather/heating candidate.
  - Use historical weather available before each fold.
  - Require applicable forecast weather for future profile construction.
  - Missing weather remains unavailable and does not fall back to a training
    mean or zero.
  - Evidence gate and candidate implementation completed on 2026-07-29.
  - Historical meteo spans 2023-01-01 through 2026-07-25 and covers all
    712,323 currently model-eligible kalorimetry observations. The stored
    forecast currently ends before the full active calendar week, so a future
    weather snapshot must fail unavailable when any required weather input is
    missing.
  - A read-only leakage-safe comparison used 31 weekly folds sampled every two
    weeks from 2025-03-24 through 2026-05-18. The HDD model beat the calendar
    baseline in 24 folds and lost in 7; median relative fold WAPE improvement
    was 7.01%.
  - Per-identifier results were not uniformly better: median improvement was
    0.13%, with 138 improvements across 266 identifier/fold comparisons.
    Therefore weather may be candidate model 2 but must never replace baseline
    globally without per-identifier rolling selection.
  - Model 2 fits a non-negative HDD slope per identifier and exact
    weekday/15-minute slot from a trailing 24-hour HDD feature. Low HDD
    variance produces a zero slope rather than an invented relationship.
  - It requires the same complete 672-point/eight-sample profile contract as
    model 1 and persists fit metadata in a dedicated weather profile table.
  - Deploy profile construction requires weather for every UTC hour mapped
    from the complete Prague forecast period. One missing or non-finite input
    returns no deploy profile with `missing_forecast_weather`.
  - Adapter, candidate, bootstrap, quality, period, import, pipeline, and
    storage regressions passed with `114 passed`; compilation and
    `git diff --check` passed. No production table or profile was created.

- [x] 7. Produce rolling per-identifier metrics for every eligible candidate.
  - Persist WAPE, MAE, RMSE, bias, coverage, and fold count.
  - Use the same calendar-week shape as production.
  - Completed on 2026-07-29 in
    `moduly/mereni/kalorimetry/rolling_backtest.py`.
  - Both candidates train only on each fold's preceding 12-month window and
    validate on the shared Prague calendar-week shape.
  - Metrics are aggregated globally and per identifier with validation total,
    matched count, coverage, MAE, RMSE, bias, WAPE, observed fold count, and
    matched fold count.
  - Weather validation loads actual measurements independently from the HDD
    join. Missing HDD therefore lowers coverage instead of silently removing
    the validation row.
  - Added idempotent ORM/bootstrap contracts for validation runs and
    per-identifier metrics plus transaction-scoped persistence.
  - The targeted kalorimetry/shared prediction matrix passed with
    `131 passed`; compilation and `git diff --check` passed. No production
    rolling run, table creation, or metric write occurred.

- [x] 8. Build a deployable candidate profile catalog per identifier.
  - Prove every selectable candidate has a complete profile for the target
    period.
  - Clamp physically impossible negative expected interval consumption.
  - Completed on 2026-07-29 in
    `moduly/mereni/kalorimetry/deployable_catalog.py`.
  - The catalog contains one explicit entry per candidate/identifier pair.
    An available entry has exactly 672 unique 15-minute week slots with the
    expected identifier/model identity, finite non-negative statistics,
    ordered quantiles, positive sample sizes, and complete weekly coverage.
  - Unavailable entries carry no profile and record
    `insufficient_history`, `missing_forecast_weather`,
    `incomplete_profile`, or `invalid_profile`.
  - Missing weather affects model 2 only and cannot be hidden behind model 1
    under the weather model identity.
  - The targeted kalorimetry/shared matrix passed with `137 passed`;
    compilation and `git diff --check` passed. No production catalog,
    profile, table, or selection was written.

- [x] 9. Implement per-identifier selection in dry-run mode.
  - Rank only candidates with sufficient metrics, coverage, folds, and a
    deployable profile.
  - Persist explicit fallback and unavailability reasons.
  - Completed on 2026-07-29 in
    `moduly/mereni/kalorimetry/selection.py`.
  - A candidate is selectable only with finite WAPE, MAE, RMSE, and bias,
    coverage of at least 85 percent, at least eight matched folds, and an
    available deployable-catalog profile.
  - Eligible candidates rank deterministically by WAPE, MAE, RMSE, absolute
    bias, descending matched observations, and stable model version.
  - The dry-run decision retains a complete candidate audit. If the metric
    winner has no deployable profile, the next eligible candidate is selected
    and the original profile-unavailability reason remains the decision
    fallback reason.
  - Identifiers with no eligible candidate remain explicitly unavailable.
    The selector performs no persistence or production activation.
  - Selection, deployable-catalog, and rolling-backtest tests passed with
    `20 passed`; the broader kalorimetry/shared prediction matrix passed with
    `125 passed`. No production write occurred.

- [x] 10. Persist selected-model and profile snapshots atomically.
  - Use the shared prediction snapshot tables with
    `medium_key='kalorimetry'`.
  - Fail before commit for any available selection with a missing profile.
  - Completed on 2026-07-29 in
    `moduly/mereni/kalorimetry/snapshot_persistence.py`.
  - The full persistence plan is validated and materialized before the first
    SQL write. Every available selection must resolve to the exact selected
    model key and a complete validated 672-point profile for the same forecast
    period.
  - Available decisions and their profile rows use the shared
    `prediction_selected_model_snapshots` and
    `prediction_profile_snapshots` contracts with
    `medium_key='kalorimetry'`. Detailed candidate availability and fallback
    reasons remain in snapshot metadata.
  - Explicitly unavailable identifiers are retained in the batch result but
    are not persisted as if a model had been selected.
  - Both idempotent inserts execute inside one nested transaction/savepoint.
    The helper flushes but never commits; the caller owns the surrounding
    rebuild transaction.
  - Focused snapshot, selection, and shared-storage tests passed with
    `40 passed`; the broader kalorimetry/shared prediction matrix passed with
    `133 passed`. No production bootstrap, snapshot, profile, or selection
    write occurred.

- [x] 11. Extend the prediction performance API/dashboard and rebuild report.
  - Show aggregate candidate rankings, winner counts, fallback reasons,
    coverage, and worst identifiers without raw operational rows.
  - Completed on 2026-07-29.
  - Added kalorimetry as a fourth medium in the shared admin-only prediction
    performance service. Its catalog exposes the two reviewed candidates and
    the API reports `not_run` safely until the reviewed tables and first
    persisted selection run exist.
  - After a run, candidate performance comes from the latest validation run
    per model available before the selection deploy period. Shared snapshot
    queries provide winner distribution, fallback distribution, coverage, and
    the bounded worst-identifier list already rendered by the common dashboard
    page.
  - Added the pure aggregate report builder and escaped HTML renderer in
    `moduly/mereni/kalorimetry/reporting/model_rebuild_report.py`. It reports
    candidate rankings, winner and fallback counts, availability totals, and
    at most ten worst identifiers by WAPE. It contains no raw measurement
    rows and does not send email.
  - The focused performance/report/period matrix passed with `14 passed`; the
    broader kalorimetry, shared prediction, API authorization, and dashboard
    navigation matrix passed with `358 passed`. No production query result,
    table, snapshot, report, or email was written or sent.

- [x] 12. Run and review a production dry-run rebuild.
  - Perform aggregate-only comparison with no scoring, alerting, report
    delivery, or active snapshot consumption.
  - Completed read-only on 2026-07-29 through
    `moduly/mereni/kalorimetry/production_dry_run.py`.
  - The orchestrator preloads eligible measurements once, performs both
    eight-fold candidate backtests in memory, builds the current deployable
    catalog and per-identifier decisions, and returns only aggregate report
    fields. It has no bootstrap, persistence, commit, scoring, alerting, or
    report-delivery path.
  - The current Prague period was 2026-07-27 through 2026-08-03. PostgreSQL
    observations ended at 2026-05-18 07:45:13, so both candidates had zero
    current-fold validation rows and all 14 identifiers remained
    `no_identifier_metrics`.
  - Calendar baseline profiles were deployable for all 14 identifiers.
    Weather profiles were unavailable for all 14 because the coherent
    forecast run from 2026-07-26 22:17:28 covered only 145 of the 168 required
    trailing-24-hour forecast features.
  - No winner was selected, no model was activated, and no database or
    external write occurred. The result is not approval for activation:
    import backlog completion and forecast-horizon correction are required
    before a new current-period production dry-run can pass.
  - The focused read-only orchestration matrix passed with `15 passed`; the
    broader kalorimetry/shared/API/dashboard matrix passed with `360 passed`.

### Phase 3 - Historical backfill

- [x] 13. Implement leakage-safe weekly historical snapshot backfill.
  - Each historical week may use only observations and weather available
    before its start.
  - Store `archive_source=historical_backfill` without changing the current
    runtime selection identity.
  - Completed on 2026-07-29 in
    `moduly/mereni/kalorimetry/prediction_backfill.py`.
  - The planner creates stable Monday-to-Monday identifier/week items and can
    skip existing immutable identities. The week calculator hard-filters both
    measurement and historical weather observations at the forecast-period
    start before any candidate sees them.
  - Each week reruns both eight-fold candidates, constructs deployable
    profiles, per-identifier decisions, two candidate audit rows per evaluated
    identifier, and the exact selected 672-point profile snapshot.
  - Historical snapshots use `selection_mode='active'`,
    `archive_source='historical_backfill'`, a positive archive version, and
    `selection_run_id=NULL`; they cannot replace or mutate the current runtime
    selection identity.
  - Weather deployment additionally requires explicit forecast-issue
    provenance strictly before the forecast week. Missing provenance or a
    forecast issued at/after the period start is rejected; absent or incomplete
    pre-week forecast data keeps weather explicitly unavailable.
  - Tests prove that extreme observations added at or after the historical
    week start cannot change candidate metrics, selection decisions, or
    profile rows.
  - The focused backfill/snapshot/selection matrix passed with `23 passed`;
    the broader kalorimetry/shared/API/dashboard matrix passed with
    `365 passed`. No production plan, backfill calculation, table bootstrap,
    or write was executed.

- [x] 14. Add dry-run, apply, resume, conflict, and verification contracts.
  - Require explicit approval before production writes.
  - Verify decisions, profile completeness, immutable period identity, and
    aggregate coverage.
  - Completed on 2026-07-29 in
    `moduly/mereni/kalorimetry/prediction_backfill_workflow.py`.
  - Dry-run and verify are read-only. Apply requires the explicit
    `confirm_apply=True` gate and refuses to bootstrap missing shared tables.
  - Existing identifier/week/archive identities classify as `absent`,
    `complete`, or `conflict`. Resume skips only an exact complete identity.
    Partial rows, a current selection-run reference, the wrong archive source,
    changed model choices, changed metrics, or changed profile content are
    conflicts.
  - Exact content comparison uses deterministic SHA-256 fingerprints for
    selected decisions, both candidate metric rows, and every selected profile
    point in addition to count and model-identity checks.
  - An absent week writes decisions, candidate metrics, and profiles in one
    savepoint. It must insert exactly the expected counts before flush and
    caller-owned weekly commit; any mismatch or exception rolls back the week.
  - The focused backfill/workflow/shared-storage matrix passed with
    `35 passed`; the broader kalorimetry/shared/API/dashboard matrix passed
    with `374 passed`. No production dry-run, apply, resume, table bootstrap,
    or verification query was executed.

- [x] 15. Run the reviewed production backfill.
  - Stop on any profile, period, history, weather, or conflict mismatch.
  - Record only aggregate completion results.
  - Controlled apply completed on 2026-07-29 for 42 Prague calendar weeks
    from 2025-07-28 through 2026-05-18 and 588 identifier-weeks.
  - Final shared historical state contains 430 decisions, 1,176 candidate
    metrics, and 288,960 profile points. Every selected profile has exactly
    672 points; verification found 42 complete weeks and zero conflicts.
  - All 430 selected snapshots use baseline model 1. No historical week had a
    complete coherent pre-week weather forecast, so weather model 2 remained
    unavailable rather than receiving an implicit fallback.
  - Historical snapshots cover 13 of 14 identifiers. The remaining identifier
    retains candidate audit metrics but had no eligible selection.
  - Every historical decision and profile has `selection_run_id=NULL`.
    Current runtime selection/profile/validation tables were not created or
    populated, and scoring, events, alerts, and report delivery were not run.

### Phase 4 - Scoring, events, and repair

- [x] 16. Implement period-valid per-identifier active profile lookup.
  - Resolve overlaps deterministically.
  - Unavailable selections produce no active score.
  - `active_profile.py` batches decision/profile reads for the requested
    identifiers and timestamp range. It selects the latest overlapping period
    by period start, creation time, and row id, then the highest archive
    version of the exact selected-model quarter-hour slot.
  - The validity interval is half-open. Missing decisions,
    `insufficient_history`, and a missing exact selected profile remain
    explicitly unavailable; no global, current, stale, zero, or other-model
    fallback is used.
  - A read-only production smoke test resolved one historical profile point
    without exposing its identifier or value. The focused test file passed
    with `9 passed`; the broader kalorimetry/shared/API/dashboard matrix passed
    with `392 passed`.

- [x] 17. Implement kalorimetry anomaly scoring and checkpoints.
  - Preserve the chosen score identity contract across selected candidates.
  - Do not score invalid or explicitly unavailable observations.
  - The active-selection scoring stream keeps stable output
    `model_version=1`, while each score records the actual selected candidate
    version plus decision/profile snapshot ids for audit.
  - Scoring reuses the step 2 eligibility contract and the step 16 exact
    period-valid lookup. Invalid, reset, negative, synthetic, gap-affected,
    missing-snapshot, and insufficient-history observations produce no score
    while the checkpoint advances.
  - An available decision missing its exact selected profile aborts before
    score or checkpoint commit. Score insertion and checkpoint advancement are
    one transaction and inserts are idempotent by measurement/scoring identity.
  - A sanitized production read-only smoke test built one finite historical
    score without writes. The focused quality/lookup/scoring matrix passed
    with `39 passed`; the broader kalorimetry/shared/anomaly/API/dashboard
    matrix passed with `413 passed`.

- [x] 18. Integrate anomaly events, alerting, and outlier-review repair.
  - Active repair uses period-valid selected profiles.
  - Non-active candidate repair remains pure candidate comparison.
  - Add alert transitions only after dry-run review and explicit approval.
  - Heat-specific event detection supports `SPIKE` and
    `SUSTAINED_HIGH_USAGE`; gas/water night-use and expected-zero semantics
    are not copied without a kalorimetry domain contract.
  - The detector persists per-event state and an event-engine score checkpoint
    transactionally. Its deterministic `CREATED`/`RESOLVED` transitions feed a
    delivery-disabled alert plan only.
  - Outlier-review measurement rebuild repairs the stable active scoring stream
    through the exact period-valid selected snapshots when scoring has been
    activated. Before the score table exists it remains a no-op. It does not
    rewrite non-active candidate profiles or metrics.
  - Focused event/scoring/repair tests passed with `13 passed`; the broader
    kalorimetry/shared/anomaly/API/dashboard matrix passed with `420 passed`.
    No production table, score, event, alert, email, or scheduler write ran.

- [x] 19. Reconcile historical active scores/events in dry-run mode.
  - Report missing, unexpected, mismatched, flag-changing, and
    severity-changing aggregate counts before any apply.
  - The PostgreSQL transaction is explicitly read-only and rolls back. It
    evaluates the controlled historical range in bounded batches and never
    creates missing score/event tables.
  - Reviewed aggregate result: 401,363 measurements, 395,149 scoring-eligible,
    6,214 ineligible, 285,766 expected scores, and 109,383 eligible rows with
    no period-valid available selection. There are 115,597 intentionally
    unscored measurements in total.
  - Score/event tables do not exist. Therefore persisted scores/events are
    both zero; 285,766 scores and 3,456 created event episodes are missing.
    Unexpected, mismatched, anomaly-flag-changing, severity-changing, and
    event-mismatch counts are all zero because there is no overlapping
    persisted state.
  - The expected event stream contains 3,456 created and 3,456 resolved
    episodes. This is an activation impact estimate, not authorization to
    create or apply scores/events/alerts.
  - Focused reconciliation/lookup tests passed with `13 passed`; the broader
    kalorimetry/shared/anomaly/API/dashboard matrix passed with `424 passed`.

### Phase 5 - API and dashboard

- [x] 20. Add authenticated device-scoped measurement/profile endpoints.
  - Enforce kalorimetry section and device access.
  - Return explicit availability for current and historical profile ranges.
  - Added bearer-authenticated `/api/v1/kalorimetry/measurement-series` and
    `/api/v1/kalorimetry/prediction-profiles`. Both route dependencies and
    service functions enforce kalorimetry section access; services additionally
    enforce the requested device before opening PostgreSQL.
  - Measurement date ranges use the shared Prague-local-to-UTC half-open
    conversion and return canonical source/time metadata.
  - Current profile reads use only the active snapshot covering current Prague
    time. Historical reads return only overlapping active periods, per-period
    availability, and highest-archive exact slots. Missing selection,
    insufficient history, and missing profile remain explicit without global
    fallback.
  - Sanitized production smoke results: one historical week returned one
    available period and 672 profile points; the current lookup returned
    `no_selection_snapshot`; one historical day returned 96 measurement rows.
  - Focused service/authorization tests passed with `212 passed`; the broader
    kalorimetry/shared/anomaly/API/dashboard matrix passed with `441 passed`.

- [x] 21. Add the shared kalorimetry prediction-series service and endpoint.
  - Support hourly, daily, and monthly output from period-valid snapshots.
  - Derive cumulative expected consumption across the complete requested
    range without resetting at weekly boundaries.
  - Completed on 2026-07-30 in
    `moduly/mereni/kalorimetry/prediction_series.py` and the authenticated
    `/api/v1/kalorimetry/prediction-series` endpoint.
  - Series use only exact period-valid profile rows, clamp negative expected
    interval consumption to zero, preserve model/profile audit metadata, and
    never fill uncovered periods from a current, global, stale, or zero
    profile.
  - Hourly, daily, and monthly rows report interval completeness. Expected
    cumulative consumption is derived once from the chronologically ordered
    requested range and does not reset at weekly snapshot boundaries.
  - The focused series/service/authorization matrix passed with `222 passed`;
    the broader kalorimetry/shared/API/navigation matrix passed with
    `423 passed`. No production write or runtime restart occurred.

- [x] 22. Integrate predictions into `Kalorimetry / Přehled`.
  - Match the established actual/expected/cumulative chart and summary metric
    contract while retaining heat-specific labels and units.
  - Display `Nedostupné` for unavailable ranges.
  - Completed on 2026-07-30 through the authenticated prediction-series API;
    the Streamlit page performs no direct prediction-profile database read.
  - The overview shows actual, expected, absolute deviation, and percentage
    deviation. Unavailable values remain `Nedostupné`, and partial ranges
    retain a visible warning.
  - Expected consumption is light gray and layered below actual consumption.
    The cumulative chart uses the same full-range expected cumulative series,
    and the shared legend is rendered below the charts.
  - The focused dashboard/API matrix passed with `235 passed`; the broader
    kalorimetry/dashboard/shared/API matrix passed with `585 passed`.

- [x] 23. Integrate predictions into `Kalorimetry / Detail`.
  - Reuse the same device-scoped API and prediction-series contract.
  - Preserve existing device metadata, reset history, and responsive behavior.
  - Completed on 2026-07-30. The page requests daily prediction rows for the
    last 31 days and monthly rows for the 24-month history through the shared
    dashboard loader.
  - Seven-day and 31-day charts align daily predictions to the displayed
    calendar days. The 24-month chart aligns monthly predictions to the
    existing month categories. Actual bars remain above the light-gray
    prediction line.
  - Explicit `insufficient_history`, unavailable, and partial states remain
    visible. Device metadata, photograph, measurement history, reset/change
    history, and the existing responsive column layout are unchanged.
  - The focused detail/dashboard/API matrix passed with `259 passed`; the
    broader kalorimetry/dashboard/shared/API matrix passed with `589 passed`.

### Phase 6 - Consumers, scheduling, and closure

- [x] 24. Inventory and classify every kalorimetry downstream consumer.
  - Mark each path prediction-bearing, actual-only, anomaly/event, model
    rebuild, or device/inventory output.
  - Convert only explicitly approved prediction-bearing consumers.
  - Completed on 2026-07-30 in
    `KALORIMETRY_CONSUMER_INVENTORY.md`.
  - The overview and detail pages are the only current user-facing
    prediction-bearing kalorimetry outputs. Their shared authenticated API
    paths remain the approved source.
  - The overview export, measurement/metadata/reset views, global health
    overview, device list, and scheduled JORDAN monthly report remain
    intentionally actual-only. JORDAN derives consumption from two valid
    cumulative energy states and receives no prediction without separate
    approval.
  - Candidate-profile reads are confined to rebuild/adapter code. Scoring,
    events, repair, reconciliation, and performance reporting retain their
    anomaly/audit classifications.
  - Focused inventory/report/dashboard/API tests passed with `229 passed`;
    the broader kalorimetry/dashboard/report/scheduler matrix passed with
    `654 passed`. No consumer was converted in this inventory step.

- [ ] 25. Add scheduler integration for import, weekly rebuild, scoring, and
  any approved reports.
  - Keep cron definitions in `core/scheduler/job_schedule.py`.
  - Preserve manual-run compatibility, locks, metrics, preflight behavior,
    and recipient safety.
  - Monday continuation is governed by
    `KALORIMETRY_ACTIVATION_RUNBOOK.md`. Before scheduler integration, verify
    the Sunday 2026-08-02 pre-week forecast, repeat the aggregate current
    dry-run, obtain explicit current-snapshot approval, verify the atomic
    snapshot write, and obtain separate scoring/event activation approval.
  - Alert delivery and new report/email delivery remain out of scope without
    separate approval.

- [ ] 26. Run the complete targeted regression matrix.
  - Cover import, time semantics, prediction core, adapter, candidates,
    backfill, storage, scoring, events, outliers, API authorization,
    dashboards, consumers, and scheduler.

- [ ] 27. Run the complete project suite and read-only production audits.
  - Record exact results and reviewed aggregate invariants.

- [ ] 28. Prepare the mandatory rollout/restart handoff and verify production.
  - Do not stop or recreate individual runtime processes.
  - After restart, verify runtime, scheduler, routing, active snapshots,
    dashboards, and aggregate score/event consistency.

## Required Weather Forecast Follow-up

- Before weather-aware kalorimetry prediction can be activated, review the
  weather forecast synchronization and retention contract.
- The synchronization must download a sufficiently long and current forecast
  to cover every timestamp required by all forecast prediction models,
  including the complete half-open Monday-to-Monday kalorimetry period.
- Verify the effective horizon after scheduler timing, provider availability,
  timezone conversion, and delayed or failed sync runs are taken into account.
- A partial weather horizon must keep the affected prediction explicitly
  unavailable. Do not fill missing future weather with zero, a training mean,
  stale forecast data, or another implicit fallback.
- Apply the resulting forecast-horizon contract consistently to every
  weather-dependent medium, not only kalorimetry.

## Explicit Non-goals

- No blind copy of water or gas thresholds, units, history requirements, or
  weather coefficients.
- No direct Streamlit database writes for new capabilities.
- No silent global/current/stale/zero profile fallback.
- No raw production rows, identifiers, credentials, tokens, or recipient data
  in reports or diagnostics.
- No production rebuild, backfill, reconciliation, alert, report, or email
  without the required dry-run review and approval.
