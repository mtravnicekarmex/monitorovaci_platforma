# Legacy SESSION_NOTES preamble

This is the pre-session-log baseline and template section preserved during the 2026-07-30 archive split.

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

