# SESSION_NOTES.md

Purpose: short current project baseline and handoff for
`monitorovaci_platforma`. Detailed historical entries are stored in
`archive/`.

## Current baseline

Date: 2026-07-30

- Production surfaces are the scheduler from `main.py`, FastAPI from
  `services/api/main.py`, Streamlit from `moduly/apps/dashboard/login.py`, and
  Caddy using the tracked root `Caddyfile`.
- `frontend_next/` remains experimental and is not the production dashboard.
- Durable operating rules are in `../../AGENTS.md`.
- Durable architecture and product decisions are in
  `../decisions/DECISIONS.md`.
- Work status is tracked in `../work/ACTIVE.md`, `../work/BACKLOG.md`,
  `../work/BLOCKED.md`, and `../work/COMPLETED.md`.
- Plans retain stable thematic paths under `../plans/`; lifecycle state does
  not move a plan between directories.

## Active handoff

- Active product work: `KAL-025`, the separately approval-gated kalorimetry
  scheduler integration.
- Required procedure:
  `../runbooks/KALORIMETRY_ACTIVATION_RUNBOOK.md`.
- Activation remains subject to the runbook's forecast, snapshot, scoring,
  event, scheduler, regression, restart, and post-rollout gates.
- Do not infer approval for production snapshots, scoring/event tables,
  scheduler writes, alert delivery, reports, or email from implementation
  readiness alone.
- The historical session split (`DOC-002`) was completed on 2026-07-30 with
  271 entries preserved: 98 in the June archive and 173 in the July archive.
- Archive preservation checks, focused tests (`10 passed`), the complete
  regression suite (`1240 passed`), and `git diff --check` all passed.

## Latest runtime verification

The read-only check immediately after the 2026-07-30 13:10:04 restart found:

- startup task `API_dashboard_caddy` completed with result 0;
- expected listeners 80, 443, 2019, 8000, and 8001 were present;
- local FastAPI live/ready, Streamlit health, and Caddy admin returned HTTP
  200;
- scheduler heartbeat was fresh and the protected kalorimetry prediction route
  returned the expected HTTP 401 without credentials;
- the public hostname timed out from the agent environment and was not
  independently verified there;
- the check occurred before the first scheduled quarter-hour execution after
  that restart, so that execution was not confirmed by this check.

Treat this as a dated observation, not a guarantee of current runtime health.

## History index

- `archive/LEGACY_PREAMBLE.md`: original baseline, architecture snapshot,
  cleanup list, completed shared-prediction checklist, and templates that
  preceded the old monolithic session log.
- `archive/2026-06.md`: 98 session entries dated 2026-06-05 through
  2026-06-26.
- `archive/2026-07.md`: 173 session entries dated 2026-07-07 through
  2026-07-30.

Monthly archives are immutable historical evidence. Corrections belong in a
new current entry or durable decision, not in silent archive rewrites.

## Recording new work

For substantive sessions:

1. Update the applicable work index.
2. Add or supersede a durable decision when architecture, product behavior, or
   workflow changes.
3. Append only a concise current handoff here when future sessions need facts
   not already captured by `AGENTS.md`, decisions, plans, or work indexes.
4. Move accumulated dated entries into a monthly archive through the verified
   archival workflow before this file becomes a long-running journal again.

Restart handoffs must follow `templates/RESTART_HANDOFF.md`.
General session entries may use `templates/SESSION_ENTRY.md`.

## Pending restart handoff

### 2026-07-30 14:07 +02:00 - Pre-restart handoff

Reason for restart:

- User-requested controlled Windows workstation restart after completion and
  commit of the repository documentation cleanup.

Current task and conversation state:

- Completed: repository-root documentation cleanup, thematic `agents/`
  structure, monthly session-history archive split, and the read-only
  pre-restart runtime baseline.
- Pending: restart Windows and perform the complete post-restart verification.
- First action after restart: read `AGENTS.md`,
  `agents/decisions/DECISIONS.md`, and this handoff; run
  `git status --short`; confirm the new boot and startup task before checking
  services.

Working tree and deployment:

- `git status --short` was clean before this handoff was appended.
- This handoff intentionally modifies only
  `agents/history/SESSION_NOTES.md`.
- Tracked and deployed Caddyfile SHA-256 hashes matched before restart.
- No application code, configuration, runtime deployment, database data, or
  scheduler state was changed as part of restart preparation.

Sensitive and runtime artifacts:

- Do not print, change, delete, or commit `.env`, credentials, tokens, cookies,
  browser sessions, ProgramData proxy credentials, raw meter data, scheduler
  locks, or operational database contents.

Expected processes after restart:

- FastAPI/Uvicorn: one runtime on `127.0.0.1:8000`.
- Streamlit: one runtime on `127.0.0.1:8001`.
- Scheduler: one `main.py` runtime holding the scheduler process lock.
- Caddy: one runtime owning TCP 80/443 and `127.0.0.1:2019`.

Expected application state:

- Baseline Windows boot time was `2026-07-30 13:10:04 +02:00`; the new boot
  must be later than this handoff.
- Startup task `API_dashboard_caddy` was `Ready`; its last run was
  `2026-07-30 13:10:14 +02:00` with result 0. It must run again after the new
  boot with result 0.
- Expected listeners before restart were 80, 443, 2019, 8000, and 8001;
  temporary listeners 8010/8011 were absent.
- Local FastAPI live/ready, Streamlit health, and Caddy admin returned HTTP
  200.
- Scheduler reported `scheduler_running=true` with heartbeat
  `2026-07-30 14:05:24 +02:00`.
- The quarter-hour job, database-availability check, and kalorimetry import
  succeeded at approximately 14:05 with zero failures in the preceding 24
  hours.
- Protected kalorimetry prediction API access without a bearer token returned
  the expected HTTP 401.
- HTTP should redirect to HTTPS and the public dashboard should retain its
  existing authentication behavior.

Required post-restart checks:

1. Confirm the new Windows boot time is later than
   `2026-07-30 14:07 +02:00`.
2. Confirm `API_dashboard_caddy` ran after boot with result 0.
3. Confirm exactly the expected listeners 80, 443, 2019, 8000, and 8001 are
   present and temporary listeners 8010/8011 are absent.
4. Confirm local FastAPI `/health/live` and `/health/ready`, Streamlit
   `/_stcore/health`, and Caddy admin `/config/` return HTTP 200.
5. Confirm the scheduler heartbeat is newer than boot.
6. Wait for and confirm one post-boot quarter-hour job, database-availability
   check, and kalorimetry import with successful aggregate status.
7. Confirm the protected kalorimetry prediction route still returns HTTP 401
   without credentials.
8. Confirm tracked and deployed Caddyfile hashes still match.
9. Attempt the public HTTPS dashboard and users-exist route from the available
   environment; record a timeout as unverified rather than treating it as
   application failure when all local checks remain healthy.
10. Append the exact post-restart result here and stop to diagnose any
    listener, readiness, scheduler, import, hash, or authentication regression.

Known risks or accepted gaps:

- The public hostname previously timed out from the agent environment even
  while local Caddy and application health were good; external routing may
  require independent browser/network confirmation.
- Do not perform kalorimetry snapshot/scoring activation, scheduler feature
  activation, alert delivery, report delivery, or unrelated production writes
  during post-restart verification.

### 2026-07-30 14:20 +02:00 - Post-restart verification

- Windows booted at `2026-07-30 14:11:16 +02:00`, after the pre-restart
  handoff.
- Startup task `API_dashboard_caddy` ran at
  `2026-07-30 14:11:26 +02:00`, returned result 0, and was `Ready`.
- Expected listeners 80, 443, 2019, 8000, and 8001 were present under Caddy
  and the two Python application runtimes. Temporary listeners 8010/8011 were
  absent.
- Local FastAPI live/ready, Streamlit health, and Caddy admin returned HTTP
  200. The protected kalorimetry prediction route returned the expected HTTP
  401 without credentials.
- Scheduler heartbeat `2026-07-30 14:16:34 +02:00` was newer than boot.
  The first post-boot quarter-hour job completed successfully at 14:16, with
  successful database-availability check and kalorimetry import and zero
  failures for those checks in the preceding 24 hours.
- Tracked and deployed Caddyfile SHA-256 hashes matched.
- Public HTTPS dashboard, users-exist, protected API, blocked documentation
  routes, and HTTP redirect were unverified from the agent environment
  because every public-host request ended in `WebException`. This matches the
  known workstation reachability gap and is not classified as a local
  application regression.
- No application code, runtime configuration, production data, activation,
  alert delivery, report delivery, or manual scheduler job was changed.
