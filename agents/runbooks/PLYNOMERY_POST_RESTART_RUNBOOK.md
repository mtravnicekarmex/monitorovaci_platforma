# Plynomery Post-Restart Runbook

Prepared: 2026-07-27 14:16 +02:00

Purpose: load the completed gas prediction pipeline into the supported
production runtime, reconcile active-period score/event drift created by the
pre-change scheduler process, and finish pipeline checks 23-24 without
printing identifiers, measurements, credentials, tokens, cookies, recipients,
or raw event rows.

## Why the restart is required

The workstation booted at `2026-07-27 09:58:22 +02:00`. The startup task
loaded API, Streamlit, scheduler, and Caddy before the gas pipeline changes
were completed. Active gas selection run 21 was published later, at about
`2026-07-27 10:22 +02:00`.

The running scheduler therefore continued to create active-model scores using
the old global candidate path even though period-valid per-identifier
decisions already existed. A supported full-workstation restart is required
to load the current source into every production process.

Do not attempt to stop and recreate individual production processes from the
interactive session.

## Pre-restart baseline

- Windows startup task: `API_dashboard_caddy`
- Task state: `Ready`
- Last task result: `0`
- Local API liveness: HTTP 200
- Local API readiness: HTTP 200
- Local Streamlit health: HTTP 200
- Local Caddy admin API: HTTP 200
- Expected application listeners present:
  - Caddy: ports 80 and 443
  - Caddy admin: `127.0.0.1:2019`
  - FastAPI: `127.0.0.1:8000`
  - Streamlit: `127.0.0.1:8001`
- Temporary listeners 8010 and 8011 are absent.
- An additional non-application listener on Tailscale address/port 443 is
  expected and is not a Caddy duplication.
- Scheduler metrics were fresh at `2026-07-27 14:16 +02:00`.
- `.venv-production` uses Python 3.14.0 and `pip check` reports no broken
  requirements.
- Full project suite: `989 passed`.
- Targeted gas pipeline matrix: `423 passed`.
- `git diff --check`: passed.
- The working tree is intentionally dirty and contains the complete
  uncommitted pipeline implementation. Do not reset, checkout, clean, or
  baseline it during restart handling.
- Code integrity baseline must not be recreated for this dirty tree.
- Public hostname requests from this workstation timed out before restart.
  Local health was good. Treat public reachability as a separate post-restart
  check and do not infer application failure from workstation hairpin routing
  alone.

## Read-only database baseline

Latest active gas selection:

- selection run: 21
- active period: `2026-07-27 00:00` through `2026-08-03 00:00`
- measured identifiers: 18
- identifiers with active decisions: 18
- prediction-available decisions: 5
- `insufficient_history` decisions: 13
- selected model versions among available decisions: 2

Profile integrity:

- matching selected profile pairs: 5
- rows per pair: 672
- total selected profile rows: 3,360
- available decisions missing a pair: 0
- unavailable decisions with a profile pair: 0
- period/model mismatches: 0

Score drift across the complete active period:

- eligible measurements inspected: 1,026
- rows produced by the period-valid selected builder: 285
- intentionally unscored/unavailable rows: 741
- persisted active-identity scores: 285
- missing persisted selected scores: 0
- unexpected persisted scores: 0
- persisted scores inconsistent with selected builder/profile: 135
- inconsistent rows already processed by event handling: 135
- anomaly flags that change under correct recalculation: 10
- severity values that change: 0

Candidate profile run 21 was the last candidate rebuild. There was no later
candidate run after active snapshots, so this is runtime source drift rather
than a later model rebuild.

## Mandatory restart procedure

1. Confirm this runbook and the dated handoff in
   `agents/history/SESSION_NOTES.md` are still
   present.
2. Confirm `git status --short` contains the expected dirty pipeline files and
   no unexplained new change.
3. Confirm no database-writing job, report delivery, alert delivery, or manual
   rebuild is running.
4. Restart the complete Windows workstation through the normal supported
   operating-system restart.
5. Do not launch `main.py`, Uvicorn, Streamlit, or Caddy manually after boot.
   Allow `API_dashboard_caddy` to start the complete process set.

## Immediate post-boot checks

Perform these before any reconciliation write:

1. Windows boot time is newer than the handoff.
2. `API_dashboard_caddy` ran after boot, is in the expected state, and its last
   result is 0.
3. Expected production processes exist:
   - scheduler from `main.py`
   - FastAPI/Uvicorn
   - Streamlit dashboard
   - Caddy
4. Expected listeners exist:
   - ports 80 and 443 on Caddy
   - `127.0.0.1:2019`
   - `127.0.0.1:8000`
   - `127.0.0.1:8001`
5. Temporary ports 8010 and 8011 are absent.
6. Local endpoints return:
   - `/health/live`: HTTP 200
   - `/health/ready`: HTTP 200
   - Streamlit `/_stcore/health`: HTTP 200
   - Caddy admin `/config/`: HTTP 200 without printing its body
7. Through authenticated `Health systemu`, verify runtime, proxy, scheduler,
   database, and SmartFuelPass summaries without exposing tokens or raw data.
8. Verify public routing separately:
   - HTTPS dashboard loads
   - users-exist endpoint responds
   - protected API without bearer remains HTTP 401
   - `/docs`, `/redoc`, and `/openapi.json` remain HTTP 404
   - HTTP redirects to HTTPS
   - reviewed security headers remain present
9. If public requests still time out only from this workstation while local
   checks pass, test from an external client before diagnosing Caddy.
10. Confirm scheduler metrics heartbeat is newer than boot. The central
    `quarter_hour_job` slots are minutes `5,16,35,47` at second 5.

Stop and diagnose before reconciliation if any required local process,
listener, readiness, database, task, or scheduler check fails.

## Reconciliation safety contract

Do not run an ad-hoc SQL update and do not merely change the 135 numeric score
rows. Ten anomaly flags change, and all affected rows were already processed,
so score and event state must be reconciled together.

Before applying:

1. Re-run the aggregate-only step 23 audit.
2. Require active selection run 21 and the exact active period above.
3. Require 18 decisions, 5 available decisions, 13 insufficient-history
   decisions, 5 complete profile pairs, and zero profile-integrity failures.
4. Require the current global active score identity expected by run 21.
5. Build expected score rows through
   `_build_per_identifier_selected_score_rows`; do not read a global profile
   as fallback.
6. Produce a dry-run summary containing counts only.
7. Refuse to apply if identifiers/period/run differ, a selected profile is
   missing, an unavailable decision obtains a score, or any unexpected score
   cannot be related to an active decision.
8. Run away from a quarter-hour slot and coordinate with the
   `quarter_hour_job` lock. Do not race scheduler scoring/event handling.

Approved implementation shape for a later explicit apply:

- one database transaction;
- rebuild the global active score identity from the active period start for
  only internally determined affected identifiers;
- use active per-identifier selection for every measurement timestamp;
- retain the global active `model_version` on score rows;
- delete scores for an unavailable selection and create no replacement;
- rebuild affected event/state data consistently with corrected score flags;
- do not call alert delivery, report delivery, email, or unrelated scheduler
  jobs;
- use the existing reviewed outlier-repair score/event mechanics only after
  checking their alert-delivery side effects;
- run a pre-commit aggregate audit inside the transaction and roll back unless
  score mismatches, missing selected scores, unexpected scores, and
  unavailable-selection scores are all zero;
- commit once;
- print aggregate counts only.

The reconciliation write is not authorized merely by this runbook. Obtain
explicit user approval after the dry-run summary.

## Post-reconciliation checks

All must pass:

- active decisions: 18
- measured identifiers without decision: 0
- available decisions: 5
- insufficient-history decisions: 13
- missing available profile pairs: 0
- profiles attached to unavailable decisions: 0
- profile pair period/model mismatches: 0
- persisted active scores inconsistent with selected builder/profile: 0
- missing persisted selected scores: 0
- unexpected persisted scores: 0
- scores for unavailable decisions: 0
- rebuilt events are consistent with corrected anomaly flags
- no alert or report email was sent by reconciliation

After the next normal quarter-hour run, confirm new scores also have zero
selected-builder mismatches and that the scheduler checkpoint advances across
unavailable measurements.

## Change-specific UI/API verification

Using authenticated, authorized access:

- `Plynomery / Prehled`:
  - available device shows a prediction across the complete selected period;
  - insufficient-history device shows `Nedostupné`;
  - actual and cumulative-actual data stop at the last real measurement;
  - hourly, daily, and monthly granularities work.
- `Plynomery / Detail`:
  - 7-day, 31-day, and 24-month prediction layers load;
  - insufficient history shows `Nedostupné`;
  - existing metadata, averages, reset, photo, and measurement views remain
    usable.
- Prediction performance admin page shows active gas selection aggregates.
- Device-scoped prediction endpoints return HTTP 403 for an unauthorized
  device and do not open database access before authorization.
- Historical profile/series requests do not project the current/global profile
  backward.
- Weather-adjusted output is partial/unavailable when required HDD is missing,
  never zero-filled.
- No gas PDF is expected; the only gas report remains the model rebuild email.

## Completion order

1. Complete immediate post-boot checks.
2. Prepare and test the fail-closed reconciliation helper.
3. Run reconciliation dry-run and report aggregate results.
4. Obtain explicit approval for the database write.
5. Apply once, without alert/report delivery.
6. Re-run step 23 read-only aggregates.
7. Observe one normal quarter-hour run and recheck new-score source.
8. Mark step 23 complete.
9. Mark restart rollout step 24 complete.
10. Continue steps 25-26 and the recorded vodomery follow-ups.
