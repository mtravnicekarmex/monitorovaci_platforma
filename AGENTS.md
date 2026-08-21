# AGENTS.md

Project: `monitorovaci_platforma`

Purpose: persistent operating context for future agent-assisted sessions. Read this file before making changes.

## Start of Every Session

1. Read `AGENTS.md`, `agents/decisions/DECISIONS.md`, and
   `agents/history/SESSION_NOTES.md`.
2. Run `git status --short` and treat the result as part of the session context.
3. Do not assume a clean working tree. This project can contain user changes and runtime artifacts.
4. Never revert, overwrite, or delete changes you did not make unless the user explicitly approves it.
5. If unexpected changes appear while working, stop and ask the user how to proceed.
6. Keep secrets and runtime data private. Do not print cookie values, tokens, credentials, or raw operational data unless the user explicitly asks and the security impact is clear.
7. Prefer read-only inspection until the user asks for implementation or explicitly approves file writes.

## Repository Root Hygiene

- Keep the repository root clean. Put every new source, document, generated
  artifact, shortcut, backup, and runtime file in the narrowest appropriate
  subdirectory whenever the required tool or runtime permits it.
- The approved root-file allowlist is enforced by
  `tests/test_repository_hygiene.py`. It is limited to conventional repository
  metadata and configuration, dependency manifests, the local `.env` contract,
  and the established root runtime entry points `main.py`, `Caddyfile`, and
  `start_api_dashboard.bat`.
- A new root file is allowed only when an external tool or an existing runtime
  contract requires that exact location. Document the reason and update the
  allowlist in the same reviewed change; convenience alone is not sufficient.
- Store generated output under `artifacts/`, operational data under `data/`,
  operator documentation under `agents/`, reusable commands under `scripts/`,
  and component-owned files inside the component directory. Do not use the
  repository root as temporary storage.
- Keep live secrets out of tracked subdirectories. The currently established
  ignored root `.env` remains an explicit compatibility exception; additional
  secret backups belong in a protected external configuration directory.

## Documentation Contract

These files are part of the daily workflow:

- `AGENTS.md`: operating rules, project map, and practices for future agents.
- `agents/decisions/DECISIONS.md`: durable architectural, product, and workflow decisions.
- `agents/history/SESSION_NOTES.md`: short current baseline, handoff, and
  archive index. Detailed immutable session history lives under
  `agents/history/archive/`.
- `agents/work/`: concise active, backlog, blocked, and completed work indexes.

At the end of every substantive session:

- Propose updates to these files when architecture, workflow, decisions, or project state changed.
- Record concrete dates instead of relative dates.
- Keep notes factual and short enough to be useful.
- Do not silently rewrite historical decisions. Add a new decision or mark the previous one as superseded.
- If the user asks to approve final text before saving, show the exact final version before writing.

## Project Map

- `main.py`: scheduler entry point. Imports and runs the main scheduler.
- `monitoring_agent/`: reviewed local source and test package for the
  independent remote read-only scheduler observer and its loopback-only
  synthetic Health server. Remote audit v2 proved that the
  4,545.121-second gap was between healthy cycles rather than inside an HTTP
  request; local Windows event correlation identified a supervision-station
  shutdown/restart. Remote `0.6.0-test` then verified prospective lifecycle
  evidence but exposed a false early-start finding across two process runs.
  Remote `0.6.1-test` verified the corrected cross-run timing and exposed
  historical process interleaving (`A-B-A-C`). Locally reviewed `0.6.2-test`
  acquires a non-blocking OS writer lock before lifecycle, heartbeat,
  observation, or HTTP activity and audit contract 5 distinguishes concurrent
  starts/run reentry from unclean restart evidence. Remote foreground proof
  verified fail-closed second-writer rejection with zero state writes and
  successful lock release after Ctrl+C. `0.7.0-test` adds the approved
  authenticated System Runtime facade/client projection, observation contract
  3 endpoint-set identity, and audit contract 6 compatibility with retained
  three-endpoint 0.6 history. On 2026-08-06 the new facade and remote 0.7
  bundle were verified, the existing state and credential were retained, and
  the endpoint set was migrated to `live`, `ready`, `system_scheduler`, and
  `system_runtime`. The agent now runs as the `MonitoringAgentTest` Windows
  Scheduled Task under `SYSTEM` on the separate supervision center. A real
  center reboot proved one logical startup writer, continued observations,
  healthy recovery, and zero new concurrent-start, run-reentry, unclean, or
  abandoned-run evidence. Windows exposes the one venv invocation as a
  two-process launcher/interpreter tree; do not mistake raw process count two
  for two writers. While the task is running, only `--check-config` and
  `--audit-state` are safe concurrent commands. The continuous observer remains
  test-mode. As of 2026-08-21, automatic runtime delivery is enabled only as
  controlled test delivery through `DELIVERY_AUTOMATION_ENABLED=true`,
  `DELIVERY_TEST_RECIPIENT`, and the existing Outlook test credentials; it
  sends at most one due pending outbox item after a completed cycle and still
  has no production-recipient, application mutation, remediation, process
  control, provider-execution, alert-suppression, or legacy-alert replacement
  capability.
  `0.8.1-test`
  supersedes the undeployed `0.8.0-test` candidate. It retains observation
  contract 4 / endpoint set 3 and audit contract 7, adding strict safe
  projections for detailed Scheduler Health, System Database, Proxy, and
  SmartFuelPass plus a credential-free direct public-page probe from the
  supervision center, for nine observations per cycle. The 0.7-to-0.8.1
  migration used the approved one-time planned hard stop, preserved the real
  `.env` values and append-only state policy, and established the clean
  `monitoring-agent-state-ops002` baseline. Env-v1 bridge, target
  scheduler-detail timezone restart, env-v2 nine-endpoint proof, and
  continuous `MonitoringAgentTest` restoration all passed. On 2026-08-14 the
  task was `Running` under `SYSTEM`, latest audit-v7 heartbeat was `healthy`
  with nine observations and zero latest transport failures, and there was no
  new concurrent-start, run-reentry, unclean, abandoned, incomplete, or
  overlap evidence. Roadmap item 1 is complete. Local item 2 source then added
  incident-rule version 1 as a pure deterministic lifecycle layer with no
  persistence, outbox, delivery, `.env` reads, network access, target mutation,
  or legacy-alert replacement. Local item 3 source added bounded
  `incident_state.json` persistence, delivery-intent outbox state, env
  contract 3 retention limits, and bounded observation retention; the outbox
  still has no sender, recipients, credentials, message body, network access,
  or delivery authorization. Local item 4 source added pure report and
  programming-agent prompt renderers over supplied normalized facts and
  optional incident-store snapshots; reports keep verified facts, rule
  conclusions, historical qualifications, evidence gaps, and hypotheses
  separate, and prompts are bounded draft-only text with no authorization for
  execution, delivery, mutation, process control, or alert replacement.
  Local item 5 then added a disabled-by-default test-only
  delivery adapter over incident outbox items, with a controlled test
  recipient from `DELIVERY_TEST_RECIPIENT`, an in-memory recipient allowlist
  derived from that same value, supplied report bodies by `report_reference`,
  sanitized results, and a standalone `send_email_outlook()` implementation
  that mirrors the local alarm-email Office365 STARTTLS pattern using
  `O_EMAIL` and `O_APP` for login/default sender, with `EMAIL`/`APP` accepted
  only as compatibility fallback. `monitoring_agent/delivery_cli.py`
  adds optional recipient hashing diagnostics, synthetic local outbox
  preparation, dry-run, and confirmed `send-due` entry points; real sending
  requires `--confirm SEND_TEST_DELIVERY`, exact `report_reference`,
  `DELIVERY_TEST_RECIPIENT`, `O_EMAIL`, `O_APP`, and a sanitized report file
  that is not `.env`. Delivery-test recipient variables avoid the
  `MONITORING_AGENT_` prefix so they do not collide with the strict runtime
  schema; the polling runtime validates only `MONITORING_AGENT_*` keys, so
  these non-prefixed delivery keys may live in the same local `.env`. On
  2026-08-14 the supervision station verified Git commit
  `5cfc5916d3e83cdcc1eecd34f3f2719d62ec351c`, hashed the configured test
  recipient without printing it, prepared an isolated synthetic outbox/report,
  dry-ran one due item, and executed one explicitly confirmed `send-due`
  command that returned `status="sent"`, `action="opened"`,
  `attempt_count=1`, and no error code. A follow-up dry-run for the same
  `idempotency_key` returned `due_count=0`, proving the sent synthetic item was
  no longer pending. At that point the delivery adapter was not wired into the
  polling loop and did not authorize further external delivery, production
  recipients, delivery channels, or legacy-alert replacement.
  Local item 6 then added pure draft-only interpretation over supplied
  report snapshots with at least one confirmed active incident. The
  interpretation policy records provider/model names, timeout, cost ceiling,
  prompt/output bounds, and item-count bounds, but all permission-style flags
  for network, state mutation, process control, delivery, and alert
  suppression must remain false. It adds no `.env` keys, provider
  credentials, network client, polling-loop integration, or state writes.
  Disabled, candidate-only, missing-provider, provider-failed, invalid, or
  unsafe-output cases fall back to the deterministic report and cannot
  suppress legacy alerts. Local item 7 source preflight adds
  `monitoring_agent/shadow_pilot.py`, a pure shadow-only comparison contract
  for supplied sanitized monitoring-agent and legacy-alert events over one
  reviewed period. It computes matched detections, confirmation/recovery
  delay, duplicate counts/rates, false positives, false negatives,
  agent/legacy-only recoveries, and blind spots without `.env` reads, DB
  access, endpoint polling, delivery, provider calls, state writes, process
  control, remediation, or alert suppression. 2026-08-17 item 7 source
  then added `monitoring_agent/runtime_shadow.py`, which runs deterministic
  incident evaluation after each completed polling cycle, persists bounded
  `incident_state.json`, emits sanitized `shadow_incidents`, and advances
  `--audit-state` to audit contract 8. It adds no `.env` variable and still
  does not claim or send outbox items, call providers, mutate the monitored
  application, control processes, remediate, or suppress/replace legacy
  alerts. This source was pushed to the standalone Git repository as commit
  `207fc1d38d066cdc642dc86bc0cc0b2b6c817cfc`; remote activation exposed an
  env-v2 source compatibility bug because `RuntimeSettings.load()` accepted
  the env-v2 key set but did not load `MONITORING_AGENT_EXTERNAL_WEB_URL` for
  `external_web`. Follow-up commit
  `e23f5f893d76951995a8b6df833e60aadb96a858` fixes that bug with no `.env`
  change required. The supervision station then proved this commit with
  foreground `--once`, running `MonitoringAgentTest`, audit-v8 latest
  heartbeat `healthy`, and `shadow_incidents.present=true`,
  `mode="shadow_only"`, `delivery_enabled=false`. Retained lifecycle/sequence
  findings from the activation are planned restart artifacts. Follow-up source commit
  `3c6502c74d478a7518d3bbc37f7799951bbbaba4` adds a file-based
  `monitoring_agent.shadow_pilot_cli` for exporting comparable agent events
  from explicit `incident_state.json`, consuming supplied sanitized
  `legacy_alert` event JSON, and writing JSON/Markdown comparison outputs
  only. It has a 22-file Git manifest SHA-256
  `f10e0392b2e294956f522f62df270859fad7c153ba4dee6a7fbac2fbba760c11` and is
  remote-proved on the supervision station with valid config, healthy
  audit-v8, and `shadow_incidents.present=true`. Roadmap items 1 through 7
  are complete as of 2026-08-17. Item 7 closed with a real healthy no-event
  reviewed comparison plus file-only synthetic comparison proof for
  matched detection/recovery, false-positive, false-negative, duplicate,
  blind-spot, and delay metrics. Legacy alerts remain authoritative and no
  alert replacement, production delivery, real provider execution,
  remediation, or process control is approved.
  Earlier in item 7, the supervision station pulled commit
  `3e7b94e9045527a1254b10066a3a34493577f025`; `--check-config` stayed valid
  with nine endpoints, env contract 2, and test mode, and audit-v7 retained a
  healthy latest heartbeat with nine observations, zero latest transport
  failures, 323 complete cycles, valid ordering/retry/timing, and no new
  lifecycle or writer anomalies.
  Continue from item 8 in
  `agents/plans/monitoring/MONITORING_AGENT_IMPLEMENTATION_ROADMAP.md`.
- `https://github.com/mtravnicekarmex/monitoring_agent_0.4.0`: standalone
  public repository for the minimal remote test project. Verified `master`
  commit `3c171cf49615cf792211f3c992320dade539ccc4` matches the complete
  `0.4.1-test` manifest, contains no real `.env` or agent state, and is not a
  clone of the complete platform repository. `0.6.2-test` is remotely verified
  against the existing contract-v2 0.6 state for foreground single-writer
  rejection and lock release. The supervision center's deployed
  `0.7.0-test` came from the separately verified ZIP; this does not imply that
  the public repository advanced beyond its verified 0.4.1 commit. The
  included unsigned startup helper was not executed because the center uses
  `Restricted` PowerShell policy; an elevated, semantically equivalent
  registration created and restart-verified the test task without changing or
  bypassing that policy.
- `https://github.com/mtravnicekarmex/monitoring-agent-0.8.1`: standalone
  public repository for the monitoring-agent test checkout. Verified on
  2026-08-14 at commit `02a90a4ae887867d20819e4b2b618d86f750c48d` with the
  original 0.8.1 bundle manifest SHA-256
  `18A3E477E724EEA61F3EFDCBE303BEBE4DC298A4D646D37FE643D6CD9C49CBB1`.
  On 2026-08-14 the user switched the test iteration workflow from per-change
  ZIP bundles to direct Git pulls. Commit
  `5cfc5916d3e83cdcc1eecd34f3f2719d62ec351c` was pushed to `master` with the
  local item 2-5 candidate source, including incident rules, bounded
  incident/outbox state, pure report/prompt rendering, and the
  `O_EMAIL`/`O_APP`/`DELIVERY_TEST_RECIPIENT` test delivery path. Commit
  `86ee42b058c74675976904c1e51a2f3677c5f138` was then pushed to `master`
  with item 6 draft/fallback interpretation source and manifest updates.
  Commit `3e7b94e9045527a1254b10066a3a34493577f025` was then pushed to
  `master` with item 7 shadow-pilot comparison source and manifest updates.
  Commit `207fc1d38d066cdc642dc86bc0cc0b2b6c817cfc` was then pushed to
  `master` with item 7 runtime shadow incident persistence, audit contract 8,
  and a 21-file Git manifest SHA-256
  `4011bb7de330b30371199123dca41aabaaddecd267293dadf990c91f57445287`.
  Commit `e23f5f893d76951995a8b6df833e60aadb96a858` was then pushed to
  `master` with the env-v2 external-web URL compatibility fix and a 21-file
  Git manifest SHA-256
  `b15c3d6288352c051a30e5693ea710b19b826d7c62bd6e803be0b79163e7d113`.
  This commit is remote-proved on the supervision station with audit-v8
  runtime shadow persistence and a running Scheduled Task. Commit
  `3c6502c74d478a7518d3bbc37f7799951bbbaba4` was then pushed with the
  file-based shadow-pilot comparison CLI and a 22-file Git manifest SHA-256
  `f10e0392b2e294956f522f62df270859fad7c153ba4dee6a7fbac2fbba760c11`; the
  supervision station pulled and verified it with env contract 2, endpoint
  count 9, healthy audit-v8 latest heartbeat, zero latest transport failures,
  and `shadow_incidents.present=true`, `mode="shadow_only"`,
  `delivery_enabled=false`. Commit
  `f6583d80a77695b3f4a094337251c6835b389b59` was pushed on 2026-08-21 with
  item-9 file-only orchestrator modules
  `monitoring_agent/orchestrator.py`,
  `monitoring_agent/orchestrator_cli.py`, and
  `monitoring_agent/orchestrator_export_cli.py`; the regenerated Git manifest
  declares 25 runtime files and has SHA-256
  `37e2967efa4edbf5cfcfdeaa5a9bb8e073ef417fd2499ed058cf7085a8daf61b`. The
  supervision station pulled and verified this commit on 2026-08-21:
  `--check-config` returned endpoint count 9, env contract 2, and test mode,
  and `orchestrator_export_cli wrap-remote-audit` wrote `remote-audit.json`
  with audit contract 8 and `captured_at="2026-08-21T05:21:19.603716Z"`.
  A 180-second follow-up runtime sample on 2026-08-21 showed
  `MonitoringAgentTest` `Running`, audit-v8 latest heartbeat `healthy`, nine
  latest observations, zero latest transport failures, valid endpoint/retry
  contracts, no in-progress/incomplete observations, and no current
  concurrent-start, run-reentry, overlap, or process-run-transition evidence.
  Retained lifecycle counts
  `unclean_restart_count=3`, `start_while_prior_run_open_count=3`, and
  `abandoned_unclosed_run_count=2` are activation/restart history, not by
  themselves current second-writer proof. Shadow incidents remained
  `mode="shadow_only"` and `delivery_enabled=false`, with
  `active_state_count=1` and `outbox_pending_count=11`; these counts require
  follow-up analysis before any delivery or alert-layer action.
  Follow-up sanitized incident-state inspection on 2026-08-21 confirmed the
  active state is `endpoint:system_scheduler`, opened at
  `2026-08-20T00:17:37.512339+02:00`, with
  `last_reason="endpoint_payload_status:degraded"`. The user identified the
  corresponding operational source as the last two days' midnight
  `daily_job` failure in `SOFTLINK_save_to_database_all`. The outbox contains
  only one pending `opened` item for `endpoint:system_scheduler`; the
  remaining pending items are older `system_runtime` and
  `target_wide_outage` intents, so this is not repeated email-delivery
  creation. Standalone commit
  `601a50587c73627835d4860b2212a82a92670f12` was pushed on 2026-08-21 to
  collapse redundant unchanged `updated` transition records, document the
  steady-state `300` second poll interval with `30` second jitter, and
  regenerate the 25-file Git manifest with SHA-256
  `07e08ccd56275a30e0169b863c60aee07241ba2f1c7126fb19989382c2c1a349`.
  The supervision station pulled and verified this commit on 2026-08-21:
  `git rev-parse HEAD` returned the exact commit, `--check-config` returned
  endpoint count 9 / env contract 2 / test mode, audit contract 8 reported
  `poll_interval_seconds=300.0`, `poll_jitter_seconds=30.0`, latest heartbeat
  `healthy`, and zero latest transport failures. After a confirmed stop with
  no remaining agent process, the restarted task produced a new
  310.977-second scheduled interval inside the 332-second allowed maximum.
  The transition-compaction check then showed no new repeated
  `endpoint:system_scheduler` unchanged `updated` records after the restarted
  300-second runtime began.
  Standalone commit `19919303fe50a280ca7e2c84b10c9a66887c9f05`
  then added a sanitized `review-outbox` CLI, and commit
  `7390aeb03303736a34d924dc6c229ab85bb1c1d5` added
  `skip-outbox` for operator-skipping selected pending items without sending.
  The supervision station verified one manually confirmed test email for
  `endpoint:system_scheduler/opened`, then used `skip-outbox` to mark the
  remaining 14 historical pending intents as `dead_letter` with
  `last_error_code="operator_skipped"`, leaving outbox counts at
  `sent=1`, `dead_letter=14`, and `pending=0`.
  Standalone commit `b6f4e047d59d14d0e34ac61c1a4e270b386f6ae9`
  was pushed on 2026-08-21 with `monitoring_agent/runtime_delivery.py`, an
  explicit non-`MONITORING_AGENT_` `DELIVERY_AUTOMATION_ENABLED` gate, runtime
  wiring after completed observation cycles, sanitized deterministic report
  bodies from `incident_state.json`, and a 26-file Git manifest SHA-256
  `429fac118d8e67bbadd8e1b53b55154953eba0a07aafd1225ec3ed40f68371cc`.
  Local verification for this commit passed with 19 runtime-delivery/shadow/
  delivery tests, 89 main monitoring-agent tests, compileall, standalone
  env-v2 `--check-config`, and fake-transport smoke proof that exactly one
  due item is marked sent. The supervision station pulled, enabled
  `DELIVERY_AUTOMATION_ENABLED=true`, restarted `MonitoringAgentTest`, and
  verified audit contract 8: task `Running`, latest heartbeat `healthy`, nine
  latest observations, zero latest transport failures,
  `shadow_incidents.delivery_enabled=true`, `outbox_pending_count=0`,
  `outbox_sent_count=1`, `outbox_dead_letter_count=14`, and update time
  `2026-08-21T11:08:28.897356+00:00`. The remaining active state is still
  one `endpoint:system_scheduler` incident; if it later recovers, the first
  recovery outbox item is expected to be sent automatically to the configured
  test recipient only.
  Treat the pulled Git commit hash as the active test-checkout identity; the original
  0.8.1 ZIP identity remains historical release evidence only until a new
  bundle is explicitly built.
- `core/db/connect.py`: SQLAlchemy database connections for PostgreSQL and MSSQL, configured through `python-decouple`.
- `core/scheduler/job_schedule.py`: single source of truth for APScheduler cron schedules. As of
  2026-08-21 the scheduled `daily_job` description is intentionally only
  `Meteo sync.` because SOFTLINK electric-meter imports are paused until the
  changed SOFTLINK credentials/login path are resolved.
- `core/scheduler/scheduler.py`: scheduler execution, locks, metrics, manual run specs, and alert emails.
  The `daily_job` now uses an independent-step runner so a failing independent
  step does not prevent later independent steps from running; it raises one
  aggregate `SchedulerContextError` after attempted steps. The SOFTLINK
  measurement import and `elektromery_softlink_monitoring_import` are removed
  from the scheduled and manual scheduler registry until SOFTLINK login is
  restored. `SOFTLINK_save_to_database_all()` lazy-loads SOFTLINK credentials
  and import modules only when explicitly called. When SOFTLINK returns, port
  `SOFTLINK_data_z_dotazu.py` to the more robust saved-session/API-validation
  pattern used by `SOFTLINK_data_zarizeni.py` before re-adding it.
- `core/scheduler/metrics.py`: scheduler metrics persistence in `core/scheduler/logs/scheduler_metrics.json`.
- `core/scheduler/database_availability_state.py`: local SQLite state and
  transition-event persistence for PostgreSQL/MSSQL availability.
- `local_monitoring_agents/database_availability.py`: first roadmap item-8
  local data-bearing agent. It reads the scheduler database-availability
  SQLite store in read-only mode on the main workstation, writes only its own
  bounded sanitized state under `.local-monitoring-agent-state/`, uses an
  agent-owned writer lock, and exposes no raw reason text, service labels,
  SQLite path, SQL, credentials, delivery, provider execution, process
  control, remediation, or alert replacement.
- `local_monitoring_agents/scheduler_metrics.py`: second roadmap item-8
  local data-bearing agent. It reads the local scheduler metrics JSON
  read-only, interprets naive scheduler timestamps as Europe/Prague local
  time, writes bounded sanitized agent-owned state under
  `.local-monitoring-agent-state/`, and exposes only aggregate scheduler/job
  health without labels, descriptions, raw skipped reasons, logs, file paths,
  delivery, provider execution, process control, remediation, or alert
  replacement.
- `monitoring_agent/incidents.py`: pure monitoring-agent incident rule and
  lifecycle engine. Rule version 1 consumes normalized observation facts or
  complete-cycle snapshots, returns sanitized states/transitions, and performs
  no persistence, delivery, network access, `.env` reads, target mutation, or
  alert replacement. Persistence/outbox state is implemented separately in
  `monitoring_agent/incident_store.py`; runtime delivery is implemented only
  by the separate gated `monitoring_agent/runtime_delivery.py` bridge.
- `monitoring_agent/incident_store.py`: bounded local monitoring-agent
  incident state and delivery-intent outbox store. It persists only normalized
  incident states, sanitized transition records, report references, and outbox
  retry/dead-letter/claim state in `incident_state.json`. It is not a sender
  and has no recipients, credentials, message body, network access, delivery
  authorization, target mutation, or alert replacement capability.
- `monitoring_agent/interpretation.py`: pure draft-only interpretation
  contract over confirmed monitoring incidents. It uses supplied report
  snapshots and an injected provider object only when explicitly enabled in
  draft mode; it adds no `.env` keys, no provider credentials, no network
  client, no polling-loop integration, no state writes, no delivery, no
  process control, and no alert suppression. Disabled, candidate-only, missing
  provider, provider-failed, invalid, or unsafe output falls back to the
  deterministic report.
- `monitoring_agent/shadow_pilot.py`: pure shadow-pilot comparison contract
  for roadmap item 7. It compares supplied sanitized monitoring-agent and
  legacy-alert detection/recovery events over one reviewed period, reports
  matched detections, delays, recoveries, duplicates, false positives, false
  negatives, and blind spots, and renders a bounded redacted operator summary.
  It performs no `.env` reads, database inspection, endpoint polling,
  delivery, interpretation-provider calls, state writes, process control, or
  alert suppression/replacement.
- `monitoring_agent/runtime_shadow.py`: runtime shadow-only incident
  persistence bridge for roadmap item 7. It evaluates the completed polling
  cycle through the deterministic incident lifecycle, applies it to the
  bounded local `IncidentStateStore`, prints sanitized aggregate
  `shadow_incidents`, and supports audit contract 8. It performs no delivery,
  provider execution, remediation, target mutation, process control, or
  legacy-alert suppression/replacement.
- `monitoring_agent/runtime_delivery.py`: opt-in runtime delivery bridge for
  controlled test email only. It runs after a completed observation cycle only
  when `DELIVERY_AUTOMATION_ENABLED=true`, reads only approved non-prefixed
  delivery keys, sends at most one due pending outbox item per cycle to
  `DELIVERY_TEST_RECIPIENT`, writes only sanitized delivery attempt state
  through `IncidentStateStore`, and performs no production delivery, provider
  execution, target mutation, remediation, process control, or legacy-alert
  replacement.
- `monitoring_agent/orchestrator.py`: file-only/shadow-only orchestrator v1
  correlation engine. It consumes only registry-approved sanitized snapshot
  files, normalizes agent status/freshness/evidence gaps/counts, computes
  bounded correlation findings, rejects duplicate agent identities, rejects
  `.env` sources, and performs no live polling, `.env` reads, delivery,
  provider execution, state mutation, process control, remediation, or alert
  replacement.
- `monitoring_agent/orchestrator_cli.py`: operator CLI for the file-only
  orchestrator proof. `python -m monitoring_agent.orchestrator_cli run`
  consumes a static registry and sanitized source files and writes bounded JSON
  and/or Markdown outputs; it does not register tasks or change runtime
  configuration.
- `monitoring_agent/orchestrator_export_cli.py`: file-only input preparation
  helper for the orchestrator. `python -m
  monitoring_agent.orchestrator_export_cli wrap-remote-audit` reads a supplied
  sanitized remote `--audit-state` JSON object from a file or stdin, rejects
  `.env` paths and wrong events, adds `captured_at`, and writes wrapped JSON
  for `remote_agent_audit_v8`; it does not poll endpoints, read `.env`, send
  email, mutate state, or control tasks.
- `moduly/mereni/prediction/storage.py`: shared prediction selected-model
  snapshot ORM/storage for per-medium, per-identifier, per-forecast-period
  model selection.
- `moduly/mereni/plynomery/branches.py`: gas branch and billing-meter
  configuration used by the manual billing-reading report workflow.
- `moduly/mereni/plynomery/reporting/monthly_billing_report.py`: manual
  plynomery billing PDF/HTML renderer for `Fakturacni odecty`, including
  optional actual kalorimetry-based allocation for selected gas meters.
- `moduly/mereni/kalorimetry/reporting/model_rebuild_report.py`: pure
  aggregate kalorimetry candidate/selection rebuild report and escaped HTML
  rendering without delivery side effects.
- `moduly/mereni/kalorimetry/production_dry_run.py`: read-only production
  kalorimetry orchestration that preloads observations, runs candidates in
  memory, checks coherent forecast coverage, and returns aggregate results
  without persistence or activation.
- `moduly/mereni/kalorimetry/prediction_backfill.py`: pure weekly historical
  kalorimetry planner/calculator producing leakage-safe candidate metrics,
  decisions, and shared snapshot rows without an apply path.
- `moduly/mereni/kalorimetry/prediction_backfill_workflow.py`: explicit
  dry-run/apply/resume/verify workflow with immutable identity comparison,
  content fingerprints, conflict rejection, and atomic weekly writes.
- `moduly/mereni/kalorimetry/production_backfill.py`: approved-range
  kalorimetry historical backfill orchestration with aggregate preflight,
  controlled apply/resume, and exact post-write verification.
- `moduly/mereni/kalorimetry/active_profile.py`: batched period-valid
  kalorimetry selected-decision and exact profile-slot lookup for scoring and
  future consumers.
- `moduly/mereni/kalorimetry/kalorimetry_anomaly.py`: period-valid
  active-selection anomaly scoring, idempotent score persistence, and atomic
  per-stream checkpoint advancement.
- `moduly/mereni/kalorimetry/events.py`: heat-specific spike/sustained-high
  event state machine, transactional event checkpoint integration, and
  delivery-disabled alert transition planning.
- `moduly/mereni/kalorimetry/reconciliation.py`: bounded, aggregate-only,
  transaction-read-only comparison of expected historical kalorimetry
  scores/events against optional persisted state.
- `scripts/kalorimetry_reconciliation_dry_run.py`: JSON aggregate entry point
  for the kalorimetry historical score/event reconciliation.
- `scripts/kalorimetry_controlled_backfill.py`: explicit-confirmation CLI for
  the controlled kalorimetry historical backfill.
- `services/api/main.py`: FastAPI application entry point and router registration.
- `services/api/core/config.py`: FastAPI runtime settings, including token and CORS configuration.
- `services/api/core/tokens.py`: custom HMAC bearer token implementation.
- `services/api/core/dependencies.py`: API authentication, admin, section, and device access dependencies.
- `services/api/routes/prediction.py`: admin-only prediction performance API
  routes for cross-media candidate and per-identifier selection views.
- `services/api/services/prediction_performance.py`: read-only cross-media
  prediction performance aggregation for candidate runs, selected-model
  snapshots, and candidate catalogs.
- `services/api/services/plynomery_billing.py`: dashboard-facing service for
  append-only gas billing readings and monthly billing report input assembly.
- `services/api/routes/kalorimetry.py`: admin outlier-review routes plus
  authenticated kalorimetry measurement and period-valid profile reads.
- `services/api/services/kalorimetry.py`: section/device-scoped kalorimetry
  measurement series and current/historical active profile availability.
- `services/api/routes/system_health.py`: admin-only system health API routes
  for safe post-restart/runtime checks.
- `services/api/services/system_health.py`: sanitized Windows runtime probes
  for boot time, startup task, expected listeners, and temporary listeners.
- `services/api/routes/monitoring.py`: dedicated authenticated, GET-only
  monitoring facade with the eight strict safe Health projections for the
  remote agent plus item-8 local-agent safe aggregate projections for database
  availability and scheduler metrics.
- `services/api/routes/smartfuelpass_excel_import.py`: admin-only raw `.xlsx`
  upload endpoints for SmartFuelPass preview and insert-only import.
- `services/api/schemas/monitoring.py`: allowlisted response contracts for the
  monitoring facade; unsafe/transient Health fields are excluded before
  network serialization.
- `services/api/services/monitoring_facade.py`: explicit projectors from the
  existing Health collectors and approved local-agent snapshots into the safe
  monitoring response contracts.
- `services/api/services/scheduler_health.py`: shared detailed Scheduler Health
  collector reused by the administrator route and safe monitoring facade.
- `services/api/routes/map.py`: general map API for layer catalog, features, filter options, and authorized device images.
- `services/api/services/map_layers.py`: map-layer metadata, access checks, filtering, distinct filter options, and image proxy orchestration.
- `services/api/services/device_map.py`: GeoJSON map feature loading, device detail enrichment, and map image file resolution.
- `moduly/apps/dashboard/login.py`: main Streamlit dashboard entry point.
- `moduly/apps/dashboard/navigation_config.py`: authoritative Streamlit navigation and permissions configuration.
- `moduly/apps/dashboard/auth.py`: Streamlit authentication/session state and API login flow.
- `moduly/apps/dashboard/responsive.py`: shared mobile breakpoint and responsive page styles for pilot dashboard pages.
- `moduly/apps/dashboard/map_shared.py`: shared Leaflet map HTML rendering and map API payload helpers.
- `moduly/apps/dashboard/database/models.py`: dashboard user and permission model.
- `moduly/apps/dashboard/database/db_init.py`: dashboard and feature table bootstrap.
- `moduly/apps/dashboard/pages/37_system_health.py`: Streamlit admin page for
  safe system health and post-restart verification checks.
- `moduly/apps/dashboard/pages/38_prediction_performance.py`: Streamlit
  admin page for cross-media prediction candidate performance and
  per-identifier selected-model snapshots.
- `moduly/apps/dashboard/pages/34_plynomery_fakturacni_odecty.py`: Streamlit
  admin page for manual plynomery billing readings and manual PDF creation.
- `moduly/apps/dashboard/pages/35_mapove_vrstvy.py`: Streamlit admin page for map layer configuration.
- `moduly/apps/dashboard/pages/36_mapove_podklady.py`: Streamlit `Mapove podklady / Mapa` page.
- `moduly/apps/smartfuelpass/service.py`: legacy SmartFuelPass portal-access
  helpers, charge-session report construction, PDF/email rendering, and
  database-backed weekly report assembly.
- `moduly/apps/smartfuelpass/sync.py`: legacy SmartFuelPass charge-session
  portal sync helpers retained for compatibility or historical diagnostics.
- `moduly/apps/smartfuelpass/excel_import.py`: manual SmartFuelPass
  ChargingSessions `.xlsx` parser, preview classifier, and insert-only
  PostgreSQL import for new charge sessions.
- `moduly/apps/smartfuelpass/database/models.py`: SmartFuelPass PostgreSQL
  ORM model for `monitoring.smartfuelpass_relace`.
- `moduly/apps/smartfuelpass/database/db_init.py`: SmartFuelPass table and
  migration bootstrap, including additive schema changes.
- `frontend_next/`: experimental Next.js MVP. It is not the active production dashboard and is not currently used in daily operation. Treat it as a future migration/prototype area, not as the source of truth for current dashboard behavior.
- `.streamlit/config.toml`: Streamlit server and navigation settings.
- `Caddyfile`: tracked mirror of the deployed public proxy configuration at `C:\Program Files\Caddy\Caddyfile`.
- `agents/security/DASHBOARD_SECURITY_CHECKLIST.md`: tracked public dashboard security
  remediation plan and status.
- `agents/plans/prediction/PREDICTION_PIPELINE_PLAN.md`: target architecture and rollout plan for the
  shared prediction pipeline, candidate plugins, forecast horizons, and
  per-identifier model selection.
- `agents/plans/plynomery/PLYNOMERY_PREDICTION_PIPELINE_PLAN.md`: active step-by-step implementation
  and verification plan for per-identifier plynomery prediction, scoring,
  dashboard, and report integration.
- `agents/inventories/PLYNOMERY_REPORT_CONSUMER_INVENTORY.md`: reviewed classification of every
  gas report/output and direct prediction-profile consumer, including
  intentionally actual-only outputs and the step 20 direct-read review queue.
- `agents/runbooks/PLYNOMERY_POST_RESTART_RUNBOOK.md`: mandatory gas-pipeline restart,
  post-boot verification, score/event reconciliation safety contract, and
  aggregate completion checks.
- `agents/plans/kalorimetry/KALORIMETRY_PREDICTION_PIPELINE_PLAN.md`: active step-by-step plan for the
  complete kalorimetry import, profile, selection, historical backfill,
  scoring, API, dashboard, and downstream-consumer lifecycle.
- `agents/inventories/KALORIMETRY_CONSUMER_INVENTORY.md`: reviewed classification of every
  kalorimetry prediction-bearing, actual-only, anomaly/event, model-rebuild,
  device/inventory, report, and scheduler consumer.
- `agents/runbooks/KALORIMETRY_ACTIVATION_RUNBOOK.md`: mandatory Monday 2026-08-03 forecast
  preflight, approval, current-snapshot activation, scoring/event pilot,
  scheduler, regression, restart, and post-rollout checklist.
- `agents/plans/monitoring/SCHEDULER_MONITORING_AGENT_PLAN.md`: approved
  step-by-step design for the first independent read-only monitoring agent,
  its deterministic incident lifecycle, test-mode reporting, and the
  separately gated path toward eventual alert-layer replacement.
- `agents/plans/monitoring/MONITORING_AGENT_IMPLEMENTATION_ROADMAP.md`:
  approved nine-step live checklist from safe observation expansion through
  incident/report/delivery/interpretation work, shadow validation, local
  agents, and the later evidence-driven orchestrator design.
- `agents/plans/monitoring/SCHEDULER_MONITORING_AGENT_REMOTE_RUNTIME_DESIGN.md`:
  selected cross-workstation boundary, private monitoring API facade,
  network/authentication constraints, known blind spots, and the required
  remote failure-isolation proof.
- `agents/plans/monitoring/AGENTIC_SUPERVISION_CENTER_ARCHITECTURE.md`:
  hub-and-spoke boundary for the clean remote supervision center, minimal
  distribution bundle, local data-bearing agents, Tailscale facade, packaging,
  installation, self-monitoring, and future-agent onboarding.
- `agents/plans/monitoring/MONITORING_ORCHESTRATOR_DESIGN.md`: accepted
  roadmap item 9 architecture baseline for the first supervision-center
  orchestrator, based on the verified remote observer plus DB-availability
  and scheduler-metrics local agents. It inventories observed shared
  contracts, failure isolation, allowed read-only correlation, explicit
  non-goals, and the next approved file-only/shadow-only CLI scope before any
  runtime-contract change.
- `agents/plans/monitoring/MONITORING_AGENT_REPORTING_LAYER_HANDOFF.md`:
  verified deployed 0.7 task/restart baseline, local 0.8 observation-contract
  candidate, audit interpretation rules, safe reporting inputs, and known
  activation gaps before deterministic reporting work.
- `agents/inventories/MONITORING_AGENT_HEALTH_ENDPOINT_INVENTORY.md`: reviewed
  allowlist and retention classification for every Health API field available
  to the first monitoring agent, including explicitly excluded log and
  manual-run surfaces.
- `agents/inventories/MONITORING_AGENT_REMOTE_WORKSTATION_INVENTORY.md`:
  non-secret Windows 11/Python 3.14 remote-station baseline, selected Tailscale
  pilot direction, remaining ownership questions, and staged verification
  sequence.
- `agents/inventories/SECURITY_SECRET_INVENTORY.md`: non-secret inventory of production secret,
  credential, session, and sensitive runtime artifact locations.
- `requirements-production.in`: reviewed direct production dependency pins.
- `requirements-production.lock.txt`: exact production direct and transitive
  dependency set for CPython 3.14 on Windows.
- `requirements-security.in`: reviewed direct dependency pins for the isolated
  local security-tooling environment.
- `requirements-security.lock.txt`: exact dependency set for `.venv-security`.
- `requirements-api.txt`: compatibility entry point that installs the
  production lock.
- `scripts/bootstrap_production_environment.ps1`: creates and verifies the
  isolated `.venv-production` runtime.
- `scripts/bootstrap_security_toolchain.ps1`: creates the isolated
  `.venv-security` audit-tooling environment.
- `scripts/run_dependency_audit.ps1`: audits the production dependency lock
  and installed `.venv-production` packages through `.venv-security`.
- `scripts/register_dependency_audit_task.ps1`: registers the daily Windows
  dependency vulnerability audit scheduled task.
- `scripts/secret_hygiene_scan.py`: redacted scanner for tracked files and Git
  history; reports sensitive paths and likely secret assignments without
  printing values.
- `scripts/code_integrity_scan.py`: creates and checks the approved code
  integrity SHA-256 manifest for tracked code/deployment files.
- `scripts/run_code_integrity_scan.ps1`: production PowerShell entry point for
  manual or scheduled code integrity baseline/scan runs.
- `scripts/register_code_integrity_scan_task.ps1`: idempotent helper for
  registering the daily Windows code integrity scheduled task.
- `scripts/export_monitoring_orchestrator_local_inputs.py`: file-only
  orchestrator pilot input helper. It exports the two local sanitized
  monitoring facade aggregates into `artifacts/monitoring/orchestrator/...`,
  optionally includes a supplied sanitized remote audit JSON, and writes a
  static orchestrator registry. It does not read `.env`, poll endpoints, send
  email, mutate application state, or control tasks.
- `scripts/run_database_availability_local_agent.py`: manual/Task-ready
  one-shot runner for the first item-8 local data-bearing agent. It reads the
  local scheduler database-availability SQLite store read-only and writes only
  bounded sanitized agent-owned state; it does not register itself, send
  email, read `.env`, or mutate scheduler/application state.
- `scripts/register_database_availability_local_agent_task.ps1`: explicit
  operator-run Scheduled Task registrar for the first item-8 local agent. It
  registers a limited current-user recurring task with `IgnoreNew` and a
  two-minute execution limit; it does not start, stop, or unregister tasks by
  itself.
- `scripts/run_local_monitoring_agents.py`: preferred item-8 shared local
  one-shot runner for all approved local agents. It runs DB availability and
  scheduler metrics sequentially, lets each agent keep its own state/lock, and
  returns only a sanitized aggregate result. Agent-reported `degraded`/`error`
  status is monitoring evidence, not runner failure; the runner fails only on
  execution/schema exceptions.
- `scripts/register_local_monitoring_agents_task.ps1`: preferred item-8
  Scheduled Task registrar for the shared local runner. It registers a limited
  current-user recurring task with `IgnoreNew` and a three-minute execution
  limit; it does not start, stop, or unregister tasks by itself. On
  2026-08-17 the older DB-only local task was retired and the active local
  monitoring task became `MonitoringLocalAgents`. Do not re-register the older
  DB-only task alongside the shared task because that would duplicate
  DB-availability agent executions.
- `scripts/run_scheduler_metrics_local_agent.py`: manual one-shot runner for
  the second item-8 local data-bearing agent. It reads local scheduler metrics
  JSON read-only and writes only bounded sanitized agent-owned state; it does
  not register itself, send email, read `.env`, or mutate scheduler/application
  state.
- `scripts/run_with_rotating_log.py`: captures API, Streamlit, and Caddy
  stdout/stderr into size-rotated ProgramData logs.
- `tests/`: pytest suite for scheduler, imports, dashboards, reports, auth/navigation, anomaly handling, and supporting services.
- `tests/test_monitoring_agent.py`: focused safety and synthetic-contract tests
  for the unregistered remote observer skeleton.

## Runtime Surfaces

Current active surfaces:

- Scheduler process started from `main.py`.
- FastAPI service from `services/api/main.py`.
- Streamlit dashboard from `moduly/apps/dashboard/login.py`.
- Local monitoring Scheduled Task `MonitoringLocalAgents`, registered from
  `scripts/register_local_monitoring_agents_task.ps1`, running approved local
  monitoring agents through `scripts/run_local_monitoring_agents.py`.

Experimental or future-facing surface:

- `frontend_next/` is a partial Next.js migration experiment. Do not assume feature parity with Streamlit. Do not use it to infer current production dashboard behavior unless the user explicitly asks about this experimental area.

## Data and Secrets

Treat these as sensitive or operational artifacts:

- Any leftover local `data/smartfuelpass/session_cookies.json` or
  `data/smartfuelpass/auto_login_session.json` files. SmartFuelPass JSON
  session persistence is retired; do not read, restore, or commit these files.
- `C:\ProgramData\monitorovaci_platforma\caddy-dashboard-auth.env`
- `C:\ProgramData\monitorovaci_platforma\dashboard-proxy-credentials.txt`
- Any `.env`, credentials, cookies, tokens, browser sessions, or account data.
- Raw meter data and imported source files unless the user explicitly requests inspection.
- Device photo paths and photo files referenced by source columns such as `foto`; serve them only through authorized API paths.

Known hygiene topics to handle only after explicit approval:

- Historical SmartFuelPass session files exist in Git history; expire portal
  sessions externally if old cookies may still be valid.
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
- Browser-initiated privileged writes must execute through authenticated
  FastAPI services. Revision and device-list mutations use
  `/api/v1/admin/revize` and `/api/v1/admin/devices/{meter_key}` with both
  route-level and service-level admin checks; do not restore direct
  PostgreSQL/MSSQL writes in Streamlit pages or shared UI modules.
- FastAPI liveness must not depend on database availability. Dashboard table
  initialization runs as a background retry task; `/health/ready` returns HTTP
  503 until that initialization succeeds.
- Streamlit remains the active dashboard unless a task explicitly targets the experimental Next.js area.
- Shared behavior should live in modules/services, not in duplicated page logic.
- Prediction model work should proceed toward the shared core described in
  `agents/decisions/DECISIONS.md`,
  `agents/plans/prediction/PREDICTION_PIPELINE_PLAN.md`, and the active work
  index in `agents/work/ACTIVE.md`: shared contracts,
  media-specific adapters, candidate
  model plugins, configurable forecast periods, rolling backtests, and
  per-identifier model selection. Implement one checklist step at a time and
  mark it complete only after targeted verification.
- All production prediction media use one Prague calendar-week validity
  contract: Monday 00:00 inclusive through the following Monday 00:00
  exclusive. Plynomery and vodomery use the shared calendar-week period
  builder; kalorimetry and elektromery must reuse the same builder when their
  prediction pipelines are added.
- Kalorimetry prediction work follows
  `agents/plans/kalorimetry/KALORIMETRY_PREDICTION_PIPELINE_PLAN.md` one
  verified checklist item at a
  time. Predict normalized non-negative energy `delta`, not cumulative
  `spotreba_energie` or `objem`; retain explicit reset, gap, synthetic,
  validity, outlier, time, and device-access semantics. Do not copy gas
  weather behavior until heat-specific historical evidence and weather-input
  availability have been reviewed.
- Kalorimetry model input and scoring require valid, non-reset, finite
  non-negative energy deltas and exclude both `synthetic` and `gap_detected`
  rows. Consumption display may retain valid gap continuity rows, while meter
  state display may retain finite cumulative states without a usable delta.
  Zero delta is a real observation and must not be removed to improve metrics.
- Kalorimetry timezone-aware forecast references are converted to
  Europe/Prague wall time before calling the shared calendar-week builder.
  Naive references already represent Prague wall time. Do not duplicate the
  Monday-to-Monday calculation in kalorimetry modules.
- Kalorimetry normalized prediction observations are loaded through
  `moduly/mereni/kalorimetry/prediction_adapter.py`. Its SQL prefilter and pure
  DEC-078 classifier form one fail-closed boundary; later candidates must not
  read `Mereni_kalorimetry_vse` directly and weaken those filters.
- Kalorimetry calendar baseline model 1 uses a 12-month window and requires
  eight eligible samples for every one of 672 weekday/15-minute slots. Never
  publish a partial identifier profile; incomplete coverage is
  `insufficient_history`. Model 1 is not production-active merely because its
  profile can be built.
- Kalorimetry weather model 2 is only a per-identifier challenger. It uses a
  leakage-safe trailing 24-hour HDD feature and a non-negative per-slot slope.
  Deploy profiles require complete weather for the full Prague week; any
  missing hour is `missing_forecast_weather` with no fallback to zero,
  training mean, historical/stale weather, or baseline under model 2 identity.
- Kalorimetry rolling comparison uses the production Prague week shape and a
  preceding 12-month training window per fold. Weather validation actuals
  must be loaded independently from HDD matches so missing weather reduces
  coverage. Persist per-identifier WAPE, MAE, RMSE, bias, coverage, observed
  fold count, and matched fold count in the caller's transaction.
- Kalorimetry selection may consume only entries from
  `deployable_catalog.py` marked available. Available means exactly 672 unique
  15-minute slots for one identifier/model with finite non-negative
  statistics, ordered quantiles, and positive sample sizes. Never attach a
  partial profile or relabel baseline as weather when model 2 is unavailable.
- Kalorimetry dry-run selection requires finite WAPE, MAE, RMSE, and bias,
  coverage of at least 85 percent, at least eight matched weekly folds, and an
  available deployable profile. Rank by WAPE, MAE, RMSE, absolute bias,
  descending matched observations, then model version. If the metric winner
  has no deployable profile, select the next eligible candidate and preserve
  the profile-unavailability reason in the audit. Selection alone must not
  persist or activate anything.
- Kalorimetry selected-model and profile snapshots use the shared prediction
  storage with `medium_key='kalorimetry'`. Build and validate the complete
  persistence batch before SQL execution; every available decision requires
  the exact selected model key and all 672 profile points for the same period.
  Do not persist unavailable identifiers as selected. Execute decision and
  profile inserts in one caller-owned transaction/savepoint and never commit
  them independently.
- The shared prediction-performance API/dashboard includes kalorimetry as a
  registered weekly medium. Before its first controlled persisted run it must
  report `not_run`; afterward it may expose only aggregate candidate metrics,
  snapshot winner/fallback distributions, coverage, and a bounded
  worst-identifier list. The kalorimetry rebuild report is a pure aggregate
  renderer and must not include raw measurements or invent email recipients.
- The 2026-07-29 kalorimetry production dry-run is not an activation approval.
  PostgreSQL observations ended on 2026-05-18, leaving all eight current
  validation folds empty and all 14 identifiers without selection metrics.
  Baseline profiles were deployable for all 14, but the coherent weather
  forecast supplied only 145 of 168 required trailing-24-hour features.
  Complete the reviewed measurement backlog import and extend/verify forecast
  coverage before repeating a current-period dry-run or activating snapshots.
- The measurement-backlog part of that blocker cleared after the 2026-07-29
  restart. A 2026-07-30 aggregate audit found PostgreSQL current with MSSQL and
  eligible observations for all 14 identifiers through 2026-07-26. The repeat
  current-period dry-run evaluated 75,190 validation rows at 100 percent
  aggregate coverage. Activation remains blocked: the latest coherent forecast
  supplied only 95 required HDD values, weather profiles were unavailable for
  all 14 identifiers, and seven identifiers still had no eligible selection
  metrics. Do not activate weekly snapshots or scoring from this result.
- Weather forecast synchronization now requests nine days and archives rows
  by composite `(forecast_run_at, datetime_hour)` identity. A kalorimetry
  deployment must select one coherent issuance strictly before the Prague
  week starts and require all raw hours for 168 trailing-24-hour HDD values.
  Do not use a run issued after Monday to reconstruct that week. Operational
  gas consumers must resolve the latest issuance per target hour now that
  multiple runs are retained.
- Return to `agents/runbooks/KALORIMETRY_ACTIVATION_RUNBOOK.md` on Monday
  2026-08-03 morning.
  Do not begin step 25 scheduler writes before the Sunday pre-week forecast,
  current dry-run, snapshot approval, snapshot verification, and separate
  scoring/event approval gates are satisfied.
- Kalorimetry historical backfill weeks hard-cut measurement and weather
  observations at the Monday period start. Historical weather deployment
  requires explicit forecast provenance issued strictly before that start.
  Snapshot batches use `selection_mode='active'`,
  `archive_source='historical_backfill'`, and `selection_run_id=NULL`; they
  must not alter the current runtime selection identity. Step 13 defines only
  planning/calculation—production dry-run/apply/resume/conflict handling
  belongs to step 14 and requires separate approval.
- Kalorimetry historical workflow classifies each identifier/week/archive
  batch as absent, exactly complete, or conflict. Resume may skip only exact
  model/count/content fingerprint equality across decisions, both candidate
  metrics, and all profile points. Apply requires `confirm_apply=True`, all
  shared tables to exist, exact insert counts, one savepoint per week, and a
  weekly commit only after validation. Never use apply merely because the
  function exists; production execution remains a separate explicit approval.
- The approved kalorimetry historical backfill completed on 2026-07-29 for
  `[2025-07-28, 2026-05-18)`: 42 weeks, 588 identifier-weeks, 430 baseline
  decisions, 1,176 candidate metrics, and 288,960 profile points. All weeks
  verify complete with zero conflicts and all selected profiles have 672
  points. Historical weather was unavailable for every week because no
  complete coherent pre-week forecast archive existed. Snapshots cover 13 of
  14 identifiers and retain `selection_run_id=NULL`; current kalorimetry
  selection/profile/validation tables were not created or activated.
- Kalorimetry active-profile lookup uses half-open snapshot validity and
  resolves overlapping decisions by latest period start, creation time, and
  row id. Within the selected decision it resolves only the exact selected
  model, period, interval, weekday, and slot, preferring highest archive
  version, creation time, and row id. `no_selection_snapshot`,
  `insufficient_history`, and `missing_profile` are unavailable and must not
  fall back to a global, current, stale, zero, or other-model profile.
- Kalorimetry active-selection anomaly scores use stable output
  `model_version=1` and separately record the selected candidate model,
  decision snapshot id, and profile snapshot id. Only observations eligible
  under the shared kalorimetry scoring-quality contract may be scored.
  Explicitly unavailable selections receive no score but advance the
  checkpoint; an available decision missing its exact profile is a hard error
  before commit. Conflict-safe score insertion and checkpoint advancement
  share one transaction. Do not create the score/checkpoint tables or run
  production scoring without the separately reviewed activation/reconciliation
  sequence.
- Kalorimetry event detection supports only `SPIKE` and
  `SUSTAINED_HIGH_USAGE`. Do not copy gas/water night-use or expected-zero
  semantics without a separate heat-domain decision. Event state, active
  events, processed-score flags, and the event-engine checkpoint share one
  transaction. Alert transition plans remain delivery-disabled until an
  aggregate dry-run is reviewed and sending is explicitly approved.
- Kalorimetry outlier-review repair rebuilds active scoring rows only through
  exact period-valid selected snapshots. It is a no-op before scoring-table
  activation, never changes the global checkpoint, and must not write
  non-active candidate comparisons, profiles, or metrics.
- The 2026-07-29 kalorimetry historical reconciliation covered
  `[2025-07-28, 2026-05-18)` read-only: 401,363 measurements, 395,149 eligible,
  6,214 ineligible, 285,766 expected scores, 109,383 eligible rows without an
  available period-valid selection, and 3,456 created plus 3,456 resolved
  expected event episodes. Score/event tables did not exist, so persisted
  counts were zero and all expected scores/created episodes were missing.
  Zero mismatch/flag/severity changes reflect no overlapping persisted state,
  not successful score activation. Do not apply this result without separate
  approval.
- Kalorimetry measurement/profile API reads require both `kalorimetry` section
  access and requested-device access, with service-level checks before opening
  PostgreSQL. Measurement ranges use Prague-local date boundaries converted to
  half-open UTC. Current profile reads use only a covering active snapshot;
  historical ranges return only overlapping active periods. Duplicate profile
  slots resolve by highest archive version, newest creation time, and highest
  row id. `no_selection_snapshot`, `insufficient_history`, and
  `missing_profile` remain explicit without global/current/stale/zero fallback.
- Kalorimetry prediction series use the authenticated device-scoped API and
  exact period-valid profile snapshots for hourly, daily, and monthly output.
  Negative expected interval consumption is clamped to zero before
  aggregation. Expected cumulative consumption is derived across the complete
  requested range and must not reset at weekly snapshot boundaries; uncovered
  ranges remain explicitly unavailable or partial.
- `Kalorimetry / Přehled` loads predictions only through that API. It shows
  actual, expected, absolute-deviation, and percentage-deviation metrics and
  overlays light-gray interval and cumulative predictions below actual energy
  consumption. Unavailable values display `Nedostupné`; do not restore a
  direct Streamlit prediction-profile database read.
- `Kalorimetry / Detail` reuses the same API: daily series for its seven-day
  and 31-day charts and monthly series for its 24-month history. Expected
  lines remain below actual bars, and unavailable/partial periods stay
  explicit. Preserve the page's device metadata, photograph, reset history,
  measurement tables, and responsive layout.
- Only `Kalorimetry / Přehled` and `Kalorimetry / Detail` are currently
  prediction-bearing user outputs. The JORDAN monthly report's kalorimetry row
  remains intentionally actual-only and derives consumption from two valid
  cumulative states. Do not add prediction or change delivery without
  separate approval; use
  `agents/inventories/KALORIMETRY_CONSUMER_INVENTORY.md` as the reviewed
  consumer baseline.
- Vodomery production scoring now reads `active` per-identifier selected-model
  snapshots for the globally active model. The selected snapshot controls the
  source profile per odběrné místo for the forecast period; inserted anomaly
  scores still use the global active `model_version` so existing event and
  alert flows remain compatible. Missing or unusable per-identifier selections
  produce no active score; available selections with missing profiles fail.
  Non-active candidate scoring remains pure per-candidate scoring for
  comparison.
- Vodomery daily, weekly, and monthly branch PDF predictions use period-bounded
  `active` profile snapshots per identifier. Historical report days must not
  use the current global profile; duplicate snapshot slots resolve by highest
  archive version and newest row. Billing-summary PDFs inherit the same branch
  report source, while actual-consumption-only reports remain unchanged.
- Vodomery dashboard profile requests without a date range use the `active`
  per-identifier profile snapshot valid at the current Prague time. Overlapping
  periods resolve to the latest period start; the global current profile is
  only a fallback when no active snapshot covers the current instant.
- Plynomery measurement and prediction-profile API reads require both
  `plynomery` section access and device access. Current profile reads use only
  the period-valid `active` selected/profile snapshot. `insufficient_history`,
  `no_selection_snapshot`, and `missing_profile` are explicit unavailable
  states with empty profile rows; do not replace them with zero or a global
  profile.
- Plynomery profile API date ranges return only overlapping `active` snapshot
  periods and carry per-period availability plus profile validity metadata.
  Mixed ranges may be `partial`. Historical reads must never project the
  current or global profile backward.
- Plynomery historical prediction coverage begins on 2026-04-21 through
  weekly per-identifier backfill snapshots. Historical backfill evaluates
  candidate models using only information available before each calendar
  week, stores active decisions with `selection_run_id=NULL`, uses
  `archive_source=historical_backfill`, and must not change the current
  runtime selection identity. Identifiers without three months of history
  remain explicitly unavailable.
- Shared plynomery prediction series are built from period-valid profile
  snapshots for hourly, daily, and monthly output. Overlaps resolve by latest
  period start and then newest selection run. Weather-adjusted rows require
  the applicable 24-hour HDD input; missing weather must remain unavailable
  and must not fall back to the stored training HDD mean or zero.
- `Plynomery / Prehled` obtains prediction series through the authenticated,
  device-scoped FastAPI endpoint. It renders the full selected period at the
  chosen hourly, daily, or monthly granularity, reports partial availability,
  and shows `Nedostupné` for unavailable predictions. Actual series remain
  bounded by the last real measurement.
- `Plynomery / Prehled` renders the expected-consumption line in the same light
  gray (`#dedcd9`) as vodomery, includes expected cumulative consumption in
  the cumulative chart, draws actual consumption above the prediction layer,
  shows the shared consumption/prediction legend below the charts, and
  presents the four summary metrics actual, expected, absolute deviation, and
  percentage deviation.
- The dashboard gas prediction loader sorts API series chronologically and
  derives expected cumulative consumption from expected bucket consumption
  across the complete selected range. Do not trust, reset, or independently
  splice cumulative values at weekly snapshot boundaries.
- Gas prediction series clamp negative expected bucket consumption to zero
  before aggregation and cumulative summation. Expected cumulative
  consumption must therefore be monotonic non-decreasing.
- `Plynomery / Detail` reuses the same device-scoped prediction-series API.
  Its 7-day and 31-day charts use daily predictions and its 24-month history
  uses monthly predictions. Historical gaps remain gaps, and
  `insufficient_history` is displayed as `Nedostupné`.
- `Plynomery / Fakturacni odecty` is a completed admin-only manual
  billing-reading workflow. Operators manually save monthly readings and
  manually create/download the PDF. It is not registered in the scheduler, has
  no automatic recipient/email delivery, and remains actual/billing-only
  rather than prediction-bearing. Selected gas-meter consumptions may be
  allocated by actual kalorimetry cumulative energy snapshots for the same
  billing-reading interval; do not use kalorimetry predictions for this PDF.
- Future prediction-bearing plynomery consumption PDFs/reports remain separate
  work. They must use the shared period-valid prediction-series contract for
  every report timestamp, display `Nedostupné` for unavailable periods, and
  must not substitute zero, the current profile, or a stale/global profile.
- Plynomery outlier-review repair rebuilds the globally active score identity
  through period-valid active per-identifier selection. Non-active model
  versions remain pure candidate rebuilds from their candidate profile tables.
  Missing/insufficient active selections produce no repaired score rather than
  a global fallback.
- Vodomery per-identifier selection may choose only a candidate that produced
  a deployable profile for that identifier. If the metric winner has no
  profile, select the next best eligible candidate with sufficient coverage
  and record `missing_profile`; if no candidate profile exists, fail the
  rebuild before persisting selections. Do not hide historical missing-profile
  gaps by copying a later or stale profile into the archive.
- Vodomery identifiers without any valid rolling fallback metrics are persisted
  as `insufficient_history`. They publish no selected profile and receive no
  active score, while the scoring checkpoint still advances. API, dashboard,
  and branch PDF consumers display `Nedostupné`; they must not substitute a
  global, zero, copied, synthetic, current, or stale profile. An available
  decision with a missing profile is a hard error.
- Vodomery outlier-review repair rebuilds the globally active score identity
  through the same period-valid active per-identifier selection as normal
  scoring. Non-active model versions remain pure candidate rebuilds for model
  comparison. Missing selection, insufficient history, or a missing selected
  profile must not fall back to a global, current, or stale profile.
- SmartFuelPass portal/browser import is retired as the active data path after
  repeated Cloudflare blockage. Do not retry, automate, bypass, disguise, or
  outsource the portal's Cloudflare flow, and do not restore JSON
  cookie/session persistence or `SMARTFUELPASS_SESSION_COOKIES_PATH`.
- SmartFuelPass charge-session data is loaded manually from administrator
  selected `ChargingSessions` `.xlsx` exports on the `Nabijecky / Import`
  page. Browser-initiated privileged writes must go through the admin-only
  FastAPI Excel import endpoints, not direct Streamlit database writes.
- The Excel parser maps `Nákup` to `id_relace`, imports only `Stav =
  Dokončeno`, uses `Energie` for `kwh`, `Suma` for `suma`, normalizes `Název
  EV lokace` to the existing short location format, stores connector/tariff
  when present, sets `battery_status=NULL`, and applies the existing
  SmartFuelPass interval UTC/source time semantics.
- Excel import is insert-only by `id_relace`. Existing database rows are shown
  in preview, including differences, but are never updated, upserted, or
  re-imported from the Excel file.
- SmartFuelPass weekly report periods use the previous completed calendar week
  from Monday through Sunday and filter by session end time.
- The database-backed SmartFuelPass weekly report remains scheduled and must
  not open the portal.
- Legacy SmartFuelPass interactive helper/task/code may remain for
  compatibility or historical diagnostics, but it is no longer the active
  dashboard workflow.
- `Mapove podklady` uses general FastAPI map endpoints and admin-configured metadata in `dashboard.Map_Layers`.
- Map feature images must be resolved server-side from `layer_id` and device identifier; do not expose an endpoint that serves arbitrary client-supplied file paths.
- Browser map image loading must use same-origin `/api/v1/map/images` through Caddy, which routes `/api/*` to FastAPI and other requests to Streamlit.
- Map iframe JavaScript must never receive the main API bearer token. The image endpoint authenticates through HttpOnly dashboard cookies; other API routes continue to require bearer authentication.
- Map image loading may also use the dedicated HttpOnly
  `__Secure-monitoring_map_image_session` cookie, scoped to
  `/api/v1/map/images` with `SameSite=None`, so Streamlit iframe fetches can
  authenticate without exposing the main bearer token to JavaScript.
- Do not restore a cross-origin map image API override. Deployments must expose the image endpoint under the dashboard origin so the browser can use the protected session cookie without disclosing it to JavaScript.
- Leaflet `1.9.4` JavaScript, CSS, images, license, and source metadata are vendored under `moduly/apps/dashboard/assets/leaflet/1.9.4` and embedded by `map_shared.py`; do not restore runtime executable-code loading from a public CDN.
- Public dashboard HTTPS is served at `https://monitoring.armexholding.cz`.
- Caddy adds the reviewed public security headers. HSTS, `nosniff`,
  `Referrer-Policy`, `X-Frame-Options`, and `Permissions-Policy` are enforced;
  the Streamlit-compatible CSP remains report-only until authenticated browser
  workflows have been reviewed against collected violations.
- The public `Permissions-Policy` must preserve same-origin geolocation for the
  map page. Do not change it to `geolocation=()` while mobile map location is a
  supported dashboard feature.
- Caddy removes public `Server` and `Via` response headers. Do not restore
  upstream or proxy fingerprinting headers without an operational reason.
- Caddy uses an explicit HTTP listener for HTTP-to-HTTPS redirects and disables
  automatic redirects so `Server`/`Via` stripping also applies to redirect
  responses.
- Public `/docs`, `/redoc`, and `/openapi.json` must return HTTP 404 at the
  Caddy layer before the Streamlit fallback. Do not let documentation-looking
  paths fall through to the Streamlit shell.
- Caddy exposes the Streamlit login page directly without a second browser
  authentication prompt. FastAPI rate-limits `/api/v1/auth/login` by normalized
  account identifier and trusted client IP with temporary increasing lockouts.
- Authentication events are written as rotated JSONL audit records under
  `C:\ProgramData\monitorovaci_platforma\logs\auth_audit.jsonl` by default.
  Audit records contain normalized identifiers, trusted source IPs, result and
  reason categories, and security-alert counters; they must never contain
  passwords, bearer tokens, or cookie values.
- Uvicorn accepts forwarded client information only from the loopback Caddy
  proxy; application code uses the trusted request scope rather than parsing
  raw `X-Forwarded-For` headers.
- `https://monitoring.armexholding.cz` is the only supported public client entry point; direct client access through the public IP address is not required or supported.
- This multi-homed production workstation cannot validate the public dashboard
  through its own public address because the Internet path has no working
  hairpin route. Post-restart checks must use local Caddy TLS/SNI for on-host
  routing and an actual external client for independent public reachability;
  an on-host public-hostname timeout alone is not a dashboard outage.
- `start_api_dashboard.bat` starts or reloads `C:\Program Files\Caddy\caddy.exe` only after FastAPI and Streamlit health checks pass.
- Production FastAPI, Streamlit, and scheduler processes use the isolated
  `.venv-production` environment. Startup fails closed if Python is not 3.14,
  pip is not the reviewed version, a locked package is missing or mismatched,
  or an unlocked package is present.
- Dependency vulnerability scanning uses the separate `.venv-security`
  environment. Do not install `pip-audit` or security-tooling packages into
  `.venv-production`; that would break the production exact-lock invariant.
- Production Uvicorn uses one worker without `--reload`. Development reload
  behavior belongs only in explicitly named `*_dev.ps1` launchers that use
  `.venv`.
- API and Streamlit remain bound to `127.0.0.1`; Caddy is the only public
  application listener and its admin API remains on `127.0.0.1:2019`.
- API, Streamlit, and fresh-start Caddy output is written under
  `C:\ProgramData\monitorovaci_platforma\logs` with 10 MiB files and 10 rotated
  backups. Scheduler logs remain daily rotated with 14 backups; authentication
  audit records retain their separately configured 90-day rotation.
- Code integrity baselines are stored outside the repository at
  `C:\ProgramData\monitorovaci_platforma\security\code_integrity_manifest.json`
  by default. Scan reports are written under
  `C:\ProgramData\monitorovaci_platforma\logs\security`. Create a new baseline
  only after the current code state is reviewed and either committed or
  explicitly approved; do not baseline a dirty working tree silently.
- The code integrity scan is a local drift detector for tracked code and
  deployment configuration. It is not tamper-proof against an actor who can
  modify both the repository and the scheduled scan mechanism.
- Secret hygiene scan reports must remain redacted. Do not print raw scanner
  match values, cookie payloads, token strings, passwords, or credential file
  contents.
- The runtime Caddy configuration is `C:\Program Files\Caddy\Caddyfile`; keep the tracked root `Caddyfile` synchronized with it.
- On the Windows production workstation, `start_api_dashboard.bat` is launched
  by Windows Task Scheduler with the trigger `At system startup`. This allows
  FastAPI, Streamlit, the scheduler, and Caddy to start without an interactive
  user login.
- Processes started by that scheduled task run in a non-interactive session;
  their console windows are not available for later operational control.
- The current supported way to renew or restart the complete runtime process
  set is to restart the whole Windows workstation. Do not assume that an agent
  can safely stop and recreate individual production processes from the current
  interactive session.
- The startup task retries launcher-level failures three times at one-minute
  intervals, but it does not supervise a child process after the launcher has
  completed. A later API, Streamlit, scheduler, or Caddy process exit therefore
  requires the supported full-workstation recovery procedure.
- The current scheduled task runs as `tra` with password logon and
  `RunLevel=Highest`. This is an accepted least-privilege gap. Do not change
  the task account or elevation without verifying access to the project,
  protected environment, ProgramData state/logs, databases, network shares,
  ports 80/443, and Caddy certificate storage. A future dedicated
  non-interactive service account should receive only those rights.
- Changes to the launcher or process startup arguments take effect only after
  the scheduled task runs again, normally after a workstation restart. Do not
  redesign this startup/recovery model without explicit user approval.
- Before every workstation restart, append a dated restart handoff to
  `agents/history/SESSION_NOTES.md`. The handoff must preserve the current
  conversation/task
  state, completed and pending work, changed/uncommitted files, deployment
  state, reason for restart, and any sensitive artifacts that must not be
  printed or modified.
- The same handoff must list the expected post-restart processes and listeners,
  plus exact health, scheduler, Caddy, routing, authentication, and
  change-specific verification steps. Do not request or initiate a restart
  until this handoff has been written and checked.

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
- Dashboard refreshes tied to `quarter_hour_job` must derive its exact run minutes from the central scheduler specification and refresh after those slots; do not assume regular 15-minute spacing.
- Scheduled database jobs check API, Streamlit dashboard, and Caddy availability
  before the database preflight. Runtime outages do not stop the data job, but
  send one transition alert per unavailable service until it recovers.
- Scheduler alert content is selected per recipient. An address assigned to an
  active dashboard admin account receives technical details; all other
  recipients receive only the existing brief description. Database brief
  alerts contain only `Nedostupnost POSTGRES` and/or `Nedostupnost MSSQL`.
  Runtime brief alerts contain only `Nedostupnost API`,
  `Nedostupnost DASHBOARD`, and/or `Nedostupnost CADDY`.
- Admin-recipient classification uses a short-lived local cache of SHA-256
  email hashes refreshed after successful PostgreSQL preflight checks. Missing,
  invalid, or stale classification must fail closed to the brief alert.
- Only `quarter_hour_job` records PostgreSQL/MSSQL availability transitions in
  local SQLite under `core/scheduler/data/database_availability.sqlite3`.
  Send one alert when a database first becomes unavailable, suppress repeated
  outage emails, and send one recovery summary after the first successful
  check. Other scheduled jobs still skip on failed database preflight but do
  not emit database availability emails.
- Recovery summaries report the first failed and first successful
  `quarter_hour_job` observations and the observed outage duration. These times
  are scheduler observation boundaries, not exact network-transition times.
- Pending SQLite transition events are marked delivered only after successful
  email delivery. SQLite failures must not fail or unblock the data job; log
  them and suppress database availability email rather than reverting to
  repeated stateless alerts.

Known job families:

- `quarter_hour_job`
- `hourly_job`
- `daily_seven_and_two_job`
- `daily_job`
- `daily_vodomery_branch_report_job`
- `weekly_job`
- `smartfuelpass_weekly_report_job`
- `monthly_job`
- `monthly_b1_v1_consumption_report_job`

## Dashboard

- Streamlit is the active dashboard.
- Navigation and permission definitions belong in `moduly/apps/dashboard/navigation_config.py`.
- Login/session behavior belongs in `moduly/apps/dashboard/auth.py`.
- Dashboard login survives browser reload through the
  `__Host-monitoring_dashboard_session` HttpOnly cookie. The cookie is always
  `Secure`, `SameSite=Lax`, and scoped to `Path=/` without a `Domain`
  attribute. FastAPI owns cookie creation and deletion through
  `/api/v1/auth/browser-session`.
- Dashboard bearer tokens use a 30-minute rolling request-inactivity limit and
  an 8-hour absolute session limit by default. Active Streamlit sessions renew
  at most once every five minutes through `/api/v1/auth/session/refresh`.
- Password, role, activation, section, page, and device-permission changes
  increment `token_version` and revoke existing bearer tokens and browser
  sessions. Email-only changes do not revoke sessions.
- New and changed dashboard passwords use one shared validator: at least 15
  characters, up to 1024 characters, Unicode and spaces allowed, no character
  composition rule, and rejection through the tracked local password
  blocklist. Passwords are NFC-normalized before hashing.
- Dashboard password hashes use PBKDF2-HMAC-SHA256 with 600,000 iterations.
  Older valid PBKDF2 hashes remain accepted and are rehashed after the next
  successful login without forcing a bulk password reset.
- Dashboard database bootstrap belongs in `moduly/apps/dashboard/database/db_init.py`.
- General map UI belongs to `moduly/apps/dashboard/pages/36_mapove_podklady.py`; map-layer administration belongs to `moduly/apps/dashboard/pages/35_mapove_vrstvy.py`.
- Shared map rendering and request helpers belong in `moduly/apps/dashboard/map_shared.py`.
- All active Streamlit dashboard pages use the shared mobile layout from `moduly/apps/dashboard/responsive.py` through the common `login.py` entry point.
- `Health systemu` is an admin-only dashboard page for post-restart and
  operational health checks. It must use authenticated FastAPI endpoints and
  display safe statuses, timestamps, listener summaries, and aggregates only.
  Do not expose secrets, environment values, bearer tokens, cookie values,
  raw process command lines, raw portal rows, or raw device photo paths.
- Desktop remains the default layout; mobile rules apply below the shared `720px` breakpoint.
- On mobile, general page columns stack vertically, metric rows use two cards per row, and tables, charts, forms, dialogs, tabs, images, and action buttons must remain usable without page-level horizontal overflow.
- Mobile map geolocation stays in the browser, is requested only after a user action, and must not be persisted or sent to the API.
- Browser geolocation on a remote phone requires the dashboard to be opened through a trusted HTTPS origin; plain LAN HTTP is not sufficient.
- For dashboard page changes, prefer small helpers and tested filtering/formatting behavior.
- For visual or UX changes, preserve existing project patterns unless the user explicitly asks for redesign.
- Branch overview hourly graphs plot the current incomplete hour at the latest real measurement timestamp so the chart does not appear stale.
- Vodomery overview graphs build the prediction series independently across
  the complete selected date range. Actual and cumulative-actual series stop
  at the last available measurement and must not be extended into future
  buckets with zero consumption.
- Vodomery photo paths stored under `P:\` require a server-side fallback to `\\SERVER1A\Company\`, because service processes may not inherit interactive mapped drives.
- Map GeoJSON should expose only photo availability such as `has_photo`; raw and resolved filesystem paths must remain server-side.
- The `B1_V1` monthly report runs on the last Czech business day at 13:03 and uses the interval from 13:15 on the previous month's last Czech business day through 13:00 on the current month's last Czech business day.

## Measurement Domains

- `vodomery`: water meters, AREAL/SCVK sources, anomaly models, events, alerting, outlier review, reports, billing logic.
- `plynomery`: gas meters, baseline and weather-adjusted models, expected-zero/outlier/alerting behavior, and manual billing-reading PDF workflow.
- `elektromery`: electricity meters, SOFTLINK and binary imports, OTE reporting, new device discovery.
- `kalorimetry`: heat meter imports, normalization, and outlier review.
- `manometry`: pressure measurements, imports, dashboard/API surfaces.
- `smartfuelpass`: fuel/card import and reporting workflow with manual Excel
  import. Administrator-selected `ChargingSessions` `.xlsx` imports persist
  charge sessions to PostgreSQL; weekly reporting reads the database rows.
- `web_search`: monitored web search and result persistence.

Water event types currently include examples such as:

- `NIGHT_USAGE`
- `SPIKE`
- `LONG_LEAK`
- `SUSTAINED_HIGH_USAGE`
- `ZERO_FLOW`
- `EXPECTED_ZERO_USAGE`
- `OUTLIER_REVIEW`

## Testing

Prefer targeted tests first, then broader tests when risk justifies it.

- `tests/test_api_authorization_regression.py` is the executable authorization
  inventory for FastAPI. New or changed routes must update its explicit public,
  admin, section/page, and device-scope expectations and preserve unauthenticated
  HTTP 401 and unauthorized HTTP 403 behavior.

Common commands:

```powershell
python -m pytest tests -v --tb=short
python -m pytest tests\test_scheduler.py -v --tb=short
python -m pytest tests\test_vodomery_db_import.py -v --tb=short
python -m pytest tests\test_dashboard_navigation_config.py -v --tb=short
.venv\Scripts\python.exe -m pytest tests\test_map_routes.py tests\test_map_layers_service.py tests\test_dashboard_map_shared.py tests\test_dashboard_navigation_config.py tests\test_device_map_service.py tests\test_dashboard_responsive.py -v --tb=short
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
5. Propose updates to `agents/decisions/DECISIONS.md` or
   `agents/history/SESSION_NOTES.md` if needed.
