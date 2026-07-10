# SESSION_NOTES.md

Purpose: current project baseline, handoff notes, and session log for `monitorovaci_platforma`.

## Latest Baseline

Date: 2026-06-05

The user requested a read-only review of the current project state and confirmed this state should be treated as the baseline for future work. The review covered the repository root and subdirectories without intentionally modifying project files.

Baseline working tree observed before creating these context files:

```text
 M data/smartfuelpass/session_cookies.json
?? moduly/mereni/elektromery/data/
```

Observed untracked electric-meter data artifacts:

```text
moduly/mereni/elektromery/data/old/19891.ts
moduly/mereni/elektromery/data/old/19892.ts
moduly/mereni/elektromery/data/old/20445.ts
moduly/mereni/elektromery/data/old/23582.ts
moduly/mereni/elektromery/data/old/39443.ts
moduly/mereni/elektromery/data/old/FVE 2026-02.xlsx
moduly/mereni/elektromery/data/old/LDS 2026-02.xlsx
```

Do not inspect or clean these artifacts unless the user explicitly asks.

## Entry Points

- Scheduler: `main.py`
- Scheduler schedules: `core/scheduler/job_schedule.py`
- Scheduler runtime: `core/scheduler/scheduler.py`
- Scheduler metrics: `core/scheduler/metrics.py`
- FastAPI app: `services/api/main.py`
- API auth tokens: `services/api/core/tokens.py`
- API dependencies: `services/api/core/dependencies.py`
- Streamlit dashboard: `moduly/apps/dashboard/login.py`
- Streamlit navigation: `moduly/apps/dashboard/navigation_config.py`
- Streamlit auth: `moduly/apps/dashboard/auth.py`
- Dashboard DB model: `moduly/apps/dashboard/database/models.py`
- Dashboard DB bootstrap: `moduly/apps/dashboard/database/db_init.py`
- Streamlit config: `.streamlit/config.toml`
- Reverse proxy config: `Caddyfile`
- Experimental Next.js area: `frontend_next/`

## Current Architecture Snapshot

- The active dashboard is Streamlit.
- `frontend_next/` is experimental, not currently used in daily operation, and may be developed further later.
- FastAPI exposes health, scheduler health, auth, admin, kalorimetry, manometry, plynomery, vodomery, and web-search routers.
- PostgreSQL is the normalized storage layer for monitoring/dashboard/web-search/revision data.
- MSSQL connections exist for source or legacy operational data.
- Scheduler definitions are centralized in `core/scheduler/job_schedule.py`.
- Scheduler runtime uses locks, metrics, manual run specs, and email alerts.
- Dashboard permissions are centralized around navigation config and dashboard user records.

## Database and Schema Notes

Known schema responsibilities:

- `monitoring`: normalized measurements, anomaly scores/events, alerting/outlier data, SmartFuelPass, meteo data.
- `dashboard`: Streamlit users and permissions.
- `web_search`: monitors and search results.
- `revize`: revision/evidence records.
- `dbo`: source or legacy operational tables.
- `evidence`: QGIS/evidence device metadata.

Important time columns and concepts:

- `source_date`
- `time_utc`
- `time_basis`
- `source_timezone`
- `source_utc_offset_minutes`
- `time_fold`
- `timestamp_position`
- SmartFuelPass start/end UTC/source interval semantics.

## Domain Notes

- `vodomery`: water meters, AREAL/SCVK sources, anomaly models v1/v2/v3, event handling, alerting, outlier review, reports, billing.
- `plynomery`: gas meters, baseline and weather-adjusted models, expected-zero/outlier/alerting behavior.
- `elektromery`: electricity meters, SOFTLINK and binary imports, OTE reporting, new device discovery.
- `kalorimetry`: heat meter imports, normalization, outlier review.
- `manometry`: pressure imports, dashboard/API surfaces.
- `smartfuelpass`: card/fuel imports and reports with browser/session artifacts.
- `web_search`: monitored searches and persisted results.

Water event examples:

- `NIGHT_USAGE`
- `SPIKE`
- `LONG_LEAK`
- `ZERO_FLOW`
- `EXPECTED_ZERO_USAGE`
- `OUTLIER_REVIEW`

## Current Functional Notes

- The water-meter dashboard page for anomalies/events contains event-type filtering for currently open and historical event sections.
- The selectors support filtering examples such as `SPIKE` and `NIGHT_USAGE`.
- The active Streamlit sidebar navigation is disabled through `.streamlit/config.toml` with custom dashboard navigation handling.
- Caddy is configured to reverse proxy port `:8080` to `127.0.0.1:8001`.

## Test Inventory

Read-only inventory found:

- 52 test files.
- 335 test functions.

High-value test areas:

- Scheduler behavior.
- Measurement imports, gaps, resets, outliers, and time semantics.
- Dashboard navigation, authentication, and auto refresh.
- Reports and billing.
- SmartFuelPass import/report workflow.
- Web search workflow.

Common verification commands:

```powershell
python -m pytest tests -v --tb=short
python -m pytest tests\test_scheduler.py -v --tb=short
python -m pytest tests\test_vodomery_db_import.py -v --tb=short
python -m pytest tests\test_dashboard_navigation_config.py -v --tb=short
```

Experimental frontend verification:

```powershell
cd frontend_next
npm run typecheck
```

Use frontend verification only when the task touches `frontend_next/`.

## Open Questions and Cleanup Topics

These are recognized topics, not approved changes:

- Decide whether SmartFuelPass session files should remain tracked.
- Decide whether scheduler lock files should remain tracked.
- Decide whether `frontend_next/tsconfig.tsbuildinfo` should be untracked/ignored.
- Decide whether `.gitignore` should ignore nested electric-meter data artifacts such as `moduly/mereni/elektromery/data/old/*.ts`.
- Decide whether context-file updates should be committed together with code changes or as separate documentation commits.

## Active Multi-Step Plan: Shared Prediction Core

Date opened: 2026-07-08
Date revised: 2026-07-09

Objective:
- Move meter prediction toward a universal pipeline with media-specific
  adapters, candidate model plugins, configurable forecast periods, rolling
  backtests, and per-identifier model selection, while preserving current
  production behavior until each step is explicitly completed.

Rules:
- Implement only the next unchecked step unless the user explicitly changes
  the plan.
- Mark a step complete only after code/docs changes and targeted verification
  for that step are done.
- Do not enable a new candidate model for automatic production selection until
  the checklist reaches the explicit enablement step.
- Vodomery production scoring uses `active` per-identifier selected-model
  snapshots when scoring the global active model. The global active model
  remains the safe fallback and score `model_version`; non-active candidate
  scoring remains pure per-candidate scoring for comparison.
- Forecast-period length is part of the shared pipeline contract: vodomery use
  weekly periods first, while future elektromery prediction will use monthly
  next-month periods calculated around the middle of the current calendar
  month.
- Candidate model parameter variants should be registered as candidates when
  they can produce materially different forecasts.
- The detailed architecture and rollout plan lives in
  `PREDICTION_PIPELINE_PLAN.md`.

Checklist:
- [x] 1. Create shared prediction contracts and data classes under
  `moduly/mereni/prediction/` with no production behavior change.
- [x] 2. Add rolling weekly backtest scaffolding and unit tests on synthetic
  data, including coverage, MAE, RMSE, bias, and WAPE-style normalized error.
- [x] 3. Add the first `vodomery` media adapter around existing tables,
  measurement filters, profile storage, active model lookup, and selection
  metadata, preserving current outputs.
- [x] 4. Move existing vodomery candidate models 1-3 behind the shared
  candidate interface without changing active-model behavior.
- [x] 5. Add `Model 4 - seasonal yearly blend` for vodomery using a 12-month
  training window, robust seasonal/day-of-week/slot blend, and fallback
  profiles. Keep it measured only and not eligible for automatic activation.
- [x] 6. Extend weekly vodomery rebuild reporting/storage so all candidates
  show rolling backtest metrics and whether they are eligible for selection.
- [x] 7. Add per-identifier rolling backtest storage and report summaries for
  vodomery candidate models, keeping per-identifier activation disabled.
- [x] 8. Define shared forecast-period and per-identifier selection contracts,
  including selected-model decision objects, fallback reasons, and tests. No
  production scoring behavior change.
- [x] 9. Add generic storage/bootstrap for selected model snapshots by medium,
  identifier, and forecast period, with audit fields and historical immutability
  rules.
- [x] 10. Wire vodomery weekly rebuild to persist per-identifier selected-model
  snapshots for the next weekly period in dry-run mode. Scoring still uses the
  current global active model.
- [x] 11. Extend the vodomery rebuild report with selected-vs-global model
  comparison, fallback counts, measured-only would-win counts, and worst
  identifiers by selected eligible rolling WAPE.
- [x] 12. Add vodomery scoring/profile lookup support for per-identifier
  selection behind an explicit feature flag or configuration switch, default
  disabled.
- [x] 13. Enable vodomery per-identifier model selection in production after a
  reviewed dry-run rebuild, keeping the global active model as fallback.
- [x] 14. Generalize forecast-period and rolling-backtest handling so the shared
  pipeline supports both weekly and monthly periods.
- [x] 15. Extract a reusable media pipeline runner so adding a new model or a
  parameter variant requires plugin registration and adapter metadata rather
  than edits to scheduler/report core.
- [x] 16. Adapt the shared prediction pipeline to `plynomery`, preserving current
  baseline/weather-aware behavior and gas-specific expected-zero/outlier
  semantics.
- [x] 17. Design and integrate `elektromery` candidates with monthly next-month
  prediction, after reviewing electricity source cadence, calendar/tariff
  behavior, imports, and reporting semantics.
- [x] 18. Add cross-media dashboard/report views for candidate and
  per-identifier selection performance only after the shared core has vodomery
  and at least one more medium integrated.

## Session Log Template

Use this format for future entries:

```text
### YYYY-MM-DD

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
- ...
```

## Restart Handoff Template

This entry is mandatory before every Windows workstation restart:

```text
### YYYY-MM-DD HH:MM - Pre-restart handoff

Reason for restart:
- ...

Current task/conversation state:
- Completed: ...
- Pending: ...
- First action after restart: ...

Working tree and deployment:
- `git status --short`: ...
- Relevant changed files: ...
- Runtime-deployed files and hash/config state: ...

Sensitive/runtime artifacts:
- Do not print/change/delete/commit: ...

Expected processes after restart:
- FastAPI/Uvicorn: one runtime on `127.0.0.1:8000`
- Streamlit: one runtime on `127.0.0.1:8001`
- Scheduler: one `main.py` runtime holding `scheduler_process` lock
- Caddy: one runtime owning TCP 80/443 and `127.0.0.1:2019`

Expected application state:
- FastAPI live/ready: HTTP 200
- Streamlit health: HTTP 200
- Scheduler heartbeat/job expectations: ...
- Tracked/runtime Caddyfile hash expectation: ...
- HTTP -> HTTPS: 308
- HTTPS dashboard: expected status/behavior ...
- Protected API without bearer token: HTTP 401 JSON
- Authentication/change-specific expectations: ...

Required post-restart checks:
- ...

Known risks or accepted gaps:
- ...
```

## Session Log

### 2026-07-08

Scope:
- Completed step 1 of the shared prediction core plan.

Changed:
- Added `moduly/mereni/prediction/` with shared prediction contracts,
  dataclasses, and protocols for candidate models and media adapters.
- Added lightweight unit tests for the new contracts.
- Marked checklist step 1 complete.

Verified:
- `.venv\Scripts\python.exe -m py_compile moduly\mereni\prediction\__init__.py
  moduly\mereni\prediction\contracts.py tests\test_prediction_contracts.py`
- `.venv\Scripts\python.exe -m pytest tests\test_prediction_contracts.py -q
  --tb=short` reported `4 passed`.

Not verified:
- No production scheduler/API/dashboard behavior was exercised because step 1
  only adds unused shared contracts.

Follow-up:
- Continue with step 2: rolling weekly backtest scaffolding and synthetic-data
  tests.

### 2026-07-08 - Shared prediction core step 2

Scope:
- Completed step 2 of the shared prediction core plan.

Changed:
- Added rolling weekly backtest scaffolding in
  `moduly/mereni/prediction/backtest.py`.
- Added fold generation, metric calculation, backtest result serialization,
  and a protocol for candidates that can produce validation predictions.
- Added synthetic-data tests for weekly folds, coverage, MAE, RMSE, bias, WAPE,
  zero-actual WAPE handling, and aggregated rolling backtest results.
- Marked checklist step 2 complete.

Verified:
- `.venv\Scripts\python.exe -m py_compile moduly\mereni\prediction\__init__.py
  moduly\mereni\prediction\contracts.py moduly\mereni\prediction\backtest.py
  tests\test_prediction_contracts.py tests\test_prediction_backtest.py`
- `.venv\Scripts\python.exe -m pytest tests\test_prediction_contracts.py
  tests\test_prediction_backtest.py -q --tb=short` reported `10 passed`.

Not verified:
- No production scheduler/API/dashboard behavior was exercised because step 2
  only adds unused shared backtest scaffolding.

Follow-up:
- Continue with step 3: add the first `vodomery` media adapter around existing
  tables and metadata while preserving current outputs.

### 2026-07-08 - Shared prediction core step 3

Scope:
- Completed step 3 of the shared prediction core plan.
- Recorded the future direction that model selection should eventually support
  per-identifier best-model assignment, while current global activation stays
  unchanged.

Changed:
- Added generic `PredictionSelectionMetadata`.
- Added `moduly/mereni/vodomery/prediction_adapter.py` with a vodomery media
  adapter around existing measurement, profile, active-model, and selection
  metadata tables.
- Added tests for vodomery adapter active-model lookup injection, current
  quality filters, observation serialization, selection metadata serialization,
  and profile row mapping.
- Marked checklist step 3 complete.

Verified:
- `.venv\Scripts\python.exe -m py_compile moduly\mereni\prediction\__init__.py
  moduly\mereni\prediction\contracts.py moduly\mereni\prediction\backtest.py
  moduly\mereni\vodomery\prediction_adapter.py
  tests\test_prediction_contracts.py tests\test_prediction_backtest.py
  tests\test_vodomery_prediction_adapter.py`
- `.venv\Scripts\python.exe -m pytest tests\test_prediction_contracts.py
  tests\test_prediction_backtest.py tests\test_vodomery_prediction_adapter.py
  -q --tb=short` reported `15 passed`.
- `.venv\Scripts\python.exe -m pytest tests\test_vodomery_prediction.py
  tests\test_prediction_contracts.py tests\test_prediction_backtest.py
  tests\test_vodomery_prediction_adapter.py -q --tb=short` reported
  `18 passed`.

Not verified:
- The adapter was not called from scheduler/API/dashboard production paths.
  That is intentional for step 3.

Follow-up:
- Continue with step 4: move existing vodomery candidate models 1-3 behind
  the shared candidate interface without changing active-model behavior.

### 2026-07-08 - Shared prediction core step 4

Scope:
- Completed step 4 of the shared prediction core plan.

Changed:
- Existing vodomery candidate models 1-3 now expose shared
  `PredictionCandidateSpec` metadata through a `VodomeryCandidateModelPlugin`
  registry.
- `vodomery_prediction.rebuild_profiles` still uses the same model versions,
  model names, SQL profile builders, validation logic, and global active-model
  selection semantics.
- Added tests for shared candidate metadata and plugin-based rebuild dispatch.
- Marked checklist step 4 complete.

Verified:
- `.venv\Scripts\python.exe -m py_compile moduly\mereni\prediction\__init__.py
  moduly\mereni\prediction\contracts.py moduly\mereni\prediction\backtest.py
  moduly\mereni\vodomery\prediction_adapter.py
  moduly\mereni\vodomery\vodomery_prediction.py
  tests\test_prediction_contracts.py tests\test_prediction_backtest.py
  tests\test_vodomery_prediction_adapter.py tests\test_vodomery_prediction.py`
- `.venv\Scripts\python.exe -m pytest tests\test_vodomery_prediction.py
  tests\test_prediction_contracts.py tests\test_prediction_backtest.py
  tests\test_vodomery_prediction_adapter.py -q --tb=short` reported
  `20 passed`.
- `.venv\Scripts\python.exe -m pytest
  tests\test_scheduler.py::test_weekly_job_rebuilds_profiles_and_sends_report
  tests\test_vodomery_prediction.py tests\test_prediction_contracts.py
  tests\test_prediction_backtest.py tests\test_vodomery_prediction_adapter.py
  -q --tb=short` reported `21 passed`.

Not verified:
- No live database profile rebuild was run. Step 4 preserves the existing SQL
  builders and only changes the in-process candidate dispatch wrapper.

Follow-up:
- Continue with step 5: add measured-only vodomery `Model 4 - seasonal yearly
  blend` using a 12-month training window.

### 2026-07-08 - Shared prediction core step 5

Scope:
- Completed step 5 of the shared prediction core plan.

Changed:
- Added measured-only vodomery `Model 4 - seasonal yearly blend` with model
  version `4`, key `seasonal_yearly_blend`, and a 12-month training window.
- Model 4 builds eval/deploy anomaly profiles from a seasonal day-of-year,
  day-of-week, workday, slot, and interval fallback blend.
- Model 4 deploy profiles use the last 12 months ending at rebuild time; its
  validation profiles use the 12 months before the validation window.
- Full weekly rebuilds now calculate Model 4 metrics, but automatic selection
  ignores candidates with `selection_enabled=False`.
- Default runtime/scoring candidate versions remain `1`, `2`, and `3`, so
  quarter-hour scoring and alerting do not start using measured-only Model 4.
- Marked checklist step 5 complete.

Verified:
- `.venv\Scripts\python.exe -m py_compile moduly\mereni\vodomery\vodomery_prediction.py
  tests\test_vodomery_prediction.py moduly\mereni\prediction\__init__.py
  moduly\mereni\prediction\contracts.py moduly\mereni\prediction\backtest.py`
- `.venv\Scripts\python.exe -m pytest tests\test_vodomery_prediction.py
  tests\test_prediction_contracts.py tests\test_prediction_backtest.py
  tests\test_vodomery_prediction_adapter.py -q --tb=short` reported
  `24 passed`.
- `.venv\Scripts\python.exe -m pytest
  tests\test_scheduler.py::test_quarter_hour_job_scores_all_candidate_models_and_alerts_active_only
  tests\test_scheduler.py::test_weekly_job_rebuilds_profiles_and_sends_report
  tests\test_vodomery_prediction.py tests\test_prediction_contracts.py
  tests\test_prediction_backtest.py tests\test_vodomery_prediction_adapter.py
  -q --tb=short` reported `26 passed`.

Not verified:
- No live PostgreSQL profile rebuild was run. The new Model 4 SQL is covered
  by unit-level statement/parameter checks only.

Follow-up:
- Continue with step 6: extend weekly vodomery rebuild reporting/storage so
  all candidates show rolling backtest metrics and eligibility.

### 2026-07-08 - Shared prediction core step 6

Scope:
- Completed step 6 of the shared prediction core plan.

Changed:
- Weekly vodomery full rebuild now calculates rolling weekly backtest metrics
  for every candidate model, including measured-only Model 4.
- Rolling backtest uses eight 7-day folds, candidate-specific training
  windows, temporary profile model versions, and weighted aggregate coverage,
  MAE, RMSE, bias, and WAPE.
- `monitoring.vodomery_model_selection_candidates` now stores model key,
  training/validation window lengths, selection eligibility, and rolling
  backtest metrics through additive `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`
  bootstrap logic.
- The vodomery model rebuild email table now shows eligibility, rolling fold
  count, rolling coverage, rolling WAPE, rolling MAE, rolling RMSE, and
  rolling bias.
- Marked checklist step 6 complete.

Verified:
- `.venv\Scripts\python.exe -m py_compile moduly\mereni\vodomery\vodomery_prediction.py
  moduly\mereni\vodomery\database\models.py
  moduly\mereni\vodomery\database\model_validation.py
  moduly\mereni\vodomery\reporting\model_rebuild_report.py
  tests\test_vodomery_prediction.py tests\test_vodomery_model_rebuild_report.py`
- `.venv\Scripts\python.exe -m pytest tests\test_vodomery_prediction.py
  tests\test_vodomery_model_rebuild_report.py tests\test_prediction_contracts.py
  tests\test_prediction_backtest.py tests\test_vodomery_prediction_adapter.py
  -q --tb=short` reported `28 passed`.
- `.venv\Scripts\python.exe -m pytest
  tests\test_scheduler.py::test_quarter_hour_job_scores_all_candidate_models_and_alerts_active_only
  tests\test_scheduler.py::test_weekly_job_rebuilds_profiles_and_sends_report
  tests\test_vodomery_prediction.py tests\test_vodomery_model_rebuild_report.py
  tests\test_prediction_contracts.py tests\test_prediction_backtest.py
  tests\test_vodomery_prediction_adapter.py -q --tb=short` reported
  `30 passed`.

Not verified:
- No live PostgreSQL weekly rebuild was run, so the additive migration and
  rolling metrics have not yet been exercised against the real production
  tables/data.

Follow-up:
- Continue with step 7: review several weekly rebuild results before deciding
  whether Model 4 or another measured-only candidate can become eligible for
  automatic selection.

### 2026-07-08 - Manual vodomery model rebuild after step 6

Scope:
- Ran a live vodomery prediction profile rebuild with the new candidate setup
  and sent the vodomery model rebuild email report.

Executed:
- `.venv-production\Scripts\python.exe` called
  `moduly.mereni.vodomery.vodomery_prediction.rebuild_profiles()`.
- The resulting payload was passed to
  `send_vodomery_model_rebuild_report(result)`.

Result:
- New `selection_run_id`: `27`.
- Active model remained `Model 3 - recency weighted blend` (`model_version=3`).
- Previous active model was also `Model 3 - recency weighted blend`.
- The rebuild evaluated 4 candidates; Model 4 stayed `selection_enabled=False`
  and was not selected.
- Email report returned `recipient_count=1`.
- Candidate summary:
  - Model 1: coverage `1.0`, MAE `0.11829`, rolling WAPE `12.004258`,
    profiles `37800`.
  - Model 2: coverage `1.0`, MAE `0.110231`, rolling WAPE `11.936217`,
    profiles `37800`.
  - Model 3: coverage `1.0`, MAE `0.037606`, rolling WAPE `4.455449`,
    profiles `37800`, selected.
  - Model 4: coverage `1.0`, MAE `0.073065`, rolling WAPE `8.741695`,
    profiles `37800`, measured only.

Notes:
- An earlier attempt hit the shell timeout before commit; PostgreSQL sequence
  values may therefore show a skipped selection run id.
- No email addresses, credentials, tokens, cookie values, or raw measurement
  rows were printed.

### 2026-07-08 - Added measured-only vodomery Model 5

Scope:
- Added a new long-window vodomery prediction candidate after the first live
  step-6 rebuild showed Model 3 still performing best.

Changed:
- Added `Model 5 - long recency weighted blend` with model version `5`, key
  `recency_weighted_long_blend`, a 12-month training window, and a 90-day
  recency half-life.
- Model 5 reuses the Model 3 recency-weighted blend SQL with configurable
  half-life and is included in full weekly rebuild metrics and rolling
  backtests.
- Model 5 is `selection_enabled=False`; runtime scoring candidates remain
  models `1`, `2`, and `3`.

Verified:
- Targeted verification is recorded in the final response for the session
  that added the candidate.

Not verified:
- No live weekly rebuild or email was run for Model 5 yet.

Follow-up:
- Continue step 7 by reviewing weekly rebuild results for measured-only
  candidates before enabling any new automatic selection path.

### 2026-07-09 - Manual vodomery model rebuild with Model 5

Scope:
- Ran a live vodomery prediction profile rebuild with measured-only Model 5
  included and sent the vodomery model rebuild email report.

Executed:
- `.venv-production\Scripts\python.exe` called
  `moduly.mereni.vodomery.vodomery_prediction.rebuild_profiles()`.
- The resulting payload was passed to
  `send_vodomery_model_rebuild_report(result)`.

Result:
- New `selection_run_id`: `28`.
- Active model remained `Model 3 - recency weighted blend` (`model_version=3`).
- Previous active model was also `Model 3 - recency weighted blend`.
- The rebuild evaluated 5 candidates; Models 4 and 5 stayed
  `selection_enabled=False` and were not selected.
- Email report returned `recipient_count=1`.
- Candidate summary:
  - Model 1: coverage `1.0`, MAE `0.10238`, rolling WAPE `11.750575`,
    profiles `37800`.
  - Model 2: coverage `1.0`, MAE `0.10228`, rolling WAPE `11.608925`,
    profiles `37800`.
  - Model 3: coverage `1.0`, MAE `0.032789`, rolling WAPE `4.30433`,
    profiles `37800`, selected.
  - Model 4: coverage `1.0`, MAE `0.072911`, rolling WAPE `8.618235`,
    profiles `37800`, measured only.
  - Model 5: coverage `1.0`, MAE `0.289074`, rolling WAPE `27.021159`,
    profiles `37800`, measured only.

Notes:
- Two initial process-launch attempts failed before importing the application
  code, so they did not rebuild profiles or send email.
- No email addresses, credentials, tokens, cookie values, or raw measurement
  rows were printed.

### 2026-07-09 - Shared prediction core step 7

Scope:
- Completed step 7 of the shared prediction core plan.
- Added per-identifier rolling backtest metrics for vodomery candidate models
  as preparation for future per-identifier model selection.

Changed:
- Added `monitoring.vodomery_model_selection_device_candidates` ORM/storage
  for candidate model metrics by `identifikace`.
- Full vodomery weekly rebuild now computes rolling metrics both globally and
  per odběrné místo for every candidate.
- Each per-identifier candidate row records coverage, matched count, MAE,
  RMSE, bias, WAPE, eligibility, and whether it was the best candidate for
  that identifier in the backtest.
- The vodomery model rebuild email now includes a compact per-odběrné místo
  summary: winner counts by model and worst identifiers by best-model rolling
  WAPE.
- Per-identifier activation remains disabled; the global active model
  selection path is unchanged.

Verified:
- `.venv\Scripts\python.exe -m py_compile moduly\mereni\vodomery\vodomery_prediction.py
  moduly\mereni\vodomery\database\models.py
  moduly\mereni\vodomery\database\model_validation.py
  moduly\mereni\vodomery\reporting\model_rebuild_report.py
  tests\test_vodomery_prediction.py tests\test_vodomery_model_rebuild_report.py`
- `.venv\Scripts\python.exe -m pytest tests\test_vodomery_prediction.py
  tests\test_vodomery_model_rebuild_report.py tests\test_prediction_contracts.py
  tests\test_prediction_backtest.py tests\test_vodomery_prediction_adapter.py
  -q --tb=short` reported `33 passed`.
- `.venv\Scripts\python.exe -m pytest
  tests\test_scheduler.py::test_quarter_hour_job_scores_all_candidate_models_and_alerts_active_only
  tests\test_scheduler.py::test_weekly_job_rebuilds_profiles_and_sends_report
  tests\test_vodomery_prediction.py tests\test_vodomery_model_rebuild_report.py
  tests\test_prediction_contracts.py tests\test_prediction_backtest.py
  tests\test_vodomery_prediction_adapter.py -q --tb=short` reported
  `35 passed`.

Not verified:
- No live PostgreSQL weekly rebuild was run after this storage/report
  extension. The next live rebuild will create the new per-identifier table if
  needed and populate it.

Decisions/notes:
- Prediction rebuild runtime is not treated as a limiting factor because jobs
  run outside working peak hours.
- Vodomery remain the pipeline pilot before electricity prediction work.
- Future electricity prediction cadence is monthly: calculate around the
  middle of the calendar month for the entire following calendar month.

Follow-up:
- Continue step 8 by reviewing weekly rebuild results and per-identifier
  winners before enabling any new automatic selection path.

### 2026-07-09 - Manual vodomery model rebuild after step 7

Scope:
- Ran a live vodomery prediction profile rebuild after adding per-identifier
  rolling backtest storage and report summaries.
- Sent the vodomery model rebuild email report from the rebuild result.

Executed:
- `.venv-production\Scripts\python.exe` called
  `moduly.mereni.vodomery.vodomery_prediction.rebuild_profiles()`.
- The resulting payload was passed to
  `send_vodomery_model_rebuild_report(result)`.

Result:
- New `selection_run_id`: `29`.
- Active model remained `Model 3 - recency weighted blend` (`model_version=3`).
- Previous active model was also `Model 3 - recency weighted blend`.
- The rebuild evaluated 5 candidates; Models 4 and 5 stayed
  `selection_enabled=False` and were not selected globally.
- Email report returned `recipient_count=1`.
- Per-identifier candidate rows returned in the rebuild payload: `290`
  across `58` identifiers.
- Best-model rows by identifier: `58`.
- Per-identifier winner counts:
  - Model 1: `2`.
  - Model 2: `27`.
  - Model 3: `5`.
  - Model 4 measured-only: `7`.
  - Model 5 measured-only: `17`.
- Candidate summary:
  - Model 1: coverage `1.0`, MAE `0.102371`, rolling WAPE `11.743962`,
    profiles `37800`.
  - Model 2: coverage `1.0`, MAE `0.102272`, rolling WAPE `11.602401`,
    profiles `37800`.
  - Model 3: coverage `1.0`, MAE `0.0328`, rolling WAPE `4.3017`,
    profiles `37800`, selected.
  - Model 4: coverage `1.0`, MAE `0.072908`, rolling WAPE `8.613523`,
    profiles `37800`, measured only.
  - Model 5: coverage `1.0`, MAE `0.289029`, rolling WAPE `27.005077`,
    profiles `37800`, measured only.

Notes:
- One initial process-launch attempt failed before importing the application
  code, so it did not rebuild profiles or send email.
- No email addresses, credentials, tokens, cookie values, or raw measurement
  rows were printed.

### 2026-07-09 - Per-identifier prediction selection plan

Scope:
- Created the implementation plan for production per-identifier model selection
  and multi-media prediction pipeline rollout.

Changed:
- Added `PREDICTION_PIPELINE_PLAN.md` with target architecture, forecast-period
  rules, candidate plugin expectations, selection policy, storage/reporting
  shape, and rollout sequence.
- Added DEC-050 for per-identifier and horizon-aware prediction selection.
- Revised the active shared prediction core checklist so steps 8-18 now cover
  shared selection contracts, selected-model storage, vodomery dry-run
  snapshots, reporting, feature-flagged scoring lookup, production enablement,
  weekly/monthly horizon generalization, reusable pipeline runner, and later
  `plynomery`/`elektromery` integration.
- Updated `AGENTS.md` so future sessions know about
  `PREDICTION_PIPELINE_PLAN.md`.

Verified:
- Documentation-only change; code tests were not run.

Next step:
- Start checklist step 8: shared forecast-period and per-identifier selection
  contracts with tests, without changing production scoring behavior.

### 2026-07-09 - Shared prediction core step 8

Scope:
- Completed step 8 of the shared prediction core plan.
- Added shared forecast-period and per-identifier selected-model decision
  contracts without changing production scoring behavior.

Changed:
- Added `PredictionForecastCadence`, `PredictionForecastPeriodDefinition`,
  and `PredictionForecastPeriod` to describe weekly, monthly, or custom
  forecast horizons in the shared prediction core.
- Added `PredictionSelectionFallbackReason` and
  `PredictionSelectedModelDecision` to represent the selected model for one
  medium, identifier, and forecast period, including global-model fallback
  reasons and selected metrics.
- Exported the new contracts from `moduly.mereni.prediction`.
- Added unit tests for cadence serialization, period validation,
  selected-model serialization, global fallback behavior, and invalid fallback
  decisions.
- Marked checklist step 8 complete.

Verified:
- `.venv\Scripts\python.exe -m py_compile
  moduly\mereni\prediction\contracts.py
  moduly\mereni\prediction\__init__.py tests\test_prediction_contracts.py`
- `.venv\Scripts\python.exe -m pytest tests\test_prediction_contracts.py
  tests\test_prediction_backtest.py tests\test_vodomery_prediction_adapter.py
  -q --tb=short` reported `21 passed`.
- `.venv\Scripts\python.exe -m pytest tests\test_vodomery_prediction.py
  tests\test_vodomery_model_rebuild_report.py tests\test_prediction_contracts.py
  tests\test_prediction_backtest.py tests\test_vodomery_prediction_adapter.py
  -q --tb=short` reported `39 passed`.

Not changed:
- No production scoring, scheduler, database storage, or report behavior was
  changed in this step.

Follow-up:
- Continue with step 9: add generic selected-model snapshot storage/bootstrap
  by medium, identifier, and forecast period.

### 2026-07-09 - Shared prediction core step 9

Scope:
- Completed step 9 of the shared prediction core plan.
- Added generic selected-model snapshot storage/bootstrap for future
  per-identifier model selection.

Changed:
- Added `moduly/mereni/prediction/storage.py` with
  `monitoring.prediction_selected_model_snapshots` ORM metadata, bootstrap,
  immutable insert helper, lookup statement, load helper, and row/contract
  serializers.
- Snapshot identity is medium, identifier, forecast-period start/end, cadence,
  and selection mode. This supports separate `dry_run` and `active` snapshots.
- Inserts use PostgreSQL `ON CONFLICT DO NOTHING` against the snapshot identity,
  so an existing historical snapshot is not overwritten.
- Snapshot rows keep selected model, global fallback model, fallback reason,
  metrics, metadata JSON, selection run id, selection mode, and created-at
  audit timestamp.
- Exported storage helpers from `moduly.mereni.prediction`.
- Added `tests/test_prediction_storage.py`.
- Updated `AGENTS.md` project map with the new shared storage module.
- Marked checklist step 9 complete.

Verified:
- `.venv\Scripts\python.exe -m py_compile
  moduly\mereni\prediction\contracts.py
  moduly\mereni\prediction\storage.py moduly\mereni\prediction\__init__.py
  tests\test_prediction_contracts.py tests\test_prediction_storage.py`
- `.venv\Scripts\python.exe -m pytest tests\test_prediction_contracts.py
  tests\test_prediction_storage.py tests\test_prediction_backtest.py
  tests\test_vodomery_prediction_adapter.py -q --tb=short` reported
  `32 passed`.
- `.venv\Scripts\python.exe -m pytest tests\test_vodomery_prediction.py
  tests\test_vodomery_model_rebuild_report.py tests\test_prediction_contracts.py
  tests\test_prediction_storage.py tests\test_prediction_backtest.py
  tests\test_vodomery_prediction_adapter.py -q --tb=short` reported
  `50 passed`.

Not changed:
- The generic snapshot table is not yet called from vodomery rebuild, scoring,
  scheduler, or reporting. That is step 10.

Follow-up:
- Continue with step 10: wire vodomery weekly rebuild to persist
  per-identifier selected-model snapshots for the next weekly period in
  `dry_run` mode while scoring still uses the current global active model.

### 2026-07-09 - Shared prediction core step 10

Scope:
- Completed step 10 of the shared prediction core plan.
- Wired vodomery weekly rebuild to persist per-identifier selected-model
  snapshots for the next weekly forecast period in `dry_run` mode.

Changed:
- `rebuild_profiles()` now ensures the generic selected-model snapshot table
  during full vodomery rebuilds.
- Full vodomery rebuild creates a weekly forecast period from rebuild time to
  rebuild time plus seven days.
- Per-identifier dry-run decisions select the best selection-enabled candidate
  by rolling WAPE when coverage is above the configured threshold.
- When no safe eligible candidate exists, the dry-run decision falls back to
  the global selected model and records a fallback reason.
- Full rebuild persists dry-run selected-model decisions through
  `persist_selected_model_decisions`.
- Rebuild result payload now includes `forecast_period`,
  `selected_model_snapshot_mode`, and `selected_model_snapshot_count`.
- Added tests for weekly forecast-period construction, dry-run eligible-model
  selection, coverage fallback, and full rebuild snapshot persistence.
- Marked checklist step 10 complete.

Verified:
- `.venv\Scripts\python.exe -m py_compile
  moduly\mereni\vodomery\vodomery_prediction.py
  moduly\mereni\prediction\storage.py moduly\mereni\prediction\contracts.py
  moduly\mereni\prediction\__init__.py tests\test_vodomery_prediction.py
  tests\test_prediction_storage.py`
- `.venv\Scripts\python.exe -m pytest tests\test_vodomery_prediction.py
  tests\test_prediction_storage.py tests\test_prediction_contracts.py
  tests\test_prediction_backtest.py tests\test_vodomery_prediction_adapter.py
  -q --tb=short` reported `53 passed`.
- `.venv\Scripts\python.exe -m pytest
  tests\test_scheduler.py::test_quarter_hour_job_scores_all_candidate_models_and_alerts_active_only
  tests\test_scheduler.py::test_weekly_job_rebuilds_profiles_and_sends_report
  tests\test_vodomery_prediction.py tests\test_vodomery_model_rebuild_report.py
  tests\test_prediction_contracts.py tests\test_prediction_storage.py
  tests\test_prediction_backtest.py tests\test_vodomery_prediction_adapter.py
  -q --tb=short` reported `56 passed`.

Not changed:
- Vodomery scoring still uses the current global active model. No runtime path
  reads `active` per-identifier snapshots yet.
- The rebuild report does not yet compare selected-vs-global snapshot results;
  that is step 11.

Follow-up:
- Continue with step 11: extend the vodomery rebuild report with
  selected-vs-global model comparison, fallback counts, measured-only
  would-win counts, and worst identifiers by selected eligible rolling WAPE.

### 2026-07-09 - Shared prediction core step 11

Scope:
- Completed step 11 of the shared prediction core plan.
- Extended the vodomery weekly rebuild email report with dry-run
  per-identifier selected-model diagnostics.

Changed:
- `rebuild_profiles()` now includes serialized `selected_model_snapshots` in
  the rebuild result payload so the report can compare dry-run decisions
  without querying the database again.
- `send_vodomery_model_rebuild_report()` now returns
  `selected_model_snapshot_count` together with candidate/device counts.
- The vodomery model rebuild email now includes a
  `Dry-run per-odberne misto selection` section with selected-vs-global counts,
  fallback reason counts, measured-only would-win counts, selected-model
  counts, forecast-period metadata, and worst selected eligible identifiers by
  rolling WAPE.
- Added report test coverage for the new dry-run selection section and rebuild
  test coverage for the serialized snapshot payload.
- Marked checklist step 11 complete.

Verified:
- `.venv\Scripts\python.exe -m py_compile
  moduly\mereni\vodomery\reporting\model_rebuild_report.py
  moduly\mereni\vodomery\vodomery_prediction.py
  tests\test_vodomery_model_rebuild_report.py tests\test_vodomery_prediction.py`
  passed.
- `.venv\Scripts\python.exe -m pytest
  tests\test_vodomery_model_rebuild_report.py tests\test_vodomery_prediction.py
  tests\test_prediction_storage.py tests\test_prediction_contracts.py
  tests\test_prediction_backtest.py tests\test_vodomery_prediction_adapter.py
  -q --tb=short` reported `54 passed`.
- `.venv\Scripts\python.exe -m pytest
  tests\test_scheduler.py::test_quarter_hour_job_scores_all_candidate_models_and_alerts_active_only
  tests\test_scheduler.py::test_weekly_job_rebuilds_profiles_and_sends_report
  tests\test_vodomery_prediction.py tests\test_vodomery_model_rebuild_report.py
  tests\test_prediction_contracts.py tests\test_prediction_storage.py
  tests\test_prediction_backtest.py tests\test_vodomery_prediction_adapter.py
  -q --tb=short` reported `56 passed`.

Not changed:
- Vodomery scoring still uses the current global active model. No runtime path
  reads `active` per-identifier snapshots yet.
- A live weekly rebuild/email was not run during this implementation step.

Follow-up:
- Continue with step 12: add vodomery scoring/profile lookup support for
  per-identifier selection behind an explicit feature flag or configuration
  switch, default disabled.

### 2026-07-09 - Manual vodomery model rebuild after step 11

Scope:
- Ran a live vodomery prediction profile rebuild after adding the dry-run
  per-identifier selection report section.
- Sent the vodomery model rebuild email report.

Executed:
- `.venv-production\Scripts\python.exe` called
  `moduly.mereni.vodomery.vodomery_prediction.rebuild_profiles()`.
- The resulting payload was passed to
  `send_vodomery_model_rebuild_report(result)`.

Result:
- New `selection_run_id`: `30`.
- Active model remained `Model 3 - recency weighted blend` (`model_version=3`).
- Previous active model was also `Model 3 - recency weighted blend`.
- Forecast period in the dry-run selection payload:
  `2026-07-09 11:35 - 2026-07-16 11:35`.
- The rebuild evaluated 5 candidates and 290 per-identifier candidate rows.
- Dry-run selected-model snapshots persisted: `58`.
- Selected-vs-global dry-run summary:
  - same as global model: `15`;
  - different from global model: `43`;
  - fallback to global model: `5`.
- Selected dry-run model counts:
  - Model 1: `1`;
  - Model 2: `42`;
  - Model 3: `15`.
- Fallback reason counts:
  - `no_identifier_metrics`: `5`.
- Measured-only would-win counts:
  - Model 4: `7`;
  - Model 5: `17`.
- Email report returned `recipient_count=1`,
  `candidate_count=5`, `device_candidate_count=290`, and
  `selected_model_snapshot_count=58`.
- Candidate summary:
  - Model 1: coverage `1.0`, MAE `0.102386`, rolling WAPE `11.752645`,
    profiles `37800`.
  - Model 2: coverage `1.0`, MAE `0.102286`, rolling WAPE `11.611093`,
    profiles `37800`, selected devices `58`.
  - Model 3: coverage `1.0`, MAE `0.032874`, rolling WAPE `4.299733`,
    profiles `37800`, selected.
  - Model 4: coverage `1.0`, MAE `0.072918`, rolling WAPE `8.618299`,
    profiles `37800`, measured only.
  - Model 5: coverage `1.0`, MAE `0.289025`, rolling WAPE `27.024664`,
    profiles `37800`, measured only.

Notes:
- Two initial process-launch attempts failed because of shell quoting before
  importing application code. They did not rebuild profiles or send email.
- No email addresses, credentials, tokens, cookie values, or raw measurement
  rows were printed.

### 2026-07-09 - Vodomery model rebuild email body clarification

Scope:
- Improved the vodomery model rebuild email body after reviewing the delivered
  step-11 test email.

Changed:
- Full `rebuild_profiles()` results now include `rebuild_duration_seconds` so
  the report can show how long model recalculation took.
- The top report summary now includes `Rebuild duration` near `Selection run`.
- The main `Model` table now has an inline explanation for every column and
  key term, including eligibility, measured-only candidates, rolling metrics,
  WAPE, and `Selected devices`.
- The per-identifier rolling backtest summary table now includes an
  `Odberna mista` column listing identifiers for each best model.
- The per-identifier detail table now lists all available best-model rows
  instead of only the capped worst rows.
- Added inline explanations below the per-identifier tables.
- Renamed and explained the dry-run selection section so it is clear that it
  is a stored proposal for the next forecast period and does not yet affect
  production scoring.

Verified:
- `.venv\Scripts\python.exe -m py_compile
  moduly\mereni\vodomery\reporting\model_rebuild_report.py
  moduly\mereni\vodomery\vodomery_prediction.py
  tests\test_vodomery_model_rebuild_report.py tests\test_vodomery_prediction.py`
  passed.
- `.venv\Scripts\python.exe -m pytest
  tests\test_vodomery_model_rebuild_report.py tests\test_vodomery_prediction.py
  -q --tb=short` reported `22 passed`.
- `.venv\Scripts\python.exe -m pytest
  tests\test_scheduler.py::test_weekly_job_rebuilds_profiles_and_sends_report
  tests\test_vodomery_model_rebuild_report.py tests\test_vodomery_prediction.py
  tests\test_prediction_contracts.py tests\test_prediction_storage.py
  tests\test_prediction_backtest.py tests\test_vodomery_prediction_adapter.py
  -q --tb=short` reported `55 passed`.

Not run:
- A new live rebuild/email was not sent after this email-body clarification.

### 2026-07-09 - Manual vodomery model rebuild after email body clarification

Scope:
- Ran a live vodomery prediction profile rebuild after clarifying the email
  body and sent the vodomery model rebuild email report.

Executed:
- `.venv-production\Scripts\python.exe` called
  `moduly.mereni.vodomery.vodomery_prediction.rebuild_profiles()`.
- The resulting payload was passed to
  `send_vodomery_model_rebuild_report(result)`.
- Only the model rebuild report path was run; the full `weekly_job` was not
  run to avoid sending unrelated weekly reports.

Result:
- New `selection_run_id`: `31`.
- Active model remained `Model 3 - recency weighted blend` (`model_version=3`).
- Previous active model was also `Model 3 - recency weighted blend`.
- Forecast period in the dry-run selection payload:
  `2026-07-09 12:19 - 2026-07-16 12:19`.
- Rebuild duration reported by the payload: `713.794` seconds.
- The rebuild evaluated 5 candidates and 290 per-identifier candidate rows.
- Dry-run selected-model snapshots persisted: `58`.
- Selected-vs-global dry-run summary:
  - same as global model: `16`;
  - different from global model: `42`;
  - fallback to global model: `4`.
- Selected dry-run model counts:
  - Model 2: `42`;
  - Model 3: `16`.
- Fallback reason counts:
  - `no_identifier_metrics`: `4`.
- Measured-only would-win counts:
  - Model 4: `7`;
  - Model 5: `17`.
- Email report returned `recipient_count=1`,
  `candidate_count=5`, `device_candidate_count=290`, and
  `selected_model_snapshot_count=58`.
- Candidate summary:
  - Model 1: coverage `1.0`, MAE `0.102392`, rolling WAPE `11.753918`,
    profiles `37800`.
  - Model 2: coverage `1.0`, MAE `0.102291`, rolling WAPE `11.612363`,
    profiles `37800`, selected devices `58`.
  - Model 3: coverage `1.0`, MAE `0.032879`, rolling WAPE `4.299627`,
    profiles `37800`, selected.
  - Model 4: coverage `1.0`, MAE `0.07292`, rolling WAPE `8.619108`,
    profiles `37800`, measured only.
  - Model 5: coverage `1.0`, MAE `0.289041`, rolling WAPE `27.027522`,
    profiles `37800`, measured only.

Notes:
- One first attempt failed before importing application code because
  multiline Python code was passed incorrectly to `python -c`. It did not
  rebuild profiles or send email.
- The successful background run wrote only PowerShell progress CLIXML to
  stderr (`Preparing modules for first use`), not an application error.
- No email addresses, credentials, tokens, cookie values, or raw measurement
  rows were printed.

### 2026-07-09 - Shared prediction core step 12

Scope:
- Completed step 12 of the shared prediction core plan.
- Added vodomery scoring/profile lookup support for per-identifier selected
  model snapshots, with production behavior still disabled by default.

Changed:
- `score_new_measurements()` can now optionally resolve the source anomaly
  profile from `monitoring.prediction_selected_model_snapshots` for the
  measurement forecast period.
- The optional lookup is controlled by
  `VODOMERY_PER_IDENTIFIER_MODEL_SELECTION_ENABLED`; the default is disabled.
- When enabled, selected per-identifier profile versions affect only expected
  profile values. Inserted anomaly scores still keep the scoring
  `model_version` argument so the current active-model event and alerting
  contract remains intact.
- Missing selected profiles fall back to the global model profile for the same
  measurement slot.
- Added anomaly-scoring tests for default-off behavior and explicit
  per-identifier profile lookup.

Verified:
- `.venv\Scripts\python.exe -m py_compile
  moduly\mereni\vodomery\vodomery_anomaly.py tests\test_anomaly_scoring.py`
  passed.
- `.venv\Scripts\python.exe -m pytest tests\test_anomaly_scoring.py -q
  --tb=short` reported `4 passed`.
- `.venv\Scripts\python.exe -m pytest
  tests\test_scheduler.py::test_quarter_hour_job_scores_all_candidate_models_and_alerts_active_only
  tests\test_scheduler.py::test_weekly_job_rebuilds_profiles_and_sends_report
  tests\test_anomaly_scoring.py tests\test_vodomery_prediction.py
  tests\test_vodomery_model_rebuild_report.py tests\test_prediction_contracts.py
  tests\test_prediction_storage.py tests\test_prediction_backtest.py
  tests\test_vodomery_prediction_adapter.py -q --tb=short` reported
  `60 passed`.

Not verified:
- No live scoring run or weekly rebuild/email was run for step 12.
- Production per-identifier selection remains disabled until checklist step 13.

Follow-up:
- Continue with step 13: enable vodomery per-identifier model selection in
  production after a reviewed dry-run rebuild, keeping the global active model
  as fallback.

### 2026-07-09 - Shared prediction core step 13

Scope:
- Completed step 13 of the shared prediction core plan.
- Enabled vodomery per-identifier model selection for production scoring while
  keeping the global active model as fallback.

Changed:
- Weekly vodomery rebuild now persists selected-model snapshots in `active`
  mode for the next weekly forecast period.
- Per-identifier decision metadata now records `selection_mode=active`.
- `quarter_hour_job`, manual vodomery scoring, and manual vodomery alerting now
  pass `use_per_identifier_selection=True` only when scoring the global active
  vodomery model.
- Non-active vodomery candidate scoring still uses each candidate model's own
  profiles so comparison data remains available.
- The vodomery model rebuild email now explains active per-identifier
  selection and describes the global active model as score-version/fallback,
  not as the only production source profile.
- Added scheduler tests for the active-model-only per-identifier scoring path
  and manual scheduler steps.
- Added DEC-050 clarification and AGENTS context for the new vodomery scoring
  contract.

Verified:
- `.venv\Scripts\python.exe -m py_compile
  moduly\mereni\vodomery\vodomery_prediction.py
  moduly\mereni\vodomery\vodomery_anomaly.py
  moduly\mereni\vodomery\reporting\model_rebuild_report.py
  core\scheduler\scheduler.py tests\test_vodomery_prediction.py
  tests\test_vodomery_model_rebuild_report.py tests\test_scheduler.py`
  passed.
- `.venv\Scripts\python.exe -m pytest tests\test_vodomery_prediction.py
  tests\test_vodomery_model_rebuild_report.py tests\test_anomaly_scoring.py
  tests\test_scheduler.py::test_quarter_hour_job_scores_all_candidate_models_and_alerts_active_only
  tests\test_scheduler.py::test_weekly_job_rebuilds_profiles_and_sends_report
  -q --tb=short` reported `28 passed`.
- `.venv\Scripts\python.exe -m pytest
  tests\test_scheduler.py::test_quarter_hour_job_scores_all_candidate_models_and_alerts_active_only
  tests\test_scheduler.py::test_vodomery_manual_scoring_step_uses_per_identifier_selection_for_active_model
  tests\test_scheduler.py::test_vodomery_manual_alerting_step_uses_per_identifier_selection
  tests\test_scheduler.py::test_weekly_job_rebuilds_profiles_and_sends_report
  -q --tb=short` reported `4 passed`.
- `.venv\Scripts\python.exe -m pytest
  tests\test_scheduler.py::test_quarter_hour_job_scores_all_candidate_models_and_alerts_active_only
  tests\test_scheduler.py::test_vodomery_manual_scoring_step_uses_per_identifier_selection_for_active_model
  tests\test_scheduler.py::test_vodomery_manual_alerting_step_uses_per_identifier_selection
  tests\test_scheduler.py::test_weekly_job_rebuilds_profiles_and_sends_report
  tests\test_anomaly_scoring.py tests\test_vodomery_prediction.py
  tests\test_vodomery_model_rebuild_report.py tests\test_prediction_contracts.py
  tests\test_prediction_storage.py tests\test_prediction_backtest.py
  tests\test_vodomery_prediction_adapter.py -q --tb=short` reported
  `62 passed`.

Not verified:
- No live weekly rebuild/email or live scoring run was performed for step 13.
- The currently running scheduler process will not use the new code until the
  normal runtime reload/restart path loads this working tree.

Follow-up:
- Run a weekly vodomery rebuild with email to persist `active` snapshots for
  the next forecast period and review the delivered report before relying on
  the next scheduled scoring cycle.
- Continue with step 14: generalize forecast-period and rolling-backtest
  handling for both weekly and monthly periods.

### 2026-07-09 15:51 +02:00 - Pre-restart handoff for active vodomery per-identifier scoring

Reason for restart:
- Load the step 13 vodomery prediction changes into the production runtime
  process set through the supported full-workstation restart path.
- After restart, manually run the targeted vodomery model rebuild/report path
  with the new active per-identifier selection setting so the next forecast
  period has `active` selected-model snapshots.
- Do not run the full scheduler `weekly_job` unless the operator explicitly
  wants all weekly side effects and emails; the intended post-restart action is
  the vodomery rebuild plus vodomery model rebuild email.

Current task/conversation state:
- Completed: shared prediction core steps 1 through 13.
- Completed: step 13 makes weekly vodomery rebuild persist selected-model
  snapshots in `active` mode, and scheduler scoring uses per-identifier
  selection only when scoring the global active vodomery model.
- Completed: non-active candidate models still score against their own
  profiles, so ongoing model comparison/backtest data remains available.
- Completed: the vodomery model rebuild email text now describes the global
  active model as score-version/fallback and describes active per-identifier
  selection as the production source-profile choice.
- Verified before this handoff: py_compile passed for changed prediction,
  reporting, scheduler, and test modules; targeted pytest reported `28 passed`,
  focused scheduler pytest reported `4 passed`, and the broader prediction
  selection suite reported `62 passed`.
- Pending: workstation restart, post-restart runtime health verification,
  manual vodomery rebuild/report email, verification that the report arrived,
  and then continuation with shared prediction core step 14.
- First action after restart: verify health/listeners/scheduler state, then run
  the targeted vodomery rebuild/report command from the repository root.

Working tree and deployment:
- `git status --short --untracked-files=all` at handoff time:

```text
 M AGENTS.md
 M DECISIONS.md
 M SESSION_NOTES.md
 M core/scheduler/scheduler.py
 M moduly/mereni/vodomery/database/model_validation.py
 M moduly/mereni/vodomery/database/models.py
 M moduly/mereni/vodomery/reporting/model_rebuild_report.py
 M moduly/mereni/vodomery/vodomery_anomaly.py
 M moduly/mereni/vodomery/vodomery_prediction.py
 M tests/test_anomaly_scoring.py
 M tests/test_scheduler.py
 M tests/test_vodomery_prediction.py
?? PREDICTION_PIPELINE_PLAN.md
?? moduly/mereni/prediction/__init__.py
?? moduly/mereni/prediction/backtest.py
?? moduly/mereni/prediction/contracts.py
?? moduly/mereni/prediction/storage.py
?? moduly/mereni/vodomery/prediction_adapter.py
?? tests/test_prediction_backtest.py
?? tests/test_prediction_contracts.py
?? tests/test_prediction_storage.py
?? tests/test_vodomery_model_rebuild_report.py
?? tests/test_vodomery_prediction_adapter.py
```

- Relevant changed files:
  - Prediction docs and durable context: `PREDICTION_PIPELINE_PLAN.md`,
    `AGENTS.md`, `DECISIONS.md`, `SESSION_NOTES.md`.
  - Shared prediction package: `moduly/mereni/prediction/__init__.py`,
    `backtest.py`, `contracts.py`, `storage.py`.
  - Vodomery adapter, rebuild, scoring, report, and validation:
    `moduly/mereni/vodomery/prediction_adapter.py`,
    `moduly/mereni/vodomery/vodomery_prediction.py`,
    `moduly/mereni/vodomery/vodomery_anomaly.py`,
    `moduly/mereni/vodomery/reporting/model_rebuild_report.py`,
    `moduly/mereni/vodomery/database/models.py`,
    `moduly/mereni/vodomery/database/model_validation.py`.
  - Scheduler integration: `core/scheduler/scheduler.py`.
  - Tests: prediction contracts/storage/backtest/adapter, vodomery prediction,
    rebuild report, anomaly scoring, and scheduler tests.
- Runtime-deployed state before restart:
  - Current time captured before restart: `2026-07-09 15:51 +02:00`.
  - Windows last boot time observed locally: `2026-07-08 09:04:09`.
  - Startup task `API_dashboard_caddy` was `Ready`; last run
    `2026-07-08 09:04:18`, result `0`.
  - Local health checks returned HTTP 200 for FastAPI live, FastAPI ready,
    Streamlit health, and Caddy admin config.
  - Listening ports observed: Caddy on `::80`, `::443`, and
    `127.0.0.1:2019`; FastAPI on `127.0.0.1:8000`; Streamlit on
    `127.0.0.1:8001`; Tailscale-owned interface-specific `443`; no observed
    `8010` or `8011` listeners.
  - The running scheduler/API/dashboard processes may still be old process
    state and have not loaded the step 13 working-tree code until restart.
  - No live step 13 rebuild/email or live scoring run has been performed yet.
  - Root tracked `Caddyfile` is not shown as changed in the handoff git status.

Sensitive/runtime artifacts:
- Do not print, change, delete, or commit `.env` values, ProgramData
  credential files, bearer tokens, cookies, SmartFuelPass session artifacts,
  raw measurement rows, raw device photo paths/files, or account/session data.
- Do not read or restore retired SmartFuelPass JSON cookie/session files.
- Post-restart rebuild/report output may include aggregate model metrics and
  run identifiers, but avoid printing raw per-measurement data.

Expected processes after restart:
- FastAPI/Uvicorn: one production runtime on `127.0.0.1:8000`.
- Streamlit: one production runtime on `127.0.0.1:8001`.
- Scheduler: one `main.py` runtime holding the `scheduler_process` lock.
- Caddy: one runtime owning TCP `80`, TCP `443`, and `127.0.0.1:2019`.
- No temporary `8010` or `8011` listeners unless explicitly started for a
  separate manual check.

Expected application state:
- FastAPI `/health/live`: HTTP 200.
- FastAPI `/health/ready`: HTTP 200 after dashboard table initialization.
- Streamlit `/_stcore/health`: HTTP 200.
- Caddy admin `http://127.0.0.1:2019/config/`: HTTP 200.
- Public HTTP dashboard origin redirects to HTTPS with HTTP 308.
- Public HTTPS dashboard returns HTTP 200 for the Streamlit shell.
- Public `/api/v1/auth/users-exist` returns HTTP 200.
- Public `/api/v1/auth/me` without bearer token returns HTTP 401 JSON.
- Public `/api/v1/map/images` without a valid dashboard image cookie returns
  HTTP 401.
- Public `/docs`, `/redoc`, and `/openapi.json` return HTTP 404 at Caddy.
- Scheduler metrics show a post-boot heartbeat and expected scheduled jobs.
- Change-specific expectation: `rebuild_profiles()` returns
  `selected_model_snapshot_mode == "active"` and writes or confirms active
  selected-model snapshots for the next weekly vodomery forecast period.

Required post-restart checks:
- From the repository root, run `git status --short --untracked-files=all` and
  confirm the dirty worktree is the same expected implementation state.
- Verify local runtime health with safe status-only probes for:
  - `http://127.0.0.1:8000/health/live` -> 200.
  - `http://127.0.0.1:8000/health/ready` -> 200.
  - `http://127.0.0.1:8001/_stcore/health` -> 200.
  - `http://127.0.0.1:2019/config/` -> 200.
- Verify listener state for `80`, `443`, `2019`, `8000`, and `8001`, and
  confirm there are no unexpected temporary listeners on `8010` or `8011`.
- Verify Caddy/auth routing on `https://monitoring.armexholding.cz`:
  - dashboard root -> 200;
  - `/api/v1/auth/users-exist` -> 200;
  - `/api/v1/auth/me` without bearer -> 401;
  - `/api/v1/map/images?layer_id=healthcheck&device_id=healthcheck` without
    cookie -> 401;
  - `/docs`, `/redoc`, `/openapi.json` -> 404;
  - `http://monitoring.armexholding.cz/` -> HTTPS redirect.
- Verify scheduler state through existing safe scheduler metrics or the
  `Health systemu` page: running state, recent heartbeat, and no stale lock.
- Run the targeted vodomery rebuild/report command with the production
  environment, not the full `weekly_job` unless explicitly requested:

```powershell
.venv-production\Scripts\python.exe -c "from moduly.mereni.vodomery.vodomery_prediction import rebuild_profiles; from moduly.mereni.vodomery.reporting import send_vodomery_model_rebuild_report; r=rebuild_profiles(); print('selection_run_id=', r.get('selection_run_id')); print('active_model_version=', r.get('active_model_version')); print('active_model_name=', r.get('active_model_name')); print('selected_model_snapshot_mode=', r.get('selected_model_snapshot_mode')); print('selected_model_snapshot_count=', r.get('selected_model_snapshot_count')); print('rebuild_duration_seconds=', r.get('rebuild_duration_seconds')); print(send_vodomery_model_rebuild_report(r))"
```

- Expected rebuild/report result:
  - `selected_model_snapshot_mode` is `active`.
  - `selected_model_snapshot_count` is positive for a new forecast period; it
    may be `0` only if the same active snapshot period was already inserted and
    immutability conflict handling skipped duplicates.
  - `active_model_version` and `active_model_name` are reported from the actual
    backtest result; do not assume Model 3 without checking the run output.
  - Email delivery returns the configured recipient count and the recipient
    confirms the report arrived.
  - Delivered report contains the active-selection wording, including
    `Aktivni vyber modelu pro dalsi obdobi`.
- Optional aggregate database check after rebuild: count selected snapshots by
  `selection_run_id` and `selection_mode` only; do not print raw identifiers or
  raw measurement rows unless explicitly requested.
- Re-run the targeted tests if the post-restart rebuild reveals any code or
  report issue:

```powershell
.venv\Scripts\python.exe -m pytest tests\test_scheduler.py::test_quarter_hour_job_scores_all_candidate_models_and_alerts_active_only tests\test_scheduler.py::test_vodomery_manual_scoring_step_uses_per_identifier_selection_for_active_model tests\test_scheduler.py::test_vodomery_manual_alerting_step_uses_per_identifier_selection tests\test_scheduler.py::test_weekly_job_rebuilds_profiles_and_sends_report tests\test_anomaly_scoring.py tests\test_vodomery_prediction.py tests\test_vodomery_model_rebuild_report.py tests\test_prediction_contracts.py tests\test_prediction_storage.py tests\test_prediction_backtest.py tests\test_vodomery_prediction_adapter.py -q --tb=short
```

Known risks or accepted gaps:
- The working tree is intentionally dirty with the active prediction pipeline
  implementation; do not revert or clean these changes during restart recovery.
- Restart must preserve uncommitted files and untracked new modules/tests.
- The scheduler startup task launches child processes but does not supervise
  later exits; if a process exits after startup, use the supported recovery
  model rather than ad hoc process replacement unless explicitly approved.
- The manual rebuild can take several minutes; recent comparable rebuilds took
  roughly 12 minutes.
- Active selected-model snapshots do not exist for step 13 until the manual
  post-restart rebuild succeeds, unless another operator has already run it.
- Direct public hostname checks may depend on workstation network/DNS path; if
  a public check fails, compare with local Caddy checks before changing config.
- The task account/elevation model remains the currently accepted operational
  gap and should not be changed as part of this restart.

### 2026-06-25

Scope:
- Added configurable conditional styling for map-layer features.
- Kept existing map-layer and device authorization behavior unchanged.

Changed:
- `Sprava / Mapove vrstvy` now includes a `Zobrazovat na zaklade podminek`
  section that builds `style.conditionalStyle`.
- Conditional style supports one property-based condition with operators
  `equals`, `not_equals`, `is_empty`, and `is_not_empty`.
- The conditional property is automatically added to `property_columns` when
  a layer is created or updated.
- Leaflet rendering now computes style per feature for points, lines, and
  polygons.

Verified:
- `.venv\Scripts\python.exe -m py_compile services\api\services\map_layers.py
  moduly\apps\dashboard\pages\35_mapove_vrstvy.py
  moduly\apps\dashboard\map_shared.py`
- `.venv\Scripts\python.exe -m pytest tests\test_map_layers_service.py
  tests\test_device_map_service.py tests\test_map_routes.py
  tests\test_dashboard_map_shared.py tests\test_dashboard_map_page_layout.py
  tests\test_dashboard_navigation_config.py -q --tb=short` passed 84 tests.
- `git diff --check` reported no whitespace errors, only expected
  LF-to-CRLF warnings.

Not verified:
- Live browser configuration and rendering of a real conditional map layer.

### 2026-06-25 08:20 +02:00 - Post-restart verification for KAMERY map photos

Scope:
- Loaded post-restart state after the `KAMERY` generic map-layer photo fix.
- Checked that new dashboard map layers with `show_photo=True` use the layer
  source table `foto` column for photo availability and image resolution.

Verified:
- Windows last boot time: `2026-06-25 08:08:25 +02:00`.
- Startup scheduled task `API_dashboard_caddy` last ran at
  `2026-06-25 08:08:35 +02:00` with result `0`.
- Listeners present: FastAPI `127.0.0.1:8000`, Streamlit
  `127.0.0.1:8001`, Caddy `80`, `443`, and `127.0.0.1:2019`.
- No temporary listeners on `8010` or `8011`.
- API `/health/live` and `/health/ready`, Streamlit `/_stcore/health`, and
  Caddy admin config endpoint returned HTTP 200.
- Current `dashboard.Map_Layers` metadata has `kamery` with
  `show_photo=True`, source `evidence.KAMERY`, identifier column `označení`,
  and source table columns include both the identifier and `foto`.
- `vodomery` remains the special supported layer that resolves photos through
  the existing device-detail path instead of `evidence.vodoměry.foto`.
- Targeted tests passed:
  `.venv\Scripts\python.exe -m pytest tests\test_device_map_service.py
  tests\test_map_layers_service.py tests\test_map_routes.py
  tests\test_dashboard_map_shared.py -q --tb=short` reported 59 passed.
- `git diff --check` reported no whitespace errors, only expected
  LF-to-CRLF warnings.

Not verified:
- Real authenticated browser click on a `KAMERY` popup photo was not performed
  in this shell session.

Decisions/notes:
- Generic non-Vodomery map layers with `show_photo=True` derive photo
  availability from the trusted source column `foto` and keep the raw photo
  path out of GeoJSON/browser properties.

### 2026-06-25 08:06 +02:00 - Pre-restart handoff after KAMERY map photo fix

Reason for restart:
- User requested saving the conversation state before restarting the Windows
  workstation.
- Restart is expected to reload FastAPI and Streamlit so the generic map-layer
  photo fix becomes active in the running dashboard.

Current task/conversation state:
- Completed: diagnosed that `Mapove podklady / Mapa` photo loading for the new
  `KAMERY` layer failed with `Fotku se nepodarilo nacist.` because map image
  resolution only supported the special Vodomery path through
  `dbo.Zarizeni_vodomery`.
- Completed: kept the existing Vodomery photo path behavior unchanged.
- Completed: added generic support for non-Vodomery layers with
  `show_photo=True`; the image endpoint now resolves the `foto` source column
  server-side from the configured layer table by `identifier_column`.
- Completed: kept raw `foto` paths out of GeoJSON/browser properties.
- Completed: ensured the layer identifier remains available in GeoJSON even if
  the admin configuration omits it from `property_columns`, so popup image
  requests can still call `/api/v1/map/images`.
- Pending: restart/reload runtime processes and verify a real authenticated
  `KAMERY` popup photo in the browser.
- First action after restart: read `AGENTS.md`, `DECISIONS.md`, and
  `SESSION_NOTES.md`; run `git status --short --untracked-files=all`; then
  verify runtime health and the real `KAMERY` map photo flow.

Working tree and deployment:
- Current time captured before restart: `2026-06-25 08:06:44 +02:00`.
- Branch: `master`.
- `HEAD`: `90a352f318f8526541f3da14eca41a0f50916d51`.
- No git commit was created for this handoff.
- `git status --short --untracked-files=all` before this handoff:
  - `M services/api/services/device_map.py`
  - `M tests/test_device_map_service.py`
- Files changed by the latest `KAMERY` map-photo fix:
  - `services/api/services/device_map.py`
  - `tests/test_device_map_service.py`
- Runtime deployment state was not checked in this handoff. Existing running
  FastAPI and Streamlit processes may still be using older code until restart.

Verification already run for the latest `KAMERY` map-photo fix:
- `.venv\Scripts\python.exe -m py_compile services\api\services\device_map.py`
- `.venv\Scripts\python.exe -m pytest tests\test_device_map_service.py
  tests\test_map_layers_service.py tests\test_map_routes.py
  tests\test_dashboard_map_shared.py -q --tb=short` passed 59 tests.
- `git diff --check` reported no whitespace errors, only expected LF-to-CRLF
  warnings.

Sensitive/runtime artifacts:
- Do not print, read, delete, revert, stage, or commit raw values from ignored
  local `.env`, dashboard/API tokens, passwords, cookies, authentication audit
  logs, ProgramData security artifacts, or any local leftover SmartFuelPass
  session JSON files.
- Do not print raw device photo filesystem paths from source columns such as
  `foto`; only inspect safe status codes and non-sensitive headers if
  troubleshooting `/api/v1/map/images`.
- Do not create a production code-integrity baseline from a dirty working tree
  unless the user explicitly approves that exact state.

Expected processes and listeners after restart:
- Windows Task Scheduler runs `API_dashboard_caddy` at system startup and its
  latest run result becomes `0`.
- One rotating-log wrapper owns one non-reload Uvicorn child on
  `127.0.0.1:8000`.
- One rotating-log wrapper owns one Streamlit child on `127.0.0.1:8001`.
- One scheduler runtime runs `main.py`, holds the `scheduler_process` lock,
  and updates `core/scheduler/logs/scheduler_metrics.json`.
- One Caddy runtime owns TCP `80`/`443` and admin `127.0.0.1:2019`.
- No listener should remain on temporary ports `8010` or `8011`.

Expected application state after restart:
- FastAPI `/health/live` and `/health/ready`: HTTP 200 while PostgreSQL is
  available.
- Streamlit `/_stcore/health` and Caddy admin endpoint: HTTP 200.
- HTTP hostname route: HTTP 308 to HTTPS.
- HTTPS dashboard: HTTP 200.
- Protected API without bearer token: HTTP 401 JSON.
- `/api/v1/map/images` without any dashboard cookie: HTTP 401.
- `Mapove podklady / Mapa` should load a `KAMERY` popup photo instead of
  displaying `Fotku se nepodarilo nacist.` when the layer has `show_photo=True`,
  a valid `identifier_column`, and a source `foto` value pointing to an
  accessible image file.

Required post-restart checks:
- Confirm boot time, scheduled-task last run/result/settings, process tree,
  listeners, and no temporary ports `8010` or `8011`.
- Confirm API live/ready, Streamlit health, Caddy admin health, and scheduler
  heartbeat.
- Log in to `https://monitoring.armexholding.cz` without printing cookie or
  token values.
- Open `Mapove podklady / Mapa`, enable/select the `KAMERY` layer, click a
  camera object with a configured photo, and confirm the popup photo loads and
  the lightbox opens.
- If the photo still fails, inspect only the HTTP status and safe headers for
  `/api/v1/map/images`; distinguish 401, 403, 404, and 400 without printing
  cookies, bearer tokens, or raw file paths.
- Re-run targeted tests:
  `.venv\Scripts\python.exe -m pytest tests\test_device_map_service.py
  tests\test_map_layers_service.py tests\test_map_routes.py
  tests\test_dashboard_map_shared.py -q --tb=short`
- Run `git diff --check` and finish with
  `git status --short --untracked-files=all`.
- Append a dated post-restart verification entry with deviations and accepted
  gaps.

Known risks or accepted gaps:
- The real authenticated browser photo flow for `KAMERY` has not yet been
  verified after the generic map-layer photo fix.
- The `KAMERY` layer configuration must use `show_photo=True`, a correct
  `identifier_column`, and a source table containing a `foto` column.
- Current changes are uncommitted and depend on the working tree being
  preserved across restart.
- The current scheduled-task account remains broader than least privilege.
- The launcher does not independently restart a child process that fails after
  startup.

### 2026-06-05

Scope:
- Created persistent context workflow for future sessions.
- Performed read-only baseline review of the project.
- Added approved root documentation files.

Changed:
- Added `AGENTS.md`.
- Added `DECISIONS.md`.
- Added `SESSION_NOTES.md`.

Verified:
- Confirmed the context files did not already exist before writing.
- Checked working tree status before writing.

Not verified:
- No test suite was run for these documentation-only changes.

Decisions/notes:
- The current state is the baseline for future sessions.
- `frontend_next/` is experimental and not currently used in daily operation.
- Existing runtime/data artifacts were intentionally left unchanged.

Follow-up:
- Review cleanup topics only after explicit user approval.

### 2026-06-05

Scope:
- Added the first Streamlit/FastAPI map MVP for the Vodomery dashboard section.
- Added contextual building polygons to the same Leaflet layer control used for base-map switching.
- Investigated dashboard login failure caused by an unresponsive API process on port `8000`.

Changed:
- Added a configurable Streamlit page `vodomery_map`.
- Added FastAPI map endpoints for Vodomery map data.
- Added a map bundle endpoint returning `Vodomery` and `Budovy` layers.
- Added `evidence.BUDOVY` as a contextual polygon overlay with `fid`, `budova`, and `pocet_podlazi` properties.
- Added OSM and CUZK `ORTOFOTO_WM` base-map switching in the Leaflet layer control.
- Set local `.env` `DASHBOARD_API_BASE_URL` to `http://127.0.0.1:8002` because port `8000` is held by an unresponsive process that could not be terminated from the current session.

Verified:
- Targeted map/navigation/API tests passed: `tests\test_dashboard_map_shared.py`, `tests\test_dashboard_navigation_config.py`, and `tests\test_device_map_service.py`.
- Real map service load returned `Vodomery` as 59 `Point` features and `Budovy` as 30 `Polygon` features, both transformed to target SRID `4326`.
- API health checks on `http://127.0.0.1:8002/health/live` and `/health/ready` returned HTTP 200.
- Dashboard API client resolved `DASHBOARD_API_BASE_URL` to `http://127.0.0.1:8002` and `/api/v1/auth/users-exist` returned HTTP 200.

Not verified:
- Full test suite was not run.
- Actual dashboard login with user credentials was not tested.

Decisions/notes:
- Vodomery map data uses `evidence.vodoměry.identifikace` for geometry mapping and enriches details from `dbo.Zarizeni_vodomery.identifikace`.
- Vodomery map page access is controlled through configurable page permission `vodomery_map`.
- The `Budovy` layer is a contextual map layer and is not filtered by device permissions; access is gated by the `vodomery_map` page permission.
- API startup initially failed because `.venv` had `pydantic-core 2.47.0` while `pydantic 2.13.4` requires `pydantic-core 2.46.4`; the local venv was corrected to `pydantic-core 2.46.4`.

Follow-up:
- If the existing Streamlit process still uses the old API URL, restart Streamlit so it reloads `.env`.
- Investigate or terminate the stale process holding port `8000` from the account or privilege level that started it.
- Decide whether the temporary local API port `8002` should remain documented as a workaround or be reverted after port `8000` is released.

### 2026-06-05

Scope:
- Continued the Vodomery map MVP with another contextual evidence layer.
- Added `evidence.MÍSTNOSTI` as a room polygon overlay.
- Drafted the intended cross-layer filtering direction for buildings, floors, rooms, and devices.

Changed:
- Added `MISTNOSTI_MAP_LAYER` using `evidence.MÍSTNOSTI` columns `fid`, `mistnost_id`, `místnost`, `patro`, `budova`, `nájemce`, `popis`, and `plocha`.
- Included map layers in contextual-to-device draw order: `Budovy`, `Místnosti`, `Vodoměry`.
- Added Leaflet styling and popup fields for the `mistnosti` overlay.
- Added a Streamlit map metric for room count.
- Added tests for room GeoJSON serialization, room layer config, endpoint layer ordering, and Leaflet overlay output.

Verified:
- Targeted tests passed: `.venv\Scripts\python.exe -m pytest tests\test_device_map_service.py tests\test_dashboard_map_shared.py tests\test_dashboard_navigation_config.py -v --tb=short`.
- Real map service load returned `Budovy` as 30 `Polygon` features, `Místnosti` as 114 `MultiPolygon` features, and `Vodoměry` as 59 `Point` features, all transformed from source SRID `3857` to target SRID `4326`.

Not verified:
- Full test suite was not run.
- Live Streamlit/browser interaction was not tested.

Decisions/notes:
- The user stated the port `8000` blockage was resolved by restart.
- Contextual layers (`Budovy`, `Místnosti`) remain gated by the `vodomery_map` page permission, not by device permissions.
- Device layers such as `Vodoměry` remain restricted by existing device permissions.

Follow-up:
- Add a server-side map filter request model before broadening the map to more device domains.
- Candidate filters are `layer_ids`, `budova`, `patro`, `mistnost_id`, optional geometry/bbox, and eventually device domain/type.

### 2026-06-05

Scope:
- Started the general map-layer configuration foundation for future `Mapove podklady`.
- Added admin-managed map-layer settings in the `Sprava` area.
- Kept user visibility direction aligned with device permissions and per-layer `map_enabled`.

Changed:
- Added dashboard table model `dashboard.Map_Layers`.
- Added idempotent seed defaults for `budovy`, `mistnosti`, and `vodomery`.
- Added admin FastAPI CRUD endpoints under `/api/v1/admin/map-layers`.
- Added dashboard API client helpers for map-layer administration.
- Added Streamlit admin page `map_layers_admin` at `pages/35_mapove_vrstvy.py`.
- Added configurable metadata to map runtime responses: `layer_kind`, `device_section_key`, `map_enabled`, `default_visible`, `draw_order`, `filter_columns`, `popup_columns`, and `style`.
- Connected existing Vodomery map bundle to enabled layer configs instead of hardcoding every layer directly in the route.
- Updated Leaflet rendering to use configured style, popup columns, and default visibility.

Verified:
- Targeted tests passed: `.venv\Scripts\python.exe -m pytest tests\test_map_layers_service.py tests\test_device_map_service.py tests\test_dashboard_map_shared.py tests\test_dashboard_navigation_config.py -v --tb=short`.
- API app import passed: `.venv\Scripts\python.exe -c "import services.api.main; print('ok')"`.
- Python compile checks passed for changed map/admin modules.
- `git diff --check` reported no whitespace errors, only existing CRLF warnings.

Not verified:
- Full test suite was not run.
- Live admin page interaction in Streamlit was not tested.
- DB bootstrap/seed was not executed manually; it will run through API startup via `ensure_dashboard_tables()`.

Decisions/notes:
- Admins configure layer metadata, not arbitrary SQL.
- Source schema/table/column names are validated through `information_schema`.
- Device layers can be marked `restrict_to_allowed_devices=True` and assigned `device_section_key`, currently seeded for `vodomery`.
- Context layers remain page-gated; device layers remain constrained by assigned devices during feature loading.

Follow-up:
- Add a public/general map API for `Mapove podklady`, separate from `/api/v1/vodomery/map-layers`.
- Add server-side filter request handling for multiselect filters per layer.
- Add a dedicated `Mapove podklady` section and a general `Mapa` page using the layer catalog.

### 2026-06-05

Scope:
- Added the general map API for the future `Mapove podklady` page.
- Added layer catalog and selected-feature loading outside the Vodomery-specific route.
- Added server-side multiselect filter normalization for configured layer filters.

Changed:
- Added `services/api/routes/map.py` with `GET /api/v1/map/layers/catalog` and `POST /api/v1/map/features`.
- Registered the map router in `services/api/main.py`.
- Added map catalog/request schemas in `services/api/schemas/device_map.py`.
- Added dashboard API client helpers `get_map_layer_catalog` and `get_map_features`.
- Added user-level layer availability checks for device layers using `device_section_key`, `restrict_to_allowed_devices`, and assigned devices.
- Added filter support to `load_map_layer_features`; multiple values are loaded with SQL `IN`, multiple filters are combined with `AND`.
- Fixed map-layer seed fallback so disabled DB-configured layers are not reintroduced from defaults.
- Added tests for map route contracts, catalog filtering, device-layer availability, and filter normalization.

Verified:
- Targeted tests passed: `.venv\Scripts\python.exe -m pytest tests\test_map_routes.py tests\test_map_layers_service.py tests\test_device_map_service.py tests\test_dashboard_map_shared.py tests\test_dashboard_navigation_config.py -v --tb=short`.
- Python compile checks passed for changed map/API modules.
- API app import passed: `.venv\Scripts\python.exe -c "import services.api.main; print('ok')"`.
- `git diff --check` reported no whitespace errors, only CRLF warnings.

Not verified:
- Full test suite was not run.
- Live HTTP calls against a running API were not tested.
- DB bootstrap/seed was not executed manually in this step.

Decisions/notes:
- `GET /api/v1/map/layers/catalog` returns only map-enabled layers available to the current authenticated user.
- `POST /api/v1/map/features` accepts per-layer filters; filter keys can use configured source columns or property aliases.
- Unknown filters are rejected server-side instead of silently ignored.
- Device layers remain constrained by assigned devices during feature loading.

Follow-up:
- Build the `Mapove podklady` dashboard section and `Mapa` page against the new catalog/features API.
- Add endpoint or API mode for filter option values, e.g. distinct `budova`, `patro`, `mistnost_id` per layer.
- Replace the Vodomery-specific map page once the general map page is ready.

### 2026-06-05

Scope:
- Added the dashboard entry point for the general map experience.
- Created the `Mapove podklady` section and the configurable `Mapa` page.
- Connected the page to the general map catalog/features API.

Changed:
- Added dashboard section `mapove_podklady` with `requires_device_permissions=False`.
- Added page `mapove_podklady_map` at `pages/36_mapove_podklady.py`.
- Added layer selection UI using the map-layer catalog.
- Added per-layer multiselect filters derived from loaded GeoJSON properties.
- Added final filtered map rendering through the shared Leaflet helper.
- Added shared dashboard map helpers for catalog normalization, feature request creation, and filter option extraction.
- Updated navigation tests and map helper tests.

Verified:
- Targeted tests passed: `.venv\Scripts\python.exe -m pytest tests\test_dashboard_navigation_config.py tests\test_dashboard_map_shared.py tests\test_map_routes.py tests\test_map_layers_service.py -v --tb=short`.
- Python compile checks passed for `pages/36_mapove_podklady.py`, `map_shared.py`, and `navigation_config.py`.
- API app import passed: `.venv\Scripts\python.exe -c "import services.api.main; print('ok')"`.
- `git diff --check` reported no whitespace errors, only CRLF warnings.

Not verified:
- Full test suite was not run.
- Live Streamlit interaction was not tested.
- Live HTTP calls from the page against a running API were not tested.

Decisions/notes:
- The new `Mapove podklady` section does not require device permissions at section level.
- Device-layer availability remains enforced by the general map API and `allowed_devices`.
- Filter options are currently derived from unfiltered selected features; a dedicated distinct-options endpoint remains a follow-up.

Follow-up:
- Add a dedicated filter-options endpoint to avoid loading full unfiltered layers only to populate multiselect values.
- Decide whether to retire or redirect the Vodomery-specific map page after the general map page is validated live.

### 2026-06-05

Scope:
- Removed the obsolete Vodomery-specific map page after the general map page was introduced.
- Adjusted the `Mapove podklady` map layout to prioritize map width and height.

Changed:
- Removed `vodomery_map` from dashboard navigation.
- Removed `pages/34_vodomery_mapa.py`.
- Removed obsolete dashboard API helpers for `/api/v1/vodomery/map-features` and `/api/v1/vodomery/map-layers`.
- Removed obsolete tests for the Vodomery-specific map page and route.
- Narrowed the `Mapove podklady` filter/layer column and widened the map column.
- Increased the rendered map iframe height from 740 px to 900 px and Leaflet map height to 880 px.

Verified:
- Targeted tests passed: `.venv\Scripts\python.exe -m pytest tests\test_dashboard_navigation_config.py tests\test_dashboard_map_shared.py tests\test_map_routes.py tests\test_map_layers_service.py tests\test_device_map_service.py -v --tb=short`.
- Python compile checks passed for the changed dashboard/API map modules.
- API app import passed: `.venv\Scripts\python.exe -c "import services.api.main; print('ok')"`.
- `git diff --check` reported no whitespace errors, only CRLF warnings.

Not verified:
- Full test suite was not run.
- Live Streamlit layout was not checked in a browser.

Decisions/notes:
- Vodomery map display should now go through `Mapove podklady / Mapa`.
- General map API remains the supported path for map layers and filtering.

Follow-up:
- Validate the wider map layout in the running Streamlit UI.

### 2026-06-05

Scope:
- Added server-side distinct filter options for the general `Mapove podklady` map page.
- Removed the need for the page to load full unfiltered GeoJSON layers only to populate multiselects.

Changed:
- Added `POST /api/v1/map/filter-options`.
- Added request/response schemas for map filter options.
- Added service logic for per-layer distinct options with the same access checks as feature loading.
- Added faceted option loading: active filters are applied to other fields while calculating each field's options.
- Added dashboard API/client helpers for filter options.
- Updated `pages/36_mapove_podklady.py` to use the new endpoint before loading filtered map features.
- Added targeted tests for route contracts, service access behavior, and dashboard option normalization.

Verified:
- Python compile passed for the changed map/API/dashboard/test modules.
- Targeted tests passed: `.venv\Scripts\python.exe -m pytest tests\test_map_routes.py tests\test_map_layers_service.py tests\test_dashboard_map_shared.py tests\test_dashboard_navigation_config.py tests\test_device_map_service.py -v --tb=short`.
- API app import passed: `.venv\Scripts\python.exe -c "import services.api.main; print('ok')"`.
- `git diff --check` reported no whitespace errors, only CRLF warnings.

Not verified:
- Full test suite was not run.
- Live Streamlit/browser interaction was not tested.
- Live HTTP calls against a running API were not tested.

Decisions/notes:
- Filter options use catalog filter keys/source columns so the same keys can be sent back in feature filters.
- Device layers remain restricted by assigned devices during both option loading and feature loading.
- No new durable decision was added; this follows DEC-014.

Follow-up:
- Validate the filter UX in the running Streamlit UI with a building/floor/device scenario.

### 2026-06-05

Scope:
- Added photo rendering to map popups for device features.

Changed:
- Updated Leaflet popup HTML generation so `foto` is not rendered as a text table row.
- Added a popup image block for non-empty `properties.foto`.
- Added client-side photo source normalization for URL, relative, Windows drive, and UNC-style paths.
- Added a dashboard map helper test for popup photo rendering.

Verified:
- Python compile passed for `moduly/apps/dashboard/map_shared.py` and `tests/test_dashboard_map_shared.py`.
- Targeted tests passed: `.venv\Scripts\python.exe -m pytest tests\test_dashboard_map_shared.py tests\test_device_map_service.py -v --tb=short`.
- Broader map test set passed: `.venv\Scripts\python.exe -m pytest tests\test_map_routes.py tests\test_map_layers_service.py tests\test_dashboard_map_shared.py tests\test_dashboard_navigation_config.py tests\test_device_map_service.py -v --tb=short`.

Not verified:
- Full test suite was not run.
- Live browser display of local or network photo paths was not tested.

Decisions/notes:
- Empty `foto` values intentionally render nothing.
- If browser security blocks direct local/UNC file paths, add a secured image-serving endpoint or thumbnail proxy in a later step.

Follow-up:
- Validate with real `foto` values in the running Streamlit UI.

### 2026-06-05

Scope:
- Added a secured API image endpoint for map device photos.
- Connected the `Mapove podklady` Leaflet popup to the endpoint.

Changed:
- Added `GET /api/v1/map/images?layer_id=...&identifier=...`.
- Added server-side image resolution for Vodomery device photos from the `foto` detail column.
- Added access checks so image loading respects active map layer availability and assigned device identifiers.
- Added image file validation for supported image suffixes and existing local/UNC-style file paths.
- Added CORS configuration for local dashboard/proxy origins so browser fetch can send `Authorization`.
- Updated popup rendering to fetch images with bearer auth and display blob URLs instead of direct local paths.
- Added tests for image route behavior, service access checks, file validation, and dashboard popup HTML.

Verified:
- Python compile passed for changed API, service, dashboard, and test modules.
- Targeted map test set passed: `.venv\Scripts\python.exe -m pytest tests\test_map_routes.py tests\test_map_layers_service.py tests\test_dashboard_map_shared.py tests\test_dashboard_navigation_config.py tests\test_device_map_service.py -v --tb=short`.
- API app import passed: `.venv\Scripts\python.exe -c "import services.api.main; print('ok')"`.

Not verified:
- Full test suite was not run.
- Live browser loading of real `foto` files was not tested.

Decisions/notes:
- The image endpoint does not accept a file path from the client; it accepts only `layer_id` and `identifier` and resolves the path server-side.
- Default API CORS origins cover local Streamlit `8001` and Caddy/proxy `8080`; override with `API_CORS_ORIGINS` if the dashboard is opened from another origin.

Follow-up:
- Validate with real device photo paths in the running Streamlit UI.

### 2026-06-05

Scope:
- Persisted current map architecture and image proxy context into the project documentation files.

Changed:
- Updated `AGENTS.md` with map API/service/dashboard entry points, map-image safety notes, CORS notes, and the targeted map test command.
- Added `DEC-015` to `DECISIONS.md` for authorized API proxy serving of map device photos.

Verified:
- Documentation files were updated in the working tree.

Not verified:
- No tests were run for documentation-only changes.

Decisions/notes:
- `SESSION_NOTES.md` already contained detailed implementation logs for map layers, filter options, popup photos, and the image endpoint.

Follow-up:
- Use `AGENTS.md`, `DECISIONS.md`, and `SESSION_NOTES.md` as the continuation context in the next session.

### 2026-06-08

Scope:
- Added a monthly consumption report for the JORDAN site.
- Generalized the existing B1 report implementation for reusable site-level meter reports.

Changed:
- Added JORDAN report meters `G_V2`, `Gmt2`, and `G-2.3`.
- Added JORDAN to `monthly_job` and the manual scheduler run registry.
- Added `MONTHLY_JORDAN_CONSUMPTION_REPORT_RECIPIENTS` to `.env.example`.
- Added shared PostgreSQL loaders for water and calorimeter cumulative states and the existing MSSQL electricity total loader.

Verified:
- Targeted report, recipient configuration, and scheduler tests passed.
- Python compile checks passed for the changed report and scheduler modules.
- Read-only dry run for May 2026 found usable start and end states for all three JORDAN meters without printing measurement values or sending email.

Not verified:
- No real email was sent.
- The full test suite was not run.

Decisions/notes:
- Site-level monthly reports use a shared report specification instead of duplicating period, SQL, HTML, and delivery logic.
- The user confirmed that calorimeter `Gmt2` should be displayed in `kWh`.
- Recipient keys are `MONTHLY_B1_CONSUMPTION_REPORT_RECIPIENTS` and `MONTHLY_JORDAN_CONSUMPTION_REPORT_RECIPIENTS` because both reports combine multiple meter domains.

Follow-up:
- None for the JORDAN report.

### 2026-06-09

Scope:
- Investigated stale-looking data on the Streamlit page `Přehled větve`.
- Corrected scheduler-aligned refresh and current-hour chart timestamps.
- Added the cumulative chart Y-axis label while preserving X-axis alignment between both branch graphs.
- Restored authorized Vodoměry photo loading on `Mapové podklady`.

Changed:
- Dashboard refresh now derives the exact `quarter_hour_job` run minutes and refreshes at `:06`, `:17`, `:36`, and `:48`.
- Current incomplete hourly buckets are plotted at the latest actual measurement timestamp.
- The upper cumulative graph uses the Y-axis label `Spotřeba [m³]`.
- The map image resolver translates stored `P:\...` paths to the `\\SERVER1A\Company\...` fallback.
- Vodoměry GeoJSON exposes `has_photo` instead of the raw `foto` path.
- Added and updated targeted tests for refresh timing, chart timestamp alignment, map rendering, and image resolution.

Verified:
- Scheduler and import metrics showed a successful water import on 2026-06-09 and current source measurements.
- Refresh, timestamp helper, and related service tests: 14 passed.
- Related dashboard tests: 24 passed.
- Targeted map tests: 64 passed.
- Read-only map diagnostic returned 59 Vodoměry features, 4 with photos, all 4 resolvable, and no raw photo paths exposed.
- Python compile checks and `git diff --check` passed; only existing line-ending warnings were reported.

Not verified:
- The full pytest suite was not run.
- Live browser rendering after a FastAPI process restart was not verified.

Decisions/notes:
- Dashboard refreshes must follow exact central scheduler slots rather than assume regular quarter-hour spacing.
- Mapped drives are not reliable for service processes; device photo paths are translated server-side.
- Map clients receive photo availability only and load image bytes through the authenticated API endpoint.

Follow-up:
- Restart or reload FastAPI if required, then validate the photo popup in the running `Mapové podklady` page.

### 2026-06-09

Scope:
- Diagnosed the failed map photo load for device `F_V1`.
- Corrected browser routing for authenticated map image requests.

Changed:
- Caddy now routes `/api/*` to FastAPI and all other requests to Streamlit.
- Map image requests default to same-origin `/api/v1/map/images` instead of the server-internal `127.0.0.1:8000` URL.
- Added `DASHBOARD_BROWSER_API_BASE_URL` as an optional override for deployments without same-origin API routing.
- Reloaded the running Caddy configuration.

Verified:
- Server-side resolution for `F_V1` found an existing JPEG.
- Authenticated live request through Caddy returned HTTP 200, `image/jpeg`, and a valid JPEG signature.
- Targeted map tests passed: 44 passed.
- Python compile checks and Caddy validation passed.

Not verified:
- The popup was not clicked in a real remote browser after the change.
- The full pytest suite was not run.

Decisions/notes:
- Same-origin proxying avoids remote-browser localhost failures and removes CORS from the normal Caddy deployment path.

Follow-up:
- Refresh the `Mapove podklady / Mapa` page so Streamlit renders the updated map HTML.

### 2026-06-09

Scope:
- Added a monthly consumption report for water meter `B1_V1`.
- Added Czech business-day scheduling and exact intraday report boundaries.

Changed:
- Added `monthly_b1_v1_consumption_report_job`, scheduled at 13:03 near month end and guarded to run only on the last Czech business day.
- The report interval starts at 13:15 on the previous month's last Czech business day and ends at 13:00 on the current month's last Czech business day.
- The scheduled job refreshes water-meter data before calculating the report.
- Added `MONTHLY_B1_V1_CONSUMPTION_REPORT_RECIPIENTS` with fallback to the existing B1 monthly report recipients.
- Added Czech fixed and Easter holiday handling.

Verified:
- Report, recipient, and scheduler tests passed: 57 tests.
- Read-only dry run for the latest completed interval found start, end, and consumption values for `B1_V1`.
- Effective recipients are configured through the B1 fallback without printing addresses.
- Python compile checks and `git diff --check` passed; only line-ending warnings were reported.

Not verified:
- No email was sent.
- The full test suite was not run.

Decisions/notes:
- Measurements within the requested boundary minute can contain non-zero seconds, so internal cutoffs use the end of the `13:15` and `13:00` minutes while email labels retain the requested minute values.

Follow-up:
- Restart the scheduler process so it loads the new job definition.

### 2026-06-09

Scope:
- Improved photo viewing and usable map space on `Mapove podklady / Mapa`.

Changed:
- Clicking a device photo opens a large lightbox over the map.
- The lightbox can be closed by button, backdrop click, or Escape and offers opening the photo in a new browser tab.
- Removed the page title, explanatory caption, `Vrstvy` heading, and the three map metrics.
- The map now starts at the top of the page beside the layer and filter controls.

Verified:
- Python compile checks passed for the changed dashboard map modules.
- Targeted map and navigation tests passed: 68 map tests after the photo lightbox change and 32 dashboard map/navigation tests after the layout change.
- `git diff --check` reported no whitespace errors, only line-ending warnings.
- The installed Streamlit iframe configuration includes popup permission needed for opening the photo in a new tab.

Not verified:
- Live browser interaction and final visual layout were not tested.
- The full pytest suite was not run.

Decisions/notes:
- Authorized image loading remains unchanged and continues to use the existing FastAPI image proxy and temporary browser blob URLs.
- No durable architectural decision was added.

Follow-up:
- Candidate space improvements are a map fullscreen control, a collapsible layer/filter panel, and viewport-based map height.

### 2026-06-09

Scope:
- Added the mobile optimization pilot for `Overview`, `Vodomery / Prehled`, and `Mapove podklady / Mapa`.
- Added optional display of the phone position in the Leaflet map.

Changed:
- Added shared responsive styles with a `720px` mobile breakpoint.
- Pilot page columns stack on mobile while KPI groups use two columns.
- Overview weather cards and dense headers adapt to narrow screens.
- The mobile map is displayed before its Streamlit filter panel and Leaflet controls use mobile sizing.
- Added a mobile-only `Moje poloha` map control with accuracy circle and permission/error feedback.
- Device location remains browser-only and is not sent to the API.

Verified:
- Python compile checks passed for all changed dashboard modules.
- Responsive, map, navigation, overview, and Vodomery targeted tests passed.
- Full targeted map suite passed: 71 tests.
- Generated map JavaScript passed Chromium syntax validation.
- `git diff --check` reported no whitespace errors, only existing line-ending warnings.

Not verified:
- Live interaction on a physical phone was not tested.
- Geolocation was not tested through a deployed trusted HTTPS origin.
- The full pytest suite was not run.

Decisions/notes:
- Mobile and desktop use the same Streamlit pages; layout changes are CSS responsive rules, not separate page implementations.
- Remote mobile browser geolocation requires HTTPS. The current plain HTTP `:8080` Caddy listener will show an explanatory error instead of requesting location.

Follow-up:
- Configure a trusted HTTPS dashboard origin before validating phone geolocation in production.

### 2026-06-09

Scope:
- Changed the mobile layout order on `Mapove podklady / Mapa`.

Changed:
- The layer selection and layer filters now render above the map on screens up to the shared `720px` breakpoint.
- Removed the obsolete note that said the map was displayed above the filter panel.
- Added a regression test for the mobile column order.

Verified:
- Python compile checks passed for the changed map page and its layout test.
- Targeted responsive, map, and navigation tests passed: 36 tests.
- `git diff --check` reported no whitespace errors, only the existing line-ending warning.

Not verified:
- Live rendering on a physical phone was not tested.
- The full pytest suite was not run.

Decisions/notes:
- Desktop map layout remains unchanged.
- No durable architectural decision was added.

Follow-up:
- None.

### 2026-06-10

Scope:
- Diagnosed mobile geolocation failure on `Mapove podklady / Mapa`.
- Added an HTTPS dashboard entry point required by mobile browser geolocation.

Changed:
- Caddy now serves the dashboard and `/api/*` on HTTPS for `server2a.armex.local`, `server2a`, and `192.168.3.250`.
- HTTPS certificates are issued by the local Caddy CA.
- The public local CA certificate is downloadable from `http://server2a:8080/caddy-local-root.crt`.
- Added a Domain/Private Windows Firewall rule for inbound TCP 443.
- Added a regression test for the HTTPS and CA-download Caddy configuration.

Verified:
- Streamlit 1.57 already delegates `geolocation` to its HTML iframe.
- Caddy validation and reload passed.
- HTTPS dashboard requests through the local proxy returned HTTP 200.
- The CA download returned the expected X.509 certificate response.
- The targeted responsive and map tests passed.

Not verified:
- The CA certificate was not installed and trusted on a physical phone.
- Live geolocation was not tested on a physical phone.
- The full pytest suite was not run.

Decisions/notes:
- Plain LAN HTTP cannot provide browser geolocation; the phone must use the trusted URL `https://server2a.armex.local`.
- Trusting the local Caddy CA is a one-time device setup and does not expose the CA private key.

Follow-up:
- Install and trust `monitoring-dashboard-local-ca.crt` on each phone that needs dashboard geolocation.

### 2026-06-10

Scope:
- Diagnosed failed HTTPS and local CA download URLs.
- Corrected the dashboard HTTPS endpoint to the actual server identity.

Changed:
- Caddy now serves HTTPS for `server4a.armex.local`, `server4a`, and `192.168.3.249`.
- The local CA is available as both `/caddy-local-root.crt` and `/caddy-local-port.crt`.
- The CA download is also exposed over HTTPS on port 443.

Verified:
- The machine identity is `SERVER4A`; `server2a.armex.local` resolves to the unavailable address `192.168.3.250`.
- Caddy validation and reload passed.
- Dashboard and CA download requests returned HTTP 200 through `192.168.3.249`.
- The targeted Caddy configuration test passed.

Not verified:
- Access from a physical phone was not tested.
- TCP 8080 could not be added to Windows Firewall because the current process lacks administrator rights.

Decisions/notes:
- Use `https://192.168.3.249` as the reliable LAN dashboard URL.
- The CA can be downloaded through `https://192.168.3.249/caddy-local-root.crt` after bypassing the initial trust warning.

Follow-up:
- An administrator can allow inbound TCP 8080 if plain-HTTP CA download is still required.

### 2026-06-10 - Restart handoff

Current state:
- The machine is `SERVER4A`, with the monitoring LAN address `192.168.3.249`.
- `server2a.armex.local` incorrectly targets `192.168.3.250` and must not be used for this dashboard.
- Caddy is configured for `server4a.armex.local`, `server4a`, and `192.168.3.249`.
- Caddy was validated and reloaded before the restart.

Verified URLs:
- Dashboard: `https://192.168.3.249`
- Dashboard by name: `https://server4a.armex.local`
- CA download: `https://192.168.3.249/caddy-local-root.crt`
- Compatible CA alias: `https://192.168.3.249/caddy-local-port.crt`
- All URLs returned HTTP 200 locally; TLS verification passed against the Caddy root CA with Windows revocation checking disabled.

Pending after restart:
- Confirm Caddy, FastAPI on `127.0.0.1:8000`, and Streamlit on `127.0.0.1:8001` started.
- Test the dashboard and CA download from the phone.
- Install and trust the downloaded local CA on the phone.
- If plain HTTP download on `http://192.168.3.249:8080/...` is required, create an inbound TCP 8080 firewall rule from an elevated administrator session. The previous attempt failed with Windows error 5 (access denied).

Working tree warning:
- Existing user/runtime changes remain present. Do not revert them.
- Relevant work from this session is in `Caddyfile`, `tests/test_caddy_config.py`, and `SESSION_NOTES.md`.

### 2026-06-10

Scope:
- Added `armex.monitoring` as the preferred HTTPS dashboard hostname.

Changed:
- Added `armex.monitoring` to the Caddy HTTPS site while retaining the existing server-name and IP aliases.
- Updated the Caddy configuration regression test.

Verified:
- Caddy validation and reload passed.
- The targeted Caddy configuration test passed.
- A local HTTPS request for `https://armex.monitoring` returned HTTP 200 with the Caddy root CA.

Not verified:
- `armex.monitoring` does not yet resolve through network DNS.
- Access from another device was not tested.

Decisions/notes:
- Network DNS must map `armex.monitoring` to `192.168.3.249` before other devices can use the new name.
- The internal DNS server is `192.168.3.252` (`server1a.armex.local`); it serves `armex.local`, but no `monitoring` zone currently exists.
- The exact hostname requires a `monitoring` DNS zone with an `armex` A record targeting `192.168.3.249`.
- `main.py` is unrelated to the dashboard hostname and was not changed.

### 2026-06-10

Scope:
- Prepared a step-by-step plan for publishing the dashboard to the public internet over HTTPS.

Changed:
- Added `PUBLIC_HTTPS_DEPLOYMENT.md` with preparation, security, DNS, router, Caddy, verification, rollback, and HTTP shutdown checklists.

Verified:
- The plan reflects the current public IP `77.95.46.168`, internet-facing server address `192.168.2.249`, and localhost-only FastAPI/Streamlit listeners.

Not verified:
- No production DNS, router, firewall, or public Caddy changes were made.

Decisions/notes:
- Tailscale remains the service and rollback access during public HTTPS deployment.
- Public port `8080` must remain only temporarily and be removed after successful HTTPS verification.

### 2026-06-11

Scope:
- Separated Caddy startup from the FastAPI, Streamlit, and scheduler launcher.
- Added the public HTTPS dashboard hostname.

Changed:
- `start_api_dashboard.bat` no longer contains or invokes the Caddy startup branch.
- The launcher now exits after starting Streamlit instead of falling through into a second API invocation.
- Replaced the old LAN/internal-CA Caddy configuration with the single public hostname `monitoring.armexholding.cz`.
- The public site routes `/api/*` to FastAPI and remaining requests to Streamlit.

Verified:
- Added a Caddy configuration regression test for the public hostname and separate API/Streamlit routing.
- Caddy configuration validation passed.
- Local TLS verification for `monitoring.armexholding.cz` returned HTTP 200 for the dashboard.
- Public DNS resolves `monitoring.armexholding.cz` to `77.95.46.168`.

Not verified:
- HTTPS access through the public IP from an external network was not tested; the same-server public-IP request timed out, consistent with unavailable NAT loopback.
- The live Caddy process did not accept the updated configuration because its admin API reload remained blocked and timed out.
- The live `/api/v1/map/layers/catalog` request still returns Streamlit HTTP 200 HTML instead of FastAPI authentication JSON.

Decisions/notes:
- Caddy is now an independently managed runtime process.
- The public dashboard URL is `https://monitoring.armexholding.cz`.
- The independently managed Caddy process must be restarted or successfully reloaded with the project `Caddyfile` before same-origin map API calls work through the public domain.

### 2026-06-11

Scope:
- Moved Caddy runtime ownership back into `start_api_dashboard.bat`.
- Adopted the Caddy installation and runtime configuration under `C:\Program Files\Caddy`.

Changed:
- Added explicit `CADDY_DIR`, `CADDY_EXE`, and `CADDY_CONFIG` paths to the launcher.
- Added preflight checks for the Caddy executable and configuration.
- Added a Streamlit `/_stcore/health` readiness check before Caddy startup.
- Added Caddy configuration validation before both first start and reload.
- Existing Caddy processes are reloaded through `127.0.0.1:2019`; otherwise Caddy runs in the foreground of its launcher window.
- Synchronized the deployed `C:\Program Files\Caddy\Caddyfile` with the tracked project configuration.
- The deployed proxy routes `/api/*` to FastAPI on port `8000` and all remaining traffic to Streamlit on port `8001`.

Verified:
- Caddy 2.11.4 was found at `C:\Program Files\Caddy\caddy.exe`.
- Project and deployed Caddyfile SHA-256 hashes matched after synchronization.
- Runtime Caddy configuration validation passed.
- Caddy was stopped and restarted through `start_api_dashboard.bat caddy`.
- The running command line uses `run --config "C:\Program Files\Caddy\Caddyfile" --adapter caddyfile`.
- Ports 80, 443, and 2019 are owned by the new Caddy process.
- Local TLS checks returned dashboard HTTP 200, unauthenticated API HTTP 401 JSON, and HTTP-to-HTTPS redirect 308.
- Re-running `start_api_dashboard.bat caddy` completed a successful reload without starting a second Caddy process.
- Targeted Caddy configuration and launcher tests passed.

Not verified:
- The complete launcher was not run because FastAPI, Streamlit, and the scheduler were already active and a full run would start duplicate application processes.
- External access from a separate internet connection was not tested.

Decisions/notes:
- DEC-018 supersedes the earlier independent-Caddy decision DEC-017.
- The root `Caddyfile` is the tracked mirror; the launcher reads the deployed copy under `C:\Program Files\Caddy`.

### 2026-06-11 - Restart handoff

Current state before workstation restart:
- `start_api_dashboard.bat` starts FastAPI, scheduler, Streamlit, and then Caddy.
- FastAPI must pass `http://127.0.0.1:8000/health/live`.
- Streamlit must pass `http://127.0.0.1:8001/_stcore/health`.
- Caddy runs from `C:\Program Files\Caddy\caddy.exe`.
- Caddy loads `C:\Program Files\Caddy\Caddyfile`.
- The deployed and tracked project Caddyfile SHA-256 hashes matched before restart.
- Caddy routes `/api/*` to FastAPI on `127.0.0.1:8000` and remaining traffic to Streamlit on `127.0.0.1:8001`.

Expected processes and listeners after restart:
- FastAPI/Uvicorn on `127.0.0.1:8000`.
- Streamlit on `127.0.0.1:8001`.
- Scheduler running `main.py`.
- Caddy from `C:\Program Files\Caddy\caddy.exe` on TCP 80 and 443 with admin endpoint `127.0.0.1:2019`.

Checks for the next session:
- Confirm the four runtime processes started without duplicate instances.
- Confirm `http://127.0.0.1:8000/health/live` returns HTTP 200.
- Confirm `http://127.0.0.1:8001/_stcore/health` returns HTTP 200.
- Confirm `http://monitoring.armexholding.cz` redirects to HTTPS.
- Confirm `https://monitoring.armexholding.cz` returns the Streamlit dashboard.
- Confirm unauthenticated `https://monitoring.armexholding.cz/api/v1/map/layers/catalog` returns FastAPI HTTP 401 JSON rather than Streamlit HTML.
- Confirm Caddy command line uses `run --config "C:\Program Files\Caddy\Caddyfile" --adapter caddyfile`.

Last verified before restart:
- Dashboard HTTPS returned HTTP 200.
- Unauthenticated map API returned HTTP 401 with `application/json`.
- HTTP returned redirect 308 to HTTPS.
- Re-running `start_api_dashboard.bat caddy` successfully reloaded the existing Caddy process.
- Targeted tests passed: `tests/test_caddy_config.py` with 2 tests.

Working tree warning:
- Existing user/runtime changes remain present and must not be reverted.
- Relevant restart work is in `start_api_dashboard.bat`, `Caddyfile`, `tests/test_caddy_config.py`, `AGENTS.md`, `DECISIONS.md`, `PUBLIC_HTTPS_DEPLOYMENT.md`, and `SESSION_NOTES.md`.

### 2026-06-11 - Post-restart runtime verification

Scope:
- Verified the complete runtime after the workstation restart.
- Confirmed the supported public access policy.

Changed:
- Updated persistent context to state that `https://monitoring.armexholding.cz` is the only supported public client entry point.
- Recorded that direct client access through the public IP address is not required or supported.

Verified:
- FastAPI live and ready endpoints on `127.0.0.1:8000` returned HTTP 200.
- Streamlit health on `127.0.0.1:8001` returned HTTP 200.
- The scheduler held its process lock, refreshed its heartbeat, and completed the 2026-06-11 14:16 quarter-hour job successfully.
- The water, gas, and pressure imports executed by that job completed successfully.
- Exactly one persistent Caddy process was running.
- Caddy owned TCP ports 80 and 443 and its admin endpoint on `127.0.0.1:2019`.
- The tracked and deployed Caddyfile SHA-256 hashes matched and the deployed configuration validated successfully.
- HTTP for `monitoring.armexholding.cz` redirected to HTTPS with status 308.
- HTTPS returned the Streamlit dashboard with status 200.
- An unauthenticated `/api/*` request returned FastAPI HTTP 401 JSON rather than Streamlit HTML.
- The served certificate used TLS 1.3, matched `monitoring.armexholding.cz`, had a valid Let's Encrypt chain, and was valid from 2026-06-11 through 2026-09-09.

Not verified:
- Direct access through the public IP address was not treated as a required check.
- External access from a separate internet connection was not tested during this session.

Decisions/notes:
- All public client connections use `https://monitoring.armexholding.cz`.
- DNS still maps the hostname to the public endpoint, but clients do not connect using the IP address as the URL.
- `main.py` remains the scheduler entry point and requires no change for public HTTPS routing.

### 2026-06-11 - Persistent login and dashboard-wide mobile layout

Scope:
- Fixed dashboard logout after a browser reload.
- Extended the existing mobile dashboard behavior from the three-page pilot to all active Streamlit pages.
- Added hot-reload handling for shared authentication and responsive modules in the common dashboard entry point.

Changed:
- Added the shared browser session cookie name in `app/dashboard_session.py`.
- Added FastAPI browser-session endpoints for setting and deleting the authenticated HttpOnly cookie.
- Added HTTP status metadata to `DashboardApiError` so Streamlit can distinguish invalid authentication from temporary API outages.
- Added Streamlit authentication restore, cookie synchronization, logout cleanup, and invalid-token cleanup.
- Applied shared responsive styles globally from `moduly/apps/dashboard/login.py`.
- Expanded responsive CSS for mobile columns, metric grids, tables, charts, images, tabs, forms, dialogs, sidebars, and full-width touch actions.
- Removed duplicate responsive style calls from `Overview`, `Vodomery / Prehled`, and `Mapove podklady / Mapa`.
- Added authentication-route, authentication-state, and responsive-layout regression tests.

Verified:
- Dashboard authentication and navigation tests passed: 29 tests.
- Dashboard-focused tests passed: 105 tests.
- Final targeted responsive, map-layout, and navigation tests passed: 26 tests.
- Python compilation passed for the dashboard package and changed authentication modules.
- Live Streamlit login rendered without `ImportError`.
- Headless Chromium at a `390x844` viewport confirmed mobile page padding, full-width login action, stacked content columns, two-column metric rows, and no JavaScript errors.
- Local FastAPI and Streamlit health endpoints returned HTTP 200.
- Browser-session deletion returned HTTP 204 with `Secure`, `HttpOnly`, and `SameSite=Lax` cookie attributes when `X-Forwarded-Proto` was HTTPS.
- The complete test suite result was 422 passed and 2 failed.

Not verified:
- Authenticated navigation through every dashboard page was not exercised manually on a physical phone.
- External HTTPS access from a separate network was not retested during this work.

Known unrelated test failures:
- `tests/test_vodomery_reports.py::test_build_consumption_curve_day_aggregates_water_measurements`
- `tests/test_vodomery_reports.py::test_build_vodomery_report_html_contains_expected_sections`
- Both failures reproduce when `tests/test_vodomery_reports.py` is run alone and are outside the authentication and responsive-layout changes.

Decisions/notes:
- DEC-020 records persistent dashboard login behavior.
- DEC-021 expands DEC-016 from the mobile pilot to the complete active Streamlit dashboard.
- `main.py` remains only the scheduler entry point and was not changed.

### 2026-06-11 - Dashboard security remediation P0.1

Scope:
- Started the dashboard security checklist with API token signing-key rotation.
- Removed the known development signing secret from tracked runtime launchers.

Changed:
- `start_api_dashboard.bat` now loads `API_TOKEN_SECRET` through application configuration.
- Removed the same fixed secret from `start_api_dashboard - kopie.bat`, `scripts/start_all_services.ps1`, and `run.txt`.
- Generated a new 384-bit random secret in the ignored local `.env`.
- Added `tests/test_dashboard_security_config.py`.
- Added `DASHBOARD_SECURITY_CHECKLIST.md` progress and DEC-022.

Verified:
- The old known signing secret produced a token accepted by the currently running API before rotation.
- A temporary loopback-only FastAPI instance loaded the new `.env` secret and accepted a newly signed token.
- The temporary API instance was stopped and port `18000` was released.
- Security, Caddy, browser-session, auth-state, auth-service, and navigation targeted tests passed: 36 tests.

Not verified:
- The running API on port `8000` could not be restarted because Windows denied terminating its privileged process tree.
- The live API therefore still uses the old signing secret until restarted from its original administrative context or after a workstation restart.
- Live rejection of an old-secret token remains pending after that restart.

Decisions/notes:
- API signing secrets must remain outside version control and must not be assigned by tracked launchers.
- `main.py`, Streamlit, scheduler, and Caddy were not restarted or changed by this step.

Follow-up:
- Restart FastAPI or the workstation, then verify health, a new token, and HTTP 401 for an old-secret token.

### 2026-06-11 - Security P0.1 restart handoff

Current state before workstation restart:
- The tracked launchers no longer assign `API_TOKEN_SECRET`.
- The previous known development secret is absent from tracked runtime files.
- A new 384-bit random `API_TOKEN_SECRET` is stored in the ignored local `.env`; its value was not printed or added to tracked documentation.
- A temporary FastAPI instance on `127.0.0.1:18000` successfully loaded the new secret and validated a newly signed token.
- The temporary instance was stopped and port `18000` was released.
- The existing privileged FastAPI process on `127.0.0.1:8000` could not be terminated from the current session.
- Immediately before restart, the live API and Streamlit health endpoints returned HTTP 200.
- Immediately before restart, the live API still accepted a token signed with the old known secret.

Expected state after restart:
- `start_api_dashboard.bat` starts FastAPI without assigning a secret in the launcher.
- FastAPI loads `API_TOKEN_SECRET` from the ignored local `.env`.
- Tokens signed with the old known secret fail signature validation with HTTP 401.
- Users must log in again because existing browser bearer tokens were signed with the previous secret.

Required post-restart checks:
- Confirm FastAPI health at `http://127.0.0.1:8000/health/live`.
- Confirm Streamlit health at `http://127.0.0.1:8001/_stcore/health`.
- Confirm public HTTPS dashboard access at `https://monitoring.armexholding.cz`.
- Confirm a fresh dashboard login succeeds and persists across a browser reload.
- Confirm an old-secret test token returns HTTP 401 from `/api/v1/auth/me`.
- Update `DASHBOARD_SECURITY_CHECKLIST.md` P0.1 restart and old-token verification items to completed.

Verification already completed:
- Targeted security, Caddy, browser-session, auth-state, auth-service, and navigation tests: 36 passed.
- `git diff --check` reported no whitespace errors.

Files changed for security P0.1:
- `start_api_dashboard.bat`
- `start_api_dashboard - kopie.bat`
- `scripts/start_all_services.ps1`
- `run.txt`
- `tests/test_dashboard_security_config.py`
- `DASHBOARD_SECURITY_CHECKLIST.md`
- `PUBLIC_HTTPS_DEPLOYMENT.md`
- `DECISIONS.md`
- `SESSION_NOTES.md`

### 2026-06-12 - Security P0.1 post-restart completion

Scope:
- Verified the complete runtime after restart.
- Completed the API signing-key rotation checks.

Changed:
- Marked the remaining P0.1 checklist items as completed.

Verified:
- FastAPI live and ready endpoints returned HTTP 200.
- Streamlit health returned HTTP 200.
- A token issued with the current `.env` secret returned HTTP 200 from `/api/v1/auth/me`.
- A token signed with the previous known secret returned HTTP 401 because its signature did not match.
- Caddy returned the Streamlit dashboard over local public-hostname TLS and routed protected `/api/*` traffic to FastAPI.
- The scheduler process lock was held, its heartbeat was current, and the 2026-06-12 06:35 quarter-hour job completed successfully with no new scheduler errors after restart.

Not verified:
- Public HTTPS was not tested from a separate external network because this server does not have NAT loopback.
- A credential-based browser login was not automated because no user password was read or requested.

Decisions/notes:
- P0.1 is complete.
- P0.2 must not apply HTTP Basic Auth to all `/api/*` requests because FastAPI uses the same `Authorization` header for bearer tokens.

### 2026-06-12 - Dashboard security remediation P0.2

Scope:
- Added a temporary second authentication gate at Caddy.
- Restricted unrestricted access to Streamlit and the public login endpoint.

Changed:
- Added scoped Caddy Basic Auth for all non-`/api/*` paths and
  `/api/v1/auth/login`.
- Added local Caddy auth env loading to `start_api_dashboard.bat`.
- Added `scripts/deploy_caddy_runtime.ps1` with validation, timestamped backup,
  reload, and automatic rollback on deployment failure.
- Added Caddy and launcher regression checks.
- Documented credentials, deployment, emergency access, and rollback.
- Added DEC-023.

Runtime state:
- Caddy username and bcrypt hash are stored outside Git in
  `C:\ProgramData\monitorovaci_platforma\caddy-dashboard-auth.env`.
- The plaintext credential handoff is stored in
  `C:\ProgramData\monitorovaci_platforma\dashboard-proxy-credentials.txt`.
- Both files and their parent directory allow access only to the operating
  account, Administrators, and SYSTEM.
- The credential value was not printed in command output or documentation.

Verified:
- Project and deployed Caddyfile SHA-256 hashes match.
- The deployed configuration validates with the local auth env file.
- Caddy reloaded successfully and remained a single process on ports 80, 443,
  and the loopback admin endpoint 2019.
- Dashboard requests without credentials and with invalid credentials returned
  HTTP 401.
- A dashboard request with valid credentials returned HTTP 200 HTML.
- `/api/v1/auth/login` without gate credentials returned HTTP 401.
- A gated login request reached FastAPI and returned HTTP 422 JSON for an empty
  test payload.
- An unauthenticated protected Bearer API route remained FastAPI HTTP 401 JSON.
- FastAPI live/ready and Streamlit health endpoints remained HTTP 200.

Not verified:
- Access was not tested from a separate external network.
- Browser credential prompting and WebSocket behavior were not exercised
  manually in a graphical browser.

Decisions/notes:
- P0.2 uses the additional reverse-proxy authentication option.
- Tailscale remains the emergency access path.
- Remove the temporary gate only after P1 login throttling is complete.

### 2026-06-12 - Security P0 restart handoff

Current state before workstation restart:
- Security checklist items P0.1 and P0.2 are completed.
- FastAPI uses the rotated `API_TOKEN_SECRET` from the ignored local `.env`.
- Tokens signed with the previous development secret are rejected with HTTP 401.
- Caddy requires temporary shared authentication for the Streamlit surface and
  `/api/v1/auth/login`.
- Other `/api/*` routes remain under FastAPI Bearer authentication and are not
  placed behind the Caddy Basic Auth gate.
- The tracked and deployed Caddyfile SHA-256 hashes match.
- At 2026-06-12 08:27 CEST, the scheduler heartbeat was current, the latest
  quarter-hour status was `success`, and the next run was scheduled for 08:35.

Sensitive local runtime files:
- `C:\ProgramData\monitorovaci_platforma\caddy-dashboard-auth.env` contains the
  Caddy username and bcrypt hash.
- `C:\ProgramData\monitorovaci_platforma\dashboard-proxy-credentials.txt`
  contains the plaintext operational credential handoff.
- Do not print, commit, move, or delete these files.
- Their ACL permits only the operating account, Administrators, and SYSTEM.

Expected startup behavior:
- `start_api_dashboard.bat` starts FastAPI, scheduler, and Streamlit.
- After both health checks pass, it starts or reloads Caddy.
- The launcher reads the Caddy gate settings from
  `C:\ProgramData\monitorovaci_platforma\caddy-dashboard-auth.env`.
- Missing or incomplete Caddy auth settings must stop Caddy startup rather than
  expose the dashboard without the temporary gate.

Required post-restart checks:
- Confirm one FastAPI/Uvicorn listener on `127.0.0.1:8000`.
- Confirm one Streamlit listener on `127.0.0.1:8001`.
- Confirm one scheduler instance holds the `scheduler_process` lock and has a
  current heartbeat.
- Confirm one Caddy process owns TCP 80, 443, and loopback admin port 2019.
- Confirm FastAPI `/health/live` and `/health/ready` return HTTP 200.
- Confirm Streamlit `/_stcore/health` returns HTTP 200.
- Confirm tracked and deployed Caddyfile hashes still match.
- Confirm HTTP redirects to HTTPS with status 308.
- Confirm HTTPS dashboard access without gate credentials returns HTTP 401 with
  a Basic authentication challenge.
- Confirm valid gate credentials return the Streamlit dashboard with HTTP 200.
- Confirm `/api/v1/auth/login` without gate credentials returns HTTP 401.
- Confirm valid gate credentials allow the login request to reach FastAPI.
- Confirm an unauthenticated protected non-login `/api/*` route returns FastAPI
  HTTP 401 JSON, not a Caddy Basic Auth response or Streamlit HTML.

Verification completed before restart:
- Targeted Caddy, security, authentication, and navigation suite: 37 passed.
- FastAPI live/ready and Streamlit health endpoints returned HTTP 200.
- Caddy configuration validation and reload passed.
- Live gate checks passed for missing, invalid, and valid credentials.
- `git diff --check` reported no whitespace errors.

Working tree at handoff:
- Security work remains uncommitted in `AGENTS.md`, `Caddyfile`,
  `DASHBOARD_SECURITY_CHECKLIST.md`, `DECISIONS.md`,
  `PUBLIC_HTTPS_DEPLOYMENT.md`, `SESSION_NOTES.md`,
  `start_api_dashboard.bat`, `tests/test_caddy_config.py`,
  `tests/test_dashboard_security_config.py`, and
  `scripts/deploy_caddy_runtime.ps1`.
- `data/smartfuelpass/session_cookies.json` is a separate sensitive runtime
  change and must not be inspected, reverted, or included with security work
  without explicit approval.

Next security step:
- Continue with P1.3, login throttling and abuse protection.
- Preserve the temporary Caddy gate until application-level throttling is
  implemented and verified.

### 2026-06-12 - Application login throttling and Caddy gate removal

Scope:
- Restored the standard Streamlit login flow without a browser Basic Auth
  prompt.
- Replaced the temporary Caddy gate with FastAPI login throttling.

Changed:
- Added process-local login limits by normalized account and trusted client IP.
- Added increasing temporary account lockouts and a bounded IP lockout.
- Added generic authentication failures and dummy PBKDF2 work for unknown
  accounts.
- Restricted Uvicorn forwarded-header trust to loopback Caddy.
- Removed Caddy gate directives and gate environment loading from the launcher
  and deployment script.
- Added DEC-024 and marked P1.3 complete.

Verified:
- Targeted login, authentication, Caddy, security, responsive-layout, and
  navigation tests: 55 passed.
- Python compilation passed for the changed authentication modules.
- The tracked Caddy configuration validated successfully.
- `git diff --check` reported no whitespace errors.
- The tracked and deployed Caddyfile hashes match after deployment.
- Public HTTPS returns the Streamlit page with HTTP 200 and no Basic Auth
  challenge.
- An empty public login request reaches FastAPI and returns HTTP 422 JSON.
- A validly encoded invalid login returns the generic HTTP 401 response.
- Live attempts 1-4 for a disposable account returned HTTP 401; attempt 5
  returned HTTP 429 with `Retry-After: 30`.
- Protected non-login API routes remain FastAPI HTTP 401 JSON.
- FastAPI live/ready and Streamlit health endpoints remain HTTP 200.

Not verified:
- Credential-based dashboard login was not automated because no dashboard
  password was read or requested.

Decisions/notes:
- DEC-024 supersedes the temporary gate decision DEC-023.
- Retired ProgramData gate credential files remain sensitive and were not
  deleted.

### 2026-06-12 - Windows scheduled startup operating constraint

Scope:
- Recorded how the production runtime starts and how it must currently be
  renewed after operational changes.

Changed:
- Added DEC-025.
- Updated `AGENTS.md`, `PUBLIC_HTTPS_DEPLOYMENT.md`, and
  `DASHBOARD_SECURITY_CHECKLIST.md` with the scheduled-start and recovery
  contract.

Decisions/notes:
- Windows Task Scheduler launches `start_api_dashboard.bat` with the trigger
  `At system startup`.
- FastAPI, Streamlit, the scheduler, and Caddy therefore start without a user
  logging into Windows.
- These processes run in a non-interactive session and their console windows
  cannot be accessed later.
- The current supported way to renew the complete production runtime is to
  restart the whole Windows workstation.
- Future agents must not start a duplicate runtime set manually or assume that
  individual scheduled processes can be safely restarted from an interactive
  session.
- Launcher and startup-argument changes require a workstation restart before
  the scheduled runtime uses them.

### 2026-06-12 - Mandatory restart handoff workflow

Scope:
- Added a mandatory state-preservation workflow before every Windows
  workstation restart.

Changed:
- Added DEC-026.
- Added the `Restart Handoff Template` to `SESSION_NOTES.md`.
- Updated operating instructions, deployment documentation, and the security
  checklist.

Decisions/notes:
- Before every restart, the active conversation/task state and expected
  post-restart process state must be written to `SESSION_NOTES.md`.
- The handoff must include the dirty working tree, runtime deployment state,
  sensitive artifacts, expected processes/listeners, scheduler state, Caddy
  state, exact HTTP expectations, and change-specific verification.
- A restart must not be initiated or requested before the handoff is complete.
- Actual post-restart verification and deviations must be appended afterward.

### 2026-06-12 09:23 CEST - Pre-restart handoff

Reason for restart:
- Renew the complete production runtime through the supported Windows
  Task Scheduler startup path.
- Ensure the scheduled runtime loads the current `start_api_dashboard.bat`,
  including trusted loopback proxy-header arguments, current login throttling,
  and the Caddy configuration without the retired Basic Auth gate.

Current task/conversation state:
- Completed API signing-secret rotation and old-token rejection.
- Removed the temporary Caddy Basic Auth browser prompt.
- Restored the standard Streamlit dashboard login.
- Added application login throttling by normalized account and trusted client
  IP, generic authentication errors, and dummy PBKDF2 verification for unknown
  users.
- Added DEC-024, DEC-025, and DEC-026.
- Documented Windows Task Scheduler startup and the mandatory restart handoff
  workflow.
- Pending: perform all checks below after restart and record actual results.
- First action after restart: read `AGENTS.md`, `DECISIONS.md`, and
  `SESSION_NOTES.md`, run `git status --short`, then execute the post-restart
  checks in this handoff.
- After successful verification, continue the dashboard security checklist;
  the next unfinished authentication item is P1.4 audit logging and alerts.

Working tree and deployment:
- `git status --short` immediately before restart:

```text
 M AGENTS.md
 M Caddyfile
 M DASHBOARD_SECURITY_CHECKLIST.md
 M DECISIONS.md
 M PUBLIC_HTTPS_DEPLOYMENT.md
 M SESSION_NOTES.md
 M data/smartfuelpass/session_cookies.json
 M moduly/apps/dashboard/api_client.py
 M moduly/apps/dashboard/auth.py
 M moduly/apps/dashboard/database/users.py
 M moduly/apps/dashboard/login.py
 M services/api/routes/auth.py
 M start_api_dashboard.bat
 M tests/test_auth_routes.py
 M tests/test_caddy_config.py
 M tests/test_dashboard_auth_service.py
 M tests/test_dashboard_auth_state.py
 M tests/test_dashboard_security_config.py
?? scripts/deploy_caddy_runtime.ps1
?? services/api/core/login_throttle.py
?? tests/test_login_throttle.py
```

- Security/login/runtime changes remain uncommitted.
- `data/smartfuelpass/session_cookies.json` is a separate sensitive runtime
  change. Do not inspect, revert, delete, print, or include it with the
  security work without explicit approval.
- The tracked root `Caddyfile` is deployed to
  `C:\Program Files\Caddy\Caddyfile`.
- Tracked and deployed Caddyfile SHA-256 before restart:
  `F41D3B31EA03308CB4345B1D11F0488B11D1FE527CBF135B0E1E166E5E7BC9BE`.
- The deployed Caddy configuration validated successfully before restart.
- Targeted login, authentication, Caddy, security, responsive-layout, and
  navigation tests passed: 55 tests.
- `git diff --check` reported no whitespace errors.

Sensitive/runtime artifacts:
- Do not print, change, delete, or commit the ignored local `.env` containing
  `API_TOKEN_SECRET`.
- Do not print, change, delete, or commit
  `data/smartfuelpass/session_cookies.json`.
- The retired files
  `C:\ProgramData\monitorovaci_platforma\caddy-dashboard-auth.env` and
  `C:\ProgramData\monitorovaci_platforma\dashboard-proxy-credentials.txt`
  remain sensitive even though Caddy no longer uses them.
- Do not print bearer tokens, passwords, cookie values, or raw operational
  data during verification.

Windows scheduled startup expectation:
- Scheduled task name: `API_dashboard_caddy`.
- Executable:
  `C:\Users\tra\PycharmProjects\monitorovaci_platforma\start_api_dashboard.bat`.
- Trigger: Windows boot (`MSFT_TaskBootTrigger`, `At system startup`).
- Principal: user `tra`, password logon type, highest run level.
- The task starts the runtime without an interactive Windows login.

Expected processes and listeners after restart:
- One FastAPI/Uvicorn runtime owns the single listener
  `127.0.0.1:8000`. Uvicorn reload mode may create a parent/child process tree,
  but there must be only one listener.
- One Streamlit runtime owns the single listener `127.0.0.1:8001`.
- One scheduler runtime runs `main.py`, holds the `scheduler_process` lock,
  and updates `core/scheduler/logs/scheduler_metrics.json`.
- One Caddy runtime from `C:\Program Files\Caddy\caddy.exe` owns TCP 80 and
  443 plus the loopback admin endpoint `127.0.0.1:2019`.
- Tailscale may separately own its Tailscale-interface port 443 listeners; this
  is expected and is not a duplicate public Caddy listener.

Expected application state after restart:
- FastAPI `/health/live`: HTTP 200 JSON.
- FastAPI `/health/ready`: HTTP 200 JSON.
- Streamlit `/_stcore/health`: HTTP 200.
- Scheduler metrics report `scheduler_running=true`, a heartbeat no older than
  the configured 300-second TTL, and no duplicate process lock owner.
- Before restart, the last `quarter_hour_job` run was
  `2026-06-12T09:16:07.877981`, status `success`, with 0 failures in 24 hours;
  the pre-restart next run was `2026-06-12T09:35:05+02:00`. After restart,
  confirm the next applicable scheduled slot and at least one successful job.
- The tracked and deployed Caddyfile hashes remain equal to the SHA-256 above.
- The deployed Caddy configuration validates.
- `http://monitoring.armexholding.cz` returns HTTP 308 to HTTPS.
- `https://monitoring.armexholding.cz` returns the Streamlit page with HTTP 200
  and no `WWW-Authenticate` Basic challenge or browser credential popup.
- An unauthenticated protected non-login `/api/*` route returns FastAPI HTTP
  401 JSON, not Streamlit HTML.
- `/api/v1/auth/login` reaches FastAPI directly.
- A validly encoded invalid login returns generic HTTP 401 JSON without account
  enumeration detail.
- A disposable test account returns HTTP 429 with `Retry-After` on the fifth
  failed attempt; do not use a real dashboard account for this test.
- A real dashboard credential login should be tested manually by the user;
  no password should be read or requested by the agent.

Required post-restart checks:
- Confirm scheduled task startup completed and no duplicate listeners exist.
- Confirm listeners on 8000, 8001, 80, 443, and 2019 match the expectations.
- Confirm FastAPI live/ready and Streamlit health endpoints.
- Confirm scheduler lock, heartbeat, latest status, and next run.
- Confirm tracked/runtime Caddyfile hash equality and configuration validation.
- Confirm HTTP 308, HTTPS dashboard 200 without Basic challenge, and protected
  API 401 JSON.
- Confirm generic invalid-login response and disposable-account throttling.
- Confirm the working tree still contains the expected uncommitted changes and
  no files were lost or unexpectedly modified by startup.
- Append a dated post-restart verification entry with all results and
  deviations.

Known risks or accepted gaps:
- Uvicorn production startup still uses `--reload`; removal remains P2.13.
- Login throttle state is process-local and resets on restart; production
  currently uses one API worker.
- External access from a separate network and a real credential-based browser
  login have not been automated.
- The complete pytest suite was not rerun; the targeted security/dashboard set
  passed 55 tests.

### 2026-06-12 09:52 CEST - Post-restart verification

Scope:
- Verified the scheduled production runtime after the workstation restart
  requested in the 09:23 CEST handoff.

Verified:
- Scheduled task `API_dashboard_caddy` ran at 09:25:23 with result `0`, uses a
  boot trigger, and points to the tracked `start_api_dashboard.bat`.
- FastAPI listens only on `127.0.0.1:8000`, Streamlit only on
  `127.0.0.1:8001`, and one Caddy runtime owns public TCP 80/443 plus
  `127.0.0.1:2019`. Separate Tailscale-interface 443 listeners remain expected.
- FastAPI live/ready and Streamlit health endpoints returned HTTP 200.
- The scheduler process lock was held. Metrics reported a running scheduler,
  a current heartbeat, and a successful first post-restart
  `quarter_hour_job` at 09:35:08 with zero failures in 24 hours.
- Tracked and deployed Caddyfile SHA-256 values both equal
  `F41D3B31EA03308CB4345B1D11F0488B11D1FE527CBF135B0E1E166E5E7BC9BE`.
- The deployed Caddy configuration validated successfully.
- HTTP returned 308 to HTTPS. HTTPS returned the Streamlit page with HTTP 200
  and no Basic Auth challenge.
- An unauthenticated protected API route returned FastAPI HTTP 401 JSON.
- A validly encoded invalid login returned the generic HTTP 401 response.
- A disposable account returned HTTP 401 on attempts 1-4 and HTTP 429 with
  `Retry-After: 30` on attempt 5.
- The working tree still contained the expected pre-restart changes; no
  tracked file was lost or unexpectedly modified by startup.

Not verified:
- Public access from a separate external network was not tested because the
  server does not have NAT loopback.
- A real credential-based browser login was not automated or requested.

Deviations:
- None. A second Caddy process observed during parallel inspection was the
  short-lived `caddy validate` command; only one Caddy process owned listeners.

### 2026-06-12 - Authentication audit logging and alerts

Scope:
- Completed dashboard security checklist item P1.4.

Changed:
- Added structured authentication audit logging with daily rotation and
  90-backup retention.
- Added internal login reason categories while preserving one generic external
  authentication failure response.
- Added audit events for login success/failure/throttling, password changes,
  token revocation, administrator password resets, role changes, activation
  changes, account creation, and account deletion.
- Added the same account/password/role/activation audit coverage to the
  supported local user-management CLI.
- Added warning events for account brute force, IP password spraying, and
  repeated administrator-account failures.
- Added DEC-027 and documented the protected audit path and thresholds.

Runtime state:
- The default audit file is
  `C:\ProgramData\monitorovaci_platforma\logs\auth_audit.jsonl`.
- Its ACL allows only SYSTEM, Administrators, and `ARMEX\tra`.
- A live disposable-account test produced five failed-login records and one
  `account_brute_force` warning record.
- The disposable test password was absent from the matching JSONL records.

Verified:
- Authentication-audit, admin-audit, CLI-audit, auth-route, login-throttle,
  auth-state, security-config, Caddy, navigation, and responsive-layout tests
  passed: 65 tests.
- Python compilation passed for all changed authentication and admin modules.
- FastAPI live and ready endpoints remained HTTP 200 after Uvicorn reloaded the
  changed source.

Not verified:
- A successful real-user login audit was not tested because no dashboard
  password was read or requested.
- Live IP password-spray and administrator-account alert thresholds were not
  triggered to avoid blocking the production source IP or touching a real
  administrator account; both are covered by unit tests.

### 2026-06-12 - Password policy hardening

Scope:
- Completed dashboard security checklist item P1.5.

Changed:
- Added one shared password validator for administrator creation/reset,
  self-service changes, local CLI management, Streamlit forms, and the
  database password-write boundary.
- Added a tracked local common/compromised password blocklist including
  deployment-specific expected values.
- Required 15 to 1024 characters while preserving Unicode, spaces, long
  passphrases, password-manager values, and paste.
- Added Unicode NFC normalization before password hashing.
- Increased PBKDF2-HMAC-SHA256 from 390,000 to 600,000 iterations.
- Added transparent rehash of older valid PBKDF2 hashes after successful login
  without incrementing token version or requiring a bulk reset.
- Changed the bootstrap CLI to use a hidden password prompt when `--password`
  is omitted.
- Added DEC-028 and deployment documentation.

Verified:
- Password-policy, blocklist, Unicode normalization, work-factor, legacy
  verification, automatic rehash, admin create/reset, self-service, CLI, UI
  wiring, authentication, audit, Caddy, navigation, and responsive tests
  passed: 84 tests.
- The full test suite passed 471 of 473 tests.
- FastAPI application import and Python compilation of changed modules passed.
- On this workstation, 600,000-iteration PBKDF2 hashing took approximately
  0.126 seconds and verification approximately 0.132 seconds.
- FastAPI live/ready, Streamlit health, and the public invalid-login path
  remained operational after Uvicorn reloaded the change.

Not verified:
- No real dashboard user password was read, changed, or used for login.
- Existing production hash iteration counts were not enumerated because
  migration occurs safely on successful login and raw password hashes remain
  sensitive.
- Two full-suite failures reproduce independently in
  `tests/test_vodomery_reports.py`: the day consumption curve expectation and
  an outdated report-heading expectation. P1.5 did not change vodomery report
  code or tests, so those failures were left outside this security task.

### 2026-06-12 11:43 CEST - Pre-restart handoff

Reason for restart:
- Renew the complete production runtime through the supported Windows
  Task Scheduler boot path.
- Verify dashboard security checklist item P1.5 from a cold application start,
  including the shared password policy, 600,000-iteration PBKDF2 hashes, and
  compatible legacy-hash handling.

Current task/conversation state:
- Completed and committed P1.5 password policy hardening in commit
  `ff7513d` (`security check P1.5 hotovo`).
- P1.5 code, tests, checklist, DEC-028, and deployment documentation are
  complete.
- Pending: restart Windows, run all checks below, and append a dated
  post-restart verification entry with any deviations.
- First action after restart: read `AGENTS.md`, `DECISIONS.md`, and
  `SESSION_NOTES.md`, then run `git status --short`.

Working tree and deployment:
- `git status --short --untracked-files=all` was empty before this handoff.
- At restart, the only expected uncommitted change is this appended
  `SESSION_NOTES.md` handoff.
- Relevant deployed source is commit `ff7513d`; no Caddy configuration was
  changed by P1.5.
- Tracked and deployed Caddyfile SHA-256 values both equal
  `F41D3B31EA03308CB4345B1D11F0488B11D1FE527CBF135B0E1E166E5E7BC9BE`.
- `C:\Program Files\Caddy\Caddyfile` validated successfully immediately before
  restart.
- Scheduled task `API_dashboard_caddy` was `Ready`; its last run was
  2026-06-12 09:25:23 CEST with result `0`. It has a boot trigger, runs as
  user `tra` with highest run level, and executes the tracked
  `start_api_dashboard.bat`.

Sensitive/runtime artifacts:
- Do not print, change, delete, or commit the ignored local `.env` containing
  `API_TOKEN_SECRET`.
- Do not inspect, print, change, delete, or commit
  `data/smartfuelpass/session_cookies.json` or other browser session data.
- Do not print raw authentication audit records from
  `C:\ProgramData\monitorovaci_platforma\logs\auth_audit.jsonl`.
- The retired ProgramData Caddy gate credential files remain sensitive and
  must not be printed, changed, or deleted.
- Do not read or request real dashboard passwords, bearer tokens, cookies, or
  stored password hashes during verification.

Expected processes and listeners after restart:
- One FastAPI/Uvicorn runtime owns the single listener
  `127.0.0.1:8000`. Reload mode may create a parent/child process tree, but
  there must be only one listener.
- One Streamlit runtime owns the single listener `127.0.0.1:8001`.
- One scheduler runtime runs `main.py`, holds the `scheduler_process` lock,
  and updates `core/scheduler/logs/scheduler_metrics.json`.
- One Caddy runtime from `C:\Program Files\Caddy\caddy.exe` owns TCP 80 and
  443 plus `127.0.0.1:2019`.
- Tailscale may separately own its interface-specific TCP 443 listeners; that
  is expected and is not a duplicate public Caddy listener.

Expected application state:
- FastAPI `/health/live` and `/health/ready`: HTTP 200.
- Streamlit `/_stcore/health`: HTTP 200.
- Scheduler reports `scheduler_running=true`, holds the process lock, and has
  a heartbeat no older than the configured 300-second TTL.
- Immediately before restart, `quarter_hour_job` last ran successfully at
  `2026-06-12T11:35:08.501241`, had 0 failures and 96 successes in 24 hours,
  and its next run was `2026-06-12T11:47:05+02:00`.
- Tracked and runtime Caddyfile hashes remain equal to the SHA-256 above and
  the runtime configuration validates.
- Local hostname routing through Caddy returns HTTP 308 from HTTP to HTTPS,
  HTTP 200 for the HTTPS Streamlit page, and FastAPI HTTP 401 JSON for a
  protected API request without a bearer token.
- A validly encoded invalid login returns the same generic HTTP 401 JSON
  response without account-enumeration detail.
- P1.5 constants remain 15-character minimum, 1024-character maximum, and
  600,000 PBKDF2-HMAC-SHA256 iterations. The tracked password blocklist loads,
  weak/short test values are rejected, and a generated non-production Unicode
  passphrase is accepted and hashed with the current work factor.
- Existing valid legacy PBKDF2 hashes remain accepted and are rehashed only
  after successful login. Do not test this against a real user automatically.

Required post-restart checks:
- Confirm the scheduled task ran after boot with result `0`.
- Confirm exactly one listener each on 8000, 8001, 80, 443, and 2019, allowing
  the documented Tailscale-interface 443 listeners.
- Confirm FastAPI live/ready and Streamlit health endpoints.
- Confirm scheduler lock ownership, heartbeat age, latest job status, next
  run, and at least one successful post-restart scheduled job.
- Confirm tracked/runtime Caddyfile hash equality and run `caddy validate`.
- Confirm local Caddy hostname routing with explicit loopback resolution:
  HTTP 308, HTTPS dashboard 200, and protected API 401 JSON.
- Import `services.api.main` and run a non-production password-policy smoke
  check without reading the database or any real credential.
- Confirm a public invalid login remains generic HTTP 401; use only a
  disposable identifier and avoid triggering a throttle threshold unless
  specifically needed.
- Confirm `git status --short` shows only the expected handoff change and no
  startup-generated tracked changes.
- Append the actual verification results and deviations to this file.

Known risks or accepted gaps:
- Uvicorn production startup still uses `--reload`; removal remains P2.13.
- No real credential-based dashboard login or live legacy-hash migration will
  be automated.
- Existing production hash iteration counts were not enumerated.
- The full suite has two independently reproducible, unrelated failures in
  `tests/test_vodomery_reports.py`; P1.5 targeted coverage passed 84 tests and
  the full suite passed 471 of 473 tests.
- Direct access through the public endpoint from this server may lack NAT
  loopback; local Caddy verification uses the production hostname resolved
  explicitly to `127.0.0.1`.

### 2026-06-12 12:19 CEST - Post-restart verification

Scope:
- Verified the cold production runtime and P1.5 password-policy deployment
  after the workstation restart described in the 11:43 CEST handoff.

Verified:
- Windows boot completed at 11:44:55 CEST. Scheduled task
  `API_dashboard_caddy` ran at 11:45:05 CEST with result `0`, uses the boot
  trigger, and points to the tracked `start_api_dashboard.bat`.
- FastAPI had one listener on `127.0.0.1:8000`, Streamlit had one listener on
  `127.0.0.1:8001`, and one Caddy runtime owned TCP 80/443 and
  `127.0.0.1:2019`. Separate Tailscale-interface TCP 443 listeners were
  present as expected.
- FastAPI live/ready and Streamlit health endpoints returned HTTP 200.
- Scheduler metrics reported `scheduler_running=true`; the
  `scheduler_process` file lock was held and the heartbeat was within the
  configured 300-second TTL.
- The first checked post-restart `quarter_hour_job` completed successfully at
  12:16:10 CEST, with 0 failures and 96 successes in 24 hours; its next run
  was scheduled for 12:35:05 CEST.
- Tracked and runtime Caddyfile SHA-256 values both remained
  `F41D3B31EA03308CB4345B1D11F0488B11D1FE527CBF135B0E1E166E5E7BC9BE`.
  The runtime Caddy configuration validated successfully.
- Local hostname routing through Caddy returned HTTP 308 from HTTP to HTTPS,
  HTTP 200 for the HTTPS Streamlit page, and FastAPI HTTP 401 JSON for an
  unauthenticated protected API route.
- A valid disposable invalid-login request returned the generic FastAPI HTTP
  401 JSON response without account-enumeration detail.
- FastAPI imported successfully. The password-policy smoke check confirmed
  the 15/1024 character limits, loaded blocklist, 600,000 PBKDF2 iterations,
  weak-password rejection, Unicode passphrase support, current-hash
  verification, and verification/rehash detection for a synthetic
  390,000-iteration legacy hash.
- Targeted password-policy and security-configuration tests passed:
  24 tests.
- `git status --short --untracked-files=all` contained only the expected
  `SESSION_NOTES.md` handoff/verification change.

Not verified:
- No real dashboard password, production password hash, bearer token, or
  browser session was read or used.
- External access from a separate network was not tested.
- The full pytest suite was not rerun because P1.5 already passed its broader
  84-test set and the full-suite baseline before restart.

Deviations:
- None.

### 2026-06-12 - MFA/SSO deferred

Scope:
- Reviewed dashboard security checklist item P1.6.

Decisions/notes:
- The user deferred selection and implementation of corporate OIDC/SAML SSO
  or application-managed MFA.
- P1.6 remains open and is not considered completed.
- The accepted residual risk is that a compromised administrator password can
  still be sufficient for account access.
- Existing password hardening, throttling, audit logging, temporary lockouts,
  and token revocation remain compensating controls.
- Revisit P1.6 when corporate identity-provider capabilities are known, before
  materially expanding administrator access or public exposure, or after the
  currently actionable P1 items are addressed.

Follow-up:
- Continue with P1.7: remove the full bearer token from map iframe JavaScript.

### 2026-06-12 - Map iframe bearer token removal

Scope:
- Completed dashboard security checklist item P1.7.

Changed:
- Removed the main bearer token and `Authorization` header from generated map
  iframe HTML and JavaScript.
- Changed map photo loading to same-origin `/api/v1/map/images` with
  browser-managed credentials.
- Added a dedicated FastAPI dependency that accepts the existing HttpOnly
  dashboard session cookie only for the map image endpoint.
- Preserved token signature, expiry, user activity, `token_version`, map-layer,
  and device authorization checks.
- Kept all other protected FastAPI routes on bearer authentication.
- Removed `DASHBOARD_BROWSER_API_BASE_URL` and its `.env.example` entry because
  map image authentication now requires same-origin routing.
- Added DEC-029 and updated the operating context and security checklist.

Verified:
- Targeted map, map-layer, device-image, authentication-route, and dashboard
  auth-state tests passed: 66 tests.
- Python compilation passed for all changed application modules.
- FastAPI application import passed.
- FastAPI live/ready and Streamlit health endpoints returned HTTP 200 after
  Uvicorn reloaded the changes.
- The live image endpoint returned HTTP 401 with the missing-cookie response
  both without credentials and with a bearer header alone.
- A normal protected map catalog request with an invalid bearer token still
  followed bearer validation, confirming that cookie authentication was not
  enabled globally.
- OpenAPI exposes `GET /api/v1/map/images` with the dedicated `APIKeyCookie`
  scheme and keeps the normal `HTTPBearer` scheme for other protected routes.
- `git diff --check` reported no whitespace errors.

Not verified:
- A real authenticated device photo was not opened in a browser because no
  dashboard credential or browser cookie was read or requested.
- The full pytest suite was not run; verification focused on the changed map,
  authentication, and authorization surfaces.

Decisions/notes:
- Compromise of map iframe JavaScript no longer exposes a reusable dashboard
  API token.
- P1.8 remains important because Leaflet JavaScript is still loaded from
  `unpkg.com` and executes in the authenticated map iframe.

Follow-up:
- Continue with P1.8: host Leaflet JavaScript and CSS locally.

### 2026-06-12 12:51 CEST - Pre-restart handoff

Reason for restart:
- Renew the complete production runtime through the supported Windows Task
  Scheduler boot path.
- Verify dashboard security checklist item P1.7 from a cold application start,
  especially the dedicated cookie authentication for map images and the
  absence of the main bearer token from map iframe JavaScript.

Current task/conversation state:
- Completed implementation and targeted verification of P1.7.
- Deferred P1.6 MFA/SSO by explicit user decision; it remains open.
- P1.7 removes the main bearer token from generated map HTML, authenticates
  only `GET /api/v1/map/images` with the HttpOnly dashboard session cookie,
  and keeps all other protected API routes on bearer authentication.
- P1.7 changes are not committed. The current HEAD remains
  `ff7513d` (`security check P1.5 hotovo`).
- Pending: restart Windows, execute all checks below, append actual
  post-restart results and deviations, then continue with P1.8 local Leaflet
  hosting.
- First action after restart: read `AGENTS.md`, `DECISIONS.md`, and
  `SESSION_NOTES.md`, then run `git status --short --untracked-files=all`.

Working tree and deployment:
- `git status --short --untracked-files=all` immediately before this handoff:

```text
 M .env.example
 M AGENTS.md
 M DASHBOARD_SECURITY_CHECKLIST.md
 M DECISIONS.md
 M SESSION_NOTES.md
 M moduly/apps/dashboard/api_client.py
 M moduly/apps/dashboard/map_shared.py
 M moduly/apps/dashboard/pages/36_mapove_podklady.py
 M services/api/core/dependencies.py
 M services/api/routes/map.py
 M tests/test_dashboard_map_page_layout.py
 M tests/test_dashboard_map_shared.py
 M tests/test_map_routes.py
```

- All listed changes belong to the current restart handoff, the previously
  recorded P1.6 deferral, or the P1.7 implementation. Do not discard or
  overwrite them after restart.
- Uvicorn reload already loaded the changed Python source in the current
  runtime, but the restart will verify a cold scheduled-task startup.
- No Caddy configuration change is part of P1.7.
- Tracked and deployed Caddyfile SHA-256 values both equal
  `F41D3B31EA03308CB4345B1D11F0488B11D1FE527CBF135B0E1E166E5E7BC9BE`.
- The deployed Caddy configuration validated successfully before restart.
- Targeted P1.7 map, authentication, and authorization tests passed:
  66 tests.
- Python compilation and FastAPI import passed.
- `git diff --check` reported no whitespace errors.

Sensitive/runtime artifacts:
- Do not print, change, delete, or commit the ignored local `.env` containing
  `API_TOKEN_SECRET`.
- Do not inspect, print, change, delete, or commit SmartFuelPass cookies or
  other browser session artifacts.
- Do not print raw authentication audit records from
  `C:\ProgramData\monitorovaci_platforma\logs\auth_audit.jsonl`.
- Do not read or print the value of the
  `monitoring_dashboard_session` HttpOnly cookie, any bearer token, password,
  or stored password hash during verification.
- The retired ProgramData Caddy gate credential files remain sensitive and
  must not be printed, changed, or deleted.

Windows scheduled startup expectation:
- Scheduled task name: `API_dashboard_caddy`.
- Executable:
  `C:\Users\tra\PycharmProjects\monitorovaci_platforma\start_api_dashboard.bat`.
- Trigger: Windows boot (`MSFT_TaskBootTrigger`).
- Principal: user `tra`, highest run level.
- Before restart the task was `Ready`; its previous run at
  2026-06-12 11:45:05 CEST completed with result `0`.

Expected processes and listeners after restart:
- One FastAPI/Uvicorn runtime owns the single listener
  `127.0.0.1:8000`. Reload mode may create a parent/child process tree, but
  there must be only one listener.
- One Streamlit runtime owns the single listener `127.0.0.1:8001`.
- One scheduler runtime runs `main.py`, holds the `scheduler_process` lock,
  and updates `core/scheduler/logs/scheduler_metrics.json`.
- One Caddy runtime from `C:\Program Files\Caddy\caddy.exe` owns TCP 80 and
  443 plus `127.0.0.1:2019`.
- Tailscale may separately own interface-specific TCP 443 listeners; those are
  expected and are not duplicate public Caddy listeners.

Expected application state:
- FastAPI `/health/live` and `/health/ready`: HTTP 200.
- Streamlit `/_stcore/health`: HTTP 200.
- Scheduler reports `scheduler_running=true`, holds the process lock, and has
  a heartbeat no older than the configured 300-second TTL.
- Immediately before restart, `quarter_hour_job` last ran successfully at
  `2026-06-12T12:47:08.170524`, had 0 failures and 96 successes in 24 hours,
  and its next run was `2026-06-12T13:05:05+02:00`.
- Tracked and runtime Caddyfile hashes remain equal to the SHA-256 above and
  the runtime configuration validates.
- Local hostname routing through Caddy returns HTTP 308 from HTTP to HTTPS,
  HTTP 200 for the HTTPS Streamlit page, and FastAPI HTTP 401 JSON for an
  unauthenticated protected bearer API route.
- `GET /api/v1/map/images` without the dashboard session cookie returns HTTP
  401 JSON with the missing-cookie response.
- Sending a bearer header without the session cookie to the image endpoint
  still returns the missing-cookie HTTP 401 response.
- Other protected API routes continue to use bearer validation and do not
  accept cookie authentication.
- OpenAPI describes the image endpoint with `APIKeyCookie` named
  `monitoring_dashboard_session` and retains `HTTPBearer` for normal protected
  API operations.
- Generated map HTML contains no bearer token, `Authorization` header,
  `mapImageAccessToken`, or token-bearing iframe argument.
- Authenticated photo requests use same-origin `/api/v1/map/images` with
  `credentials: "same-origin"`; raw filesystem paths remain server-side.

Required post-restart checks:
- Confirm the scheduled task ran after boot with result `0`.
- Confirm exactly one listener each on 8000, 8001, 80, 443, and 2019, allowing
  the documented Tailscale-interface 443 listeners.
- Confirm FastAPI live/ready and Streamlit health endpoints.
- Confirm scheduler lock ownership, heartbeat age, latest job status, next
  run, and at least one successful post-restart scheduled job.
- Confirm tracked/runtime Caddyfile hash equality and run `caddy validate`.
- Confirm local Caddy hostname routing with explicit loopback resolution:
  HTTP 308, HTTPS dashboard 200, and protected bearer API 401 JSON.
- Confirm the image endpoint returns missing-cookie HTTP 401 both without
  credentials and with a bearer header alone.
- Import `services.api.main` and inspect OpenAPI without printing credentials:
  image security must be `APIKeyCookie`; normal protected routes must remain
  `HTTPBearer`.
- Run the targeted 66-test P1.7 suite and Python compilation.
- Search generated/source map HTML contracts to confirm no main bearer token
  or browser API override returned.
- Confirm `git status --short --untracked-files=all` still contains exactly
  the expected uncommitted P1.6/P1.7 documentation and code changes plus this
  handoff; no startup-generated tracked changes may appear.
- A real authenticated map photo may be checked manually by the user without
  exposing the cookie or password. Do not automate by reading browser state.
- Append a dated post-restart verification entry with results and deviations.

Known risks or accepted gaps:
- Uvicorn production startup still uses `--reload`; removal remains P2.13.
- A real authenticated device photo was not opened automatically before the
  restart because no dashboard credential or browser cookie was read.
- The full pytest suite was not rerun for P1.7; the focused 66-test set passed.
- Leaflet JavaScript and CSS are still loaded from `unpkg.com`; P1.8 is the
  next planned security item.
- P1.6 MFA/SSO remains deferred, so compromise of an administrator password
  can still be sufficient for account access.

### 2026-06-12 13:05 CEST - Post-restart verification

Scope:
- Verified the cold production runtime and P1.7 map iframe credential changes
  after the workstation restart described in the 12:51 CEST handoff.

Verified:
- Windows boot completed at 12:55:48 CEST. Scheduled task
  `API_dashboard_caddy` ran at 12:55:58 CEST with result `0`, remained
  `Ready`, used its boot trigger, and pointed to the tracked launcher.
- FastAPI had one listener on `127.0.0.1:8000`, Streamlit had one listener on
  `127.0.0.1:8001`, and one Caddy runtime owned TCP 80/443 and
  `127.0.0.1:2019`. Separate Tailscale-interface TCP 443 listeners were
  present as expected.
- FastAPI live/ready and Streamlit health endpoints returned HTTP 200.
- Scheduler metrics reported `scheduler_running=true`; the
  `scheduler_process` file lock was held and the heartbeat was within the
  configured 300-second TTL.
- The first post-restart `quarter_hour_job` completed successfully at
  13:05:10 CEST, with 0 failures and 96 successes in 24 hours; its next run
  was scheduled for 13:16:05 CEST.
- Tracked and runtime Caddyfile SHA-256 values both remained
  `F41D3B31EA03308CB4345B1D11F0488B11D1FE527CBF135B0E1E166E5E7BC9BE`.
  The runtime Caddy configuration validated successfully.
- Local hostname routing through Caddy returned HTTP 308 from HTTP to HTTPS,
  HTTP 200 for the HTTPS Streamlit page, and FastAPI HTTP 401 JSON for an
  unauthenticated protected bearer API route.
- `GET /api/v1/map/images` returned HTTP 401 without the dashboard session
  cookie and also returned HTTP 401 when sent only a synthetic bearer header.
- FastAPI imported successfully. OpenAPI described the image endpoint with
  `APIKeyCookie` named `monitoring_dashboard_session` and kept `HTTPBearer`
  for the normal protected map catalog route.
- Generated map HTML used same-origin `/api/v1/map/images` with
  `credentials: "same-origin"` and contained no `Authorization` header,
  bearer text, token variable, or browser API override.
- The focused P1.7 test suite passed all 66 tests. Python compilation passed
  for every changed application module, and `git diff --check` reported no
  whitespace errors.
- `git status --short --untracked-files=all` contained exactly the expected
  uncommitted P1.6/P1.7 documentation, application, and test changes.

Not verified:
- No real dashboard password, bearer token, browser cookie, production
  password hash, or authenticated device photo was read or used.
- External access from a separate network was not tested.
- The full pytest suite was not rerun; verification used the focused 66-test
  P1.7 suite from the handoff.

Deviations:
- None.

Follow-up:
- Continue with P1.8 by pinning and hosting the reviewed Leaflet JavaScript
  and CSS under application control and adding an external-script regression
  test.

### 2026-06-12 13:21 CEST - Local Leaflet assets

Scope:
- Completed dashboard security checklist item P1.8.

Changed:
- Vendored Leaflet `1.9.4` JavaScript, CSS, five referenced PNG assets, BSD
  license, and source/hash metadata under
  `moduly/apps/dashboard/assets/leaflet/1.9.4`.
- Replaced runtime `unpkg.com` Leaflet loading with cached local asset reads
  and inline iframe CSS/JavaScript.
- Embedded Leaflet CSS images and default marker images as data URIs.
- Added DEC-030 and updated the operating context and security checklist.
- Added regression tests for the official Leaflet SRI hashes, external
  executable script origins, inline map assets, and unbundled CSS references.

Verified:
- Vendored `leaflet.css` matched official SHA-256 SRI
  `p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=`.
- Vendored `leaflet.js` matched official SHA-256 SRI
  `20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=`.
- Generated map HTML contained Leaflet `1.9.4`, no external script source,
  no `unpkg.com` reference, no unbundled `url(images/...)` reference, and no
  stale source-map directive.
- Active dashboard Python and HTML sources contained no external HTTP(S)
  executable script tag.
- The combined P1.7/P1.8 map, authentication, authorization, and security
  suite passed all 73 tests.
- Python compilation, `git diff --check`, FastAPI live/ready, and Streamlit
  health checks passed.

Not verified:
- No real authenticated map interaction was automated because no dashboard
  credential or browser cookie was read or requested.
- The full pytest suite was not rerun; verification focused on the affected
  map, authentication, authorization, and security surfaces.

Decisions/notes:
- External OSM/CUZK map tiles and weather data remain network resources, but
  authenticated dashboard pages no longer execute third-party JavaScript.
- A workstation restart is not required for P1.8; Streamlit loads the changed
  renderer and repository assets on the next page rerun.

Follow-up:
- Continue with P1.9 browser session hardening.

### 2026-06-12 13:29 CEST - Pre-restart handoff

Reason for restart:
- Save the completed P1.7 and P1.8 security work and renew the complete
  production runtime through the supported Windows Task Scheduler boot path.
- Verify cookie-only map image authentication and locally vendored Leaflet
  assets from a cold start before continuing with P1.9 browser session
  hardening.

Current task/conversation state:
- P1.6 MFA/SSO remains deferred by explicit user decision.
- P1.7 is complete: map iframe JavaScript no longer receives the main bearer
  token, and only the map image endpoint accepts the HttpOnly dashboard
  session cookie.
- P1.8 is complete: Leaflet `1.9.4` JavaScript, CSS, images, license, and
  metadata are pinned under application control with no runtime executable
  code loading from `unpkg.com`.
- Pending before restart: commit all expected P1.6/P1.7/P1.8 files. Do not
  restart if staging, commit, or final clean-tree verification fails.
- Pending after restart: execute all checks below, append the actual result,
  then continue with P1.9 from `DASHBOARD_SECURITY_CHECKLIST.md`.
- First action after restart: read `AGENTS.md`, `DECISIONS.md`, and
  `SESSION_NOTES.md`, then run `git status --short --untracked-files=all`.

Working tree and deployment:
- Current HEAD before saving is `ff7513d` (`security check P1.5 hotovo`) on
  `master`.
- Expected files to commit before restart:

```text
.gitattributes
.env.example
AGENTS.md
DASHBOARD_SECURITY_CHECKLIST.md
DECISIONS.md
SESSION_NOTES.md
moduly/apps/dashboard/api_client.py
moduly/apps/dashboard/assets/leaflet/1.9.4/LICENSE
moduly/apps/dashboard/assets/leaflet/1.9.4/THIRD_PARTY.md
moduly/apps/dashboard/assets/leaflet/1.9.4/images/layers-2x.png
moduly/apps/dashboard/assets/leaflet/1.9.4/images/layers.png
moduly/apps/dashboard/assets/leaflet/1.9.4/images/marker-icon-2x.png
moduly/apps/dashboard/assets/leaflet/1.9.4/images/marker-icon.png
moduly/apps/dashboard/assets/leaflet/1.9.4/images/marker-shadow.png
moduly/apps/dashboard/assets/leaflet/1.9.4/leaflet.css
moduly/apps/dashboard/assets/leaflet/1.9.4/leaflet.js
moduly/apps/dashboard/map_shared.py
moduly/apps/dashboard/pages/36_mapove_podklady.py
services/api/core/dependencies.py
services/api/routes/map.py
tests/test_dashboard_map_page_layout.py
tests/test_dashboard_map_shared.py
tests/test_dashboard_security_config.py
tests/test_map_routes.py
```

- The expected working tree after commit and before restart is clean.
- Uvicorn reload and Streamlit page reruns have already loaded the Python
  changes in the current runtime; the restart will verify the committed cold
  startup.
- No Caddy configuration change is part of P1.7 or P1.8.
- Tracked and deployed Caddyfile SHA-256 values both equal
  `F41D3B31EA03308CB4345B1D11F0488B11D1FE527CBF135B0E1E166E5E7BC9BE`.
- The runtime Caddy configuration validated successfully before restart.
- The combined P1.7/P1.8 suite passed all 73 tests. Python compilation and
  `git diff --check` passed.

Sensitive/runtime artifacts:
- Do not print, change, delete, or commit the ignored local `.env` containing
  `API_TOKEN_SECRET`.
- Do not inspect, print, change, delete, or commit SmartFuelPass cookies or
  other browser session artifacts.
- Do not print raw authentication audit records from
  `C:\ProgramData\monitorovaci_platforma\logs\auth_audit.jsonl`.
- Do not read or print the `monitoring_dashboard_session` cookie, any bearer
  token, password, or stored password hash during verification.
- The retired ProgramData Caddy gate credential files remain sensitive and
  must not be printed, changed, or deleted.

Windows scheduled startup expectation:
- Scheduled task name: `API_dashboard_caddy`.
- Executable:
  `C:\Users\tra\PycharmProjects\monitorovaci_platforma\start_api_dashboard.bat`.
- Trigger: Windows boot (`MSFT_TaskBootTrigger`).
- Principal: user `tra`, highest run level.
- Before restart the task was `Ready`; its last run at
  2026-06-12 12:55:58 CEST completed with result `0`.

Expected processes and listeners after restart:
- One FastAPI/Uvicorn runtime owns the single listener
  `127.0.0.1:8000`. Reload mode may create a parent/child process tree, but
  there must be only one listener.
- One Streamlit runtime owns the single listener `127.0.0.1:8001`.
- One scheduler runtime runs `main.py`, holds the `scheduler_process` lock,
  and updates `core/scheduler/logs/scheduler_metrics.json`.
- One Caddy runtime from `C:\Program Files\Caddy\caddy.exe` owns TCP 80 and
  443 plus `127.0.0.1:2019`.
- Tailscale may separately own interface-specific TCP 443 listeners; those
  are expected and are not duplicate public Caddy listeners.

Expected application state:
- FastAPI `/health/live` and `/health/ready`: HTTP 200.
- Streamlit `/_stcore/health`: HTTP 200.
- Scheduler reports `scheduler_running=true`, holds the process lock, and has
  a heartbeat no older than the configured 300-second TTL.
- Immediately before restart, `quarter_hour_job` last ran successfully at
  `2026-06-12T13:16:08.313423`, had 0 failures and 96 successes in 24 hours,
  and its next run was `2026-06-12T13:35:05+02:00`.
- Tracked and runtime Caddyfile hashes remain equal to the SHA-256 above and
  the runtime configuration validates.
- Local hostname routing through Caddy returns HTTP 308 from HTTP to HTTPS,
  HTTP 200 for the HTTPS Streamlit page, and FastAPI HTTP 401 JSON for an
  unauthenticated protected bearer API route.
- `GET /api/v1/map/images` without the dashboard session cookie returns HTTP
  401, including when a bearer header is sent without the cookie.
- OpenAPI keeps `APIKeyCookie` only for the image endpoint and `HTTPBearer`
  for normal protected routes.
- Generated map HTML contains no main token, bearer header, external
  executable script source, `unpkg.com` reference, unbundled Leaflet image
  path, or stale source-map directive.
- Vendored `leaflet.js` and `leaflet.css` continue to match the official
  SHA-256 SRI values recorded in the tests and `THIRD_PARTY.md`.

Required post-restart checks:
- Confirm the scheduled task ran after boot with result `0`.
- Confirm exactly one listener each on 8000, 8001, 80, 443, and 2019, allowing
  the documented Tailscale-interface 443 listeners.
- Confirm FastAPI live/ready and Streamlit health endpoints.
- Confirm scheduler lock ownership, heartbeat age, latest job status, next
  run, and at least one successful post-restart scheduled job.
- Confirm tracked/runtime Caddyfile hash equality and run `caddy validate`.
- Confirm local Caddy hostname routing with explicit loopback resolution:
  HTTP 308, HTTPS dashboard 200, protected bearer API 401, and map image
  endpoint 401 without the dashboard cookie.
- Import `services.api.main` and inspect OpenAPI without printing credentials:
  image security must be `APIKeyCookie`; normal protected routes must remain
  `HTTPBearer`.
- Run the 73-test combined P1.7/P1.8 suite and Python compilation.
- Generate map HTML and confirm the token, same-origin image, local Leaflet,
  asset hash, and external-script regression contracts.
- Confirm `git status --short --untracked-files=all` is clean and HEAD is the
  commit created immediately before this restart.
- A real authenticated map may be checked manually by the user without
  exposing the cookie or password. Do not automate by reading browser state.
- Append a dated post-restart verification entry with results and deviations.

Known risks or accepted gaps:
- Uvicorn production startup still uses `--reload`; removal remains P2.13.
- No real authenticated map or device photo will be automated.
- The full pytest suite was not rerun; the focused combined suite passed all
  73 tests.
- P1.6 MFA/SSO remains deferred, so compromise of an administrator password
  can still be sufficient for account access.
- P1.9 browser session hardening has not started.

### 2026-06-12 14:28 CEST - Post-restart verification

Scope:
- Verified the committed P1.7/P1.8 deployment after the workstation restart
  described in the 13:29 CEST handoff.

Verified:
- Windows boot completed at 13:39:14 CEST. Scheduled task
  `API_dashboard_caddy` ran at 13:39:24 CEST with result `0`, remained
  `Ready`, and used the expected boot trigger and tracked launcher.
- HEAD was `b3e3e29` (`security check P1.7 a P1.8 hotovo`), and the working
  tree was clean before this verification note was appended.
- FastAPI had one listener on `127.0.0.1:8000`, Streamlit had one listener on
  `127.0.0.1:8001`, and one Caddy runtime owned TCP 80/443 and
  `127.0.0.1:2019`. Separate Tailscale-interface TCP 443 listeners were
  present as expected.
- FastAPI live/ready and Streamlit health endpoints returned HTTP 200.
- Scheduler metrics reported `scheduler_running=true`; the
  `scheduler_process` lock was held and the heartbeat was within the
  configured 300-second TTL.
- The post-restart `quarter_hour_job` completed successfully at 14:16:07
  CEST, with 0 failures and 96 successes in 24 hours; its next run was
  scheduled for 14:35:05 CEST.
- Tracked and runtime Caddyfile SHA-256 values both remained
  `F41D3B31EA03308CB4345B1D11F0488B11D1FE527CBF135B0E1E166E5E7BC9BE`,
  and the runtime configuration validated successfully.
- Local hostname routing returned HTTP 308 from HTTP to HTTPS, HTTP 200 for
  the HTTPS dashboard, HTTP 401 JSON for an unauthenticated protected API
  route, and HTTP 401 JSON for the map image endpoint both without
  credentials and with a bearer header alone.
- FastAPI OpenAPI kept `APIKeyCookie` named
  `monitoring_dashboard_session` for the image endpoint and `HTTPBearer` for
  the normal protected map catalog route.
- The combined P1.7/P1.8 suite passed all 73 tests. Python compilation of the
  changed application modules and `git diff --check` also passed.
- Regression coverage confirmed the main bearer token is absent from map
  iframe HTML, image requests remain same-origin, Leaflet assets match the
  reviewed hashes, and active dashboard sources load no external executable
  scripts.

Not verified:
- No real dashboard credential, bearer token, browser cookie, authenticated
  map, or device photo was read or used.
- External access from a separate network was not tested.
- The full pytest suite was not rerun; verification used the focused 73-test
  P1.7/P1.8 suite.

Deviations:
- None.

Follow-up:
- Continue with P1.9 browser session hardening.

### 2026-06-12 18:28 CEST - Browser session hardening

Scope:
- Completed dashboard security checklist item P1.9.
- Added bounded rolling sessions, a host-bound cookie, periodic renewal, and
  revocation for authorization changes.

Changed:
- Renamed the browser cookie to
  `__Host-monitoring_dashboard_session`; it is always `Secure`, `HttpOnly`,
  `SameSite=Lax`, `Path=/`, and has no `Domain` attribute.
- Added signed token claims for issue time, session start, rolling expiry, and
  absolute expiry.
- Added a 30-minute default request-inactivity limit, an 8-hour absolute
  limit, and `POST /api/v1/auth/session/refresh`.
- Active Streamlit sessions renew at most once every five minutes without
  extending the original absolute expiry.
- Rejected the previous token format without the new session claims. Existing
  users therefore need one new login after deployment.
- Password, role, activation, allowed-section, allowed-page, and
  allowed-device changes now increment `token_version` once and revoke all
  existing sessions. Email-only updates keep sessions valid.
- Browser-session deletion removes both the current and retired cookie and
  returns `Clear-Site-Data` for origin cache and storage.
- Added DEC-031 and updated the checklist, API configuration example, API
  README, and operating context.

Verified:
- Focused P1.9 lifecycle tests passed: 50 tests.
- Broader authentication, audit, password, Caddy, navigation, responsive,
  map, and session tests passed: 154 tests.
- The full suite passed 492 of 494 tests. The same two unrelated,
  independently reproducible failures remain in
  `tests/test_vodomery_reports.py`.
- Python compilation, FastAPI import, and `git diff --check` passed.
- Running FastAPI live/ready and Streamlit health endpoints returned HTTP 200.
- Live OpenAPI exposed the refresh route and the
  `__Host-monitoring_dashboard_session` cookie security scheme while normal
  protected routes remained on `HTTPBearer`.
- A synthetic legacy-format token signed by the current application was
  rejected with HTTP 401 because the new session claims were absent.
- Local public-hostname HTTPS returned HTTP 200; the unauthenticated map image
  and session-refresh routes returned HTTP 401.

Not verified:
- No real dashboard password, bearer token, browser cookie, or authenticated
  map session was read or used.
- A real browser login, five-minute renewal, 30-minute inactivity expiry, and
  eight-hour absolute expiry were not observed wall-clock end to end.
- External access from a separate network was not tested.

Decisions/notes:
- Request activity, including dashboard reruns, can renew the rolling timeout;
  the absolute eight-hour limit remains fixed.
- No workstation restart is required for P1.9. Uvicorn reload loaded the API
  changes, and Streamlit will use the changed auth module on application
  rerun.

Follow-up:
- Continue with P1.10 by moving privileged revision writes behind FastAPI
  server-side authorization.

### 2026-06-12 22:26 CEST - Database connectivity observation

Scope:
- Investigated an unexpected scheduler skip found during the final P1.9
  runtime sanity check.

Observed:
- Scheduler remained running, held its process lock, and refreshed its
  heartbeat within the configured 300-second TTL.
- `quarter_hour_job` was skipped at 22:18:32 CEST with
  `database_unavailable`; its next retry remained scheduled for 22:35:05 CEST.
- FastAPI live/ready and Streamlit health endpoints still returned HTTP 200.
- DNS resolved the configured database host, but TCP connections to both
  PostgreSQL port 5432 and MS SQL port 1433 failed.
- A direct combined database availability check did not complete within 60
  seconds. A separate MS SQL connection returned a network/login timeout, and
  the separate PostgreSQL connection did not complete within 20 seconds.

Decisions/notes:
- This is an external database/network availability issue, not a P1.9 code or
  test failure.
- No process restart or configuration change was attempted. The scheduler's
  existing preflight behavior safely skips database jobs and retries on their
  next scheduled run.

Follow-up:
- Confirm corporate network/database availability and verify that a later
  `quarter_hour_job` returns to `success`.

### 2026-06-12 22:37 CEST - Pre-restart handoff

Reason for restart:
- Save the completed P1.9 browser-session hardening and renew the complete
  production runtime through the supported Windows Task Scheduler boot path.
- Verify the committed session token/cookie behavior from a cold start.
- Recheck the external database connectivity problem observed before restart;
  the restart is not assumed to repair an unavailable database server or
  corporate network path.

Current task/conversation state:
- P1.6 MFA/SSO remains deferred by explicit user decision.
- P1.7, P1.8, and P1.9 are complete.
- P1.9 introduced the `__Host-monitoring_dashboard_session` cookie, a
  30-minute rolling request-inactivity timeout, an 8-hour absolute timeout,
  periodic token renewal, and session revocation after security-relevant user
  changes.
- P1.10 privileged revision-write authorization has not started.
- First action after restart: read `AGENTS.md`, `DECISIONS.md`,
  `SESSION_NOTES.md`, and `DASHBOARD_SECURITY_CHECKLIST.md`, then run
  `git status --short --untracked-files=all`.

Working tree and deployment:
- Current saved P1.9 commit is `a0900a7de36797ce44be49a8106ad929149ac4ed`
  (`security check 1.4 hotovo`) on `master` and `origin/master`.
- The working tree was clean before this handoff was appended.
- This handoff must be committed separately before restart; the expected
  working tree immediately before restart is clean.
- Uvicorn reload already loaded the P1.9 API changes. Live OpenAPI exposed
  `/api/v1/auth/session/refresh` and cookie security name
  `__Host-monitoring_dashboard_session`.
- Streamlit health and FastAPI live/ready returned HTTP 200.
- Local Caddy routing returned HTTP 308 to HTTPS, dashboard HTTP 200,
  protected bearer API HTTP 401, and unauthenticated refresh HTTP 401.
- Tracked and runtime Caddyfile SHA-256 values both equal
  `F41D3B31EA03308CB4345B1D11F0488B11D1FE527CBF135B0E1E166E5E7BC9BE`.
- The deployed Caddy configuration validated successfully before restart.
- Focused P1.9 lifecycle tests passed 50 tests; the broader security,
  authentication, dashboard, and map suite passed 154 tests.
- The full suite passed 492 of 494 tests. The two remaining failures are the
  previously documented unrelated failures in
  `tests/test_vodomery_reports.py`.

Sensitive/runtime artifacts:
- Do not print, change, delete, or commit the ignored local `.env` containing
  `API_TOKEN_SECRET`.
- Do not inspect, print, change, delete, or commit SmartFuelPass cookies or
  other browser session artifacts.
- Do not print raw authentication audit records from
  `C:\ProgramData\monitorovaci_platforma\logs\auth_audit.jsonl`.
- Do not read or print the `__Host-monitoring_dashboard_session` cookie, any
  bearer token, password, or stored password hash during verification.
- The retired ProgramData Caddy gate credential files remain sensitive and
  must not be printed, changed, or deleted.

Windows scheduled startup expectation:
- Scheduled task name: `API_dashboard_caddy`.
- Executable:
  `C:\Users\tra\PycharmProjects\monitorovaci_platforma\start_api_dashboard.bat`.
- Trigger: Windows boot (`MSFT_TaskBootTrigger`).
- Principal: user `tra`, highest run level.
- Before restart the task was `Ready`; its last run at
  2026-06-12 13:39:24 CEST completed with result `0`.

Expected processes and listeners after restart:
- One FastAPI/Uvicorn runtime owns the single listener
  `127.0.0.1:8000`. Reload mode may create a parent/child process tree, but
  there must be only one listener.
- One Streamlit runtime owns the single listener `127.0.0.1:8001`.
- One scheduler runtime runs `main.py`, holds the `scheduler_process` lock,
  and updates `core/scheduler/logs/scheduler_metrics.json`.
- One Caddy runtime from `C:\Program Files\Caddy\caddy.exe` owns TCP 80 and
  443 plus `127.0.0.1:2019`.
- Tailscale may separately own interface-specific TCP 443 listeners; those are
  expected and are not duplicate public Caddy listeners.

Expected application and security state:
- FastAPI `/health/live` and `/health/ready`: HTTP 200.
- Streamlit `/_stcore/health`: HTTP 200.
- Tracked and runtime Caddyfile hashes remain equal to the SHA-256 above and
  the runtime configuration validates.
- Local hostname routing returns HTTP 308 from HTTP to HTTPS, HTTP 200 for the
  dashboard, HTTP 401 JSON for an unauthenticated protected bearer route, HTTP
  401 for the map image endpoint without its cookie, and HTTP 401 for session
  refresh without a bearer token.
- OpenAPI contains `/api/v1/auth/session/refresh`.
- OpenAPI uses `APIKeyCookie` named
  `__Host-monitoring_dashboard_session` for the map image endpoint and
  `HTTPBearer` for normal protected routes.
- A token in the retired format without signed `iat`, `ses`, and `abs` claims
  is rejected with HTTP 401.
- Existing browser sessions issued before P1.9 remain invalid; users need one
  new login. No credential-based login should be automated.

Database and scheduler state before restart:
- Scheduler was running, held its process lock, and had a live heartbeat.
- The scheduler slot planned for 22:35 completed at 22:49:32 CEST after
  database connection timeouts and was skipped with
  `database_unavailable`, 0 failures, and 82 successes in the preceding 24
  hours.
- The next `quarter_hour_job` attempt was scheduled for 23:05:05 CEST.
- DNS resolved `server2a` to the configured internal address, but direct TCP
  checks to PostgreSQL port 5432 and MS SQL port 1433 both failed immediately
  before this handoff.
- FastAPI readiness does not include both scheduler source databases, so HTTP
  200 readiness does not prove scheduler database availability.

Required post-restart checks:
- Confirm the scheduled task ran after boot with result `0`.
- Confirm exactly one listener each on 8000, 8001, 80, 443, and 2019, allowing
  the documented Tailscale-interface 443 listeners.
- Confirm FastAPI live/ready and Streamlit health endpoints.
- Confirm scheduler lock ownership, heartbeat age, latest job status, next
  run, and at least one completed post-restart scheduler slot.
- Test TCP connectivity to `server2a` ports 5432 and 1433 without printing
  credentials. If unavailable, record the continuing external outage and do
  not treat a skipped database job as an application deployment regression.
- If both database ports recover, confirm `quarter_hour_job` returns to
  `success`.
- Confirm tracked/runtime Caddyfile hash equality and run `caddy validate`.
- Confirm local Caddy hostname routing with explicit loopback resolution:
  HTTP 308, HTTPS dashboard 200, protected bearer API 401, map image 401
  without cookie, and refresh 401 without bearer authentication.
- Inspect live OpenAPI without printing credentials: refresh route present,
  image cookie name uses the `__Host-` prefix, and normal routes remain
  `HTTPBearer`.
- Run the focused 50-test P1.9 lifecycle suite, Python compilation, FastAPI
  import, and `git diff --check`.
- Confirm `git status --short --untracked-files=all` is clean and HEAD is the
  commit containing this handoff.
- Append a dated post-restart verification entry with all results and
  deviations.

Known risks or accepted gaps:
- Uvicorn production startup still uses `--reload`; removal remains P2.13.
- No real credential-based login, browser renewal, inactivity expiry, or
  absolute expiry will be automated.
- External access from a separate network was not tested.
- P1.6 MFA/SSO remains deferred.
- The database host/network path was unavailable immediately before restart;
  application restart cannot guarantee its recovery.

### 2026-06-12 23:29 CEST - Post-restart verification

Scope:
- Verified the cold-start state after the workstation booted at
  2026-06-12 22:59:05 CEST.
- No production process, runtime configuration, credential, cookie, token, or
  audit record was changed or printed.

Startup and runtime:
- Scheduled task `API_dashboard_caddy` started at 22:59:15 with the expected
  boot trigger, account, highest run level, and launcher action.
- The task remained `Running` with status `0x41301` instead of completing with
  result `0`.
- The launcher, API, and scheduler process trees existed in the non-interactive
  Services session.
- The scheduler process lock was held. Its heartbeat refreshed at 23:24:23 and
  was within the 300-second TTL during verification.
- Post-restart quarter-hour slots completed at 23:05 and 23:16, but both were
  skipped with `database_unavailable`. The latest recorded completion was
  23:18:32 and the next run was scheduled for 23:35:05.
- TCP checks to `server2a:5432` and `server2a:1433` both failed. The external
  database/network outage observed before restart therefore continued.

Application and routing:
- The FastAPI worker had `127.0.0.1:8000` bound but not listening. FastAPI
  live/ready and Streamlit health requests could not connect.
- No listener existed on loopback ports 8000, 8001, or 2019, and Caddy did not
  own ports 80 or 443. Only the documented Tailscale interface listeners
  existed on port 443.
- Explicit-loopback hostname checks for HTTP redirect, HTTPS dashboard,
  protected API, map image, and session refresh all failed to connect with
  curl status `000`.
- The observed state is consistent with FastAPI blocking in its synchronous
  lifespan call to `ensure_dashboard_tables()` while PostgreSQL is
  unavailable. The launcher then cannot pass its API health gate, so it does
  not start Streamlit or Caddy and remains at the non-interactive failure
  `pause`.

Caddy and security verification:
- Tracked and runtime Caddyfile SHA-256 values both remained
  `F41D3B31EA03308CB4345B1D11F0488B11D1FE527CBF135B0E1E166E5E7BC9BE`.
- `caddy validate` reported a valid runtime configuration.
- FastAPI imported successfully and the changed P1.9 modules compiled.
- The focused P1.9 suite passed all 50 tests.
- Local OpenAPI generation contained `/api/v1/auth/session/refresh`, used
  `APIKeyCookie` named `__Host-monitoring_dashboard_session` for map images,
  and retained `HTTPBearer` for normal protected map routes.
- A synthetic retired-format token signed by the current local application
  secret was rejected without printing the secret or token.
- The local `.env` existed and remained ignored by Git.
- `git diff --check` passed. The working tree was clean before this
  post-restart note was appended, at commit
  `ce8b68442150fd9f1d9119e5423415e02e9fc529`.

Deviations:
- The complete production dashboard runtime did not recover after restart.
- The scheduled task did not finish with result `0`.
- FastAPI, Streamlit, and Caddy health/listener/routing expectations were not
  met because database connectivity prevented FastAPI startup.

Not verified:
- No real dashboard credential, bearer token, browser cookie, authenticated
  map, or device photo was used.
- External access from a separate network was not tested.
- Real browser renewal and timeout behavior was not observed wall-clock.

Required recovery follow-up:
- Restore or confirm the network path to both PostgreSQL and MSSQL on
  `server2a`.
- Do not start duplicate runtime processes manually while the current
  scheduled scheduler process is active.
- After database connectivity is restored, prepare a new restart handoff and
  use the supported full-workstation restart path to renew the complete
  runtime, then repeat the listener, health, scheduler, Caddy, routing, and
  P1.9 checks.

Follow-up observation at 2026-06-13 02:13 CEST:
- The scheduled task still reported `Running`, and no expected application
  listener had appeared.
- The scheduler heartbeat remained live at 02:09:24, but the latest
  `quarter_hour_job` status was still `skipped (database_unavailable)`.

### 2026-06-13 09:17 CEST - Pre-restart recovery handoff

Reason for restart:
- The user explicitly requested another full workstation restart.
- Renew the complete production process set through the supported Windows
  Task Scheduler boot path after the failed 2026-06-12 cold start.
- Recheck whether the external database/network path becomes available during
  boot. Connectivity was still unavailable immediately before this restart,
  so a successful application startup is not assumed.

Current task and security state:
- Dashboard security checklist items P1.7, P1.8, and P1.9 remain complete.
- P1.6 MFA/SSO remains deferred by user decision.
- P1.10 privileged revision-write authorization has not started.
- P1.9 focused regression verification passed all 50 tests after the previous
  restart. FastAPI import, changed-module compilation, local OpenAPI security
  schemes, and retired-token rejection also passed.
- First action after restart: read `AGENTS.md`, `DECISIONS.md`,
  `SESSION_NOTES.md`, and `DASHBOARD_SECURITY_CHECKLIST.md`, then run
  `git status --short --untracked-files=all`.

Working tree and deployment:
- Current `HEAD` is
  `ce8b68442150fd9f1d9119e5423415e02e9fc529` on `master`.
- `origin/master` remains
  `a0900a7de36797ce44be49a8106ad929149ac4ed`.
- The only modified file is `SESSION_NOTES.md`, containing the previous
  post-restart verification and this handoff. No application source or
  runtime configuration is modified.
- `git diff --check` passed before this handoff.
- Tracked and runtime Caddyfile SHA-256 values both remain
  `F41D3B31EA03308CB4345B1D11F0488B11D1FE527CBF135B0E1E166E5E7BC9BE`.
- The deployed Caddy configuration validated successfully immediately before
  restart.

Pre-restart runtime state:
- Scheduled task `API_dashboard_caddy` remained `Running` with status
  `0x41301` from its 2026-06-12 22:59:15 boot run.
- The scheduler process remained active, held its process lock, and refreshed
  its heartbeat at 09:14:25 CEST.
- The latest completed `quarter_hour_job` finished at 09:07:32 CEST as
  `skipped (database_unavailable)`. The 09:16:05 slot had started and was
  still waiting in `check_database_availability` at 09:17:34.
- Direct TCP checks to `server2a:5432` and `server2a:1433` both failed.
- No application listener existed on 80, 2019, 8000, or 8001, and Caddy did
  not own a public port 443 listener. Only the expected Tailscale
  interface-specific port 443 listeners were present.
- This state remained consistent with FastAPI blocking in
  `ensure_dashboard_tables()` while PostgreSQL was unavailable, preventing
  the launcher from reaching Streamlit and Caddy startup.

Sensitive/runtime artifacts:
- Do not print, change, delete, or commit the ignored local `.env` containing
  `API_TOKEN_SECRET`.
- Do not inspect, print, change, delete, or commit SmartFuelPass cookies or
  other browser session artifacts.
- Do not print raw authentication audit records from
  `C:\ProgramData\monitorovaci_platforma\logs\auth_audit.jsonl`.
- Do not read or print dashboard cookies, bearer tokens, passwords, password
  hashes, or retired Caddy gate credentials.

Expected boot path and desired runtime:
- Scheduled task `API_dashboard_caddy` runs at system startup as user `tra`
  with highest run level and executes the tracked
  `start_api_dashboard.bat`.
- One FastAPI/Uvicorn runtime should own `127.0.0.1:8000`.
- One Streamlit runtime should own `127.0.0.1:8001`.
- One scheduler runtime should run `main.py`, hold the
  `scheduler_process` lock, and update scheduler metrics.
- One `C:\Program Files\Caddy\caddy.exe` runtime should own ports 80 and 443
  plus `127.0.0.1:2019`. Tailscale interface-specific port 443 listeners are
  allowed in addition.
- If PostgreSQL remains unavailable, FastAPI is expected to block before
  listening and the launcher may again fail to start Streamlit and Caddy.

Required post-restart verification:
- Confirm the boot time and that scheduled task `API_dashboard_caddy` ran.
- Confirm task state/result and inspect the process tree without starting
  duplicate runtimes.
- Test TCP connectivity to `server2a:5432` and `server2a:1433` without
  printing credentials.
- Confirm scheduler lock ownership, heartbeat age, latest job status, next
  run, and at least one completed post-restart scheduler slot.
- Confirm exactly one expected listener each on 8000, 8001, 80, 443, and
  2019, allowing Tailscale interface-specific 443 listeners.
- Confirm FastAPI `/health/live` and `/health/ready` and Streamlit
  `/_stcore/health` return HTTP 200.
- Confirm tracked/runtime Caddyfile hash equality and run `caddy validate`.
- Confirm explicit-loopback hostname routing: HTTP 308, HTTPS dashboard 200,
  protected Bearer API 401, map image 401 without cookie, and session refresh
  401 without Bearer authentication.
- Inspect live OpenAPI: refresh route present, map image uses
  `APIKeyCookie` named `__Host-monitoring_dashboard_session`, and normal
  protected routes use `HTTPBearer`.
- Confirm a retired-format token without `iat`, `ses`, and `abs` is rejected,
  without printing any secret or token.
- Run the focused 50-test P1.9 suite, changed-module compilation, FastAPI
  import, and `git diff --check`.
- Record the actual results and all deviations in a dated post-restart entry
  in `SESSION_NOTES.md`.

### 2026-06-13 09:40 CEST - Post-restart recovery verification

Scope:
- Verified the workstation cold-start state after the boot at
  2026-06-13 09:19:11 CEST.
- No production process, runtime configuration, credential, cookie, token, or
  audit record was changed or printed.

Startup and process state:
- Scheduled task `API_dashboard_caddy` started at 09:19:21 with the expected
  launcher action and highest run level.
- The task remained `Running` with result `0x41301` instead of completing with
  result `0`.
- The non-interactive Services session contained three `cmd` and four
  `python` processes. No `caddy.exe` process was running.
- FastAPI had `127.0.0.1:8000` in TCP state `Bound`, but no process was
  listening on loopback ports 8000, 8001, or 2019.
- Caddy did not own ports 80 or 443. Only the documented Tailscale
  interface-specific port 443 listeners were present.

Database and scheduler:
- DNS resolved `server2a`, but TCP connections to PostgreSQL port 5432 and
  MSSQL port 1433 both failed.
- The scheduler process lock was held.
- The scheduler heartbeat refreshed at 09:39:27 and was 40 seconds old at the
  final check, within the configured 300-second TTL.
- The first completed post-restart `quarter_hour_job` finished at 09:37:32 as
  `skipped (database_unavailable)`. The next run was scheduled for 09:47:05.
- The scheduler recorded 37 successes and 0 failures in the preceding
  24-hour window; database-unavailable skips are recorded separately from
  failures.

Application and routing:
- FastAPI `/health/live` and `/health/ready` and Streamlit
  `/_stcore/health` could not connect and returned curl status `000`.
- Explicit-loopback hostname checks for HTTP redirect, HTTPS dashboard,
  protected Bearer API, unauthenticated map image, and unauthenticated session
  refresh all returned curl status `000`.
- The observed state is consistent with FastAPI blocking during synchronous
  startup database initialization while PostgreSQL is unavailable. The
  launcher therefore cannot pass its API health gate and does not start
  Streamlit or Caddy.

Caddy and P1.9 security verification:
- Tracked and runtime Caddyfile SHA-256 values both remained
  `F41D3B31EA03308CB4345B1D11F0488B11D1FE527CBF135B0E1E166E5E7BC9BE`.
- `caddy validate` reported a valid runtime configuration.
- The focused P1.9 lifecycle and map authorization suite passed all 50 tests.
- Changed P1.9 modules compiled and FastAPI imported successfully.
- Local OpenAPI generation contained `/api/v1/auth/session/refresh`, used
  `APIKeyCookie` named `__Host-monitoring_dashboard_session` for map images,
  and retained `HTTPBearer` for normal protected map routes.
- A synthetic retired-format token signed by the current local application
  secret was rejected without printing the secret or token.
- The ignored local `.env` existed and remained ignored by Git.
- `git diff --check` passed before this post-restart entry was appended.

Deviations:
- The complete production dashboard runtime did not recover after the second
  restart.
- The scheduled task did not finish with result `0`.
- FastAPI, Streamlit, Caddy, health, listener, and hostname-routing
  expectations were not met because the database network path remained
  unavailable.
- The pre-restart handoff remained an uncommitted change in
  `SESSION_NOTES.md`; `HEAD` remained
  `ce8b68442150fd9f1d9119e5423415e02e9fc529`, while `origin/master` remained
  `a0900a7de36797ce44be49a8106ad929149ac4ed`.

Not verified:
- Live OpenAPI could not be inspected because FastAPI was not listening;
  equivalent local application generation was verified instead.
- No real dashboard credential, bearer token, browser cookie, authenticated
  map, or device photo was used.
- External access from a separate network was not tested.
- Real browser renewal and timeout behavior was not observed wall-clock.

Required recovery follow-up:
- Restore or confirm the network path to both PostgreSQL and MSSQL on
  `server2a`.
- Do not start duplicate production processes manually while the current
  scheduled scheduler process is active.
- After database connectivity is restored, prepare a new restart handoff and
  use the supported full-workstation restart path, then repeat the listener,
  health, scheduler, Caddy, routing, and P1.9 checks.

### 2026-06-13 09:52 CEST - Cold-start diff review and API startup correction

Scope:
- Reviewed the security-checklist diff and Git history to determine whether
  P1.3-P1.9 caused Streamlit and Caddy not to start after the workstation
  restart.
- Corrected the FastAPI cold-start dependency on PostgreSQL availability.

Findings:
- P1.3-P1.9 did not modify `services/api/main.py`,
  `moduly/apps/dashboard/database/db_init.py`, or the launcher API health-gate
  ordering.
- `ensure_dashboard_tables()` had run synchronously in the FastAPI lifespan
  since 2026-03-27.
- The launcher had waited for `/health/live` before starting Streamlit since
  2026-04-30.
- The Windows boot startup introduced a cold-start path while PostgreSQL was
  unavailable. The existing synchronous lifespan call then prevented
  liveness, and the launcher correctly stopped before Streamlit and Caddy.
- The June 2026 security launcher change only added trusted-proxy arguments to
  Uvicorn; it did not add the database startup dependency.

Changed:
- Added thread-safe API readiness state in
  `services/api/core/runtime_state.py`.
- FastAPI now starts database initialization as a background retry task instead
  of awaiting it in the lifespan.
- `/health/live` remains independent of database availability.
- `/health/ready` returns HTTP 503 until database initialization succeeds.
- Retry logging records only the exception type and does not print raw
  connection details.
- Added focused cold-start, liveness, readiness, and retry tests.
- Added DEC-032 and updated API/runtime documentation and the security
  checklist.

Verified:
- The focused startup, P1.9, authentication, map, Caddy, and security suite
  passed all 57 tests.
- Python compilation, FastAPI import, and `git diff --check` passed.
- The running Uvicorn reload process loaded the correction without starting a
  duplicate API process.
- During the continuing database outage, live FastAPI returned HTTP 200 from
  `/health/live` and HTTP 503 from `/health/ready`.
- TCP port 8000 changed from `Bound` without a listener to a loopback
  `Listen` state.

Not verified:
- Streamlit and Caddy were not started manually because the original scheduled
  launcher remains paused after its earlier failed health-gate run.
- The complete boot sequence with the correction requires a future supported
  workstation restart and a new pre-restart handoff.
- Database initialization success after connectivity recovery was covered by
  tests but not observed against the unavailable production database.

Decisions/notes:
- No duplicate production runtime was started.
- Database connectivity to `server2a` remains an external prerequisite for
  authentication and data operations, but no longer for API liveness or future
  Streamlit/Caddy process startup.

### 2026-06-13 10:12 CEST - Minimal database and runtime availability alerts

Scope:
- Restricted database availability email content to the unavailable database
  names requested by the user.
- Added API, Streamlit dashboard, and Caddy availability monitoring before
  each scheduled database-job preflight.

Changed:
- Database alert subjects and bodies now contain only
  `Nedostupnost POSTGRES` and/or `Nedostupnost MSSQL`.
- Removed job IDs, exception reasons, targets, timestamps, URLs, and HTML
  diagnostics from database availability emails.
- Added local probes for FastAPI `/health/live`, Streamlit
  `/_stcore/health`, and the Caddy loopback admin listener on port 2019.
- Runtime alert subjects and bodies contain only `Nedostupnost API`,
  `Nedostupnost DASHBOARD`, and/or `Nedostupnost CADDY`.
- Runtime probes retry once after one second to avoid alerting on a brief
  reload.
- Runtime outages do not stop data jobs. Each service sends one alert when it
  becomes unavailable and can alert again only after recovery.
- Added optional `RUNTIME_ERROR_RECIPIENTS`; when unset, runtime alerts use
  `DATABASE_ERROR_RECIPIENTS`.
- Changed the tracked-secret regression test to inspect the Git index instead
  of opening tracked runtime lock files held by the production scheduler.
- Added DEC-033 and updated operating and security documentation.

Verified:
- `tests/test_scheduler.py` passed all 39 tests.
- Combined scheduler, startup, Caddy, and security tests passed all 55 tests.
- Python compilation and `git diff --check` passed.
- A read-only local probe detected the currently unavailable runtime surfaces
  without sending an email.

Not verified:
- No real availability alert email was sent, to avoid notifying operational
  recipients during development verification.
- The running scheduler process does not reload Python source and therefore
  has not loaded this change.
- Activation requires the next supported full-runtime restart after a new
  pre-restart handoff.

Decisions/notes:
- Technical connection and probe errors remain available only in protected
  scheduler logs.
- No production process was stopped, restarted, or duplicated.

### 2026-06-13 10:14 CEST - Pre-restart availability-alert handoff

Reason for restart:
- Activate the non-blocking FastAPI database initialization and the new
  minimal database/runtime availability alerts in the production scheduler.
- Renew the incomplete boot runtime so Streamlit and Caddy can start after
  FastAPI liveness even if PostgreSQL remains unavailable.
- The user explicitly approved the restart on 2026-06-13 at 10:18 CEST.

Current task and implementation state:
- FastAPI liveness is independent of database initialization; readiness is
  HTTP 503 until initialization succeeds.
- Every scheduled database-job preflight now first checks API, dashboard, and
  Caddy availability.
- Database alert emails contain only `Nedostupnost POSTGRES` and/or
  `Nedostupnost MSSQL`.
- Runtime alert emails contain only `Nedostupnost API`,
  `Nedostupnost DASHBOARD`, and/or `Nedostupnost CADDY`.
- Runtime probes retry once and alert once per outage transition.
- Runtime alerts use `RUNTIME_ERROR_RECIPIENTS` when configured and otherwise
  fall back to `DATABASE_ERROR_RECIPIENTS`.
- First action after restart: read the project context and this handoff, then
  run `git status --short --untracked-files=all`.

Working tree and deployment:
- `HEAD` remains `ce8b68442150fd9f1d9119e5423415e02e9fc529`.
- `origin/master` remains `a0900a7de36797ce44be49a8106ad929149ac4ed`.
- Relevant uncommitted implementation files:
  `.env.example`, `core/scheduler/scheduler.py`,
  `services/api/core/runtime_state.py`, `services/api/main.py`,
  `services/api/routes/health.py`, `services/api/README.md`,
  `tests/test_api_startup.py`, `tests/test_scheduler.py`, and
  `tests/test_dashboard_security_config.py`.
- Documentation changes are present in `AGENTS.md`,
  `DASHBOARD_SECURITY_CHECKLIST.md`, `DECISIONS.md`, and `SESSION_NOTES.md`.
- The running Uvicorn reload process has loaded the FastAPI startup correction.
- The running scheduler process has not loaded the scheduler alert changes.
- Tracked and runtime Caddyfile SHA-256 values remain equal at
  `F41D3B31EA03308CB4345B1D11F0488B11D1FE527CBF135B0E1E166E5E7BC9BE`.

Current runtime state:
- Workstation boot time: 2026-06-13 09:19:11 CEST.
- Scheduled task `API_dashboard_caddy` remains `Running` with result
  `0x41301` from 09:19:21.
- FastAPI listens on `127.0.0.1:8000`; live is HTTP 200 and ready is HTTP 503.
- Streamlit does not listen on port 8001.
- Caddy does not own ports 80, public 443, or loopback 2019. Only Tailscale
  interface-specific 443 listeners exist.
- PostgreSQL `server2a:5432` and MSSQL `server2a:1433` remain unavailable.
- Scheduler lock and heartbeat remain active. The latest quarter-hour job
  completed at 10:07:32 as `skipped (database_unavailable)`, with the next run
  scheduled for 10:16:05.

Sensitive/runtime artifacts:
- Do not print, change, delete, or commit the ignored local `.env`, API signing
  secret, email credentials, dashboard credentials, cookies, bearer tokens, or
  authentication audit records.
- Do not inspect or change SmartFuelPass browser/session artifacts.
- Do not print actual operational recipient addresses.

Expected processes and listeners after restart:
- One FastAPI/Uvicorn runtime owns `127.0.0.1:8000`.
- One Streamlit runtime owns `127.0.0.1:8001`.
- One scheduler runtime runs `main.py`, holds `scheduler_process`, and loads
  the new availability-alert behavior.
- One Caddy runtime owns ports 80 and 443 plus `127.0.0.1:2019`.
- Tailscale interface-specific 443 listeners may also remain.

Expected application and alert state:
- FastAPI `/health/live`: HTTP 200 even while PostgreSQL is unavailable.
- FastAPI `/health/ready`: HTTP 503 while PostgreSQL initialization is pending,
  then HTTP 200 after database recovery.
- Streamlit `/_stcore/health`: HTTP 200.
- HTTP hostname route: 308 to HTTPS.
- HTTPS dashboard: HTTP 200.
- Protected API, map image without cookie, and session refresh without bearer:
  HTTP 401.
- If PostgreSQL and MSSQL remain unavailable, scheduled database jobs are
  skipped and availability emails contain only the standardized database
  messages.
- If API, dashboard, or Caddy fails after startup, the next scheduled preflight
  sends only the standardized runtime message for each newly unavailable
  service.

Required post-restart checks:
- Confirm scheduled task completion/result and exactly one expected runtime
  process/listener per service.
- Confirm API live/ready semantics and Streamlit health.
- Confirm Caddy hash equality, configuration validation, admin listener, HTTP
  redirect, HTTPS dashboard, and protected route status codes.
- Confirm scheduler lock, heartbeat, next run, and one completed post-restart
  job.
- Recheck `server2a:5432` and `server2a:1433`.
- Inspect protected scheduler logs to confirm runtime checks ran, without
  printing raw connection diagnostics.
- Confirm any emitted availability email contains only the allowed
  `Nedostupnost ...` text and no job ID, URL, timestamp, or exception detail.
- Run `tests/test_scheduler.py`, `tests/test_api_startup.py`,
  `tests/test_caddy_config.py`, and
  `tests/test_dashboard_security_config.py`.
- Run Python compilation, FastAPI import, `git diff --check`, and final
  `git status --short --untracked-files=all`.

### 2026-06-13 10:55 CEST - Post-restart runtime verification

Scope:
- Verified the production cold start after the workstation boot at
  2026-06-13 10:22:27 CEST.
- No production process, runtime configuration, credential, cookie, token,
  recipient address, or authentication audit record was changed or printed.

Startup and process state:
- Scheduled task `API_dashboard_caddy` ran at 10:22:37 and completed with
  result `0`; its final state was `Ready`.
- One FastAPI listener owned `127.0.0.1:8000`.
- One Streamlit listener owned `127.0.0.1:8001`.
- One Caddy process owned ports 80 and 443 plus `127.0.0.1:2019`.
- The documented Tailscale interface-specific port 443 listeners remained in
  addition to the single Caddy public listener.

Application and routing:
- FastAPI `/health/live` returned HTTP 200.
- FastAPI `/health/ready` returned HTTP 503 because dashboard database
  initialization was still pending.
- Streamlit `/_stcore/health` and the Caddy admin endpoint returned HTTP 200.
- Explicit-loopback hostname routing returned HTTP 308 for HTTP, HTTP 200 for
  the HTTPS dashboard, and HTTP 401 for the protected API, map image without
  its session cookie, and session refresh without Bearer authentication.
- Live OpenAPI exposed the refresh route, used `APIKeyCookie` named
  `__Host-monitoring_dashboard_session` for map images, and used `HTTPBearer`
  for the normal protected map catalog route.

Database and scheduler:
- DNS resolved `server2a` to `192.168.3.250`, but TCP connections to
  PostgreSQL port 5432 and MSSQL port 1433 both failed.
- The scheduler process lock was held and the heartbeat remained within its
  configured 300-second TTL.
- The post-restart `quarter_hour_job` completed at 10:49:32 as
  `skipped (database_unavailable)`; its next run was scheduled for 11:05:05.
- Scheduler metrics reported 32 successes and 0 failures in the preceding
  24-hour window; database-unavailable skips are recorded separately.
- A read-only runtime availability probe reported API, dashboard, and Caddy
  available with no runtime failures.

Caddy and verification:
- Tracked and runtime Caddyfile SHA-256 values both remained
  `F41D3B31EA03308CB4345B1D11F0488B11D1FE527CBF135B0E1E166E5E7BC9BE`.
- `caddy validate` reported a valid runtime configuration.
- The required scheduler, API startup, Caddy, and security regression suite
  passed all 55 tests.
- Changed modules compiled, FastAPI imported successfully, and
  `git diff --check` passed with only existing line-ending warnings.
- Final working-tree status matched the pre-restart handoff; no unexpected
  tracked or untracked changes appeared.

Deviations and accepted gaps:
- PostgreSQL and MSSQL remained unavailable, so API readiness stayed HTTP 503
  and scheduled database work remained skipped.
- The complete public runtime recovered despite the database outage, which
  confirms that FastAPI liveness no longer blocks Streamlit and Caddy startup.
- No real availability email was inspected or sent during verification.
  Minimal allowed email content and removal of diagnostics were verified by
  the passing regression tests.
- No real dashboard credential, bearer token, browser cookie, authenticated
  map request, or external-network client was used.

### 2026-06-13 - Per-recipient scheduler alert detail policy

Scope:
- Added recipient-specific detail handling for operational scheduler alerts.

Changed:
- Active dashboard admin email recipients receive technical details for
  scheduler job failures/misfires, database outages, and runtime service
  outages.
- Non-admin, inactive-admin, unknown, or unverifiable recipients continue to
  receive only the existing brief alert description.
- Added a 24-hour fail-closed cache under the ignored scheduler logs
  directory. It stores only SHA-256 email hashes and is refreshed after a
  successful PostgreSQL preflight query.
- Runtime check failures now retain the checked target and sanitized reason
  for admin-only alert bodies.
- Added DEC-034 and updated scheduler operating guidance.

Verified:
- The combined scheduler, API startup, Caddy, and security suite passed all 61
  tests.
- Python compilation, scheduler/FastAPI imports, and `git diff --check`
  passed.

Not verified:
- No real alert email was sent.
- PostgreSQL remained unavailable during implementation, so a production
  admin-email cache refresh was not observed.
- The running scheduler process has not loaded this source change; activation
  requires the next supported full-runtime restart after a restart handoff.

### 2026-06-13 - SQLite database availability transition registry

Scope:
- Replaced repeated stateless database outage emails with persistent
  transition-based alerting for `quarter_hour_job`.

Changed:
- Added `core/scheduler/database_availability_state.py`.
- Added local runtime database
  `core/scheduler/data/database_availability.sqlite3` to `.gitignore`.
- SQLite stores current PostgreSQL/MSSQL state and pending/delivered transition
  events.
- The first failed quarter-hour check sends one outage email. Repeated failed
  checks update the failure count without another email.
- The first subsequent successful check sends one recovery summary with the
  observed outage start, recovery time, and duration.
- Recovery details for active admin recipients also include the latest
  sanitized reason and failed-check count.
- Non-quarter-hour jobs still skip on failed database preflight but no longer
  generate database availability emails.
- Pending events are retained for retry when email delivery fails.
- Added redaction of common URL credentials and
  `password`/`pwd`/`token`/`secret` assignments before technical details are
  stored or emailed.
- Added DEC-035 and scheduler operating guidance.

Verified:
- SQLite state, transition, persistence, delivery, and recovery tests passed.
- The combined scheduler, SQLite, API startup, Caddy, and security suite passed
  all 68 tests.
- Python compilation, scheduler/FastAPI imports, and `git diff --check`
  passed.

Not verified:
- No real alert or recovery email was sent.
- No production SQLite runtime database was created.
- PostgreSQL and MSSQL remained unavailable during implementation.
- The running scheduler has not loaded this change; activation requires the
  next supported full-runtime restart after a restart handoff.

### 2026-06-13 11:46 CEST - Pre-restart SQLite alert activation handoff

Reason for restart:
- The user explicitly requested saving the current state and restarting the
  workstation.
- Activate non-blocking FastAPI startup, per-recipient scheduler alert detail,
  and the local SQLite database availability transition registry in the
  production scheduler.
- Replace repeated quarter-hour database outage emails with one outage alert
  and one later recovery summary.

Current task/conversation state:
- Completed: implemented and tested SQLite transition persistence for
  PostgreSQL/MSSQL availability.
- Completed: database availability email generation is restricted to
  `quarter_hour_job`; other jobs still skip on failed preflight without
  sending database availability emails.
- Completed: active dashboard admin recipients receive sanitized technical
  detail; other or unverifiable recipients receive brief text.
- Completed: corrected test isolation and removed the test-created runtime
  SQLite file.
- Pending: restart the workstation and perform full post-restart verification.
- First action after restart: read `AGENTS.md`, `DECISIONS.md`,
  `SESSION_NOTES.md`, and this handoff, then run
  `git status --short --untracked-files=all`.

Working tree and deployment:
- `HEAD` is `ce8b68442150fd9f1d9119e5423415e02e9fc529` on `master`.
- `origin/master` is
  `a0900a7de36797ce44be49a8106ad929149ac4ed`.
- Modified tracked files:
  `.env.example`, `.gitignore`, `AGENTS.md`,
  `DASHBOARD_SECURITY_CHECKLIST.md`, `DECISIONS.md`, `SESSION_NOTES.md`,
  `core/scheduler/scheduler.py`, `services/api/README.md`,
  `services/api/main.py`, `services/api/routes/health.py`,
  `tests/test_dashboard_security_config.py`, and
  `tests/test_scheduler.py`.
- Untracked source/test files:
  `core/scheduler/database_availability_state.py`,
  `services/api/core/runtime_state.py`, `tests/test_api_startup.py`, and
  `tests/test_database_availability_state.py`.
- The working tree is intentionally uncommitted. Do not revert or overwrite
  these changes after restart.
- The running scheduler still uses the pre-change Python code. The scheduled
  startup task will load the working-tree implementation after restart.
- Tracked and runtime Caddyfile SHA-256 values are equal at
  `F41D3B31EA03308CB4345B1D11F0488B11D1FE527CBF135B0E1E166E5E7BC9BE`.
- Runtime Caddy configuration validated successfully before restart.
- The combined scheduler, SQLite, API startup, Caddy, and security suite passed
  all 68 tests after test-isolation correction.
- Python compilation, scheduler/FastAPI imports, and `git diff --check`
  passed.

Pre-restart runtime state:
- Workstation boot time was 2026-06-13 10:22:27 CEST.
- Scheduled task `API_dashboard_caddy` was `Ready`; its 10:22:37 run
  completed with result `0`.
- FastAPI listened on `127.0.0.1:8000`, Streamlit on
  `127.0.0.1:8001`, and Caddy on ports 80/443 plus
  `127.0.0.1:2019`.
- Tailscale interface-specific port 443 listeners were also present as
  expected.
- FastAPI live returned HTTP 200, FastAPI ready returned HTTP 503, Streamlit
  health returned HTTP 200, and the Caddy admin endpoint returned HTTP 200.
- Explicit-loopback hostname routing returned HTTP 308 for HTTP, HTTP 200 for
  HTTPS dashboard, and HTTP 401 for a protected API route without
  authentication.
- PostgreSQL `server2a:5432` and MSSQL `server2a:1433` were both unavailable.
- The scheduler process lock was held. The latest observed heartbeat was
  2026-06-13 11:42:43 CEST, within the configured 300-second TTL at the final
  check.
- The latest `quarter_hour_job` completed at 11:37:39 as
  `skipped (database_unavailable)`; the next pre-restart run was scheduled for
  11:47:05.

SQLite and alert state before restart:
- `core/scheduler/data/database_availability.sqlite3` does not exist.
- `core/scheduler/logs/admin_alert_email_hashes.json` does not exist because
  PostgreSQL has not been available to refresh active admin classification.
- The SQLite runtime path is ignored through
  `core/scheduler/data/*.sqlite3*`.
- If both databases remain unavailable, the first post-restart
  `quarter_hour_job` must create state rows for `postgres` and `mssql`, create
  one unavailable event per database, and send one combined outage alert.
- With no admin-email cache, that first outage email must use the brief
  non-admin content even for configured admin addresses.
- After successful outage email delivery, both events must have
  `delivered_at`; later unavailable checks must only increment state counters
  and must not create or send another outage event.
- On the first later successful check for a database, create one recovery
  event and send a summary containing the first failed observation, first
  successful observation, and observed duration.
- If email delivery fails, the transition event must remain pending for a
  later `quarter_hour_job` retry.

Sensitive/runtime artifacts:
- Do not print, change, delete, or commit the ignored local `.env`, API signing
  secret, email credentials, dashboard credentials, cookies, bearer tokens,
  authentication audit records, or actual operational recipient addresses.
- Do not inspect or change SmartFuelPass browser/session artifacts.
- Do not print raw SQLite `last_reason` values. Report only sanitized status,
  timestamps, counters, event types, and pending/delivered state.

Expected processes and listeners after restart:
- Scheduled task `API_dashboard_caddy` runs at system startup and completes
  with result `0`.
- One FastAPI/Uvicorn runtime owns `127.0.0.1:8000`.
- One Streamlit runtime owns `127.0.0.1:8001`.
- One scheduler runtime runs `main.py`, holds `scheduler_process`, and loads
  the SQLite transition implementation.
- One Caddy runtime owns ports 80 and 443 plus `127.0.0.1:2019`.
- Tailscale interface-specific port 443 listeners may remain in addition.

Expected application state:
- FastAPI `/health/live`: HTTP 200 even while PostgreSQL is unavailable.
- FastAPI `/health/ready`: HTTP 503 while PostgreSQL initialization remains
  pending; HTTP 200 after initialization succeeds.
- Streamlit `/_stcore/health`: HTTP 200.
- HTTP hostname route: HTTP 308 to HTTPS.
- HTTPS dashboard: HTTP 200.
- Protected API, map image without cookie, and session refresh without Bearer:
  HTTP 401.
- Scheduler lock and heartbeat remain active.
- Database jobs remain skipped while either required database is unavailable.

Required post-restart checks:
- Confirm boot time, scheduled-task run/result, process tree, and exactly one
  expected runtime listener per service.
- Confirm API live/ready semantics, Streamlit health, and Caddy admin health.
- Confirm tracked/runtime Caddyfile hash equality and run `caddy validate`.
- Confirm HTTP redirect, HTTPS dashboard, protected API, map image, and session
  refresh status codes through explicit-loopback hostname routing.
- Recheck TCP connectivity to `server2a:5432` and `server2a:1433` without
  printing credentials.
- Confirm scheduler process lock, heartbeat age, latest/next job state, and at
  least one completed post-restart `quarter_hour_job`.
- Inspect SQLite integrity, schema, service keys, availability flags,
  observation timestamps, failed-check counters, event types, and
  pending/delivered counts without printing raw reasons.
- Confirm the first outage transition sends at most one email and subsequent
  failed quarter-hour checks do not create another outage event.
- If a database recovers, verify one recovery event and summary interval.
- Run the 68-test focused suite, Python compilation, imports,
  `git diff --check`, and final `git status --short --untracked-files=all`.
- Append a dated post-restart verification entry with all deviations.

Known risks or accepted gaps:
- Database network connectivity remained unavailable immediately before
  restart.
- The exact network outage start predates SQLite activation. The first
  recorded outage start will therefore be the first failed post-restart
  quarter-hour observation, not the true historical start.
- No real outage or recovery email was sent during development verification.

### 2026-06-13 12:20 CEST - Post-restart SQLite alert verification

Scope:
- Verified the production cold start after the workstation boot at
  2026-06-13 11:49:11 CEST.
- Verified two post-restart `quarter_hour_job` database-unavailable
  observations and SQLite transition suppression.

Startup and runtime:
- Scheduled task `API_dashboard_caddy` ran at 11:49:21 and completed with
  result `0`; its final state was `Ready`.
- FastAPI listened on `127.0.0.1:8000`, Streamlit on `127.0.0.1:8001`, and
  one Caddy process owned ports 80/443 plus `127.0.0.1:2019`.
- FastAPI live returned HTTP 200, FastAPI ready returned HTTP 503, Streamlit
  health returned HTTP 200, and the Caddy admin endpoint returned HTTP 200.
- Explicit-loopback hostname routing returned HTTP 308 for HTTP, HTTP 200 for
  the HTTPS dashboard, and HTTP 401 for the protected API, map image without
  its session cookie, and session refresh without Bearer authentication.
- Tracked and runtime Caddyfile SHA-256 values remained equal at
  `F41D3B31EA03308CB4345B1D11F0488B11D1FE527CBF135B0E1E166E5E7BC9BE`;
  `caddy validate` reported a valid configuration.

Database, scheduler, and SQLite:
- PostgreSQL `server2a:5432` and MSSQL `server2a:1433` remained unreachable.
- The scheduler process lock remained held and heartbeat stayed within the
  configured 300-second TTL.
- The first post-restart `quarter_hour_job` completed at 12:07:32 as
  `skipped (database_unavailable)`.
- SQLite integrity was `ok`; one `unavailable` event was created for
  `postgres` and one for `mssql`. Both events were marked delivered at the
  same time, with no pending events.
- The second post-restart `quarter_hour_job` completed at 12:18:30 with the
  same skipped status. Both failed-check counters increased from 1 to 2,
  while the total event count remained 2 and the pending count remained 0.
  This confirms that repeated failed observations did not create or deliver
  another outage transition.
- The active-admin email hash cache remained absent because PostgreSQL was
  unavailable, so alert selection failed closed to the brief content path.
- The next observed `quarter_hour_job` run was scheduled for 12:35:05.

Verification:
- The focused scheduler, SQLite, API startup, Caddy, and security suite passed
  all 68 tests.
- Python compilation and scheduler/FastAPI imports passed.
- `git diff --check` passed with only existing line-ending warnings.
- Final working-tree entries matched the pre-restart handoff; no unexpected
  tracked or untracked files appeared.

Accepted gaps:
- No mailbox was opened, so the received email body was not inspected
  directly. Successful delivery handling is evidenced by both transition
  events having `delivered_at`; brief-content selection is also covered by
  the passing regression tests.
- No database recovery occurred, so recovery-event and recovery-email
  behavior was not exercised in production.

### 2026-06-13 12:30 CEST - Pre-restart SQLite persistence handoff

Reason for restart:
- The user explicitly requested saving the current state and restarting the
  workstation.
- Verify that the SQLite database availability state survives another full
  workstation restart and continues suppressing duplicate outage alerts.

Current task/conversation state:
- Completed: verified the 2026-06-13 11:49 cold start, complete public
  runtime recovery, and two post-restart database-unavailable observations.
- Completed: SQLite contains one delivered `unavailable` event for
  PostgreSQL and one for MSSQL; the second failed observation incremented
  counters without creating another event.
- Pending: restart the workstation and verify runtime recovery plus SQLite
  persistence across the second restart.
- First action after restart: read `AGENTS.md`, `DECISIONS.md`,
  `SESSION_NOTES.md`, and this handoff, then run
  `git status --short --untracked-files=all`.

Working tree and deployment:
- `HEAD`, `origin/master`, and `origin/HEAD` are
  `f18111e22c6231b7449b362cb53b6d87303bde07`.
- Commit `f18111e` contains the non-blocking FastAPI startup,
  recipient-specific scheduler alerts, SQLite database availability
  transitions, tests, and documentation.
- The working tree was clean before adding this handoff. After this entry,
  only `SESSION_NOTES.md` is expected to be modified.
- The production processes are running from the committed implementation.
- Tracked and runtime Caddyfile SHA-256 values are equal at
  `F41D3B31EA03308CB4345B1D11F0488B11D1FE527CBF135B0E1E166E5E7BC9BE`.
- The focused scheduler, SQLite, API startup, Caddy, and security suite passed
  all 68 tests during the preceding post-restart verification.

Pre-restart runtime state:
- Workstation boot time is 2026-06-13 11:49:11 CEST.
- Scheduled task `API_dashboard_caddy` is `Ready`; its 11:49:21 run completed
  with result `0`.
- FastAPI listens on `127.0.0.1:8000`, Streamlit on `127.0.0.1:8001`, and
  one Caddy process owns ports 80/443 plus `127.0.0.1:2019`.
- Tailscale interface-specific port 443 listeners are also present as
  expected.
- FastAPI live returns HTTP 200, FastAPI ready returns HTTP 503, Streamlit
  health returns HTTP 200, and the Caddy admin endpoint returns HTTP 200.
- Explicit-loopback hostname routing returns HTTP 308 for HTTP, HTTP 200 for
  the HTTPS dashboard, and HTTP 401 for the protected API, map image without
  its session cookie, and session refresh without Bearer authentication.
- PostgreSQL `server2a:5432` and MSSQL `server2a:1433` are both unreachable.
- The scheduler process lock is held. The latest observed heartbeat was
  2026-06-13 12:24:28 CEST, within the configured 300-second TTL.
- The latest `quarter_hour_job` completed at 12:18:30 as
  `skipped (database_unavailable)`; the next observed run was scheduled for
  12:35:05.

SQLite state before restart:
- `core/scheduler/data/database_availability.sqlite3` exists and its integrity
  check is `ok`.
- Both `postgres` and `mssql` are stored as unavailable with a common first
  failed observation at 2026-06-13 12:07:30 CEST.
- Both services have `failed_check_count=2`.
- Exactly two transition events exist: one `unavailable` event for each
  database. Both are delivered and none are pending.
- `core/scheduler/logs/admin_alert_email_hashes.json` does not exist because
  PostgreSQL has not been available for an active-admin cache refresh.
- If both databases remain unavailable after restart, the first subsequent
  `quarter_hour_job` must preserve the original outage start, increment both
  failed-check counters to 3 or higher, leave the event count at 2, and send
  no duplicate outage alert.
- If a database recovers, exactly one `recovered` event should be created for
  that database and its recovery summary should use the preserved outage
  start.

Sensitive/runtime artifacts:
- Do not print, change, delete, or commit the ignored local `.env`, API signing
  secret, email credentials, dashboard credentials, cookies, bearer tokens,
  authentication audit records, actual operational recipient addresses, or
  raw SQLite reason values.
- Do not inspect or change SmartFuelPass browser/session artifacts.

Expected processes and listeners after restart:
- Scheduled task `API_dashboard_caddy` runs at system startup and completes
  with result `0`.
- One FastAPI/Uvicorn runtime owns `127.0.0.1:8000`.
- One Streamlit runtime owns `127.0.0.1:8001`.
- One scheduler runtime runs `main.py` and holds `scheduler_process`.
- One Caddy runtime owns ports 80/443 plus `127.0.0.1:2019`.
- Tailscale interface-specific port 443 listeners may remain in addition.

Expected application state:
- FastAPI `/health/live`: HTTP 200.
- FastAPI `/health/ready`: HTTP 503 while PostgreSQL initialization remains
  pending; HTTP 200 after successful initialization.
- Streamlit `/_stcore/health`: HTTP 200.
- Caddy admin endpoint: HTTP 200.
- HTTP hostname route: HTTP 308 to HTTPS.
- HTTPS dashboard: HTTP 200.
- Protected API, map image without cookie, and session refresh without Bearer:
  HTTP 401.
- Scheduler lock and heartbeat remain active.
- Database jobs remain skipped while either required database is unavailable.

Required post-restart checks:
- Confirm boot time, scheduled-task result, process tree, and exactly one
  expected runtime listener per service.
- Confirm API live/ready semantics, Streamlit health, and Caddy admin health.
- Confirm tracked/runtime Caddyfile hash equality and run `caddy validate`.
- Confirm HTTP redirect, HTTPS dashboard, protected API, map image, and
  session refresh status codes through explicit-loopback hostname routing.
- Recheck TCP connectivity to `server2a:5432` and `server2a:1433` without
  printing credentials.
- Confirm scheduler process lock, heartbeat age, latest/next job state, and at
  least one completed post-restart `quarter_hour_job`.
- Confirm SQLite integrity and persistence of the original outage start,
  delivered event count, pending count, and failed-check counters without
  printing raw reasons.
- If databases remain unavailable, confirm the event count remains 2 after a
  post-restart failed check and counters increase without another alert.
- If a database recovers, verify one recovery event and summary interval.
- Run the focused 68-test suite, Python compilation, imports,
  `git diff --check`, and final `git status --short --untracked-files=all`.
- Append a dated post-restart verification entry with all deviations.

Known risks or accepted gaps:
- Both database network endpoints are unavailable immediately before restart.
- API readiness and scheduled database work are therefore expected to remain
  degraded until database connectivity returns.
- The received outage email body was not inspected directly in a mailbox.

### 2026-06-13 20:34 CEST - Post-restart SQLite persistence verification

Scope:
- Verified the production cold start after the workstation boot at
  2026-06-13 12:32:01 CEST.
- Verified runtime recovery and SQLite outage-state persistence across the
  second workstation restart.

Startup and runtime:
- Scheduled task `API_dashboard_caddy` ran at 12:32:11 and completed with
  result `0`; its final state was `Ready`.
- FastAPI listened on `127.0.0.1:8000`, Streamlit on `127.0.0.1:8001`, and
  one Caddy process owned ports 80/443 plus `127.0.0.1:2019`.
- FastAPI live returned HTTP 200, FastAPI ready returned HTTP 503, Streamlit
  health returned HTTP 200, and the Caddy admin endpoint returned HTTP 200.
- Explicit-loopback hostname routing returned HTTP 308 for HTTP, HTTP 200 for
  the HTTPS dashboard, and HTTP 401 for the protected API, map image without
  its session cookie, and session refresh without Bearer authentication.
- Tracked and runtime Caddyfile SHA-256 values remained equal at
  `F41D3B31EA03308CB4345B1D11F0488B11D1FE527CBF135B0E1E166E5E7BC9BE`;
  `caddy validate` reported a valid configuration.

Database, scheduler, and SQLite:
- PostgreSQL `server2a:5432` and MSSQL `server2a:1433` remained unreachable.
- The scheduler process lock was held and its heartbeat was current.
- The latest checked `quarter_hour_job` completed at 20:18:30 as
  `skipped (database_unavailable)`; its next run was scheduled for 20:35:05.
- SQLite integrity was `ok`. The original outage start remained
  2026-06-13 12:07:30 CEST for both databases.
- Both failed-check counters increased from 2 before restart to 34.
- The event registry still contained exactly two delivered `unavailable`
  events, one per database, with no pending or recovery events. No duplicate
  outage transition was created after restart.
- The active-admin email hash cache remained absent because PostgreSQL was
  unavailable, so recipient classification continued to fail closed.

Verification:
- The focused scheduler, SQLite, API startup, Caddy, and security suite passed
  all 68 tests.
- Python compilation and scheduler/FastAPI imports passed.
- `git diff --check` passed with only the existing line-ending warning for
  `SESSION_NOTES.md`.
- `HEAD` and `origin/master` both remained
  `f18111e22c6231b7449b362cb53b6d87303bde07`.

Accepted gaps:
- No database recovery occurred, so production recovery-event and
  recovery-email behavior remains unexercised.
- No mailbox was opened and no authenticated browser session was used.

### 2026-06-14 09:50 CEST - Pre-restart healthy-database handoff

Reason for restart:
- The user explicitly requested saving the current state and restarting the
  workstation.
- Renew the complete production runtime through the supported Windows startup
  task and verify cold start while PostgreSQL and MSSQL are available.

Current task/conversation state:
- Completed: verified current FastAPI, Streamlit, scheduler, Caddy, database,
  routing, authentication-boundary, and SQLite transition state.
- Completed: confirmed that the previously unavailable PostgreSQL and MSSQL
  services recovered and that both recovery events were delivered.
- Pending: restart the workstation and perform full post-restart verification.
- First action after restart: read `AGENTS.md`, `DECISIONS.md`,
  `SESSION_NOTES.md`, and this handoff, then run
  `git status --short --untracked-files=all`.

Working tree and deployment:
- `HEAD`, `origin/master`, and `origin/HEAD` are
  `f18111e22c6231b7449b362cb53b6d87303bde07`.
- Before this handoff, modified tracked files were `SESSION_NOTES.md` and the
  sensitive runtime file `data/smartfuelpass/session_cookies.json`.
- The `SESSION_NOTES.md` changes contain the previous restart handoff and
  post-restart verification plus this new handoff.
- The SmartFuelPass cookie file was not opened, changed, reverted, or staged
  during this session.
- The production processes run the committed implementation.
- Tracked and runtime Caddyfile SHA-256 values are equal at
  `F41D3B31EA03308CB4345B1D11F0488B11D1FE527CBF135B0E1E166E5E7BC9BE`.
- Runtime Caddy configuration validated successfully.
- The focused 68-test suite last passed on 2026-06-13 at the preceding
  post-restart verification. No source code changed afterward.

Pre-restart runtime state:
- Workstation boot time is 2026-06-13 12:32:01 CEST.
- Scheduled task `API_dashboard_caddy` is `Ready`; its 2026-06-13 12:32:11
  run completed with result `0`.
- FastAPI listens on `127.0.0.1:8000`, Streamlit on `127.0.0.1:8001`, and
  one Caddy process owns ports 80/443 plus `127.0.0.1:2019`.
- Tailscale interface-specific port 443 listeners are also present as
  expected.
- FastAPI live and ready both return HTTP 200. Streamlit health and the Caddy
  admin endpoint also return HTTP 200.
- Explicit-loopback hostname routing returns HTTP 308 for HTTP, HTTP 200 for
  the HTTPS dashboard, and HTTP 401 for the protected API, map image without
  its session cookie, and session refresh without Bearer authentication.
- PostgreSQL `server2a:5432` and MSSQL `server2a:1433` are both reachable.
- The scheduler process lock is held. Its latest observed heartbeat was
  2026-06-14 09:47:19 CEST, within the configured 300-second TTL.
- The latest `quarter_hour_job` completed successfully at
  2026-06-14 09:47:08 CEST; the next observed run was scheduled for 10:05:05.

SQLite and alert state before restart:
- `core/scheduler/data/database_availability.sqlite3` exists and its integrity
  check is `ok`.
- Both `postgres` and `mssql` are stored as available, with no active outage
  start and `failed_check_count=0`.
- Exactly four transition events exist: one delivered `unavailable` and one
  delivered `recovered` event for each database. No event is pending.
- The outage was first observed on 2026-06-13 12:07:30 CEST and recovery was
  first observed on 2026-06-13 21:35:05 CEST after 38 failed observations.
- `core/scheduler/logs/admin_alert_email_hashes.json` exists after successful
  PostgreSQL preflight checks. Do not print its hash values.
- If both databases remain available after restart, the first subsequent
  `quarter_hour_job` must leave the event count at four, keep both services
  available, and send no database transition alert.
- If either database becomes unavailable, exactly one new `unavailable`
  transition should be created for that service.

Sensitive/runtime artifacts:
- Do not print, change, delete, revert, stage, or commit the modified
  `data/smartfuelpass/session_cookies.json` without explicit user approval.
- Do not print, change, delete, or commit the ignored local `.env`, API
  signing secret, email credentials, dashboard credentials, cookies, bearer
  tokens, authentication audit records, operational recipient addresses, raw
  SQLite reason values, or admin email hash-cache values.
- Do not inspect or change other SmartFuelPass browser/session artifacts.

Expected processes and listeners after restart:
- Scheduled task `API_dashboard_caddy` runs at system startup and completes
  with result `0`.
- One FastAPI/Uvicorn runtime owns `127.0.0.1:8000`.
- One Streamlit runtime owns `127.0.0.1:8001`.
- One scheduler runtime runs `main.py` and holds `scheduler_process`.
- One Caddy runtime owns ports 80/443 plus `127.0.0.1:2019`.
- Tailscale interface-specific port 443 listeners may remain in addition.

Expected application state:
- FastAPI `/health/live` and `/health/ready`: HTTP 200 while PostgreSQL
  remains available.
- Streamlit `/_stcore/health` and Caddy admin endpoint: HTTP 200.
- HTTP hostname route: HTTP 308 to HTTPS.
- HTTPS dashboard: HTTP 200.
- Protected API, map image without cookie, and session refresh without Bearer:
  HTTP 401.
- PostgreSQL and MSSQL TCP checks remain reachable.
- Scheduler lock and heartbeat remain active, and database jobs run normally.

Required post-restart checks:
- Confirm boot time, scheduled-task result, process tree, and exactly one
  expected runtime listener per service.
- Confirm API live/ready semantics, Streamlit health, and Caddy admin health.
- Confirm tracked/runtime Caddyfile hash equality and run `caddy validate`.
- Confirm HTTP redirect, HTTPS dashboard, protected API, map image, and
  session refresh status codes through explicit-loopback hostname routing.
- Recheck TCP connectivity to `server2a:5432` and `server2a:1433` without
  printing credentials.
- Confirm scheduler process lock, heartbeat age, latest/next job state, and at
  least one completed post-restart `quarter_hour_job`.
- Confirm SQLite integrity, both available service states, four delivered
  transition events, no pending event, and no duplicate recovery event.
- Confirm the admin email hash cache exists without printing its values.
- Run the focused 68-test suite, Python compilation, imports,
  `git diff --check`, and final `git status --short --untracked-files=all`.
- Append a dated post-restart verification entry with all deviations.

Known risks or accepted gaps:
- The modified SmartFuelPass cookie file is an existing sensitive runtime
  change and must remain untouched.
- A database or network outage during restart can make API readiness return
  HTTP 503 and cause scheduled database jobs to skip until connectivity
  recovers.
- No mailbox was opened and no authenticated browser session was used.

### 2026-06-14 10:06 CEST - Post-restart healthy-database verification

Scope:
- Verified the production cold start after the workstation boot at
  2026-06-14 09:56:55 CEST.
- Verified the complete runtime and the first post-restart
  `quarter_hour_job` while PostgreSQL and MSSQL were available.

Startup and runtime:
- Scheduled task `API_dashboard_caddy` ran at 09:57:05 and completed with
  result `0`; its final state was `Ready`.
- FastAPI listened on `127.0.0.1:8000`, Streamlit on `127.0.0.1:8001`, and
  one Caddy process owned ports 80/443 plus `127.0.0.1:2019`.
- Tailscale interface-specific port 443 listeners were also present as
  expected.
- FastAPI live and ready, Streamlit health, and the Caddy admin endpoint all
  returned HTTP 200.
- Explicit-loopback hostname routing returned HTTP 308 for HTTP, HTTP 200 for
  the HTTPS dashboard, and HTTP 401 for the protected API, map image without
  its session cookie, and session refresh without Bearer authentication.
- Tracked and runtime Caddyfile SHA-256 values remained equal at
  `F41D3B31EA03308CB4345B1D11F0488B11D1FE527CBF135B0E1E166E5E7BC9BE`;
  `caddy validate` reported a valid configuration.

Database, scheduler, and SQLite:
- PostgreSQL `server2a:5432` and MSSQL `server2a:1433` were reachable.
- The scheduler process lock was held and the heartbeat remained within its
  configured 300-second TTL.
- The first post-restart `quarter_hour_job` completed successfully at
  10:05:08; its next run was scheduled for 10:16:05.
- SQLite integrity was `ok`. PostgreSQL and MSSQL remained stored as
  available, with no active outage and zero failed checks.
- The event registry remained at exactly four delivered events: one
  `unavailable` and one `recovered` event for each database. No event was
  pending and no duplicate recovery event was created.
- The active-admin email hash cache existed and was refreshed by the
  successful post-restart database preflight; its values were not printed.

Verification:
- The focused scheduler, SQLite, API startup, Caddy, and security suite passed
  all 68 tests.
- Python compilation and scheduler/FastAPI imports passed.
- `git diff --check` passed with only the existing line-ending warning for
  `SESSION_NOTES.md`.
- `HEAD` and `origin/master` both remained
  `f18111e22c6231b7449b362cb53b6d87303bde07`.
- Final working-tree entries remained the expected modified
  `SESSION_NOTES.md` and sensitive
  `data/smartfuelpass/session_cookies.json`; no unexpected file appeared.

Accepted gaps:
- No mailbox was opened and no authenticated browser session was used.
- Process command lines from the non-interactive scheduled-task session were
  not visible, so service identity was confirmed through listener ownership,
  health checks, scheduler metrics, and the held scheduler process lock.

### 2026-06-14 10:44 CEST - P1.10 privileged write authorization

Scope:
- Completed dashboard security checklist item P1.10.
- Inventoried browser-facing PostgreSQL/MSSQL mutations and moved revision and
  device-list writes behind FastAPI admin authorization.

Changed:
- Added admin revision create/update services and endpoints under
  `/api/v1/admin/revize`.
- Added admin device create/update services and endpoints under
  `/api/v1/admin/devices/{meter_key}`.
- Added dashboard API client methods with date/decimal serialization.
- Replaced direct PostgreSQL writes in the revision page and shared revision
  module with bearer-authenticated API calls.
- Replaced direct MSSQL writes in the shared device-list module with
  bearer-authenticated API calls.
- Added route-dependency, service-level authorization, API-client, persistence,
  and no-direct-Streamlit-write regression tests.
- Added DEC-036 and updated the security checklist and operating context.

Inventory findings:
- User administration, self-service account changes, map-layer
  administration, scheduler controls, web-search mutations, and alerting
  mutations already use authenticated FastAPI operations.
- Dashboard report pages use read-only database queries and browser download
  generation.
- Revision file actions read, preview, download, or open existing targets; no
  browser-triggered server-side file write/delete operation was found.
- Revision Excel imports are batch/off-dashboard workflows and are not exposed
  as Streamlit mutations.
- Database bootstrap, authentication persistence, scheduler jobs, trusted CLI
  operations, and batch imports remain separate non-browser write surfaces.

Verified:
- Focused P1.10 suite passed all 42 tests.
- Broader authentication, session, password, security, navigation, startup,
  map, revision, and device suite passed all 136 tests.
- Full suite passed 525 of 527 tests. The two failures are the previously
  documented unrelated failures in `tests/test_vodomery_reports.py`.
- Changed modules compiled; FastAPI and dashboard modules imported.
- Live FastAPI OpenAPI exposed all four new operations with `HTTPBearer`
  security.
- Live unauthenticated revision and device creation requests returned HTTP
  401 without opening a mutation path.
- FastAPI live/ready and Streamlit health remained HTTP 200.
- `git diff --check` passed with only existing line-ending warnings.

Not verified:
- No authenticated production revision or device record was created or
  changed, because doing so would mutate operational data.
- A real non-admin bearer token was not used against production; HTTP 403 and
  pre-database rejection are covered by dependency and service regression
  tests.
- No external-network verification was performed.

Working tree:
- Existing modified `data/smartfuelpass/session_cookies.json` remained
  untouched and must not be staged or committed without explicit approval.

### 2026-06-15 - P1.11 authorization regression coverage

Scope:
- Completed dashboard security checklist item P1.11.
- Converted the current FastAPI authorization surface into an executable route,
  role, section, page, and device contract.

Changed:
- Added `tests/test_api_authorization_regression.py` with runtime enumeration of
  all 75 `/api/v1/*` and `/health/*` operations.
- Explicitly classified five public operations and verified that all 70
  protected operations return HTTP 401 without credentials.
- Explicitly inventoried 37 admin operations and verified each with a valid
  signed non-admin token returning HTTP 403.
- Added denial coverage for every vodomery, manometry, plynomery, and web-search
  section/page route, plus positive dependency checks.
- Added allowed/disallowed identifier coverage for all non-admin
  identifier-scoped routes and pre-database service rejection tests.
- Added token-revocation tests for section, page, device, role, and activation
  changes against both bearer and browser-cookie tokens issued before the
  change.
- Expanded map catalog, feature-query, filter-query, and image cross-device
  coverage.
- Added DEC-037 and the authorization inventory rule to `AGENTS.md`.

Finding and fix:
- `get_vodomery_measurement_series`,
  `get_vodomery_prediction_profiles`, and
  `get_vodomery_recent_anomalies` caught `ValueError` before
  `AuthorizationError`.
- Because `AuthorizationError` subclasses `ValueError`, cross-device requests
  returned HTTP 422 instead of HTTP 403.
- Reordered those exception handlers so authorization failures now return HTTP
  403.

Verification:
- Focused P1.11 tests: 222 passed.
- Broader auth/admin/token/navigation/startup/map tests: 304 passed.
- Full suite: 702 passed, 2 failed. Both failures are the previously documented
  unrelated failures in `tests/test_vodomery_reports.py`.

Deployment:
- No production process was restarted during P1.11.
- The route-status correction is present in the working tree and will take
  effect in the production FastAPI process after the next supported workstation
  restart.
- The existing modified sensitive
  `data/smartfuelpass/session_cookies.json` was not read or changed.

### 2026-06-15 07:06 CEST - Pre-restart P1.11 handoff

Reason for restart:
- The user explicitly requested saving the current conversation state and
  restarting the workstation.
- Renew the complete production runtime through the supported Windows startup
  task and cold-start the completed P1.11 authorization changes.

Current task/conversation state:
- Completed: dashboard security checklist item P1.11.
- Completed: executable authorization inventory for route, role, section,
  configurable-page, device, token-revocation, and map boundaries.
- Completed: corrected three vodomery routes so cross-device
  `AuthorizationError` responses map to HTTP 403 instead of HTTP 422.
- Pending: restart the workstation and perform the post-restart verification
  listed below.
- First action after restart: read `AGENTS.md`, `DECISIONS.md`,
  `SESSION_NOTES.md`, and this handoff, then run
  `git status --short --untracked-files=all`.

Working tree and deployment:
- `HEAD`, `origin/master`, and `origin/HEAD` are
  `918d7bc0516cd080b97ddedf790fdcc3a56972ae`.
- Modified P1.11 files are:
  - `AGENTS.md`
  - `DASHBOARD_SECURITY_CHECKLIST.md`
  - `DECISIONS.md`
  - `SESSION_NOTES.md`
  - `services/api/routes/vodomery.py`
  - `tests/test_dashboard_session_security.py`
  - `tests/test_device_map_service.py`
  - `tests/test_map_layers_service.py`
- Untracked P1.11 file:
  - `tests/test_api_authorization_regression.py`
- Existing sensitive runtime modification:
  - `data/smartfuelpass/session_cookies.json`
- No P1.11 change is committed. The startup task runs directly from this
  working tree, so the cold-started services must load the uncommitted files.
- FastAPI currently starts with Uvicorn `--reload`, but no authenticated live
  cross-device request was issued against operational data. The post-restart
  focused tests are the required verification of the HTTP 403 correction.

P1.11 verification already completed:
- Focused P1.11 suite passed all 222 tests.
- Broader auth/admin/token/navigation/startup/map suite passed all 304 tests.
- Full suite passed 702 tests and retained only the two previously documented
  unrelated failures in `tests/test_vodomery_reports.py`.
- Changed Python files compiled successfully.
- `git diff --check` passed with only line-ending warnings.

Pre-restart runtime state:
- Workstation boot time is 2026-06-14 09:56:55 CEST.
- Scheduled task `API_dashboard_caddy` is `Ready`; its
  2026-06-14 09:57:05 run completed with result `0`.
- FastAPI listens on `127.0.0.1:8000`, Streamlit on `127.0.0.1:8001`, and one
  Caddy process owns ports 80/443 plus `127.0.0.1:2019`.
- Tailscale owns its expected interface-specific port 443 listeners.
- FastAPI live and ready, Streamlit health, and the Caddy admin endpoint all
  return HTTP 200.
- Explicit-loopback hostname routing returns HTTP 308 for HTTP, HTTP 200 for
  the HTTPS dashboard, and HTTP 401 for the protected API, map image without
  its session cookie, and session refresh without bearer authentication.
- PostgreSQL `server2a:5432` and MSSQL `server2a:1433` are reachable.
- The scheduler process lock is held. The latest observed heartbeat is within
  the configured 300-second TTL.
- The latest `quarter_hour_job` completed successfully at
  2026-06-15 07:05:08 CEST with no failures in the preceding 24 hours; its next
  scheduled run is 07:16:05 CEST.
- The latest `hourly_job` completed successfully at
  2026-06-15 07:02:19 CEST with no failures in the preceding 24 hours.

Caddy, SQLite, and alert state:
- Tracked and runtime Caddyfile SHA-256 values are equal at
  `F41D3B31EA03308CB4345B1D11F0488B11D1FE527CBF135B0E1E166E5E7BC9BE`.
- `caddy validate` reports a valid runtime configuration.
- `core/scheduler/data/database_availability.sqlite3` exists and its integrity
  check is `ok`.
- PostgreSQL and MSSQL are both stored as available, with no active outage and
  zero failed checks.
- Exactly four delivered transition events exist: one `unavailable` and one
  `recovered` event for each database. No event is pending.
- The active-admin email hash cache exists and was refreshed at
  2026-06-15 07:05:05 CEST. Its values were not printed.

Sensitive/runtime artifacts:
- Do not print, change, delete, revert, stage, or commit
  `data/smartfuelpass/session_cookies.json` without explicit user approval.
- Do not print, change, delete, or commit the ignored local `.env`, API signing
  secret, email credentials, dashboard credentials, cookies, bearer tokens,
  authentication audit records, operational recipient addresses, raw SQLite
  reason values, or admin email hash-cache values.
- Do not inspect or change other SmartFuelPass browser/session artifacts.

Expected processes and listeners after restart:
- Scheduled task `API_dashboard_caddy` runs at system startup and completes
  with result `0`.
- One FastAPI/Uvicorn runtime owns `127.0.0.1:8000`.
- One Streamlit runtime owns `127.0.0.1:8001`.
- One scheduler runtime runs `main.py`, holds `scheduler_process`, and updates
  `core/scheduler/logs/scheduler_metrics.json`.
- One Caddy runtime owns ports 80/443 plus `127.0.0.1:2019`.
- Tailscale interface-specific port 443 listeners may remain in addition.

Expected application state:
- FastAPI `/health/live` and `/health/ready`: HTTP 200 while PostgreSQL remains
  available.
- Streamlit `/_stcore/health` and the Caddy admin endpoint: HTTP 200.
- HTTP hostname route: HTTP 308 to HTTPS.
- HTTPS dashboard: HTTP 200.
- Protected API, map image without cookie, and session refresh without bearer:
  HTTP 401.
- PostgreSQL and MSSQL TCP checks remain reachable.
- Scheduler lock and heartbeat remain active, and database jobs run normally.
- The P1.11 route inventory remains at 75 application operations, five
  explicitly public operations, 70 protected operations, and 37 admin
  operations unless an intentional route change occurs.
- Unassigned identifiers on the three corrected vodomery routes map to HTTP
  403, not HTTP 422.

Required post-restart checks:
- Confirm boot time, scheduled-task result, process tree, and exactly one
  expected runtime listener per service.
- Confirm API live/ready semantics, Streamlit health, and Caddy admin health.
- Confirm tracked/runtime Caddyfile hash equality and run `caddy validate`.
- Confirm HTTP redirect, HTTPS dashboard, protected API, map image, and session
  refresh status codes through explicit-loopback hostname routing.
- Recheck TCP connectivity to `server2a:5432` and `server2a:1433` without
  printing credentials.
- Confirm scheduler process lock, heartbeat age, latest/next job state, and at
  least one completed post-restart `quarter_hour_job`.
- Confirm SQLite integrity, both available service states, four delivered
  transition events, no pending event, and no duplicate recovery event.
- Confirm the admin email hash cache exists without printing its values.
- Run:
  `.venv\Scripts\python.exe -m pytest
  tests\test_api_authorization_regression.py
  tests\test_dashboard_session_security.py tests\test_map_routes.py
  tests\test_map_layers_service.py tests\test_device_map_service.py
  -q --tb=short`
  and expect 222 passing tests.
- Compile the changed Python modules, import FastAPI, run `git diff --check`,
  and finish with `git status --short --untracked-files=all`.
- Append a dated post-restart verification entry with all deviations.

Known risks or accepted gaps:
- The modified SmartFuelPass cookie file is an existing sensitive runtime
  change and must remain untouched.
- P1.11 changes are uncommitted and depend on the current working tree being
  preserved across restart.
- A database or network outage during restart can make API readiness return
  HTTP 503 and cause scheduled database jobs to skip until connectivity
  recovers.
- No authenticated production cross-device request, mailbox access, or
  operational data mutation was performed.

### 2026-06-15 07:24 CEST - Post-restart P1.11 verification

Scope:
- Verified the production cold start after the workstation boot at
  2026-06-15 07:12:42 CEST.
- Verified the complete runtime and the first post-restart
  `quarter_hour_job` with the uncommitted P1.11 authorization changes loaded
  from the preserved working tree.

Startup and runtime:
- Scheduled task `API_dashboard_caddy` ran at 07:12:52 and completed with
  result `0`; its final state was `Ready`.
- FastAPI listened on `127.0.0.1:8000`, Streamlit on `127.0.0.1:8001`, and
  one Caddy process owned ports 80/443 plus `127.0.0.1:2019`.
- Tailscale interface-specific port 443 listeners were also present as
  expected.
- FastAPI live and ready, Streamlit health, and the Caddy admin endpoint all
  returned HTTP 200.
- Explicit-loopback hostname routing returned HTTP 308 for HTTP, HTTP 200 for
  the HTTPS dashboard, and HTTP 401 JSON for the protected API, map image
  without its session cookie, and session refresh without bearer
  authentication.
- Tracked and runtime Caddyfile SHA-256 values remained equal at
  `F41D3B31EA03308CB4345B1D11F0488B11D1FE527CBF135B0E1E166E5E7BC9BE`;
  `caddy validate` reported a valid configuration.

Database and scheduler:
- PostgreSQL `server2a:5432` and MSSQL `server2a:1433` were reachable.
- The scheduler process lock was held and the heartbeat remained within its
  configured 300-second TTL.
- The first post-restart `quarter_hour_job` completed successfully at
  07:16:10 CEST with zero failures in the preceding 24 hours; its next run was
  scheduled for 07:35:05 CEST.
- SQLite integrity was `ok`. PostgreSQL and MSSQL remained stored as
  available, with no active outage and zero failed checks.
- The event registry remained at exactly four delivered events: one
  `unavailable` and one `recovered` event for each database. No event was
  pending and no duplicate recovery event was created.
- The active-admin email hash cache existed and was refreshed at
  07:16:07 CEST; its values were not printed.

P1.11 verification:
- The required authorization, session, map-route, map-layer, and device-map
  suite passed all 222 tests.
- The executable route inventory therefore remained at 75 application
  operations, five public operations, 70 protected operations, and 37 admin
  operations.
- The three corrected Vodomery authorization paths retained HTTP 403 behavior
  for unassigned identifiers through the focused regression coverage.
- Changed Python modules compiled and FastAPI/Vodomery imports passed.
- `git diff --check` passed with only existing line-ending warnings.

Deviations and accepted gaps:
- No deviation from the pre-restart handoff was found.
- Process command lines in the non-interactive scheduled-task session were not
  visible; service identity was confirmed through listener ownership, process
  topology, health checks, scheduler metrics, and the held scheduler lock.
- No authenticated production cross-device request, mailbox access, or
  operational data mutation was performed.
- The existing sensitive modification to
  `data/smartfuelpass/session_cookies.json` remained untouched.

### 2026-06-15 07:35 CEST - P1.12 security response headers

Scope:
- Completed dashboard security checklist item 12.
- Added and deployed reviewed security response headers for the public
  Streamlit and same-origin FastAPI surfaces.

Changed:
- Added HSTS with a one-year max age and no subdomain/preload scope.
- Added `X-Content-Type-Options: nosniff`,
  `Referrer-Policy: strict-origin-when-cross-origin`, and
  `X-Frame-Options: SAMEORIGIN`.
- Added a restrictive `Permissions-Policy` that disables unused capabilities
  while preserving `geolocation=(self)` for the map page.
- Added a Streamlit-compatible `Content-Security-Policy-Report-Only` covering
  inline runtime code, WebSockets, local iframe components, HTTPS map tiles,
  and data/blob resources.
- Removed public `Server` and `Via` response headers.
- Added Caddy regression coverage and documented DEC-038 and the deployment
  behavior.

Deployment:
- The tracked Caddy configuration validated with Caddy 2.11.4.
- The deployment script created
  `Caddyfile.pre-deploy-20260615-073310`, synchronized the runtime file, and
  reloaded the existing Caddy process through the loopback admin API.
- Tracked and runtime Caddyfile SHA-256 values both became
  `3387659A473097A43B76B7951D833463F77F7C0AC559975271EA3F48B59D1802`.
- One Caddy process continued to own ports 80/443 and `127.0.0.1:2019`; no
  duplicate runtime was started.

Verified:
- Four Caddy configuration tests passed.
- The broader Caddy, authentication, session, authorization, map, and
  responsive-dashboard suite passed all 273 tests.
- Live dashboard HTTP 200 and protected FastAPI HTTP 401 responses contained
  the complete security header set and contained neither `Server` nor `Via`.
- HTTP continued to redirect to HTTPS with status 308.
- FastAPI live/ready, Streamlit health, and the Caddy admin endpoint remained
  HTTP 200.
- A direct Streamlit WebSocket handshake returned HTTP 101 and included the
  enforced HSTS and `nosniff` headers.
- The public dashboard HTML referenced local Streamlit scripts and styles; no
  external executable script or stylesheet origin was present.

Accepted gap:
- CSP remains report-only. No authenticated production browser session or
  mobile geolocation prompt was used during this change.
- The existing sensitive modification to
  `data/smartfuelpass/session_cookies.json` remained untouched.

### 2026-06-15 08:25 CEST - Pre-restart P1.13 handoff

Reason for restart:
- Activate the hardened production process configuration for dashboard
  security checklist item P1.13 through the supported Windows startup task.
- Replace the currently running pre-change `.venv`/Uvicorn reload process set
  with the exact `.venv-production` runtime and non-reload launch arguments.

Current task/conversation state:
- Completed: separated production and development launchers.
- Completed: removed `--reload` from every production launcher and set
  Uvicorn to one worker on `127.0.0.1:8000`.
- Completed: kept development reload only in explicitly named
  `scripts/start_api_dev.ps1` and `scripts/start_all_services_dev.ps1`.
- Completed: added reviewed direct dependency pins and an exact 82-package
  direct/transitive lock for CPython 3.14 on Windows.
- Completed: created and verified the ignored local `.venv-production`.
- Completed: added fail-closed environment verification and rotating
  API/Streamlit/Caddy output logs.
- Completed: documented restart, retention, listener, and operating-account
  behavior in AGENTS, DEC-039, the security checklist, API README, and public
  deployment guidance.
- Pending: restart the workstation and perform the post-restart verification
  below before marking the P1.13 completion criterion operationally verified.
- First action after restart: read `AGENTS.md`, `DECISIONS.md`,
  `SESSION_NOTES.md`, and this handoff, then run
  `git status --short --untracked-files=all`.

P1.13 implementation:
- Production uses `.venv-production`; startup rejects Python versions other
  than 3.14, pip versions other than 26.1.2, missing/mismatched locked
  packages, and unlocked installed packages.
- `requirements-production.in` contains 22 reviewed direct pins.
- `requirements-production.lock.txt` contains 82 exact direct and transitive
  pins and has SHA-256
  `25A86320E4290817842D9CC0CB3D5AB975C3CA8E10D79306F0E5B2988F99092F`.
- API, Streamlit, and a fresh Caddy start write combined output under
  `C:\ProgramData\monitorovaci_platforma\logs` with 10 MiB files and 10
  backups.
- Scheduler logging remains daily rotated with 14 backups. Authentication
  audit retention remains separately configured for 90 days.
- The task retries launcher-level failure three times at one-minute intervals,
  but does not supervise a child after launcher completion. A later child
  failure still requires the supported full-workstation restart.
- The scheduled task currently runs as `tra`, uses password logon, and has
  `RunLevel=Highest`. This is an accepted least-privilege gap pending a
  separate migration to a dedicated non-interactive account with validated
  project, protected-config, ProgramData, database, network-share, listener,
  and Caddy certificate rights.

Working tree and deployment:
- `HEAD`, `origin/master`, and `origin/HEAD` are
  `918d7bc0516cd080b97ddedf790fdcc3a56972ae`.
- Modified files are:
  - `.gitignore`
  - `AGENTS.md`
  - `Caddyfile`
  - `DASHBOARD_SECURITY_CHECKLIST.md`
  - `DECISIONS.md`
  - `PUBLIC_HTTPS_DEPLOYMENT.md`
  - `SESSION_NOTES.md`
  - `data/smartfuelpass/session_cookies.json`
  - `requirements-api.txt`
  - `run.txt`
  - `scripts/start_all_services.ps1`
  - `scripts/start_api.ps1`
  - `services/api/README.md`
  - `services/api/routes/vodomery.py`
  - `start_api_dashboard - kopie.bat`
  - `start_api_dashboard.bat`
  - `tests/test_caddy_config.py`
  - `tests/test_dashboard_session_security.py`
  - `tests/test_device_map_service.py`
  - `tests/test_map_layers_service.py`
- Untracked files are:
  - `requirements-production.in`
  - `requirements-production.lock.txt`
  - `scripts/bootstrap_production_environment.ps1`
  - `scripts/run_with_rotating_log.py`
  - `scripts/start_all_services_dev.ps1`
  - `scripts/start_api_dev.ps1`
  - `scripts/verify_production_environment.py`
  - `tests/test_api_authorization_regression.py`
  - `tests/test_production_runtime.py`
- The ignored `.venv-production` is a required local deployment artifact and
  must remain present across restart.
- No P1.13 file is committed. The startup task runs directly from this working
  tree and will load the uncommitted launcher and lock.
- P1.13 launcher changes are not active in the current production process set:
  the workstation booted at 07:12:42 CEST, before these files and
  `.venv-production` were prepared.
- P1.12 Caddy headers are already deployed. Tracked and runtime Caddyfile
  SHA-256 values match at
  `3387659A473097A43B76B7951D833463F77F7C0AC559975271EA3F48B59D1802`,
  and the runtime configuration validates.

P1.13 verification already completed:
- The bootstrap created `.venv-production` successfully, pinned pip 26.1.2,
  installed the exact lock, passed `pip check`, and passed the fail-closed
  environment verifier.
- FastAPI, Streamlit, pandas, SQLAlchemy, reportlab, openpyxl, PostgreSQL and
  MSSQL drivers, the API application, and scheduler modules imported from the
  production environment.
- Every active Streamlit page loaded from the production environment without a
  missing-module error.
- A temporary production Uvicorn instance returned HTTP 200 on
  `127.0.0.1:8010`; its command line did not contain `--reload`.
- A temporary production Streamlit instance returned HTTP 200 on
  `127.0.0.1:8011/_stcore/health`.
- Both temporary processes were stopped and ports 8010/8011 were confirmed
  closed.
- Production launcher dry-run showed `.venv-production`, one Uvicorn worker,
  loopback API/Streamlit bindings, and rotating-log wrappers.
- PowerShell parsing passed for all new and changed launcher/bootstrap scripts.
- Focused production, Caddy, and security configuration tests passed all 21
  tests.
- Full suite passed 710 tests. The only two failures are the previously
  documented unrelated `tests/test_vodomery_reports.py` failures.
- Changed Python files compiled and `git diff --check` passed with only
  line-ending warnings.

Pre-restart runtime state:
- Workstation boot time is 2026-06-15 07:12:42 CEST.
- Scheduled task `API_dashboard_caddy` is `Ready`; its 07:12:52 run completed
  with result `0`.
- Task settings are password logon, `RunLevel=Highest`,
  `MultipleInstances=IgnoreNew`, three one-minute restart attempts, and
  `StartWhenAvailable=True`.
- FastAPI listens on `127.0.0.1:8000`, Streamlit on `127.0.0.1:8001`, and one
  Caddy process owns ports 80/443 plus `127.0.0.1:2019`.
- Tailscale owns its expected interface-specific port 443 listeners.
- FastAPI live and ready, Streamlit health, and Caddy admin health return HTTP
  200.
- Explicit-loopback hostname routing returns HTTP 308 for HTTP, HTTP 200 for
  the HTTPS dashboard, and HTTP 401 for the protected API, map image without
  its session cookie, and session refresh without bearer authentication.
- PostgreSQL `server2a:5432` and MSSQL `server2a:1433` are reachable.
- Scheduler metrics report `scheduler_running=True`; the process lock is held
  and the heartbeat is within the configured 300-second TTL.
- `quarter_hour_job` last completed successfully at 08:16:07 with zero
  failures in 24 hours; its next run is 08:35:05.
- `hourly_job` last completed successfully at 08:02:19 with zero failures in
  24 hours; its next run is 09:02:05.
- SQLite integrity is `ok`. PostgreSQL and MSSQL are stored as available, have
  no active outage, and have zero failed checks.
- The event registry has four delivered events, no pending event, and no
  duplicate recovery event.
- The active-admin email hash cache exists and was refreshed at 08:16:05; its
  values were not printed.

Sensitive/runtime artifacts:
- Do not print, change, delete, revert, stage, or commit
  `data/smartfuelpass/session_cookies.json` without explicit user approval.
- Do not print, change, delete, or commit the ignored local `.env`, API signing
  secret, email credentials, dashboard credentials, cookies, bearer tokens,
  authentication audit records, operational recipient addresses, raw SQLite
  reason values, or admin email hash-cache values.
- Do not inspect or change other SmartFuelPass browser/session artifacts.
- Do not delete or rebuild `.venv-production` during post-restart verification
  unless its exact verifier fails and the user approves remediation.

Expected processes and listeners after restart:
- Scheduled task `API_dashboard_caddy` runs at system startup and completes
  with result `0`.
- One rotating-log wrapper owns one non-reload Uvicorn child that listens only
  on `127.0.0.1:8000`.
- One rotating-log wrapper owns one Streamlit child that listens only on
  `127.0.0.1:8001`.
- One scheduler runtime runs `main.py`, holds `scheduler_process`, and updates
  `core/scheduler/logs/scheduler_metrics.json`.
- One rotating-log wrapper owns one Caddy runtime that listens on ports 80/443
  plus admin `127.0.0.1:2019`.
- Tailscale interface-specific port 443 listeners may remain in addition.
- No listener exists on temporary ports 8010 or 8011.

Expected application and log state:
- `.venv-production\Scripts\python.exe
  scripts\verify_production_environment.py` succeeds and `pip check` reports no
  broken requirements.
- FastAPI `/health/live` and `/health/ready`: HTTP 200 while PostgreSQL remains
  available.
- Streamlit `/_stcore/health` and the Caddy admin endpoint: HTTP 200.
- HTTP hostname route: HTTP 308 to HTTPS.
- HTTPS dashboard: HTTP 200.
- Protected API, map image without cookie, and session refresh without bearer:
  HTTP 401.
- `C:\ProgramData\monitorovaci_platforma\logs\api.log`,
  `dashboard.log`, and `caddy.log` exist and contain startup records without
  secrets.
- `api.log` contains a normal Uvicorn server start and does not contain a
  Uvicorn reloader/watchfiles start.
- Scheduler lock and heartbeat remain active, and database jobs run normally.

Required post-restart checks:
- Confirm boot time, scheduled-task result/settings, process tree, and exactly
  one expected listener owner per production service.
- Confirm `.venv-production` exact-lock verification and `pip check`.
- Confirm API live/ready semantics, Streamlit health, and Caddy admin health.
- Confirm tracked/runtime Caddyfile hash equality and run `caddy validate`.
- Confirm HTTP redirect, HTTPS dashboard, protected API, map image, and session
  refresh status codes through explicit-loopback hostname routing.
- Confirm API/Streamlit/Caddy log creation and inspect only safe startup lines;
  verify the API log has no reloader/watchfiles startup.
- Recheck TCP connectivity to `server2a:5432` and `server2a:1433` without
  printing credentials.
- Confirm scheduler process lock, heartbeat age, latest/next job state, and at
  least one completed post-restart `quarter_hour_job`.
- Confirm SQLite integrity, both available service states, four delivered
  transition events, no pending event, and no duplicate recovery event.
- Confirm the admin email hash cache exists without printing its values.
- Run:
  `.venv\Scripts\python.exe -m pytest
  tests\test_production_runtime.py tests\test_caddy_config.py
  tests\test_dashboard_security_config.py -q --tb=short`
  and expect 21 passing tests.
- Compile the changed Python modules, import FastAPI and scheduler through
  `.venv-production`, run `git diff --check`, and finish with
  `git status --short --untracked-files=all`.
- Append a dated post-restart P1.13 verification entry with all deviations and
  only then mark the completion criterion operationally verified.

Known risks or accepted gaps:
- The modified SmartFuelPass cookie file is an existing sensitive runtime
  change and must remain untouched.
- P1.11-P1.13 changes are uncommitted and depend on the current working tree
  and ignored `.venv-production` being preserved across restart.
- A database or network outage during restart can make API readiness return
  HTTP 503 and cause scheduled database jobs to skip until connectivity
  recovers.
- The current scheduled-task account remains broader than least privilege.
- The launcher does not independently restart a child that fails after startup.
- No authenticated production browser workflow, mailbox access, or
  operational data mutation was performed.

### 2026-06-16 - SmartFuelPass charge sessions fetch fix

Scope:
- Investigated failed `daily_job` and `smartfuelpass_weekly_report_job`
  alerts caused by SmartFuelPass charge-session loading.
- Confirmed both failures were isolated to the SmartFuelPass portal fetch path,
  not PostgreSQL, MSSQL, scheduler liveness, DB upsert, or email delivery.

Changed:
- Removed the `open_summary()` / `Celkově` click from
  `fetch_charge_sessions_dataframe()` because the portal no longer loads the
  charge-session table after that filter is clicked.
- Updated the SmartFuelPass service regression test so the fetch flow fails if
  it tries to click the summary/all filter.

Verified:
- `.venv\Scripts\python.exe -m pytest tests\test_smartfuelpass_service.py
  tests\test_smartfuelpass_sync.py -q --tb=short` passed 29 tests.
- `.venv-production\Scripts\python.exe -m py_compile
  moduly\apps\smartfuelpass\service.py` passed.
- Live SmartFuelPass read-only fetch through the production Python runtime
  succeeded with a temporary cookie file in `%TEMP%`: 17 source rows and 11
  columns were loaded.
- Sync row building on the live dataframe, without PostgreSQL writes, produced
  8 completed rows, 0 invalid rows, and 0 missing IDs.
- Report building, without PDF render or email send, produced 17 source rows,
  8 valid rows, and 0 invalid rows.
- `git diff --check -- moduly\apps\smartfuelpass\service.py
  tests\test_smartfuelpass_service.py` passed with only existing line-ending
  warnings.

Not verified:
- No production database upsert was performed.
- No SmartFuelPass weekly email was sent.
- The full test suite was not run for this narrow SmartFuelPass flow change.

Decisions/notes:
- `data/smartfuelpass/session_cookies.json` remains unchanged for now by user
  request.
- Headless login without a persistent cookie was proven functional during
  read-only checks, but removing persistent cookie storage remains a future
  design change rather than part of this fix.

### 2026-06-16 - Dashboard security checklist P2.14

Scope:
- Continued `DASHBOARD_SECURITY_CHECKLIST.md` implementation with P2.14
  public endpoint exposure hardening.

Changed:
- Added `API_ENABLE_DOCS` to FastAPI settings with default `false`.
- Registered `/docs`, `/redoc`, and `/openapi.json` only when
  `API_ENABLE_DOCS=true` is set explicitly.
- Refactored `services/api/main.py` to use a small `create_api_app()` factory
  so route exposure can be tested without relying on the local `.env`.
- Added regression tests for disabled/enabled documentation routes, minimal
  health responses, and Caddy route exposure.
- Documented that `/api/v1/auth/users-exist` intentionally remains public as
  a minimal boolean bootstrap endpoint for the active Streamlit login page.
- Updated `DASHBOARD_SECURITY_CHECKLIST.md`, `.env.example`,
  `services/api/README.md`, and `DECISIONS.md`.

Verified:
- `.venv\Scripts\python.exe -m pytest tests\test_api_public_exposure.py
  tests\test_dashboard_security_config.py tests\test_caddy_config.py
  tests\test_api_authorization_regression.py -q --tb=short` passed 182 tests.
- `.venv-production\Scripts\python.exe -m py_compile services\api\main.py
  services\api\core\config.py` passed.

Not verified:
- The running production API process was not restarted, so the new FastAPI
  documentation-route setting will activate on the next normal API restart.
- No external network route scan was performed in this step.

Decisions/notes:
- P2.14 is implemented in code and tests. Runtime activation of the FastAPI
  docs setting follows the existing no-reload production restart model.

### 2026-06-16 09:08 CEST - Pre-restart handoff

Reason for restart:
- The user requested saving the current work, restarting the workstation, and
  checking runtime state after restart.
- Activate the current working-tree runtime changes through the supported
  Windows startup task, including the SmartFuelPass fetch fix, P2.14 FastAPI
  documentation-route hardening, and the previously prepared P1.13 production
  process configuration.

Current task/conversation state:
- Completed: SmartFuelPass charge-session fetch no longer clicks
  `open_summary()` / `Celkove`, because that portal filter no longer loads the
  table.
- Completed: live read-only SmartFuelPass verification through the production
  Python runtime loaded 17 source rows and built 8 valid report/sync rows
  without database writes or email sends.
- Completed: dashboard security checklist P2.14 implementation in code and
  tests. FastAPI docs are disabled by default and enabled only with
  `API_ENABLE_DOCS=true`.
- Completed: `/api/v1/auth/users-exist` remains public by decision as a
  minimal boolean bootstrap endpoint for the active Streamlit login page.
- Completed: targeted P2.14 tests passed 182 tests, and changed FastAPI modules
  compiled under `.venv-production`.
- Pending after restart: verify the startup task loads the current working
  tree, production services start once, FastAPI docs are unavailable by
  default, the public route surface remains correct, and SmartFuelPass fetch
  works without the removed `Celkove` click.
- First action after restart: read `AGENTS.md`, `DECISIONS.md`,
  `SESSION_NOTES.md`, and this handoff, then run
  `git status --short --untracked-files=all`.

Working tree and deployment:
- Current time captured before restart: 2026-06-16 09:08:14 CEST.
- Branch: `master`.
- `HEAD`: `918d7bc0516cd080b97ddedf790fdcc3a56972ae`.
- No git commit was created for this restart handoff.
- `git status --short --untracked-files=all` before restart:
  - `M .env.example`
  - `M .gitignore`
  - `M AGENTS.md`
  - `M Caddyfile`
  - `M DASHBOARD_SECURITY_CHECKLIST.md`
  - `M DECISIONS.md`
  - `M PUBLIC_HTTPS_DEPLOYMENT.md`
  - `M SESSION_NOTES.md`
  - `M data/smartfuelpass/session_cookies.json`
  - `M moduly/apps/smartfuelpass/service.py`
  - `M requirements-api.txt`
  - `M run.txt`
  - `M scripts/start_all_services.ps1`
  - `M scripts/start_api.ps1`
  - `M services/api/README.md`
  - `M services/api/core/config.py`
  - `M services/api/main.py`
  - `M services/api/routes/vodomery.py`
  - `M start_api_dashboard - kopie.bat`
  - `M start_api_dashboard.bat`
  - `M tests/test_caddy_config.py`
  - `M tests/test_dashboard_security_config.py`
  - `M tests/test_dashboard_session_security.py`
  - `M tests/test_device_map_service.py`
  - `M tests/test_map_layers_service.py`
  - `M tests/test_smartfuelpass_service.py`
  - `?? .idea/pyProjectModel.xml`
  - `?? requirements-production.in`
  - `?? requirements-production.lock.txt`
  - `?? scripts/bootstrap_production_environment.ps1`
  - `?? scripts/run_with_rotating_log.py`
  - `?? scripts/start_all_services_dev.ps1`
  - `?? scripts/start_api_dev.ps1`
  - `?? scripts/verify_production_environment.py`
  - `?? tests/test_api_authorization_regression.py`
  - `?? tests/test_api_public_exposure.py`
  - `?? tests/test_production_runtime.py`
- Tracked root `Caddyfile` SHA-256 before restart:
  `3387659A473097A43B76B7951D833463F77F7C0AC559975271EA3F48B59D1802`.
- Existing runtime process state before restart:
  - FastAPI health live: HTTP 200 on `127.0.0.1:8000`.
  - FastAPI health ready: HTTP 200 on `127.0.0.1:8000`.
  - Streamlit health: HTTP 200 on `127.0.0.1:8001`.
  - Loopback listeners: `127.0.0.1:8000` owned by PID 10076,
    `127.0.0.1:8001` owned by PID 10944, and `127.0.0.1:2019` owned by
    PID 10528.
  - Scheduled task `API_dashboard_caddy`: `Ready`; last run
    2026-06-15 10:02:24 CEST; result `0`.
  - PostgreSQL `server2a:5432` and MSSQL `server2a:1433` TCP checks returned
    reachable without printing credentials.
- Scheduler metrics before restart:
  - `quarter_hour_job`: last success at 2026-06-16 09:05:09 CEST; next run
    2026-06-16 09:16:05 CEST; zero failures in the last 24 hours.
  - `hourly_job`: last success at 2026-06-16 09:02:19 CEST; next run
    2026-06-16 10:02:05 CEST; zero failures in the last 24 hours.
  - `daily_job`: last error at 2026-06-16 00:22:54 CEST from the pre-fix
    SmartFuelPass `sync_charge_sessions_to_db` failure.
  - `smartfuelpass_weekly_report_job`: last error at 2026-06-16 07:02:45 CEST
    from the pre-fix SmartFuelPass `send_charge_sessions_report_email`
    failure.

Sensitive/runtime artifacts:
- Do not print, change, delete, revert, stage, or commit
  `data/smartfuelpass/session_cookies.json` without explicit user approval.
  The user explicitly chose to leave this file as-is for now.
- Do not print, change, delete, or commit the ignored local `.env`,
  `API_TOKEN_SECRET`, email credentials, dashboard credentials, cookies,
  bearer tokens, authentication audit records, operational recipient addresses,
  raw SQLite reason values, or admin email hash-cache values.
- Do not inspect or change other SmartFuelPass browser/session artifacts unless
  needed for a user-approved SmartFuelPass session-storage change.
- Keep the ignored `.venv-production` local deployment artifact present across
  restart.

Expected processes and listeners after restart:
- Windows Task Scheduler runs `API_dashboard_caddy` at system startup and the
  latest run result becomes `0`.
- One rotating-log wrapper owns one non-reload Uvicorn child on
  `127.0.0.1:8000`.
- One rotating-log wrapper owns one Streamlit child on `127.0.0.1:8001`.
- One scheduler runtime runs `main.py`, holds the `scheduler_process` lock, and
  updates `core/scheduler/logs/scheduler_metrics.json`.
- One Caddy runtime owns TCP 80/443 and admin `127.0.0.1:2019`.
- Tailscale interface-specific port 443 listeners may remain in addition.
- No listener should remain on temporary ports 8010 or 8011.

Expected application state after restart:
- `.venv-production\Scripts\python.exe
  scripts\verify_production_environment.py` succeeds and `pip check` reports no
  broken requirements.
- FastAPI `/health/live` returns HTTP 200.
- FastAPI `/health/ready` returns HTTP 200 while PostgreSQL remains available;
  HTTP 503 is acceptable only if database initialization is still retrying
  during a database outage.
- Streamlit `/_stcore/health` and the Caddy admin endpoint return HTTP 200.
- HTTP hostname route redirects to HTTPS with HTTP 308.
- HTTPS dashboard returns HTTP 200.
- Protected API, map image without cookie, and session refresh without bearer
  return HTTP 401.
- FastAPI docs are disabled by default after the restart:
  `/docs`, `/redoc`, and `/openapi.json` are not registered unless
  `API_ENABLE_DOCS=true` is explicitly set.
- The public Caddy hostname continues to route only `/api/*` to FastAPI and all
  other paths to Streamlit.
- `GET /api/v1/auth/users-exist` remains intentionally public and returns only
  the minimal boolean bootstrap response.
- SmartFuelPass charge-session fetch works without the `Celkove` click.

Required post-restart checks:
- Read the context files and run `git status --short --untracked-files=all`.
- Confirm boot time, scheduled-task last run/result/settings, process tree, and
  exactly one expected listener owner per service.
- Confirm `.venv-production` exact-lock verification and `pip check`.
- Confirm API live/ready, Streamlit health, and Caddy admin health.
- Confirm tracked/runtime Caddyfile hash equality and run Caddy validation.
- Confirm HTTP redirect, HTTPS dashboard, protected API, map image, and session
  refresh status codes through explicit-loopback hostname routing.
- Confirm `/docs`, `/redoc`, and `/openapi.json` are not API documentation
  routes in the restarted FastAPI runtime unless `API_ENABLE_DOCS=true` is
  intentionally configured.
- Confirm `/api/v1/auth/users-exist` remains HTTP 200 with a minimal boolean
  response and no account details.
- Recheck TCP connectivity to `server2a:5432` and `server2a:1433` without
  printing credentials.
- Confirm scheduler process lock, heartbeat age, latest/next job state, and at
  least one completed post-restart `quarter_hour_job`.
- Confirm SmartFuelPass read-only fetch through the production Python runtime
  with a temporary cookie path, no DB write, and no email send.
- Run:
  `.venv\Scripts\python.exe -m pytest
  tests\test_api_public_exposure.py tests\test_dashboard_security_config.py
  tests\test_caddy_config.py tests\test_api_authorization_regression.py
  tests\test_smartfuelpass_service.py tests\test_smartfuelpass_sync.py
  tests\test_production_runtime.py -q --tb=short`
- Compile changed Python modules through `.venv-production`:
  `.venv-production\Scripts\python.exe -m py_compile
  services\api\main.py services\api\core\config.py
  moduly\apps\smartfuelpass\service.py`
- Run `git diff --check` for changed files and finish with
  `git status --short --untracked-files=all`.
- Append a dated post-restart verification entry with deviations and accepted
  gaps.

Known risks or accepted gaps:
- `data/smartfuelpass/session_cookies.json` is still a tracked sensitive
  runtime/session artifact by explicit current decision.
- P1.11-P1.14 and SmartFuelPass changes are uncommitted and depend on the
  current working tree being preserved across restart.
- A database or network outage during restart can make API readiness return
  HTTP 503 and cause scheduled database jobs to skip until connectivity
  recovers.
- The current scheduled-task account remains broader than least privilege.
- The launcher does not independently restart a child that fails after startup.

### 2026-06-16 10:11 CEST - Post-restart verification

Scope:
- Checked runtime state after the Windows workstation restart requested on
  2026-06-16.

Changed:
- Added this post-restart verification note only.

Verified:
- Workstation boot time was 2026-06-16 10:03:08 CEST.
- Scheduled task `API_dashboard_caddy` last ran at 2026-06-16 10:03:18 CEST
  with result `0`, state `Ready`, and zero missed runs.
- Expected listeners were present: Caddy on ports 80/443 and
  `127.0.0.1:2019`, FastAPI on `127.0.0.1:8000`, Streamlit on
  `127.0.0.1:8001`, and no listeners on temporary ports 8010 or 8011.
- Tailscale interface-specific port 443 listeners were present as expected.
- `.venv-production` matched `requirements-production.lock.txt`, and
  `pip check` reported no broken requirements.
- FastAPI `/health/live`, FastAPI `/health/ready`, Streamlit
  `/_stcore/health`, and Caddy admin `/config/` returned HTTP 200.
- Tracked and runtime `Caddyfile` SHA-256 values matched
  `3387659A473097A43B76B7951D833463F77F7C0AC559975271EA3F48B59D1802`, and
  `caddy validate --config "C:\Program Files\Caddy\Caddyfile"` reported a
  valid configuration.
- Explicit-loopback hostname routing returned HTTP 308 for HTTP and HTTP 200
  for the HTTPS dashboard.
- Protected API `/api/v1/auth/me`, map image without cookie, and session
  refresh without bearer authentication returned HTTP 401.
- FastAPI docs were disabled by default: `/docs`, `/redoc`, and
  `/openapi.json` returned HTTP 404 on `127.0.0.1:8000`.
- `/api/v1/auth/users-exist` returned HTTP 200 and only the boolean
  `users_exist` response field.
- PostgreSQL `server2a:5432` and MSSQL `server2a:1433` TCP checks returned
  reachable without printing credentials.
- Scheduler metrics reported `scheduler_running=True`; heartbeat updated after
  restart, and `quarter_hour_job` completed successfully at
  2026-06-16 10:05:09 CEST with next run at 2026-06-16 10:16:05 CEST.
- Scheduler lock files were present, including `scheduler_process.lock`.
- Production Python `get_manual_run_specs()` included
  `sync_charge_sessions_to_db` with label `Zapis SmartFuelPass relaci do
  databaze` under lock `daily_job`, `smartfuelpass_weekly_report_job` with
  label `SmartFuelPass weekly report job`, and
  `send_charge_sessions_report_email` with label
  `Odeslani SmartFuelPass PDF emailu` under lock
  `smartfuelpass_weekly_report_job`.
- Local FastAPI route `/health/scheduler` exists and returned HTTP 401 without
  authentication.
- `.venv\Scripts\python.exe -m pytest tests\test_scheduler.py -q --tb=short`
  passed 51 tests.
- `.venv-production\Scripts\python.exe -m py_compile
  core\scheduler\scheduler.py core\scheduler\job_schedule.py
  moduly\mereni\elektromery\SOFTLINK\SOFTLINK_data_z_dotazu.py
  tests\test_scheduler.py` passed.
- `git diff --check` reported no whitespace errors, only existing LF-to-CRLF
  warnings.

Not verified:
- No authenticated production browser workflow was performed.
- The authenticated `/health/scheduler` response was not fetched with an admin
  bearer token. The route existence, unauthenticated HTTP 401 behavior, and
  production manual-run registry were verified instead.
- Process command lines for non-interactive startup-owned child processes were
  not visible from the current interactive session, but listener ownership and
  health checks matched the expected runtime.

Decisions/notes:
- `daily_job`, `sync_charge_sessions_to_db`,
  `smartfuelpass_weekly_report_job`, and `send_charge_sessions_report_email`
  still show the pre-fix 2026-06-16 failures in scheduler metrics until their
  next real or manual runs record a new result.
- `data/smartfuelpass/session_cookies.json` remains an existing tracked
  sensitive runtime artifact and was not printed, changed, removed, staged, or
  committed.
- No authenticated production browser workflow, mailbox access, production
  database SmartFuelPass upsert, or SmartFuelPass email send was performed
  before this restart.

### 2026-06-16 09:21 CEST - Post-restart verification

Scope:
- Checked runtime state after the Windows workstation restart requested on
  2026-06-16.

Changed:
- Added this post-restart verification note only.

Verified:
- Workstation boot time was 2026-06-16 09:11:13 CEST.
- Scheduled task `API_dashboard_caddy` last ran at 2026-06-16 09:11:23 CEST
  with result `0` and state `Ready`.
- Expected listeners were present: Caddy on ports 80/443 and
  `127.0.0.1:2019`, FastAPI on `127.0.0.1:8000`, Streamlit on
  `127.0.0.1:8001`, and no listeners on temporary ports 8010 or 8011.
- `.venv-production` matched `requirements-production.lock.txt`, and
  `pip check` reported no broken requirements.
- FastAPI `/health/live`, FastAPI `/health/ready`, Streamlit
  `/_stcore/health`, and Caddy admin `/config/` returned HTTP 200.
- Tracked and runtime `Caddyfile` SHA-256 values matched
  `3387659A473097A43B76B7951D833463F77F7C0AC559975271EA3F48B59D1802`, and
  `caddy validate --config "C:\Program Files\Caddy\Caddyfile"` reported a
  valid configuration.
- Explicit-loopback hostname routing returned HTTP 308 for HTTP, HTTP 200 for
  the HTTPS dashboard, and HTTP 401 for protected API, map image without
  cookie, and session refresh without bearer authentication.
- FastAPI docs were disabled by default: `/docs`, `/redoc`, and
  `/openapi.json` returned HTTP 404 on `127.0.0.1:8000`.
- `/api/v1/auth/users-exist` returned HTTP 200 and only the boolean
  `users_exist` response field.
- PostgreSQL `server2a:5432` and MSSQL `server2a:1433` TCP checks returned
  reachable without printing credentials.
- Scheduler metrics reported `scheduler_running=True`; heartbeat updated after
  restart, and `quarter_hour_job` completed successfully at
  2026-06-16 09:16:09 CEST with next run at 2026-06-16 09:35:05 CEST.
- Database availability SQLite integrity was `ok`; PostgreSQL and MSSQL were
  stored as available, with no active outage, zero failed checks, four
  delivered events, and zero pending events.
- Admin alert email hash cache existed and contained one hash; hash values were
  not printed.
- Safe startup log inspection showed Uvicorn started PID 7100 without
  reloader/watchfiles output, Streamlit started after restart, and Caddy served
  the initial configuration after restart.
- SmartFuelPass read-only fetch through `.venv-production` and a temporary
  cookie path loaded 17 source rows and 11 columns, built 8 completed sync
  rows, found 0 invalid rows, and found 0 missing IDs. No database write, PDF
  render, or email send was performed. The temporary cookie file was removed.
- `.venv\Scripts\python.exe -m pytest
  tests\test_api_public_exposure.py tests\test_dashboard_security_config.py
  tests\test_caddy_config.py tests\test_api_authorization_regression.py
  tests\test_smartfuelpass_service.py tests\test_smartfuelpass_sync.py
  tests\test_production_runtime.py -q --tb=short` passed 219 tests.
- `.venv-production\Scripts\python.exe -m py_compile services\api\main.py
  services\api\core\config.py moduly\apps\smartfuelpass\service.py` passed.
- `git diff --check` reported no whitespace errors, only existing LF-to-CRLF
  warnings.

Not verified:
- No authenticated production browser workflow was performed.
- No production SmartFuelPass database upsert or SmartFuelPass email send was
  performed.
- Process command lines for non-interactive startup-owned child processes were
  not visible from the current interactive session, but listener ownership,
  health checks, and logs matched the expected runtime.

Decisions/notes:
- `daily_job` and `smartfuelpass_weekly_report_job` still show the pre-fix
  2026-06-16 failures in scheduler metrics until their next scheduled runs,
  but the post-restart read-only SmartFuelPass fetch verified the fixed portal
  flow.
- Caddy logged transient HTTP 502 responses around 2026-06-16 09:10:53 to
  09:10:59 CEST while Streamlit was not yet accepting connections. Current
  Streamlit health and HTTPS routing are healthy.
- `data/smartfuelpass/session_cookies.json` remains an existing tracked
  sensitive runtime artifact and was not printed, changed, removed, staged, or
  committed.

### 2026-06-16 - Manual daily job and SmartFuelPass scheduler UI check

Scope:
- Investigated a manual `daily_job` alert from the dashboard Scheduler Health
  page.
- Checked the manual-run registry for SmartFuelPass database sync and weekly
  PDF report entries.

Changed:
- Added `sync_charge_sessions_to_db` as a manual internal scheduler step under
  the `daily_job` lock.
- Renamed the scheduled SmartFuelPass report label to distinguish it from the
  internal email-sending step.
- Renamed the SmartFuelPass report internal step label to
  `Odeslani SmartFuelPass PDF emailu`.
- Replaced the SOFTLINK login success `print()` checkmark with ASCII text so
  manual runs do not fail on Windows `charmap` stdout encoding.
- Added scheduler regression coverage for the new SmartFuelPass DB sync manual
  step and distinct SmartFuelPass report labels.

Verified:
- The alert screenshot showed `daily_job` failing on
  `SOFTLINK_save_to_database_all` with a `charmap` encoding error for Unicode
  character `\u2705`.
- `.venv\Scripts\python.exe -m pytest tests\test_scheduler.py -q --tb=short`
  passed 51 tests.
- `.venv-production\Scripts\python.exe -m py_compile
  core\scheduler\scheduler.py core\scheduler\job_schedule.py
  moduly\mereni\elektromery\SOFTLINK\SOFTLINK_data_z_dotazu.py
  tests\test_scheduler.py` passed.
- Local `.venv-production` supervised `daily_job.__scheduler_unlocked_fn__()`
  completed all steps: runtime/database preflight, SOFTLINK import,
  monitoring import, SmartFuelPass DB sync, and meteo sync.
- Local `.venv-production` `trigger_manual_job("daily_job")` completed with
  `JOB MANUAL SUCCESS` at 2026-06-16 09:47:23 CEST. Substeps completed
  successfully; no manual-run alert was emitted by that local process.
- `git diff --check` reported no whitespace errors, only existing LF-to-CRLF
  warnings.

Not verified:
- The running FastAPI process was not restarted, so the dashboard UI and API
  manual-run endpoint will not expose the new SmartFuelPass DB sync step or
  use the SOFTLINK ASCII output fix until the next supported runtime restart.
- No authenticated browser UI check was performed after the code change.

Decisions/notes:
- The two SmartFuelPass report entries were expected from different registry
  layers: scheduled job `smartfuelpass_weekly_report_job` and internal step
  `send_charge_sessions_report_email`. Their labels are now intentionally
  distinct.
- The local manual-trigger verification used a separate Python process and can
  race with the production scheduler metrics writer. The scheduler log showed
  the production `quarter_hour_job` still completed at 2026-06-16 09:47:09
  CEST while the local manual run was active.

### 2026-06-16 09:59 CEST - Pre-restart handoff

Reason for restart:
- The user requested loading the current state and restarting the workstation.
- Activate the latest scheduler/manual-run changes in the running FastAPI and
  scheduler runtime: SmartFuelPass DB sync as a manual `daily_job` step,
  distinct SmartFuelPass report labels, and the SOFTLINK ASCII login output
  fix.

Current task/conversation state:
- Completed: investigated the manual `daily_job` alert; root cause was the
  SOFTLINK login success `print()` containing Unicode checkmark `\u2705` under
  Windows `charmap` stdout encoding.
- Completed: added manual scheduler step `sync_charge_sessions_to_db` under
  the `daily_job` lock.
- Completed: distinguished scheduled SmartFuelPass weekly report job label
  from the internal email-sending step label.
- Completed: local `.venv-production` supervised `daily_job` and local
  `trigger_manual_job("daily_job")` both completed successfully from the
  current working tree.
- Pending after restart: verify FastAPI has loaded the new manual-run registry
  and the dashboard/API exposes `sync_charge_sessions_to_db`.
- First action after restart: read `AGENTS.md`, `DECISIONS.md`,
  `SESSION_NOTES.md`, then run `git status --short --untracked-files=all`.

Working tree and deployment:
- Current time captured before restart: 2026-06-16 09:59:41 CEST.
- Branch: `master`.
- `HEAD`: `5928652359e82dbd5a309ec33a4dff353898551f`.
- No git commit was created for this restart handoff.
- `git status --short --untracked-files=all` before restart:
  - `M SESSION_NOTES.md`
  - `M core/scheduler/job_schedule.py`
  - `M core/scheduler/scheduler.py`
  - `M data/smartfuelpass/session_cookies.json`
  - `M moduly/mereni/elektromery/SOFTLINK/SOFTLINK_data_z_dotazu.py`
  - `M tests/test_scheduler.py`
- Tracked root `Caddyfile` SHA-256 before restart:
  `3387659A473097A43B76B7951D833463F77F7C0AC559975271EA3F48B59D1802`.
- Runtime `C:\Program Files\Caddy\Caddyfile` SHA-256 before restart:
  `3387659A473097A43B76B7951D833463F77F7C0AC559975271EA3F48B59D1802`.
- Existing runtime process state before restart:
  - FastAPI health live: HTTP 200 on `127.0.0.1:8000`.
  - FastAPI health ready: HTTP 200 on `127.0.0.1:8000`.
  - Streamlit health: HTTP 200 on `127.0.0.1:8001`.
  - Caddy admin `/config/`: HTTP 200 on `127.0.0.1:2019`.
  - Loopback listeners: `127.0.0.1:8000` PID 7100,
    `127.0.0.1:8001` PID 10580, `127.0.0.1:2019` PID 11024.
  - Caddy owns ports 80/443; Tailscale owns expected interface-specific 443
    listeners.
  - No listeners were present on temporary ports 8010 or 8011.
- Scheduler metrics before restart:
  - `scheduler_running=True`; heartbeat at 2026-06-16 09:56:29 CEST.
  - `quarter_hour_job`: last success at 2026-06-16 09:47:09 CEST; next run
    2026-06-16 10:05:05 CEST; zero failures in 24 hours.
  - `daily_job`: still shows the pre-fix scheduled error from
    2026-06-16 00:22:54 CEST until the running scheduler/API reloads and a
    later real/manual run records success.
  - `sync_charge_sessions_to_db`: still shows the pre-fix scheduled error from
    2026-06-16 00:22:54 CEST in production metrics; local supervised checks
    succeeded from the current working tree.
  - `smartfuelpass_weekly_report_job`: still shows the pre-fix scheduled error
    from 2026-06-16 07:02:45 CEST.

Sensitive/runtime artifacts:
- Do not print, change, delete, revert, stage, or commit
  `data/smartfuelpass/session_cookies.json` without explicit user approval.
- Do not print, change, delete, or commit the ignored local `.env`,
  `API_TOKEN_SECRET`, email credentials, dashboard credentials, cookies,
  bearer tokens, authentication audit records, operational recipient
  addresses, raw SQLite reason values, or admin email hash-cache values.

Expected processes and listeners after restart:
- Windows Task Scheduler runs `API_dashboard_caddy` at system startup and the
  latest run result becomes `0`.
- One rotating-log wrapper owns one non-reload Uvicorn child on
  `127.0.0.1:8000`.
- One rotating-log wrapper owns one Streamlit child on `127.0.0.1:8001`.
- One scheduler runtime runs `main.py`, holds the `scheduler_process` lock, and
  updates `core/scheduler/logs/scheduler_metrics.json`.
- One Caddy runtime owns TCP 80/443 and admin `127.0.0.1:2019`.
- Tailscale interface-specific port 443 listeners may remain in addition.
- No listener should remain on temporary ports 8010 or 8011.

Expected application state after restart:
- FastAPI `/health/live` and `/health/ready`: HTTP 200 while PostgreSQL remains
  available.
- Streamlit `/_stcore/health` and Caddy admin endpoint: HTTP 200.
- HTTP hostname route: HTTP 308 to HTTPS.
- HTTPS dashboard: HTTP 200.
- Protected API, map image without cookie, and session refresh without bearer:
  HTTP 401.
- FastAPI docs remain disabled by default: `/docs`, `/redoc`, and
  `/openapi.json` return HTTP 404 unless `API_ENABLE_DOCS=true` is explicitly
  set.
- Scheduler Health manual-run registry includes internal step
  `sync_charge_sessions_to_db` with label `Zapis SmartFuelPass relaci do
  databaze`.
- Scheduler Health SmartFuelPass entries distinguish scheduled
  `SmartFuelPass weekly report job` from internal
  `Odeslani SmartFuelPass PDF emailu`.
- Manual `daily_job` no longer fails on the SOFTLINK login success print.

Required post-restart checks:
- Confirm boot time, scheduled-task last run/result/settings, process tree,
  listeners, and no temporary ports 8010/8011.
- Confirm `.venv-production` exact-lock verification and `pip check`.
- Confirm API live/ready, Streamlit health, and Caddy admin health.
- Confirm tracked/runtime Caddyfile hash equality and Caddy validation.
- Confirm HTTP redirect, HTTPS dashboard, protected API, map image, session
  refresh, disabled docs, and public `users-exist` status codes.
- Confirm scheduler process lock, heartbeat age, latest/next `quarter_hour_job`,
  and at least one completed post-restart scheduler heartbeat.
- Confirm FastAPI scheduler health response includes
  `sync_charge_sessions_to_db`, `smartfuelpass_weekly_report_job`, and
  `send_charge_sessions_report_email` with the expected labels and locks.
- Run `.venv\Scripts\python.exe -m pytest tests\test_scheduler.py -q --tb=short`.
- Compile changed scheduler/SOFTLINK modules through `.venv-production`.
- Run `git diff --check` and finish with
  `git status --short --untracked-files=all`.
- Append a dated post-restart verification entry with deviations and accepted
  gaps.

Known risks or accepted gaps:
- `data/smartfuelpass/session_cookies.json` is still a tracked sensitive
  runtime/session artifact by explicit current decision.
- Current changes are uncommitted and depend on the working tree being
  preserved across restart.
- A database or network outage during restart can make API readiness return
  HTTP 503 and cause scheduled database jobs to skip until connectivity
  recovers.
- The current scheduled-task account remains broader than least privilege.
- The launcher does not independently restart a child that fails after startup.

### 2026-06-16 - Dashboard security checklist P2.15 code integrity scan

Scope:
- Continued P2.15 with a repeatable scheduled code integrity scan for
  detecting unauthorized changes to tracked code and deployment configuration.

Changed:
- Added `scripts/code_integrity_scan.py`.
- Added `scripts/run_code_integrity_scan.ps1`.
- Added `scripts/register_code_integrity_scan_task.ps1`.
- Added `tests/test_code_integrity_scan.py`.
- Updated `DASHBOARD_SECURITY_CHECKLIST.md`, `DECISIONS.md`, and `AGENTS.md`.

Verified:
- `.venv\Scripts\python.exe -m pytest tests\test_code_integrity_scan.py -q
  --tb=short` passed 4 tests.
- `.venv-production\Scripts\python.exe scripts\code_integrity_scan.py
  baseline --manifest .codex\tmp_code_integrity_manifest.json` refused to
  create a baseline because scanned files are currently dirty, which is the
  intended fail-closed behavior.

Not verified:
- No production baseline manifest was created.
- The Windows scheduled task was not registered or run.
- No dependency vulnerability scan was added or run yet.

Decisions/notes:
- The code integrity manifest is stored outside the repository under
  `C:\ProgramData\monitorovaci_platforma\security` by default, and scan
  reports are written under ProgramData security logs.
- Runtime data, scheduler locks/logs/local SQLite state, SmartFuelPass session
  artifacts, and known electric-meter source data artifacts are excluded from
  the integrity scope.
- Activation requires a reviewed/approved code state, then baseline creation
  and scheduled task registration.

### 2026-06-16 15:21 CEST - Pre-restart handoff

Reason for restart:
- The user requested saving the conversation/task state and restarting the
  workstation.
- Preserve and resume the current dashboard security checklist P2.15 work:
  repeatable code integrity scan and pending scheduled scan activation.

Current task/conversation state:
- Completed: post-restart runtime check after the earlier restart confirmed
  FastAPI, Streamlit, Caddy, and scheduler were healthy.
- Completed: investigated the next security-checklist item and confirmed MFA
  remains deferred by user decision.
- Completed: implemented local code integrity scanning for tracked code and
  deployment configuration files.
- Completed: added PowerShell entry points for manual scan/baseline and
  Windows scheduled-task registration.
- Completed: documented the code integrity approach in
  `DASHBOARD_SECURITY_CHECKLIST.md`, `DECISIONS.md`, `AGENTS.md`, and
  `SESSION_NOTES.md`.
- Pending after restart: review the current dirty working tree, decide whether
  to commit or otherwise approve it as a new checkpoint, then create the first
  production code-integrity baseline and register/run the scheduled scan.
- Pending after restart: dependency vulnerability scanning with `pip-audit` or
  an equivalent tool is still not implemented.
- First action after restart: read `AGENTS.md`, `DECISIONS.md`,
  `SESSION_NOTES.md`, and `DASHBOARD_SECURITY_CHECKLIST.md`, then run
  `git status --short --untracked-files=all`.

Working tree and deployment:
- Current time captured before restart: 2026-06-16 15:21:41 CEST.
- Branch: `master`.
- `HEAD`: `5928652359e82dbd5a309ec33a4dff353898551f`.
- No git commit was created for this restart handoff.
- `git status --short --untracked-files=all` before restart:
  - `M AGENTS.md`
  - `M DASHBOARD_SECURITY_CHECKLIST.md`
  - `M DECISIONS.md`
  - `M SESSION_NOTES.md`
  - `M core/scheduler/job_schedule.py`
  - `M core/scheduler/scheduler.py`
  - `M data/smartfuelpass/session_cookies.json`
  - `M moduly/mereni/elektromery/SOFTLINK/SOFTLINK_data_z_dotazu.py`
  - `M tests/test_scheduler.py`
  - `?? scripts/code_integrity_scan.py`
  - `?? scripts/register_code_integrity_scan_task.ps1`
  - `?? scripts/run_code_integrity_scan.ps1`
  - `?? tests/test_code_integrity_scan.py`
- Tracked root `Caddyfile` SHA-256 before restart:
  `3387659A473097A43B76B7951D833463F77F7C0AC559975271EA3F48B59D1802`.
- Runtime `C:\Program Files\Caddy\Caddyfile` SHA-256 before restart:
  `3387659A473097A43B76B7951D833463F77F7C0AC559975271EA3F48B59D1802`.
- Existing runtime process state before restart:
  - FastAPI health live: HTTP 200 on `127.0.0.1:8000`.
  - FastAPI health ready: HTTP 200 on `127.0.0.1:8000`.
  - Streamlit health: HTTP 200 on `127.0.0.1:8001`.
  - Caddy admin `/config/`: HTTP 200 on `127.0.0.1:2019`.
  - Loopback listeners: `127.0.0.1:8000` PID 9972,
    `127.0.0.1:8001` PID 10928, `127.0.0.1:2019` PID 11180.
  - Caddy owns ports 80/443; Tailscale owns expected interface-specific 443
    listeners.
  - No listeners were present on temporary ports 8010 or 8011.
- Scheduler metrics before restart:
  - `scheduler_running=True`; heartbeat at 2026-06-16 15:18:27 CEST.
  - `quarter_hour_job`: last success at 2026-06-16 15:16:08 CEST; next run
    2026-06-16 15:35:05 CEST; zero failures in 24 hours.
  - `hourly_job`: last success at 2026-06-16 15:02:19 CEST; next run
    2026-06-16 16:02:05 CEST; zero failures in 24 hours.
  - `daily_job`: still shows the pre-fix scheduled error from
    2026-06-16 00:22:54 CEST until a later real/manual run records success.
  - `sync_charge_sessions_to_db`: still shows the pre-fix scheduled error
    from 2026-06-16 00:22:54 CEST until a later real/manual run records
    success.
  - `smartfuelpass_weekly_report_job` and
    `send_charge_sessions_report_email` still show the pre-fix scheduled error
    from 2026-06-16 07:02:45 CEST.
- Verification before restart:
  - `.venv\Scripts\python.exe -m pytest tests\test_code_integrity_scan.py
    tests\test_scheduler.py -q --tb=short` passed 55 tests.
  - `.venv-production\Scripts\python.exe scripts\code_integrity_scan.py
    baseline --manifest .codex\tmp_code_integrity_manifest.json` refused to
    create a baseline because scanned files are dirty. This is expected and
    must remain the fail-closed behavior until the current code state is
    reviewed/approved.

Sensitive/runtime artifacts:
- Do not print, change, delete, revert, stage, or commit
  `data/smartfuelpass/session_cookies.json` without explicit user approval.
  It remains a tracked sensitive runtime/session artifact.
- Do not print, change, delete, or commit the ignored local `.env`,
  `API_TOKEN_SECRET`, email credentials, dashboard credentials, cookies,
  bearer tokens, authentication audit records, operational recipient
  addresses, raw SQLite reason values, admin email hash-cache values, or
  ProgramData security manifests/logs.
- Do not create a production code integrity baseline from a dirty working tree
  unless the user explicitly approves that exact state as the new checkpoint.

Expected processes and listeners after restart:
- Windows Task Scheduler runs `API_dashboard_caddy` at system startup and the
  latest run result becomes `0`.
- One rotating-log wrapper owns one non-reload Uvicorn child on
  `127.0.0.1:8000`.
- One rotating-log wrapper owns one Streamlit child on `127.0.0.1:8001`.
- One scheduler runtime runs `main.py`, holds the `scheduler_process` lock, and
  updates `core/scheduler/logs/scheduler_metrics.json`.
- One Caddy runtime owns TCP 80/443 and admin `127.0.0.1:2019`.
- Tailscale interface-specific port 443 listeners may remain in addition.
- No listener should remain on temporary ports 8010 or 8011.

Expected application state after restart:
- FastAPI `/health/live` and `/health/ready`: HTTP 200 while PostgreSQL remains
  available.
- Streamlit `/_stcore/health` and Caddy admin endpoint: HTTP 200.
- HTTP hostname route: HTTP 308 to HTTPS.
- HTTPS dashboard: HTTP 200.
- Protected API, map image without cookie, and session refresh without bearer:
  HTTP 401.
- FastAPI docs remain disabled by default: `/docs`, `/redoc`, and
  `/openapi.json` return HTTP 404 unless `API_ENABLE_DOCS=true` is explicitly
  set.
- Scheduler Health manual-run registry still includes
  `sync_charge_sessions_to_db` with label `Zapis SmartFuelPass relaci do
  databaze`, plus distinct SmartFuelPass weekly report labels.
- Code integrity scanner scripts remain present in the working tree but no
  production baseline or scheduled task is active unless explicitly created
  after restart.

Required post-restart checks:
- Confirm boot time, scheduled-task last run/result/settings, process tree,
  listeners, and no temporary ports 8010/8011.
- Confirm `.venv-production` exact-lock verification and `pip check`.
- Confirm API live/ready, Streamlit health, and Caddy admin health.
- Confirm tracked/runtime Caddyfile hash equality and Caddy validation.
- Confirm HTTP redirect, HTTPS dashboard, protected API, map image, session
  refresh, disabled docs, and public `users-exist` status codes.
- Confirm scheduler process lock, heartbeat age, latest/next
  `quarter_hour_job`, and at least one completed post-restart scheduler
  heartbeat.
- Confirm FastAPI scheduler health/manual-run registry includes
  `sync_charge_sessions_to_db`, `smartfuelpass_weekly_report_job`, and
  `send_charge_sessions_report_email` with expected labels and locks.
- Run `.venv\Scripts\python.exe -m pytest tests\test_code_integrity_scan.py
  tests\test_scheduler.py -q --tb=short`.
- Compile changed scheduler/SOFTLINK/security scanner modules through
  `.venv-production`.
- Run the code integrity baseline command and confirm it still refuses dirty
  scanned files until the current state is reviewed/approved.
- Run `git diff --check` and finish with
  `git status --short --untracked-files=all`.
- Append a dated post-restart verification entry with deviations and accepted
  gaps.

Known risks or accepted gaps:
- `data/smartfuelpass/session_cookies.json` is still a tracked sensitive
  runtime/session artifact by explicit current decision.
- Current changes are uncommitted and depend on the working tree being
  preserved across restart.
- The code integrity scan is a local drift detector, not tamper-proof host
  intrusion detection.
- Dependency vulnerability scanning remains open in P2.15.
- A database or network outage during restart can make API readiness return
  HTTP 503 and cause scheduled database jobs to skip until connectivity
  recovers.
- The current scheduled-task account remains broader than least privilege.
- The launcher does not independently restart a child that fails after startup.

### 2026-06-17 07:21 CEST - Post-restart verification

Scope:
- Checked runtime state after the 2026-06-16 workstation restart.
- Verified the scheduler/API/dashboard/Caddy runtime and the pending P2.15
  code-integrity activation state.

Changed:
- Appended this post-restart verification note.

Verified:
- Windows boot time was 2026-06-16 15:28:04 CEST.
- Scheduled task `API_dashboard_caddy` last ran at 2026-06-16 15:28:14 CEST
  with result `0`.
- Listeners were present on Caddy `:80`/`:443`, Caddy admin
  `127.0.0.1:2019`, FastAPI `127.0.0.1:8000`, and Streamlit
  `127.0.0.1:8001`; no listeners were present on temporary ports `8010` or
  `8011`. Tailscale still had expected interface-specific `443` listeners.
- Local health checks returned HTTP 200 for FastAPI `/health/live`,
  FastAPI `/health/ready`, Streamlit `/_stcore/health`, and Caddy admin
  `/config/`.
- `.venv-production` passed `pip check` and
  `scripts/verify_production_environment.py`.
- The tracked root `Caddyfile` and runtime
  `C:\Program Files\Caddy\Caddyfile` SHA-256 hashes matched
  `3387659A473097A43B76B7951D833463F77F7C0AC559975271EA3F48B59D1802`, and
  `caddy validate` reported a valid configuration.
- Loopback Caddy checks using host `monitoring.armexholding.cz` returned HTTP
  308 for HTTP root, HTTP 200 for HTTPS dashboard, HTTP 401 for protected map
  catalog without bearer token, HTTP 401 for map image without cookie, HTTP
  401 for session refresh without bearer token, and HTTP 200 for public
  `users-exist`.
- Direct FastAPI checks returned HTTP 404 for `/docs`, `/redoc`, and
  `/openapi.json`.
- Scheduler metrics showed `scheduler_running=True`, heartbeat
  `2026-06-17T07:18:24.632597`, `quarter_hour_job` success at
  `2026-06-17T07:16:09.045294`, next `quarter_hour_job` at
  `2026-06-17T07:35:05+02:00`, and zero `quarter_hour_job` failures in the
  last 24 hours.
- The production scheduler recorded post-restart success for `daily_job`,
  `SOFTLINK_save_to_database_all`, and `sync_charge_sessions_to_db`.
- Local production-code manual-run specs included
  `sync_charge_sessions_to_db` with label `Zapis SmartFuelPass relaci do
  databaze` and lock `daily_job`, plus distinct SmartFuelPass report labels
  `SmartFuelPass weekly report job` and `Odeslani SmartFuelPass PDF emailu`.
- `.venv\Scripts\python.exe -m pytest tests\test_code_integrity_scan.py
  tests\test_scheduler.py -q --tb=short` passed 55 tests.
- `.venv-production\Scripts\python.exe -m py_compile` passed for the changed
  scheduler, SOFTLINK, code-integrity, and related test modules.
- Code-integrity baseline creation still refused the dirty working tree, as
  expected before an approved baseline.
- `git diff --check` reported no whitespace errors, only existing LF-to-CRLF
  warnings.

Not verified:
- True external access from outside the server/LAN was not verified. From the
  workstation, `monitoring.armexholding.cz` resolved to `77.95.46.168`, but
  TCP `443` timed out from source `192.168.2.249`; this matches the known
  same-server/public-IP hairpin limitation and should be checked from an
  external network if public reachability must be confirmed.
- The authenticated `/health/scheduler` API response was not read because it
  requires an administrator bearer token or browser session; no secrets,
  cookies, or tokens were inspected. The route returned HTTP 401 without
  authentication, and the code registry plus runtime metrics were checked
  separately.
- No production code-integrity baseline was created and no scheduled
  code-integrity task was registered.

Working tree after verification before this note:
- `M AGENTS.md`
- `M DASHBOARD_SECURITY_CHECKLIST.md`
- `M DECISIONS.md`
- `M SESSION_NOTES.md`
- `M core/scheduler/job_schedule.py`
- `M core/scheduler/scheduler.py`
- `M data/smartfuelpass/session_cookies.json`
- `M moduly/mereni/elektromery/SOFTLINK/SOFTLINK_data_z_dotazu.py`
- `M tests/test_scheduler.py`
- `?? scripts/code_integrity_scan.py`
- `?? scripts/register_code_integrity_scan_task.ps1`
- `?? scripts/run_code_integrity_scan.ps1`
- `?? tests/test_code_integrity_scan.py`

Follow-up:
- Confirm public reachability from an external network if needed.
- Review/commit or explicitly approve the dirty working tree before creating
  the production code-integrity baseline.
- Dependency vulnerability scanning remains open for P2.15.

### 2026-06-17 - Scheduler Health manual-run log panel

Scope:
- Updated the Streamlit `Sprava / Health scheduleru` page so manual scheduler
  job or internal-step runs keep an open progress/log panel.

Changed:
- `moduly/apps/dashboard/pages/16_scheduler_health.py` now stores the latest
  manual-run request in Streamlit session state, polls the scheduler log while
  the run is active, renders the same ERROR summary styling as the main
  scheduler log excerpt, shows `Nejsou zadne ERROR zaznamy` after a clean
  success, and leaves the panel open after completion.
- `moduly/apps/dashboard/scheduler_log_view.py` now has helpers for slicing
  scheduler logs from the manual-run request time and detecting
  `JOB MANUAL SUCCESS`, `JOB MANUAL ERROR`, and `JOB MANUAL SKIPPED` records.
- `tests/test_dashboard_scheduler_log_view.py` covers the new log slicing and
  manual-run completion detection helpers.

Verified:
- `.venv\Scripts\python.exe -m pytest tests\test_dashboard_scheduler_log_view.py
  tests\test_scheduler_metrics.py -q --tb=short` passed 11 tests.
- `.venv-production\Scripts\python.exe -m py_compile` passed for the changed
  scheduler-health page, log-view helper, and test module.
- `git diff --check` reported no whitespace errors, only existing LF-to-CRLF
  warnings.

Not verified:
- No authenticated browser click-through was performed against the running
  dashboard.
- The running Streamlit process was not restarted, so the UI change will load
  after the next supported runtime restart or Streamlit reload.

### 2026-06-17 08:20 CEST - Pre-restart handoff

Reason for restart:
- The user requested saving the current state and restarting the workstation.
- Activate the latest Streamlit dashboard change in the running runtime:
  `Sprava / Health scheduleru` manual-run progress/log panel.
- Preserve the current dirty working tree and pending security-checklist
  P2.15 code-integrity activation state.

Current task/conversation state:
- Completed: post-restart runtime check earlier on 2026-06-17 confirmed
  FastAPI, Streamlit, Caddy, and scheduler were healthy after the 2026-06-16
  restart.
- Completed: implemented the Scheduler Health manual-run progress/log panel.
  The page stores the latest manual-run request in Streamlit session state,
  polls scheduler log tail during active runs, highlights ERROR blocks with
  the existing scheduler log styling, shows `Nejsou zadne ERROR zaznamy` on a
  clean success, and leaves the panel open after completion.
- Completed: added scheduler-log helper coverage for manual-run log slicing
  and `JOB MANUAL SUCCESS`, `JOB MANUAL ERROR`, and `JOB MANUAL SKIPPED`
  detection.
- Pending after restart: verify the dashboard UI loads the new manual-run
  panel in an authenticated browser session.
- Pending after restart: review/commit or explicitly approve the dirty working
  tree before creating the first production code-integrity baseline.
- Pending after restart: dependency vulnerability scanning remains open for
  P2.15.
- First action after restart: read `AGENTS.md`, `DECISIONS.md`,
  `SESSION_NOTES.md`, then run `git status --short --untracked-files=all`.

Working tree and deployment:
- Current time captured before restart: 2026-06-17 08:20:19 CEST.
- Branch: `master`.
- `HEAD`: `5928652359e82dbd5a309ec33a4dff353898551f`.
- No git commit was created for this restart handoff.
- `git status --short --untracked-files=all` before restart:
  - `M AGENTS.md`
  - `M DASHBOARD_SECURITY_CHECKLIST.md`
  - `M DECISIONS.md`
  - `M SESSION_NOTES.md`
  - `M core/scheduler/job_schedule.py`
  - `M core/scheduler/scheduler.py`
  - `M data/smartfuelpass/session_cookies.json`
  - `M moduly/apps/dashboard/pages/16_scheduler_health.py`
  - `M moduly/apps/dashboard/scheduler_log_view.py`
  - `M moduly/mereni/elektromery/SOFTLINK/SOFTLINK_data_z_dotazu.py`
  - `M tests/test_dashboard_scheduler_log_view.py`
  - `M tests/test_scheduler.py`
  - `?? scripts/code_integrity_scan.py`
  - `?? scripts/register_code_integrity_scan_task.ps1`
  - `?? scripts/run_code_integrity_scan.ps1`
  - `?? tests/test_code_integrity_scan.py`
- Tracked root `Caddyfile` SHA-256 before restart:
  `3387659A473097A43B76B7951D833463F77F7C0AC559975271EA3F48B59D1802`.
- Runtime `C:\Program Files\Caddy\Caddyfile` SHA-256 before restart:
  `3387659A473097A43B76B7951D833463F77F7C0AC559975271EA3F48B59D1802`.
- Caddy runtime configuration validation reported `Valid configuration`.
- Existing runtime process/listener state before restart:
  - Caddy owned TCP `:80` and `:443`, PID `11232`.
  - Caddy admin listened on `127.0.0.1:2019`, PID `11232`.
  - FastAPI listened on `127.0.0.1:8000`, PID `9928`.
  - Streamlit listened on `127.0.0.1:8001`, PID `10824`.
  - Tailscale owned expected interface-specific `443` listeners on
    `100.66.79.74` and `fd7a:115c:a1e0::e38:4f4b`.
  - No listeners were present on temporary ports `8010` or `8011`.
- Runtime health before restart:
  - FastAPI `/health/live`: HTTP 200 on `127.0.0.1:8000`.
  - FastAPI `/health/ready`: HTTP 200 on `127.0.0.1:8000`.
  - Streamlit `/_stcore/health`: HTTP 200 on `127.0.0.1:8001`.
  - Caddy admin `/config/`: HTTP 200 on `127.0.0.1:2019`.
- Production environment before restart:
  - `.venv-production\Scripts\python.exe -m pip check` reported no broken
    requirements.
  - `scripts/verify_production_environment.py` reported that the production
    Python environment matches `requirements-production.lock.txt`.
- Scheduler metrics before restart:
  - `scheduler_running=True`; heartbeat at `2026-06-17T08:18:24.975504`.
  - `quarter_hour_job`: last success at `2026-06-17T08:16:08.980943`; next
    run `2026-06-17T08:35:05+02:00`; zero failures in 24 hours.
  - `hourly_job`: last success at `2026-06-17T08:02:19.052882`; next run
    `2026-06-17T09:02:05+02:00`.
  - `daily_job`: last success at `2026-06-17T00:20:56.302058`.
  - `sync_charge_sessions_to_db`: last success at
    `2026-06-17T00:20:55.909289`.
  - `SOFTLINK_save_to_database_all`: last success at
    `2026-06-17T00:15:15.207851`.
- Verification before restart:
  - `.venv\Scripts\python.exe -m pytest tests\test_dashboard_scheduler_log_view.py
    tests\test_scheduler_metrics.py -q --tb=short` passed 11 tests after the
    Scheduler Health manual-run log-panel change.
  - `.venv-production\Scripts\python.exe -m py_compile` passed for the
    changed Scheduler Health page, scheduler-log helper, and test module.
  - `git diff --check` reported no whitespace errors, only existing
    LF-to-CRLF warnings.

Sensitive/runtime artifacts:
- Do not print, change, delete, revert, stage, or commit
  `data/smartfuelpass/session_cookies.json` without explicit user approval.
  It remains a tracked sensitive runtime/session artifact.
- Do not print, change, delete, or commit the ignored local `.env`,
  `API_TOKEN_SECRET`, email credentials, dashboard credentials, cookies,
  bearer tokens, authentication audit records, operational recipient
  addresses, raw SQLite reason values, admin email hash-cache values, or
  ProgramData security manifests/logs.
- Do not create a production code-integrity baseline from a dirty working tree
  unless the user explicitly approves that exact state as the new checkpoint.

Expected processes and listeners after restart:
- Windows Task Scheduler runs `API_dashboard_caddy` at system startup and the
  latest run result becomes `0`.
- One rotating-log wrapper owns one non-reload Uvicorn child on
  `127.0.0.1:8000`.
- One rotating-log wrapper owns one Streamlit child on `127.0.0.1:8001`.
- One scheduler runtime runs `main.py`, holds the `scheduler_process` lock,
  and updates `core/scheduler/logs/scheduler_metrics.json`.
- One Caddy runtime owns TCP `80`/`443` and admin `127.0.0.1:2019`.
- Tailscale interface-specific `443` listeners may remain in addition.
- No listener should remain on temporary ports `8010` or `8011`.

Expected application state after restart:
- FastAPI `/health/live` and `/health/ready`: HTTP 200 while PostgreSQL
  remains available.
- Streamlit `/_stcore/health` and Caddy admin endpoint: HTTP 200.
- HTTP hostname route: HTTP 308 to HTTPS.
- HTTPS dashboard: HTTP 200.
- Protected API, map image without cookie, and session refresh without bearer:
  HTTP 401.
- FastAPI docs remain disabled by default: `/docs`, `/redoc`, and
  `/openapi.json` return HTTP 404 unless `API_ENABLE_DOCS=true` is explicitly
  set.
- Scheduler Health manual-run registry includes `sync_charge_sessions_to_db`
  with label `Zapis SmartFuelPass relaci do databaze`, plus distinct
  SmartFuelPass weekly report labels.
- Scheduler Health manual-run UI opens and preserves a progress/log panel for
  the selected job or internal step.
- A successful manual run displays green `Nejsou zadne ERROR zaznamy`; ERROR
  records display in the same red block style as the main scheduler log
  excerpt.
- Code integrity scanner scripts remain present in the working tree, but no
  production baseline or scheduled task is active unless explicitly created
  after restart.

Required post-restart checks:
- Confirm boot time, scheduled-task last run/result/settings, process tree,
  listeners, and no temporary ports `8010`/`8011`.
- Confirm `.venv-production` exact-lock verification and `pip check`.
- Confirm API live/ready, Streamlit health, and Caddy admin health.
- Confirm tracked/runtime Caddyfile hash equality and Caddy validation.
- Confirm HTTP redirect, HTTPS dashboard, protected API, map image, session
  refresh, disabled docs, and public `users-exist` status codes.
- Confirm scheduler process lock, heartbeat age, latest/next
  `quarter_hour_job`, and at least one completed post-restart scheduler
  heartbeat.
- Confirm FastAPI scheduler health/manual-run registry includes
  `sync_charge_sessions_to_db`, `smartfuelpass_weekly_report_job`, and
  `send_charge_sessions_report_email` with expected labels and locks.
- Verify the authenticated Streamlit `Sprava / Health scheduleru` page shows
  the new manual-run progress/log panel after a manual run request. Prefer a
  low-risk internal step and do not run data-changing jobs casually.
- Run `.venv\Scripts\python.exe -m pytest tests\test_dashboard_scheduler_log_view.py
  tests\test_scheduler_metrics.py tests\test_code_integrity_scan.py
  tests\test_scheduler.py -q --tb=short`.
- Compile changed scheduler, SOFTLINK, dashboard Scheduler Health, scheduler
  log-view, and code-integrity modules through `.venv-production`.
- Run the code-integrity baseline command and confirm it still refuses dirty
  scanned files until the current state is reviewed/approved.
- Run `git diff --check` and finish with
  `git status --short --untracked-files=all`.
- Append a dated post-restart verification entry with deviations and accepted
  gaps.

Known risks or accepted gaps:
- `data/smartfuelpass/session_cookies.json` is still a tracked sensitive
  runtime/session artifact by explicit current decision.
- Current changes are uncommitted and depend on the working tree being
  preserved across restart.
- The code integrity scan is a local drift detector, not tamper-proof host
  intrusion detection.
- Dependency vulnerability scanning remains open in P2.15.
- True external public reachability from outside the server/LAN remains a
  separate check. Earlier local same-server public-IP access timed out while
  loopback Caddy hostname routing worked.
- A database or network outage during restart can make API readiness return
  HTTP 503 and cause scheduled database jobs to skip until connectivity
  recovers.
- The current scheduled-task account remains broader than least privilege.
- The launcher does not independently restart a child that fails after
  startup.

## 2026-06-18 13:20 +02:00 - Restart Handoff Before SmartFuelPass/P2.17 Activation

Reason for restart:
- User requested saving state and restarting the workstation.
- Restart is intended to reload FastAPI, Streamlit, scheduler, and Caddy from
  the normal Windows startup task after the SmartFuelPass and security
  hardening work.

Current conversation/task state:
- P2.16 secret hygiene is partially complete. SmartFuelPass reusable session
  JSON persistence was retired and the two session JSON files were removed
  from the Git index. Other tracked runtime/private artifacts remain open.
- User chose SmartFuelPass password login only, without saving JSON session
  files.
- P2.17 external security verification was started, not completed. Loopback
  hostname checks passed for several HTTPS/auth/header controls, but a true
  external-network test outside the server/LAN remains required.
- Runtime Caddy deployment of the tracked P2.17 proxy fixes is still pending
  because `scripts\deploy_caddy_runtime.ps1` requires an elevated
  administrator PowerShell session.

Completed work in the current state:
- SmartFuelPass service no longer reads or writes
  `data/smartfuelpass/session_cookies.json` or
  `data/smartfuelpass/auto_login_session.json`.
- SmartFuelPass reporting snapshots and charge-session imports use a fresh
  Playwright context and `SMARTFUELPASS_EMAIL` /
  `SMARTFUELPASS_PASSWORD` login for each portal run.
- Existing SmartFuelPass `cookie_path` parameters remain compatibility no-ops.
- `SMARTFUELPASS_SESSION_COOKIES_PATH` was removed from `.env.example`.
- `data/smartfuelpass/session_cookies.json` and
  `data/smartfuelpass/auto_login_session.json` were removed from the Git
  index with `git rm --cached`; local ignored copies were not read or deleted.
- Tracked `Caddyfile` now disables automatic redirects, uses an explicit HTTP
  redirect block with `-Server`/`-Via`, uses an explicit HTTPS block, and
  returns HTTP 404 for `/docs`, `/redoc`, and `/openapi.json` before the
  Streamlit fallback.
- Added or updated `SECURITY_SECRET_INVENTORY.md`,
  `DASHBOARD_SECURITY_CHECKLIST.md`, `DECISIONS.md`, `AGENTS.md`, and these
  session notes for P2.16/P2.17.

Changed/uncommitted files before restart:
- Modified: `.env.example`, `.gitignore`, `AGENTS.md`, `Caddyfile`,
  `DASHBOARD_SECURITY_CHECKLIST.md`, `DECISIONS.md`, `SESSION_NOTES.md`,
  `moduly/apps/smartfuelpass/__init__.py`,
  `moduly/apps/smartfuelpass/service.py`,
  `requirements-production.in`, `requirements-production.lock.txt`,
  `scripts/code_integrity_scan.py`,
  `scripts/register_code_integrity_scan_task.ps1`,
  `tests/test_caddy_config.py`, `tests/test_code_integrity_scan.py`,
  `tests/test_smartfuelpass_service.py`.
- Git-index deletions: `data/smartfuelpass/auto_login_session.json`,
  `data/smartfuelpass/session_cookies.json`.
- Untracked new files: `SECURITY_SECRET_INVENTORY.md`,
  `requirements-security.in`, `requirements-security.lock.txt`,
  `scripts/bootstrap_security_toolchain.ps1`,
  `scripts/register_dependency_audit_task.ps1`,
  `scripts/run_dependency_audit.ps1`, `scripts/secret_hygiene_scan.py`,
  `tests/test_dependency_audit_tooling.py`,
  `tests/test_secret_hygiene_scan.py`.

Verification already run:
- `.venv\Scripts\python.exe -m pytest tests\test_smartfuelpass_service.py
  tests\test_smartfuelpass_sync.py tests\test_secret_hygiene_scan.py
  tests\test_code_integrity_scan.py tests\test_dependency_audit_tooling.py
  tests\test_production_runtime.py tests\test_dashboard_security_config.py
  tests\test_caddy_config.py tests\test_api_public_exposure.py -q --tb=short`
  passed 66 tests.
- `C:\Program Files\Caddy\caddy.exe validate --config Caddyfile --adapter caddyfile`
  passed and reported automatic HTTP redirects disabled.
- `.venv\Scripts\python.exe -m py_compile scripts\secret_hygiene_scan.py
  scripts\code_integrity_scan.py moduly\apps\smartfuelpass\service.py
  moduly\apps\smartfuelpass\__init__.py` passed.
- `git diff --check` reported no whitespace errors, only expected LF-to-CRLF
  warnings.
- Redacted secret hygiene scan reported current findings only for tracked
  electric-meter source files, scheduler lock files, and
  `frontend_next/tsconfig.tsbuildinfo`; no current SmartFuelPass session JSON
  findings remained.

Deployment state before restart:
- Running FastAPI, Streamlit, and scheduler processes were started before the
  SmartFuelPass code change and need restart to load it.
- Tracked `Caddyfile` contains P2.17 fixes, but runtime
  `C:\Program Files\Caddy\Caddyfile` was not updated from this non-elevated
  shell. A restart alone is not expected to activate those tracked Caddy proxy
  fixes unless the runtime file has been synchronized separately.
- `MonitoringDependencyAudit` was registered earlier and last ran
  successfully. Code-integrity baseline/scheduled activation remains pending
  until the working tree is reviewed/approved.

Sensitive artifacts and handling rules:
- Do not print, read, delete, revert, or commit raw values from ignored local
  `.env`, dashboard/API tokens, passwords, cookies, authentication audit logs,
  ProgramData security artifacts, or any local leftover SmartFuelPass session
  JSON files.
- Local leftover `data/smartfuelpass/session_cookies.json` and
  `data/smartfuelpass/auto_login_session.json` files may still exist but are
  ignored and must not be inspected. Expire SmartFuelPass portal sessions
  externally if old cookies may still be valid.
- Do not create a production code-integrity baseline from the dirty working
  tree unless the user explicitly approves that exact state.

Expected processes and listeners after restart:
- Windows Task Scheduler runs `API_dashboard_caddy` at system startup and its
  latest run result becomes `0`.
- One rotating-log wrapper owns one non-reload Uvicorn child on
  `127.0.0.1:8000`.
- One rotating-log wrapper owns one Streamlit child on `127.0.0.1:8001`.
- One scheduler runtime runs `main.py`, holds the `scheduler_process` lock,
  and updates `core/scheduler/logs/scheduler_metrics.json`.
- One Caddy runtime owns TCP `80`/`443` and admin `127.0.0.1:2019`.
- No listener should remain on temporary ports `8010` or `8011`.

Expected application state after restart:
- FastAPI `/health/live` and `/health/ready`: HTTP 200 while PostgreSQL is
  available.
- Streamlit `/_stcore/health` and Caddy admin endpoint: HTTP 200.
- HTTPS dashboard: HTTP 200.
- HTTP hostname route: HTTP 308 to HTTPS. After runtime Caddy deployment, the
  redirect response should not include `Server` or `Via`.
- Protected API, map image without cookie, and session refresh without bearer:
  HTTP 401.
- Public `/api/v1/auth/users-exist`: HTTP 200 with minimal boolean payload.
- FastAPI docs remain disabled. After runtime Caddy deployment, public
  `/docs`, `/redoc`, and `/openapi.json` should return HTTP 404 rather than
  the Streamlit shell.
- SmartFuelPass scheduled/manual jobs should use password login only and must
  not create or update SmartFuelPass session JSON files.

Required post-restart checks:
- Confirm boot time, scheduled-task last run/result/settings, process tree,
  listeners, and no temporary ports `8010`/`8011`.
- Confirm `.venv-production` exact-lock verification and `pip check`.
- Confirm API live/ready, Streamlit health, Caddy admin health, and scheduler
  heartbeat.
- Confirm tracked/runtime Caddyfile hash equality. If they differ, run
  `scripts\deploy_caddy_runtime.ps1` from an elevated administrator PowerShell
  session and reload Caddy before rechecking P2.17 proxy findings.
- Validate runtime Caddyfile and verify HTTP redirect, HTTPS dashboard,
  protected API, map image, session refresh, disabled docs, and public
  `users-exist` status codes.
- Confirm no `Server` or `Via` headers on HTTPS responses and, after runtime
  Caddy deployment, on HTTP redirect responses.
- Run SmartFuelPass targeted tests again:
  `.venv\Scripts\python.exe -m pytest tests\test_smartfuelpass_service.py
  tests\test_smartfuelpass_sync.py -q --tb=short`.
- Run security/tooling tests as needed:
  `.venv\Scripts\python.exe -m pytest tests\test_secret_hygiene_scan.py
  tests\test_code_integrity_scan.py tests\test_dependency_audit_tooling.py
  tests\test_caddy_config.py tests\test_api_public_exposure.py -q --tb=short`.
- Run `scripts\secret_hygiene_scan.py` and confirm no current SmartFuelPass
  session JSON findings.
- Run `git diff --check` and finish with
  `git status --short --untracked-files=all`.
- Append a dated post-restart verification entry with deviations and accepted
  gaps.

Known risks or accepted gaps:
- True P2.17 external verification from a network outside the server and
  corporate LAN is still open.
- Login throttling, session expiry, logout, token revocation, horizontal and
  vertical authorization boundaries, and XSS/CSRF/injection/path traversal
  checks are not fully completed for P2.17.
- Runtime Caddy proxy fixes are not active until the runtime Caddyfile is
  synchronized and Caddy is reloaded.
- The current changes are uncommitted and depend on the working tree being
  preserved across restart.
- The current scheduled-task account remains broader than least privilege.
- The launcher does not independently restart a child process that fails after
  startup.

## 2026-06-25 06:52 +02:00 - Current pre-restart handoff after map photo iframe fix

Reason for restart:
- User requested saving the current conversation state before restarting the
  workstation.
- Restart is expected to reload FastAPI, Streamlit, scheduler, and Caddy from
  the normal Windows startup task.

Current task/conversation state:
- Completed: diagnosed the `Mapove podklady / Mapa` popup photo failure as a
  browser credential issue in the Streamlit component iframe.
- Completed: changed map popup photo fetches from `credentials: "same-origin"`
  to `credentials: "include"` so the HttpOnly dashboard session cookie can be
  attached to `/api/v1/map/images` from the iframe.
- Completed: preserved the P1.7 security rule that the main bearer token is
  not passed into generated map HTML or JavaScript.
- Pending after restart: open the dashboard through
  `https://monitoring.armexholding.cz`, go to `Mapove podklady / Mapa`, click
  a Vodomery object with `has_photo`, and confirm the photo loads instead of
  `Fotku se nepodarilo nacist.`
- Pending after restart: if the popup still fails, inspect the browser network
  status for `/api/v1/map/images` without printing cookies or token values.
- First action after restart: read `AGENTS.md`, `DECISIONS.md`, and
  `SESSION_NOTES.md`, then run `git status --short --untracked-files=all`.

Working tree and deployment:
- Current time captured before restart: 2026-06-25 06:52:21 +02:00.
- Branch: `master`.
- `HEAD`: `69dc532eccbc49db3152e7a1ce0627392375601b`.
- No git commit was created for this handoff.
- `git status --short --untracked-files=all` before restart:
  - `M .env.example`
  - `M .gitignore`
  - `M AGENTS.md`
  - `M Caddyfile`
  - `M DASHBOARD_SECURITY_CHECKLIST.md`
  - `M DECISIONS.md`
  - `M SESSION_NOTES.md`
  - `D data/smartfuelpass/auto_login_session.json`
  - `D data/smartfuelpass/session_cookies.json`
  - `M moduly/apps/dashboard/map_shared.py`
  - `M moduly/apps/smartfuelpass/__init__.py`
  - `M moduly/apps/smartfuelpass/service.py`
  - `M requirements-production.in`
  - `M requirements-production.lock.txt`
  - `M scripts/code_integrity_scan.py`
  - `M scripts/register_code_integrity_scan_task.ps1`
  - `M tests/test_caddy_config.py`
  - `M tests/test_code_integrity_scan.py`
  - `M tests/test_dashboard_map_shared.py`
  - `M tests/test_smartfuelpass_service.py`
  - `?? SECURITY_SECRET_INVENTORY.md`
  - `?? requirements-security.in`
  - `?? requirements-security.lock.txt`
  - `?? scripts/bootstrap_security_toolchain.ps1`
  - `?? scripts/register_dependency_audit_task.ps1`
  - `?? scripts/run_dependency_audit.ps1`
  - `?? scripts/secret_hygiene_scan.py`
  - `?? tests/test_dependency_audit_tooling.py`
  - `?? tests/test_secret_hygiene_scan.py`
- Files changed in this final map-photo fix only:
  - `moduly/apps/dashboard/map_shared.py`
  - `tests/test_dashboard_map_shared.py`
- Existing unrelated dirty files are from earlier security, Caddy,
  SmartFuelPass, dependency-audit, and code-integrity work. Do not revert or
  clean them without explicit approval.
- Tracked root `Caddyfile` SHA-256 before restart:
  `08CDF04AFC4F856FEC8DFE4AB2E07A746763B152CA91553E349CCCE8E6D3DF2C`.
- Runtime Caddyfile hash equality was not checked in this handoff from
  `C:\Program Files\Caddy\Caddyfile`; verify after restart.
- Existing listener state before restart:
  - Caddy owned TCP `:80` and `:443`, PID `10048`.
  - Caddy admin listened on `127.0.0.1:2019`, PID `10048`.
  - FastAPI listened on `127.0.0.1:8000`, PID `11252`.
  - Streamlit listened on `127.0.0.1:8001`, PID `11972`.
  - Tailscale owned expected interface-specific `443` listeners on
    `100.66.79.74` and `fd7a:115c:a1e0::e38:4f4b`, PID `7060`.
- Runtime health before restart:
  - FastAPI `/health/live`: HTTP 200 on `127.0.0.1:8000`.
  - FastAPI `/health/ready`: HTTP 200 on `127.0.0.1:8000`.
  - Streamlit `/_stcore/health`: HTTP 200 on `127.0.0.1:8001`.
  - Caddy admin `/config/`: HTTP 200 on `127.0.0.1:2019`.
- Scheduler metrics before restart:
  - `scheduler_running=True`.
  - Heartbeat observed at `2026-06-25T06:52:24.432676`.
  - `quarter_hour_job` detail was not extracted by the quick handoff command;
    verify latest/next job state after restart.

Verification already run for the map-photo fix:
- `.venv\Scripts\python.exe -m pytest tests\test_dashboard_map_shared.py
  tests\test_map_routes.py tests\test_map_layers_service.py
  tests\test_device_map_service.py tests\test_dashboard_map_page_layout.py
  -v --tb=short` passed 56 tests.
- `.venv\Scripts\python.exe -m py_compile
  moduly\apps\dashboard\map_shared.py` passed.
- `git diff --check -- moduly/apps/dashboard/map_shared.py
  tests/test_dashboard_map_shared.py` reported no whitespace errors, only
  expected LF-to-CRLF warnings.

Not verified before restart:
- Full pytest suite was not run.
- Live authenticated browser click on a real map object/photo was not tested.
- Production `.venv-production` verification was not rerun in this handoff.
- Runtime Caddyfile hash equality was not checked in this handoff.

Sensitive/runtime artifacts:
- Do not print, read, delete, revert, stage, or commit raw values from ignored
  local `.env`, API/dashboard tokens, passwords, cookies, authentication audit
  logs, ProgramData security artifacts, or local leftover SmartFuelPass session
  JSON files.
- `data/smartfuelpass/session_cookies.json` and
  `data/smartfuelpass/auto_login_session.json` remain sensitive historical
  session artifacts and are currently deleted from the Git index in the dirty
  working tree. Do not inspect or restore their contents.
- Do not create a production code-integrity baseline from the dirty working
  tree unless the user explicitly approves that exact state.
- For the map-photo verification, browser DevTools may show whether a cookie
  was included, but cookie values must not be printed or copied.

Expected processes and listeners after restart:
- Windows Task Scheduler runs `API_dashboard_caddy` at system startup and its
  latest run result becomes `0`.
- One rotating-log wrapper owns one non-reload Uvicorn child on
  `127.0.0.1:8000`.
- One rotating-log wrapper owns one Streamlit child on `127.0.0.1:8001`.
- One scheduler runtime runs `main.py`, holds the `scheduler_process` lock,
  and updates `core/scheduler/logs/scheduler_metrics.json`.
- One Caddy runtime owns TCP `80`/`443` and admin `127.0.0.1:2019`.
- Tailscale interface-specific `443` listeners may remain in addition.
- No listener should remain on temporary ports `8010` or `8011`.

Expected application state after restart:
- FastAPI `/health/live` and `/health/ready`: HTTP 200 while PostgreSQL is
  available.
- Streamlit `/_stcore/health` and Caddy admin endpoint: HTTP 200.
- HTTPS dashboard: HTTP 200.
- HTTP hostname route: HTTP 308 to HTTPS.
- Protected bearer API without bearer token: HTTP 401 JSON.
- Map image without dashboard session cookie: HTTP 401.
- Public `/api/v1/auth/users-exist`: HTTP 200 with minimal boolean payload.
- FastAPI docs remain disabled. Public `/docs`, `/redoc`, and
  `/openapi.json` should return HTTP 404 after runtime Caddy deployment is
  synchronized.
- Generated map HTML must still contain no `Authorization`, `Bearer`, access
  token, or `mapImageAccessToken` text.
- Generated map photo loading should call `/api/v1/map/images` with
  `credentials: "include"`.

Required post-restart checks:
- Confirm boot time, scheduled-task last run/result/settings, process tree,
  listeners, and no temporary ports `8010` or `8011`.
- Confirm `.venv-production` exact-lock verification and `pip check`.
- Confirm API live/ready, Streamlit health, Caddy admin health, and scheduler
  heartbeat.
- Confirm latest/next `quarter_hour_job` state from scheduler metrics.
- Confirm tracked/runtime Caddyfile hash equality and Caddy validation. If
  they differ, run `scripts\deploy_caddy_runtime.ps1` from an elevated
  administrator PowerShell session and reload Caddy before rechecking public
  proxy findings.
- Verify HTTP redirect, HTTPS dashboard, protected API, unauthenticated map
  image, disabled docs, session refresh, and public `users-exist` status codes.
- Open an authenticated browser session and validate the change-specific map
  workflow: `Mapove podklady / Mapa` -> click a Vodomery object with a photo
  -> confirm the popup photo loads and the lightbox opens.
- If the photo still fails, inspect only status code and safe headers for
  `/api/v1/map/images`; do not print cookie or token values.
- Rerun the targeted map tests:
  `.venv\Scripts\python.exe -m pytest tests\test_dashboard_map_shared.py
  tests\test_map_routes.py tests\test_map_layers_service.py
  tests\test_device_map_service.py tests\test_dashboard_map_page_layout.py
  -v --tb=short`.
- Run `git diff --check` and finish with
  `git status --short --untracked-files=all`.
- Append a dated post-restart verification entry with deviations and accepted
  gaps.

Known risks or accepted gaps:
- The map-photo fix has not yet been validated with a real authenticated
  browser click.
- Current changes are uncommitted and depend on the working tree being
  preserved across restart.
- Earlier P2.17 external security verification and runtime Caddy deployment
  synchronization topics may still be open.
- The launcher does not independently restart a child process that fails after
  startup.

## 2026-06-25 06:52 +02:00 - Pre-restart handoff after map photo iframe fix

Reason for restart:
- User requested saving the current conversation state before restarting the
  workstation.
- Restart is expected to reload FastAPI, Streamlit, scheduler, and Caddy from
  the normal Windows startup task.

Current task/conversation state:
- Completed: diagnosed the `Mapove podklady / Mapa` popup photo failure as a
  browser credential issue in the Streamlit component iframe.
- Completed: changed map popup photo fetches from `credentials: "same-origin"`
  to `credentials: "include"` so the HttpOnly dashboard session cookie can be
  attached to `/api/v1/map/images` from the iframe.
- Completed: preserved the P1.7 security rule that the main bearer token is
  not passed into generated map HTML or JavaScript.
- Pending after restart: open the dashboard through
  `https://monitoring.armexholding.cz`, go to `Mapove podklady / Mapa`, click
  a Vodomery object with `has_photo`, and confirm the photo loads instead of
  `Fotku se nepodarilo nacist.`
- Pending after restart: if the popup still fails, inspect the browser network
  status for `/api/v1/map/images` without printing cookies or token values.
- First action after restart: read `AGENTS.md`, `DECISIONS.md`, and
  `SESSION_NOTES.md`, then run `git status --short --untracked-files=all`.

Working tree and deployment:
- Current time captured before restart: 2026-06-25 06:52:21 +02:00.
- Branch: `master`.
- `HEAD`: `69dc532eccbc49db3152e7a1ce0627392375601b`.
- No git commit was created for this handoff.
- `git status --short --untracked-files=all` before restart:
  - `M .env.example`
  - `M .gitignore`
  - `M AGENTS.md`
  - `M Caddyfile`
  - `M DASHBOARD_SECURITY_CHECKLIST.md`
  - `M DECISIONS.md`
  - `M SESSION_NOTES.md`
  - `D data/smartfuelpass/auto_login_session.json`
  - `D data/smartfuelpass/session_cookies.json`
  - `M moduly/apps/dashboard/map_shared.py`
  - `M moduly/apps/smartfuelpass/__init__.py`
  - `M moduly/apps/smartfuelpass/service.py`
  - `M requirements-production.in`
  - `M requirements-production.lock.txt`
  - `M scripts/code_integrity_scan.py`
  - `M scripts/register_code_integrity_scan_task.ps1`
  - `M tests/test_caddy_config.py`
  - `M tests/test_code_integrity_scan.py`
  - `M tests/test_dashboard_map_shared.py`
  - `M tests/test_smartfuelpass_service.py`
  - `?? SECURITY_SECRET_INVENTORY.md`
  - `?? requirements-security.in`
  - `?? requirements-security.lock.txt`
  - `?? scripts/bootstrap_security_toolchain.ps1`
  - `?? scripts/register_dependency_audit_task.ps1`
  - `?? scripts/run_dependency_audit.ps1`
  - `?? scripts/secret_hygiene_scan.py`
  - `?? tests/test_dependency_audit_tooling.py`
  - `?? tests/test_secret_hygiene_scan.py`
- Files changed in this final map-photo fix only:
  - `moduly/apps/dashboard/map_shared.py`
  - `tests/test_dashboard_map_shared.py`
- Existing unrelated dirty files are from earlier security, Caddy,
  SmartFuelPass, dependency-audit, and code-integrity work. Do not revert or
  clean them without explicit approval.
- Tracked root `Caddyfile` SHA-256 before restart:
  `08CDF04AFC4F856FEC8DFE4AB2E07A746763B152CA91553E349CCCE8E6D3DF2C`.
- Runtime Caddyfile hash equality was not checked in this handoff from
  `C:\Program Files\Caddy\Caddyfile`; verify after restart.
- Existing listener state before restart:
  - Caddy owned TCP `:80` and `:443`, PID `10048`.
  - Caddy admin listened on `127.0.0.1:2019`, PID `10048`.
  - FastAPI listened on `127.0.0.1:8000`, PID `11252`.
  - Streamlit listened on `127.0.0.1:8001`, PID `11972`.
  - Tailscale owned expected interface-specific `443` listeners on
    `100.66.79.74` and `fd7a:115c:a1e0::e38:4f4b`, PID `7060`.
- Runtime health before restart:
  - FastAPI `/health/live`: HTTP 200 on `127.0.0.1:8000`.
  - FastAPI `/health/ready`: HTTP 200 on `127.0.0.1:8000`.
  - Streamlit `/_stcore/health`: HTTP 200 on `127.0.0.1:8001`.
  - Caddy admin `/config/`: HTTP 200 on `127.0.0.1:2019`.
- Scheduler metrics before restart:
  - `scheduler_running=True`.
  - Heartbeat observed at `2026-06-25T06:52:24.432676`.
  - `quarter_hour_job` detail was not extracted by the quick handoff command;
    verify latest/next job state after restart.

Verification already run for the map-photo fix:
- `.venv\Scripts\python.exe -m pytest tests\test_dashboard_map_shared.py
  tests\test_map_routes.py tests\test_map_layers_service.py
  tests\test_device_map_service.py tests\test_dashboard_map_page_layout.py
  -v --tb=short` passed 56 tests.
- `.venv\Scripts\python.exe -m py_compile
  moduly\apps\dashboard\map_shared.py` passed.
- `git diff --check -- moduly/apps/dashboard/map_shared.py
  tests/test_dashboard_map_shared.py` reported no whitespace errors, only
  expected LF-to-CRLF warnings.

Not verified before restart:
- Full pytest suite was not run.
- Live authenticated browser click on a real map object/photo was not tested.
- Production `.venv-production` verification was not rerun in this handoff.
- Runtime Caddyfile hash equality was not checked in this handoff.

Sensitive/runtime artifacts:
- Do not print, read, delete, revert, stage, or commit raw values from ignored
  local `.env`, API/dashboard tokens, passwords, cookies, authentication audit
  logs, ProgramData security artifacts, or local leftover SmartFuelPass session
  JSON files.
- `data/smartfuelpass/session_cookies.json` and
  `data/smartfuelpass/auto_login_session.json` remain sensitive historical
  session artifacts and are currently deleted from the Git index in the dirty
  working tree. Do not inspect or restore their contents.
- Do not create a production code-integrity baseline from the dirty working
  tree unless the user explicitly approves that exact state.
- For the map-photo verification, browser DevTools may show whether a cookie
  was included, but cookie values must not be printed or copied.

Expected processes and listeners after restart:
- Windows Task Scheduler runs `API_dashboard_caddy` at system startup and its
  latest run result becomes `0`.
- One rotating-log wrapper owns one non-reload Uvicorn child on
  `127.0.0.1:8000`.
- One rotating-log wrapper owns one Streamlit child on `127.0.0.1:8001`.
- One scheduler runtime runs `main.py`, holds the `scheduler_process` lock,
  and updates `core/scheduler/logs/scheduler_metrics.json`.
- One Caddy runtime owns TCP `80`/`443` and admin `127.0.0.1:2019`.
- Tailscale interface-specific `443` listeners may remain in addition.
- No listener should remain on temporary ports `8010` or `8011`.

Expected application state after restart:
- FastAPI `/health/live` and `/health/ready`: HTTP 200 while PostgreSQL is
  available.
- Streamlit `/_stcore/health` and Caddy admin endpoint: HTTP 200.
- HTTPS dashboard: HTTP 200.
- HTTP hostname route: HTTP 308 to HTTPS.
- Protected bearer API without bearer token: HTTP 401 JSON.
- Map image without dashboard session cookie: HTTP 401.
- Public `/api/v1/auth/users-exist`: HTTP 200 with minimal boolean payload.
- FastAPI docs remain disabled. Public `/docs`, `/redoc`, and
  `/openapi.json` should return HTTP 404 after runtime Caddy deployment is
  synchronized.
- Generated map HTML must still contain no `Authorization`, `Bearer`, access
  token, or `mapImageAccessToken` text.
- Generated map photo loading should call `/api/v1/map/images` with
  `credentials: "include"`.

Required post-restart checks:
- Confirm boot time, scheduled-task last run/result/settings, process tree,
  listeners, and no temporary ports `8010` or `8011`.
- Confirm `.venv-production` exact-lock verification and `pip check`.
- Confirm API live/ready, Streamlit health, Caddy admin health, and scheduler
  heartbeat.
- Confirm latest/next `quarter_hour_job` state from scheduler metrics.
- Confirm tracked/runtime Caddyfile hash equality and Caddy validation. If
  they differ, run `scripts\deploy_caddy_runtime.ps1` from an elevated
  administrator PowerShell session and reload Caddy before rechecking public
  proxy findings.
- Verify HTTP redirect, HTTPS dashboard, protected API, unauthenticated map
  image, disabled docs, session refresh, and public `users-exist` status codes.
- Open an authenticated browser session and validate the change-specific map
  workflow: `Mapove podklady / Mapa` -> click a Vodomery object with a photo
  -> confirm the popup photo loads and the lightbox opens.
- If the photo still fails, inspect only status code and safe headers for
  `/api/v1/map/images`; do not print cookie or token values.
- Rerun the targeted map tests:
  `.venv\Scripts\python.exe -m pytest tests\test_dashboard_map_shared.py
  tests\test_map_routes.py tests\test_map_layers_service.py
  tests\test_device_map_service.py tests\test_dashboard_map_page_layout.py
  -v --tb=short`.
- Run `git diff --check` and finish with
  `git status --short --untracked-files=all`.
- Append a dated post-restart verification entry with deviations and accepted
  gaps.

Known risks or accepted gaps:
- The map-photo fix has not yet been validated with a real authenticated
  browser click.
- Current changes are uncommitted and depend on the working tree being
  preserved across restart.
- Earlier P2.17 external security verification and runtime Caddy deployment
  synchronization topics may still be open.
- The launcher does not independently restart a child process that fails after
  startup.

## 2026-06-18 13:56 +02:00 - Post-restart verification after SmartFuelPass/P2.17 restart

Scope:
- Performed the required read-only post-restart runtime and security checks
  after the workstation restart.
- Attempted the tracked-to-runtime Caddy deployment step, but it could not run
  from the current non-elevated PowerShell session.

Verified:
- Windows boot time was `2026-06-18 13:28:45 +02:00`.
- Scheduled task `API_dashboard_caddy` last ran at `2026-06-18 13:28:55`
  with result `0`, state `Ready`, user `tra`, and run level `Highest`.
- Listeners were present on Caddy `:80`, `:443`, and `127.0.0.1:2019`,
  FastAPI `127.0.0.1:8000`, and Streamlit `127.0.0.1:8001`.
- No listeners were present on temporary ports `8010` or `8011`.
- `.venv-production` matched `requirements-production.lock.txt`, and
  `pip check` reported no broken requirements.
- FastAPI `/health/live`, FastAPI `/health/ready`, Streamlit
  `/_stcore/health`, and Caddy admin `/config/` returned HTTP 200.
- Scheduler metrics reported `scheduler_running=True` and heartbeat
  `2026-06-18T13:39:01.901482`.
- `quarter_hour_job` last ran successfully at
  `2026-06-18T13:35:09.165524`, next run
  `2026-06-18T13:47:05+02:00`, with zero 24h failures.
- `hourly_job` and `daily_job` also reported successful latest runs and zero
  24h failures.
- SmartFuelPass manual-run registry contains
  `sync_charge_sessions_to_db`, `smartfuelpass_weekly_report_job`, and
  `send_charge_sessions_report_email` with expected labels and locks.
- Loopback hostname checks returned HTTP 308 for HTTP root, HTTP 200 for the
  HTTPS dashboard, HTTP 401 for protected map catalog without bearer,
  HTTP 401 for map image without cookie, HTTP 401 for session refresh without
  bearer, and HTTP 200 for public `users-exist`.
- HTTPS dashboard/API responses had the reviewed security headers and did not
  expose `Server` or `Via`.
- `tests\test_smartfuelpass_service.py` and
  `tests\test_smartfuelpass_sync.py` passed: 28 tests.
- Security/tooling tests passed: `tests\test_secret_hygiene_scan.py`,
  `tests\test_code_integrity_scan.py`,
  `tests\test_dependency_audit_tooling.py`, `tests\test_caddy_config.py`,
  and `tests\test_api_public_exposure.py`: 19 tests.
- `scripts\code_integrity_scan.py baseline` refused to create a baseline on
  dirty scanned files without explicit approval.
- Redacted `scripts\secret_hygiene_scan.py` reported 17 expected current
  findings for tracked scheduler locks, `frontend_next/tsconfig.tsbuildinfo`,
  and old electric-meter source data paths; no current SmartFuelPass session
  JSON findings were present.
- `git diff --check` reported no whitespace errors, only existing LF/CRLF
  warnings.

Deviations:
- Tracked `Caddyfile` SHA-256 was
  `B72714F21E00CB6CD1F27391707D7B0BF5442ED47C8DF6B59C225F4E1DEAA980`.
- Runtime `C:\Program Files\Caddy\Caddyfile` SHA-256 was
  `3387659A473097A43B76B7951D833463F77F7C0AC559975271EA3F48B59D1802`.
- Runtime Caddyfile validation passed, but it still showed automatic
  HTTP-to-HTTPS redirects enabled.
- Public `/docs`, `/redoc`, and `/openapi.json` still returned HTTP 200 via
  the Streamlit fallback because the runtime Caddyfile had not been deployed.
- HTTP redirect still exposed a `Server` header for the same reason.
- `scripts\deploy_caddy_runtime.ps1` was invoked through an approved
  escalated command but failed with its intended administrator-session guard:
  `This script must run from an elevated administrator PowerShell session.`

Not verified:
- Authenticated Streamlit `Sprava / Health scheduleru` manual-run UI was not
  verified because no browser/admin session was used in this check.
- No live SmartFuelPass portal login/manual run was executed.
- True external-network P2.17 verification outside the server/corporate LAN
  remains open.

Follow-up:
- Run `scripts\deploy_caddy_runtime.ps1` from an elevated administrator
  PowerShell session, then recheck runtime/tracked Caddyfile hash equality,
  Caddy validation, `/docs`/`/redoc`/`/openapi.json` HTTP 404, and absence of
  `Server`/`Via` headers on HTTP redirects.
- Review/commit or explicitly approve the current dirty working tree before
  creating the first production code-integrity baseline.

## 2026-06-18 14:08 +02:00 - Caddy runtime proxy fix deployed

Scope:
- Resolved the remaining post-restart Caddy runtime deviation.

Changed:
- Wrapped the public Caddy routing rules in an explicit `route` block so
  `/docs`, `/redoc`, and `/openapi.json` are handled before the Streamlit
  fallback after Caddy adapts the Caddyfile.
- Tightened `tests/test_caddy_config.py` to require that ordered route block.
- Deployed the tracked `Caddyfile` to `C:\Program Files\Caddy\Caddyfile`
  through `scripts\deploy_caddy_runtime.ps1` from an elevated PowerShell
  process.

Verified:
- Tracked and runtime Caddyfile SHA-256 values matched:
  `08CDF04AFC4F856FEC8DFE4AB2E07A746763B152CA91553E349CCCE8E6D3DF2C`.
- Runtime Caddy validation reported `Valid configuration` and automatic
  HTTP-to-HTTPS redirects disabled.
- Loopback hostname checks returned HTTP 308 for HTTP root, HTTP 200 for the
  HTTPS dashboard, HTTP 401 for protected map catalog without bearer,
  HTTP 401 for map image without cookie, HTTP 401 for session refresh without
  bearer, HTTP 200 for public `users-exist`, and HTTP 404 for `/docs`,
  `/redoc`, and `/openapi.json`.
- HTTP redirect, HTTPS dashboard, HTTPS docs, and HTTPS `users-exist`
  responses did not expose `Server` or `Via` headers.
- FastAPI live/ready, Streamlit health, and Caddy admin health returned
  HTTP 200 after reload.
- Caddy/API public exposure tests passed:
  `.venv\Scripts\python.exe -m pytest tests\test_caddy_config.py
  tests\test_api_public_exposure.py -q --tb=short`.

Not verified:
- No authenticated browser workflows were retested in this step.

## 2026-06-18 14:12 +02:00 - P2.17 automated security regression follow-up

Scope:
- Continued P2.17 after the Caddy runtime fix by running the existing
  automated security regression set for login/session behavior, token
  revocation, authorization boundaries, and map/photo file-serving controls.

Changed:
- Updated `DASHBOARD_SECURITY_CHECKLIST.md` to record the deployed Caddy
  runtime remediation and automated security regression coverage.
- Marked the login/session, authorization-boundary, and common attack-scenario
  P2.17 checklist items as partial because automated tests passed, but full
  external and authenticated browser verification remains open.

Verified:
- `.venv\Scripts\python.exe -m pytest tests\test_auth_routes.py
  tests\test_login_throttle.py tests\test_auth_audit.py
  tests\test_admin_auth_audit.py tests\test_dashboard_auth_state.py
  tests\test_dashboard_session_security.py
  tests\test_api_authorization_regression.py
  tests\test_admin_write_authorization.py tests\test_map_routes.py
  tests\test_map_layers_service.py tests\test_device_map_service.py
  tests\test_dashboard_map_shared.py tests\test_dashboard_device_photo.py
  tests\test_api_public_exposure.py tests\test_caddy_config.py -q --tb=short`
  passed 283 tests.

Not verified:
- True external-network P2.17 test outside the server and corporate LAN.
- Authenticated browser workflows for login throttling, session expiry,
  logout, token revocation, and UI-level authorization behavior.
- Manual penetration-style XSS/CSRF/injection/path traversal testing against
  the live authenticated dashboard.

## 2026-06-18 - SmartFuelPass Session JSON Persistence Retired

- User approved replacing SmartFuelPass JSON session persistence with password
  login only.
- Updated SmartFuelPass service code so reporting snapshots and charge-session
  imports use a fresh Playwright context and `SMARTFUELPASS_EMAIL` /
  `SMARTFUELPASS_PASSWORD` login for each portal run.
- Kept existing `cookie_path` parameters as compatibility no-ops; application
  code no longer reads or writes `data/smartfuelpass/session_cookies.json` or
  `data/smartfuelpass/auto_login_session.json`.
- Removed both SmartFuelPass session JSON files from the Git index with
  `git rm --cached`; local ignored copies were not read or deleted.
- Removed `SMARTFUELPASS_SESSION_COOKIES_PATH` from `.env.example`.
- Added DEC-044 documenting that SmartFuelPass sessions must not be persisted
  as JSON.
- Verification:
  - `.venv\Scripts\python.exe -m py_compile moduly\apps\smartfuelpass\service.py
    moduly\apps\smartfuelpass\__init__.py`
  - `.venv\Scripts\python.exe -m pytest tests\test_smartfuelpass_service.py
    tests\test_smartfuelpass_sync.py -q --tb=short` passed 28 tests.
  - `.venv\Scripts\python.exe -m pytest tests\test_smartfuelpass_service.py
    tests\test_smartfuelpass_sync.py tests\test_secret_hygiene_scan.py
    tests\test_code_integrity_scan.py tests\test_dependency_audit_tooling.py
    tests\test_production_runtime.py tests\test_dashboard_security_config.py
    -q --tb=short` passed 59 tests.
  - `.venv\Scripts\python.exe scripts\secret_hygiene_scan.py` reported
    `status=findings findings=17 raw_values=not_included`; redacted metadata
    showed only tracked electric-meter source files, scheduler lock files, and
    `frontend_next/tsconfig.tsbuildinfo` as current findings.
- Remaining related risk: historical or local leftover SmartFuelPass session
  JSON values remain sensitive. Do not print or inspect their contents; expire
  portal sessions externally if old cookies may still be valid.

## 2026-06-18 - P2.17 External Security Verification Started

- Public-hostname requests from the server to
  `https://monitoring.armexholding.cz/` and
  `http://monitoring.armexholding.cz/` timed out, so a true external-network
  check outside the server/LAN remains required.
- Loopback SNI checks with `curl --resolve monitoring.armexholding.cz:443:127.0.0.1`
  verified HTTPS dashboard HTTP 200 and certificate validation without `-k`.
- HTTPS security headers were present through loopback hostname: HSTS,
  `nosniff`, `Referrer-Policy`, `X-Frame-Options`, `Permissions-Policy`, and
  CSP report-only. `Server` and `Via` were absent on HTTPS responses.
- Public `users-exist` returned HTTP 200 with only the minimal boolean payload.
- Unauthenticated `POST /api/v1/auth/session/refresh` returned HTTP 401.
- Unauthenticated `/api/v1/map/images` without the dashboard session cookie
  returned HTTP 401.
- Findings in the running runtime before deployment:
  - HTTP redirect response still included `Server: Caddy`.
  - Public `/docs`, `/redoc`, and `/openapi.json` fell through to the
    Streamlit shell with HTTP 200.
- Updated tracked `Caddyfile` to use `auto_https disable_redirects`, an
  explicit HTTP redirect block with `-Server`/`-Via`, explicit HTTPS site
  block, and HTTP 404 responses for `/docs`, `/redoc`, and `/openapi.json`
  before API/Streamlit handlers.
- Added DEC-045 for public proxy documentation aliases and explicit redirect
  handling.
- Validation:
  - `C:\Program Files\Caddy\caddy.exe validate --config Caddyfile --adapter caddyfile`
    passed and reported automatic HTTP redirects disabled for the HTTPS site.
  - `.venv\Scripts\python.exe -m pytest tests\test_caddy_config.py
    tests\test_api_public_exposure.py tests\test_dashboard_security_config.py
    -q --tb=short` passed 18 tests.
  - `.venv\Scripts\python.exe -m pytest tests\test_caddy_config.py
    -q --tb=short` passed 4 tests after the final Caddyfile adjustment.
- Runtime deployment attempt with `scripts\deploy_caddy_runtime.ps1` failed
  because the current shell is not an elevated administrator PowerShell
  session. The runtime file at `C:\Program Files\Caddy\Caddyfile` still needs
  deployment/reload from an elevated shell.

### 2026-06-18 - Dashboard security checklist P2.15 dependency audit

Scope:
- Continued `DASHBOARD_SECURITY_CHECKLIST.md` P2.15 after the user confirmed
  P1.6 MFA/SSO is intentionally skipped for now.
- Added dependency vulnerability scanning while preserving the production
  exact-lock runtime model.

Changed:
- Added `requirements-security.in` and `requirements-security.lock.txt` for an
  isolated `.venv-security` audit toolchain with `pip-audit==2.10.1`.
- Added `scripts/bootstrap_security_toolchain.ps1`,
  `scripts/run_dependency_audit.ps1`, and
  `scripts/register_dependency_audit_task.ps1`.
- Updated `requirements-production.in` and
  `requirements-production.lock.txt` from `pypdf==6.12.2` to
  `pypdf==6.13.0` after the first audit found `CVE-2026-54531` and
  `CVE-2026-54530`.
- Updated the local `.venv-production` installation to `pypdf==6.13.0`.
- Updated `.gitignore` for `.venv-security/` and
  `.codex/local_programdata/`.
- Fixed scheduled-task registration script compatibility for both dependency
  audit and code-integrity scan by using `-At $time`,
  `-LogonType Interactive`, and `-RunLevel Limited`.
- Updated `scripts/code_integrity_scan.py` so untracked `.in`
  source/configuration files are included in unexpected-file detection.
- Added dependency-audit and code-integrity regression coverage.
- Updated `AGENTS.md`, `DECISIONS.md`, and
  `DASHBOARD_SECURITY_CHECKLIST.md`.

Verified:
- Created `.venv-security` from `.venv-production` Python and installed
  `pip-audit==2.10.1`; `.venv-security` passed `pip check`.
- `.venv-security\Scripts\python.exe -m pip_audit --version` returned
  `pip-audit 2.10.1`.
- The first dependency audit found two `pypdf==6.12.2` vulnerabilities in both
  the production lock and installed environment, with fix version `6.13.0`.
- After updating `pypdf`, `.venv-production\Scripts\python.exe
  scripts\verify_production_environment.py` passed.
- `.venv-production\Scripts\python.exe -m pip check` passed.
- `scripts\run_dependency_audit.ps1 -ReportDir
  .codex\local_programdata\logs\security` returned status `ok` with no known
  vulnerabilities for both requirements and installed environment.
- `scripts\run_dependency_audit.ps1` wrote clean dependency audit reports under
  `C:\ProgramData\monitorovaci_platforma\logs\security`.
- Registered Windows scheduled task `MonitoringDependencyAudit` for daily
  03:40.
- Started `MonitoringDependencyAudit` once through Task Scheduler; it finished
  with `LastTaskResult=0` at 2026-06-18 07:43:37 CEST and next run
  2026-06-19 03:40:00 CEST.
- Reviewed active dashboard browser asset references: no external executable
  script source is loaded by active dashboard files; remaining external browser
  endpoints are data/image endpoints such as Open-Meteo and map tiles.
- `scripts\run_code_integrity_scan.ps1 -Mode Baseline` refused the dirty
  scanned working tree as expected and now includes `requirements-security.in`
  in the dirty path list.
- `.venv\Scripts\python.exe -m pytest
  tests\test_code_integrity_scan.py tests\test_dependency_audit_tooling.py
  tests\test_production_runtime.py tests\test_dashboard_security_config.py
  tests\test_dashboard_map_shared.py -q --tb=short` passed 40 tests.

Not verified:
- The full test suite was not run.
- Code-integrity production baseline was not created because the current
  scanned working tree is dirty.
- `MonitoringCodeIntegrityScan` was not registered or run because there is no
  approved production manifest baseline yet.
- No workstation restart or authenticated browser Scheduler Health manual-run
  verification was performed in this step.

Decisions/notes:
- Added DEC-042: dependency audits use isolated `.venv-security`; do not
  install `pip-audit` into `.venv-production`.
- P1.6 remains an accepted password-only administrator residual risk by user
  decision, not a blocker for P2 work.
- Dependency audit uses fully pinned requirements with `--no-deps`; hash-pinned
  requirements are a possible future hardening step.

Follow-up:
- Review and commit, or explicitly approve, the current dirty working tree
  before creating the production code-integrity baseline.
- After the baseline exists, register and run `MonitoringCodeIntegrityScan`.
- Continue with P2.16 secret/runtime artifact hygiene.

### 2026-06-18 - Dashboard security checklist P2.16 secret hygiene

Scope:
- Continued `DASHBOARD_SECURITY_CHECKLIST.md` P2.16.
- Searched tracked files, untracked source files, and reachable Git history for
  credentials, tokens, cookies, private operational data, and runtime
  artifacts without printing raw values.

Changed:
- Added `scripts/secret_hygiene_scan.py`, a redacted metadata scanner that
  reports rule, severity, path, line number, and commit while writing
  `value=REDACTED`.
- Added `tests/test_secret_hygiene_scan.py`.
- Added `SECURITY_SECRET_INVENTORY.md` with non-secret production secret and
  sensitive artifact locations plus access expectations.
- Updated `.gitignore` so future additions of SmartFuelPass session JSON,
  scheduler lock files, nested electric-meter source data, frontend
  `tsconfig.tsbuildinfo`, SOFTLINK auth JSON, `.env*`, and `run.txt` are
  ignored.
- Updated `AGENTS.md`, `DECISIONS.md`, and
  `DASHBOARD_SECURITY_CHECKLIST.md`.

Verified:
- `git check-ignore --no-index -v` confirmed ignore coverage for `.env`,
  `.env.local`, SmartFuelPass session JSON files, SOFTLINK auth JSON,
  scheduler lock files, `frontend_next/tsconfig.tsbuildinfo`, nested
  electric-meter `.ts` and `.xlsx` source artifacts, and `run.txt`.
- `git ls-files` confirmed `.env` and `SOFTLINK/lds_auth.json` are not
  currently tracked, while `data/smartfuelpass/session_cookies.json`,
  `data/smartfuelpass/auto_login_session.json`, and `run.txt` remain tracked.
- `.venv\Scripts\python.exe -m pytest tests\test_secret_hygiene_scan.py -q
  --tb=short` passed 3 tests.
- `.venv\Scripts\python.exe scripts\secret_hygiene_scan.py --history --output
  .codex\local_programdata\logs\security\secret_hygiene_report_20260618.json`
  completed with redacted findings only.
- Final redacted scan summary: 78 findings, including 39 critical, 18 high,
  and 21 medium metadata findings; no raw values were printed.
- Current critical tracked paths reported by the final scan:
  `data/smartfuelpass/session_cookies.json` and
  `data/smartfuelpass/auto_login_session.json`.
- Current high tracked private source-data paths reported:
  `moduly/mereni/elektromery/data/old/*.ts` and
  `moduly/mereni/elektromery/data/old/*.xlsx`.
- Current medium tracked runtime/build artifacts reported:
  `core/scheduler/locks/*.lock` and `frontend_next/tsconfig.tsbuildinfo`.
- Historical redacted findings included `.env` paths, hard-coded
  `API_TOKEN_SECRET` assignments in launch scripts and `run.txt`,
  SmartFuelPass session JSON paths, SOFTLINK auth path, and tracked
  operational/build artifacts. The historical API signing secret had already
  been rotated on 2026-06-12.

Not verified:
- Raw SmartFuelPass cookie/session payloads were not printed or inspected.
- SmartFuelPass sessions were not invalidated and tracked session JSON files
  were not removed from Git.
- SOFTLINK credentials/session were not externally rotated.
- Git history was not rewritten.
- Full test suite was not run.

Decisions/notes:
- Added DEC-043: secret hygiene reviews use redacted metadata.
- P2.16 is partially complete. Search, ignore verification, and secret
  inventory documentation are complete; active tracked SmartFuelPass session
  artifacts keep the completion criterion open.

Follow-up:
- Invalidate/rotate SmartFuelPass portal sessions before untracking or
  deleting tracked session JSON files.
- Rotate SOFTLINK credentials/session externally if the historical auth file
  value is still valid.
- Decide whether to untrack/remove tracked runtime/data/build artifacts:
  SmartFuelPass session JSON, scheduler lock files, electric-meter source
  data artifacts, and `frontend_next/tsconfig.tsbuildinfo`.
- Continue to P2.17 only after accepting that P2.16 cleanup remains blocked,
  or after the above cleanup is explicitly approved and completed.

### 2026-06-17 08:51 CEST - Post-restart verification

Scope:
- Checked runtime state after the 2026-06-17 workstation restart requested to
  activate the Scheduler Health manual-run progress/log panel.

Changed:
- Appended this post-restart verification note.

Verified:
- Windows boot time was 2026-06-17 08:43:52 CEST.
- Scheduled task `API_dashboard_caddy` last ran at 2026-06-17 08:44:02 CEST
  with result `0`; the task uses a boot trigger, `RunLevel=Highest`, and user
  `tra`.
- Listeners were present on Caddy `:80`/`:443`, Caddy admin
  `127.0.0.1:2019`, FastAPI `127.0.0.1:8000`, and Streamlit
  `127.0.0.1:8001`; no listeners were present on temporary ports `8010` or
  `8011`. Tailscale still had expected interface-specific `443` listeners.
- Local health checks returned HTTP 200 for FastAPI `/health/live`,
  FastAPI `/health/ready`, Streamlit `/_stcore/health`, and Caddy admin
  `/config/`.
- `.venv-production` passed `pip check` and
  `scripts/verify_production_environment.py`.
- The tracked root `Caddyfile` and runtime
  `C:\Program Files\Caddy\Caddyfile` SHA-256 hashes matched
  `3387659A473097A43B76B7951D833463F77F7C0AC559975271EA3F48B59D1802`, and
  `caddy validate` reported a valid configuration.
- Loopback Caddy checks using host `monitoring.armexholding.cz` returned HTTP
  308 for HTTP root, HTTP 200 for HTTPS dashboard, HTTP 401 for protected map
  catalog without bearer token, HTTP 401 for map image without cookie, HTTP
  401 for session refresh without bearer token, and HTTP 200 for public
  `users-exist`.
- Direct FastAPI checks returned HTTP 404 for `/docs`, `/redoc`, and
  `/openapi.json`.
- Scheduler metrics showed `scheduler_running=True`, heartbeat
  `2026-06-17T08:49:07.691389`, `quarter_hour_job` success at
  `2026-06-17T08:47:09.230514`, next `quarter_hour_job` at
  `2026-06-17T09:05:05+02:00`, and zero `quarter_hour_job` failures in the
  last 24 hours.
- The production scheduler manual-run registry included
  `sync_charge_sessions_to_db` with label `Zapis SmartFuelPass relaci do
  databaze` and lock `daily_job`, plus `smartfuelpass_weekly_report_job` with
  label `SmartFuelPass weekly report job` and
  `send_charge_sessions_report_email` with label `Odeslani SmartFuelPass PDF
  emailu`, both using lock `smartfuelpass_weekly_report_job`.
- `.venv\Scripts\python.exe -m pytest tests\test_dashboard_scheduler_log_view.py
  tests\test_scheduler_metrics.py tests\test_code_integrity_scan.py
  tests\test_scheduler.py -q --tb=short` passed 66 tests.
- `.venv-production\Scripts\python.exe -m py_compile` passed for the changed
  scheduler, SOFTLINK, dashboard Scheduler Health, scheduler log-view,
  code-integrity, and related test modules.
- Code-integrity baseline creation still refused the dirty working tree, as
  expected before an approved baseline.
- `git diff --check` reported no whitespace errors, only existing LF-to-CRLF
  warnings.

Not verified:
- Authenticated browser click-through of `Sprava / Health scheduleru` was not
  performed because no administrator bearer token, cookie, or credentials were
  inspected.
- True external access from outside the server/LAN was not verified; loopback
  hostname routing through Caddy was verified.
- No production code-integrity baseline was created and no scheduled
  code-integrity task was registered.

Working tree after verification before this note:
- `M AGENTS.md`
- `M DASHBOARD_SECURITY_CHECKLIST.md`
- `M DECISIONS.md`
- `M SESSION_NOTES.md`
- `M core/scheduler/job_schedule.py`
- `M core/scheduler/scheduler.py`
- `M data/smartfuelpass/session_cookies.json`
- `M moduly/apps/dashboard/pages/16_scheduler_health.py`
- `M moduly/apps/dashboard/scheduler_log_view.py`
- `M moduly/mereni/elektromery/SOFTLINK/SOFTLINK_data_z_dotazu.py`
- `M tests/test_dashboard_scheduler_log_view.py`
- `M tests/test_scheduler.py`
- `?? scripts/code_integrity_scan.py`
- `?? scripts/register_code_integrity_scan_task.ps1`
- `?? scripts/run_code_integrity_scan.ps1`
- `?? tests/test_code_integrity_scan.py`

Follow-up:
- Verify the new Scheduler Health manual-run panel in an authenticated
  browser session with a low-risk manual target.
- Review/commit or explicitly approve the dirty working tree before creating
  the production code-integrity baseline.
- Dependency vulnerability scanning remains open for P2.15.

### 2026-06-17 - Scheduler Health manual-run log fix

Scope:
- Fixed the Scheduler Health manual-run progress panel that stayed on
  `Cekam na prvni zaznam rucniho behu v scheduler logu` and did not show the
  log text area.

Changed:
- `core/scheduler/scheduler.py` now enables scheduler file logging before a
  manual-run worker executes in the FastAPI process, so `JOB MANUAL ...`
  records are written to `core/scheduler/logs/scheduler.log`.
- `services/api/routes/scheduler_health.py` supports optional `since` filtering
  for `/health/scheduler/log`.
- `moduly/apps/dashboard/api_client.py` can pass the `since` query parameter.
- `moduly/apps/dashboard/pages/16_scheduler_health.py` reads manual-run logs
  from the request time and always renders the manual-run log text area, even
  while waiting for the first record.
- Added regression coverage in `tests/test_scheduler.py` and
  `tests/test_scheduler_metrics.py`.

Verified:
- `.venv\Scripts\python.exe -m pytest tests\test_dashboard_scheduler_log_view.py
  tests\test_scheduler_metrics.py tests\test_scheduler.py -q --tb=short`
  passed 64 tests.
- `.venv-production\Scripts\python.exe -m py_compile` passed for the changed
  scheduler, scheduler-health route, dashboard API client, Scheduler Health
  page, scheduler log-view helper, and related tests.
- `.venv-production\Scripts\python.exe -c "import services.api.main; print('ok')"`
  passed.
- `git diff --check` reported no whitespace errors, only existing LF-to-CRLF
  warnings.

Not verified:
- Authenticated browser click-through was not repeated after this fix.
- The running production FastAPI/Streamlit processes have not been restarted
  yet, so the fix is not active in the currently running runtime until the next
  supported restart/reload.

Follow-up:
- After the next supported runtime restart, verify the panel with a low-risk
  manual target and confirm `JOB MANUAL START` plus a completion record appears
  in the text area.

### 2026-06-17 10:27 CEST - Pre-restart handoff

Reason for restart:
- The user requested saving the current state and restarting the workstation.
- Activate the Scheduler Health manual-run log fix in the running FastAPI and
  Streamlit runtime.

Current task/conversation state:
- Completed: diagnosed the Scheduler Health manual-run progress panel staying
  on `Cekam na prvni zaznam rucniho behu v scheduler logu`.
- Completed: fixed manual-run workers so they enable scheduler file logging in
  the FastAPI process before executing a manual job.
- Completed: added optional `since` filtering to `/health/scheduler/log`,
  dashboard API client support for `since`, and UI behavior that always renders
  the manual-run log text area.
- Completed: added targeted regression tests for manual-run file logging and
  timestamp-filtered scheduler log reads.
- Pending after restart: verify `Sprava / Health scheduleru` in an
  authenticated browser session with a low-risk manual target and confirm
  `JOB MANUAL START` plus a completion record appears in the text area.
- Pending after restart: review/commit or explicitly approve the dirty working
  tree before creating the first production code-integrity baseline.
- Pending after restart: dependency vulnerability scanning remains open for
  P2.15.
- First action after restart: read `AGENTS.md`, `DECISIONS.md`,
  `SESSION_NOTES.md`, then run `git status --short --untracked-files=all`.

Working tree and deployment:
- Current time captured before restart: 2026-06-17 10:27:11 CEST.
- Branch: `master`.
- `HEAD`: `5928652359e82dbd5a309ec33a4dff353898551f`.
- No git commit was created for this restart handoff.
- `git status --short --untracked-files=all` before restart:
  - `M AGENTS.md`
  - `M DASHBOARD_SECURITY_CHECKLIST.md`
  - `M DECISIONS.md`
  - `M SESSION_NOTES.md`
  - `M core/scheduler/job_schedule.py`
  - `M core/scheduler/scheduler.py`
  - `M data/smartfuelpass/session_cookies.json`
  - `M moduly/apps/dashboard/api_client.py`
  - `M moduly/apps/dashboard/pages/16_scheduler_health.py`
  - `M moduly/apps/dashboard/scheduler_log_view.py`
  - `M moduly/mereni/elektromery/SOFTLINK/SOFTLINK_data_z_dotazu.py`
  - `M services/api/routes/scheduler_health.py`
  - `M tests/test_dashboard_scheduler_log_view.py`
  - `M tests/test_scheduler.py`
  - `M tests/test_scheduler_metrics.py`
  - `?? scripts/code_integrity_scan.py`
  - `?? scripts/register_code_integrity_scan_task.ps1`
  - `?? scripts/run_code_integrity_scan.ps1`
  - `?? tests/test_code_integrity_scan.py`
- Tracked root `Caddyfile` SHA-256 before restart:
  `3387659A473097A43B76B7951D833463F77F7C0AC559975271EA3F48B59D1802`.
- Runtime `C:\Program Files\Caddy\Caddyfile` SHA-256 before restart:
  `3387659A473097A43B76B7951D833463F77F7C0AC559975271EA3F48B59D1802`.
- Caddy runtime configuration validation reported `Valid configuration`.
- Existing runtime process/listener state before restart:
  - Caddy owned TCP `:80` and `:443`, PID `10392`.
  - Caddy admin listened on `127.0.0.1:2019`, PID `10392`.
  - FastAPI listened on `127.0.0.1:8000`, PID `9848`.
  - Streamlit listened on `127.0.0.1:8001`, PID `10852`.
  - Tailscale owned expected interface-specific `443` listeners on
    `100.66.79.74` and `fd7a:115c:a1e0::e38:4f4b`.
  - No listeners were present on temporary ports `8010` or `8011`.
- Runtime health before restart:
  - FastAPI `/health/live`: HTTP 200 on `127.0.0.1:8000`.
  - FastAPI `/health/ready`: HTTP 200 on `127.0.0.1:8000`.
  - Streamlit `/_stcore/health`: HTTP 200 on `127.0.0.1:8001`.
  - Caddy admin `/config/`: HTTP 200 on `127.0.0.1:2019`.
- Loopback Caddy checks using host `monitoring.armexholding.cz` returned HTTP
  308 for HTTP root, HTTP 200 for HTTPS dashboard, HTTP 401 for protected map
  catalog without bearer token, HTTP 401 for map image without cookie, HTTP
  401 for session refresh without bearer token, and HTTP 200 for public
  `users-exist`.
- Production environment before restart:
  - `.venv-production\Scripts\python.exe -m pip check` reported no broken
    requirements.
  - `scripts/verify_production_environment.py` reported that the production
    Python environment matches `requirements-production.lock.txt`.
- Scheduler metrics before restart:
  - `scheduler_running=True`; heartbeat at `2026-06-17T10:24:08.448402`.
  - `quarter_hour_job`: last success at `2026-06-17T10:16:08.598185`; next
    run `2026-06-17T10:35:05+02:00`; zero failures in 24 hours.
  - `hourly_job`: last success at `2026-06-17T10:02:19.877368`; next run
    `2026-06-17T11:02:05+02:00`.
  - `daily_job`: last success at `2026-06-17T00:20:56.302058`.
  - `sync_charge_sessions_to_db`: last success at
    `2026-06-17T00:20:55.909289`.
  - `SOFTLINK_save_to_database_all`: last success at
    `2026-06-17T00:15:15.207851`.
- Verification before restart:
  - `.venv\Scripts\python.exe -m pytest tests\test_dashboard_scheduler_log_view.py
    tests\test_scheduler_metrics.py tests\test_scheduler.py -q --tb=short`
    passed 64 tests after the manual-run log fix.
  - `.venv-production\Scripts\python.exe -m py_compile` passed for the
    changed scheduler, scheduler-health route, dashboard API client, Scheduler
    Health page, scheduler log-view helper, and related tests.
  - `.venv-production\Scripts\python.exe -c "import services.api.main; print('ok')"`
    passed.
  - `git diff --check` reported no whitespace errors, only existing
    LF-to-CRLF warnings.
- Runtime activation state before restart:
  - The currently running FastAPI and Streamlit processes were started before
    the manual-run log fix and do not yet include it.
  - The restart is expected to load the updated
    `core/scheduler/scheduler.py`, `services/api/routes/scheduler_health.py`,
    `moduly/apps/dashboard/api_client.py`, and
    `moduly/apps/dashboard/pages/16_scheduler_health.py`.

Sensitive/runtime artifacts:
- Do not print, change, delete, revert, stage, or commit
  `data/smartfuelpass/session_cookies.json` without explicit user approval.
  It remains a tracked sensitive runtime/session artifact.
- Do not print, change, delete, or commit the ignored local `.env`,
  `API_TOKEN_SECRET`, email credentials, dashboard credentials, cookies,
  bearer tokens, authentication audit records, operational recipient
  addresses, raw SQLite reason values, admin email hash-cache values, or
  ProgramData security manifests/logs.
- Do not create a production code-integrity baseline from a dirty working tree
  unless the user explicitly approves that exact state as the new checkpoint.

Expected processes and listeners after restart:
- Windows Task Scheduler runs `API_dashboard_caddy` at system startup and the
  latest run result becomes `0`.
- One rotating-log wrapper owns one non-reload Uvicorn child on
  `127.0.0.1:8000`.
- One rotating-log wrapper owns one Streamlit child on `127.0.0.1:8001`.
- One scheduler runtime runs `main.py`, holds the `scheduler_process` lock,
  and updates `core/scheduler/logs/scheduler_metrics.json`.
- One Caddy runtime owns TCP `80`/`443` and admin `127.0.0.1:2019`.
- Tailscale interface-specific `443` listeners may remain in addition.
- No listener should remain on temporary ports `8010` or `8011`.

Expected application state after restart:
- FastAPI `/health/live` and `/health/ready`: HTTP 200 while PostgreSQL
  remains available.
- Streamlit `/_stcore/health` and Caddy admin endpoint: HTTP 200.
- HTTP hostname route: HTTP 308 to HTTPS.
- HTTPS dashboard: HTTP 200.
- Protected API, map image without cookie, and session refresh without bearer:
  HTTP 401.
- Public `users-exist`: HTTP 200.
- FastAPI docs remain disabled by default: `/docs`, `/redoc`, and
  `/openapi.json` return HTTP 404 unless `API_ENABLE_DOCS=true` is explicitly
  set.
- Scheduler Health manual-run registry includes `sync_charge_sessions_to_db`
  with label `Zapis SmartFuelPass relaci do databaze`, plus distinct
  SmartFuelPass weekly report labels.
- Scheduler Health manual-run UI opens and preserves a progress/log panel for
  the selected job or internal step. The log text area should appear even
  before the first matching log record.
- A manual run should write `JOB MANUAL START` and one of
  `JOB MANUAL SUCCESS`, `JOB MANUAL ERROR`, or `JOB MANUAL SKIPPED` to
  `core/scheduler/logs/scheduler.log`; the dashboard panel should display
  those records.
- Code integrity scanner scripts remain present in the working tree, but no
  production baseline or scheduled task is active unless explicitly created
  after restart.

Required post-restart checks:
- Confirm boot time, scheduled-task last run/result/settings, process tree,
  listeners, and no temporary ports `8010`/`8011`.
- Confirm `.venv-production` exact-lock verification and `pip check`.
- Confirm API live/ready, Streamlit health, and Caddy admin health.
- Confirm tracked/runtime Caddyfile hash equality and Caddy validation.
- Confirm HTTP redirect, HTTPS dashboard, protected API, map image, session
  refresh, disabled docs, and public `users-exist` status codes.
- Confirm scheduler process lock, heartbeat age, latest/next
  `quarter_hour_job`, and at least one completed post-restart scheduler
  heartbeat.
- Confirm FastAPI scheduler health/manual-run registry includes
  `sync_charge_sessions_to_db`, `smartfuelpass_weekly_report_job`, and
  `send_charge_sessions_report_email` with expected labels and locks.
- Verify the authenticated Streamlit `Sprava / Health scheduleru` page with a
  low-risk manual target. Confirm exactly one progress panel remains open,
  the log text area renders, and the log contains `JOB MANUAL START` plus a
  completion record.
- Run `.venv\Scripts\python.exe -m pytest tests\test_dashboard_scheduler_log_view.py
  tests\test_scheduler_metrics.py tests\test_scheduler.py -q --tb=short`.
- Compile changed scheduler, scheduler-health route, dashboard API client,
  Scheduler Health page, scheduler log-view helper, and related tests through
  `.venv-production`.
- Run the code-integrity baseline command and confirm it still refuses dirty
  scanned files until the current state is reviewed/approved.
- Run `git diff --check` and finish with
  `git status --short --untracked-files=all`.
- Append a dated post-restart verification entry with deviations and accepted
  gaps.

Known risks or accepted gaps:
- `data/smartfuelpass/session_cookies.json` is still a tracked sensitive
  runtime/session artifact by explicit current decision.
- Current changes are uncommitted and depend on the working tree being
  preserved across restart.
- The code integrity scan is a local drift detector, not tamper-proof host
  intrusion detection.
- Dependency vulnerability scanning remains open in P2.15.
- True external public reachability from outside the server/LAN remains a
  separate check. Earlier local same-server public-IP access timed out while
  loopback Caddy hostname routing worked.
- A database or network outage during restart can make API readiness return
  HTTP 503 and cause scheduled database jobs to skip until connectivity
  recovers.
- The current scheduled-task account remains broader than least privilege.
- The launcher does not independently restart a child that fails after
  startup.

## 2026-06-18 13:23 +02:00 - Current Restart Handoff Before SmartFuelPass/P2.17 Activation

Reason for restart:
- User requested saving state and restarting the workstation.
- Restart is intended to reload FastAPI, Streamlit, scheduler, and Caddy from
  the normal Windows startup task after the SmartFuelPass and security
  hardening work.

Current conversation/task state:
- P2.16 secret hygiene is partially complete. SmartFuelPass reusable session
  JSON persistence was retired and the two session JSON files were removed
  from the Git index. Other tracked runtime/private artifacts remain open.
- User chose SmartFuelPass password login only, without saving JSON session
  files.
- P2.17 external security verification was started, not completed. Loopback
  hostname checks passed for several HTTPS/auth/header controls, but a true
  external-network test outside the server/LAN remains required.
- Runtime Caddy deployment of the tracked P2.17 proxy fixes is still pending
  because `scripts\deploy_caddy_runtime.ps1` requires an elevated
  administrator PowerShell session.

Completed work in the current state:
- SmartFuelPass service no longer reads or writes
  `data/smartfuelpass/session_cookies.json` or
  `data/smartfuelpass/auto_login_session.json`.
- SmartFuelPass reporting snapshots and charge-session imports use a fresh
  Playwright context and `SMARTFUELPASS_EMAIL` /
  `SMARTFUELPASS_PASSWORD` login for each portal run.
- Existing SmartFuelPass `cookie_path` parameters remain compatibility no-ops.
- `SMARTFUELPASS_SESSION_COOKIES_PATH` was removed from `.env.example`.
- `data/smartfuelpass/session_cookies.json` and
  `data/smartfuelpass/auto_login_session.json` were removed from the Git
  index with `git rm --cached`; local ignored copies were not read or deleted.
- Tracked `Caddyfile` now disables automatic redirects, uses an explicit HTTP
  redirect block with `-Server`/`-Via`, uses an explicit HTTPS block, and
  returns HTTP 404 for `/docs`, `/redoc`, and `/openapi.json` before the
  Streamlit fallback.
- Documentation and handoff state were updated in
  `SECURITY_SECRET_INVENTORY.md`, `DASHBOARD_SECURITY_CHECKLIST.md`,
  `DECISIONS.md`, `AGENTS.md`, and `SESSION_NOTES.md`.

Changed/uncommitted files before restart:
- Modified: `.env.example`, `.gitignore`, `AGENTS.md`, `Caddyfile`,
  `DASHBOARD_SECURITY_CHECKLIST.md`, `DECISIONS.md`, `SESSION_NOTES.md`,
  `moduly/apps/smartfuelpass/__init__.py`,
  `moduly/apps/smartfuelpass/service.py`,
  `requirements-production.in`, `requirements-production.lock.txt`,
  `scripts/code_integrity_scan.py`,
  `scripts/register_code_integrity_scan_task.ps1`,
  `tests/test_caddy_config.py`, `tests/test_code_integrity_scan.py`,
  `tests/test_smartfuelpass_service.py`.
- Git-index deletions: `data/smartfuelpass/auto_login_session.json`,
  `data/smartfuelpass/session_cookies.json`.
- Untracked new files: `SECURITY_SECRET_INVENTORY.md`,
  `requirements-security.in`, `requirements-security.lock.txt`,
  `scripts/bootstrap_security_toolchain.ps1`,
  `scripts/register_dependency_audit_task.ps1`,
  `scripts/run_dependency_audit.ps1`, `scripts/secret_hygiene_scan.py`,
  `tests/test_dependency_audit_tooling.py`,
  `tests/test_secret_hygiene_scan.py`.

Verification already run:
- `.venv\Scripts\python.exe -m pytest tests\test_smartfuelpass_service.py
  tests\test_smartfuelpass_sync.py tests\test_secret_hygiene_scan.py
  tests\test_code_integrity_scan.py tests\test_dependency_audit_tooling.py
  tests\test_production_runtime.py tests\test_dashboard_security_config.py
  tests\test_caddy_config.py tests\test_api_public_exposure.py -q --tb=short`
  passed 66 tests.
- `C:\Program Files\Caddy\caddy.exe validate --config Caddyfile --adapter caddyfile`
  passed and reported automatic HTTP redirects disabled.
- `.venv\Scripts\python.exe -m py_compile scripts\secret_hygiene_scan.py
  scripts\code_integrity_scan.py moduly\apps\smartfuelpass\service.py
  moduly\apps\smartfuelpass\__init__.py` passed.
- `git diff --check` reported no whitespace errors, only expected LF-to-CRLF
  warnings.
- Redacted secret hygiene scan reported current findings only for tracked
  electric-meter source files, scheduler lock files, and
  `frontend_next/tsconfig.tsbuildinfo`; no current SmartFuelPass session JSON
  findings remained.

Deployment state before restart:
- Running FastAPI, Streamlit, and scheduler processes were started before the
  SmartFuelPass code change and need restart to load it.
- Tracked `Caddyfile` contains P2.17 fixes, but runtime
  `C:\Program Files\Caddy\Caddyfile` was not updated from this non-elevated
  shell. A restart alone is not expected to activate those tracked Caddy proxy
  fixes unless the runtime file has been synchronized separately.
- `MonitoringDependencyAudit` was registered earlier and last ran
  successfully. Code-integrity baseline/scheduled activation remains pending
  until the working tree is reviewed/approved.

Sensitive artifacts and handling rules:
- Do not print, read, delete, revert, or commit raw values from ignored local
  `.env`, dashboard/API tokens, passwords, cookies, authentication audit logs,
  ProgramData security artifacts, or any local leftover SmartFuelPass session
  JSON files.
- Local leftover `data/smartfuelpass/session_cookies.json` and
  `data/smartfuelpass/auto_login_session.json` files may still exist but are
  ignored and must not be inspected. Expire SmartFuelPass portal sessions
  externally if old cookies may still be valid.
- Do not create a production code-integrity baseline from the dirty working
  tree unless the user explicitly approves that exact state.

Expected processes and listeners after restart:
- Windows Task Scheduler runs `API_dashboard_caddy` at system startup and its
  latest run result becomes `0`.
- One rotating-log wrapper owns one non-reload Uvicorn child on
  `127.0.0.1:8000`.
- One rotating-log wrapper owns one Streamlit child on `127.0.0.1:8001`.
- One scheduler runtime runs `main.py`, holds the `scheduler_process` lock,
  and updates `core/scheduler/logs/scheduler_metrics.json`.
- One Caddy runtime owns TCP `80`/`443` and admin `127.0.0.1:2019`.
- No listener should remain on temporary ports `8010` or `8011`.

Expected application state after restart:
- FastAPI `/health/live` and `/health/ready`: HTTP 200 while PostgreSQL is
  available.
- Streamlit `/_stcore/health` and Caddy admin endpoint: HTTP 200.
- HTTPS dashboard: HTTP 200.
- HTTP hostname route: HTTP 308 to HTTPS. After runtime Caddy deployment, the
  redirect response should not include `Server` or `Via`.
- Protected API, map image without cookie, and session refresh without bearer:
  HTTP 401.
- Public `/api/v1/auth/users-exist`: HTTP 200 with minimal boolean payload.
- FastAPI docs remain disabled. After runtime Caddy deployment, public
  `/docs`, `/redoc`, and `/openapi.json` should return HTTP 404 rather than
  the Streamlit shell.
- SmartFuelPass scheduled/manual jobs should use password login only and must
  not create or update SmartFuelPass session JSON files.

Required post-restart checks:
- Confirm boot time, scheduled-task last run/result/settings, process tree,
  listeners, and no temporary ports `8010` or `8011`.
- Confirm `.venv-production` exact-lock verification and `pip check`.
- Confirm API live/ready, Streamlit health, Caddy admin health, and scheduler
  heartbeat.
- Confirm tracked/runtime Caddyfile hash equality. If they differ, run
  `scripts\deploy_caddy_runtime.ps1` from an elevated administrator PowerShell
  session and reload Caddy before rechecking P2.17 proxy findings.
- Validate runtime Caddyfile and verify HTTP redirect, HTTPS dashboard,
  protected API, map image, session refresh, disabled docs, and public
  `users-exist` status codes.
- Confirm no `Server` or `Via` headers on HTTPS responses and, after runtime
  Caddy deployment, on HTTP redirect responses.
- Run SmartFuelPass targeted tests again:
  `.venv\Scripts\python.exe -m pytest tests\test_smartfuelpass_service.py
  tests\test_smartfuelpass_sync.py -q --tb=short`.
- Run security/tooling tests as needed:
  `.venv\Scripts\python.exe -m pytest tests\test_secret_hygiene_scan.py
  tests\test_code_integrity_scan.py tests\test_dependency_audit_tooling.py
  tests\test_caddy_config.py tests\test_api_public_exposure.py -q --tb=short`.
- Run `scripts\secret_hygiene_scan.py` and confirm no current SmartFuelPass
  session JSON findings.
- Run `git diff --check` and finish with
  `git status --short --untracked-files=all`.
- Append a dated post-restart verification entry with deviations and accepted
  gaps.

Known risks or accepted gaps:
- True P2.17 external verification from a network outside the server and
  corporate LAN is still open.
- Login throttling, session expiry, logout, token revocation, horizontal and
  vertical authorization boundaries, and XSS/CSRF/injection/path traversal
  checks are not fully completed for P2.17.
- Runtime Caddy proxy fixes are not active until the runtime Caddyfile is
  synchronized and Caddy is reloaded.
- The current changes are uncommitted and depend on the working tree being
  preserved across restart.
- The current scheduled-task account remains broader than least privilege.
- The launcher does not independently restart a child process that fails after
  startup.

## 2026-06-25 06:52 +02:00 - Current restart pointer

- Full current pre-restart handoff for the map photo iframe fix is recorded above under `2026-06-25 06:52 +02:00 - Current pre-restart handoff after map photo iframe fix`.
- First action after restart: read `AGENTS.md`, `DECISIONS.md`, and `SESSION_NOTES.md`, then run `git status --short --untracked-files=all`.
- Change-specific post-restart check: open `https://monitoring.armexholding.cz`, go to `Mapove podklady / Mapa`, click a Vodomery object with a photo, and confirm `/api/v1/map/images` loads the popup photo without printing cookies or tokens.

### 2026-06-25

Scope:
- Continued diagnosis of `Mapove podklady / Mapa` popup photos still showing
  `Fotku se nepodarilo nacist.`
- Kept the main bearer token out of map iframe JavaScript.

Changed:
- Added dedicated HttpOnly `__Secure-monitoring_map_image_session` cookie for
  `/api/v1/map/images` with `SameSite=None`.
- Updated the map image route to accept either the main dashboard session
  cookie or the dedicated map image cookie.
- Updated Leaflet HTML generation so map image requests can use an absolute
  endpoint URL derived from the current Streamlit request origin.
- Updated auth, map route, map HTML, map page, and authorization regression
  tests.
- Added DEC-046 and updated AGENTS map-photo notes.

Verified:
- `.venv\Scripts\python.exe -m py_compile app\dashboard_session.py
  services\api\core\dependencies.py services\api\routes\auth.py
  services\api\routes\map.py moduly\apps\dashboard\map_shared.py
  moduly\apps\dashboard\pages\36_mapove_podklady.py`
- `.venv\Scripts\python.exe -m pytest tests\test_auth_routes.py
  tests\test_map_routes.py tests\test_dashboard_map_shared.py
  tests\test_dashboard_map_page_layout.py
  tests\test_api_authorization_regression.py -q --tb=short`
  passed 201 tests.
- `.venv\Scripts\python.exe -m pytest tests\test_map_routes.py
  tests\test_map_layers_service.py tests\test_device_map_service.py
  tests\test_dashboard_map_shared.py tests\test_dashboard_map_page_layout.py
  tests\test_dashboard_navigation_config.py -q --tb=short` passed 79 tests.

Not verified:
- Live authenticated browser click on a real Vodomery map photo was not tested
  in this session.
- Running production FastAPI/Streamlit processes may need restart or reload to
  pick up the new cookie and iframe HTML changes.

Follow-up:
- After runtime reload, open `https://monitoring.armexholding.cz`, go to
  `Mapove podklady / Mapa`, click a Vodomery object with a photo, and confirm
  `/api/v1/map/images` returns the image without printing cookie or token
  values.

### 2026-06-25 07:16 +02:00 - Pre-restart handoff after dedicated map image cookie fix

Reason for restart:
- User requested saving the conversation state before restarting the Windows
  workstation.
- Restart is expected to reload FastAPI, Streamlit, scheduler, and Caddy from
  the normal startup task so the map-photo cookie and iframe URL fixes can
  become active in the running dashboard.

Current task/conversation state:
- Completed: diagnosed that `Mapove podklady / Mapa` popup photos still showed
  `Fotku se nepodarilo nacist.` after the prior iframe `credentials: "include"`
  change because iframe fetches may not receive the main `SameSite=Lax`
  dashboard session cookie.
- Completed: added dedicated HttpOnly
  `__Secure-monitoring_map_image_session` cookie scoped to
  `/api/v1/map/images` with `SameSite=None`.
- Completed: updated `/api/v1/map/images` to authenticate through either the
  main dashboard session cookie or the dedicated map image cookie.
- Completed: updated Leaflet iframe HTML generation to accept an image endpoint
  URL and the Streamlit map page to derive that URL from the current dashboard
  request origin.
- Completed: kept the main API bearer token out of map iframe JavaScript.
- Pending: restart/reload runtime processes and verify a real authenticated
  Vodomery photo popup in the browser.
- First action after restart: read `AGENTS.md`, `DECISIONS.md`, and
  `SESSION_NOTES.md`; run `git status --short --untracked-files=all`; then
  verify runtime health and the real map photo flow.

Working tree and deployment:
- Current time captured before restart: `2026-06-25 07:16:22 +02:00`.
- Branch: `master`.
- `HEAD`: `69dc532eccbc49db3152e7a1ce0627392375601b`.
- No git commit was created for this handoff.
- `git status --short --untracked-files=all` before restart:
  - `M .env.example`
  - `M .gitignore`
  - `M AGENTS.md`
  - `M Caddyfile`
  - `M DASHBOARD_SECURITY_CHECKLIST.md`
  - `M DECISIONS.md`
  - `M SESSION_NOTES.md`
  - `M app/dashboard_session.py`
  - `D data/smartfuelpass/auto_login_session.json`
  - `D data/smartfuelpass/session_cookies.json`
  - `M moduly/apps/dashboard/map_shared.py`
  - `M moduly/apps/dashboard/pages/36_mapove_podklady.py`
  - `M moduly/apps/smartfuelpass/__init__.py`
  - `M moduly/apps/smartfuelpass/service.py`
  - `M requirements-production.in`
  - `M requirements-production.lock.txt`
  - `M scripts/code_integrity_scan.py`
  - `M scripts/register_code_integrity_scan_task.ps1`
  - `M services/api/core/dependencies.py`
  - `M services/api/routes/auth.py`
  - `M services/api/routes/map.py`
  - `M tests/test_api_authorization_regression.py`
  - `M tests/test_auth_routes.py`
  - `M tests/test_caddy_config.py`
  - `M tests/test_code_integrity_scan.py`
  - `M tests/test_dashboard_map_page_layout.py`
  - `M tests/test_dashboard_map_shared.py`
  - `M tests/test_map_routes.py`
  - `M tests/test_smartfuelpass_service.py`
  - `?? SECURITY_SECRET_INVENTORY.md`
  - `?? requirements-security.in`
  - `?? requirements-security.lock.txt`
  - `?? scripts/bootstrap_security_toolchain.ps1`
  - `?? scripts/register_dependency_audit_task.ps1`
  - `?? scripts/run_dependency_audit.ps1`
  - `?? scripts/secret_hygiene_scan.py`
  - `?? tests/test_dependency_audit_tooling.py`
  - `?? tests/test_secret_hygiene_scan.py`
- Files changed by the latest map-photo fix:
  - `app/dashboard_session.py`
  - `services/api/routes/auth.py`
  - `services/api/core/dependencies.py`
  - `services/api/routes/map.py`
  - `moduly/apps/dashboard/map_shared.py`
  - `moduly/apps/dashboard/pages/36_mapove_podklady.py`
  - `tests/test_auth_routes.py`
  - `tests/test_map_routes.py`
  - `tests/test_dashboard_map_shared.py`
  - `tests/test_dashboard_map_page_layout.py`
  - `tests/test_api_authorization_regression.py`
  - `AGENTS.md`
  - `DECISIONS.md`
  - `SESSION_NOTES.md`
- Runtime deployment state was not checked in this handoff. Existing running
  FastAPI and Streamlit processes may still be using older code until restart.
- Tracked/runtime Caddyfile synchronization was not checked in this handoff.

Verification already run for the latest map-photo fix:
- `.venv\Scripts\python.exe -m py_compile app\dashboard_session.py
  services\api\core\dependencies.py services\api\routes\auth.py
  services\api\routes\map.py moduly\apps\dashboard\map_shared.py
  moduly\apps\dashboard\pages\36_mapove_podklady.py`
- `.venv\Scripts\python.exe -m pytest tests\test_auth_routes.py
  tests\test_map_routes.py tests\test_dashboard_map_shared.py
  tests\test_dashboard_map_page_layout.py
  tests\test_api_authorization_regression.py -q --tb=short`
  passed 201 tests.
- `.venv\Scripts\python.exe -m pytest tests\test_map_routes.py
  tests\test_map_layers_service.py tests\test_device_map_service.py
  tests\test_dashboard_map_shared.py tests\test_dashboard_map_page_layout.py
  tests\test_dashboard_navigation_config.py -q --tb=short` passed 79 tests.
- `.venv\Scripts\python.exe -m pytest tests\test_dashboard_auth_state.py
  tests\test_dashboard_session_security.py -q --tb=short` passed 23 tests.
- `git diff --check` reported no whitespace errors, only expected LF-to-CRLF
  warnings.

Sensitive/runtime artifacts:
- Do not print, read, delete, revert, stage, or commit raw values from ignored
  local `.env`, dashboard/API tokens, passwords, cookies, authentication audit
  logs, ProgramData security artifacts, or any local leftover SmartFuelPass
  session JSON files.
- `data/smartfuelpass/session_cookies.json` and
  `data/smartfuelpass/auto_login_session.json` are shown as Git-index
  deletions from earlier approved SmartFuelPass cleanup work; do not restore,
  inspect, or delete local leftover copies unless explicitly approved.
- Do not create a production code-integrity baseline from the dirty working
  tree unless the user explicitly approves that exact state.
- Browser DevTools may be used after restart only to inspect safe status codes
  and non-sensitive headers for `/api/v1/map/images`; do not print cookie or
  token values.

Expected processes and listeners after restart:
- Windows Task Scheduler runs `API_dashboard_caddy` at system startup and its
  latest run result becomes `0`.
- One rotating-log wrapper owns one non-reload Uvicorn child on
  `127.0.0.1:8000`.
- One rotating-log wrapper owns one Streamlit child on `127.0.0.1:8001`.
- One scheduler runtime runs `main.py`, holds the `scheduler_process` lock,
  and updates `core/scheduler/logs/scheduler_metrics.json`.
- One Caddy runtime owns TCP `80`/`443` and admin `127.0.0.1:2019`.
- No listener should remain on temporary ports `8010` or `8011`.

Expected application state after restart:
- FastAPI `/health/live` and `/health/ready`: HTTP 200 while PostgreSQL is
  available.
- Streamlit `/_stcore/health` and Caddy admin endpoint: HTTP 200.
- HTTP hostname route: HTTP 308 to HTTPS.
- HTTPS dashboard: HTTP 200.
- Protected API without bearer token: HTTP 401 JSON.
- `/api/v1/map/images` without any dashboard cookie: HTTP 401.
- `/api/v1/auth/browser-session` after authenticated Streamlit login sets both
  `__Host-monitoring_dashboard_session` and
  `__Secure-monitoring_map_image_session`; do not print cookie values.
- Generated map iframe HTML keeps `Authorization`, `Bearer`, and
  `mapImageAccessToken` out of JavaScript and uses `/api/v1/map/images` under
  the dashboard origin.
- `Mapove podklady / Mapa` should load a Vodomery popup photo instead of
  displaying `Fotku se nepodarilo nacist.`

Required post-restart checks:
- Confirm boot time, scheduled-task last run/result/settings, process tree,
  listeners, and no temporary ports `8010` or `8011`.
- Confirm `.venv-production` exact-lock verification and `pip check`.
- Confirm API live/ready, Streamlit health, Caddy admin health, and scheduler
  heartbeat.
- Confirm tracked/runtime Caddyfile hash equality and Caddy validation.
- Verify HTTP redirect, HTTPS dashboard, protected API without bearer token,
  map image without cookie, disabled docs, and public `users-exist` status.
- Log in to `https://monitoring.armexholding.cz`; confirm login still persists
  after reload without printing any cookie or token values.
- Open `Mapove podklady / Mapa`, click a Vodomery object with a photo, and
  confirm the popup photo loads and lightbox opens.
- If the photo still fails, inspect only the HTTP status and safe headers for
  `/api/v1/map/images`; likely statuses to distinguish are 401, 403, 404, and
  400. Do not print cookies, bearer tokens, or raw file paths.
- Re-run targeted tests:
  `.venv\Scripts\python.exe -m pytest tests\test_auth_routes.py
  tests\test_map_routes.py tests\test_dashboard_map_shared.py
  tests\test_dashboard_map_page_layout.py
  tests\test_api_authorization_regression.py -q --tb=short`
- Re-run map service tests:
  `.venv\Scripts\python.exe -m pytest tests\test_map_layers_service.py
  tests\test_device_map_service.py tests\test_dashboard_navigation_config.py
  -q --tb=short`
- Run `git diff --check` and finish with
  `git status --short --untracked-files=all`.
- Append a dated post-restart verification entry with deviations and accepted
  gaps.

Known risks or accepted gaps:
- The real authenticated browser photo flow has not yet been verified after
  the dedicated map image cookie fix.
- Current changes are uncommitted and depend on the working tree being
  preserved across restart.
- Runtime Caddy deployment state was not checked in this handoff.
- True external verification from a network outside the server and corporate
  LAN remains a separate task.
- Existing unrelated SmartFuelPass/security hardening changes are still
  present in the dirty working tree.
- The current scheduled-task account remains broader than least privilege.
- The launcher does not independently restart a child process that fails after
  startup.

### 2026-06-26

Scope:
- Extended map-layer conditional styling to support multiple rules.
- Corrected SmartFuelPass weekly report period/detail behavior.
- Switched the SmartFuelPass weekly email/PDF report source from live portal
  scraping to synchronized PostgreSQL rows.

Changed:
- `Sprava / Mapove vrstvy` now stores multiple conditional style rules in
  `style.conditionalStyle.rules`; Leaflet applies the first matching rule and
  keeps the prior single-condition format compatible.
- Map-layer create/update automatically adds all conditional-rule columns to
  `property_columns`.
- SmartFuelPass weekly periods now use the previous completed calendar week
  Monday-Sunday and filter by session end time.
- SmartFuelPass PDF now includes a detailed `Poslední týden` section.
- `send_charge_sessions_report_email` now builds reports from
  `monitoring.smartfuelpass_relace`.
- SmartFuelPass sync now upserts existing `id_relace` rows and persists
  `connector_id`.
- Added DEC-047 and updated AGENTS SmartFuelPass operating context.

Verified:
- `.venv\Scripts\python.exe -m py_compile services\api\services\map_layers.py
  moduly\apps\dashboard\pages\35_mapove_vrstvy.py
  moduly\apps\dashboard\map_shared.py`
- `.venv\Scripts\python.exe -m pytest tests\test_map_routes.py
  tests\test_map_layers_service.py tests\test_device_map_service.py
  tests\test_dashboard_map_shared.py tests\test_dashboard_map_page_layout.py
  tests\test_dashboard_navigation_config.py -q --tb=short` passed 86 tests.
- `.venv\Scripts\python.exe -m pytest tests\test_smartfuelpass_service.py
  tests\test_smartfuelpass_sync.py -q --tb=short` passed 30 tests.
- `.venv\Scripts\python.exe -m pytest tests\test_scheduler.py -q --tb=short
  -k "smartfuelpass or daily_job"` passed 7 tests.
- `.venv\Scripts\python.exe -m py_compile
  moduly\apps\smartfuelpass\service.py moduly\apps\smartfuelpass\sync.py
  moduly\apps\smartfuelpass\database\models.py
  moduly\apps\smartfuelpass\database\db_init.py
  moduly\apps\smartfuelpass\__init__.py core\scheduler\scheduler.py`
- `git diff --check` reported no whitespace errors, only expected
  LF-to-CRLF warnings.

Not verified:
- Live dashboard configuration/rendering of multiple conditional map rules.
- Live SmartFuelPass portal sync, PostgreSQL migration of `connector_id`, or
  real weekly email/PDF delivery.

Decisions/notes:
- `daily_job` remains the SmartFuelPass portal ingestion path after midnight.
- Weekly SmartFuelPass reports read synchronized database rows rather than the
  portal.

### 2026-06-26 12:16 +02:00 - Pre-restart handoff after SmartFuelPass DB-report pipeline

Reason for restart:
- Reload FastAPI, Streamlit, scheduler, and Caddy through the normal startup
  task so current map and SmartFuelPass code changes become active in runtime
  processes.
- Preserve restart context after changing the SmartFuelPass weekly report data
  source and map conditional styling behavior.

Current task/conversation state:
- Completed: map-layer conditional styling supports multiple rules, such as
  coloring `stav = bez_vody`, `stav = tece`, and `stav = stoji` differently.
- Completed: SmartFuelPass weekly report period now means the previous closed
  Monday-Sunday calendar week and uses session end time for period filters.
- Completed: SmartFuelPass weekly PDF includes a `Poslední týden` detail
  section.
- Completed: SmartFuelPass weekly email report now builds from
  `monitoring.smartfuelpass_relace` instead of live portal scraping.
- Completed: SmartFuelPass sync now updates existing `id_relace` rows and
  persists `connector_id`.
- Pending: restart/reload runtime processes and verify the live dashboard map
  and SmartFuelPass database-backed report path.
- First action after restart: read `AGENTS.md`, `DECISIONS.md`, and
  `SESSION_NOTES.md`; run `git status --short --untracked-files=all`; verify
  runtime health, then run the change-specific checks below.

Working tree and deployment:
- Current time captured before restart: `2026-06-26 12:16:50 +02:00`.
- Branch: `master`.
- `HEAD`: `c52270d20c4473d501f474c04d6c3fc2080febf5`.
- No git commit was created for this handoff.
- `git status --short --untracked-files=all` before documentation updates:
  - `M SESSION_NOTES.md`
  - `M moduly/apps/dashboard/map_shared.py`
  - `M moduly/apps/dashboard/pages/35_mapove_vrstvy.py`
  - `M moduly/apps/smartfuelpass/__init__.py`
  - `M moduly/apps/smartfuelpass/database/db_init.py`
  - `M moduly/apps/smartfuelpass/database/models.py`
  - `M moduly/apps/smartfuelpass/service.py`
  - `M moduly/apps/smartfuelpass/sync.py`
  - `M services/api/services/map_layers.py`
  - `M tests/test_dashboard_map_shared.py`
  - `M tests/test_map_layers_service.py`
  - `M tests/test_smartfuelpass_service.py`
  - `M tests/test_smartfuelpass_sync.py`
- Documentation files changed by this handoff:
  - `AGENTS.md`
  - `DECISIONS.md`
  - `SESSION_NOTES.md`
- Runtime deployment state was not checked in this handoff. Existing running
  FastAPI, Streamlit, and scheduler processes may still be using older code
  until restart.
- Tracked/runtime Caddyfile synchronization was not changed by this work.

Verification already run:
- `.venv\Scripts\python.exe -m py_compile services\api\services\map_layers.py
  moduly\apps\dashboard\pages\35_mapove_vrstvy.py
  moduly\apps\dashboard\map_shared.py`
- `.venv\Scripts\python.exe -m pytest tests\test_map_routes.py
  tests\test_map_layers_service.py tests\test_device_map_service.py
  tests\test_dashboard_map_shared.py tests\test_dashboard_map_page_layout.py
  tests\test_dashboard_navigation_config.py -q --tb=short` passed 86 tests.
- `.venv\Scripts\python.exe -m pytest tests\test_smartfuelpass_service.py
  tests\test_smartfuelpass_sync.py -q --tb=short` passed 30 tests.
- `.venv\Scripts\python.exe -m pytest tests\test_scheduler.py -q --tb=short
  -k "smartfuelpass or daily_job"` passed 7 tests.
- `.venv\Scripts\python.exe -m py_compile
  moduly\apps\smartfuelpass\service.py moduly\apps\smartfuelpass\sync.py
  moduly\apps\smartfuelpass\database\models.py
  moduly\apps\smartfuelpass\database\db_init.py
  moduly\apps\smartfuelpass\__init__.py core\scheduler\scheduler.py`
- `git diff --check` reported no whitespace errors, only expected
  LF-to-CRLF warnings.

Sensitive/runtime artifacts:
- Do not print, read, delete, revert, stage, or commit raw values from ignored
  local `.env`, dashboard/API tokens, passwords, cookies, authentication audit
  logs, ProgramData security artifacts, or local leftover SmartFuelPass session
  JSON files.
- Do not print raw SmartFuelPass portal data, raw device photo filesystem paths,
  cookies, bearer tokens, or dashboard session cookie values while verifying.
- Do not create a production code-integrity baseline from this dirty working
  tree unless the user explicitly approves that exact state.

Expected processes and listeners after restart:
- Windows Task Scheduler runs `API_dashboard_caddy` at system startup and its
  latest run result becomes `0`.
- One rotating-log wrapper owns one non-reload Uvicorn child on
  `127.0.0.1:8000`.
- One rotating-log wrapper owns one Streamlit child on `127.0.0.1:8001`.
- One scheduler runtime runs `main.py`, holds the `scheduler_process` lock,
  and updates `core/scheduler/logs/scheduler_metrics.json`.
- One Caddy runtime owns TCP `80`/`443` and admin `127.0.0.1:2019`.
- No listener should remain on temporary ports `8010` or `8011`.

Expected application state after restart:
- FastAPI `/health/live` and `/health/ready`: HTTP 200 while PostgreSQL is
  available.
- Streamlit `/_stcore/health` and Caddy admin endpoint: HTTP 200.
- HTTP hostname route: HTTP 308 to HTTPS.
- HTTPS dashboard: HTTP 200.
- Protected API without bearer token: HTTP 401 JSON.
- Scheduler manual spec for `sync_charge_sessions_to_db` remains available and
  tied to the `daily_job` lock.
- `daily_job` should continue to run after midnight and sync SmartFuelPass
  portal rows into PostgreSQL.
- The next SmartFuelPass sync or weekly report call should run
  `ensure_smartfuelpass_tables()` and add `monitoring.smartfuelpass_relace.connector_id`
  if it does not already exist.
- SmartFuelPass weekly report email generation should read from
  `monitoring.smartfuelpass_relace`, not from the portal.
- `Mapove vrstvy` conditional styles should accept multiple rules and
  `Mapove podklady / Mapa` should render the first matching style rule.

Required post-restart checks:
- Confirm boot time, scheduled-task last run/result/settings, process tree,
  listeners, and no temporary ports `8010` or `8011`.
- Confirm API live/ready, Streamlit health, Caddy admin health, scheduler
  heartbeat, and current runtime log freshness.
- Confirm `.venv-production` exact-lock verification and `pip check` if
  reviewing production runtime startup.
- Log in to `https://monitoring.armexholding.cz` without printing cookie or
  token values.
- In `Sprava / Mapove vrstvy`, verify a layer can save multiple conditional
  rules for a status column and that all conditional columns are present in
  `property_columns`.
- In `Mapove podklady / Mapa`, verify the configured status values render with
  distinct styles.
- Verify SmartFuelPass DB schema contains `connector_id` after
  `ensure_smartfuelpass_tables()` has run.
- Run or wait for the next `daily_job` SmartFuelPass sync; verify only safe
  counts/timestamps and that existing rows can be updated by `id_relace`.
- Generate a SmartFuelPass report through the database-backed path without
  sending real email unless explicitly approved; verify period boundaries and
  counts against safe aggregate SQL only.
- Re-run targeted tests:
  `.venv\Scripts\python.exe -m pytest tests\test_smartfuelpass_service.py
  tests\test_smartfuelpass_sync.py tests\test_scheduler.py -q --tb=short
  -k "smartfuelpass or daily_job"`
- Re-run map tests:
  `.venv\Scripts\python.exe -m pytest tests\test_map_routes.py
  tests\test_map_layers_service.py tests\test_device_map_service.py
  tests\test_dashboard_map_shared.py tests\test_dashboard_map_page_layout.py
  tests\test_dashboard_navigation_config.py -q --tb=short`
- Run `git diff --check` and finish with
  `git status --short --untracked-files=all`.
- Append a dated post-restart verification entry with deviations and accepted
  gaps.

Known risks or accepted gaps:
- Live browser rendering of multiple conditional map styles has not been
  verified.
- Live SmartFuelPass portal sync, DB migration of `connector_id`, and real
  weekly email delivery have not been verified.
- Current changes are uncommitted and depend on the working tree being
  preserved across restart.
- Runtime Caddy deployment state was not checked in this handoff.
- The current scheduled-task account remains broader than least privilege.
- The launcher does not independently restart a child process that fails after
  startup.

### 2026-06-26 13:41 +02:00 - Post-restart verification after SmartFuelPass DB-report pipeline

Scope:
- Performed post-restart runtime and change-specific checks after the
  2026-06-26 12:16 +02:00 restart handoff.
- Kept checks to safe statuses, metadata, and aggregates; no cookies, tokens,
  portal rows, device photo paths, or email contents were printed.

Verified:
- Windows last boot time: `2026-06-26 12:22:26 +02:00`.
- Startup scheduled task `API_dashboard_caddy` last ran at
  `2026-06-26 12:22:36 +02:00` with result `0`.
- Expected listeners are present: FastAPI `127.0.0.1:8000`, Streamlit
  `127.0.0.1:8001`, Caddy `80`, `443`, and Caddy admin `127.0.0.1:2019`.
- No listener was present on temporary ports `8010` or `8011`.
- Additional `443` listeners on Tailscale addresses are owned by
  `tailscaled.exe`, separate from the public Caddy listener.
- API `/health/live` and `/health/ready`, Streamlit `/_stcore/health`, and
  Caddy admin `/config/` returned HTTP 200.
- Direct public requests to `monitoring.armexholding.cz` from this workstation
  timed out, but local Caddy hostname routing via `curl --resolve` verified:
  dashboard HTTP 200, `users-exist` HTTP 200, protected API without bearer
  HTTP 401 JSON, map image without cookie HTTP 401 JSON, `/docs`, `/redoc`,
  and `/openapi.json` HTTP 404, and HTTP-to-HTTPS redirect HTTP 308.
- Public response security headers were present on the local Caddy hostname
  path; `Server` and `Via` headers were absent.
- Tracked root `Caddyfile` and runtime
  `C:\Program Files\Caddy\Caddyfile` have matching SHA-256 hashes, and
  `caddy validate --config "C:\Program Files\Caddy\Caddyfile"` reported a
  valid configuration.
- `.venv-production` passed `pip check` and
  `scripts/verify_production_environment.py`.
- Scheduler metrics show `scheduler_running=true`, heartbeat
  `2026-06-26T13:32:42.157787`, and `quarter_hour_job` success at
  `2026-06-26T13:35:09.270859` with next run
  `2026-06-26T13:47:05+02:00`.
- Scheduler metrics show `daily_job`, `smartfuelpass_weekly_report_job`,
  `sync_charge_sessions_to_db`, and `send_charge_sessions_report_email` with
  zero failures in the last 24 hours.
- `monitoring.smartfuelpass_relace.connector_id` exists.
- Safe aggregate SQL showed `monitoring.smartfuelpass_relace` has 21 rows,
  0 rows with non-empty `connector_id`, and `ended_at` range
  `2026-02-11 17:25:00` through `2026-06-23 14:22:00`.
- Database-backed SmartFuelPass report builder ran without sending email or
  rendering/sending a real PDF. It produced `last_week` period
  `2026-06-15T00:00:00` through `2026-06-21T23:59:59.999999`, with safe
  aggregate counts only: `source_rows=21`, `valid_rows=21`,
  `invalid_rows=0`, `last_week_sessions=1`, `previous_month_sessions=8`,
  `total_sessions=21`.
- Targeted SmartFuelPass/scheduler tests passed:
  `.venv\Scripts\python.exe -m pytest tests\test_smartfuelpass_service.py
  tests\test_smartfuelpass_sync.py tests\test_scheduler.py -q --tb=short
  -k "smartfuelpass or daily_job"` reported 37 passed and 45 deselected.
- Targeted map tests passed:
  `.venv\Scripts\python.exe -m pytest tests\test_map_routes.py
  tests\test_map_layers_service.py tests\test_device_map_service.py
  tests\test_dashboard_map_shared.py tests\test_dashboard_map_page_layout.py
  tests\test_dashboard_navigation_config.py -q --tb=short` reported
  86 passed.
- `git diff --check` reported no whitespace errors, only expected
  LF-to-CRLF warnings.

Not verified:
- Authenticated browser login, session reload persistence, `Sprava / Mapove
  vrstvy` multi-rule save flow, and `Mapove podklady / Mapa` live conditional
  style rendering were not verified in the browser during this shell-only
  check.
- Direct public hostname reachability from this workstation remained timed out;
  Caddy routing was verified locally with SNI/Host routing through loopback.
- A new live SmartFuelPass portal sync after the restart was not run. The next
  scheduled `daily_job` should verify updated `connector_id` ingestion after
  midnight; current synced rows have the column but no non-empty connector
  values.
- Real SmartFuelPass weekly email/PDF delivery was not performed.

Working tree:
- `git status --short --untracked-files=all` before this post-restart note
  still showed the expected modified files from the SmartFuelPass/map work:
  `AGENTS.md`, `DECISIONS.md`, `SESSION_NOTES.md`,
  `moduly/apps/dashboard/map_shared.py`,
  `moduly/apps/dashboard/pages/35_mapove_vrstvy.py`,
  SmartFuelPass service/sync/model/bootstrap files,
  `services/api/services/map_layers.py`, and related tests.

Follow-up:
- Verify authenticated dashboard map conditional styling in a real browser.
- Let the next `daily_job` run, then check safe SmartFuelPass aggregate counts
  for non-empty `connector_id` values and updated `id_relace` upserts.

### 2026-07-07

Scope:
- Began incremental implementation of the admin-only `Health systemu` dashboard
  page for post-restart and operational checks.
- Agreed to proceed one check at a time: describe the item, data source,
  display, and safety limits; implement it; verify it; then move to the next
  item.

Planned order:
- Runtime startup health: Windows boot time, startup scheduled task metadata,
  expected listeners on `80`, `443`, `127.0.0.1:2019`, `127.0.0.1:8000`, and
  `127.0.0.1:8001`, plus absence of temporary listeners on `8010` and `8011`.
- Proxy/routing health: local Caddy hostname routing, protected API statuses,
  documentation aliases, HTTP redirect, and reviewed public headers.
- Scheduler health: existing scheduler metrics, heartbeat freshness, key job
  statuses, and log freshness.
- Production environment health: `.venv-production` lock verification and
  `pip check` result through a safe backend probe.
- Database and SmartFuelPass health: schema metadata and safe aggregate counts,
  without raw portal rows or sensitive values.

Safety notes:
- Health checks must run through authenticated admin FastAPI endpoints, not
  directly in browser JavaScript or Streamlit shell commands.
- Responses must contain safe statuses, timestamps, listener summaries, and
  aggregates only. Do not expose secrets, environment values, bearer tokens,
  cookie values, raw process command lines, raw portal rows, raw device photo
  paths, or credential file contents.

Changed:
- Added admin API route `GET /health/system/runtime`.
- Added sanitized system health service for Windows boot time, startup task
  result, expected listeners, and temporary listener absence.
- Added dashboard API client helper `get_system_runtime_health`.
- Connected the first `Runtime po restartu` block on `Health systemu`.
- Added tests for runtime health status construction, route delegation,
  dashboard navigation, and authorization inventory.
- Fixed Streamlit dashboard entrypoint module reload handling so a module that
  disappeared from `sys.modules` during hot-reload is imported again instead
  of raising `ImportError`.
- Updated `Health systemu` runtime block to handle HTTP 404 from
  `/health/system/runtime` as a controlled "API runtime not reloaded yet"
  warning instead of showing a traceback.

Verified:
- `.venv\Scripts\python.exe -m py_compile services\api\services\system_health.py
  services\api\routes\system_health.py services\api\schemas\admin.py
  services\api\main.py moduly\apps\dashboard\api_client.py
  moduly\apps\dashboard\pages\37_system_health.py
  moduly\apps\dashboard\navigation_config.py`
- `.venv\Scripts\python.exe -m pytest tests\test_system_health.py
  tests\test_api_authorization_regression.py
  tests\test_dashboard_navigation_config.py -q --tb=short` reported
  192 passed.
- Local runtime collector returned `status=ok` on 2026-07-07 07:27 +02:00:
  boot time available, startup task last result `0`, expected listeners present
  on `80`, `443`, `127.0.0.1:2019`, `127.0.0.1:8000`, and
  `127.0.0.1:8001`, and no listeners on `8010` or `8011`.
- `.venv\Scripts\python.exe -m py_compile moduly\apps\dashboard\login.py`
- `.venv\Scripts\python.exe -m pytest tests\test_dashboard_responsive.py -q
  --tb=short` reported 4 passed.
- `.venv\Scripts\python.exe -m py_compile
  moduly\apps\dashboard\pages\37_system_health.py`
- `.venv\Scripts\python.exe -m pytest tests\test_system_health.py
  tests\test_dashboard_navigation_config.py -q --tb=short` reported
  26 passed.

Not verified:
- Authenticated browser rendering of the new `Health systemu` page.
- Live Streamlit hot-reload recovery in an authenticated browser session.
- Runtime health data through the dashboard before FastAPI has been restarted
  or reloaded with the new `/health/system/runtime` route.

### 2026-07-07 07:40 +02:00 - Pre-restart handoff after Health systemu runtime check

Reason for restart:
- Reload FastAPI, Streamlit, scheduler, and Caddy through the normal startup
  task so the new admin endpoint `GET /health/system/runtime` is registered in
  the running FastAPI process.
- Clear the current dashboard-visible `DashboardApiError: Not Found` state on
  `Health systemu`, which is expected while Streamlit has loaded the new page
  but FastAPI is still running the older route set.

Current task/conversation state:
- Completed: documented the incremental `Health systemu` plan in
  `AGENTS.md`, `DECISIONS.md`, and `SESSION_NOTES.md`.
- Completed: added admin-only `Health systemu` dashboard page in the footer
  navigation after `Health scheduleru`.
- Completed: added `GET /health/system/runtime` and sanitized backend runtime
  probes for Windows boot time, startup scheduled task result, expected
  listeners, and absence of temporary listeners.
- Completed: connected the dashboard `Runtime po restartu` block to the new
  API endpoint.
- Completed: added controlled handling for HTTP 404 from
  `/health/system/runtime`, so a not-yet-reloaded FastAPI runtime shows a
  warning instead of a traceback.
- Completed: fixed Streamlit dashboard entrypoint module reload handling for
  modules missing from `sys.modules` during hot-reload.
- Pending: restart workstation, then verify the running FastAPI process exposes
  `/health/system/runtime` and the `Health systemu` page renders live runtime
  data.
- First action after restart: read `AGENTS.md`, `DECISIONS.md`, and
  `SESSION_NOTES.md`; run `git status --short --untracked-files=all`; verify
  runtime health, then test the `Health systemu` page and endpoint.

Working tree and deployment:
- Current time captured before restart: `2026-07-07 07:40:03 +02:00`.
- Branch: `master`.
- `HEAD`: `c52270d20c4473d501f474c04d6c3fc2080febf5`.
- No git commit was created for this handoff.
- `git status --short --untracked-files=all` before this handoff:
  - `M AGENTS.md`
  - `M DECISIONS.md`
  - `M SESSION_NOTES.md`
  - `M moduly/apps/dashboard/api_client.py`
  - `M moduly/apps/dashboard/login.py`
  - `M moduly/apps/dashboard/map_shared.py`
  - `M moduly/apps/dashboard/navigation_config.py`
  - `M moduly/apps/dashboard/pages/35_mapove_vrstvy.py`
  - `M moduly/apps/smartfuelpass/__init__.py`
  - `M moduly/apps/smartfuelpass/database/db_init.py`
  - `M moduly/apps/smartfuelpass/database/models.py`
  - `M moduly/apps/smartfuelpass/service.py`
  - `M moduly/apps/smartfuelpass/sync.py`
  - `M services/api/main.py`
  - `M services/api/schemas/admin.py`
  - `M services/api/services/map_layers.py`
  - `M tests/test_api_authorization_regression.py`
  - `M tests/test_dashboard_map_shared.py`
  - `M tests/test_dashboard_navigation_config.py`
  - `M tests/test_dashboard_responsive.py`
  - `M tests/test_map_layers_service.py`
  - `M tests/test_smartfuelpass_service.py`
  - `M tests/test_smartfuelpass_sync.py`
  - `?? moduly/apps/dashboard/pages/37_system_health.py`
  - `?? services/api/routes/system_health.py`
  - `?? services/api/services/system_health.py`
  - `?? tests/test_system_health.py`
- Files changed by the latest `Health systemu` work:
  - `AGENTS.md`
  - `DECISIONS.md`
  - `SESSION_NOTES.md`
  - `moduly/apps/dashboard/api_client.py`
  - `moduly/apps/dashboard/login.py`
  - `moduly/apps/dashboard/navigation_config.py`
  - `moduly/apps/dashboard/pages/37_system_health.py`
  - `services/api/main.py`
  - `services/api/routes/system_health.py`
  - `services/api/schemas/admin.py`
  - `services/api/services/system_health.py`
  - `tests/test_api_authorization_regression.py`
  - `tests/test_dashboard_navigation_config.py`
  - `tests/test_dashboard_responsive.py`
  - `tests/test_system_health.py`
- Existing unrelated or earlier in-progress files from map/SmartFuelPass work
  remain modified and must not be reverted during post-restart verification.
- Runtime deployment state: Streamlit can load the new `Health systemu` page
  from the working tree; running FastAPI still returns HTTP 404 for
  `/health/system/runtime` until restart/reload registers the new route.
- Tracked/runtime Caddyfile synchronization was not changed by this work.

Verification already run:
- `.venv\Scripts\python.exe -m py_compile services\api\services\system_health.py
  services\api\routes\system_health.py services\api\schemas\admin.py
  services\api\main.py moduly\apps\dashboard\api_client.py
  moduly\apps\dashboard\pages\37_system_health.py
  moduly\apps\dashboard\navigation_config.py`
- `.venv\Scripts\python.exe -m pytest tests\test_system_health.py
  tests\test_api_authorization_regression.py
  tests\test_dashboard_navigation_config.py -q --tb=short` reported
  192 passed.
- Local runtime collector returned `status=ok` on 2026-07-07 07:27 +02:00:
  boot time available, startup task last result `0`, expected listeners present
  on `80`, `443`, `127.0.0.1:2019`, `127.0.0.1:8000`, and
  `127.0.0.1:8001`, and no listeners on `8010` or `8011`.
- `.venv\Scripts\python.exe -m py_compile moduly\apps\dashboard\login.py`
- `.venv\Scripts\python.exe -m pytest tests\test_dashboard_responsive.py -q
  --tb=short` reported 4 passed.
- `.venv\Scripts\python.exe -m py_compile
  moduly\apps\dashboard\pages\37_system_health.py`
- `.venv\Scripts\python.exe -m pytest tests\test_system_health.py
  tests\test_dashboard_navigation_config.py -q --tb=short` reported
  26 passed.
- `git diff --check` reported no whitespace errors, only expected
  LF-to-CRLF warnings.

Sensitive/runtime artifacts:
- Do not print, read, delete, revert, stage, or commit raw values from ignored
  local `.env`, dashboard/API tokens, passwords, cookies, authentication audit
  logs, ProgramData security artifacts, or local leftover SmartFuelPass session
  JSON files.
- Do not print raw SmartFuelPass portal data, raw device photo filesystem paths,
  process command lines, environment variables, bearer tokens, or dashboard
  session cookie values while verifying.
- Do not create a production code-integrity baseline from this dirty working
  tree unless the user explicitly approves that exact state.

Expected processes and listeners after restart:
- Windows Task Scheduler runs `API_dashboard_caddy` at system startup and its
  latest run result becomes `0`.
- One rotating-log wrapper owns one non-reload Uvicorn child on
  `127.0.0.1:8000`.
- One rotating-log wrapper owns one Streamlit child on `127.0.0.1:8001`.
- One scheduler runtime runs `main.py`, holds the `scheduler_process` lock,
  and updates `core/scheduler/logs/scheduler_metrics.json`.
- One Caddy runtime owns TCP `80`/`443` and admin `127.0.0.1:2019`.
- No listener should remain on temporary ports `8010` or `8011`.

Expected application state after restart:
- FastAPI `/health/live` and `/health/ready`: HTTP 200 while PostgreSQL is
  available.
- Streamlit `/_stcore/health` and Caddy admin endpoint: HTTP 200.
- FastAPI `GET /health/system/runtime` with a valid admin bearer token:
  HTTP 200 and safe JSON with `status`, boot metadata, startup task metadata,
  expected listeners, and temporary listeners.
- FastAPI `GET /health/system/runtime` without bearer token: HTTP 401.
- Non-admin bearer token for `GET /health/system/runtime`: HTTP 403.
- `Health systemu` dashboard page loads without traceback and the
  `Runtime po restartu` block shows live runtime data instead of the
  "API runtime not reloaded yet" warning.
- Runtime block expected values: startup task result `0`, expected listeners
  present on `80`, `443`, `127.0.0.1:2019`, `127.0.0.1:8000`, and
  `127.0.0.1:8001`, and no listeners on `8010` or `8011`.
- HTTP hostname route: HTTP 308 to HTTPS.
- HTTPS dashboard: HTTP 200.
- Protected API without bearer token: HTTP 401 JSON.
- Public `/docs`, `/redoc`, and `/openapi.json`: HTTP 404 at Caddy layer.

Required post-restart checks:
- Confirm boot time, scheduled-task last run/result/settings, process tree,
  listeners, and no temporary ports `8010` or `8011`.
- Confirm API live/ready, Streamlit health, Caddy admin health, scheduler
  heartbeat, and current runtime log freshness.
- Confirm `.venv-production` exact-lock verification and `pip check` if
  reviewing production runtime startup.
- Confirm tracked root `Caddyfile` and runtime
  `C:\Program Files\Caddy\Caddyfile` still have matching SHA-256 hashes, then
  validate runtime Caddy config.
- Verify local Caddy hostname routing with SNI/Host routing if direct public
  hostname requests from the workstation still time out.
- Log in to `https://monitoring.armexholding.cz` without printing cookie or
  token values.
- Open `Health systemu` and confirm the `Runtime po restartu` block displays
  live data and no traceback.
- Exercise `GET /health/system/runtime` through the dashboard/API path and
  check only safe status fields and listener summaries.
- Re-run targeted tests:
  `.venv\Scripts\python.exe -m pytest tests\test_system_health.py
  tests\test_api_authorization_regression.py
  tests\test_dashboard_navigation_config.py
  tests\test_dashboard_responsive.py -q --tb=short`
- Run `git diff --check` and finish with
  `git status --short --untracked-files=all`.
- Append a dated post-restart verification entry with deviations and accepted
  gaps.

Known risks or accepted gaps:
- Current changes are uncommitted and depend on the working tree being
  preserved across restart.
- The new FastAPI route will not exist in runtime until the startup task has
  restarted the API process from the current working tree.
- Authenticated browser rendering of `Health systemu` has only been partially
  checked: the page loads, but runtime data is pending FastAPI restart.
- Direct public hostname reachability from the workstation previously timed
  out; local Caddy hostname routing through loopback may still be needed for
  server-side verification.
- Existing unrelated SmartFuelPass/map changes remain in the dirty working
  tree and should not be reverted as part of post-restart checks.
- The current scheduled-task account remains broader than least privilege.
- The launcher does not independently restart a child process that fails after
  startup.

### 2026-07-07 07:56 +02:00 - Post-restart verification after Health systemu runtime check

Scope:
- Verified the production runtime after the 2026-07-07 workstation restart for
  the new admin-only `Health systemu` runtime check.
- Kept checks to safe statuses, timestamps, listener summaries, and test
  results; no cookies, bearer tokens, credentials, raw process command lines,
  environment values, portal rows, or device photo paths were printed.

Verified:
- `git status --short --untracked-files=all` was clean before this note was
  appended.
- Windows last boot time: `2026-07-07 07:43:38 +02:00`.
- Startup scheduled task `API_dashboard_caddy` last ran at
  `2026-07-07 07:43:49 +02:00` with result `0`.
- Expected listeners are present: Caddy on `80`, `443`, and
  `127.0.0.1:2019`; FastAPI on `127.0.0.1:8000`; Streamlit on
  `127.0.0.1:8001`.
- No listener was present on temporary ports `8010` or `8011`.
- Additional `443` listeners on Tailscale addresses are owned by
  `tailscaled.exe`, separate from the public Caddy listener.
- API `/health/live` and `/health/ready`, Streamlit `/_stcore/health`, and
  Caddy admin `/config/` returned HTTP 200.
- `GET /health/system/runtime` without a bearer token returned HTTP 401 JSON,
  confirming that the post-restart FastAPI route is registered instead of
  returning the previous HTTP 404.
- The user confirmed the `Health systemu` dashboard page appears without an
  error after restart.
- Local Caddy hostname routing via SNI/Host to `127.0.0.1` verified:
  dashboard HTTP 200, `users-exist` HTTP 200, protected API without bearer
  HTTP 401 JSON, map image without cookie HTTP 401 JSON, `/docs`, `/redoc`,
  and `/openapi.json` HTTP 404, and HTTP-to-HTTPS redirect HTTP 308.
- Public response security headers were present on the local Caddy hostname
  path: HSTS, `nosniff`, `Referrer-Policy`, `X-Frame-Options`,
  `Permissions-Policy`, and CSP report-only. `Server` and `Via` headers were
  absent.
- Tracked root `Caddyfile` and runtime
  `C:\Program Files\Caddy\Caddyfile` have matching SHA-256 hashes, and
  `caddy validate --config "C:\Program Files\Caddy\Caddyfile"` reported a
  valid configuration.
- `.venv-production` passed `pip check` and
  `scripts/verify_production_environment.py`.
- Scheduler metrics show `scheduler_running=true`, heartbeat
  `2026-07-07T07:54:11.203611`, and `quarter_hour_job` success at
  `2026-07-07T07:47:11.629926`, after the `07:43:38` boot.
- Scheduler failure timestamp metrics were empty during this check.
- Targeted tests passed:
  `.venv\Scripts\python.exe -m pytest tests\test_system_health.py
  tests\test_api_authorization_regression.py
  tests\test_dashboard_navigation_config.py
  tests\test_dashboard_responsive.py -q --tb=short` reported 196 passed.
- `git diff --check` reported no whitespace errors before this note was
  appended.

Not verified:
- A direct live HTTP 200 call to `GET /health/system/runtime` with an admin
  bearer token was not made from the shell because the check intentionally did
  not read or print dashboard cookies or bearer tokens.
- A live non-admin HTTP 403 call to `GET /health/system/runtime` was not made;
  this remains covered by the authorization regression tests.
- Direct public hostname reachability through external DNS/NAT was not
  re-tested from the workstation; routing was verified through local Caddy
  SNI/Host resolution, and the user confirmed the dashboard page rendered.

Decisions/notes:
- The previous dashboard-visible `DashboardApiError: Not Found` state is
  resolved after restart because the new FastAPI route is now registered.
- No DECISION update is needed for this verification-only session.

### 2026-07-07

Scope:
- Added the second incremental `Health systemu` check: proxy and public
  routing health.
- Kept the check backend-owned and admin-only; browser/Streamlit does not run
  local shell, filesystem, or raw network probes directly.

Changed:
- Added admin API route `GET /health/system/proxy`.
- Added sanitized Caddy proxy checks for local hostname routing through
  `127.0.0.1` with the production Host/SNI value.
- The proxy check verifies dashboard HTTP 200, public `users-exist` HTTP 200,
  protected API without bearer HTTP 401, map image without cookie HTTP 401,
  `/docs`, `/redoc`, and `/openapi.json` HTTP 404, and HTTP-to-HTTPS redirect
  HTTP 308.
- The proxy check verifies selected public response headers are present and
  that `Server` and `Via` are absent, without returning response bodies.
- Added dashboard API helper and a new `Proxy a routovani` block on
  `Health systemu`.
- Added service, route, and authorization tests for the new proxy endpoint.

Verified:
- `.venv\Scripts\python.exe -m py_compile services\api\services\system_health.py
  services\api\routes\system_health.py services\api\schemas\admin.py
  moduly\apps\dashboard\api_client.py
  moduly\apps\dashboard\pages\37_system_health.py`
- `.venv\Scripts\python.exe -m pytest tests\test_system_health.py
  tests\test_api_authorization_regression.py
  tests\test_dashboard_navigation_config.py
  tests\test_dashboard_responsive.py -q --tb=short` reported 201 passed.
- Local collector call returned proxy `status=ok`; all expected route checks
  and header checks were `ok`.
- `git diff --check` reported no whitespace errors, only expected
  LF-to-CRLF warnings.

Not verified:
- Live dashboard rendering of the new proxy block through the running FastAPI
  process. The running production API must restart or reload before
  `/health/system/proxy` is registered in that process.

Decisions/notes:
- No new durable decision was needed; this implements the already planned
  second `Health systemu` check.

### 2026-07-07 08:52 +02:00 - Pre-restart handoff after Health systemu proxy check

Reason for restart:
- Reload FastAPI, Streamlit, scheduler, and Caddy through the normal startup
  task so the new admin endpoint `GET /health/system/proxy` is registered in
  the running FastAPI process.
- Allow the `Health systemu` dashboard page to load the new `Proxy a routovani`
  block from the live API instead of showing the controlled "endpoint not
  available yet" state.

Current task/conversation state:
- Completed: post-restart verification confirmed the first
  `Health systemu` runtime block is live after the previous restart.
- Completed: added the second `Health systemu` check for Caddy proxy routing
  and public response headers.
- Completed: added admin API route `GET /health/system/proxy` and response
  schemas for route/header statuses.
- Completed: added backend local Caddy Host/SNI checks through `127.0.0.1`
  for dashboard, public auth bootstrap, protected API, map image auth,
  documentation aliases, HTTP redirect, and selected public headers.
- Completed: added dashboard API helper and the `Proxy a routovani` block on
  `Health systemu`.
- Completed: added system health and authorization regression tests.
- Pending: restart workstation, then verify the running FastAPI process exposes
  `/health/system/proxy` and the dashboard proxy block renders live data.
- First action after restart: read `AGENTS.md`, `DECISIONS.md`, and
  `SESSION_NOTES.md`; run `git status --short --untracked-files=all`; verify
  runtime health, then test `Health systemu` runtime and proxy blocks.

Working tree and deployment:
- Current time captured before restart: `2026-07-07 08:52:09 +02:00`.
- Branch: `master`.
- `HEAD`: `cae679396fd1c0879d5aec919c1c7ca4660164d2`.
- No git commit was created for this handoff.
- `git status --short --untracked-files=all` before this handoff:
  - `M SESSION_NOTES.md`
  - `M moduly/apps/dashboard/api_client.py`
  - `M moduly/apps/dashboard/pages/37_system_health.py`
  - `M services/api/routes/system_health.py`
  - `M services/api/schemas/admin.py`
  - `M services/api/services/system_health.py`
  - `M tests/test_api_authorization_regression.py`
  - `M tests/test_system_health.py`
- Files changed by the latest `Health systemu` proxy work:
  - `moduly/apps/dashboard/api_client.py`
  - `moduly/apps/dashboard/pages/37_system_health.py`
  - `services/api/routes/system_health.py`
  - `services/api/schemas/admin.py`
  - `services/api/services/system_health.py`
  - `tests/test_api_authorization_regression.py`
  - `tests/test_system_health.py`
  - `SESSION_NOTES.md`
- Runtime deployment state: running FastAPI was not restarted after adding
  `/health/system/proxy`; the new route may return HTTP 404 until the startup
  task restarts the API process from the current working tree.
- Tracked/runtime Caddyfile synchronization was not changed by this work.

Verification already run:
- `.venv\Scripts\python.exe -m py_compile services\api\services\system_health.py
  services\api\routes\system_health.py services\api\schemas\admin.py
  moduly\apps\dashboard\api_client.py
  moduly\apps\dashboard\pages\37_system_health.py`
- `.venv\Scripts\python.exe -m pytest tests\test_system_health.py
  tests\test_api_authorization_regression.py
  tests\test_dashboard_navigation_config.py
  tests\test_dashboard_responsive.py -q --tb=short` reported 201 passed.
- Local collector call returned proxy `status=ok`; route checks reported:
  dashboard HTTP 200, `users-exist` HTTP 200, protected API without bearer
  HTTP 401, map image without cookie HTTP 401, `/docs`, `/redoc`, and
  `/openapi.json` HTTP 404, and HTTP-to-HTTPS redirect HTTP 308.
- Local collector header checks reported HSTS, `nosniff`, `Referrer-Policy`,
  `X-Frame-Options`, `Permissions-Policy`, and CSP report-only present, with
  `Server` and `Via` absent.
- `git diff --check` reported no whitespace errors, only expected
  LF-to-CRLF warnings.

Sensitive/runtime artifacts:
- Do not print, read, delete, revert, stage, or commit raw values from ignored
  local `.env`, dashboard/API tokens, passwords, cookies, authentication audit
  logs, ProgramData security artifacts, or local leftover SmartFuelPass session
  JSON files.
- Do not print raw SmartFuelPass portal data, raw device photo filesystem paths,
  process command lines, environment variables, bearer tokens, dashboard
  session cookie values, or response bodies from protected API checks.
- Do not create a production code-integrity baseline from this dirty working
  tree unless the user explicitly approves that exact state.

Expected processes and listeners after restart:
- Windows Task Scheduler runs `API_dashboard_caddy` at system startup and its
  latest run result becomes `0`.
- One rotating-log wrapper owns one non-reload Uvicorn child on
  `127.0.0.1:8000`.
- One rotating-log wrapper owns one Streamlit child on `127.0.0.1:8001`.
- One scheduler runtime runs `main.py`, holds the `scheduler_process` lock,
  and updates `core/scheduler/logs/scheduler_metrics.json`.
- One Caddy runtime owns TCP `80`/`443` and admin `127.0.0.1:2019`.
- No listener should remain on temporary ports `8010` or `8011`.

Expected application state after restart:
- FastAPI `/health/live` and `/health/ready`: HTTP 200 while PostgreSQL is
  available.
- Streamlit `/_stcore/health` and Caddy admin endpoint: HTTP 200.
- FastAPI `GET /health/system/runtime` without bearer token: HTTP 401 JSON,
  proving the runtime route remains registered.
- FastAPI `GET /health/system/proxy` without bearer token: HTTP 401 JSON,
  proving the new proxy route is registered.
- FastAPI `GET /health/system/proxy` with a valid admin bearer token:
  HTTP 200 and safe JSON with `status`, `checked_at`, `public_host`, route
  statuses, and header statuses.
- Non-admin bearer token for `GET /health/system/proxy`: HTTP 403.
- `Health systemu` dashboard page loads without traceback; `Runtime po
  restartu` and `Proxy a routovani` blocks both display live data.
- Proxy block expected values: overall `OK`, public host
  `monitoring.armexholding.cz`, zero routes outside OK, zero headers outside
  OK.
- HTTP hostname route: HTTP 308 to HTTPS.
- HTTPS dashboard: HTTP 200.
- Protected API without bearer token: HTTP 401 JSON.
- Map image without cookie: HTTP 401 JSON.
- Public `/docs`, `/redoc`, and `/openapi.json`: HTTP 404 at Caddy layer.
- Public response security headers present on the local Caddy hostname path:
  HSTS, `nosniff`, `Referrer-Policy`, `X-Frame-Options`,
  `Permissions-Policy`, and CSP report-only; `Server` and `Via` absent.

Required post-restart checks:
- Confirm boot time, scheduled-task last run/result/settings, process tree,
  listeners, and no temporary ports `8010` or `8011`.
- Confirm API live/ready, Streamlit health, Caddy admin health, scheduler
  heartbeat, and current runtime log freshness.
- Confirm tracked root `Caddyfile` and runtime
  `C:\Program Files\Caddy\Caddyfile` still have matching SHA-256 hashes, then
  validate runtime Caddy config.
- Verify local Caddy hostname routing with SNI/Host routing if direct public
  hostname requests from the workstation still time out.
- Log in to `https://monitoring.armexholding.cz` without printing cookie or
  token values.
- Open `Health systemu` and confirm the `Proxy a routovani` block displays
  live data and no traceback.
- Exercise `GET /health/system/proxy` through the dashboard/API path and check
  only safe status fields, expected HTTP codes, and header presence summaries.
- Re-run targeted tests:
  `.venv\Scripts\python.exe -m pytest tests\test_system_health.py
  tests\test_api_authorization_regression.py
  tests\test_dashboard_navigation_config.py
  tests\test_dashboard_responsive.py -q --tb=short`
- Run `git diff --check` and finish with
  `git status --short --untracked-files=all`.
- Append a dated post-restart verification entry with deviations and accepted
  gaps.

Known risks or accepted gaps:
- Current changes are uncommitted and depend on the working tree being
  preserved across restart.
- The new FastAPI proxy route will not exist in runtime until the startup task
  has restarted the API process from the current working tree.
- Direct public hostname reachability from the workstation may still require
  local Caddy Host/SNI verification through loopback.
- The current scheduled-task account remains broader than least privilege.
- The launcher does not independently restart a child process that fails after
  startup.

### 2026-07-07 13:14 +02:00 - Post-restart verification and Scheduler Health manual-run fix

Scope:
- Ran post-restart checks after the `API_dashboard_caddy` startup task.
- Fixed `Health scheduleru` manual-run confirmation behavior where `Spustit
  jednou` stayed disabled after checking the confirmation box.

Changed:
- `moduly/apps/dashboard/pages/16_scheduler_health.py`: moved the manual-run
  selectbox, confirmation checkbox, and `Spustit jednou` button outside
  `st.form`. Streamlit form widget changes are submitted only by the submit
  button, so a disabled submit button could not react to the checkbox value.

Verified:
- Windows boot time was `2026-07-07 12:57:02 +02:00`.
- Startup task `API_dashboard_caddy` last ran at
  `2026-07-07 12:57:12 +02:00` with result `0`.
- Expected listeners were present on `80`, `443`, `127.0.0.1:2019`,
  `127.0.0.1:8000`, and `127.0.0.1:8001`; no listeners were present on
  temporary ports `8010` or `8011`.
- FastAPI `/health/live` and `/health/ready`, Streamlit `/_stcore/health`,
  and Caddy admin `/config/` returned HTTP 200.
- `/health/system/runtime`, `/health/system/proxy`, and
  `/health/system/scheduler` without bearer token returned HTTP 401.
- `/api/v1/map/images` without a dashboard cookie returned HTTP 401.
- Scheduler metrics showed `scheduler_running=True` and heartbeat
  `2026-07-07T13:07:19.872512`; `quarter_hour_job` last ran at
  `2026-07-07T13:05:09.433327` with status `success`, next run
  `2026-07-07T13:16:05+02:00`, and zero 24h failures.
- Tracked root `Caddyfile` and runtime
  `C:\Program Files\Caddy\Caddyfile` SHA-256 hashes matched.
- Runtime Caddy configuration validation reported `Valid configuration`.
- Direct public hostname requests from the workstation timed out, so local
  Caddy Host/SNI routing was verified through loopback instead: dashboard
  HTTP 200, `users-exist` HTTP 200, protected auth endpoint HTTP 401,
  map-image without cookie HTTP 401, `/docs`, `/redoc`, and `/openapi.json`
  HTTP 404, and HTTP-to-HTTPS redirect HTTP 308.
- Public response security header check through local Caddy Host/SNI showed
  HSTS, `nosniff`, `Referrer-Policy`, `X-Frame-Options`,
  `Permissions-Policy`, and CSP report-only. The selected header check did
  not report `Server` or `Via`.
- `.venv\Scripts\python.exe -m py_compile
  moduly\apps\dashboard\pages\16_scheduler_health.py` passed.
- `.venv-production\Scripts\python.exe -m py_compile
  moduly\apps\dashboard\pages\16_scheduler_health.py` passed.
- `.venv\Scripts\python.exe -m pytest
  tests\test_dashboard_scheduler_health_view.py
  tests\test_dashboard_scheduler_log_view.py tests\test_scheduler_metrics.py
  tests\test_dashboard_navigation_config.py -q --tb=short` reported
  `38 passed`.
- `git diff --check` reported no whitespace errors, only the expected
  LF-to-CRLF warning for the edited Streamlit page.

Not verified:
- Authenticated browser confirmation on `Health scheduleru` was not performed
  in this shell session.
- Direct public hostname reachability from the workstation still timed out;
  local Caddy Host/SNI verification covered the running local proxy path.

Follow-up:
- Refresh `Health scheduleru` in the authenticated browser and confirm that a
  high-impact target enables `Spustit jednou` after checking
  `Potvrzuji provozni dopad a chci tento cil spustit.`
- If testing an actual manual run, prefer low-risk
  `check_database_availability` and avoid data-changing or email/report
  targets without deliberate operator confirmation.

### 2026-07-07 13:34 +02:00 - Health systemu PostgreSQL check

Scope:
- Continued `Health systemu` incremental checks with a PostgreSQL database
  health block.
- User confirmed the previous `Health scheduleru` manual-run confirmation fix
  works in the browser and a job started successfully.

Changed:
- Added admin-only FastAPI endpoint `GET /health/system/database`.
- Added sanitized PostgreSQL collector for connection availability, query
  latency, server time/timezone/version, transaction read-only state, and
  presence of expected schemas: `dashboard`, `dbo`, `evidence`, `monitoring`,
  `revize`, and `web_search`.
- Added dashboard API client and `Health systemu` Streamlit `PostgreSQL`
  block with summary metrics and schema table.
- Updated the FastAPI authorization inventory and system health tests.

Verified:
- `.venv\Scripts\python.exe -m py_compile services\api\services\system_health.py
  services\api\routes\system_health.py services\api\schemas\admin.py
  moduly\apps\dashboard\api_client.py
  moduly\apps\dashboard\pages\37_system_health.py tests\test_system_health.py`
  passed.
- `.venv-production\Scripts\python.exe -m py_compile
  services\api\services\system_health.py services\api\routes\system_health.py
  services\api\schemas\admin.py moduly\apps\dashboard\api_client.py
  moduly\apps\dashboard\pages\37_system_health.py` passed.
- `.venv\Scripts\python.exe -m pytest tests\test_system_health.py
  tests\test_api_authorization_regression.py -q --tb=short` reported
  `187 passed`.
- `.venv\Scripts\python.exe -m pytest tests\test_dashboard_navigation_config.py
  tests\test_dashboard_responsive.py -q --tb=short` reported `26 passed`.
- Direct sanitized collector run returned PostgreSQL `status=ok`,
  `connected=True`, `read_only=False`, query latency about `82 ms`, and all
  six expected schemas present.

Not verified:
- Running FastAPI process has not been restarted after adding
  `/health/system/database`; the live unauthenticated route check currently
  returns HTTP 404. The dashboard block will populate after the standard
  runtime restart/reload.
- Authenticated browser rendering of the new `Health systemu` PostgreSQL block
  was not performed in this shell session.

Decisions/notes:
- The database health response intentionally does not expose DSN, host,
  username, password, environment values, raw table rows, or raw operational
  data.

### 2026-07-07 13:38 +02:00 - Pre-restart handoff after Health systemu PostgreSQL check

Reason for restart:
- Reload FastAPI, Streamlit, scheduler, and Caddy through the normal startup
  task after adding the `Health systemu` PostgreSQL check.
- Activate the new FastAPI route `GET /health/system/database` and the new
  Streamlit `PostgreSQL` block in the running dashboard process.

Current task/conversation state:
- Completed: post-restart runtime verification after the previous restart.
- Completed: fixed `Health scheduleru` manual-run confirmation behavior by
  moving the selectbox, checkbox, and `Spustit jednou` button outside
  `st.form`.
- Completed: user confirmed the `Health scheduleru` button now enables after
  checking the confirmation box and a manual job started successfully.
- Completed: added an admin-only `Health systemu` PostgreSQL database check
  with sanitized connection/query metadata and expected schema presence.
- Completed: direct sanitized collector run returned PostgreSQL `status=ok`,
  `connected=True`, `read_only=False`, query latency about `82 ms`, and all
  expected schemas present.
- Pending: restart workstation/runtime processes and verify the new database
  endpoint and dashboard block from the running production processes.
- First action after restart: read `AGENTS.md`, `DECISIONS.md`, and
  `SESSION_NOTES.md`; run `git status --short --untracked-files=all`; then run
  the post-restart checks below.

Working tree and deployment:
- Current time captured before restart: `2026-07-07 13:38:19 +02:00`.
- Branch: `master`.
- `HEAD`: `0e4d13ca4b90c6afdba5ee1353e2dc9ccc99b052`.
- No git commit was created for this handoff.
- `git status --short --untracked-files=all` before this handoff:
  - `M SESSION_NOTES.md`
  - `M moduly/apps/dashboard/api_client.py`
  - `M moduly/apps/dashboard/pages/16_scheduler_health.py`
  - `M moduly/apps/dashboard/pages/37_system_health.py`
  - `M services/api/routes/system_health.py`
  - `M services/api/schemas/admin.py`
  - `M services/api/services/system_health.py`
  - `M tests/test_api_authorization_regression.py`
  - `M tests/test_system_health.py`
- Files changed by the `Health scheduleru` manual-run confirmation fix:
  - `moduly/apps/dashboard/pages/16_scheduler_health.py`
- Files changed by the `Health systemu` PostgreSQL check:
  - `moduly/apps/dashboard/api_client.py`
  - `moduly/apps/dashboard/pages/37_system_health.py`
  - `services/api/routes/system_health.py`
  - `services/api/schemas/admin.py`
  - `services/api/services/system_health.py`
  - `tests/test_api_authorization_regression.py`
  - `tests/test_system_health.py`
- Session documentation changed:
  - `SESSION_NOTES.md`
- Runtime deployment state: the running FastAPI process was started before
  adding `/health/system/database`; unauthenticated
  `http://127.0.0.1:8000/health/system/database` currently returns HTTP 404.
  After restart it should return HTTP 401 without bearer token.
- The running Streamlit process may not show the new `PostgreSQL` block until
  it restarts from the current working tree.
- Tracked root `Caddyfile` SHA-256 before restart:
  `08CDF04AFC4F856FEC8DFE4AB2E07A746763B152CA91553E349CCCE8E6D3DF2C`.
- Runtime `C:\Program Files\Caddy\Caddyfile` SHA-256 before restart:
  `08CDF04AFC4F856FEC8DFE4AB2E07A746763B152CA91553E349CCCE8E6D3DF2C`.
- Root/runtime Caddyfile hashes match, and runtime Caddy validation reported
  `Valid configuration`.
- Startup task `API_dashboard_caddy` last ran at
  `2026-07-07 12:57:12 +02:00` with result `0`.
- Existing listener state before restart:
  - Caddy owns TCP `80`, `443`, and `127.0.0.1:2019`, PID `11372`.
  - FastAPI listens on `127.0.0.1:8000`, PID `9604`.
  - Streamlit listens on `127.0.0.1:8001`, PID `10808`.
  - Tailscale owns expected interface-specific `443` listeners, PID `7192`.
  - No listeners are present on temporary ports `8010` or `8011`.
- Runtime health before restart:
  - FastAPI `/health/live`: HTTP 200.
  - FastAPI `/health/ready`: HTTP 200.
  - Streamlit `/_stcore/health`: HTTP 200.
  - Caddy admin `/config/`: HTTP 200.
  - FastAPI `/health/system/scheduler` without bearer token: HTTP 401 JSON.
  - FastAPI `/health/system/database` without bearer token: HTTP 404 JSON
    until FastAPI is restarted.
- Scheduler metrics before restart:
  - `scheduler_running=True`.
  - `last_heartbeat=2026-07-07T13:37:20.012713`.
  - `quarter_hour_job` last run `2026-07-07T13:35:09.275152`, status
    `success`, next run `2026-07-07T13:47:05+02:00`.
  - `quarter_hour_job` 24h failures: `0`.
  - Metrics currently contain 42 job/internal-step records.

Verification already run:
- `.venv\Scripts\python.exe -m py_compile services\api\services\system_health.py
  services\api\routes\system_health.py services\api\schemas\admin.py
  moduly\apps\dashboard\api_client.py
  moduly\apps\dashboard\pages\37_system_health.py tests\test_system_health.py`
  passed.
- `.venv-production\Scripts\python.exe -m py_compile
  services\api\services\system_health.py services\api\routes\system_health.py
  services\api\schemas\admin.py moduly\apps\dashboard\api_client.py
  moduly\apps\dashboard\pages\37_system_health.py` passed.
- `.venv\Scripts\python.exe -m pytest tests\test_system_health.py
  tests\test_api_authorization_regression.py -q --tb=short` reported
  `187 passed`.
- `.venv\Scripts\python.exe -m pytest tests\test_dashboard_navigation_config.py
  tests\test_dashboard_responsive.py -q --tb=short` reported `26 passed`.
- `.venv\Scripts\python.exe -m py_compile
  moduly\apps\dashboard\pages\16_scheduler_health.py` passed.
- `.venv-production\Scripts\python.exe -m py_compile
  moduly\apps\dashboard\pages\16_scheduler_health.py` passed.
- `.venv\Scripts\python.exe -m pytest
  tests\test_dashboard_scheduler_health_view.py
  tests\test_dashboard_scheduler_log_view.py tests\test_scheduler_metrics.py
  tests\test_dashboard_navigation_config.py -q --tb=short` reported
  `38 passed`.
- `git diff --check` reported no whitespace errors, only expected LF-to-CRLF
  warnings on edited files.

Sensitive/runtime artifacts:
- Do not print, read, delete, revert, stage, or commit raw values from ignored
  local `.env`, dashboard/API tokens, passwords, cookies, authentication audit
  logs, ProgramData security artifacts, local leftover SmartFuelPass session
  JSON files, or protected API response bodies.
- Do not print PostgreSQL DSN, host, username, password, environment values,
  raw table rows, raw operational data, process command lines, raw SmartFuelPass
  portal data, or raw device photo filesystem paths.
- Do not create a production code-integrity baseline from this dirty working
  tree unless the user explicitly approves that exact state.

Expected processes and listeners after restart:
- Windows Task Scheduler runs `API_dashboard_caddy` at system startup and its
  latest run result becomes `0`.
- One rotating-log wrapper owns one non-reload Uvicorn child on
  `127.0.0.1:8000`.
- One rotating-log wrapper owns one Streamlit child on `127.0.0.1:8001`.
- One scheduler runtime runs `main.py`, holds the `scheduler_process` lock,
  and updates `core/scheduler/logs/scheduler_metrics.json`.
- One Caddy runtime owns TCP `80`/`443` and admin `127.0.0.1:2019`.
- Tailscale interface-specific `443` listeners may remain in addition.
- No listener should remain on temporary ports `8010` or `8011`.

Expected application state after restart:
- FastAPI `/health/live` and `/health/ready`: HTTP 200 while PostgreSQL is
  available.
- Streamlit `/_stcore/health` and Caddy admin endpoint: HTTP 200.
- FastAPI `GET /health/system/runtime`, `/health/system/proxy`,
  `/health/system/scheduler`, and `/health/system/database` without bearer
  token: HTTP 401 JSON.
- FastAPI `GET /health/system/database` with a valid admin bearer token:
  HTTP 200 and safe JSON with PostgreSQL `status`, `checked_at`,
  `connected`, query latency, server time/timezone/version, read-only state,
  and expected schema statuses only.
- Non-admin bearer token for `GET /health/system/database`: HTTP 403.
- `Health systemu` dashboard page loads without traceback; `Runtime po
  restartu`, `Proxy a routovani`, `Scheduler`, and `PostgreSQL` blocks display
  live data.
- `Health systemu / PostgreSQL` expected values if DB state is unchanged:
  overall `OK`, `Pripojeni=ANO`, `Read-only=NE`, and all six schemas
  `dashboard`, `dbo`, `evidence`, `monitoring`, `revize`, and `web_search`
  present.
- `Health scheduleru` page remains available; high-impact manual targets keep
  `Spustit jednou` disabled until the confirmation checkbox is checked, and
  the button enables after checking it.
- HTTP hostname route: HTTP 308 to HTTPS.
- HTTPS dashboard through local Caddy hostname/SNI route: HTTP 200.
- Protected API without bearer token: HTTP 401 JSON.
- Map image without cookie: HTTP 401 JSON.
- Public `/docs`, `/redoc`, and `/openapi.json`: HTTP 404 at Caddy layer.
- Public response security headers remain present on the local Caddy hostname
  path: HSTS, `nosniff`, `Referrer-Policy`, `X-Frame-Options`,
  `Permissions-Policy`, and CSP report-only; `Server` and `Via` absent.

Required post-restart checks:
- Confirm boot time, scheduled-task last run/result/settings, process tree,
  listeners, and no temporary ports `8010` or `8011`.
- Confirm API live/ready, Streamlit health, Caddy admin health, scheduler
  heartbeat, and current runtime log freshness.
- Confirm scheduler metrics show `scheduler_running=true`, recent
  `last_heartbeat`, and a fresh `quarter_hour_job` observation after boot once
  the next scheduled quarter-hour run has had time to execute.
- Confirm tracked root `Caddyfile` and runtime
  `C:\Program Files\Caddy\Caddyfile` still have matching SHA-256 hashes, then
  validate runtime Caddy config.
- Verify local Caddy hostname routing with SNI/Host routing if direct public
  hostname requests from the workstation still time out.
- Confirm unauthenticated `GET /health/system/database` returns HTTP 401,
  replacing the pre-restart HTTP 404.
- Log in to `https://monitoring.armexholding.cz` without printing cookie or
  token values.
- Open `Health systemu` and confirm the `PostgreSQL` block displays live data
  and no traceback.
- Exercise `GET /health/system/database` through the dashboard/API path and
  check only safe status fields, latency, server time/timezone/version,
  read-only state, and schema aggregate statuses.
- Open `Health scheduleru` and confirm the manual-run confirmation checkbox
  still enables `Spustit jednou` for high-impact targets. Avoid running
  data-changing or email/report targets without deliberate operator
  confirmation.
- Re-run targeted tests:
  `.venv\Scripts\python.exe -m pytest tests\test_system_health.py
  tests\test_api_authorization_regression.py
  tests\test_dashboard_navigation_config.py tests\test_dashboard_responsive.py
  tests\test_dashboard_scheduler_health_view.py
  tests\test_dashboard_scheduler_log_view.py tests\test_scheduler_metrics.py
  -q --tb=short`
- Run the direct sanitized PostgreSQL collector and confirm it reports
  PostgreSQL `status=ok`, `connected=True`, `read_only=False`, and all six
  expected schemas present unless database state changed.
- Run `git diff --check` and finish with
  `git status --short --untracked-files=all`.
- Append a dated post-restart verification entry with deviations and accepted
  gaps.

Known risks or accepted gaps:
- Current changes are uncommitted and depend on the working tree being
  preserved across restart.
- The new FastAPI database route will not exist in runtime until the startup
  task has restarted the API process from the current working tree.
- Immediately after boot, `quarter_hour_job` may not yet have a post-boot
  observation until its next scheduled minute runs.
- Direct public hostname reachability from the workstation may still require
  local Caddy Host/SNI verification through loopback.
- The current scheduled-task account remains broader than least privilege.
- The launcher does not independently restart a child process that fails after
  startup.

### 2026-07-07 11:57 +02:00 - Pre-restart handoff after monthly_job fix

Reason for restart:
- Reload FastAPI, Streamlit, scheduler, and Caddy through the normal startup
  task so all current working-tree changes are active in runtime.
- Make the new `Health systemu` scheduler endpoint available in the running
  FastAPI process.
- Load the `monthly_job` fix into the scheduler process before any manual
  monthly report retry.

Current task/conversation state:
- Completed: diagnosed the `monthly_job` alert from `2026-07-01 06:20:05
  +02:00`. The failing target was
  `send_monthly_vodomery_consumption_report`.
- Completed: root cause was a stale query for `identifikace` in
  `evidence."vodomery"` / `evidence."vodoměry"`; the current evidence table
  no longer has that application identifier column.
- Completed: changed the monthly all-vodomery consumption report to load
  device identifiers from `monitoring."Mereni_vodomery_vse"` instead of the
  QGIS/evidence layer.
- Completed: added a regression test preventing this report from returning to
  the evidence-table identifier query.
- Completed earlier: added the third incremental `Health systemu` check for
  scheduler summary through admin FastAPI route
  `GET /health/system/scheduler` and the Streamlit dashboard block.
- Pending: restart workstation, then verify runtime health, the new
  `Health systemu` scheduler block, and the monthly report data-building path.
- First action after restart: read `AGENTS.md`, `DECISIONS.md`, and
  `SESSION_NOTES.md`; run `git status --short --untracked-files=all`; verify
  runtime health; then run the post-restart checks below.

Working tree and deployment:
- Current time captured before restart: `2026-07-07 11:57:25 +02:00`.
- Branch: `master`.
- `HEAD`: `9e94e13c257a55cda85b61ac259b6bc28580c801`.
- No git commit was created for this handoff.
- `git status --short --untracked-files=all` before this handoff:
  - `M SESSION_NOTES.md`
  - `M moduly/apps/dashboard/api_client.py`
  - `M moduly/apps/dashboard/pages/37_system_health.py`
  - `M moduly/mereni/vodomery/reporting/monthly_consumption_report.py`
  - `M services/api/routes/system_health.py`
  - `M services/api/schemas/admin.py`
  - `M services/api/services/system_health.py`
  - `M tests/test_api_authorization_regression.py`
  - `M tests/test_system_health.py`
  - `?? tests/test_monthly_consumption_report.py`
- Files changed by the latest monthly-job fix:
  - `moduly/mereni/vodomery/reporting/monthly_consumption_report.py`
  - `tests/test_monthly_consumption_report.py`
- Files already changed by the preceding `Health systemu` scheduler work:
  - `moduly/apps/dashboard/api_client.py`
  - `moduly/apps/dashboard/pages/37_system_health.py`
  - `services/api/routes/system_health.py`
  - `services/api/schemas/admin.py`
  - `services/api/services/system_health.py`
  - `tests/test_api_authorization_regression.py`
  - `tests/test_system_health.py`
  - `SESSION_NOTES.md`
- Runtime deployment state: running FastAPI was not restarted after adding
  `/health/system/scheduler`; the route may return HTTP 404 until restart.
  Running scheduler was not restarted after the monthly report fix; it may
  still use the old report code until restart.
- Tracked/runtime Caddyfile synchronization was not changed by this work.

Verification already run:
- `.venv\Scripts\python.exe -m pytest tests\test_monthly_consumption_report.py
  tests\test_scheduler.py::test_monthly_job_calls_all_monthly_reports -q
  --tb=short` reported `2 passed`.
- `.venv\Scripts\python.exe -m py_compile
  moduly\mereni\vodomery\reporting\monthly_consumption_report.py
  tests\test_monthly_consumption_report.py`
- `.venv-production\Scripts\python.exe -m py_compile
  moduly\mereni\vodomery\reporting\monthly_consumption_report.py`
- Real PostgreSQL read-only monthly dataframe check for period
  `2026-06-01T00:00:00` to `2026-07-01T00:00:00` returned `row_count=58`,
  `with_consumption=58`, `missing_start=0`, and `missing_end=0`.
- `git diff --check` reported no whitespace errors, only expected
  LF-to-CRLF warnings.
- Earlier `Health systemu` scheduler work verification:
  `.venv\Scripts\python.exe -m pytest tests\test_system_health.py
  tests\test_api_authorization_regression.py
  tests\test_dashboard_navigation_config.py
  tests\test_dashboard_responsive.py -q --tb=short` reported `207 passed`.

Sensitive/runtime artifacts:
- Do not print, read, delete, revert, stage, or commit raw values from ignored
  local `.env`, dashboard/API tokens, passwords, cookies, authentication audit
  logs, ProgramData security artifacts, or local leftover SmartFuelPass session
  JSON files.
- Do not print raw SmartFuelPass portal data, raw device photo filesystem
  paths, process command lines, environment variables, bearer tokens, dashboard
  session cookie values, or protected API response bodies.
- Do not print raw meter/source data rows while checking the monthly report;
  use aggregate counts and safe status fields.
- Do not create a production code-integrity baseline from this dirty working
  tree unless the user explicitly approves that exact state.

Expected processes and listeners after restart:
- Windows Task Scheduler runs `API_dashboard_caddy` at system startup and its
  latest run result becomes `0`.
- One rotating-log wrapper owns one non-reload Uvicorn child on
  `127.0.0.1:8000`.
- One rotating-log wrapper owns one Streamlit child on `127.0.0.1:8001`.
- One scheduler runtime runs `main.py`, holds the `scheduler_process` lock,
  and updates `core/scheduler/logs/scheduler_metrics.json`.
- One Caddy runtime owns TCP `80`/`443` and admin `127.0.0.1:2019`.
- No listener should remain on temporary ports `8010` or `8011`.

Expected application state after restart:
- FastAPI `/health/live` and `/health/ready`: HTTP 200 while PostgreSQL is
  available.
- Streamlit `/_stcore/health` and Caddy admin endpoint: HTTP 200.
- FastAPI `GET /health/system/runtime` without bearer token: HTTP 401 JSON.
- FastAPI `GET /health/system/proxy` without bearer token: HTTP 401 JSON.
- FastAPI `GET /health/system/scheduler` without bearer token: HTTP 401 JSON,
  proving the new scheduler route is registered.
- `Health systemu` dashboard page loads without traceback; `Runtime po
  restartu`, `Proxy a routovani`, and `Scheduler` blocks display live data.
- Scheduler block expected values: overall `OK`, `Scheduler bezi` = `ANO`,
  heartbeat age below the configured TTL, zero 24h failures unless a real job
  failed after restart, and 9 scheduled jobs.
- The monthly vodomery consumption report data-builder should no longer query
  `evidence."vodomery"` / `evidence."vodoměry"` for `identifikace`.
- Do not manually run `monthly_job` or
  `send_monthly_vodomery_consumption_report` without explicit user
  confirmation after restart, because the send path can email recipients.

Required post-restart checks:
- Confirm boot time, scheduled-task last run/result/settings, process tree,
  listeners, and no temporary ports `8010` or `8011`.
- Confirm API live/ready, Streamlit health, Caddy admin health, scheduler
  heartbeat, and current runtime log freshness.
- Confirm scheduler metrics show `scheduler_running=true`, recent
  `last_heartbeat`, and a fresh `quarter_hour_job` observation after boot once
  the next scheduled quarter-hour run has had time to execute.
- Confirm tracked root `Caddyfile` and runtime
  `C:\Program Files\Caddy\Caddyfile` still have matching SHA-256 hashes, then
  validate runtime Caddy config.
- Verify local Caddy hostname routing with SNI/Host routing if direct public
  hostname requests from the workstation still time out.
- Log in to `https://monitoring.armexholding.cz` without printing cookie or
  token values.
- Open `Health systemu` and confirm the `Scheduler` block displays live data
  and no traceback.
- Exercise `GET /health/system/scheduler` through the dashboard/API path and
  check only safe status fields, heartbeat metadata, 24h totals, and job
  summary statuses.
- Re-run targeted tests:
  `.venv\Scripts\python.exe -m pytest tests\test_monthly_consumption_report.py
  tests\test_scheduler.py::test_monthly_job_calls_all_monthly_reports
  tests\test_system_health.py tests\test_api_authorization_regression.py
  tests\test_dashboard_navigation_config.py tests\test_dashboard_responsive.py
  -q --tb=short`
- Run the read-only monthly dataframe check for reference date `2026-07-07`
  and confirm aggregate output remains `row_count=58`, `with_consumption=58`,
  `missing_start=0`, and `missing_end=0` unless new data changed since this
  handoff.
- Only after user confirmation, retry the relevant monthly report send or
  manual scheduler step.
- Run `git diff --check` and finish with
  `git status --short --untracked-files=all`.
- Append a dated post-restart verification entry with deviations and accepted
  gaps.

Known risks or accepted gaps:
- Current changes are uncommitted and depend on the working tree being
  preserved across restart.
- The new FastAPI scheduler route and monthly report fix will not exist in
  runtime until the startup task has restarted the API/scheduler processes from
  the current working tree.
- Immediately after boot, `quarter_hour_job` may not yet have a post-boot
  observation until its next scheduled minute runs.
- `monthly_job` failed before subsequent monthly report steps on
  `2026-07-01`; those emails may still need a controlled manual retry after
  restart.
- Direct public hostname reachability from the workstation may still require
  local Caddy Host/SNI verification through loopback.
- The current scheduled-task account remains broader than least privilege.
- The launcher does not independently restart a child process that fails after
  startup.

### 2026-07-07

Scope:
- Added the third incremental `Health systemu` check: scheduler summary.
- Reused existing scheduler metrics as the safe source of truth instead of
  reading process command lines or raw logs.

Changed:
- Added admin API route `GET /health/system/scheduler`.
- Added sanitized scheduler health schema and collector with heartbeat age,
  heartbeat TTL, 24h success/failure totals, and scheduled-job summaries.
- The summary degrades on stale/missing scheduler heartbeat, missing job next
  run metadata, recent 24h failures, or stale `quarter_hour_job`; historical
  last-status errors outside the current 24h failure window are shown in
  detail but do not degrade the post-restart summary.
- Added dashboard API helper and a new `Scheduler` block on `Health systemu`.
- Added system health and authorization regression tests for the new endpoint.

Verified:
- `.venv\Scripts\python.exe -m py_compile services\api\services\system_health.py
  services\api\routes\system_health.py services\api\schemas\admin.py
  moduly\apps\dashboard\api_client.py
  moduly\apps\dashboard\pages\37_system_health.py`
- `.venv\Scripts\python.exe -m pytest tests\test_system_health.py
  tests\test_api_authorization_regression.py
  tests\test_dashboard_navigation_config.py
  tests\test_dashboard_responsive.py -q --tb=short` reported 207 passed.
- Local collector call returned scheduler `status=ok`, running scheduler,
  recent heartbeat, zero 24h failures, and 9 scheduled jobs.
- `git diff --check` reported no whitespace errors, only expected
  LF-to-CRLF warnings.

Not verified:
- Live dashboard rendering of the new scheduler block through the running
  FastAPI process. The running production API must restart or reload before
  `/health/system/scheduler` is registered in that process.

Decisions/notes:
- No new durable decision was needed; this implements the already planned
  scheduler check under DEC-048.

### 2026-07-07 09:57 +02:00 - Pre-restart handoff after Health systemu scheduler check

Reason for restart:
- Reload FastAPI, Streamlit, scheduler, and Caddy through the normal startup
  task so the new admin endpoint `GET /health/system/scheduler` is registered
  in the running FastAPI process.
- Allow the `Health systemu` dashboard page to load the new `Scheduler` block
  from the live API instead of showing the controlled "endpoint not available
  yet" state.

Current task/conversation state:
- Completed: the user confirmed the standalone `Health scheduleru` page
  displays correctly.
- Completed: added the third incremental `Health systemu` check for scheduler
  summary using existing scheduler metrics.
- Completed: added admin API route `GET /health/system/scheduler` and response
  schemas for heartbeat age, heartbeat TTL, 24h success/failure totals, and
  scheduled-job summaries.
- Completed: added dashboard API helper and the `Scheduler` block on
  `Health systemu`.
- Completed: added system health and authorization regression tests.
- Pending: restart workstation, then verify the running FastAPI process
  exposes `/health/system/scheduler` and the dashboard scheduler block renders
  live data.
- First action after restart: read `AGENTS.md`, `DECISIONS.md`, and
  `SESSION_NOTES.md`; run `git status --short --untracked-files=all`; verify
  runtime health, then test `Health systemu` runtime, proxy, and scheduler
  blocks.

Working tree and deployment:
- Current time captured before restart: `2026-07-07 09:57:44 +02:00`.
- Branch: `master`.
- `HEAD`: `9e94e13c257a55cda85b61ac259b6bc28580c801`.
- No git commit was created for this handoff.
- `git status --short --untracked-files=all` before this handoff:
  - `M SESSION_NOTES.md`
  - `M moduly/apps/dashboard/api_client.py`
  - `M moduly/apps/dashboard/pages/37_system_health.py`
  - `M services/api/routes/system_health.py`
  - `M services/api/schemas/admin.py`
  - `M services/api/services/system_health.py`
  - `M tests/test_api_authorization_regression.py`
  - `M tests/test_system_health.py`
- Files changed by the latest `Health systemu` scheduler work:
  - `moduly/apps/dashboard/api_client.py`
  - `moduly/apps/dashboard/pages/37_system_health.py`
  - `services/api/routes/system_health.py`
  - `services/api/schemas/admin.py`
  - `services/api/services/system_health.py`
  - `tests/test_api_authorization_regression.py`
  - `tests/test_system_health.py`
  - `SESSION_NOTES.md`
- Runtime deployment state: running FastAPI was not restarted after adding
  `/health/system/scheduler`; the new route may return HTTP 404 until the
  startup task restarts the API process from the current working tree.
- `main.py` remains the scheduler entry point and should be relaunched by the
  startup task as part of the standard runtime set.
- Tracked/runtime Caddyfile synchronization was not changed by this work.

Verification already run:
- `.venv\Scripts\python.exe -m py_compile services\api\services\system_health.py
  services\api\routes\system_health.py services\api\schemas\admin.py
  moduly\apps\dashboard\api_client.py
  moduly\apps\dashboard\pages\37_system_health.py`
- `.venv\Scripts\python.exe -m pytest tests\test_system_health.py
  tests\test_api_authorization_regression.py
  tests\test_dashboard_navigation_config.py
  tests\test_dashboard_responsive.py -q --tb=short` reported 207 passed.
- Local collector call returned scheduler `status=ok`, `scheduler_running=True`,
  recent heartbeat, zero 24h failures, and 9 scheduled jobs.
- `git diff --check` reported no whitespace errors, only expected
  LF-to-CRLF warnings.

Sensitive/runtime artifacts:
- Do not print, read, delete, revert, stage, or commit raw values from ignored
  local `.env`, dashboard/API tokens, passwords, cookies, authentication audit
  logs, ProgramData security artifacts, or local leftover SmartFuelPass session
  JSON files.
- Do not print raw SmartFuelPass portal data, raw device photo filesystem paths,
  process command lines, environment variables, bearer tokens, dashboard
  session cookie values, or response bodies from protected API checks.
- Do not create a production code-integrity baseline from this dirty working
  tree unless the user explicitly approves that exact state.

Expected processes and listeners after restart:
- Windows Task Scheduler runs `API_dashboard_caddy` at system startup and its
  latest run result becomes `0`.
- One rotating-log wrapper owns one non-reload Uvicorn child on
  `127.0.0.1:8000`.
- One rotating-log wrapper owns one Streamlit child on `127.0.0.1:8001`.
- One scheduler runtime runs `main.py`, holds the `scheduler_process` lock,
  and updates `core/scheduler/logs/scheduler_metrics.json`.
- One Caddy runtime owns TCP `80`/`443` and admin `127.0.0.1:2019`.
- No listener should remain on temporary ports `8010` or `8011`.

Expected application state after restart:
- FastAPI `/health/live` and `/health/ready`: HTTP 200 while PostgreSQL is
  available.
- Streamlit `/_stcore/health` and Caddy admin endpoint: HTTP 200.
- FastAPI `GET /health/system/runtime` without bearer token: HTTP 401 JSON,
  proving the runtime route remains registered.
- FastAPI `GET /health/system/proxy` without bearer token: HTTP 401 JSON,
  proving the proxy route remains registered.
- FastAPI `GET /health/system/scheduler` without bearer token: HTTP 401 JSON,
  proving the new scheduler route is registered.
- FastAPI `GET /health/system/scheduler` with a valid admin bearer token:
  HTTP 200 and safe JSON with `status`, `checked_at`, heartbeat metadata, 24h
  success/failure totals, and scheduled-job summaries.
- Non-admin bearer token for `GET /health/system/scheduler`: HTTP 403.
- `Health systemu` dashboard page loads without traceback; `Runtime po
  restartu`, `Proxy a routovani`, and `Scheduler` blocks all display live data.
- Scheduler block expected values: overall `OK`, `Scheduler bezi` = `ANO`,
  heartbeat age below the configured TTL, zero 24h failures unless a real job
  failed after restart, and 9 scheduled jobs.
- `Health scheduleru` page remains available and displays correctly.
- HTTP hostname route: HTTP 308 to HTTPS.
- HTTPS dashboard: HTTP 200.
- Protected API without bearer token: HTTP 401 JSON.
- Map image without cookie: HTTP 401 JSON.
- Public `/docs`, `/redoc`, and `/openapi.json`: HTTP 404 at Caddy layer.
- Public response security headers present on the local Caddy hostname path:
  HSTS, `nosniff`, `Referrer-Policy`, `X-Frame-Options`,
  `Permissions-Policy`, and CSP report-only; `Server` and `Via` absent.

Required post-restart checks:
- Confirm boot time, scheduled-task last run/result/settings, process tree,
  listeners, and no temporary ports `8010` or `8011`.
- Confirm API live/ready, Streamlit health, Caddy admin health, scheduler
  heartbeat, and current runtime log freshness.
- Confirm scheduler metrics show `scheduler_running=true`, recent
  `last_heartbeat`, and a fresh `quarter_hour_job` observation after boot once
  the next scheduled quarter-hour run has had time to execute.
- Confirm tracked root `Caddyfile` and runtime
  `C:\Program Files\Caddy\Caddyfile` still have matching SHA-256 hashes, then
  validate runtime Caddy config.
- Verify local Caddy hostname routing with SNI/Host routing if direct public
  hostname requests from the workstation still time out.
- Log in to `https://monitoring.armexholding.cz` without printing cookie or
  token values.
- Open `Health systemu` and confirm the `Scheduler` block displays live data
  and no traceback.
- Exercise `GET /health/system/scheduler` through the dashboard/API path and
  check only safe status fields, heartbeat metadata, 24h totals, and job
  summary statuses.
- Re-run targeted tests:
  `.venv\Scripts\python.exe -m pytest tests\test_system_health.py
  tests\test_api_authorization_regression.py
  tests\test_dashboard_navigation_config.py
  tests\test_dashboard_responsive.py -q --tb=short`
- Run `git diff --check` and finish with
  `git status --short --untracked-files=all`.
- Append a dated post-restart verification entry with deviations and accepted
  gaps.

Known risks or accepted gaps:
- Current changes are uncommitted and depend on the working tree being
  preserved across restart.
- The new FastAPI scheduler route will not exist in runtime until the startup
  task has restarted the API process from the current working tree.
- Immediately after boot, `quarter_hour_job` may not yet have a post-boot
  observation until its next scheduled minute runs.
- Direct public hostname reachability from the workstation may still require
  local Caddy Host/SNI verification through loopback.
- The current scheduled-task account remains broader than least privilege.
- The launcher does not independently restart a child process that fails after
  startup.

### 2026-07-07 12:00 +02:00 - Active pre-restart marker

Use the detailed handoff `2026-07-07 11:57 +02:00 - Pre-restart handoff after
monthly_job fix` as the current pre-restart state. It records the active dirty
working tree, the `monthly_job` fix, the pending `Health systemu` scheduler
runtime reload, expected post-restart processes/listeners, sensitive-artifact
constraints, and exact post-restart verification steps.

### 2026-07-07 12:50 +02:00 - Pre-restart handoff after Scheduler Health manual-run guard

Reason for restart:
- Reload FastAPI, Streamlit, scheduler, and Caddy through the normal startup
  task after the post-restart checks and the latest `Health scheduleru` UI
  hardening.
- Activate the new Streamlit `Health scheduleru` manual-run confirmation guard
  in the running dashboard process.

Current task/conversation state:
- Completed: post-restart runtime verification after the `monthly_job` fix and
  `Health systemu` scheduler API work.
- Completed: confirmed FastAPI `/health/system/scheduler` is registered in the
  running API by returning HTTP 401 without bearer token.
- Completed: confirmed scheduler heartbeat after boot and a post-boot
  `quarter_hour_job` success.
- Completed: confirmed the monthly vodomery consumption dataframe for
  reference date `2026-07-07` builds June 2026 aggregates from the measurement
  table with `row_count=58`, `with_consumption=58`, `missing_start=0`, and
  `missing_end=0`.
- Completed: added a `Health scheduleru` UI guard that labels manual-run
  impact and requires an explicit checkbox before running scheduled jobs,
  import/sync/scoring/report/email-like steps, while leaving low-risk checks
  such as `check_database_availability` available without extra confirmation.
- Pending: restart workstation, then verify the updated `Health scheduleru`
  page in an authenticated browser session.
- Pending: only after deliberate operator confirmation, use a low-risk manual
  target such as `check_database_availability` to verify the manual-run
  progress/log panel. Do not run data-changing or email/report jobs casually.
- First action after restart: read `AGENTS.md`, `DECISIONS.md`, and
  `SESSION_NOTES.md`; run `git status --short --untracked-files=all`; then run
  the post-restart checks below.

Working tree and deployment:
- Current time captured before restart: `2026-07-07 12:50:30 +02:00`.
- Branch: `master`.
- `HEAD`: `9e94e13c257a55cda85b61ac259b6bc28580c801`.
- No git commit was created for this handoff.
- `git status --short --untracked-files=all` before this handoff:
  - `M SESSION_NOTES.md`
  - `M moduly/apps/dashboard/api_client.py`
  - `M moduly/apps/dashboard/pages/16_scheduler_health.py`
  - `M moduly/apps/dashboard/pages/37_system_health.py`
  - `M moduly/mereni/vodomery/reporting/monthly_consumption_report.py`
  - `M services/api/routes/system_health.py`
  - `M services/api/schemas/admin.py`
  - `M services/api/services/system_health.py`
  - `M tests/test_api_authorization_regression.py`
  - `M tests/test_system_health.py`
  - `?? moduly/apps/dashboard/scheduler_health_view.py`
  - `?? tests/test_dashboard_scheduler_health_view.py`
  - `?? tests/test_monthly_consumption_report.py`
- Files changed by the latest `Health scheduleru` guard:
  - `moduly/apps/dashboard/pages/16_scheduler_health.py`
  - `moduly/apps/dashboard/scheduler_health_view.py`
  - `tests/test_dashboard_scheduler_health_view.py`
- Files already changed by preceding `Health systemu` scheduler work:
  - `moduly/apps/dashboard/api_client.py`
  - `moduly/apps/dashboard/pages/37_system_health.py`
  - `services/api/routes/system_health.py`
  - `services/api/schemas/admin.py`
  - `services/api/services/system_health.py`
  - `tests/test_api_authorization_regression.py`
  - `tests/test_system_health.py`
  - `SESSION_NOTES.md`
- Files already changed by the monthly-job fix:
  - `moduly/mereni/vodomery/reporting/monthly_consumption_report.py`
  - `tests/test_monthly_consumption_report.py`
- Runtime deployment state: the current running Streamlit process was started
  before the latest `Health scheduleru` guard and may not show the new
  checkbox/impact UI until this restart. The running FastAPI process already
  exposes `/health/system/scheduler`.
- Tracked root `Caddyfile` SHA-256 before restart:
  `08CDF04AFC4F856FEC8DFE4AB2E07A746763B152CA91553E349CCCE8E6D3DF2C`.
- Runtime `C:\Program Files\Caddy\Caddyfile` SHA-256 before restart:
  `08CDF04AFC4F856FEC8DFE4AB2E07A746763B152CA91553E349CCCE8E6D3DF2C`.
- Root/runtime Caddyfile hashes match, and runtime Caddy validation reported
  `Valid configuration`.
- Startup task `API_dashboard_caddy` last ran at `2026-07-07 12:03:40 +02:00`
  with result `0`.
- Existing listener state before restart:
  - Caddy owns TCP `80`, `443`, and `127.0.0.1:2019`, PID `10988`.
  - FastAPI listens on `127.0.0.1:8000`, PID `9988`.
  - Streamlit listens on `127.0.0.1:8001`, PID `10892`.
  - Tailscale owns expected interface-specific `443` listeners, PID `7200`.
  - No listeners are present on temporary ports `8010` or `8011`.
- Runtime health before restart:
  - FastAPI `/health/live`: HTTP 200.
  - FastAPI `/health/ready`: HTTP 200.
  - Streamlit `/_stcore/health`: HTTP 200.
  - Caddy admin `/config/`: HTTP 200.
  - FastAPI `/health/system/scheduler` without bearer token: HTTP 401 JSON.
- Scheduler metrics before restart:
  - `scheduler_running=True`.
  - `last_heartbeat=2026-07-07T12:48:46.140735`.
  - `quarter_hour_job` last run `2026-07-07T12:47:09.002516`, status
    `success`, next run `2026-07-07T13:05:05+02:00`.
  - Metrics currently contain 42 job/internal-step records.

Verification already run:
- `.venv\Scripts\python.exe -m pytest tests\test_monthly_consumption_report.py
  tests\test_scheduler.py::test_monthly_job_calls_all_monthly_reports
  tests\test_system_health.py tests\test_api_authorization_regression.py
  tests\test_dashboard_navigation_config.py tests\test_dashboard_responsive.py
  -q --tb=short` reported `209 passed`.
- `.venv\Scripts\python.exe -m pytest tests\test_dashboard_scheduler_health_view.py
  tests\test_dashboard_scheduler_log_view.py tests\test_scheduler_metrics.py
  tests\test_dashboard_navigation_config.py -q --tb=short` reported
  `38 passed`.
- `.venv\Scripts\python.exe -m py_compile
  moduly\apps\dashboard\scheduler_health_view.py
  moduly\apps\dashboard\pages\16_scheduler_health.py
  tests\test_dashboard_scheduler_health_view.py` passed.
- `.venv-production\Scripts\python.exe -m py_compile
  moduly\apps\dashboard\scheduler_health_view.py
  moduly\apps\dashboard\pages\16_scheduler_health.py` passed.
- Read-only monthly dataframe check for period `2026-06-01T00:00:00` to
  `2026-07-01T00:00:00` returned `row_count=58`, `with_consumption=58`,
  `missing_start=0`, and `missing_end=0`.
- `git diff --check` reported no whitespace errors, only expected LF-to-CRLF
  warnings.

Sensitive/runtime artifacts:
- Do not print, read, delete, revert, stage, or commit raw values from ignored
  local `.env`, dashboard/API tokens, passwords, cookies, authentication audit
  logs, ProgramData security artifacts, local leftover SmartFuelPass session
  JSON files, or protected API response bodies.
- Do not print raw SmartFuelPass portal data, raw device photo filesystem
  paths, process command lines, environment variables, bearer tokens, dashboard
  session cookie values, or raw meter/source rows.
- Do not create a production code-integrity baseline from this dirty working
  tree unless the user explicitly approves that exact state.

Expected processes and listeners after restart:
- Windows Task Scheduler runs `API_dashboard_caddy` at system startup and its
  latest run result becomes `0`.
- One rotating-log wrapper owns one non-reload Uvicorn child on
  `127.0.0.1:8000`.
- One rotating-log wrapper owns one Streamlit child on `127.0.0.1:8001`.
- One scheduler runtime runs `main.py`, holds the `scheduler_process` lock,
  and updates `core/scheduler/logs/scheduler_metrics.json`.
- One Caddy runtime owns TCP `80`/`443` and admin `127.0.0.1:2019`.
- Tailscale interface-specific `443` listeners may remain in addition.
- No listener should remain on temporary ports `8010` or `8011`.

Expected application state after restart:
- FastAPI `/health/live` and `/health/ready`: HTTP 200 while PostgreSQL is
  available.
- Streamlit `/_stcore/health` and Caddy admin endpoint: HTTP 200.
- FastAPI `GET /health/system/runtime`, `/health/system/proxy`, and
  `/health/system/scheduler` without bearer token: HTTP 401 JSON.
- `Health systemu` dashboard page loads without traceback; `Runtime po
  restartu`, `Proxy a routovani`, and `Scheduler` blocks display live data.
- `Health scheduleru` page remains available and the manual-run table includes
  the `dopad` column.
- In `Health scheduleru`, selecting a high-impact target such as a scheduled
  job, report/email step, import/sync/scoring step, or `sync_charge_sessions_to_db`
  displays a warning and keeps `Spustit jednou` disabled until the confirmation
  checkbox is checked.
- In `Health scheduleru`, selecting low-risk `check_database_availability`
  does not require the new confirmation checkbox.
- HTTP hostname route: HTTP 308 to HTTPS.
- HTTPS dashboard through local Caddy hostname/SNI route: HTTP 200.
- Protected API without bearer token: HTTP 401 JSON.
- Map image without cookie: HTTP 401 JSON.
- Public `/docs`, `/redoc`, and `/openapi.json`: HTTP 404 at Caddy layer.
- Public response security headers remain present on the local Caddy hostname
  path: HSTS, `nosniff`, `Referrer-Policy`, `X-Frame-Options`,
  `Permissions-Policy`, and CSP report-only; `Server` and `Via` absent.

Required post-restart checks:
- Confirm boot time, scheduled-task last run/result/settings, process tree,
  listeners, and no temporary ports `8010` or `8011`.
- Confirm API live/ready, Streamlit health, Caddy admin health, scheduler
  heartbeat, and current runtime log freshness.
- Confirm scheduler metrics show `scheduler_running=true`, recent
  `last_heartbeat`, and a fresh `quarter_hour_job` observation after boot once
  the next scheduled quarter-hour run has had time to execute.
- Confirm tracked root `Caddyfile` and runtime
  `C:\Program Files\Caddy\Caddyfile` still have matching SHA-256 hashes, then
  validate runtime Caddy config.
- Verify local Caddy hostname routing with SNI/Host routing if direct public
  hostname requests from the workstation still time out.
- Log in to `https://monitoring.armexholding.cz` without printing cookie or
  token values.
- Open `Health systemu` and confirm the `Scheduler` block displays live data
  and no traceback.
- Open `Health scheduleru` and confirm the new manual-run `dopad` column and
  checkbox behavior for both high-impact and low-risk targets.
- If manually testing the progress/log panel, prefer `check_database_availability`
  and do not run data-changing or email/report targets without explicit
  operator confirmation.
- Re-run targeted tests:
  `.venv\Scripts\python.exe -m pytest tests\test_dashboard_scheduler_health_view.py
  tests\test_dashboard_scheduler_log_view.py tests\test_scheduler_metrics.py
  tests\test_dashboard_navigation_config.py tests\test_monthly_consumption_report.py
  tests\test_scheduler.py::test_monthly_job_calls_all_monthly_reports
  tests\test_system_health.py tests\test_api_authorization_regression.py
  tests\test_dashboard_responsive.py -q --tb=short`
- Run the read-only monthly dataframe check for reference date `2026-07-07`
  and confirm aggregate output remains `row_count=58`,
  `with_consumption=58`, `missing_start=0`, and `missing_end=0` unless new
  data changed since this handoff.
- Run `git diff --check` and finish with
  `git status --short --untracked-files=all`.
- Append a dated post-restart verification entry with deviations and accepted
  gaps.

Known risks or accepted gaps:
- Current changes are uncommitted and depend on the working tree being
  preserved across restart.
- The latest `Health scheduleru` guard will not be visible in the running
  dashboard until Streamlit restarts from the current working tree.
- Immediately after boot, `quarter_hour_job` may not yet have a post-boot
  observation until its next scheduled minute runs.
- Direct public hostname reachability from the workstation may still require
  local Caddy Host/SNI verification through loopback.
- The current scheduled-task account remains broader than least privilege.
- The launcher does not independently restart a child process that fails after
  startup.

### 2026-07-07 13:40 +02:00 - Active pre-restart marker

Use the detailed handoff `2026-07-07 13:38 +02:00 - Pre-restart handoff after
Health systemu PostgreSQL check` as the current pre-restart state. It records
the active dirty working tree, the `Health scheduleru` manual-run confirmation
fix, the new `Health systemu` PostgreSQL check, the current runtime/deployment
state, expected post-restart processes/listeners, sensitive-artifact
constraints, and exact post-restart verification steps.

### 2026-07-07 15:20 +02:00 - Post-restart verification after Health systemu PostgreSQL check

Scope:
- Verified runtime state after workstation restart and activation of
  `GET /health/system/database`.

Verified:
- Current Git state before this note was clean at
  `15ad5df` (`master`, `origin/master`); the dirty working-tree changes from
  the pre-restart handoff were committed before this check.
- Windows boot time was `2026-07-07 13:44:09 +02:00`.
- Startup task `API_dashboard_caddy` last ran at
  `2026-07-07 13:44:18 +02:00` with result `0`.
- Expected listeners were present: Caddy on TCP `80`, `443`, and
  `127.0.0.1:2019`; FastAPI on `127.0.0.1:8000`; Streamlit on
  `127.0.0.1:8001`; Tailscale retained expected interface-specific `443`
  listeners.
- No listeners were present on temporary ports `8010` or `8011`.
- FastAPI `/health/live` and `/health/ready` returned HTTP 200.
- Unauthenticated `/health/system/runtime`, `/health/system/proxy`,
  `/health/system/scheduler`, and `/health/system/database` returned HTTP 401;
  the database route is now registered in the running API.
- Streamlit `/_stcore/health` and Caddy admin `/config/` returned HTTP 200.
- Unauthenticated map-image request returned HTTP 401.
- Scheduler metrics reported `scheduler_running=True`, heartbeat
  `2026-07-07T15:14:24.773694`, `quarter_hour_job` success at
  `2026-07-07T15:05:09.147380`, `failure_count_24h=0`, and
  `success_count_24h=96`.
- Root `Caddyfile` and runtime `C:\Program Files\Caddy\Caddyfile` SHA-256
  hashes matched:
  `08CDF04AFC4F856FEC8DFE4AB2E07A746763B152CA91553E349CCCE8E6D3DF2C`.
- Runtime Caddy validation reported `Valid configuration`.
- Local Caddy hostname/SNI route through `127.0.0.1` returned HTTPS dashboard
  HTTP 200, HTTP-to-HTTPS redirect HTTP 308, `users-exist` HTTP 200,
  protected `/auth/me` HTTP 401, map image without cookie HTTP 401, and
  `/docs`, `/redoc`, `/openapi.json` HTTP 404.
- Public response headers through local Caddy SNI included HSTS, `nosniff`,
  `Referrer-Policy`, `X-Frame-Options`, `Permissions-Policy`, and CSP
  report-only; `Server` and `Via` were absent.
- Direct sanitized PostgreSQL collector returned `status=ok`,
  `connected=True`, `transaction_read_only=False`, latency about `71 ms`, and
  all expected schemas present: `dashboard`, `dbo`, `evidence`, `monitoring`,
  `revize`, and `web_search`.
- Targeted tests passed:
  `.venv\Scripts\python.exe -m pytest tests\test_system_health.py
  tests\test_api_authorization_regression.py
  tests\test_dashboard_navigation_config.py tests\test_dashboard_responsive.py
  tests\test_dashboard_scheduler_health_view.py
  tests\test_dashboard_scheduler_log_view.py tests\test_scheduler_metrics.py
  -q --tb=short` reported `229 passed`.
- `git diff --check` reported no whitespace errors.

Not verified:
- Authenticated browser verification of `Health systemu` and `Health
  scheduleru` pages was not performed in this shell session.
- Admin-token HTTP 200 and non-admin HTTP 403 checks for
  `/health/system/database` were not run because no bearer token was used.
- Direct public hostname requests from this workstation timed out; local Caddy
  hostname/SNI verification through `127.0.0.1` succeeded and was used instead.
- ProgramData API/dashboard/Caddy log files did not receive fresh writes during
  these health checks; process creation times after boot and live health
  endpoints were used as the runtime freshness signal.

Follow-up:
- Continue with the planned SmartFuelPass adjustment after reviewing the
  relevant code path.

### 2026-07-08 08:26 +02:00 - SmartFuelPass Health systemu sync and reporting summary

Scope:
- Added a safe admin-only SmartFuelPass health check for database sync,
  report-period coverage, and scheduler job summaries.

Changed files:
- `services/api/schemas/admin.py`
- `services/api/services/system_health.py`
- `services/api/routes/system_health.py`
- `moduly/apps/dashboard/api_client.py`
- `moduly/apps/dashboard/pages/37_system_health.py`
- `tests/test_system_health.py`
- `tests/test_api_authorization_regression.py`

Implementation notes:
- Added `GET /health/system/smartfuelpass`, protected by admin authentication.
- The service checks `monitoring.smartfuelpass_relace` read-only and returns
  only aggregates: table status, import freshness, session counts, amount
  totals, period summaries, and scheduler metric summaries for SmartFuelPass
  sync/report jobs.
- The dashboard `Health systemu` page now renders the SmartFuelPass block
  instead of listing it under planned controls.
- No raw portal rows, relation identifiers, credentials, tokens, cookies, or
  detailed operational records are exposed.
- Running production services need their normal workstation restart path before
  the new route/page block is available in the live API/dashboard process.

Verified:
- `.venv\Scripts\python.exe -m py_compile services\api\services\system_health.py services\api\routes\system_health.py services\api\schemas\admin.py moduly\apps\dashboard\api_client.py moduly\apps\dashboard\pages\37_system_health.py tests\test_system_health.py tests\test_api_authorization_regression.py`
  passed.
- `.venv-production\Scripts\python.exe -m py_compile services\api\services\system_health.py services\api\routes\system_health.py services\api\schemas\admin.py moduly\apps\dashboard\api_client.py moduly\apps\dashboard\pages\37_system_health.py`
  passed.
- `.venv\Scripts\python.exe -m pytest tests\test_system_health.py tests\test_api_authorization_regression.py tests\test_smartfuelpass_service.py tests\test_smartfuelpass_sync.py -q --tb=short`
  reported `223 passed`.
- `.venv\Scripts\python.exe -m pytest tests\test_dashboard_navigation_config.py tests\test_dashboard_responsive.py -q --tb=short`
  reported `26 passed`.
- `git diff --check` reported no whitespace errors before this note.
- Direct production-environment collector check reported SmartFuelPass
  `status=ok`, table present, 22 total sessions, zero missing UTC end values,
  latest import `2026-07-06 22:17:21.474904`, and both SmartFuelPass scheduler
  metrics in success state.

Not verified:
- Authenticated browser rendering of the new dashboard block was not performed.
- Live HTTP checks for `/health/system/smartfuelpass` were not run because the
  currently running API process has not yet loaded the new route.
- Local `.venv` database configuration did not see the SmartFuelPass table, so
  the production `.venv-production` collector result is the relevant deployment
  signal for this check.

### 2026-07-08 09:00 +02:00 - Pre-restart handoff after SmartFuelPass Health systemu check

Reason for restart:
- Load the new SmartFuelPass `Health systemu` API route and dashboard block
  into the production FastAPI and Streamlit processes through the supported
  workstation restart path.

Current Git state:
- Branch: `master`
- HEAD: `15ad5dfbba631f636b44fc04f9b18c5b16b0ffb1`
- Working tree is intentionally dirty with the current SmartFuelPass health
  changes and session notes:
  - `SESSION_NOTES.md`
  - `moduly/apps/dashboard/api_client.py`
  - `moduly/apps/dashboard/pages/37_system_health.py`
  - `services/api/routes/system_health.py`
  - `services/api/schemas/admin.py`
  - `services/api/services/system_health.py`
  - `tests/test_api_authorization_regression.py`
  - `tests/test_system_health.py`

Completed before restart:
- Added admin-only `GET /health/system/smartfuelpass`.
- Added read-only SmartFuelPass health collection for database sync status,
  report-period summaries, import freshness, and scheduler metrics.
- Added the SmartFuelPass block to the Streamlit `Health systemu` page.
- Updated API client and authorization/system-health tests.
- Kept `main.py` unchanged; scheduler startup remains through the existing
  entry point and central scheduler wiring.

Verification before restart:
- `.venv\Scripts\python.exe -m py_compile services\api\services\system_health.py services\api\routes\system_health.py services\api\schemas\admin.py moduly\apps\dashboard\api_client.py moduly\apps\dashboard\pages\37_system_health.py tests\test_system_health.py tests\test_api_authorization_regression.py`
  passed.
- `.venv-production\Scripts\python.exe -m py_compile services\api\services\system_health.py services\api\routes\system_health.py services\api\schemas\admin.py moduly\apps\dashboard\api_client.py moduly\apps\dashboard\pages\37_system_health.py`
  passed.
- `.venv\Scripts\python.exe -m pytest tests\test_system_health.py tests\test_api_authorization_regression.py tests\test_smartfuelpass_service.py tests\test_smartfuelpass_sync.py -q --tb=short`
  reported `223 passed`.
- `.venv\Scripts\python.exe -m pytest tests\test_dashboard_navigation_config.py tests\test_dashboard_responsive.py -q --tb=short`
  reported `26 passed`.
- `git diff --check` reported no whitespace errors, with only expected LF/CRLF
  warnings.
- Direct `.venv-production` SmartFuelPass collector check reported
  `status=ok`, table present, `22` total sessions, `0` missing UTC end values,
  latest import `2026-07-06 22:17:21.474904`, sync metric `ok:success`,
  weekly report metric `ok:success`, and period counts:
  last completed week `0`, current month `1`, previous month `4`, total `22`.

Runtime state before restart:
- Windows boot time: `2026-07-07 13:44:09 +02:00`.
- Startup task `API_dashboard_caddy` state `Ready`, last run
  `2026-07-07 13:44:18 +02:00`, last result `0`.
- Expected listeners were present:
  - Caddy public listeners on TCP `80` and `443` owned by PID `11596`.
  - Caddy admin on `127.0.0.1:2019` owned by PID `11596`.
  - FastAPI on `127.0.0.1:8000` owned by PID `9352`.
  - Streamlit on `127.0.0.1:8001` owned by PID `11200`.
  - Tailscale retained interface-specific TCP `443` listeners owned by
    PID `7064`.
- No listeners were present on temporary ports `8010` or `8011`.
- Caddy PID `11596` was visible with creation time
  `2026-07-07 13:44:30 +02:00`. Windows did not expose API/Streamlit process
  paths or start times from this session, so listener ownership is the recorded
  process evidence for those services.
- FastAPI `/health/live` and `/health/ready` returned HTTP `200`.
- Streamlit `/_stcore/health` returned HTTP `200`.
- Caddy admin `/config/` returned HTTP `200`.
- Unauthenticated `/health/system/smartfuelpass` on the currently running API
  returned HTTP `404`, as expected before the process has loaded the new route.
- Scheduler metrics reported `scheduler_running=True`, heartbeat
  `2026-07-08T08:54:30.618706`, `quarter_hour_job` success at
  `2026-07-08T08:47:08.950298`, next run `2026-07-08T09:05:05+02:00`,
  `failure_count_24h=0`, and `success_count_24h=96`.
- SmartFuelPass sync scheduler metric reported success at
  `2026-07-08T00:17:25.861323`, duration `129.71` seconds,
  `success_count_24h=1`, and `failure_count_24h=0`.
- SmartFuelPass weekly report metric reported success at
  `2026-07-07T06:55:09.631677`, next run
  `2026-07-14T06:55:05+02:00`, and `failure_count_24h=0`.

Sensitive-artifact constraints:
- Do not read or print SmartFuelPass cookie/session JSON payloads.
- Do not print `.env` values, ProgramData credential files, bearer tokens,
  cookie values, portal credentials, raw portal rows, raw relation identifiers,
  or raw device photo paths.
- The SmartFuelPass health check must remain aggregate-only.

Expected post-restart processes and listeners:
- Startup task `API_dashboard_caddy` should run after boot and return result
  `0`.
- Scheduler process should start from `main.py`.
- FastAPI should listen on `127.0.0.1:8000`.
- Streamlit should listen on `127.0.0.1:8001`.
- Caddy should listen on TCP `80`, TCP `443`, and admin
  `127.0.0.1:2019`.
- Temporary ports `8010` and `8011` should remain unused.
- Tailscale may still own interface-specific TCP `443` listeners.

Required post-restart checks:
- Confirm Windows boot time, scheduled-task state, last run/result, relevant
  processes, expected listeners, and absence of temporary listeners.
- Confirm FastAPI `/health/live` and `/health/ready`, Streamlit
  `/_stcore/health`, and Caddy admin `/config/` return HTTP `200`.
- Confirm unauthenticated `/health/system/runtime`, `/health/system/proxy`,
  `/health/system/scheduler`, `/health/system/database`, and
  `/health/system/smartfuelpass` return HTTP `401`. The SmartFuelPass route
  returning `401` instead of the pre-restart `404` is the route-registration
  signal.
- Confirm unauthenticated map image access still returns HTTP `401`.
- Confirm local Caddy routing for `https://monitoring.armexholding.cz`:
  dashboard HTTP `200`, HTTP-to-HTTPS redirect HTTP `308`, `users-exist`
  HTTP `200`, protected `/auth/me` HTTP `401`, and `/docs`, `/redoc`,
  `/openapi.json` HTTP `404`. If direct public hostname requests time out from
  the workstation, use local Caddy Host/SNI verification through loopback.
- Confirm public response headers still include HSTS, `nosniff`,
  `Referrer-Policy`, `X-Frame-Options`, `Permissions-Policy`, and CSP
  report-only, with `Server` and `Via` absent.
- Confirm root `Caddyfile` and runtime
  `C:\Program Files\Caddy\Caddyfile` still have matching SHA-256 hashes, then
  validate the runtime Caddy configuration.
- Confirm scheduler metrics show `scheduler_running=True`, a post-boot
  heartbeat, and a fresh `quarter_hour_job` observation after the next
  scheduled quarter-hour slot has run.
- Run the `.venv-production` SmartFuelPass collector check again and expect
  `status=ok`, table present, sync/report metrics in success state, and safe
  aggregate period counts. Counts may change if a new sync runs before the
  check.
- Log in to `https://monitoring.armexholding.cz` without printing cookie or
  token values, open `Health systemu`, and confirm the SmartFuelPass block
  renders without traceback and exposes only aggregate data.
- Re-run targeted tests:
  `.venv\Scripts\python.exe -m pytest tests\test_system_health.py tests\test_api_authorization_regression.py tests\test_smartfuelpass_service.py tests\test_smartfuelpass_sync.py tests\test_dashboard_navigation_config.py tests\test_dashboard_responsive.py -q --tb=short`
- Run `git diff --check` and finish with
  `git status --short --untracked-files=all`.
- Append a dated post-restart verification entry with deviations and accepted
  gaps.

Known risks or accepted gaps:
- The current SmartFuelPass health changes are uncommitted and depend on the
  dirty working tree being preserved across restart.
- Live SmartFuelPass route registration and authenticated browser rendering are
  not verified until after restart.
- Local `.venv` database configuration did not see the SmartFuelPass table;
  `.venv-production` is the relevant deployment signal for this check.
- Immediately after boot, `quarter_hour_job` may not yet have a post-boot
  observation until its next scheduled minute runs.
- The scheduled task starts the process set but does not supervise later child
  process exits; recovery remains the supported full-workstation restart path.

### 2026-07-10 08:14 +02:00 - Post-restart verification and manual weekly rebuild

Scope:
- Verified runtime state after the 2026-07-09 workstation restart.
- Confirmed the SmartFuelPass `Health systemu` route is loaded in the running
  API process.
- Manually ran `weekly_job` from `.venv-production` with the scheduler manual
  run wrapper so weekly rebuild profiles and email reports were sent.

Changed:
- Added this session note only.

Verified:
- `git status --short` was clean before operational checks.
- Windows boot time was `2026-07-09 15:57:57 +02:00`.
- Startup task `API_dashboard_caddy` last ran at
  `2026-07-09 15:58:06 +02:00` with result `0`.
- Expected listeners were present: Caddy on TCP `80`, `443`, and
  `127.0.0.1:2019`; FastAPI on `127.0.0.1:8000`; Streamlit on
  `127.0.0.1:8001`; Tailscale retained interface-specific TCP `443`
  listeners. No listeners were present on temporary ports `8010` or `8011`.
- FastAPI `/health/live` and `/health/ready`, Streamlit `/_stcore/health`,
  and Caddy admin `/config/` returned HTTP `200`.
- Unauthenticated `/health/system/runtime`, `/health/system/proxy`,
  `/health/system/scheduler`, `/health/system/database`,
  `/health/system/smartfuelpass`, and map-image access returned HTTP `401`.
- Local Caddy Host/SNI route through `127.0.0.1` returned HTTPS dashboard
  HTTP `200`, HTTP-to-HTTPS redirect HTTP `308`, `users-exist` HTTP `200`,
  protected `/auth/me` HTTP `401`, map image without cookie HTTP `401`, and
  `/docs`, `/redoc`, `/openapi.json` HTTP `404`.
- Public response headers through the local Caddy Host/SNI route included
  HSTS, `nosniff`, `Referrer-Policy`, `X-Frame-Options`,
  `Permissions-Policy`, and CSP report-only; `Server` and `Via` were absent.
- Root `Caddyfile` and runtime `C:\Program Files\Caddy\Caddyfile` SHA-256
  hashes matched:
  `08CDF04AFC4F856FEC8DFE4AB2E07A746763B152CA91553E349CCCE8E6D3DF2C`.
- Runtime Caddy validation reported `Valid configuration`.
- Scheduler metrics showed `scheduler_running=True`, heartbeat
  `2026-07-10T07:43:17.338050`, and a post-boot `quarter_hour_job` success at
  `2026-07-10T07:47:09.856475` with `failure_count_24h=0`.
- Direct production-environment database collector reported PostgreSQL
  `status=ok`, `connected=True`, `transaction_read_only=False`, latency about
  `1.5 ms`, and expected schemas `dashboard`, `dbo`, `evidence`,
  `monitoring`, `revize`, and `web_search` present.
- SmartFuelPass collector route was registered and callable. Its scheduler
  sync/report metrics were `ok`, daily sync last ran successfully at
  `2026-07-10T00:17:20.377435`, weekly report last ran successfully at
  `2026-07-07T06:55:09.631677`, table existed with `22` total sessions and
  `0` missing UTC end values.
- SmartFuelPass collector overall status was `degraded` because table
  `last_imported_at` was still `2026-07-06T22:17:21.474904`.
- Manual `weekly_job` started at `2026-07-10 06:50:07 +02:00` and completed
  with `JOB MANUAL SUCCESS` at `2026-07-10 07:03:24 +02:00`, duration
  `796.27` seconds.
- Manual `weekly_job` log showed successful runtime/database preflight,
  vodomery rebuild, plynomery rebuild, vodomery model rebuild email,
  plynomery model rebuild email, weekly vodomery branch email, weekly
  vodomery billing summary email, weekly elektromery branch email, and weekly
  new elektromery email.
- Database checks after the manual rebuild showed vodomery selection run `32`
  with active Model 3, 37,800 profiles for each vodomery model version 1-5,
  and active vodomery selected-model snapshots for 58 identifiers. Plynomery
  selection run `13` selected Model 2 and had 3,360 profiles for Model 2.
- Targeted tests passed:
  `.venv\Scripts\python.exe -m pytest tests\test_system_health.py
  tests\test_api_authorization_regression.py tests\test_smartfuelpass_service.py
  tests\test_smartfuelpass_sync.py tests\test_dashboard_navigation_config.py
  tests\test_dashboard_responsive.py -q --tb=short` reported `249 passed`.
- `git diff --check` reported no whitespace errors.

Not verified:
- Authenticated browser rendering of `Health systemu` was not performed in this
  shell session.
- Direct public hostname routing from outside the workstation was not tested;
  local Caddy Host/SNI verification through `127.0.0.1` was used.
- Scheduler metrics JSON did not retain the manual `weekly_job` run from the
  one-off shell process because the running scheduler process later rewrote the
  file from its in-memory metrics. `scheduler.log` and database rows are the
  retained evidence for this manual run.

Follow-up:
- Consider making scheduler metrics writes merge-safe across processes if
  manual one-off runs must remain visible in `Health scheduleru` metrics after
  the main scheduler heartbeat rewrites the metrics file.

### 2026-07-10 - Shared prediction core step 14

Scope:
- Completed step 14 of the shared prediction core plan.

Changed:
- Added shared forecast-period helpers in `moduly/mereni/prediction/periods.py`
  for weekly and monthly cadence, including next-month monthly forecast
  periods.
- Generalized rolling backtest fold generation and runner in
  `moduly/mereni/prediction/backtest.py` so shared code supports weekly and
  monthly validation periods.
- Kept existing weekly backtest helpers as compatibility wrappers.
- Wired vodomery weekly forecast-period construction through the shared helper
  without changing its period length or label format.
- Added tests for monthly forecast periods, calendar-month rolling folds, and
  the generic monthly rolling backtest runner.
- Marked checklist step 14 complete.

Verified:
- `.venv\Scripts\python.exe -m py_compile moduly\mereni\prediction\contracts.py
  moduly\mereni\prediction\periods.py moduly\mereni\prediction\backtest.py
  moduly\mereni\prediction\__init__.py
  moduly\mereni\vodomery\vodomery_prediction.py
  tests\test_prediction_backtest.py tests\test_prediction_contracts.py
  tests\test_vodomery_prediction.py` passed.
- `.venv\Scripts\python.exe -m pytest tests\test_prediction_contracts.py
  tests\test_prediction_backtest.py tests\test_prediction_storage.py
  tests\test_vodomery_prediction.py tests\test_vodomery_prediction_adapter.py
  -q --tb=short` reported `56 passed`.
- `.venv\Scripts\python.exe -m pytest
  tests\test_scheduler.py::test_weekly_job_rebuilds_profiles_and_sends_report
  tests\test_vodomery_model_rebuild_report.py -q --tb=short` reported
  `2 passed`.

Not verified:
- No live database rebuild or scheduler manual run was executed for this step;
  the change is shared-period/backtest plumbing and keeps vodomery production
  weekly behavior covered by unit tests.

Follow-up:
- Continue with step 15: extract a reusable media pipeline runner so candidate
  registration and adapter metadata drive future models and parameter variants.

### 2026-07-10 - Shared prediction core step 15

Scope:
- Completed step 15 of the shared prediction core plan.

Changed:
- Added `moduly/mereni/prediction/pipeline.py` with shared pipeline settings,
  a validated candidate plugin registry, rebuild-window construction, forecast
  period delegation, and candidate selection rules.
- Exported the shared pipeline runner and helpers from
  `moduly/mereni/prediction/__init__.py`.
- Rewired vodomery candidate metadata, rebuild-window calculation, forecast
  period construction, global candidate selection, and rolling-backtest profile
  dispatch through the shared runner/registry.
- Kept existing vodomery scheduler/report entry points and return payloads
  compatible; model-specific profile construction remains in vodomery helper
  functions registered as plugin callbacks.
- Added `tests/test_prediction_pipeline.py` for registry validation, runner
  metadata behavior, rebuild-window validation, and shared candidate selection.
- Marked checklist step 15 complete.

Verified:
- `.venv\Scripts\python.exe -m py_compile moduly\mereni\prediction\contracts.py
  moduly\mereni\prediction\periods.py moduly\mereni\prediction\backtest.py
  moduly\mereni\prediction\pipeline.py moduly\mereni\prediction\__init__.py
  moduly\mereni\vodomery\vodomery_prediction.py
  tests\test_prediction_pipeline.py tests\test_vodomery_prediction.py` passed.
- `.venv\Scripts\python.exe -m pytest tests\test_prediction_pipeline.py
  tests\test_prediction_contracts.py tests\test_prediction_backtest.py
  tests\test_prediction_storage.py tests\test_vodomery_prediction.py
  tests\test_vodomery_prediction_adapter.py -q --tb=short` reported
  `61 passed`.
- `.venv\Scripts\python.exe -m pytest
  tests\test_scheduler.py::test_weekly_job_rebuilds_profiles_and_sends_report
  tests\test_vodomery_model_rebuild_report.py -q --tb=short` reported
  `2 passed`.
- `git diff --check` reported no whitespace errors beyond existing LF/CRLF
  normalization warnings.

Not verified:
- No live database rebuild or scheduler manual run was executed for this step;
  the change is shared pipeline plumbing and preserves the existing vodomery
  weekly rebuild/report surface in unit tests.

Follow-up:
- Continue with step 16: adapt the shared prediction pipeline to `plynomery`
  while preserving current gas-specific behavior.

### 2026-07-10 - Shared prediction core step 16

Scope:
- Completed step 16 of the shared prediction core plan.

Changed:
- Added shared pipeline metadata to `moduly/mereni/plynomery/plynomery_prediction.py`
  for the gas medium, including stable candidate specs for the exact/fallback
  baseline and weather-adjusted baseline models.
- Rewired plynomery rebuild windows, global candidate selection, single-model
  rebuild dispatch, and candidate model metadata through the shared prediction
  runner/registry while preserving existing report payload shape.
- Added `moduly/mereni/plynomery/prediction_adapter.py` with gas observation
  loading metadata, selection metadata serialization, active model lookup, and
  baseline profile row mapping using the existing plynomery quality filters.
- Kept `plynomery_anomaly.py`, expected-zero tables, outlier event logic, and
  outlier review rebuild/apply behavior unchanged.
- Added tests for plynomery shared candidate specs and adapter behavior.
- Marked checklist step 16 complete.

Verified:
- `.venv\Scripts\python.exe -m py_compile moduly\mereni\prediction\pipeline.py
  moduly\mereni\prediction\__init__.py
  moduly\mereni\plynomery\plynomery_prediction.py
  moduly\mereni\plynomery\prediction_adapter.py
  tests\test_plynomery_prediction.py
  tests\test_plynomery_prediction_adapter.py` passed.
- `.venv\Scripts\python.exe -m pytest tests\test_plynomery_prediction.py
  tests\test_plynomery_prediction_adapter.py tests\test_plynomery_db_import.py
  tests\test_plynomery_outlier_review_apply.py
  tests\test_plynomery_alert_rule_validation.py
  tests\test_plynomery_outlier_notifications.py -q --tb=short` reported
  `29 passed`.
- `.venv\Scripts\python.exe -m pytest tests\test_prediction_pipeline.py
  tests\test_prediction_contracts.py tests\test_prediction_backtest.py
  tests\test_prediction_storage.py -q --tb=short` reported `35 passed`.
- `.venv\Scripts\python.exe -m pytest
  tests\test_scheduler.py::test_weekly_job_rebuilds_profiles_and_sends_report
  tests\test_vodomery_model_rebuild_report.py -q --tb=short` reported
  `2 passed`.
- `git diff --check` reported no whitespace errors beyond existing LF/CRLF
  normalization warnings.

Not verified:
- No live database rebuild, manual scheduler run, or workstation restart was
  executed for this step. The user explicitly chose to defer restart and live
  rebuild checks until after step 16; those checks still need a pre-restart
  handoff before execution.

Follow-up:
- Prepare the agreed restart handoff and then perform post-restart/runtime
  verification plus any approved manual rebuild/scheduler run before moving to
  step 17.

### 2026-07-10 11:13 +02:00 - Pre-restart handoff after prediction steps 14-16

Reason for restart:
- Load the shared prediction pipeline changes from steps 14-16 into the
  production FastAPI, Streamlit, and scheduler processes through the supported
  full-workstation restart path.
- After restart, verify runtime health and run the agreed testrun before
  continuing to checklist step 17.

Current task/conversation state:
- Completed: shared prediction checklist steps 14, 15, and 16.
- Completed: vodomery forecast-period/backtest generalization, reusable
  prediction pipeline runner/registry, and plynomery integration with shared
  candidate metadata/adapter.
- Pending: workstation restart, post-restart runtime checks, and testrun.
- First action after restart: confirm startup task/process/listener health,
  then run targeted prediction/plynomery tests and the agreed scheduler/rebuild
  testrun if runtime checks pass.

Working tree and deployment:
- Branch: `master`
- HEAD: `8a9b2e2e96b553b107864e9199172dbfd5363b80`
- `git status --short --untracked-files=all` before restart:

```text
 M SESSION_NOTES.md
 M moduly/mereni/plynomery/plynomery_prediction.py
 M moduly/mereni/prediction/__init__.py
 M moduly/mereni/prediction/backtest.py
 M moduly/mereni/vodomery/vodomery_prediction.py
 M tests/test_plynomery_prediction.py
 M tests/test_prediction_backtest.py
?? moduly/mereni/plynomery/prediction_adapter.py
?? moduly/mereni/prediction/periods.py
?? moduly/mereni/prediction/pipeline.py
?? tests/test_plynomery_prediction_adapter.py
?? tests/test_prediction_pipeline.py
```

- `main.py` is unchanged.
- No Caddy configuration changes were made in steps 14-16.
- Running production processes have not yet loaded these prediction changes.
  Restart should load the current dirty working tree into the process set.
- Current pre-restart runtime snapshot:
  - Windows boot time: `2026-07-09 15:57:57 +02:00`.
  - Startup task `API_dashboard_caddy`: state `Ready`, last run
    `2026-07-09 15:58:06 +02:00`, last result `0`.
  - Expected listeners present before restart: Caddy on TCP `80`, `443`, and
    `127.0.0.1:2019`; FastAPI on `127.0.0.1:8000`; Streamlit on
    `127.0.0.1:8001`; Tailscale retained interface-specific TCP `443`
    listeners.
  - Temporary ports `8010` and `8011` were not listening.

Sensitive/runtime artifacts:
- Do not print, read, modify, delete, or commit `.env` values, ProgramData
  credential files, bearer tokens, cookie values, SmartFuelPass session JSON
  payloads, raw portal rows, raw meter rows, raw device photo paths, or
  production credentials.
- Scheduler lock files under `core/scheduler/locks` are tracked runtime
  artifacts; do not delete or rewrite them as part of restart verification.

Expected processes after restart:
- FastAPI/Uvicorn: one runtime on `127.0.0.1:8000`.
- Streamlit: one runtime on `127.0.0.1:8001`.
- Scheduler: one `main.py` runtime holding the scheduler process role.
- Caddy: one runtime owning TCP `80`, TCP `443`, and admin
  `127.0.0.1:2019`.
- Temporary ports `8010` and `8011` should remain unused.
- Tailscale may retain interface-specific TCP `443` listeners.

Expected application state:
- FastAPI `/health/live` and `/health/ready`: HTTP `200`.
- Streamlit `/_stcore/health`: HTTP `200`.
- Caddy admin `/config/`: HTTP `200`.
- Public dashboard via local Caddy Host/SNI route: HTTPS dashboard HTTP `200`.
- HTTP to HTTPS redirect: HTTP `308`.
- `/api/v1/auth/users-exist`: HTTP `200`.
- Protected API without bearer token: HTTP `401` JSON.
- `/docs`, `/redoc`, and `/openapi.json`: HTTP `404` at Caddy layer.
- Scheduler metrics should show `scheduler_running=True`, a post-boot
  heartbeat, and a post-boot `quarter_hour_job` observation after the next
  scheduled slot.

Required post-restart checks:
- Confirm Windows boot time is after this handoff and startup task
  `API_dashboard_caddy` last result is `0`.
- Confirm expected listeners and absence of temporary listeners.
- Confirm FastAPI, Streamlit, and Caddy local health endpoints.
- Confirm unauthenticated protected health/admin routes still return `401`.
- Confirm local Caddy routing and public response headers; `Server` and `Via`
  should remain absent.
- Confirm root `Caddyfile` and runtime `C:\Program Files\Caddy\Caddyfile`
  hashes still match, then validate the runtime Caddy configuration.
- Confirm scheduler heartbeat and a fresh post-boot `quarter_hour_job`
  observation.
- Run targeted code verification:
  `.venv\Scripts\python.exe -m py_compile moduly\mereni\prediction\contracts.py
  moduly\mereni\prediction\periods.py moduly\mereni\prediction\backtest.py
  moduly\mereni\prediction\pipeline.py moduly\mereni\prediction\__init__.py
  moduly\mereni\vodomery\vodomery_prediction.py
  moduly\mereni\plynomery\plynomery_prediction.py
  moduly\mereni\plynomery\prediction_adapter.py
  tests\test_prediction_pipeline.py tests\test_prediction_backtest.py
  tests\test_plynomery_prediction.py tests\test_plynomery_prediction_adapter.py`
- Run targeted tests:
  `.venv\Scripts\python.exe -m pytest tests\test_prediction_pipeline.py
  tests\test_prediction_contracts.py tests\test_prediction_backtest.py
  tests\test_prediction_storage.py tests\test_vodomery_prediction.py
  tests\test_vodomery_prediction_adapter.py
  tests\test_plynomery_prediction.py tests\test_plynomery_prediction_adapter.py
  tests\test_plynomery_db_import.py tests\test_plynomery_outlier_review_apply.py
  tests\test_plynomery_alert_rule_validation.py
  tests\test_plynomery_outlier_notifications.py -q --tb=short`
- Run scheduler/report smoke:
  `.venv\Scripts\python.exe -m pytest
  tests\test_scheduler.py::test_weekly_job_rebuilds_profiles_and_sends_report
  tests\test_vodomery_model_rebuild_report.py -q --tb=short`
- Run the agreed testrun only after runtime checks pass. If it is the manual
  scheduler/rebuild testrun, run it from `.venv-production` through the
  scheduler manual-run wrapper and expect configured report emails to be sent.
- After testrun, verify database evidence for latest vodomery and plynomery
  selection runs/profile counts without printing raw measurement data.
- Finish with `git diff --check` and
  `git status --short --untracked-files=all`.
- Append a dated post-restart verification entry with results, deviations, and
  accepted gaps.

Known risks or accepted gaps:
- The process set will load uncommitted working-tree changes. This is intended
  for the agreed post-step-16 runtime testrun.
- If a scheduled production job runs before manual verification, it may use the
  new prediction code after restart.
- `git diff --check` before restart reported only LF/CRLF normalization
  warnings, not whitespace errors.
- Immediately after boot, scheduler metrics may not yet contain a post-boot
  `quarter_hour_job` observation until the next scheduled slot.
- The startup task starts the process set but does not supervise later child
  process exits; recovery remains full-workstation restart.

### 2026-07-10 11:40 +02:00 - Post-restart runtime verification after prediction steps 14-16

Scope:
- Checked workstation and application runtime state after the restart requested
  in the 2026-07-10 11:13 pre-restart handoff.
- Ran the targeted code and test verification listed in the handoff.

Changed:
- Added this session note only.

Verified:
- Windows boot time was `2026-07-10 11:16:54 +02:00`.
- Startup task `API_dashboard_caddy` last ran at
  `2026-07-10 11:17:04 +02:00` with result `0`.
- Expected listeners were present: Caddy on TCP `80`, `443`, and
  `127.0.0.1:2019`; FastAPI on `127.0.0.1:8000`; Streamlit on
  `127.0.0.1:8001`; Tailscale retained interface-specific TCP `443`
  listeners. Temporary ports `8010` and `8011` were not listening.
- FastAPI `/health/live` and `/health/ready`, Streamlit `/_stcore/health`,
  and Caddy admin `/config/` returned HTTP `200`.
- Unauthenticated system-health routes returned HTTP `401`.
- Local Caddy Host/SNI route returned HTTPS dashboard HTTP `200`,
  HTTP-to-HTTPS redirect HTTP `308`, `users-exist` HTTP `200`,
  protected `/auth/me` HTTP `401`, map image without cookie HTTP `401`, and
  `/docs`, `/redoc`, `/openapi.json` HTTP `404`.
- Public response headers through the local Caddy Host/SNI route included
  HSTS, `nosniff`, `Referrer-Policy`, `X-Frame-Options`,
  `Permissions-Policy`, and CSP report-only; `Server` and `Via` were absent.
- Root `Caddyfile` and runtime `C:\Program Files\Caddy\Caddyfile` SHA-256
  hashes matched:
  `08CDF04AFC4F856FEC8DFE4AB2E07A746763B152CA91553E349CCCE8E6D3DF2C`.
- Runtime Caddy validation reported `Valid configuration`.
- Scheduler metrics showed `scheduler_running=True`, heartbeat
  `2026-07-10T11:32:10.706143`, and a post-boot `quarter_hour_job` success at
  `2026-07-10T11:35:10.531349` with `failure_count_24h=0`.
- Targeted `py_compile` for prediction/vodomery/plynomery modules and related
  tests passed.
- Targeted prediction and plynomery pytest suite reported `90 passed`.
- Scheduler/report smoke tests reported `2 passed`.
- `git diff --check` reported no whitespace errors beyond existing LF/CRLF
  normalization warnings.

Not verified:
- Manual production scheduler/rebuild testrun was not run in this check.
- Database evidence for a new manual rebuild was not checked because no manual
  rebuild was started.
- Direct public hostname routing from outside the workstation was not tested;
  local Caddy Host/SNI verification through `127.0.0.1` was used.

Follow-up:
- Continue with the next agreed step only after deciding whether to run the
  manual production scheduler/rebuild testrun that sends configured reports.

### 2026-07-10 12:21 +02:00 - Manual weekly rebuild testrun after prediction steps 14-16

Scope:
- Ran the agreed manual production `weekly_job` rebuild/test run from
  `.venv-production` before moving to prediction checklist step 17.
- Verified scheduler log, runtime health, and aggregate database evidence
  without printing raw measurements or per-device identifiers.

Changed:
- Added this session note only.
- Production database state changed through the intended manual rebuild:
  vodomery and plynomery model selection/profile tables were refreshed and
  configured weekly/model report emails were sent.

Verified:
- Manual `weekly_job` started at `2026-07-10 11:53:37 +02:00` and completed
  with `JOB MANUAL SUCCESS` at `2026-07-10 12:07:12 +02:00`, duration
  `814.35` seconds.
- Runtime/database preflight succeeded before the rebuild.
- Vodomery rebuild completed with `selection_run_id=33` and global active
  `Model 3 - recency weighted blend`.
- Plynomery rebuild completed with `selection_run_id=14` and active
  `Model 2 - weather adjusted baseline`.
- Scheduler log showed successful completion of vodomery rebuild, plynomery
  rebuild, vodomery model rebuild report, plynomery model rebuild report,
  weekly vodomery branch report, weekly vodomery billing summary report,
  weekly elektromery branch report, and weekly new elektromery report.
- Vodomery database aggregate checks after the run:
  - 37,800 anomaly-profile rows for each vodomery model version 1-5.
  - 58 identifiers covered by each vodomery model version.
  - Active selected-model snapshots: 58 total for the new weekly forecast
    period, 55 without fallback and 3 with `no_identifier_metrics` fallback.
  - Active selected-model distribution: 43 snapshots use Model 2 and
    15 snapshots use Model 3.
  - 43 active snapshots differ from the global active Model 3, confirming
    per-identifier selection is active in the rebuild output.
  - Measured-only candidates were evaluated but not selected for production
    snapshots; per-identifier best counts included Model 4 for 6 identifiers
    and Model 5 for 17 identifiers.
- Vodomery rolling WAPE by candidate in this run:
  - Model 1: `11.252027`
  - Model 2: `11.127486`
  - Model 3: `3.9993`
  - Model 4 measured-only: `8.329386`
  - Model 5 measured-only: `26.829175`
- Plynomery database aggregate checks after the run:
  - Model 1 baseline candidate had 3,360 profiles for 5 identifiers.
  - Model 2 weather-adjusted candidate had 3,360 profiles for 5 identifiers
    and was selected.
  - Model 2 had lower MAE/RMSE/bias than Model 1 in the latest selection run.
- Runtime health after the rebuild remained OK: FastAPI `/health/live` and
  `/health/ready`, Streamlit `/_stcore/health`, and Caddy admin `/config/`
  returned HTTP `200`.
- Scheduler metrics still showed `scheduler_running=True`; `quarter_hour_job`
  last succeeded at `2026-07-10T12:16:09.538693`.

Not verified:
- The wrapper shell command returned exit code `1` after the successful job
  because the inline Python expression incorrectly attempted to `raise` the
  return value of `_run_manual_job_worker`. The scheduler job itself was not
  rerun, because the log already contained `JOB MANUAL SUCCESS` and rerunning
  would resend reports.
- Scheduler metrics JSON did not retain the manual `weekly_job` result from
  the one-off shell process after the main scheduler rewrote metrics from its
  in-memory state. `scheduler.log` and database rows are the retained evidence.
- Authenticated browser rendering of report/status pages was not checked.
- Direct public hostname routing from outside the workstation was not tested.

Follow-up:
- Continue with checklist step 17 for elektromery monthly next-month
  prediction candidates after reviewing electricity source cadence, calendar
  and tariff behavior, imports, and reporting semantics.

### 2026-07-10 12:49 +02:00 - SmartFuelPass health freshness investigation

Scope:
- Investigated why `Health systemu / SmartFuelPass` showed the last import as
  about three days old before starting prediction checklist step 17.
- Checked code wiring, scheduler metrics/logs, aggregate PostgreSQL state, and
  a read-only live SmartFuelPass portal fetch without printing raw relace
  identifiers, cookies, credentials, or portal rows.

Changed:
- Updated `services/api/services/system_health.py` so stale
  `MAX(imported_at)` does not degrade the SmartFuelPass health table when the
  scheduler sync job ran successfully within the expected daily window.
- Updated `moduly/apps/dashboard/pages/37_system_health.py` so the primary
  metric says `Posledni sync` and uses `sync_job.last_run`; the table
  `last_imported_at` remains visible as the latest newly inserted DB import.
- Added a regression test for the case where no new SmartFuelPass sessions were
  inserted recently but the daily sync completed successfully.

Verified:
- Scheduler metrics showed `daily_job` success at
  `2026-07-10T00:17:21.125356` and `sync_charge_sessions_to_db` success at
  `2026-07-10T00:17:20.377435`, with no failures in the last 24 hours.
- Scheduler log showed `sync_charge_sessions_to_db` started at
  `2026-07-10 00:15:16 +02:00` and completed at
  `2026-07-10 00:17:20 +02:00`, duration `124.11` seconds.
- PostgreSQL aggregate checks showed `monitoring.smartfuelpass_relace` had
  22 rows, all with normalized UTC end timestamps, last completed relace at
  `2026-07-06 17:02:00`, and `MAX(imported_at)` at
  `2026-07-06 22:17:21.474904`.
- Corrected recent-window aggregate checks showed 0 completed relace in the
  last 1 and 3 days, 1 in the last 7 days, and 5 in the last 30 days.
- Read-only live portal fetch returned 5 completed relace, with latest
  completed end time `2026-07-06 17:02:00`, matching the DB aggregate.
- Direct `.venv-production` collector call after the code change returned
  SmartFuelPass `status=ok`, table `status=ok`, sync `status=ok`, and the
  detail that no newly inserted sessions were recorded recently while the
  scheduler sync ran successfully within the daily window.
- `.venv\Scripts\python.exe -m py_compile services\api\services\system_health.py
  moduly\apps\dashboard\pages\37_system_health.py tests\test_system_health.py`
  passed.
- `.venv\Scripts\python.exe -m pytest tests\test_system_health.py
  tests\test_api_authorization_regression.py -q --tb=short` reported
  `194 passed`.

Not verified:
- The running FastAPI/Streamlit production processes have not loaded this code
  change yet. The dashboard will keep showing the old SmartFuelPass health
  interpretation until the next supported process reload/restart.
- Authenticated browser rendering of the updated `Health systemu` page was not
  checked.

Follow-up:
- Load the SmartFuelPass health fix into production through the supported
  restart/reload path before relying on the dashboard display.
- Continue with prediction checklist step 17 after the health display fix is
  accepted.

### 2026-07-10 13:04 +02:00 - Shared prediction core step 17

Scope:
- Completed step 17 of the shared prediction core plan for `elektromery`.
- Reviewed electricity source cadence and reporting semantics before adding
  monthly next-month prediction candidates.

Changed:
- Added `moduly/mereni/elektromery/prediction_adapter.py` with valid
  consumption observation loading from `monitoring.Mereni_elektromery_vse`,
  source-aware monthly aggregation, and a no-op active-model/selection
  adapter surface for the current non-production electricity prediction stage.
- Added `moduly/mereni/elektromery/elektromery_prediction.py` with shared
  monthly pipeline settings, next-month forecast-period construction, three
  candidate plugins, previous-completed-calendar-month rebuild windows,
  monthly rolling-backtest execution, and shared candidate selection helpers.
- Electricity monthly aggregation prefers detailed non-`SOFTLINK` sources for
  an identifier/month when present, otherwise falls back to `SOFTLINK`, so
  parallel sources are not double-counted.
- Candidate models added:
  - Model 1: recent 3-month average.
  - Model 2: trailing 12-month median.
  - Model 3: same month last year.
- Added targeted tests for adapter SQL filters, source-priority aggregation,
  candidate metadata, next-month forecast periods, and synthetic monthly
  backtests.
- Marked checklist step 17 complete.

Verified:
- `.venv\Scripts\python.exe -m py_compile moduly\mereni\elektromery\prediction_adapter.py
  moduly\mereni\elektromery\elektromery_prediction.py
  tests\test_elektromery_prediction_adapter.py tests\test_elektromery_prediction.py`
  passed.
- `.venv\Scripts\python.exe -m pytest tests\test_elektromery_prediction_adapter.py
  tests\test_elektromery_prediction.py tests\test_prediction_pipeline.py
  tests\test_prediction_backtest.py tests\test_elektromery_db_vse.py
  tests\test_elektromery_reports.py tests\test_elektromery_branch_period_report.py
  -q --tb=short` reported `66 passed`.
- `.venv\Scripts\python.exe -m pytest tests\test_prediction_contracts.py
  tests\test_prediction_backtest.py tests\test_prediction_pipeline.py
  tests\test_prediction_storage.py tests\test_vodomery_prediction.py
  tests\test_vodomery_prediction_adapter.py tests\test_plynomery_prediction.py
  tests\test_plynomery_prediction_adapter.py tests\test_elektromery_prediction.py
  tests\test_elektromery_prediction_adapter.py tests\test_elektromery_db_vse.py
  tests\test_elektromery_reports.py tests\test_elektromery_branch_period_report.py
  -q --tb=short` reported `125 passed`.

Not verified:
- No live electricity prediction/backtest was run against production
  PostgreSQL data.
- No scheduler, report email, dashboard, or production scoring integration was
  enabled for electricity prediction in this step.
- Running production processes have not loaded these uncommitted code changes;
  restart/reload remains deferred by user request.

Follow-up:
- Step 18 remains open: add cross-media dashboard/report views for candidate
  and per-identifier selection performance after deciding the display shape.

### 2026-07-10 13:14 +02:00 - Pre-restart handoff after SmartFuelPass health fix and prediction step 17

Reason for restart:
- Load the uncommitted SmartFuelPass `Health systemu` freshness fix and shared
  prediction pipeline changes through the supported full-workstation restart
  path.
- Confirm after boot that FastAPI, Streamlit, scheduler, and Caddy all start
  cleanly from the current dirty working tree.
- Continue after restart with post-restart verification before any new
  implementation work.

Current task/conversation state:
- Completed: shared prediction checklist steps 14, 15, 16, and 17.
- Completed: manual production `weekly_job` rebuild testrun after steps 14-16.
- Completed: SmartFuelPass health investigation. The real sync last succeeded
  on `2026-07-10 00:17:20 +02:00`; the dashboard issue was caused by using
  `MAX(imported_at)` as the main freshness signal when no new relace were
  inserted.
- Completed: SmartFuelPass health fix now treats stale `MAX(imported_at)` as
  OK when `sync_charge_sessions_to_db` ran successfully within the daily
  window, and the dashboard primary metric now displays `Posledni sync`.
- Completed: `elektromery` monthly next-month prediction candidate integration
  without scheduler/report/scoring enablement.
- Pending: workstation restart and post-restart verification.
- Pending: prediction checklist step 18, cross-media dashboard/report views,
  only after post-restart state is confirmed.
- First action after restart: read `AGENTS.md`, `DECISIONS.md`, and
  `SESSION_NOTES.md`, run `git status --short --untracked-files=all`, then
  execute the post-restart checks below.

Working tree and deployment:
- Branch: `master`
- HEAD: `8a9b2e2e96b553b107864e9199172dbfd5363b80`
- `git status --short --untracked-files=all` before restart:

```text
 M SESSION_NOTES.md
 M moduly/apps/dashboard/pages/37_system_health.py
 M moduly/mereni/plynomery/plynomery_prediction.py
 M moduly/mereni/prediction/__init__.py
 M moduly/mereni/prediction/backtest.py
 M moduly/mereni/vodomery/vodomery_prediction.py
 M services/api/services/system_health.py
 M tests/test_plynomery_prediction.py
 M tests/test_prediction_backtest.py
 M tests/test_system_health.py
?? moduly/mereni/elektromery/elektromery_prediction.py
?? moduly/mereni/elektromery/prediction_adapter.py
?? moduly/mereni/plynomery/prediction_adapter.py
?? moduly/mereni/prediction/periods.py
?? moduly/mereni/prediction/pipeline.py
?? tests/test_elektromery_prediction.py
?? tests/test_elektromery_prediction_adapter.py
?? tests/test_plynomery_prediction_adapter.py
?? tests/test_prediction_pipeline.py
```

- `main.py` is unchanged.
- No Caddy configuration changes were made. Root `Caddyfile` and runtime
  `C:\Program Files\Caddy\Caddyfile` SHA-256 hashes matched before restart:
  `08CDF04AFC4F856FEC8DFE4AB2E07A746763B152CA91553E349CCCE8E6D3DF2C`.
- Runtime Caddy validation before restart reported `Valid configuration`.
- Current running FastAPI/Streamlit/scheduler processes have not yet loaded
  the latest SmartFuelPass health fix or the `elektromery` step 17 modules.
  Restart should load the current dirty working tree into the process set.
- Current pre-restart runtime snapshot:
  - Windows boot time: `2026-07-10 11:16:54 +02:00`.
  - Startup task `API_dashboard_caddy`: state `Ready`, last run
    `2026-07-10 11:17:04 +02:00`, last result `0`.
  - Expected listeners present before restart: Caddy on TCP `80`, `443`, and
    `127.0.0.1:2019`; FastAPI on `127.0.0.1:8000`; Streamlit on
    `127.0.0.1:8001`; Tailscale retained interface-specific TCP `443`
    listeners.
  - Temporary ports `8010` and `8011` were not listening.
  - FastAPI `/health/live` and `/health/ready`, Streamlit `/_stcore/health`,
    and Caddy admin `/config/` returned HTTP `200`.
  - Local Caddy Host/SNI route returned HTTPS dashboard HTTP `200`,
    HTTP-to-HTTPS redirect HTTP `308`, `users-exist` HTTP `200`,
    protected `/auth/me` HTTP `401`, and `/docs` HTTP `404`.
  - Scheduler metrics showed `scheduler_running=True`, heartbeat
    `2026-07-10T13:07:11.205795`, and `quarter_hour_job` success at
    `2026-07-10T13:05:09.995917`.

Sensitive/runtime artifacts:
- Do not print, read, modify, delete, or commit `.env` values, ProgramData
  credential files, bearer tokens, cookie values, SmartFuelPass session JSON
  payloads, raw portal rows, raw meter rows, raw device photo paths, or
  production credentials.
- Do not inspect local SOFTLINK auth files such as
  `moduly/mereni/elektromery/SOFTLINK/lds_auth.json`.
- Do not inspect or clean raw electric-meter data artifacts under
  `moduly/mereni/elektromery/data/` unless explicitly requested.
- Scheduler lock files under `core/scheduler/locks` are tracked runtime
  artifacts; do not delete or rewrite them as part of restart verification.

Expected processes after restart:
- FastAPI/Uvicorn: one runtime on `127.0.0.1:8000`.
- Streamlit: one runtime on `127.0.0.1:8001`.
- Scheduler: one `main.py` runtime holding the scheduler process role.
- Caddy: one runtime owning TCP `80`, TCP `443`, and admin
  `127.0.0.1:2019`.
- Temporary ports `8010` and `8011` should remain unused.
- Tailscale may retain interface-specific TCP `443` listeners.

Expected application state:
- FastAPI `/health/live` and `/health/ready`: HTTP `200`.
- Streamlit `/_stcore/health`: HTTP `200`.
- Caddy admin `/config/`: HTTP `200`.
- Public dashboard via local Caddy Host/SNI route: HTTPS dashboard HTTP `200`.
- HTTP to HTTPS redirect: HTTP `308`.
- `/api/v1/auth/users-exist`: HTTP `200`.
- Protected API without bearer token: HTTP `401` JSON.
- Map image without cookie: HTTP `401`.
- `/docs`, `/redoc`, and `/openapi.json`: HTTP `404` at Caddy layer.
- Public response headers should include HSTS, `nosniff`, `Referrer-Policy`,
  `X-Frame-Options`, `Permissions-Policy`, and CSP report-only; `Server` and
  `Via` should remain absent.
- Scheduler metrics should show `scheduler_running=True`, a post-boot
  heartbeat, and a post-boot `quarter_hour_job` observation after the next
  scheduled slot.
- Direct `.venv-production` SmartFuelPass collector call should return
  `status=ok` for the current expected state where sync is fresh but
  `MAX(imported_at)` may still be `2026-07-06 22:17:21.474904` until a new
  completed relace appears.
- `elektromery` prediction modules should import and tests should pass, but no
  production scheduler/report/scoring path should start using them yet.

Required post-restart checks:
- Confirm Windows boot time is after this handoff and startup task
  `API_dashboard_caddy` last result is `0`.
- Confirm expected listeners and absence of temporary listeners.
- Confirm FastAPI, Streamlit, and Caddy local health endpoints.
- Confirm unauthenticated protected health/admin routes still return `401`,
  including `/health/system/smartfuelpass`.
- Confirm local Caddy routing and public response headers; `Server` and `Via`
  should remain absent.
- Confirm root `Caddyfile` and runtime `C:\Program Files\Caddy\Caddyfile`
  hashes still match, then validate the runtime Caddy configuration.
- Confirm scheduler heartbeat and a fresh post-boot `quarter_hour_job`
  observation.
- Run direct production-environment SmartFuelPass collector check:
  `.venv-production\Scripts\python.exe -c "import json; from services.api.services.system_health import collect_system_smartfuelpass_health; r=collect_system_smartfuelpass_health(); print(json.dumps({'status': r.status, 'table_status': r.table.status, 'sync_status': r.sync_job.status, 'sync_last_status': r.sync_job.last_status, 'sync_last_run': r.sync_job.last_run, 'last_imported_at': r.table.last_imported_at}, default=str, ensure_ascii=False, indent=2))"`
- Run targeted code verification:
  `.venv\Scripts\python.exe -m py_compile services\api\services\system_health.py
  moduly\apps\dashboard\pages\37_system_health.py
  moduly\mereni\prediction\periods.py moduly\mereni\prediction\pipeline.py
  moduly\mereni\prediction\backtest.py moduly\mereni\prediction\__init__.py
  moduly\mereni\vodomery\vodomery_prediction.py
  moduly\mereni\plynomery\plynomery_prediction.py
  moduly\mereni\plynomery\prediction_adapter.py
  moduly\mereni\elektromery\prediction_adapter.py
  moduly\mereni\elektromery\elektromery_prediction.py`
- Run targeted tests:
  `.venv\Scripts\python.exe -m pytest tests\test_system_health.py
  tests\test_api_authorization_regression.py tests\test_prediction_contracts.py
  tests\test_prediction_backtest.py tests\test_prediction_pipeline.py
  tests\test_prediction_storage.py tests\test_vodomery_prediction.py
  tests\test_vodomery_prediction_adapter.py tests\test_plynomery_prediction.py
  tests\test_plynomery_prediction_adapter.py tests\test_elektromery_prediction.py
  tests\test_elektromery_prediction_adapter.py tests\test_elektromery_db_vse.py
  tests\test_elektromery_reports.py tests\test_elektromery_branch_period_report.py
  -q --tb=short`
- Run scheduler/report smoke:
  `.venv\Scripts\python.exe -m pytest
  tests\test_scheduler.py::test_weekly_job_rebuilds_profiles_and_sends_report
  tests\test_vodomery_model_rebuild_report.py -q --tb=short`
- Do not run another manual production `weekly_job` rebuild unless the user
  explicitly asks, because it sends configured reports and was already run on
  `2026-07-10 11:53-12:07 +02:00`.
- Finish with `git diff --check` and
  `git status --short --untracked-files=all`.
- Append a dated post-restart verification entry with results, deviations, and
  accepted gaps.

Known risks or accepted gaps:
- The process set will load uncommitted working-tree changes. This is intended
  for the agreed restart.
- Step 17 only integrates electricity prediction candidates and tests; it does
  not enable live electricity prediction, scheduler rebuilds, report views, or
  scoring.
- Authenticated browser rendering of the updated `Health systemu` page may
  still require manual browser verification after restart.
- Direct public hostname routing from outside the workstation is not covered
  by local Host/SNI checks.
- Immediately after boot, scheduler metrics may not yet contain a post-boot
  `quarter_hour_job` observation until the next scheduled slot.
- The startup task starts the process set but does not supervise later child
  process exits; recovery remains full-workstation restart.

### 2026-07-10 14:14 +02:00 - Post-restart verification

Scope:
- Completed the required post-restart verification from the
  `2026-07-10 13:14 +02:00` handoff.

Changed:
- Appended this verification note to `SESSION_NOTES.md`.

Verified:
- Windows boot time was `2026-07-10 13:17:55 +02:00`, after the handoff.
- Startup task `API_dashboard_caddy` last ran at
  `2026-07-10 13:18:04 +02:00` with result `0`.
- Expected listeners were present: Caddy on TCP `80`, TCP `443`, and
  `127.0.0.1:2019`; FastAPI on `127.0.0.1:8000`; Streamlit on
  `127.0.0.1:8001`; Tailscale retained its interface-specific TCP `443`
  listeners.
- Temporary ports `8010` and `8011` were not listening.
- Local health endpoints returned HTTP `200`: FastAPI `/health/live`,
  FastAPI `/health/ready`, Streamlit `/_stcore/health`, and Caddy admin
  `/config/`.
- Unauthenticated protected system health routes returned HTTP `401`,
  including `/health/system/smartfuelpass`.
- Local Caddy Host/SNI routing returned: dashboard HTTP `200`,
  `/api/v1/auth/users-exist` HTTP `200`, protected `/auth/me` HTTP `401`,
  map image without cookie HTTP `401`, `/docs`, `/redoc`, and
  `/openapi.json` HTTP `404`, and HTTP-to-HTTPS redirect HTTP `308`.
- Public response headers included HSTS, `nosniff`, `Referrer-Policy`,
  `X-Frame-Options`, `Permissions-Policy`, and CSP report-only; `Server` and
  `Via` were absent.
- Root `Caddyfile` and runtime `C:\Program Files\Caddy\Caddyfile` SHA-256
  hashes matched:
  `08CDF04AFC4F856FEC8DFE4AB2E07A746763B152CA91553E349CCCE8E6D3DF2C`.
- Runtime Caddy validation reported `Valid configuration`.
- Scheduler metrics showed `scheduler_running=True`, heartbeat
  `2026-07-10T13:58:10.799420`, and post-boot `quarter_hour_job` success at
  `2026-07-10T13:47:09.583349` with `0` failures in the last 24 hours.
- Direct `.venv-production` SmartFuelPass collector returned overall
  `status=ok`, table `status=ok`, sync `status=ok`, sync last status
  `success`, sync last run `2026-07-10 00:17:20.377435`, and
  `last_imported_at=2026-07-06 22:17:21.474904`.
- Targeted `py_compile` for the SmartFuelPass health fix and prediction
  modules passed.
- Targeted pytest suite for system health, API authorization, prediction
  contracts/pipeline/storage, vodomery, plynomery, and elektromery reported
  `319 passed`.
- Scheduler/report smoke tests reported `2 passed`.

Not verified:
- Authenticated browser rendering of the updated `Health systemu` page was
  not checked.
- Direct external public routing from outside the workstation was not checked.
- Exact Python process command-line details were not available through the
  read-only process query; API and Streamlit were verified by listeners and
  health endpoints, and scheduler by metrics heartbeat plus post-boot
  `quarter_hour_job`.
- No manual production `weekly_job` rebuild was run after restart, as required
  by the handoff because the earlier manual run already sent reports.

Follow-up:
- Continue with prediction checklist step 18 after deciding the
  cross-media dashboard/report view shape.

### 2026-07-10 14:47 +02:00 - Shared prediction core step 18

Scope:
- Completed step 18 of the shared prediction core plan.
- Added cross-media admin views for prediction candidate performance and
  per-identifier selected-model snapshots after vodomery, plynomery, and
  elektromery shared-pipeline integration.

Changed:
- Added admin-only FastAPI route `GET /api/v1/prediction/performance`.
- Added `services/api/services/prediction_performance.py` to aggregate latest
  vodomery/plynomery selection runs, shared selected-model snapshots, worst
  identifier selections, and registered candidate catalogs.
- Added `services/api/schemas/prediction.py` response schemas.
- Added Streamlit admin page
  `moduly/apps/dashboard/pages/38_prediction_performance.py` and footer
  navigation entry `prediction_performance`.
- Added dashboard API client method `get_prediction_performance`.
- Updated API authorization inventory and dashboard navigation tests.
- Updated `AGENTS.md` project map for the new prediction API/service/page.
- Marked prediction checklist step 18 complete.

Verified:
- `.venv\Scripts\python.exe -m py_compile services\api\schemas\prediction.py
  services\api\services\prediction_performance.py services\api\routes\prediction.py
  services\api\main.py moduly\apps\dashboard\api_client.py
  moduly\apps\dashboard\navigation_config.py
  moduly\apps\dashboard\pages\38_prediction_performance.py
  tests\test_prediction_performance.py tests\test_api_authorization_regression.py
  tests\test_dashboard_navigation_config.py` passed.
- `.venv\Scripts\python.exe -m pytest tests\test_prediction_performance.py
  tests\test_api_authorization_regression.py tests\test_dashboard_navigation_config.py
  -q --tb=short` reported `201 passed`.
- `.venv\Scripts\python.exe -m pytest tests\test_prediction_performance.py
  tests\test_api_authorization_regression.py tests\test_dashboard_navigation_config.py
  tests\test_prediction_contracts.py tests\test_prediction_backtest.py
  tests\test_prediction_pipeline.py tests\test_prediction_storage.py
  tests\test_vodomery_prediction.py tests\test_vodomery_prediction_adapter.py
  tests\test_plynomery_prediction.py tests\test_plynomery_prediction_adapter.py
  tests\test_elektromery_prediction.py tests\test_elektromery_prediction_adapter.py
  -q --tb=short` reported `281 passed`.
- Direct `.venv-production` collector call returned aggregate-only status
  `ok`: vodomery `5` candidate rows, `58` selected-model snapshots, `3`
  fallback snapshots, and `25` worst-identifier rows; plynomery `2`
  candidate rows; elektromery `3` catalog candidates and `not_run` status.

Not verified:
- Authenticated browser rendering of the new `Predikce modelu` dashboard page
  was not checked.
- The running production FastAPI process has not loaded the new route yet;
  it will require the supported restart/reload path before the dashboard page
  can use the endpoint in production.
- No live elektromery production prediction run was enabled; elektromery remain
  catalog-only in this view until a future scheduler/report/scoring step.

Follow-up:
- Before relying on the new dashboard page in production, load the changed
  FastAPI/Streamlit code through the supported restart path.

### 2026-07-10 14:54 +02:00 - Pre-restart handoff after prediction performance view

Reason for restart:
- Load the new admin-only prediction performance API route and Streamlit
  dashboard page into the supported production runtime process set.
- Confirm after boot that FastAPI, Streamlit, scheduler, and Caddy start from
  the current dirty working tree and that the new prediction performance view
  works through the public dashboard route.

Current task/conversation state:
- Completed: post-restart verification from the earlier
  `2026-07-10 13:14 +02:00` handoff.
- Completed: shared prediction checklist step 18.
- Completed: admin-only FastAPI route `GET /api/v1/prediction/performance`.
- Completed: Streamlit admin page `Predikce modelu` at
  `moduly/apps/dashboard/pages/38_prediction_performance.py`.
- Completed: dashboard navigation entry `prediction_performance`.
- Completed: API client method `get_prediction_performance`.
- Completed: targeted tests and direct aggregate collector check for the new
  prediction performance view.
- Pending: workstation restart and post-restart verification.
- First action after restart: read `AGENTS.md`, `DECISIONS.md`, and
  `SESSION_NOTES.md`, run `git status --short --untracked-files=all`, then
  execute the post-restart checks below.

Working tree and deployment:
- Branch: `master`
- HEAD: `8a9b2e2e96b553b107864e9199172dbfd5363b80`
- `git status --short --untracked-files=all` before restart:

```text
 M AGENTS.md
 M SESSION_NOTES.md
 M moduly/apps/dashboard/api_client.py
 M moduly/apps/dashboard/navigation_config.py
 M moduly/apps/dashboard/pages/37_system_health.py
 M moduly/mereni/plynomery/plynomery_prediction.py
 M moduly/mereni/prediction/__init__.py
 M moduly/mereni/prediction/backtest.py
 M moduly/mereni/vodomery/vodomery_prediction.py
 M services/api/main.py
 M services/api/services/system_health.py
 M tests/test_api_authorization_regression.py
 M tests/test_dashboard_navigation_config.py
 M tests/test_plynomery_prediction.py
 M tests/test_prediction_backtest.py
 M tests/test_system_health.py
?? moduly/apps/dashboard/pages/38_prediction_performance.py
?? moduly/mereni/elektromery/elektromery_prediction.py
?? moduly/mereni/elektromery/prediction_adapter.py
?? moduly/mereni/plynomery/prediction_adapter.py
?? moduly/mereni/prediction/periods.py
?? moduly/mereni/prediction/pipeline.py
?? services/api/routes/prediction.py
?? services/api/schemas/prediction.py
?? services/api/services/prediction_performance.py
?? tests/test_elektromery_prediction.py
?? tests/test_elektromery_prediction_adapter.py
?? tests/test_plynomery_prediction_adapter.py
?? tests/test_prediction_performance.py
?? tests/test_prediction_pipeline.py
```

- `main.py` is unchanged.
- No Caddy configuration changes were made. Root `Caddyfile` and runtime
  `C:\Program Files\Caddy\Caddyfile` SHA-256 hashes matched before restart:
  `08CDF04AFC4F856FEC8DFE4AB2E07A746763B152CA91553E349CCCE8E6D3DF2C`.
- Runtime Caddy validation before restart reported `Valid configuration`.
- Current running FastAPI/Streamlit processes have not loaded the new
  prediction route/page code. Pre-restart public
  `/api/v1/prediction/performance` without bearer returned HTTP `404`; after
  restart the expected unauthenticated result is HTTP `401`.
- Current pre-restart runtime snapshot:
  - Windows boot time: `2026-07-10 13:17:55 +02:00`.
  - Startup task `API_dashboard_caddy`: state `Ready`, last run
    `2026-07-10 13:18:04 +02:00`, last result `0`.
  - Expected listeners present before restart: Caddy on TCP `80`, TCP `443`,
    and `127.0.0.1:2019`; FastAPI on `127.0.0.1:8000`; Streamlit on
    `127.0.0.1:8001`; Tailscale retained interface-specific TCP `443`
    listeners.
  - Temporary ports `8010` and `8011` were not listening.
  - FastAPI `/health/live` and `/health/ready`, Streamlit `/_stcore/health`,
    and Caddy admin `/config/` returned HTTP `200`.
  - Local Caddy Host/SNI route returned HTTPS dashboard HTTP `200`,
    HTTP-to-HTTPS redirect HTTP `308`, `users-exist` HTTP `200`, protected
    `/auth/me` HTTP `401`, map image without cookie HTTP `401`, and `/docs`
    HTTP `404`.
  - Scheduler metrics showed `scheduler_running=True`, heartbeat
    `2026-07-10T14:53:11.082173`, and `quarter_hour_job` success at
    `2026-07-10T14:47:09.626052` with `0` failures in the last 24 hours.

Sensitive/runtime artifacts:
- Do not print, read, modify, delete, or commit `.env` values, ProgramData
  credential files, bearer tokens, cookie values, SmartFuelPass session JSON
  payloads, raw portal rows, raw meter rows, raw device photo paths, or
  production credentials.
- Do not inspect local SOFTLINK auth files such as
  `moduly/mereni/elektromery/SOFTLINK/lds_auth.json`.
- Do not inspect or clean raw electric-meter data artifacts under
  `moduly/mereni/elektromery/data/` unless explicitly requested.
- Scheduler lock files under `core/scheduler/locks` are tracked runtime
  artifacts; do not delete or rewrite them as part of restart verification.

Expected processes after restart:
- FastAPI/Uvicorn: one runtime on `127.0.0.1:8000`.
- Streamlit: one runtime on `127.0.0.1:8001`.
- Scheduler: one `main.py` runtime holding the scheduler process role.
- Caddy: one runtime owning TCP `80`, TCP `443`, and admin
  `127.0.0.1:2019`.
- Temporary ports `8010` and `8011` should remain unused.
- Tailscale may retain interface-specific TCP `443` listeners.

Expected application state:
- FastAPI `/health/live` and `/health/ready`: HTTP `200`.
- Streamlit `/_stcore/health`: HTTP `200`.
- Caddy admin `/config/`: HTTP `200`.
- Public dashboard via local Caddy Host/SNI route: HTTPS dashboard HTTP `200`.
- HTTP-to-HTTPS redirect: HTTP `308`.
- `/api/v1/auth/users-exist`: HTTP `200`.
- Protected API without bearer token: HTTP `401` JSON.
- New `/api/v1/prediction/performance` without bearer token: HTTP `401`
  JSON, confirming the new route is loaded and protected.
- Map image without cookie: HTTP `401`.
- `/docs`, `/redoc`, and `/openapi.json`: HTTP `404` at Caddy layer.
- Public response headers should include HSTS, `nosniff`, `Referrer-Policy`,
  `X-Frame-Options`, `Permissions-Policy`, and CSP report-only; `Server` and
  `Via` should remain absent.
- Scheduler metrics should show `scheduler_running=True`, a post-boot
  heartbeat, and a post-boot `quarter_hour_job` observation after the next
  scheduled slot.
- Direct `.venv-production` prediction performance collector should return
  aggregate-only `status=ok` with vodomery candidate/snapshot rows, plynomery
  candidate rows, and elektromery catalog-only `not_run` status until a future
  production electricity prediction run is explicitly enabled.

Required post-restart checks:
- Confirm Windows boot time is after this handoff and startup task
  `API_dashboard_caddy` last result is `0`.
- Confirm expected listeners and absence of temporary listeners.
- Confirm FastAPI, Streamlit, and Caddy local health endpoints.
- Confirm unauthenticated protected routes still return `401`, including
  `/api/v1/prediction/performance` and `/health/system/smartfuelpass`.
- Confirm local Caddy routing and public response headers; `Server` and `Via`
  should remain absent.
- Confirm root `Caddyfile` and runtime `C:\Program Files\Caddy\Caddyfile`
  hashes still match, then validate the runtime Caddy configuration.
- Confirm scheduler heartbeat and a fresh post-boot `quarter_hour_job`
  observation.
- Run direct production-environment prediction performance collector check:
  `.venv-production\Scripts\python.exe -c "import json; from services.api.services.prediction_performance import collect_prediction_performance_report; r=collect_prediction_performance_report(); print(json.dumps({'status': r.status, 'media': [{'medium': m.medium_key, 'status': m.status, 'candidates': len(m.candidate_performance), 'catalog': len(m.candidate_catalog), 'snapshots': None if m.snapshot_summary is None else m.snapshot_summary.snapshot_count, 'fallbacks': None if m.snapshot_summary is None else m.snapshot_summary.fallback_count, 'worst_rows': len(m.worst_identifier_selections)} for m in r.media]}, default=str, ensure_ascii=False, indent=2))"`
- Run targeted code verification:
  `.venv\Scripts\python.exe -m py_compile services\api\schemas\prediction.py
  services\api\services\prediction_performance.py services\api\routes\prediction.py
  services\api\main.py moduly\apps\dashboard\api_client.py
  moduly\apps\dashboard\navigation_config.py
  moduly\apps\dashboard\pages\38_prediction_performance.py
  tests\test_prediction_performance.py tests\test_api_authorization_regression.py
  tests\test_dashboard_navigation_config.py`
- Run targeted tests:
  `.venv\Scripts\python.exe -m pytest tests\test_prediction_performance.py
  tests\test_api_authorization_regression.py tests\test_dashboard_navigation_config.py
  -q --tb=short`
- Run broader prediction regression set:
  `.venv\Scripts\python.exe -m pytest tests\test_prediction_performance.py
  tests\test_api_authorization_regression.py tests\test_dashboard_navigation_config.py
  tests\test_prediction_contracts.py tests\test_prediction_backtest.py
  tests\test_prediction_pipeline.py tests\test_prediction_storage.py
  tests\test_vodomery_prediction.py tests\test_vodomery_prediction_adapter.py
  tests\test_plynomery_prediction.py tests\test_plynomery_prediction_adapter.py
  tests\test_elektromery_prediction.py tests\test_elektromery_prediction_adapter.py
  -q --tb=short`
- If admin browser access is available, open `Predikce modelu` in the
  dashboard and confirm the page loads candidate tables without exposing raw
  measurement rows or secrets.
- Finish with `git diff --check` and
  `git status --short --untracked-files=all`.
- Append a dated post-restart verification entry with results, deviations, and
  accepted gaps.

Known risks or accepted gaps:
- The process set will load uncommitted working-tree changes. This is intended
  for the agreed restart.
- The new prediction view is read-only and aggregate-oriented; it does not
  enable live elektromery prediction, scheduler rebuilds, report emails, or
  scoring.
- Elektromery are expected to show catalog-only `not_run` status in the new
  view until a future reviewed step enables persisted production prediction
  runs.
- Authenticated browser rendering of the new `Predikce modelu` page still
  requires post-restart manual/admin browser verification.
- Direct public hostname routing from outside the workstation is not covered
  by local Host/SNI checks.
- Immediately after boot, scheduler metrics may not yet contain a post-boot
  `quarter_hour_job` observation until the next scheduled slot.
- The startup task starts the process set but does not supervise later child
  process exits; recovery remains full-workstation restart.
