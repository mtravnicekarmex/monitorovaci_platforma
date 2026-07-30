# Kalorimetry Downstream Consumer Inventory

Date: 2026-07-30

Status: reviewed baseline for pipeline step 24.

## Scope and classification

This inventory covers tracked Python consumers of kalorimetry measurements,
prediction profiles and series, selected/profile snapshots, anomaly
scores/events, reports, exports, dashboards, and scheduler operations.

Classifications:

- `prediction-bearing`: presents expected consumption to a user.
- `actual-only`: intentionally presents measurements, cumulative states,
  consumption derived from measurements, or device metadata only.
- `anomaly/event`: produces or presents scores, events, outlier reviews, or
  alert transitions.
- `model rebuild`: candidate construction, validation, selection, persistence,
  backfill, reconciliation, or aggregate rebuild reporting.
- `device/inventory`: device counts, recency, permissions, or metadata without
  consumption prediction.

## User-facing outputs and reports

| Path | Output | Classification | Current source and disposition |
| --- | --- | --- | --- |
| `moduly/apps/dashboard/pages/11_kalorimetry.py` | `Kalorimetry / Přehled` metrics, interval and cumulative charts | prediction-bearing | Converted in step 22; keep the device-scoped `/api/v1/kalorimetry/prediction-series` source |
| `moduly/apps/dashboard/pages/12_kalorimetry_detail.py` | `Kalorimetry / Detail` 7-day, 31-day, and 24-month overlays | prediction-bearing | Converted in step 23; keep daily/monthly rows from the same API |
| `moduly/apps/dashboard/pages/11_kalorimetry.py` | Excel export, boundary table, reset/change table, and measurement table | actual-only | Measurement rows only; intentionally actual-only |
| `moduly/apps/dashboard/pages/12_kalorimetry_detail.py` | Metadata, photograph, latest state, averages, recent measurements, and reset history | actual-only subviews | Measurement/device metadata only; intentionally actual-only |
| `moduly/apps/dashboard/pages/33_kalorimetry_seznam.py` and `device_list_shared.py` | Kalorimetry device list | device/inventory | Evidence/device metadata only; intentionally no prediction |
| `moduly/apps/dashboard/pages/0_overview.py` and `overview_shared.py` | Main dashboard kalorimetry device/measurement health summary | device/inventory | Counts, recency, validity, and latest measurement metadata; intentionally no consumption prediction |
| `moduly/apps/dashboard/pages/17_outlier_review.py` and `outlier_review_shared.py` | Shared kalorimetry outlier review | anomaly/event | Admin-scoped review API and stored review candidates; not a consumption forecast |
| `moduly/apps/dashboard/pages/38_prediction_performance.py` | Admin candidate/snapshot performance | model rebuild | Aggregate prediction-performance API; keep as audit/reporting |
| `moduly/mereni/kalorimetry/reporting/model_rebuild_report.py` | Aggregate model rebuild report renderer | model rebuild | Candidate/selection aggregates only; no delivery side effect or raw measurements |
| `moduly/mereni/vodomery/reporting/monthly_jordan_consumption_report.py` | Scheduled JORDAN monthly email row for kalorimetr `Gmt2` | actual-only | Difference between two valid cumulative `spotreba_energie` states in `monthly_site_consumption_report.py`; do not add prediction without separate approval |

No other tracked kalorimetry PDF, branch report, billing report, consumption
email, or export was found.

## Prediction profile and snapshot consumers

| Consumer | Classification | Reviewed behavior |
| --- | --- | --- |
| `services/api/services/kalorimetry.py::load_prediction_profiles` | prediction-bearing source | Reads only overlapping `active` selected/profile snapshots with deterministic archive precedence and explicit unavailable reasons |
| `services/api/services/kalorimetry.py::load_prediction_series` | prediction-bearing source | Builds hourly/daily/monthly output from the period-valid profile response |
| `moduly/mereni/kalorimetry/prediction_series.py` | prediction-bearing construction | Aggregates exact period-valid intervals and derives one continuous cumulative series without filling gaps |
| `moduly/mereni/kalorimetry/active_profile.py` | anomaly/event source | Resolves only the exact period-valid selected decision and profile slot; no global/current/stale fallback |
| `moduly/mereni/kalorimetry/kalorimetry_anomaly.py` | anomaly/event | Applies the quality contract and active-profile lookup; unavailable observations receive no active score |
| `moduly/mereni/kalorimetry/database/outlier_review_apply.py` | anomaly/event repair | Rebuilds only active scores through period-valid selection when score tables are activated; otherwise remains a no-op |
| `moduly/mereni/kalorimetry/events.py` | anomaly/event | Consumes stored active scores for heat-specific event state; alert delivery remains disabled |
| `moduly/mereni/kalorimetry/reconciliation.py` | model rebuild/anomaly audit | Read-only comparison of expected scores/events with optional persisted state |
| `prediction_adapter.py`, candidate modules, `rolling_backtest.py`, `selection.py`, `deployable_catalog.py`, and `snapshot_persistence.py` | model rebuild | Candidate construction, evaluation, selection, and atomic shared-snapshot preparation |
| `prediction_backfill.py`, `prediction_backfill_workflow.py`, and `production_backfill.py` | model rebuild | Leakage-safe historical planning/apply/verification; not a user-facing forecast consumer |
| `production_dry_run.py` | model rebuild | Aggregate-only current-period dry run with no persistence or delivery |
| `services/api/services/prediction_performance.py` | model rebuild | Aggregate candidate metrics and selected-snapshot audit |

Direct reads of candidate tables
`kalorimetry_anomaly_profiles` and `kalorimetry_weather_model_profiles` are
confined to candidate adapter/bootstrap code. No user-facing dashboard,
consumption report, or prediction-series path reads those candidate tables
directly.

## Measurement-only and operational consumers

- `kalorimetry_shared.py` reads measurement/device data for the active
  Streamlit pages. Its prediction loader separately crosses authenticated
  FastAPI.
- `services/api/services/kalorimetry.py::load_measurement_series` provides the
  authenticated measurement API.
- `services/api/services/kalorimetry_admin.py` lists devices for admin
  outlier-review operations.
- `kalorimetry_db_vse.py` imports, normalizes, validates, and derives review
  candidates; it is a producer/maintenance path rather than a prediction
  consumer.
- `monthly_site_consumption_report.py` reads the last valid cumulative
  kalorimetry state at two cutoffs for the actual-only JORDAN report.
- `overview_shared.py` reads aggregate device and measurement health only.
- `dashboard_admin.py` reads device identifiers for permission
  administration.

## Scheduler inventory

- `quarter_hour_job` currently runs `kalorimetry_db_import`. It does not yet
  run kalorimetry snapshot rebuild, active scoring, event processing, alert
  delivery, or a kalorimetry model report.
- `monthly_job` sends the actual-only JORDAN site report containing one
  kalorimetry row. It does not read prediction profiles or series.
- Manual scheduler operations currently expose `kalorimetry_db_import`.
- Historical backfill and reconciliation scripts are explicit operator tools,
  not scheduled consumers.
- Step 25 must add only the separately approved import/rebuild/scoring/report
  operations and preserve delivery-disabled alert behavior until approval.

## Step 24 disposition

- Keep the overview and detail as the only current prediction-bearing
  user-facing kalorimetry outputs.
- Keep the overview export, detail measurement/metadata views, global health
  overview, device list, and JORDAN monthly report intentionally actual-only.
- Keep anomaly/event and model-rebuild paths separate from consumption
  prediction presentation.
- Do not add prediction to JORDAN, invent a new report, add recipients, or
  activate score/event/alert delivery as part of this inventory step.
- Any future kalorimetry consumption report must update this inventory, use
  period-valid device-scoped prediction semantics, and display
  `Nedostupné` for uncovered periods rather than substituting zero/current/
  global/stale profiles.
