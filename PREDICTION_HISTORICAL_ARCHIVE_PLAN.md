# Historical Prediction Archive Plan

Opened: 2026-07-13

Purpose: plan the change that makes historical dashboard charts compare
measured consumption with the prediction that was valid for the same historical
period, not with the current prediction profile projected backward.

Status: implemented through Step 3 on 2026-07-24. Historical vodomery overview
charts now read the archived selected profile valid for each forecast period.

## Agreed Step 1 Direction

Agreed on 2026-07-13:

- The archive will store only the selected model profile for each metering
  point and forecast period, not all candidate model profiles.
- Historical backfill will be separated from normal production archive writes.
- From the production rollout onward, each weekly rebuild should continuously
  write the selected prediction profile for the upcoming week.
- If both a real weekly rebuild archive row and a historical backfill row exist
  for the same metering point, forecast period, and slot, dashboard lookup must
  prefer the real `weekly_rebuild` source.
- For a chart range spanning both old and current periods, lookup is resolved
  per forecast period: older weeks can use `historical_backfill`, newer weeks
  can use `weekly_rebuild`, and weeks without archive coverage should show no
  prediction.
- Step 1 implementation scope is storage/bootstrap and tests only. Connecting
  weekly rebuild writes and dashboard reads will be handled in later approved
  steps.

Implemented on 2026-07-13:

- Added generic storage/bootstrap metadata for
  `monitoring.prediction_profile_snapshots`.
- Added supported archive sources `weekly_rebuild` and `historical_backfill`.
- The unique archive identity intentionally excludes `model_version`, because
  the table stores the selected profile outcome rather than all candidates.
- `expected_mean` is required; percentile/band fields are optional.
- No weekly rebuild writer, backfill writer, API lookup, or dashboard lookup was
  connected in this step.

Step 1b implemented on 2026-07-13:

- Full weekly `vodomery` rebuild now ensures the profile snapshot archive table
  exists together with existing model-validation and selected-model snapshot
  tables.
- Rebuild still does not write archive profile rows yet.
- Single-candidate rebuild remains unchanged because it is not a production
  forecast-period archive point.

Agreed Step 1c direction on 2026-07-13:

- Full weekly rebuild will write selected prediction profile archive rows in
  the same transaction as selected-model snapshots.
- If archive writing fails, the weekly rebuild must fail and roll back.
- Repeated weekly rebuilds for the same forecast period must not overwrite
  existing archive rows; inserts use `ON CONFLICT DO NOTHING`.
- `rebuild_profiles()` should report
  `prediction_profile_snapshot_source = weekly_rebuild` and
  `prediction_profile_snapshot_count`.

## Problem

Water-meter prediction profiles are recalculated during weekly model rebuilds
for the following forecast week. The dashboard currently loads the current
active prediction profile and joins it to any selected measurement period by
weekday and time slot.

That means a historical filter, for example January 2025, can show January 2025
measurements against today's expectation profile. This is misleading for
historical analysis because the expected values may reflect newer consumption
patterns, newer training windows, and newer model selection.

## Target Behavior

When the user filters a historical period, the prediction curve should use the
prediction profile that was valid for each measurement timestamp.

For weekly water-meter forecasts:

- each measurement belongs to one weekly forecast period,
- each metering point can have a different selected candidate model for that
  week,
- the dashboard should compare the measurement with the archived expected
  profile for that metering point, week, model, weekday, and time slot,
- if no trustworthy archived prediction exists for a historical week, the
  dashboard should show no prediction for that part of the chart instead of
  silently using today's profile.

## Scope

Initial scope is `vodomery`.

The design should remain compatible with the shared prediction architecture, so
the archive structure should not prevent later use for `plynomery` or
`elektromery`.

## Guiding Rules

- Discuss and approve each step before implementation.
- Keep existing production scoring behavior stable unless a later approved
  step explicitly changes it.
- Keep current `monitoring.vodomery_anomaly_profiles` as the fast current
  runtime profile table.
- Add a historical archive for charting and retrospective analysis.
- Do not overwrite historical archive rows silently.
- Do not print or export raw measurement rows during planning or verification
  unless explicitly requested.
- Prefer aggregate checks, counts, date ranges, and selected-model summaries.

## Step 1: Create Archive Structure

Goal: add persistent storage for the exact expected profile values that are
valid for a metering point and forecast period.

Proposed table direction:

- generic table: `monitoring.prediction_profile_snapshots`
- or water-specific table first: `monitoring.vodomery_prediction_profile_snapshots`

Preferred direction is the generic table if the schema can stay simple and not
force non-water media into water-specific assumptions.

Minimum identity fields:

- `medium_key`
- `identifier`
- `forecast_period_start`
- `forecast_period_end`
- `forecast_cadence`
- `selection_mode`
- `selection_run_id`
- `model_version`
- `interval_minutes`
- `day_of_week`
- `slot`

Minimum profile value fields:

- `expected_mean`
- `expected_median`
- `expected_p10`
- `expected_p90`
- `expected_std`
- `sample_size`
- `created_at`

Useful metadata fields to discuss:

- `model_key`
- `model_name`
- `source_profile_created_at`
- `profile_build_reference_time`
- `training_window_start`
- `training_window_end`
- `validation_window_start`
- `validation_window_end`
- `metadata_json`

Design questions before implementation:

- Should the archive store profiles for all candidate models, or only the
  selected model per metering point and week?
- Should `selection_run_id` be required for archive rows created by normal
  weekly rebuilds?
- Should backfilled rows use a distinct mode such as `backfill`, or should mode
  remain `active` with explicit metadata?
- What is the uniqueness rule for a backfilled row if we later rerun the
  backfill with improved logic?
- How long should archived profile rows be retained?

Acceptance criteria for Step 1:

- table/bootstrap code exists,
- indexes support lookup by medium, identifier, forecast period, and mode,
- inserts are idempotent or explicitly conflict-aware,
- no dashboard behavior changes yet,
- targeted storage tests pass.

## Step 2: Backfill Archive

Goal: one-time historical reconstruction so old dashboard periods can compare
measurements with the expected profile that would have been valid for that
week.

Agreed Step 2 direction on 2026-07-13:

- Earliest backfill boundary is `2024-01-01`.
- Each metering point can enter backfill only after it has at least one month
  of available measurement history.
- Historical backfill rows use `archive_source = historical_backfill`.
- First backfill logic uses `archive_version = 1`; changed logic in a later
  rerun must use a new archive version instead of silently rewriting version 1.
- Models 4 and 5 will not be calculated for the first backfill. The first
  backfill uses only production-selection candidates 1-3.

Backfill should be designed and reviewed separately before any production run.
The current preferred direction:

1. Determine each water-meter identifier's first available consumption record.
2. Build weekly forecast periods from that first record through the current
   archive start boundary.
3. For each identifier and week, rebuild the candidate evaluation using only
   data that would have been available before that forecast week.
4. Select the best candidate for that identifier and week using the same
   selection policy as production, including coverage and fallback rules.
5. Persist the selected expected profile values for that identifier and week.
6. Store enough metadata to identify that the row was produced by historical
   backfill and which algorithm/version created it.

Important backfill considerations:

- metering points have different start dates because remote readings were
  introduced gradually,
- early weeks may not have enough history for every candidate,
- expected-zero and quality filtering rules must match historical scoring
  semantics as closely as possible,
- weekly windows must be precise and deterministic,
- the operation must be restartable,
- dry-run reporting should estimate row counts and runtime before writes,
- verification should use aggregate counts, coverage summaries, and sampled
  identifiers without printing raw measurements.

Open questions before Step 2:

- What is the earliest allowed backfill date?
- How much training history is required before an identifier can receive a
  historical prediction?
- Should missing early weeks be left blank, or filled by a conservative
  baseline fallback?
- Should the backfill recalculate all candidates 1-5, or only selection-eligible
  candidates?
- Should measured-only candidates 4 and 5 remain diagnostics during backfill,
  or be excluded completely from historical chart expectations?
- How should reruns be handled if the first backfill finds a bug or needs a
  changed policy?

## Backfill Model Statistics

The backfill should also support model-success statistics, but this should be
kept separate from the selected-profile archive.

The selected-profile archive is intentionally compact and stores only the model
that was selected for the metering point and forecast period. That is enough for
historical charting, but it is not enough to later compare all candidate models
against each other, because losing candidate profiles and metrics are not
stored there.

Recommended approach:

- During backfill, store aggregate candidate metrics for models 1-3 per
  metering point and forecast week.
- Do not store full profile rows for losing candidates.
- Store one compact metric row per candidate, identifier, and forecast period
  with values such as validation count, matched count, coverage, MAE, RMSE,
  bias, WAPE, selected flag, and fallback/eligibility reason.
- After backfill, compute realized selected-model performance from archived
  selected profiles joined to actual measurements. This can answer how the
  model selected for the chart actually performed in each historical week.

This gives two useful statistic families:

- candidate-selection statistics: which eligible model would have won per
  identifier/week and with what validation metrics,
- realized selected-model statistics: how the archived expected values compared
  with actual measurements after the forecast week happened.

Open statistics design questions:

- Should candidate metric storage be generic across media, or water-specific
  for the first implementation?
- Should realized selected-model statistics be persisted as a table, or
  calculated from archive rows and measurements on demand for reports?
- Which primary metric should drive summary reporting: WAPE by default, with
  MAE/RMSE/bias as diagnostics?

Agreed candidate metric storage direction on 2026-07-13:

- Use a separate generic table
  `monitoring.prediction_backfill_candidate_metrics`.
- Do not store candidate metrics inside
  `monitoring.prediction_profile_snapshots`.
- `archive_run_id` identifies a concrete execution but is not part of the
  unique key.
- Corrections or changed logic must use a new `archive_version`, not overwrite
  an existing version.
- Store `rank_by_policy` so reports can distinguish winners from second/third
  ranked candidates.
- `best_overall` is not needed for the first backfill because models 4 and 5
  are not calculated.

Proposed unique key:

- `medium_key`
- `identifier`
- `forecast_period_start`
- `forecast_period_end`
- `forecast_cadence`
- `archive_version`
- `model_version`

Proposed metric columns:

- `model_key`
- `model_name`
- `selection_enabled`
- `selected`
- `eligible`
- `rank_by_policy`
- `fallback_reason`
- `validation_total_count`
- `matched_validation_count`
- `coverage`
- `mae`
- `rmse`
- `bias`
- `wape`
- `training_window_start`
- `training_window_end`
- `validation_window_start`
- `validation_window_end`
- `created_at`
- `metadata_json`

Implemented on 2026-07-13:

- Added generic storage/bootstrap metadata for
  `monitoring.prediction_backfill_candidate_metrics`.
- Added conflict-safe insert/persist helpers using the agreed identity without
  `archive_run_id`.
- Added storage tests for identity, required/optional columns, and
  `ON CONFLICT DO NOTHING`.
- No backfill runner or production writes were connected in this step.

## Backfill Runner Design

The backfill runner should be implemented as a controlled offline operation,
not as part of the normal scheduler loop.

Initial module direction:

- `moduly/mereni/vodomery/vodomery_prediction_backfill.py`

The runner should reuse existing vodomery prediction functions where possible:

- candidate definitions for models 1-3,
- rebuild-window construction,
- candidate profile builders,
- rolling weekly backtest by identifier,
- selected-model decision builder,
- selected-profile archive writer,
- candidate metric storage writer.

It should not run live until dry-run outputs are reviewed.

### Backfill Modes

Required modes:

- `plan`: no profile calculations and no writes; only estimates identifiers,
  weeks, minimum-history eligibility, and rough output row counts.
- `dry_run`: performs the historical calculations for the requested scope but
  does not write archive/profile/metric rows.
- `write`: writes selected profile archive rows and candidate metric rows.

Optional later mode:

- `verify`: reads existing backfill rows and reports aggregate coverage and
  gaps without running model calculations.

### Backfill Scope Controls

The runner must support restrictive scope parameters before any full run:

- `start_date`, default `2024-01-01`,
- `end_date`, default first forecast period that is already covered by real
  `weekly_rebuild` archive rows or the current date if no such row exists,
- identifier allow-list,
- max weeks,
- max identifiers,
- archive version, default `1`,
- archive run id, required for `dry_run` and `write` reporting,
- batch size by forecast week.

The first write test should use a tiny explicit scope, for example one or two
identifiers and two to four forecast weeks.

### Week Planning

For each identifier:

1. Find the first valid measurement at or after `2024-01-01`.
2. Require at least one month of history before the first forecast period.
3. Generate weekly forecast periods from the first eligible forecast week until
   the backfill end boundary.
4. Do not plan periods that already have `weekly_rebuild` archive coverage.

The exact week boundary should match the production vodomery weekly forecast
period semantics as closely as possible. This needs one explicit decision before
implementation: use calendar Monday 00:00 weeks for historical backfill, or use
the same time-of-day anchor as production weekly rebuilds.

### Per-Week Calculation

For each planned forecast week:

1. Build windows as if the rebuild reference time were the forecast period
   start.
2. Limit candidates to models 1-3.
3. Build candidate deploy profiles using only data before the forecast period.
4. Run rolling weekly backtest by identifier for selection metrics.
5. Build selected-model decisions using the same production policy and one
   month minimum-history eligibility.
6. Persist candidate metrics for models 1-3 per identifier/week.
7. Persist selected profile archive rows for selected identifier/model pairs.

Write mode must commit per forecast week or per small week batch so an
interrupted run can resume without losing already completed weeks.

### Resume And Conflict Rules

- Inserts use `ON CONFLICT DO NOTHING`.
- Existing rows for the same `archive_version` are not overwritten.
- A corrected run must use a new `archive_version`.
- The runner should report inserted counts and skipped-conflict counts where
  possible.
- The runner should skip a forecast week/identifier pair if both selected
  profile rows and candidate metric rows already exist for the requested
  archive version, unless a later explicit repair mode is designed.

### Dry-Run Output

Dry-run output should include only aggregates:

- archive run id,
- date range,
- archive version,
- identifier count,
- forecast week count,
- planned identifier-week count,
- skipped identifier-week count by reason,
- candidate metric row estimate,
- selected profile row estimate,
- missing-history counts,
- estimated first and last forecast period,
- expected models used: 1, 2, 3.

Do not print raw measurement rows.

### Open Runner Decisions

- Week boundary: calendar Monday 00:00 or production rebuild timestamp anchor.
- Commit scope: one week per transaction or configurable week batches.
- Whether `dry_run` should build temporary deploy profiles or only run metric
  calculations.
- Whether candidate metrics should store only identifiers passing the
  one-month history gate or all identifiers with any validation observations.

Resolved on 2026-07-13:

- Historical backfill forecast weeks use calendar Monday `00:00` boundaries.
- Write mode commits after each forecast week.
- `dry_run` includes real calculations without writes so aggregate output is as
  detailed as possible.
- Candidate metrics are produced only for identifier/week pairs that passed the
  one-month history gate.

Implemented plan mode foundation on 2026-07-13:

- Added `moduly/mereni/vodomery/vodomery_prediction_backfill.py`.
- Added pure planning structures for identifier history, forecast-week plan
  items, and aggregate plan summaries.
- Plan mode uses calendar Monday `00:00` weeks, one-month history gate,
  candidate models 1-3, `archive_version = 1`, and no writes.
- Planner stops scheduling an identifier after the week of its last valid
  measurement.
- Added unit tests for week boundaries, one-month eligibility, existing
  `weekly_rebuild` skips, and scope limits.

Implemented dry-run foundation on 2026-07-13:

- Added non-writing `dry_run_vodomery_prediction_backfill()`.
- Dry-run groups plan items by forecast week, calculates models 1-3 for that
  week, builds per-identifier selected-model decisions, and derives candidate
  metric row counts without calling persist helpers.
- Dry-run rolls back the session after each forecast week so temporary profile
  table changes made by model calculations are not committed.
- Current dry-run result reports aggregate counts per week: planned
  identifiers, calculated identifiers, candidate metric rows, selected
  decisions, selected profile pairs, and skip reasons.
- Added unit coverage with monkeypatched model calculations to verify weekly
  orchestration and rollback behavior.

Implemented safe CLI entrypoint on 2026-07-13:

- Added `scripts/vodomery_prediction_backfill.py`.
- CLI supports `plan` and `dry-run` commands.
- CLI output is aggregate JSON only and does not print identifier lists or raw
  measurement rows.
- `dry-run` requires an explicit `--archive-run-id`.
- Scope controls include `--start-date`, `--end-date`, repeated
  `--identifikace`, `--archive-version`, `--max-identifiers`, and
  `--max-weeks`.
- Added tests for aggregate-only plan/dry-run reports and a monkeypatched CLI
  `plan` command without live database access.

Implemented write-mode foundation on 2026-07-13:

- Added `write_vodomery_prediction_backfill()`.
- Write mode reuses the same weekly calculation path as dry-run.
- For each forecast week, write mode persists candidate metric rows and
  historical selected profile snapshots, then commits that week.
- On any per-week error, write mode rolls back that week and propagates the
  exception.
- Historical selected profile snapshots use
  `archive_source = historical_backfill`, configured `archive_version`, and the
  provided `archive_run_id`.
- CLI now includes a `write` command with aggregate JSON output only.
- Added unit tests for successful commit, rollback on write error, aggregate
  write reporting, and monkeypatched CLI write execution without live database
  access.
- Live write execution has not been run.

Implemented verify mode on 2026-07-13:

- Added read-only `verify_vodomery_prediction_backfill()`.
- Verify mode aggregates existing `prediction_profile_snapshots` rows by
  `archive_source` and `archive_version`.
- Verify mode aggregates existing
  `prediction_backfill_candidate_metrics` rows for the requested
  `archive_version`.
- CLI now includes a `verify` command.
- Verify output is aggregate JSON only and does not print identifier lists or
  raw measurement rows.
- Added unit tests for read-only aggregate parsing, verify report generation,
  and monkeypatched CLI verify execution without live database access.
- Live verify execution has not been run.

Acceptance criteria for Step 2:

- reviewed backfill algorithm document or checklist exists,
- dry-run can report planned periods, identifiers, candidate counts, and
  estimated archive rows,
- write mode is resumable and conflict-safe,
- verification queries prove expected coverage by week and identifier,
- no dashboard behavior changes until Step 3 is approved.

## Step 3: Connect Dashboard To Historical Backend Logic

Goal: dashboard graphs use archived historical predictions when a date filter is
selected.

Backend changes to discuss:

- extend `/api/v1/vodomery/prediction-profiles` with optional `start_date` and
  `end_date`,
- preserve current behavior when no date range is supplied,
- when a date range is supplied, load archived profile snapshots overlapping
  that range,
- return profile rows with validity bounds such as `valid_from` and `valid_to`,
- return metadata such as `model_version`, `selection_run_id`, and whether the
  row came from archive or current runtime profiles.

Dashboard changes to discuss:

- pass the selected filter date range when loading prediction profiles,
- join measurement rows to prediction rows by:
  - measurement timestamp within `[valid_from, valid_to)`,
  - `interval_minutes`,
  - `day_of_week`,
  - `slot`,
- show no prediction for periods without archive coverage,
- optionally display a compact note that historical prediction coverage is
  incomplete.

Acceptance criteria for Step 3:

- January 2025-style filters no longer use the current active profile unless
  that profile was truly valid for that period,
- charts can span multiple weekly forecast periods and use the correct archived
  profile for each week,
- missing archive periods are visible as missing prediction data, not filled by
  today's profile,
- API and dashboard tests cover multi-week historical joins.

Implemented on 2026-07-24:

- `/api/v1/vodomery/prediction-profiles` accepts optional paired
  `start_date` and `end_date` parameters.
- Calls without a date range preserve the current-profile response for
  existing consumers.
- Date-range calls return only selected profile snapshots whose forecast
  periods overlap the requested range, including `valid_from`, `valid_to`,
  model, archive-source, and selection-run metadata.
- When multiple archive versions contain the same profile slot, the highest
  archive version and newest row wins deterministically.
- The vodomery overview passes its selected date range and joins each
  measurement only to a profile whose `[valid_from, valid_to)` contains the
  measurement timestamp.
- Archive gaps remain null prediction values; the current active profile is
  not projected backward to fill them.
- Unit coverage verifies multi-week profile changes, missing-week behavior,
  legacy current-profile compatibility, and authorization regression.
- A production read-only query for January 2025 returned five bounded weekly
  periods for one sampled identifier without printing its identifier.

## Suggested Review Order

1. Agree on the archive table identity and whether it should be generic or
   water-specific.
2. Agree on whether normal weekly rebuilds archive all candidates or only the
   selected per-identifier profile.
3. Implement Step 1 only.
4. Review a detailed backfill design with dry-run outputs and rollback/rerun
   rules.
5. Implement and run Step 2 only after explicit approval.
6. Review API/dashboard behavior for missing archive coverage.
7. Implement Step 3.

## Current Known Risk

Historical selected-model snapshots alone are not enough to reproduce the exact
old prediction curve, because current profile tables are rebuilt per
`model_version`. The archive must preserve the concrete profile values for each
forecast period if the dashboard is expected to show historical expectations
faithfully.
