# Kalorimetry Monday Activation Runbook

Date prepared: 2026-07-30

Target return: Monday 2026-08-03 morning, Europe/Prague.

Status: mandatory pending handoff. Do not activate before completing the
read-only gates below.

## Objective

Finish the kalorimetry prediction pipeline safely after the first archived
nine-day Sunday forecast run. The intended target period is the Prague
calendar week:

- start: 2026-08-03 00:00 inclusive;
- end: 2026-08-10 00:00 exclusive.

This runbook does not itself authorize production snapshot, score, event,
alert, report, scheduler, or restart actions. Observe the explicit approval
gates.

## Known baseline

- Measurement backlog is current. PostgreSQL matched the current MSSQL source
  checkpoint and all 14 identifiers had eligible observations through
  2026-07-26.
- Forecast synchronization requests nine days and archives rows by composite
  `(forecast_run_at, datetime_hour)` identity.
- The scheduled daily meteo sync runs at 00:15 Prague time. The Sunday
  2026-08-02 run should be the first issuance capable of covering the complete
  target week plus its trailing 24-hour HDD input.
- The current week beginning 2026-07-27 must not be reconstructed from a run
  issued after that Monday.
- Historical snapshot backfill is complete through 2026-05-18.
- Current selection/profile/validation tables and scoring/event/checkpoint
  tables have not been activated.
- Alert delivery remains disabled. No kalorimetry consumption or model report
  delivery has been approved.

## Gate 1 - Start-of-session safety

- Read `AGENTS.md`, `DECISIONS.md`, `SESSION_NOTES.md`, this runbook, and
  `KALORIMETRY_PREDICTION_PIPELINE_PLAN.md`.
- Run `git status --short`; preserve all existing user and pipeline changes.
- Check Windows boot time, startup task result, Caddy/API/Streamlit listeners,
  FastAPI readiness, Streamlit response, scheduler heartbeat, and recent
  quarter-hour/import status.
- Do not restart or recreate individual production processes.
- Use aggregate output only. Do not print identifiers, raw measurements,
  credentials, recipients, tokens, cookies, or forecast payloads.

## Gate 2 - Sunday forecast audit (read-only)

Confirm all of the following for the target period:

- one coherent forecast run exists with `forecast_run_at` strictly before
  2026-08-03 00:00 Prague;
- the selected run is the newest eligible pre-week issuance;
- it contains every raw UTC hour required for the target week and the
  preceding trailing HDD window;
- exactly 168 trailing-24-hour HDD features can be derived;
- no value is filled from zero, a training mean, stale weather, a different
  run, or post-week-start actual weather;
- archive identity and composite primary key remain intact.

If any item fails, stop. Run meteo sync only if the scheduled Sunday run
failed or is incomplete, then repeat this gate. A manual run issued on Monday
is not eligible for the target week.

## Gate 3 - Current-period production dry-run (read-only)

Run the aggregate-only kalorimetry production dry-run for the target period.
It must confirm:

- observations are current through the latest completed pre-week interval;
- all eight validation folds contain observations;
- candidate validation coverage is at least 85 percent;
- every selected identifier has at least eight matched folds;
- WAPE, MAE, RMSE, and bias are finite;
- candidate rankings and fallback reasons are deterministic;
- selected candidates have deployable profiles;
- every available profile contains exactly 672 unique 15-minute points;
- unavailable identifiers and their aggregate reasons remain explicit;
- no table bootstrap, snapshot persistence, scoring, event processing,
  alerting, report delivery, or email occurs.

Record only aggregate counts and distributions. Review unusually high WAPE,
winner/fallback distribution, and every unavailable-reason category before
proceeding.

## Approval gate A - Current snapshot activation

Stop and obtain explicit user approval after presenting the Gate 2 and Gate 3
aggregate results.

Approval must name:

- the exact target period;
- available and unavailable identifier counts;
- winner and fallback distributions;
- coherent forecast coverage;
- expected decision and profile-point counts;
- confirmation that unavailable identifiers will not receive a selected
  snapshot or fallback profile.

Without approval, do not create current selection/profile/validation tables
and do not persist snapshots.

## Gate 4 - Controlled current snapshot write

After approval:

- build and validate the complete decision/profile persistence plan before SQL;
- persist only `medium_key='kalorimetry'` and the exact target period;
- use the approved active/current selection identity, not historical-backfill
  identity;
- write decisions and their exact selected 672-point profiles atomically;
- never persist an unavailable identifier as selected;
- stop and roll back on identity, model, count, profile, period, or content
  mismatch;
- independently reload and verify exact counts, model identities, half-open
  validity, and profile completeness before continuing.

Do not activate scoring in the same approval or transaction.

## Approval gate B - Scoring and event-state activation

Present the verified snapshot state and the existing reconciliation impact
baseline. Obtain separate explicit approval to:

- create scoring and scoring-checkpoint tables;
- choose checkpoint bootstrap behavior;
- create event and event-checkpoint tables;
- process scores/events.

The earlier historical estimate was 285,766 expected scores and 3,456 created
event episodes for the controlled historical period. Decide explicitly
whether activation begins at the latest measurement checkpoint or includes a
separately controlled historical apply. Never infer this choice.

Alert delivery remains disabled regardless of scoring/event approval.

## Gate 5 - Controlled scoring and event activation

After approval:

- create only the reviewed kalorimetry score/checkpoint tables;
- run a bounded pilot batch;
- verify score identity, selected candidate identity, decision/profile audit
  references, checkpoint movement, unavailable/ineligible counts, and
  idempotency;
- run a bounded event pilot with only `SPIKE` and
  `SUSTAINED_HIGH_USAGE`;
- verify event state, processed-score flags, and event checkpoint atomically;
- confirm every generated alert plan has `delivery_enabled=False`;
- repeat the aggregate score/event reconciliation;
- stop on missing selected profile, identity mismatch, unexpected score/event,
  severity change, or checkpoint inconsistency.

## Gate 6 - Scheduler integration (pipeline step 25)

Only after current snapshots and scoring/event pilots verify:

- retain the existing quarter-hour `kalorimetry_db_import`;
- add active scoring and event processing to `quarter_hour_job` with the shared
  job lock, database preflight, `safe_call`, metrics, and manual-run contracts;
- do not add alert delivery;
- add weekly current-period rebuild to `weekly_job` after weather provenance
  preflight;
- keep cron definitions exclusively in `core/scheduler/job_schedule.py`;
- add manual operations for rebuild, scoring, and events with the same lock
  names as their scheduled parent jobs;
- add no kalorimetry email/report operation unless recipients and delivery
  receive separate approval;
- verify scheduler tests, lock behavior, failure isolation, and metric names.

## Gates 7 and 8 - Regression closure

Complete pipeline steps 26 and 27:

- run the full targeted kalorimetry matrix covering import, time semantics,
  candidates, weather provenance, backfill, snapshots, scoring, events,
  outlier repair, APIs, dashboards, consumers, and scheduler;
- run the complete project test suite;
- run read-only production audits for active snapshots, exact 672-point
  profiles, score/event/checkpoint consistency, API availability, and
  scheduler state;
- record exact pass counts and aggregate invariants in `SESSION_NOTES.md`;
- stop on any unexpected worktree change or production mismatch.

## Gate 9 - Rollout and restart

Complete pipeline step 28 only after all prior gates:

- prepare the exact restart/handoff summary;
- obtain restart approval;
- restart using the established whole-stack procedure, never by stopping or
  recreating individual processes;
- verify startup task, Caddy, API, Streamlit, scheduler heartbeat, scheduled
  jobs, current active snapshots, dashboard prediction availability, scoring
  checkpoints, event consistency, and delivery-disabled alert plans;
- repeat aggregate reconciliation after restart;
- update `AGENTS.md`, `DECISIONS.md`, `SESSION_NOTES.md`, and the active plan
  with concrete results.

## Hard stop conditions

Stop without activation if:

- no complete pre-week coherent forecast run exists;
- fewer than 168 HDD features are available;
- observations or validation folds are stale/incomplete;
- an available decision lacks exactly 672 profile points;
- persistence identity conflicts with existing state;
- an unavailable identifier would receive a fallback snapshot;
- scoring requires an unapproved historical apply;
- any alert delivery path is enabled;
- a recipient or report scope is inferred rather than approved;
- an unexpected worktree or production-state change appears.

## Monday completion target

The pipeline is complete only when steps 25-28 are checked off with exact
verification results, production runtime is healthy after the approved
restart, snapshots and score/event state reconcile, dashboards expose the
expected availability, and alert/report delivery remains within explicitly
approved scope.
