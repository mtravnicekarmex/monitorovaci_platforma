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

### 2026-07-31 10:31 +02:00 - Monitoring-facade pre-restart handoff

- Reason: FastAPI runs elevated and can only be refreshed through the
  workstation startup sequence. A controlled full restart is required to
  load the new read-only monitoring facade and its configured credential
  digest.
- Before restart, API live/ready and Streamlit health returned HTTP 200.
  Scheduler heartbeat was current at `2026-07-31 10:26:41 +02:00`.
- Startup task `API_dashboard_caddy` was `Ready`; its preceding run at
  `2026-07-30 14:11:26 +02:00` returned result 0.
- Expected listeners 80, 443, 2019, 8000, and 8001 were present. Existing
  Tailscale Serve listeners on port 443 were unchanged. Ports 8010, 8011, and
  reserved monitoring port 9443 were absent.
- The new monitoring route correctly remained HTTP 404 in the old API process.
  `.env` contained one syntactically valid
  `MONITORING_AGENT_TOKEN_SHA256` setting; its value was not printed.
- The remote center holds the corresponding 64-character bearer secret in an
  ACL-restricted local file accessible only to its operating identity and
  `SYSTEM`. Only the SHA-256 digest was shared with the monitored station.
- Relevant tests passed before restart: 53 focused monitoring-agent,
  monitoring-facade, system-health, and API-startup tests.
- Working tree contains the reviewed monitoring-facade, credential-client,
  tests, documentation, and `0.2.0-test` bundle changes. Do not revert or
  overwrite them during restart verification.
- After boot, verify the new boot time and startup-task result, expected
  listeners, API live/ready, dashboard health, current scheduler heartbeat,
  and that the monitoring facade returns HTTP 401 without a bearer
  credential. Do not print or copy the bearer secret.
- Do not configure Tailscale Serve port 9443 until local post-restart checks
  pass. Existing Tailscale Serve port 443 must remain unchanged.

### 2026-08-03 - Monitoring facade remote HTTPS handoff

- The 2026-07-31 restart completed successfully: boot and startup task were
  new, expected local listeners and health checks passed, the scheduler
  heartbeat was fresh, and the first post-boot quarter-hour run, database
  availability check, and kalorimetry import succeeded with zero 24-hour
  failures. The monitoring facade loaded and returned HTTP 401 without a
  credential. Tracked and deployed Caddyfile hashes matched.
- After local verification, the user approved and configured a persistent
  tailnet-only Tailscale Serve HTTPS listener on port `9443` to loopback
  FastAPI. Existing Serve port 443 remained unchanged and 9443 was not broadly
  bound to LAN interfaces.
- The `0.2.0-test` bundle ZIP and its ten-file manifest verified on the remote
  supervision center. Its separately stored credential completed one
  authenticated three-endpoint cycle with HTTP 200, schema-valid normalized
  observations and an agent-owned heartbeat.
- Remote authorization checks returned HTTP 401 without the credential,
  HTTP 401 when the monitoring credential was presented to the human-admin
  Health route, HTTP 404 for an unknown monitoring route, and HTTP 405 for
  POST on monitoring liveness.
- No token, credential path, tailnet DNS name, address, raw response body,
  production mutation, external delivery, task registration, or alert change
  was made or recorded.
- Next: define polling, timeout, retry, jitter, and self-health behavior, then
  execute the non-production cross-host failure-isolation proof. Credential
  rotation and Scheduled Task registration remain separate later gates.

### 2026-08-03 - Kalorimetry activation gates 1-8 complete

- The coherent pre-week forecast, current-period dry-run, and explicit
  snapshot approval gates passed for `[2026-08-03, 2026-08-10)` Prague.
  The atomic activation persisted and independently verified 8 active model-2
  decisions and 5,376 profile points; 6 unavailable identifiers received no
  fallback snapshot.
- After separate approval, latest-only scoring/event activation created the
  reviewed tables and checkpoints without applying historical scores/events.
  Current catch-up ended with scoring checkpoint equal to latest measurement,
  event checkpoint equal to latest score, zero unprocessed scores, zero link
  mismatches, zero events, and no enabled alert plan.
- Scheduler step 25 is implemented: the quarter-hour job runs import, active
  scoring, and approved event detection without alert delivery; the weekly job
  runs an idempotent forecast-gated snapshot rebuild. Manual operations share
  their parent job locks. The current-week production rebuild returned
  `verified_existing` with no write.
- The targeted regression matrix passed with `454 passed`; the complete suite
  passed with `1278 passed`; `git diff --check` passed. Local API live/ready,
  Streamlit health, and Caddy admin were HTTP 200, and the protected
  prediction-series route was HTTP 401 without credentials.
- Remaining gate: prepare and obtain approval for one whole-stack restart,
  then verify the first post-restart quarter-hour scoring/event metrics,
  snapshots, API/dashboard availability, checkpoints, delivery-disabled
  alert state, and historical read-only reconciliation.

### 2026-08-03 12:18 +02:00 - Kalorimetry pre-restart handoff

- Reason: load the completed step-25 scheduler integration into the production
  scheduler and finish activation-runbook gate 9. Restart must use the existing
  whole-stack Windows startup procedure; do not stop or recreate individual
  processes.
- Pre-restart boot was `2026-07-31 10:57:05 +02:00`. Startup task
  `API_dashboard_caddy` was `Ready`; its 2026-07-31 10:57:15 run returned 0.
- Listeners 80, 443, 2019, 8000, 8001, and tailnet-only 9443 were present;
  temporary 8010/8011 were absent. Tracked and deployed Caddyfile SHA-256
  hashes matched.
- API live/ready, Streamlit health, and Caddy admin were HTTP 200. The
  protected kalorimetry prediction route returned HTTP 401 without a token.
  Scheduler, quarter-hour job, kalorimetry import, and weekly job reported
  success with zero 24-hour failures for the recorded jobs.
- Exact current-week invariants before restart: 8 active decisions, 5,376
  profile points in 8 complete groups, 6 explicitly unavailable identifiers,
  zero link mismatches, scoring checkpoint equal to latest measurement, event
  checkpoint equal to latest score, zero unprocessed scores, zero events, and
  no enabled alert plan.
- The working tree intentionally contains the reviewed monitoring pilot and
  calorimetry activation/scheduler changes. The root test ZIP deletion was
  user-confirmed; its reviewed replacement is under `artifacts/monitoring_agent/`.
  Do not revert, delete, or overwrite these changes during restart.
- After restart, require a newer boot/task run, the same listener and Caddy
  invariants, healthy local services, a fresh scheduler heartbeat, and one
  successful post-boot quarter-hour run that records successful
  `kalorimetry_db_import`, `score_new_kalorimetry_measurements`, and
  `detect_kalorimetry_events_from_scores` metrics. Then repeat aggregate
  snapshot/checkpoint/event/API and historical reconciliation checks.

### 2026-08-03 14:12 +02:00 - Kalorimetry post-restart verification and metric-identity correction

- The workstation booted at 12:22:19 and startup task
  `API_dashboard_caddy` ran at 12:22:29 with result 0. Expected local
  listeners and tailnet-only 9443 were present; temporary 8010/8011 listeners
  were absent. Local API live/ready, Streamlit health, and Caddy admin were
  HTTP 200, protected prediction and monitoring routes were HTTP 401 without
  credentials, and tracked/deployed Caddyfile hashes matched.
- The scheduler heartbeat and repeated quarter-hour/database/import runs were
  current and successful with zero 24-hour failures. Production aggregates
  remained exact: 8 active decisions, 5,376 profile points in complete
  672-slot groups, zero link mismatches, aligned measurement/scoring/event
  checkpoints, zero unprocessed scores, 16 valid event-state rows, and zero
  events.
- Historical reconciliation remained read-only with zero mismatched or
  unexpected scores/events and zero anomaly-flag or severity changes.
  Historical score/event persistence remains intentionally unapplied.
- The scoring/event functions ran, but scheduled metrics combined vodomery,
  plynomery, and kalorimetry under their shared underlying function names.
  The same inherited collision affected plynomery runtime-model lookup and
  the vodomery/plynomery rebuild metric.
- `safe_call` now accepts an explicit scheduler `step_id`, which controls
  metrics, logs, and wrapped error targets. Scheduled plynomery and
  kalorimetry calls use their existing unique manual-step identities while
  legacy vodomery identities remain unchanged. No production process or data
  was changed by this correction.
- The focused scheduler, metrics, System Health, monitoring facade/agent, and
  dashboard regression set passed with `122 passed`; the complete suite passed
  with `1279 passed`; `git diff --check` passed.
- A separately approved whole-stack restart is still required to load the
  metric-identity correction and confirm the distinct production keys. The
  public hostname remained unverified from the agent environment because its
  bounded requests did not complete, matching the known reachability gap.

### 2026-08-03 14:45 +02:00 - Scheduler metric-identity pre-restart handoff

Reason for restart:

- Load the reviewed `safe_call(step_id=...)` observability correction so
  scheduled plynomery and kalorimetry steps record distinct metric, log, and
  wrapped-error identities instead of inherited shared function names.

Current task and conversation state:

- Completed: the correction and regression tests; the focused
  scheduler/metrics/Health/monitoring/dashboard matrix passed with
  `122 passed`, the complete suite passed with `1279 passed`, Python compile
  checks passed, and `git diff --check` passed.
- Pending: one approved whole-stack restart and the first post-boot
  quarter-hour verification of the distinct metric keys.
- First action after restart: read the mandatory project context, run
  `git status --short`, confirm a boot later than this handoff and a successful
  post-boot `API_dashboard_caddy` task run, then perform only read-only checks.

Working tree and deployment:

- `git status --short` matches the reviewed monitoring-pilot,
  kalorimetry-activation, scheduler, tests, documentation, root test-ZIP
  deletion, and replacement bundle changes already recorded in this handoff.
  No unexpected files appeared during restart preparation.
- The metric correction is in `core/scheduler/scheduler.py` with regression
  coverage in `tests/test_scheduler.py`. It is not loaded in the currently
  running scheduler process.
- Tracked and deployed Caddyfile SHA-256 hashes match. No Caddy deployment
  change is part of this restart.

Sensitive and runtime artifacts:

- Do not print, change, delete, or commit `.env`, credentials, bearer tokens,
  cookies, browser sessions, ProgramData proxy credentials, raw meter data,
  scheduler locks, or operational database contents.

Expected processes after restart:

- FastAPI/Uvicorn: one runtime on `127.0.0.1:8000`.
- Streamlit: one runtime on `127.0.0.1:8001`.
- Scheduler: one `main.py` runtime holding the scheduler process lock.
- Caddy: one runtime owning TCP 80/443 and `127.0.0.1:2019`.
- Existing Tailscale Serve listeners on tailnet-only 443/9443 must remain;
  temporary listeners 8010/8011 must remain absent.

Expected application state:

- Pre-restart boot is `2026-08-03 12:22:19 +02:00`. Startup task
  `API_dashboard_caddy` is `Ready`; its 12:22:29 run returned 0.
- FastAPI live/ready, Streamlit health, and Caddy admin are HTTP 200.
  Protected kalorimetry prediction and monitoring-facade liveness routes are
  HTTP 401 without credentials.
- Scheduler heartbeat was current at `2026-08-03 14:42:38 +02:00`.
  Quarter-hour job, database check, kalorimetry import, shared-name scoring and
  shared-name event metrics were successful at approximately 14:35 with zero
  failures in the preceding 24 hours; weekly job was also successful.
- Current kalorimetry invariants are 8 active decisions, 5,376 profile points,
  zero incomplete groups, zero score/snapshot link mismatches, scoring
  checkpoint equal to latest measurement 885936, event checkpoint equal to
  latest score 144, zero unprocessed scores, 16 valid event-state rows, and
  zero events.
- The new `score_new_plynomery_measurements`,
  `score_new_kalorimetry_measurements`, and
  `detect_kalorimetry_events_from_scores` scheduled metric keys are absent
  before restart, as expected for the old loaded process.
- HTTP should retain its existing HTTPS redirect and public-dashboard
  authentication behavior.

Required post-restart checks:

1. Confirm a boot later than this handoff and a startup-task run after that
   boot with result 0.
2. Confirm listeners 80, 443, 2019, 8000, 8001, and tailnet-only 9443;
   confirm 8010/8011 remain absent.
3. Confirm local API live/ready, Streamlit health, Caddy admin, protected
   prediction HTTP 401, monitoring-facade HTTP 401, and matching Caddy hashes.
4. Confirm a scheduler heartbeat newer than boot and wait for one successful
   post-boot quarter-hour job/database check/kalorimetry import.
5. Confirm successful distinct metrics with zero failures for
   `get_plynomery_runtime_model_version`,
   `score_new_plynomery_measurements`,
   `detect_plynomery_events_from_scores`,
   `score_new_kalorimetry_measurements`, and
   `detect_kalorimetry_events_from_scores`. Confirm the legacy vodomery keys
   remain present. Do not manually run the weekly job merely to exercise
   `rebuild_plynomery_profiles`.
6. Repeat the aggregate snapshot/profile/checkpoint/event consistency query
   and the historical read-only reconciliation; stop on any mismatch,
   unexpected event, enabled delivery, or checkpoint regression.
7. Attempt the public HTTPS/dashboard routes from the available environment;
   record an unresolved timeout as unverified when local checks remain healthy.
8. Record the exact result and mark pipeline step 28 complete only after these
   checks pass.

Known risks or accepted gaps:

- Existing combined success counts under legacy vodomery-style metric keys
  will remain inflated until their preceding 24-hour samples age out. Do not
  edit or reset the metrics file; the new medium-specific keys must begin
  naturally with the first post-restart scheduled calls.
- The public hostname has repeatedly been unreachable from the agent
  environment while local services remained healthy.
- This restart does not authorize snapshots, historical scoring/event writes,
  manual scheduler jobs, alert delivery, reports, email, credential changes,
  or unrelated production mutations.

### 2026-08-04 06:46 +02:00 - Kalorimetry final post-restart verification

- Windows booted at `2026-08-03 20:00:41 +02:00`; startup task
  `API_dashboard_caddy` ran at `20:00:51`, returned 0, and was `Ready`.
- Expected listeners 80, 443, 2019, 8000, 8001, and tailnet-only 9443 were
  present. Temporary listeners 8010/8011 were absent. Tracked and deployed
  Caddyfile SHA-256 hashes matched.
- Local FastAPI live/ready, Streamlit health, and Caddy admin returned HTTP
  200. The protected kalorimetry prediction and monitoring-facade routes
  returned the expected HTTP 401 without credentials.
- Scheduler heartbeat `2026-08-04 06:41:02 +02:00` was current. The latest
  quarter-hour job, database-availability check, and kalorimetry import were
  successful with zero failures in the preceding 24 hours.
- Distinct scheduled metrics for plynomery runtime-model lookup, plynomery
  scoring/events, and kalorimetry scoring/events were present, current, and
  successful with zero 24-hour failures. Legacy vodomery metric identities
  remained present; the metric-identity correction is verified in production.
- Current kalorimetry aggregates were exact: 8 active decisions, 5,376
  profile points in 8 complete 672-slot groups, zero incomplete groups, zero
  score/snapshot link mismatches, scoring checkpoint 886832 equal to the
  latest measurement, event checkpoint 656 equal to the latest score, zero
  unprocessed scores, 16 valid event-state rows, and zero events. Kalorimetry
  alert delivery remains absent and every generated alert plan is
  delivery-disabled by contract.
- Historical reconciliation for `[2025-07-28, 2026-05-18)` remained read-only:
  401,365 measurements, 395,149 eligible, 6,216 ineligible, 285,766 expected
  scores, 3,456 expected created and resolved event episodes, and zero
  mismatched or unexpected scores/events, anomaly-flag changes, or severity
  changes. Historical score/event persistence remains intentionally unapplied.
- Public HTTPS dashboard, users-exist, protected API, and HTTP redirect were
  unverified because bounded requests returned `WebException`, matching the
  documented agent-environment reachability gap while all local checks were
  healthy.
- No runtime configuration, credentials, production data, snapshots,
  historical scores/events, manual jobs, alert/report delivery, or email was
  changed. Kalorimetry pipeline step 28 and work item KAL-025 are complete.

### 2026-08-04 - Monitoring-agent polling and self-health step complete

- Monitoring-agent config contract version 2 now defines serialized
  60-second start-to-start cycles with 0-5 seconds jitter, three-second
  request timeouts, at most three attempts, and exponential 0.5/1.0-second
  backoff only for connection errors and timeouts.
- HTTP errors, invalid JSON, and schema errors fail closed without retry.
  Approved HTTP 503 readiness remains application evidence rather than a
  transport failure.
- Agent-owned heartbeat state is written as `polling` at cycle start and
  `healthy` or `degraded` at completion. Scheduler degradation with successful
  transport does not degrade observer self-health; transport loss does not
  claim that the scheduler itself stopped.
- A reproducible explicit-allowlist builder created `0.3.0-test` with ten
  runtime files and verified manifests. ZIP SHA-256 is
  `872F2277B5A03AA00807846E1EFA08F4F792AD29F8F7F65A4A93C745E9F3D57E`.
- The monitoring/facade/authorization matrix passed with `254 passed`; the
  focused monitoring-agent file passed with `32 passed`; Python compile and
  `git diff --check` passed.
- The side-by-side foreground cross-host failure-isolation procedure is
  recorded in
  `agents/runbooks/MONITORING_AGENT_FAILURE_ISOLATION_TEST.md`. The new bundle
  has not been transferred or run remotely. Target-loss/recovery execution,
  credential rotation, Scheduled Task registration, and external delivery
  remain separate approval gates.

### 2026-08-04 - Monitoring-agent remote runtime reset to dotenv/PyCharm project

- The user stopped the incomplete 0.3 remote setup and selected a clean
  supervision-center workflow: all local runtime values live in one ignored,
  ACL-restricted `.env`, with no session/persistent process variables, JSON
  config, or separate credential file in new bundles.
- `run_monitoring_agent.py` is the single entry point for PyCharm foreground
  testing and any later separately approved Windows automatic-start
  registration. Agent state is required to remain outside the code/config
  directory.
- The strict dotenv parser accepts standard or BOM-prefixed UTF-8, requires an
  exact monitoring-only schema, rejects duplicates, unknown keys,
  placeholders, unsafe endpoints and state paths, and excludes the bearer
  from repr and safe output.
- `0.4.0-test` contains 11 explicit project/runtime files plus both manifests,
  `.env.example`, and `.gitignore`, but no real `.env` or operational state.
  ZIP SHA-256 is
  `A6C9DCF82137D252519A05E705CF05D6B1252A4DCA74974037602231088FC767`.
- The focused suite passed with `44 passed`; the combined
  monitoring/facade/authorization matrix passed with `267 passed`; Python
  compile and `git diff --check` passed.
- The new archive has not been transferred. Remote `.env` provisioning,
  foreground HTTPS verification, failure isolation, credential rotation, and
  Windows automatic startup remain separate next gates.
