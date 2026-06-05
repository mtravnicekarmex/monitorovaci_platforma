# AGENTS.md

Project: `monitorovaci_platforma`

Purpose: persistent operating context for future agent-assisted sessions. Read this file before making changes.

## Start of Every Session

1. Read `AGENTS.md`, `DECISIONS.md`, and `SESSION_NOTES.md`.
2. Run `git status --short` and treat the result as part of the session context.
3. Do not assume a clean working tree. This project can contain user changes and runtime artifacts.
4. Never revert, overwrite, or delete changes you did not make unless the user explicitly approves it.
5. If unexpected changes appear while working, stop and ask the user how to proceed.
6. Keep secrets and runtime data private. Do not print cookie values, tokens, credentials, or raw operational data unless the user explicitly asks and the security impact is clear.
7. Prefer read-only inspection until the user asks for implementation or explicitly approves file writes.

## Documentation Contract

These files are part of the daily workflow:

- `AGENTS.md`: operating rules, project map, and practices for future agents.
- `DECISIONS.md`: durable architectural, product, and workflow decisions.
- `SESSION_NOTES.md`: current baseline, session history, open questions, and handoff notes.

At the end of every substantive session:

- Propose updates to these files when architecture, workflow, decisions, or project state changed.
- Record concrete dates instead of relative dates.
- Keep notes factual and short enough to be useful.
- Do not silently rewrite historical decisions. Add a new decision or mark the previous one as superseded.
- If the user asks to approve final text before saving, show the exact final version before writing.

## Project Map

- `main.py`: scheduler entry point. Imports and runs the main scheduler.
- `core/db/connect.py`: SQLAlchemy database connections for PostgreSQL and MSSQL, configured through `python-decouple`.
- `core/scheduler/job_schedule.py`: single source of truth for APScheduler cron schedules.
- `core/scheduler/scheduler.py`: scheduler execution, locks, metrics, manual run specs, and alert emails.
- `core/scheduler/metrics.py`: scheduler metrics persistence in `core/scheduler/logs/scheduler_metrics.json`.
- `services/api/main.py`: FastAPI application entry point and router registration.
- `services/api/core/tokens.py`: custom HMAC bearer token implementation.
- `services/api/core/dependencies.py`: API authentication, admin, section, and device access dependencies.
- `moduly/apps/dashboard/login.py`: main Streamlit dashboard entry point.
- `moduly/apps/dashboard/navigation_config.py`: authoritative Streamlit navigation and permissions configuration.
- `moduly/apps/dashboard/auth.py`: Streamlit authentication/session state and API login flow.
- `moduly/apps/dashboard/database/models.py`: dashboard user and permission model.
- `moduly/apps/dashboard/database/db_init.py`: dashboard and feature table bootstrap.
- `frontend_next/`: experimental Next.js MVP. It is not the active production dashboard and is not currently used in daily operation. Treat it as a future migration/prototype area, not as the source of truth for current dashboard behavior.
- `.streamlit/config.toml`: Streamlit server and navigation settings.
- `Caddyfile`: local reverse proxy configuration.
- `requirements-api.txt`: Python runtime/API dependency set.
- `tests/`: pytest suite for scheduler, imports, dashboards, reports, auth/navigation, anomaly handling, and supporting services.

## Runtime Surfaces

Current active surfaces:

- Scheduler process started from `main.py`.
- FastAPI service from `services/api/main.py`.
- Streamlit dashboard from `moduly/apps/dashboard/login.py`.

Experimental or future-facing surface:

- `frontend_next/` is a partial Next.js migration experiment. Do not assume feature parity with Streamlit. Do not use it to infer current production dashboard behavior unless the user explicitly asks about this experimental area.

## Data and Secrets

Treat these as sensitive or operational artifacts:

- `data/smartfuelpass/session_cookies.json`
- `data/smartfuelpass/auto_login_session.json`
- Any `.env`, credentials, cookies, tokens, browser sessions, or account data.
- Raw meter data and imported source files unless the user explicitly requests inspection.

Known hygiene topics to handle only after explicit approval:

- Some SmartFuelPass session files are tracked or modified.
- `core/scheduler/locks/*.lock` are tracked runtime lock artifacts.
- `frontend_next/tsconfig.tsbuildinfo` is a tracked build artifact.
- `.gitignore` ignores `moduly/mereni/elektromery/data/*.ts` but not nested files such as `moduly/mereni/elektromery/data/old/*.ts`.

## Architecture Notes

- PostgreSQL schemas are the main normalized storage layer.
- `monitoring` stores measurements, anomaly scores/events, alerting/outlier tables, SmartFuelPass, and meteo data.
- `dashboard` stores Streamlit users and permissions.
- `web_search` stores search monitors and results.
- `revize` stores revision/evidence data.
- `dbo` contains source or legacy operational tables, including some MSSQL-related structures.
- `evidence` contains QGIS/evidence device metadata.
- FastAPI should be the preferred boundary for new external or frontend-facing capabilities.
- Streamlit remains the active dashboard unless a task explicitly targets the experimental Next.js area.
- Shared behavior should live in modules/services, not in duplicated page logic.

## Time Semantics

Time handling is a core project constraint.

Important modules:

- `moduly/mereni/time_semantics.py`
- `moduly/apps/dashboard/time_semantics.py`

Canonical time columns include:

- `source_date`
- `time_utc`
- `time_basis`
- `source_timezone`
- `source_utc_offset_minutes`
- `time_fold`
- `timestamp_position`

SmartFuelPass intervals use start/end UTC/source semantics. Do not simplify timezone or interval handling without checking existing tests and domain behavior.

## Scheduler

- Keep schedule definitions in `core/scheduler/job_schedule.py`.
- Scheduler execution, locks, manual jobs, metrics, and alert emails are handled in `core/scheduler/scheduler.py`.
- Metrics are persisted by `core/scheduler/metrics.py`.
- Avoid adding schedule definitions directly inside feature modules.
- When changing scheduler behavior, run targeted scheduler tests and check manual-run compatibility.

Known job families:

- `quarter_hour_job`
- `hourly_job`
- `daily_seven_and_two_job`
- `daily_job`
- `daily_vodomery_branch_report_job`
- `weekly_job`
- `smartfuelpass_weekly_report_job`
- `monthly_job`

## Dashboard

- Streamlit is the active dashboard.
- Navigation and permission definitions belong in `moduly/apps/dashboard/navigation_config.py`.
- Login/session behavior belongs in `moduly/apps/dashboard/auth.py`.
- Dashboard database bootstrap belongs in `moduly/apps/dashboard/database/db_init.py`.
- For dashboard page changes, prefer small helpers and tested filtering/formatting behavior.
- For visual or UX changes, preserve existing project patterns unless the user explicitly asks for redesign.

## Measurement Domains

- `vodomery`: water meters, AREAL/SCVK sources, anomaly models, events, alerting, outlier review, reports, billing logic.
- `plynomery`: gas meters, baseline and weather-adjusted models, expected-zero/outlier/alerting behavior.
- `elektromery`: electricity meters, SOFTLINK and binary imports, OTE reporting, new device discovery.
- `kalorimetry`: heat meter imports, normalization, and outlier review.
- `manometry`: pressure measurements, imports, dashboard/API surfaces.
- `smartfuelpass`: fuel/card import and reporting workflow with browser/session artifacts.
- `web_search`: monitored web search and result persistence.

Water event types currently include examples such as:

- `NIGHT_USAGE`
- `SPIKE`
- `LONG_LEAK`
- `ZERO_FLOW`
- `EXPECTED_ZERO_USAGE`
- `OUTLIER_REVIEW`

## Testing

Prefer targeted tests first, then broader tests when risk justifies it.

Common commands:

```powershell
python -m pytest tests -v --tb=short
python -m pytest tests\test_scheduler.py -v --tb=short
python -m pytest tests\test_vodomery_db_import.py -v --tb=short
python -m pytest tests\test_dashboard_navigation_config.py -v --tb=short
```

Experimental frontend command:

```powershell
cd frontend_next
npm run typecheck
```

Use the frontend command only for work that actually touches `frontend_next/`.

## Implementation Rules

- Use `rg` / `rg --files` for search when available.
- Prefer `apply_patch` for small single-file edits.
- Do not use destructive git commands unless explicitly requested and approved.
- Do not amend commits unless explicitly requested.
- Keep changes scoped to the user request.
- Preserve existing Czech/domain terminology in UI and reports.
- Add comments only when they clarify non-obvious behavior.
- For new code touching time semantics, imports, anomaly/event logic, permissions, or scheduler behavior, look for existing tests before editing.

## Session Closeout

Before final response on substantive work:

1. Check `git status --short`.
2. Summarize changed files and why they changed.
3. State what verification was run.
4. State what was not run and why.
5. Propose updates to `DECISIONS.md` or `SESSION_NOTES.md` if needed.
