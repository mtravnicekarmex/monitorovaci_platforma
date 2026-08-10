# Plynomery Report and Prediction Consumer Inventory

Date: 2026-07-27

Status: reviewed baseline for pipeline steps 18-20; step 19 confirmed.

## Scope and classification

This inventory covers plynomery reports, exports, dashboard outputs, email
outputs, scheduled consumers, and every direct read of a plynomery prediction
profile or shared selected/profile snapshot found in the tracked Python code.

Classifications:

- `prediction-bearing`: presents expected consumption to a user.
- `actual-only`: intentionally presents measurements or device metadata only.
- `anomaly/event`: produces or presents scores, events, outlier reviews, or
  alerts.
- `model-rebuild reporting`: candidate evaluation, model selection, snapshot
  audit, or rebuild reporting rather than a consumption forecast.

## User-facing reports and outputs

| Path | Output | Classification | Profile source | Step 18 disposition |
| --- | --- | --- | --- | --- |
| `moduly/apps/dashboard/pages/9_plynomery.py` | `Plynomery / Prehled` charts and prediction metric | prediction-bearing | Device-scoped `/api/v1/plynomery/prediction-series`, active period-valid snapshots | Converted in steps 15-16; keep |
| `moduly/apps/dashboard/pages/10_plynomery_detail.py` | `Plynomery / Detail` 7-day, 31-day, and 24-month prediction overlays | prediction-bearing | Same device-scoped prediction-series API | Converted in step 17; keep |
| `moduly/apps/dashboard/pages/9_plynomery.py` | Downloaded consumption Excel | actual-only | Measurements loaded for the selected device/range; export columns contain no prediction | Intentionally actual-only |
| `moduly/apps/dashboard/pages/9_plynomery.py` | Boundary, reset/change, measurement, and actual-consumption tables | actual-only | Measurement rows | Intentionally actual-only |
| `moduly/apps/dashboard/pages/10_plynomery_detail.py` | Device metadata, latest reading, averages, recent measurements, resets | actual-only subviews | Measurement/device metadata rows | Intentionally actual-only; prediction remains a separate layer |
| `moduly/apps/dashboard/pages/31_plynomery_seznam.py` and `device_list_shared.py` | Device inventory/list | actual-only | Device evidence/metadata | Intentionally actual-only |
| `moduly/apps/dashboard/pages/34_plynomery_fakturacni_odecty.py` and `moduly/mereni/plynomery/reporting/monthly_billing_report.py` | `Plynomery / Fakturacni odecty` manual monthly billing PDF | actual-only | Manual billing readings plus submeter snapshots from the previous/current billing-reading interval; no prediction profile | Completed after step 19; keep manual, actual/billing-only, and outside scheduler automation |
| `moduly/apps/dashboard/pages/21_plynomery_anomalie_eventy.py` | Open/resolved event dashboard | anomaly/event | Stored active-model events through FastAPI | Not a consumption prediction |
| `moduly/apps/dashboard/pages/22_plynomery_outlier_review.py` | Outlier review dashboard | anomaly/event | Stored outlier-review candidates | Not a consumption prediction |
| `moduly/apps/dashboard/pages/20_plynomery_alerting.py` | Expected-zero and alert-rule administration | anomaly/event | Rules/state only | Not a consumption prediction |
| `moduly/mereni/plynomery/alerting/service.py` | Event alert emails | anomaly/event | Stored active-model events | Not a consumption prediction |
| `moduly/mereni/plynomery/alerting/outlier_notifications.py` | New/reopened outlier emails | anomaly/event | Stored outlier-review candidates | Not a consumption prediction |
| `moduly/mereni/plynomery/reporting/model_rebuild_report.py` | Weekly model rebuild email | model-rebuild reporting | Rebuild result aggregates and per-identifier selection audit supplied by the rebuild | Keep as model reporting; it must not be converted into a consumption forecast |
| `moduly/apps/dashboard/pages/38_prediction_performance.py` and prediction performance API | Admin candidate/snapshot performance | model-rebuild reporting | Candidate tables and selected/profile snapshot audit tables | Keep as model reporting |

## Direct profile and snapshot consumers

| Consumer | Classification | Current behavior | Step 19/20 action |
| --- | --- | --- | --- |
| `services/api/services/plynomery.py::load_prediction_profiles` | prediction-bearing source | Reads only period-overlapping `active` selected-model and profile snapshots; no implicit global fallback | Keep |
| `services/api/services/plynomery.py::load_prediction_series` | prediction-bearing source | Uses the shared series builder plus server-side historical/forecast HDD | Keep |
| `moduly/mereni/plynomery/prediction_series.py` | prediction-bearing construction | Resolves period overlap deterministically; missing profile/HDD stays unavailable | Keep |
| `moduly/mereni/plynomery/plynomery_anomaly.py` active mixed scoring path | anomaly/event | Resolves period-valid active per-identifier decisions, then loads only the selected candidate profile versions; scores retain global active identity | Keep and explicitly document in step 20 |
| `moduly/mereni/plynomery/plynomery_anomaly.py` non-active candidate paths | anomaly/event/model evaluation | Pure per-candidate reads from baseline/weather candidate profile tables | Intentional candidate comparison; retain in step 20 |
| `moduly/mereni/plynomery/database/outlier_review_apply.py` | anomaly/event repair | Rebuilds the active score identity through period-valid per-identifier selection; non-active models read their own baseline/weather candidate profile tables | Corrected in step 20; active and retained candidate paths have explicit regression coverage |
| `moduly/mereni/plynomery/plynomery_prediction.py` | model rebuild | Builds candidate profiles/backtests, reads candidate profile catalogs to create selected snapshots, and persists decisions/profile snapshots | Rebuild-internal; retain |
| `moduly/mereni/plynomery/prediction_adapter.py` | model rebuild | Persists and counts baseline candidate profiles | Rebuild-internal; retain |
| `services/api/services/prediction_performance.py` | model-rebuild reporting | Reads candidate runs and selected/profile snapshot coverage | Audit/reporting read; retain |

## Scheduler inventory

- `quarter_hour_job` imports measurements, scores all gas candidates, derives
  events, and sends active-model alerts. It does not create a consumption
  report.
- `weekly_job` rebuilds gas profiles and sends only the plynomery model rebuild
  email.
- Manual scheduler operations expose gas import, model lookup, scoring, event
  detection, alerting, rebuild, and rebuild-report operations.
- There is no scheduled daily, weekly, or monthly plynomery consumption PDF,
  branch report, billing report, or consumption email. The completed
  `Plynomery / Fakturacni odecty` PDF exists only as manual dashboard
  creation/download and is not scheduler-owned.

## Approved step 19 report scope

No existing scheduled plynomery PDF or periodic consumption report is
prediction-bearing. The completed manual `Plynomery / Fakturacni odecty`
billing PDF is actual/billing-only and outside scheduler automation. Therefore
step 19 has no legacy gas report path to convert. Its required work is a
regression-backed no-op confirmation:

- keep the model rebuild email classified as model-rebuild reporting;
- keep the overview Excel export actual-only;
- keep the manual billing PDF classified as actual/billing-only and outside
  scheduler/report email delivery;
- do not add a recipient, scheduler job, PDF, or new report merely to satisfy
  the pipeline checklist;
- if a gas consumption report is added later, it must use the shared
  period-valid prediction-series contract and display `Nedostupné` for
  unavailable periods.

Step 19 result on 2026-07-27:

- At that time, the user confirmed that plynomery did not have PDF reports yet
  and that these would be added in the future.
- No production reporting code was converted because there is no qualifying
  path.
- The 2026-07-27 regression coverage asserted that the then-current plynomery
  reporting package exposed only `send_plynomery_model_rebuild_report` and
  contained only the model rebuild report module.
- Adding a future gas report intentionally requires updating this inventory,
  its classification, scheduler/report tests, and the period-valid prediction
  contract.

Update on 2026-08-10:

- `Plynomery / Fakturacni odecty` now exists as a manual monthly billing PDF.
  It uses append-only manual billing readings and interval-bound submeter
  snapshots, remains actual/billing-only, and is not scheduler-owned.
- The user accepted the final PDF and confirmed no scheduler integration is
  needed. This does not create a step 19 prediction conversion target.

## Step 20 review queue

1. Prove every remaining direct candidate-profile read is either
   rebuild-internal, non-active candidate comparison, or anomaly/event repair.
2. Add explicit regression coverage for the retained reads.
3. Review `outlier_review_apply.py` so active-model history repaired after an
   outlier decision cannot silently diverge from period-valid per-identifier
   selection.
4. Confirm no user-facing consumption output reads
   `plynomery_anomaly_profiles` or `plynomery_weather_profiles` directly.

## Step 20 result

Completed on 2026-07-27:

- The active outlier-review repair path now calls the same shared selected
  score-row builder as normal production scoring.
- The builder resolves the active snapshot independently for each repaired
  measurement timestamp, supports mixed baseline/weather selections, and
  preserves the global active model version in stored score identity.
- `insufficient_history`, no period-valid snapshot, missing selected profile,
  and missing HDD create no repaired score and do not trigger a global
  fallback.
- Non-active candidate repair intentionally continues reading the candidate
  baseline/weather profile tables so model performance remains comparable.
- Pure candidate scoring and rebuild/backtest internals retain the same direct
  candidate-profile reads for the same reason.
- The explicitly disabled per-identifier scoring path remains a compatibility
  mode; scheduler active scoring and active outlier repair do not use it.
- User-facing profile/series APIs and both prediction dashboard pages read
  only active selected/profile snapshots and never read candidate profile
  tables directly.
- Regression coverage distinguishes active selected repair from retained
  static/weather candidate repair.
