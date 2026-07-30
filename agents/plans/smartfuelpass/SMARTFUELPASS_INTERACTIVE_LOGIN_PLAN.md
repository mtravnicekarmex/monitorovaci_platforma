# SmartFuelPass Interactive Login and Import Plan

Prepared: 2026-07-28

Status: Paused on 2026-07-29. The production restart and runtime deployment
checks passed, but the Cloudflare challenge could not be completed manually
from the production workstation. No bypass will be introduced. Resume this
plan only when the portal operator provides a supported access path or an
official API/export is available.

## Goal

Replace the scheduled headless SmartFuelPass portal synchronization with an
explicit admin-initiated, interactive import. A visible browser opens on the
production workstation, an administrator completes the Cloudflare challenge
and portal login manually, and the existing importer continues in the same
temporary browser context.

The weekly SmartFuelPass report remains scheduled and continues to read only
from `monitoring.smartfuelpass_relace`.

## Safety Contract

- The workflow requires an authenticated dashboard administrator.
- Browser-initiated privileged actions execute through authenticated FastAPI.
- The interactive helper runs only on the production workstation and only in
  a logged-on, unlocked Windows desktop session.
- Portal credentials, cookies, browser storage, raw session rows, and
  Cloudflare clearance values are never returned to FastAPI or Streamlit.
- No persistent SmartFuelPass JSON session or reusable browser profile is
  created.
- The browser uses a temporary context that is removed after completion.
- Status exposed to the dashboard contains only timestamps, state, safe
  aggregate counts, and a sanitized error category/message.
- Only one interactive import may run at a time.
- Starting the workflow never sends reports, alerts, or email.
- The database write reuses the reviewed idempotent upsert by `id_relace`.
- Cloudflare protection is completed manually; the implementation must not
  automate, bypass, disguise, or outsource the challenge.

## Implementation Checklist

### 1. Architecture and contracts

- [x] Confirm the portal is reachable in a normal visible browser on the
  production workstation.
- [x] Confirm headless automation is challenged before the login form.
- [x] Confirm the user approves an explicit interactive workflow.
- [x] Define sanitized status states: `idle`, `starting`,
  `waiting_for_login`, `importing`, `success`, and `error`.
- [x] Define the single-run lock and atomic status-file format.
- [x] Define FastAPI response schemas without credentials, cookies, raw rows,
  portal HTML, browser command lines, or sensitive paths.

### 2. Interactive helper

- [x] Add a production-Python entry point for one interactive import.
- [x] Launch visible Chromium/Chrome in a temporary browser context.
- [x] Navigate to the configured SmartFuelPass login page.
- [x] Wait for the administrator to complete Cloudflare and portal login.
- [x] Continue to the company dashboard and charging-session table in the
  authenticated browser context.
- [x] Load and normalize the table using existing service functions.
- [x] Run the existing PostgreSQL upsert without reports or email.
- [x] Persist only sanitized progress/result state.
- [x] Close the browser and remove temporary state on every exit path.
- [x] Refuse concurrent runs.

### 3. Windows interactive task

- [x] Add an idempotent registration script for a dedicated task named
  `Monitoring_SmartFuelPass_Interactive_Import`.
- [x] Configure the task to run only while the designated user is logged on,
  with an interactive token and the reviewed production Python environment.
- [x] Configure no periodic trigger; the task is started only on demand.
- [x] Use the repository as the working directory and fail closed when the
  production runtime invariant is not satisfied.
- [x] Document registration, inspection, and removal commands.

### 4. Admin FastAPI boundary

- [x] Add an admin-only status endpoint.
- [x] Add an admin-only start endpoint.
- [x] Validate Windows platform, task existence, task state, logged-on
  interactive session availability, and single-run state before start.
- [x] Start only the exact dedicated scheduled task; accept no client-supplied
  command, executable, arguments, task name, or filesystem path.
- [x] Return sanitized conflict/unavailable errors.
- [x] Add authorization, service, route, and response-schema tests.

### 5. Dashboard page

- [x] Add admin-only page `Nabíječky / Přihlášení SmartFuelPass`.
- [x] Explain that the visible browser opens on the production workstation.
- [x] Show prerequisites: logged-on and unlocked production desktop session.
- [x] Add explicit `Přihlásit` / start-import confirmation.
- [x] Poll and display sanitized workflow status and latest aggregate result.
- [x] Link or include the existing safe SmartFuelPass table/report health
  summary.
- [x] Never display credentials, cookies, raw rows, portal HTML, or operational
  identifiers.
- [x] Add navigation, API-client, and dashboard rendering/helper tests.

### 6. Scheduler separation

- [x] Remove SmartFuelPass portal synchronization from `daily_job`.
- [x] Remove the portal-sync step from the scheduler manual-run registry so
  it cannot launch headless from `Health scheduleru`.
- [x] Update the `daily_job` description and scheduler tests.
- [x] Keep `smartfuelpass_weekly_report_job` unchanged and database-backed.
- [x] Update system health so manual interactive import state replaces the
  expectation of a daily headless sync.

### 7. Verification and deployment

- [x] Run focused SmartFuelPass, API authorization, navigation, dashboard,
  scheduler, and system-health tests.
- [x] Run the complete project test suite.
- [x] Run `git diff --check`.
- [x] Review the final task definition before registration.
- [x] Register the interactive task with explicit user approval.
- [x] Prepare the mandatory dated restart handoff.
- [x] Restart the workstation to load API, Streamlit, and scheduler changes.
- [x] Complete the normal post-restart runtime/routing checks.
- [ ] From an unlocked production desktop, start the workflow through the
  admin page and complete one controlled manual login/import. Blocked:
  Cloudflare could not be completed manually from the production workstation;
  do not retry until a supported access path is agreed.
- [ ] Confirm the task transitions through safe states and finishes.
- [ ] Confirm aggregate table counts/UTC completeness and idempotent upsert.
- [ ] Confirm no session artifact, report, alert, or email was created.
- [ ] Confirm the next weekly report still reads PostgreSQL successfully.

## Explicit Non-goals

- No Cloudflare bypass or automated challenge solving.
- No stored portal cookies, `cf_clearance`, browser profile, or JSON session.
- No portal password entry through the dashboard.
- No scheduled or unattended portal login.
- No arbitrary process/task launcher exposed through FastAPI.
- No change to the database-backed weekly report delivery contract.

## Paused Follow-up

- Confirm the supported access options with the SmartFuelPass portal operator.
- Prefer an official API, supported export, or explicit allowlisting over
  browser automation.
- Before resuming, review data-freshness communication for the database-backed
  weekly report and prepare a new controlled verification plan.
- Do not interpret this pause as authorization to retry, bypass Cloudflare, use
  a different network identity to evade the restriction, or persist a portal
  session.

## Windows Task Operations

Review and register, from an elevated PowerShell session:

```powershell
.\scripts\register_smartfuelpass_interactive_import_task.ps1
```

Inspect without exposing the action command:

```powershell
Get-ScheduledTask -TaskName Monitoring_SmartFuelPass_Interactive_Import |
    Select-Object TaskName, State, TaskPath
```

Removal is a separate destructive deployment action and must be explicitly
approved:

```powershell
Unregister-ScheduledTask `
    -TaskName Monitoring_SmartFuelPass_Interactive_Import `
    -Confirm
```
