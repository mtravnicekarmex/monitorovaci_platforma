# Prediction Pipeline Plan

Purpose: implementation plan for a universal meter prediction pipeline that
can add candidate models, select the best model per metering point for the next
forecast period, and reuse the same architecture across water, gas, and
electricity.

Status: active plan, opened on 2026-07-09. The executable checklist lives in
`SESSION_NOTES.md`; this file describes the target architecture and rollout
rules.

## Goals

- Support new candidate models and parameter variants as plugins.
- Select the best model per metering point for the next forecast period.
- Make forecast-period length configurable by medium.
- Preserve media-specific semantics for measurements, calendars, imports,
  expected-zero behavior, outlier filtering, and reporting.
- Keep global model selection as a fallback and operational comparison signal.
- Start with `vodomery`, then adapt the same pipeline to `plynomery` and
  `elektromery`.

## Forecast Periods

- `vodomery`: weekly selection and weekly forecast windows.
- `elektromery`: monthly selection, calculated around the middle of the
  calendar month for the entire following calendar month.
- `plynomery`: to be defined during gas integration, preserving weather-aware
  and expected-zero semantics.

The shared core must not assume that every medium uses weekly windows. Rolling
backtests, profile generation, report labels, and selection storage must take a
forecast-period definition from the media adapter or pipeline configuration.

## Architecture

### Shared Core

The shared package under `moduly/mereni/prediction/` should own:

- contracts for observations, profiles, candidates, metrics, forecast periods,
  and selection decisions,
- rolling backtest orchestration,
- metric aggregation and candidate ranking,
- per-identifier selection policy,
- fallback policy,
- reusable report payload structures.

The shared core should not know water/gas/electric database table names.

### Media Adapters

Each medium adapter should own:

- measurement loading and quality filters,
- identifier naming,
- time semantics and source cadence,
- profile persistence,
- active global model lookup,
- per-identifier selection persistence,
- medium-specific eligibility rules,
- scheduler/report integration points.

Initial adapters:

- `vodomery`: pilot implementation.
- `plynomery`: preserve gas baseline, weather-aware, expected-zero, and
  outlier behavior.
- `elektromery`: monthly forecast periods, source cadence, tariff/calendar
  semantics, and future OTE/reporting needs.

### Candidate Plugins

Each candidate model or parameter variant should be registered with stable
metadata:

- `model_key`,
- `model_version`,
- human-readable name,
- parameter signature,
- training-window definition,
- forecast-period compatibility,
- selection eligibility.

A new parameterization of an existing algorithm should be treated as a separate
candidate if it can produce materially different forecasts.

## Selection Policy

The pipeline should rank candidates per identifier using rolling backtest
metrics for the same forecast-period shape that will be predicted next.

Default ranking:

1. Exclude candidates that are not selection-eligible.
2. Exclude candidates below minimum coverage or fold-count thresholds.
3. Rank by rolling WAPE.
4. Use MAE/RMSE/bias as secondary diagnostics, not the first selection key.
5. Fall back to the global active model when no candidate is safe for an
   identifier.

Measured-only candidates remain visible in reports but are not used for
production selection until explicitly made eligible.

## Storage

Selection storage should keep two related concepts:

- candidate backtest metrics by selection run, model, and identifier,
- the selected model snapshot for a medium, identifier, and forecast period.

The selected snapshot should record:

- selection run id,
- medium,
- identifier,
- forecast period start/end,
- selected model key/version/name,
- global fallback model key/version/name,
- selected metric values,
- eligibility/fallback reason,
- created timestamp.

Scoring should read a stable snapshot for the forecast period. A later rebuild
must not silently rewrite historical selections for an already evaluated
period.

## Reporting

Weekly/monthly rebuild reports should show:

- global candidate ranking,
- per-identifier winner counts,
- fallback counts and reasons,
- measured-only winners that would have won if eligible,
- worst identifiers by best eligible rolling WAPE,
- comparison between global active model and per-identifier selected model.

The report must not include raw measurement rows, secrets, tokens, or
credential data.

## Rollout Plan

- Step 1: define shared forecast-period and per-identifier selection contracts.
- Step 2: add generic selection storage/bootstrap for selected model snapshots.
- Step 3: write vodomery selection snapshots in dry-run mode during rebuild.
- Step 4: extend vodomery report with selected-vs-global and fallback details.
- Step 5: add an explicit feature flag for vodomery scoring/profile lookup to
  use per-identifier selection; default disabled.
- Step 6: enable vodomery per-identifier selection after dry-run verification,
  with global fallback retained.
- Step 7: generalize rolling backtests and rebuild runner for weekly/monthly
  forecast periods.
- Step 8: extract the reusable media pipeline runner so adding models or
  parameter variants only requires plugin registration and adapter metadata.
- Step 9: integrate `plynomery`.
- Step 10: integrate `elektromery` with monthly next-month prediction.

Each step should update tests and only be marked complete in `SESSION_NOTES.md`
after targeted verification.
