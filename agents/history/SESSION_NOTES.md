# SESSION_NOTES.md

Purpose: short current project baseline and handoff for
`monitorovaci_platforma`. Detailed historical entries are stored in
`archive/`.

## Current baseline

Date: 2026-08-21

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

- 2026-08-24 dashboard map UI handoff: `Mapove podklady / Mapa` now uses a
  full-width Streamlit iframe with Leaflet-owned base-layer, overlay,
  location, and visible-layer filter controls. The map includes a `Bez mapy`
  white-base option; hidden overlays lazy-initialize their GeoJSON only when
  enabled, and the in-map filter panel shows only currently visible
  filterable layers grouped per layer. Streamlit still prepares the safe
  catalog/filter-options/features payload with bearer auth; iframe JavaScript
  receives no bearer token and does not call map feature/filter APIs directly.
- Active product work: `OPS-002`, the independent read-only scheduler
  monitoring agent.
- Remote `0.8.1-test` is deployed on the separate supervision center and runs
  continuously through the Windows Scheduled Task `MonitoringAgentTest`. The
  task owns the only continuous writer, runs as `SYSTEM`, and uses the
  project-local Python 3.14 virtual environment. Legacy alerts remain
  authoritative.
- Current pause point for the remote agent test: on 2026-08-21 the supervision
  station is running standalone commit
  `b6f4e047d59d14d0e34ac61c1a4e270b386f6ae9`
  (`Add automatic test delivery gate`) from
  `https://github.com/mtravnicekarmex/monitoring-agent-0.8.1.git`.
  `DELIVERY_AUTOMATION_ENABLED=true` is enabled in the remote local `.env`.
  This is still controlled test-only delivery: only `DELIVERY_TEST_RECIPIENT`,
  at most one due pending outbox item after a completed cycle, and no
  production recipients, provider execution, remediation, process control,
  alert suppression, or legacy-alert replacement.
- Latest supplied remote audit on 2026-08-21 after the start/restart check
  showed `MonitoringAgentTest` `Running`, audit contract 8, latest heartbeat
  `healthy`, nine latest observations, zero latest transport failures,
  `shadow_incidents.delivery_enabled=true`, `outbox_pending_count=0`,
  `outbox_sent_count=1`, `outbox_dead_letter_count=14`, and shadow update time
  `2026-08-21T11:08:28.897356+00:00`. The active state count remained 1,
  still tied to `endpoint:system_scheduler`; because pending outbox is zero,
  no immediate email should have been sent at activation. If that active
  scheduler incident later recovers, a recovery outbox item may be sent
  automatically to the configured test recipient.
- The 0.8.1 runtime uses the intentional clean
  `monitoring-agent-state-ops002` baseline. Env-v1 bridge recovery, the
  target scheduler-detail timezone restart, env-v2 nine-endpoint proof, and
  continuous Scheduled Task restoration all passed.
- On 2026-08-14 the latest audit-v7 heartbeat was `healthy` with nine
  observations and zero latest transport failures. The task was `Running`;
  `LastTaskResult=267009` / `0x41301` is the expected currently-running task
  status. Lifecycle was a clean open continuous run with no new
  concurrent-start, run-reentry, unclean, abandoned, incomplete, or overlap
  evidence.
- The standalone GitHub repository
  `https://github.com/mtravnicekarmex/monitoring-agent-0.8.1.git` is public
  on `master`; the active test-checkout identity is the commit pulled on the
  supervision station, currently
  `b6f4e047d59d14d0e34ac61c1a4e270b386f6ae9`. The user switched the test
  iteration workflow from per-change ZIP bundles to direct Git pulls. Treat
  the pulled Git commit hash as the active test-checkout identity; the
  original 0.8.1 ZIP manifest remains historical release evidence only.
- Roadmap items 1, 2, 3, 4, 5, and 6 are complete as of 2026-08-14; item 7 is
  complete as of 2026-08-17. Local source
  contains incident-rule version 1, bounded incident/outbox state,
  observation retention, pure report/programming-agent prompt rendering, and
  a disabled-by-default test-only Outlook delivery adapter, plus pure
  draft-only interpretation over confirmed incidents. The supervision station
  verified commit `5cfc5916d3e83cdcc1eecd34f3f2719d62ec351c`, loaded the
  configured test recipient only as a hash, prepared an isolated synthetic
  outbox/report, dry-ran one due item, and sent one explicitly confirmed
  synthetic test email through `send-due` with sanitized result
  `status="sent"`, `action="opened"`, `attempt_count=1`, and no error code.
  Independent center observation, real interpretation-provider execution,
  production delivery, and legacy-alert replacement remain separate later
  gates. Automatic delivery is now approved only for the controlled
  test-recipient runtime gate recorded above.
- After pulling commit `86ee42b058c74675976904c1e51a2f3677c5f138`, the
  supervision station reported `--check-config` valid with endpoint count 9,
  env contract 2, and mode `test`. Audit-v7 then reported 289 complete cycles,
  latest heartbeat `healthy`, nine latest observations, zero latest transport
  failures, valid endpoint/cycle order, valid retry/attempt bounds, clean open
  continuous lifecycle, and no new concurrent-start, run-reentry, unclean,
  abandoned, incomplete, or overlap evidence.
- After pulling commit `3e7b94e9045527a1254b10066a3a34493577f025`, the
  supervision station again reported `--check-config` valid with endpoint
  count 9, env contract 2, and mode `test`. Audit-v7 reported 323 complete
  cycles, latest heartbeat `healthy`, nine latest observations, zero latest
  transport failures, valid ordering/retry/timing, clean open continuous
  lifecycle, and no new lifecycle/writer anomalies.
- Local source on 2026-08-17 adds `monitoring_agent/runtime_shadow.py` and
  wires deterministic incident evaluation into the polling loop after each
  completed cycle. It persists bounded `incident_state.json`, emits sanitized
  `shadow_incidents`, and advances `--audit-state` to audit contract 8. It
  adds no `.env` key and does not enable automatic delivery, provider
  execution, remediation, process control, or legacy-alert replacement.
  Targeted runtime-shadow/agent tests passed with `91 passed`; the broader
  monitoring-agent matrix passed with `169 passed`. This was pushed to the
  standalone Git repository as commit
  `207fc1d38d066cdc642dc86bc0cc0b2b6c817cfc`
  (`Wire shadow incident persistence`) with 21-file Git manifest SHA-256
  `4011bb7de330b30371199123dca41aabaaddecd267293dadf990c91f57445287`. This
  exact commit did not become the final remote proof because activation found
  the env-v2 compatibility bug below.
- Remote activation of `207fc1d38d066cdc642dc86bc0cc0b2b6c817cfc` on
  2026-08-17 exposed a source bug before runtime-shadow proof: the Scheduled
  Task exited with `LastTaskResult=1`, and foreground `--once` reported
  `client setup error: external web URL is required by the endpoint set`.
  The remote `.env` was not missing a key; env contract 2 includes
  `MONITORING_AGENT_EXTERNAL_WEB_URL`, but `RuntimeSettings.load()` loaded
  that value only for env contract 3. Follow-up commit
  `e23f5f893d76951995a8b6df833e60aadb96a858` fixed and remote-proved the
  external web URL loading for env v2 and env v3.
- Follow-up standalone commit
  `e23f5f893d76951995a8b6df833e60aadb96a858`
  (`Load external web URL for env v2`) fixes that compatibility bug by loading
  `MONITORING_AGENT_EXTERNAL_WEB_URL` whenever the accepted env contract
  contains it, including env v2. The Git manifest still declares 21 runtime
  files and has SHA-256
  `b15c3d6288352c051a30e5693ea710b19b826d7c62bd6e803be0b79163e7d113`.
  Targeted env-v2/runner tests passed with `3 passed`; the broader
  monitoring-agent matrix passed with `169 passed`.
- Remote proof of `e23f5f893d76951995a8b6df833e60aadb96a858` completed on
  2026-08-17. `--check-config` returned env contract 2, endpoint count 9, and
  test mode. With the task stopped, foreground `--once` completed one
  nine-observation success cycle and created `incident_state.json`; audit-v8
  reported `shadow_incidents.present=true`, `mode="shadow_only"`,
  `delivery_enabled=false`, `state_count=0`, and `outbox_count=0`. After
  restarting `MonitoringAgentTest`, the task was `Running`; audit-v8 reported
  latest heartbeat `healthy`, nine latest observations, zero latest transport
  failures, current-run observation count 27, and shadow state updated at
  `2026-08-17T07:00:53.832229+00:00`. Retained lifecycle/sequence findings
  `unclean_restart_count=2`, `start_while_prior_run_open_count=2`,
  `abandoned_unclosed_run_count=1`, and `cycle_sequence_valid=false` are
  planned activation artifacts from the stopped long-running process and
  foreground `--once`.
- Local item-7 follow-up on 2026-08-17 adds
  `monitoring_agent/shadow_pilot_cli.py` plus parser/export helpers. It
  exports comparable monitoring-agent events from an explicit
  `incident_state.json`, consumes supplied sanitized `legacy_alert` event
  JSON, and writes operator-requested JSON/Markdown comparison output for a
  reviewed period. It does not read `.env`, inspect production DBs or
  mailboxes, poll endpoints, send email, claim outbox items, call providers,
  mutate state, control processes, remediate, or suppress/replace alerts.
  Local verification passed with `13 passed` for focused shadow-pilot tests,
  `159 passed` for `tests/test_monitoring_agent*.py`, Python compileall, and
  `git diff --check` with line-ending warnings only. The standalone GitHub
  repository was pushed to commit
  `3c6502c74d478a7518d3bbc37f7799951bbbaba4`
  (`Add shadow pilot file comparison CLI`) with 22-file Git manifest SHA-256
  `f10e0392b2e294956f522f62df270859fad7c153ba4dee6a7fbac2fbba760c11`.
  The supervision station pulled and verified this commit on 2026-08-17:
  `--check-config` returned env contract 2, endpoint count 9, and test mode;
  audit-v8 reported latest heartbeat `healthy`, nine latest observations,
  zero latest transport failures, current-run observation count 315, and
  `shadow_incidents.present=true`, `mode="shadow_only"`,
  `delivery_enabled=false`, `state_count=0`, `outbox_count=0`, updated at
  `2026-08-17T07:34:19.759021+00:00`. Retained lifecycle/sequence findings
  remain the planned activation artifacts from the earlier stopped process
  and foreground `--once`.
- Local legacy input preparation on 2026-08-17 adds
  `scripts/export_database_availability_shadow_events.py`, a read-only
  sanitizer/exporter for delivered rows in
  `core/scheduler/data/database_availability.sqlite3`. It maps
  `unavailable`/`recovered` to `alerted`/`resolved` for
  `endpoint:system_database`, omits raw `reason` text, does not read `.env`,
  does not call the email backend, and does not mutate the store. Local
  inspection found six delivered historical DB-availability events:
  MSSQL unavailable/recovered on 2026-06-13, PostgreSQL
  unavailable/recovered on 2026-06-13, and PostgreSQL
  unavailable/recovered on 2026-07-18. No matching scheduler/runtime
  alert/error patterns were found in current scheduler logs during the
  active shadow-runtime period. Exporter/CLI/shadow tests passed with
  `15 passed`; compileall passed for the exporter and its test.
- Remote no-event baseline comparison on 2026-08-17 covered the reviewed
  period `2026-08-17T07:00:00+00:00 <= event <
  2026-08-17T07:35:00+00:00`. The supervision station exported agent events
  from `incident_state.json`, used an explicitly empty sanitized
  `legacy_alert` event file, and ran `shadow_pilot_cli compare`. The generated
  report at `2026-08-17T07:52:10.639549+00:00` stayed
  `mode="shadow_only"` and reported zero matched detections, zero
  agent-only/legacy-only detections, zero matched recoveries, zero
  agent-only/legacy-only recoveries, zero duplicates, and zero blind spots.
  This proves the healthy current-alert no-event baseline.
- Remote synthetic comparison mechanics proof on 2026-08-17 covered the
  file-only period `2026-08-17T08:00:00+00:00 <= event <
  2026-08-17T09:00:00+00:00`. The generated report at
  `2026-08-17T08:07:12.386903+00:00` reported matched detections 1,
  agent-only detections/false positives 1, legacy-only detections/false
  negatives 1, matched recoveries 1, recovery mismatches 0, duplicates 0/0,
  blind spots 0/0/0, and both confirmation and recovery delay as agent later
  by 60 seconds. The safety boundary remained explicit: legacy alerts remain
  authoritative and no alert may be replaced, disabled, rerouted, or
  downgraded without separate approval. This completes item 7 without waiting
  for or inducing an operational incident.
- Roadmap item 8 started on 2026-08-17 with the first local data-bearing
  agent: `local_monitoring_agents/database_availability.py`. The agent reads
  the local scheduler `database_availability.sqlite3` store in SQLite
  read-only mode, writes bounded sanitized agent-owned state under the
  ignored `.local-monitoring-agent-state/` directory with its own writer lock,
  and exposes only aggregate service counts/statuses through the authenticated
  monitoring facade route
  `/api/v1/monitoring/health/local-agents/database-availability`. The direct
  local one-shot run returned sanitized `status="ok"`, `service_count=2`,
  `pending_event_count=0`, `unavailable_service_count=0`, and
  `stale_service_count=0`. No `.env` key, email delivery, provider execution,
  scheduler/application mutation, process control, remediation, raw reason
  text, service labels, SQLite path, SQL, or alert replacement was added.
  Targeted local-agent/facade tests passed with `19 passed`; compileall passed.
- Item 8 continued on 2026-08-17 with a controlled scheduling helper for the
  first local agent and a second local data-bearing agent:
  `local_monitoring_agents/scheduler_metrics.py`. The DB-availability task
  helper `scripts/register_database_availability_local_agent_task.ps1`
  registers a limited current-user recurring task with `IgnoreNew`, working
  directory set to the project root, and a two-minute execution limit; it does
  not start/stop/unregister tasks or read `.env`. The scheduler-metrics agent
  reads `core/scheduler/logs/scheduler_metrics.json` read-only, interprets
  naive scheduler timestamps as Europe/Prague local time, normalizes raw job
  `last_status` into bounded classes, writes sanitized agent-owned state under
  `.local-monitoring-agent-state/`, and exposes only safe aggregate fields at
  `/api/v1/monitoring/health/local-agents/scheduler-metrics`. The real local
  one-shot returned `status="degraded"`, `scheduler_running=true`,
  `job_count=51`, `success_count_24h=2594`, `failure_count_24h=0`,
  `error_job_count=2`, and `degraded_job_count=0`; this is fail-visible
  evidence of historical last-error job states, not a 24h failure count. No
  labels, descriptions, raw skipped reasons, logs, paths, `.env`, delivery,
  provider execution, mutation, process control, remediation, or alert
  replacement was added. Targeted local-agent/facade/shadow tests passed with
  `40 passed`; compileall passed. Item 8 remains open for controlled local
  scheduling/facade polling proof before any item-9 orchestrator work.
- Controlled local Scheduled Task proof for the first item-8 local agent
  completed on 2026-08-17. `MonitoringDatabaseAvailabilityLocalAgent` did not
  previously exist, was registered by
  `scripts/register_database_availability_local_agent_task.ps1` with the
  project `.venv` Python, project-root working directory, current-user limited
  principal, `IgnoreNew`, `StartWhenAvailable`, five-minute repetition, and a
  two-minute execution limit. A manual `Start-ScheduledTask` run finished with
  `LastTaskResult=0`. The first automatic trigger ran at
  `2026-08-17 13:23:21 +02:00`, finished with `LastTaskResult=0`, had
  `NumberOfMissedRuns=0`, and scheduled the next run for
  `2026-08-17 13:28:21 +02:00`. The facade aggregate immediately after the
  scheduled run was `status="ok"`, `service_count=2`,
  `pending_event_count=0`, `unavailable_service_count=0`, and
  `stale_service_count=0`. No remote polling set, remote `.env`, delivery,
  provider execution, scheduler/application mutation, process control,
  remediation, or alert replacement changed.
- The item-8 runtime direction was then changed to a shared local runner for
  multiple agents rather than one Scheduled Task per agent.
  `scripts/run_local_monitoring_agents.py` now runs approved local agents in
  deterministic order, currently DB availability and scheduler metrics, while
  each agent keeps its own state file and writer lock. The runner returns a
  sanitized aggregate `local_monitoring_agents_cycle`; agent-reported
  `degraded` or `error` is monitoring evidence and does not make the runner
  fail. Runner failure is reserved for execution/schema exceptions.
  `scripts/register_local_monitoring_agents_task.ps1` can register the shared
  runner as a limited current-user recurring task with `IgnoreNew`,
  project-root working directory, and a three-minute execution limit.
  It was parsed successfully. Manual shared-runner proof against real local
  sources returned overall `status="degraded"` with DB availability
  `status="ok"` and scheduler metrics `status="degraded"`,
  `scheduler_running=true`, `job_count=51`, `success_count_24h=2594`,
  `failure_count_24h=0`, `error_job_count=2`, and `degraded_job_count=0`.
  Verification returned `43 passed`, shared registrar parse OK, and compileall
  passed.
- Controlled migration to the shared local task completed on 2026-08-17.
  `MonitoringDatabaseAvailabilityLocalAgent` was stopped/removed and verified
  absent. `MonitoringLocalAgents` was registered with project `.venv` Python,
  project-root working directory, current-user limited principal, `IgnoreNew`,
  `StartWhenAvailable`, five-minute repetition, and a three-minute execution
  limit. A manual run completed at `2026-08-17 13:41:50 +02:00` with
  `LastTaskResult=0`. The first automatic trigger ran at
  `2026-08-17 13:42:32 +02:00` with `LastTaskResult=0`,
  `NumberOfMissedRuns=0`, and next run `2026-08-17 13:47:32 +02:00`. The
  sanitized facade projection after the scheduled run reported DB availability
  `status="ok"`, `service_count=2`, `pending_event_count=0`,
  `unavailable_service_count=0`, `stale_service_count=0`, and scheduler
  metrics `status="degraded"`, `scheduler_running=true`, `job_count=51`,
  `success_count_24h=2594`, `failure_count_24h=0`, `error_job_count=2`,
  `degraded_job_count=0`; both local-agent projections had no evidence gaps.
  Item 8 local-agent runtime proof is complete. No remote polling set, remote
  `.env`, delivery, provider execution, scheduler/application mutation,
  process control, remediation, or alert replacement changed.
- Roadmap item 9 design was prepared and accepted on 2026-08-17 in
  `../plans/monitoring/MONITORING_ORCHESTRATOR_DESIGN.md` and referenced from
  the supervision-center architecture. The draft is based on three verified
  agent surfaces: the remote external monitoring agent, the DB-availability
  local agent, and the scheduler-metrics local agent. It inventories shared
  contracts for stable agent identity, bounded status vocabulary,
  freshness/staleness, evidence gaps, safe aggregate projections,
  lifecycle/single-writer proof, incident/report references, and shadow
  comparison. The proposed v1 orchestrator is supervision-center-local and
  read-only: it may correlate center-owned audit summaries, file-only
  sanitized snapshots, and later separately approved GET-only facade reads.
  The user approved purpose/scope, evidence baseline, shared contracts,
  non-goals, placement/data flow, registry and snapshot contract, correlation
  rules, failure isolation, and pilot sequence. Roadmap item 9 is complete.
  The next approved implementation scope is file-only/shadow-only
  orchestrator CLI over sanitized sample snapshots. No runtime orchestrator,
  live polling, scheduling, polling-set change, `.env` change, delivery,
  provider execution, process control, remediation, or alert replacement was
  added.
- The approved item-9 file-only CLI scope was implemented locally on
  2026-08-17. `monitoring_agent/orchestrator.py` adds the static registry,
  normalized `AgentSnapshot`, status/freshness/evidence-gap/count handling,
  sanitized payload digests, bounded correlation findings, duplicate-key
  fail-closed validation, `.env` source rejection, and the approved v1
  correlation rules. `monitoring_agent/orchestrator_cli.py` adds
  `python -m monitoring_agent.orchestrator_cli run` over supplied sanitized
  files only. Supported payload kinds are `agent_snapshot_v1`,
  `local_agent_facade_v1`, and `remote_agent_audit_v8`. Verification returned
  `8 passed` for `tests/test_monitoring_agent_orchestrator.py` and
  `49 passed` for the focused orchestrator/shadow/local-agent/facade set.
  This source was later extended by the 2026-08-18 remote-audit timestamp
  wrapper. No live polling, scheduling, remote `.env` or polling-set change,
  delivery, provider execution, process control, remediation, or alert
  replacement was added.
- Item 9 remote-audit timestamp wrapper was added locally on 2026-08-18.
  `monitoring_agent/orchestrator_export_cli.py` provides
  `python -m monitoring_agent.orchestrator_export_cli wrap-remote-audit` for
  file-only wrapping of supplied sanitized remote `--audit-state` JSON with
  `captured_at`. It accepts file or stdin input, rejects `.env` paths and
  non-`agent_state_audit` payloads, and writes only a copied wrapped JSON
  output. The orchestrator remote-audit parser now uses `captured_at` before
  falling back to `checked_at` or `generated_at`.
- Item 9 local-only file preflight ran on 2026-08-18. The shared local runner
  refreshed local sanitized state and returned DB availability `status="ok"`
  plus scheduler metrics `status="degraded"`, `failure_count_24h=0`,
  `error_job_count=2`, and `job_count=51`.
  `scripts/export_monitoring_orchestrator_local_inputs.py` exported local
  facade aggregate snapshots to
  `artifacts/monitoring/orchestrator/2026-08-18-file-only-pilot/`, and
  `python -m monitoring_agent.orchestrator_cli run` over the local-only
  registry wrote `orchestrator-local-preflight.json` and
  `orchestrator-local-preflight.md`. The result was `status="degraded"` with
  two fresh sources, no evidence gaps, and correlation
  `scheduler_historical_error_states_no_recent_failures`. This is not the
  full three-surface pilot; the current remote `--audit-state` JSON from the
  supervision station is still required.
- Item 9 full three-surface file-only pilot completed on 2026-08-18. The
  supervision station supplied a sanitized audit-v8 `--audit-state` JSON. The
  full registry consumed `external_health`, `database_availability`, and
  `scheduler_metrics` from files only and wrote
  `artifacts/monitoring/orchestrator/2026-08-18-file-only-pilot/orchestrator-full-pilot.json`
  plus `.md`. Result: three fresh sources, two `ok` sources, one `degraded`
  source, no unavailable/error/invalid/stale sources, and overall
  `status="degraded"`. `external_health` was `ok` with evidence gaps
  `heartbeat_transition_history_not_persisted` and `source_timestamp_missing`;
  the latter is expected for raw `--audit-state` JSON because it has no
  generated/checked timestamp. DB availability was `ok` with no evidence gaps.
  Scheduler metrics was `degraded` with no evidence gaps,
  `failure_count_24h=0`, `error_job_count=2`, and `job_count=51`. The only
  correlation was `scheduler_historical_error_states_no_recent_failures`.
  Remote latest heartbeat was healthy with nine latest observations and zero
  latest transport failures; shadow incidents remained `mode="shadow_only"`
  and `delivery_enabled=false`, with two pending outbox intents. No live
  polling, deployment, scheduling, remote `.env` or polling-set change,
  delivery, provider execution, process control, remediation, or alert
  replacement was added.
- Item 9 captured-audit rerun completed on 2026-08-18. The same supplied
  remote audit was wrapped with `captured_at` and the file-only pilot was
  rerun, writing
  `artifacts/monitoring/orchestrator/2026-08-18-file-only-pilot/orchestrator-full-pilot-captured.json`
  plus `.md`. Result: overall `status="degraded"` remained unchanged,
  `external_health status="ok"` retained only
  `heartbeat_transition_history_not_persisted`,
  `database_availability status="ok"` had no evidence gaps, and
  `scheduler_metrics status="degraded"` had no evidence gaps with correlation
  `scheduler_historical_error_states_no_recent_failures`. Verification
  returned `18 passed` for focused orchestrator/export/helper tests,
  `190 passed` for the broader monitoring-agent/local-agent set, Python
  compileall passed, and `git diff --check` passed.
- Standalone GitHub commit
  `f6583d80a77695b3f4a094337251c6835b389b59` was pushed to `master` on
  2026-08-21 to make the item-9 file-only orchestrator wrapper available to
  the supervision station through the established `git pull` workflow. The
  commit adds `monitoring_agent/orchestrator.py`,
  `monitoring_agent/orchestrator_cli.py`,
  `monitoring_agent/orchestrator_export_cli.py`, updates
  `monitoring_agent/README.md`, and regenerates `manifest.json` plus
  `manifest.sha256`. The Git manifest now declares 25 runtime files and has
  SHA-256 `37e2967efa4edbf5cfcfdeaa5a9bb8e073ef417fd2499ed058cf7085a8daf61b`.
  A temporary standalone checkout compiled, the wrapper help loaded, a sample
  stdin wrap produced `captured_at`, and every manifest-declared file hash
  matched. The supervision station then verified the same commit:
  `git rev-parse HEAD` returned
  `f6583d80a77695b3f4a094337251c6835b389b59`,
  `run_monitoring_agent.py --check-config` returned endpoint count 9, env
  contract 2, and mode `test`, and
  `monitoring_agent.orchestrator_export_cli wrap-remote-audit` wrote
  `remote-audit.json` with `event="agent_state_audit"`,
  `audit_contract_version=8`, and
  `captured_at="2026-08-21T05:21:19.603716Z"`.
- Follow-up continuous-runtime sample on 2026-08-21, taken after a
  180-second wait on the supervision station, showed `MonitoringAgentTest`
  `State=Running` and audit contract 8. Latest heartbeat was `healthy` with
  nine latest observations, zero latest transport failures, and matches to
  the last complete cycle/run. Endpoint order and retry/attempt contracts were
  valid, with no in-progress or incomplete observations. Current-run
  observation count was 9,999, latest complete-cycle count was 1,111, and
  timing stayed within the configured 94.5-second cycle budget. Retained
  lifecycle artifacts increased to `unclean_restart_count=3`,
  `start_while_prior_run_open_count=3`, and
  `abandoned_unclosed_run_count=2`; current lifecycle history remained valid,
  single-writer history was valid, and there was no concurrent start,
  run-reentry, overlap, or process-run transition evidence in the current
  sample. Shadow incidents remained `mode="shadow_only"` and
  `delivery_enabled=false`, with `active_state_count=1`, `resolved_state_count=2`,
  `outbox_pending_count=11`, and update time
  `2026-08-21T05:28:14.530041+00:00`. Treat the active/pending shadow counts
  as follow-up evidence for analysis, not as delivery authorization.
- Follow-up sanitized incident-state inspection on 2026-08-21 explained the
  active shadow count. The only active state was
  `endpoint:system_scheduler`, opened at
  `2026-08-20T00:17:37.512339+02:00`, last observed at
  `2026-08-21T07:38:37.446088+02:00`, with
  `last_reason="endpoint_payload_status:degraded"`, `failure_count=1807`,
  and zero recovery confirmations. The user identified the operational source
  as the last two days' midnight `daily_job` failure in
  `SOFTLINK_save_to_database_all`. Outbox aggregation showed only one pending
  `opened` intent for `endpoint:system_scheduler`; the other pending intents
  belong to older `system_runtime` and `target_wide_outage` transitions. This
  is shadow-only evidence and not repeated email delivery.
- 2026-08-21 source review of the SOFTLINK failure found the direct failure in
  `moduly/mereni/elektromery/SOFTLINK/SOFTLINK_data_z_dotazu.py`: after
  submitting the SOFTLINK login form, Playwright waited 30 seconds for visible
  `text=Odhlásit` and timed out on both 2026-08-20 and 2026-08-21. The
  preflight database checks were healthy, so this was a SOFTLINK login/session
  problem, not a scheduler/database-lock problem. The user confirmed the
  SOFTLINK credentials changed. Source was updated so scheduled `daily_job`
  runs only `meteo_sync` while the SOFTLINK measurement import and
  `elektromery_softlink_monitoring_import` are paused and removed from the
  manual scheduler registry. `daily_job` now uses an independent-step runner
  that continues after a failed independent step and raises one aggregate
  scheduler error after attempting all configured steps. `SOFTLINK_save_to_database_all()`
  lazy-loads SOFTLINK credential-dependent modules only when explicitly called.
  Return gate: rework `SOFTLINK_data_z_dotazu.py` to the robust
  saved-session/API-validation pattern already used in
  `SOFTLINK_data_zarizeni.py`, then re-add the paused scheduler steps after
  login verification. Verification:
  `.venv\Scripts\python.exe -m pytest tests\test_scheduler.py -q` returned
  `58 passed`; `py -3.14 -m py_compile` passed for the touched scheduler
  modules/tests; `git diff --check` passed with line-ending normalization
  warnings only.
- Standalone commit
  `601a50587c73627835d4860b2212a82a92670f12`
  (`Collapse redundant incident updates`) was pushed to
  `https://github.com/mtravnicekarmex/monitoring-agent-0.8.1.git` on
  2026-08-21. It keeps incident state and outbox behavior unchanged but
  collapses redundant unchanged `updated` transition records so long-running
  active incidents do not evict meaningful history. It also updates the
  recommended steady-state `.env.example` profile to
  `MONITORING_AGENT_POLL_INTERVAL_SECONDS=300.0` and
  `MONITORING_AGENT_POLL_JITTER_SECONDS=30.0`, matching the user's remote
  `.env` change, and regenerates the 25-file Git manifest with SHA-256
  `07e08ccd56275a30e0169b863c60aee07241ba2f1c7126fb19989382c2c1a349`.
  Local verification returned `14 passed` for incident-store/runtime-shadow
  tests, `128 passed` for the broader monitoring-agent focused set,
  standalone compileall passed, and a line-ending-tolerant manifest check
  passed. The supervision station then pulled and verified this commit:
  `git rev-parse HEAD` returned
  `601a50587c73627835d4860b2212a82a92670f12`, `--check-config` returned
  endpoint count 9, env contract 2, and mode `test`, and audit contract 8
  reported `poll_interval_seconds=300.0`,
  `poll_jitter_seconds=30.0`, latest heartbeat `healthy`, and zero latest
  transport failures. The first audit after pull still reflected retained
  60-second runtime history, so the Scheduled Task was stopped; the process
  check found no remaining agent process. After restart and a 420-second wait,
  the audit showed a new 310.977-second scheduled interval inside the
  332-second allowed maximum, while `MonitoringAgentTest` remained `Running`.
  A transition-compaction check at `2026-08-21T10:02:52.185543+02:00`
  showed the last repeated `endpoint:system_scheduler` unchanged `updated`
  record at `2026-08-21T08:15:17.351985+02:00`, before the restarted
  300-second runtime, and no further unchanged scheduler `updated` records in
  the recent history.
- 2026-08-21 controlled alert-email test progression: standalone commit
  `19919303fe50a280ca7e2c84b10c9a66887c9f05` added sanitized
  `delivery_cli review-outbox`, and commit
  `7390aeb03303736a34d924dc6c229ab85bb1c1d5` added `skip-outbox`.
  The supervision station first reviewed 15 due pending items, then sent one
  manually confirmed test email for
  `incident-report:v1:endpoint:system_scheduler:opened:2026-08-19T22:17:37.512339+00:00`
  using `send-due --confirm SEND_TEST_DELIVERY`. The sanitized result was
  `status="sent"`, `action="opened"`, `attempt_count=1`, and no error code.
  Afterward the remaining 14 historical pending outbox intents were
  operator-skipped with `skip-outbox --confirm SKIP_PENDING_OUTBOX`; their
  terminal state became `dead_letter` with
  `last_error_code="operator_skipped"`. A follow-up `review-outbox` showed
  `due_pending_count=0`, `status_counts={"dead_letter":14,"sent":1}`.
  The task was restarted and audit-v8 remained healthy with
  `outbox_pending_count=0`, `outbox_dead_letter_count=14`,
  `outbox_sent_count=1`, `delivery_enabled=false`, and one active
  `endpoint:system_scheduler` state.
- Standalone commit
  `b6f4e047d59d14d0e34ac61c1a4e270b386f6ae9`
  (`Add automatic test delivery gate`) was pushed on 2026-08-21. It adds
  `monitoring_agent/runtime_delivery.py`, reads the explicit non-
  `MONITORING_AGENT_` gate `DELIVERY_AUTOMATION_ENABLED`, wires runtime
  delivery after completed polling cycles, refreshes the shadow summary after
  sent/failed delivery attempts, and documents controlled automatic
  test-only delivery. It sends at most one due pending outbox item per cycle,
  only to `DELIVERY_TEST_RECIPIENT`, using existing Outlook test credentials
  and sanitized deterministic report text generated from `incident_state.json`.
  It does not add production recipients, provider execution, monitored-target
  mutation, remediation, process control, alert suppression, or legacy-alert
  replacement. The standalone Git manifest declares 26 files and has SHA-256
  `429fac118d8e67bbadd8e1b53b55154953eba0a07aafd1225ec3ed40f68371cc`.
  Local verification passed with 19 runtime-delivery/shadow/delivery tests,
  89 main monitoring-agent tests, compileall, standalone env-v2
  `--check-config`, and fake-transport smoke proof that one due outbox item is
  marked `sent`.
- The supervision station pulled commit
  `b6f4e047d59d14d0e34ac61c1a4e270b386f6ae9`, validated config, enabled
  `DELIVERY_AUTOMATION_ENABLED=true` in the local `.env`, and restarted
  `MonitoringAgentTest`. The latest supplied audit on 2026-08-21 reported
  `MonitoringAgentTest` `Running`, audit contract 8, latest heartbeat
  `healthy`, nine latest observations, zero latest transport failures,
  `shadow_incidents.mode="shadow_only"`,
  `shadow_incidents.delivery_enabled=true`, `active_state_count=1`,
  `resolved_state_count=2`, `outbox_count=15`, `outbox_pending_count=0`,
  `outbox_sent_count=1`, `outbox_dead_letter_count=14`, and update time
  `2026-08-21T11:08:28.897356+00:00`. No immediate automatic email is
  expected because pending outbox is zero. If the active
  `endpoint:system_scheduler` incident later recovers, the recovery intent is
  expected to be sent automatically to the configured test recipient only.
  Retained lifecycle counters increased after the controlled stop/start work
  (`unclean_restart_count=7`, `start_while_prior_run_open_count=7`,
  `abandoned_unclosed_run_count=6`), but the current audit still showed no
  concurrent start, no run reentry, and no overlap evidence.
- While the Scheduled Task is running, do not start foreground continuous mode
  or `--once` against the same state. `--check-config` and `--audit-state`
  remain safe concurrent commands.

## Latest runtime verification

The read-only check after the 2026-08-05 restart found:

- Windows booted at `2026-08-05 08:13:22 +02:00` and startup task
  `API_dashboard_caddy` ran at `08:13:32` with result 0;
- listeners 80, 443, 2019, 8000, 8001, and tailnet-only 9443 were present;
  temporary listeners 8010/8011 were absent;
- local FastAPI live/ready, Streamlit health, and Caddy admin returned HTTP
  200, while the unauthenticated monitoring facade returned HTTP 401;
- tracked and deployed Caddyfile hashes matched;
- scheduler heartbeat was current and the 08:35 quarter-hour, database,
  import, plynomery, and kalorimetry steps were successful with zero failures
  in the preceding 24 hours.

The supervision-center verification completed on 2026-08-06:

- `MonitoringAgentTest` started automatically after boot and remained
  `Running` as one logical `SYSTEM` agent;
- the task definition, interpreter, working directory, startup trigger,
  duplicate suppression, and restart settings matched the reviewed contract;
- postboot state advanced from 1,036 to 1,162 complete cycles and recovered
  from transient connection errors/timeouts to a healthy four-observation
  heartbeat;
- audit sequence, endpoint order, retry bounds, lifecycle consistency, and
  latest-heartbeat consistency passed.

Treat these as dated observations, not guarantees of current runtime health.

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

The 2026-08-21 10:31 +02:00 restart handoff below is historical. The later
remote-agent state supersedes it: current supervision-station checkout is
`b6f4e047d59d14d0e34ac61c1a4e270b386f6ae9`,
`DELIVERY_AUTOMATION_ENABLED=true`, `MonitoringAgentTest` is running healthy,
and the outbox has `pending=0`, `sent=1`, `dead_letter=14`.

### 2026-08-21 10:31 +02:00 - Pre-restart handoff

Reason for restart:

- User-requested controlled Windows workstation restart to load the scheduler
  source change that pauses SOFTLINK electric-meter imports, keeps midnight
  `daily_job` on `meteo_sync` only, and makes independent `daily_job` steps
  continue after a failed independent step before raising one aggregate error.
- After restart, continue work on the remote supervision-station monitoring
  agent; do not broaden its delivery, provider, process-control, or
  alert-replacement boundary.

Current task and conversation state:

- Completed: diagnosed the last two midnight `daily_job` failures as a
  SOFTLINK login/session problem in
  `moduly/mereni/elektromery/SOFTLINK/SOFTLINK_data_z_dotazu.py`, where
  Playwright timed out waiting for visible `text=Odhlásit` after login
  submission on 2026-08-20 and 2026-08-21. The user confirmed changed
  SOFTLINK credentials.
- Completed: paused `SOFTLINK_save_to_database_all` and
  `elektromery_softlink_monitoring_import` from scheduled/manual scheduler
  execution. `daily_job` now contains only `meteo_sync`; SOFTLINK imports are
  lazy-loaded only if `SOFTLINK_save_to_database_all()` is explicitly called.
- Completed: scheduler regression verification passed:
  `.venv\Scripts\python.exe -m pytest tests\test_scheduler.py -q` returned
  `58 passed`; `py -3.14 -m py_compile` passed for touched scheduler modules
  and tests; `git diff --check` passed with line-ending normalization
  warnings only.
- Pending after restart: verify that the running scheduler process loaded the
  new source and that `daily_job` registry state is `Meteo sync.` with no
  SOFTLINK manual entries. The old `daily_job` error in scheduler metrics may
  remain visible until a later successful scheduled or separately approved
  manual `daily_job` run updates those metrics.
- First action after restart: read `AGENTS.md`,
  `agents/decisions/DECISIONS.md`, and this handoff; run
  `git status --short`; confirm the Windows boot time is after
  `2026-08-21 10:31 +02:00` and the startup task ran after that boot before
  checking services.

Remote supervision-station monitoring-agent state:

- Historical remote checkout at the time of this restart handoff:
  `601a50587c73627835d4860b2212a82a92670f12` in
  `https://github.com/mtravnicekarmex/monitoring-agent-0.8.1.git`. Do not use
  this as the current checkout after the later automatic-test-delivery
  activation; use `b6f4e047d59d14d0e34ac61c1a4e270b386f6ae9`.
- Remote config proof after pull: `--check-config` returned endpoint count 9,
  env contract 2, and mode `test`.
- Remote runtime proof after the explicit stop/no-process/start/wait cycle:
  `MonitoringAgentTest` was `Running`; audit contract 8 reported
  `poll_interval_seconds=300.0`, `poll_jitter_seconds=30.0`, latest heartbeat
  `healthy`, nine latest observations, and zero latest transport failures.
  The new observed scheduled interval was 310.977 seconds, inside the
  332-second allowed maximum.
- Remote state compaction proof: the transition check at
  `2026-08-21T10:02:52.185543+02:00` retained 2,000 bounded transition
  records and showed no new repeated unchanged
  `endpoint:system_scheduler` `updated` records after the restarted
  300-second runtime began.
- Historical latest known shadow state at the time still had
  `delivery_enabled=false`, `mode="shadow_only"`, one active
  `endpoint:system_scheduler` incident tied to the old SOFTLINK-backed
  `daily_job` failure, and pending outbox items. This was superseded later on
  2026-08-21 by the review/send/skip cleanup and automatic test-delivery
  activation: current known outbox counts are `pending=0`, `sent=1`,
  `dead_letter=14`, with `delivery_enabled=true`.
- While `MonitoringAgentTest` is running, safe concurrent commands remain
  `--check-config` and `--audit-state`. Do not start foreground continuous
  mode or `--once` against the same state unless the task is intentionally
  stopped and that action is separately approved.
- The local workstation restart may briefly produce remote target degradation
  while FastAPI/Streamlit/Caddy/scheduler are unavailable. Treat that as
  expected restart evidence if it aligns with the restart window. Do not treat
  retained lifecycle/sequence counters by themselves as current second-writer
  proof.

Working tree and deployment:

- `git status --short` is intentionally dirty. Existing monitoring-agent,
  local-agent, orchestrator, facade, docs, artifacts, and tests remain in the
  working tree; do not reset, delete, revert, or overwrite unrelated changes.
- Relevant new scheduler files for this restart:
  `core/scheduler/scheduler.py`, `core/scheduler/job_schedule.py`, and
  `tests/test_scheduler.py`.
- Relevant documentation updates:
  `AGENTS.md`, `agents/history/SESSION_NOTES.md`,
  `agents/work/ACTIVE.md`,
  `agents/plans/monitoring/MONITORING_AGENT_REPORTING_LAYER_HANDOFF.md`, and
  `agents/decisions/DECISIONS.md` (`DEC-147`).
- No Caddy configuration change is part of this restart. No `.env` change is
  required by the scheduler pause itself. SOFTLINK credentials remain a
  separate user-managed issue.

Sensitive and runtime artifacts:

- Do not print, change, delete, or commit `.env`, SOFTLINK credentials,
  `lds_auth.json`, cookies/session JSON, bearer tokens, app passwords,
  recipient values, raw scheduler logs with secrets, raw meter rows, or raw
  operational database data.
- Do not change the remote station `.env` beyond the already-approved
  `DELIVERY_AUTOMATION_ENABLED=true` test-only gate; if a future value is
  needed, ask the user to add the named variable and describe its expected
  content.
- Do not manually claim or send monitoring-agent outbox items while the
  scheduled agent is running. Delivery is now enabled only through the
  approved automatic test-only gate; production delivery and legacy-alert
  replacement remain unauthorized.

Expected processes after restart:

- FastAPI/Uvicorn: one runtime on `127.0.0.1:8000`.
- Streamlit: one runtime on `127.0.0.1:8001`.
- Scheduler: one `main.py` runtime holding the scheduler process lock.
- Caddy: one runtime owning TCP 80/443 and `127.0.0.1:2019`.
- Local monitoring agents: `MonitoringLocalAgents` should continue as the
  shared local Scheduled Task for DB-availability and scheduler-metrics
  snapshots.
- Remote supervision station: `MonitoringAgentTest` should remain the
  independent remote observer; the local workstation restart does not require
  changing its code, `.env`, task registration, or delivery settings.

Expected application state:

- FastAPI live/ready: HTTP 200 after startup settles.
- Streamlit health: HTTP 200.
- Caddy admin on `127.0.0.1:2019`: reachable locally.
- Protected monitoring facade without bearer token: HTTP 401 JSON.
- Scheduler heartbeat: current after `main.py` is running.
- `daily_job` schedule description: `Meteo sync.`
- Manual scheduler registry: `meteo_sync` present;
  `SOFTLINK_save_to_database_all` and
  `elektromery_softlink_monitoring_import` absent.
- Existing `daily_job`/`SOFTLINK_save_to_database_all` metric errors from
  2026-08-20 and 2026-08-21 may remain until a successful active `daily_job`
  run updates the metrics. This is expected retained state, not proof that the
  new source still calls SOFTLINK.

Required post-restart checks:

1. Run `git status --short` and confirm no unexpected files appeared.
2. Confirm Windows boot time is after `2026-08-21 10:31 +02:00` and
   `API_dashboard_caddy` or the active startup task has a post-boot successful
   run.
3. Confirm one FastAPI listener on `127.0.0.1:8000`, one Streamlit listener on
   `127.0.0.1:8001`, Caddy listeners on 80/443 and admin on
   `127.0.0.1:2019`, and no duplicate scheduler process.
4. Check FastAPI live/ready, Streamlit health, local Caddy admin, and
   unauthenticated monitoring facade 401.
5. Verify loaded scheduler source/registry with the project runtime:
   `daily_job` description equals `Meteo sync.`, `meteo_sync` is present in
   manual specs, and both SOFTLINK manual specs are absent.
6. Verify scheduler heartbeat/current metrics after startup. Do not manually
   run SOFTLINK.
7. On the remote supervision station, use only safe concurrent checks while
   the task is running:
   `git rev-parse HEAD`,
   `run_monitoring_agent.py --check-config`, and
   `run_monitoring_agent.py --audit-state`. Expect commit
   `b6f4e047d59d14d0e34ac61c1a4e270b386f6ae9`, env contract 2, endpoint count
   9, mode `test`, poll profile `300/30`, latest heartbeat healthy,
   `delivery_enabled=true`, and `outbox_pending_count=0`.
8. If remote `endpoint:system_scheduler` remains active immediately after the
   restart, first correlate it with retained scheduler metrics and the old
   SOFTLINK `daily_job` failure before treating it as a new incident.

Known risks or accepted gaps:

- SOFTLINK login is not fixed. The old measurement fetcher still needs to be
  rebuilt to the saved-session/API-validation pattern used by
  `SOFTLINK_data_zarizeni.py` before SOFTLINK returns to scheduler execution.
- The remote agent's historical pending outbox was reviewed on 2026-08-21.
  Current known counts are `pending=0`, `sent=1`, and `dead_letter=14`.
  Do not manually claim/send outbox items while automatic test delivery is
  enabled and the Scheduled Task is running.
- The worktree is dirty by design; preserve existing monitoring/orchestrator
  work and unrelated user changes.
- No production delivery, interpretation-provider execution, remediation,
  process control, or legacy-alert replacement is authorized by this restart.

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

### 2026-08-05 - Monitoring-agent foreground loss and recovery observed

- The `0.4.0-test` project is provisioned and running from an isolated Python
  environment on the separate supervision center. Its real local `.env` and
  agent-owned state remain outside GitHub output and were not displayed.
- The standalone public repository
  `mtravnicekarmex/monitoring_agent_0.4.0` has one `master` commit,
  `88158812000c9a91b9a7da1c61045737549a3363`. Its 11 runtime files match the
  reviewed `0.4.0-test` manifest, `.env` is absent, and `.gitignore` excludes
  live configuration, IDE state, Python caches, and local agent state. The
  repository does not track the local virtual environment, but `.venv/` is not
  yet explicitly ignored and must be added before the next commit.
- One uninterrupted foreground output sequence showed healthy cycles,
  sustained three-endpoint `timeout` cycles during target loss, one mixed
  `success`/`timeout` cycle while the target returned, and stable successful
  cycles afterward. The mixed cycle is expected because endpoints are polled
  serially and recovery occurred during the cycle.
- This functionally proves remote target-loss detection and recovery without
  restarting the observer. Formal retained evidence is still required for
  bounded attempt counts, the `degraded` to `healthy` heartbeat transition,
  unchanged process identity, and serialized start-to-start timing.
- Current legacy alerts remain authoritative. No credential rotation,
  Windows automatic-start registration, external delivery, application or
  database mutation, manual job, or alert replacement was performed.

### 2026-08-05 - Monitoring-agent 0.4.1 integrity repair prepared

- Remote `master` commit `08362ec3ff504986109180bb9d1c89ea096ae19b`
  changed only `.gitignore` by adding `.venv/`. No real `.env`, virtual
  environment, state, PR, or issue was added.
- Repository preflight found the expected integrity failure: `manifest.json`
  still declared the preceding 88-byte `.gitignore`, while the hardened file
  is 95 bytes with SHA-256
  `E4924A6E050E0769863BAB798E453493383CEEB636727CA2210CF24D70C45470`.
- Local packaging source, README, and bundle regression coverage now include
  `.venv/`. Reproducible bundle `0.4.1-test` contains 11 declared runtime
  files, no real `.env`, no unexpected entries, zero file-hash mismatches, and
  a valid manifest digest.
- `0.4.1-test` ZIP SHA-256 is
  `1EEBB2E946A87E5300A72126AF9A3E358DC6EA121384D2BC8BBA568E3F5DB49B`;
  manifest SHA-256 is
  `3705F5458D2D9D4E8A8EDB556A34993FED17B4646CF61DBC1AF9AEBC2D68E437`.
- The bundle-builder regression passed and the complete
  monitoring-agent/facade/authorization matrix passed with `267 passed`.
  The new bundle has not yet been synchronized to the standalone repository
  or run on the center.

### 2026-08-05 - Remote 0.4.1 verified and local 0.5 audit ready

- Standalone repository `master` commit
  `3c171cf49615cf792211f3c992320dade539ccc4` synchronized the expected README,
  `manifest.json`, and `manifest.sha256` after the preceding `.gitignore`
  hardening. The resulting `0.4.1-test` manifest digest is exact and `.env`
  remains absent.
- New read-only CLI mode `--audit-state` validates the exact observation and
  heartbeat schemas, configured endpoint sequence, attempt bounds, retry
  exhaustion, inferred cycle health/recovery transitions, timing, overlap,
  and latest heartbeat consistency.
- Audit output excludes state paths, `.env`, bearer, instance/PID values,
  UUIDs, timestamps, endpoint keys, payloads, and raw records. It reports only
  PID presence and aggregate facts. Invalid JSON/schema fails closed without
  echoing raw content.
- The current atomic heartbeat records only the latest state. The audit
  therefore declares `heartbeat_transition_history_not_persisted` and
  `process_identity_history_not_persisted` instead of claiming those proofs.
- Reproducible `0.5.0-test` contains 12 declared files, no real `.env`, no
  unexpected entries, zero hash mismatches, and a valid manifest digest. ZIP
  SHA-256 is
  `739B6C57BE2BAF24CA2F4219F7FBF358859DE53D8AC5BAC07A5B6E4F420DB748`;
  manifest SHA-256 is
  `E94580B4EEBD74FCF653F2FC699CE7EA521012C68F824261304AAFF4E2B9269A`.
- Focused monitoring-agent tests passed with `48 passed`; the combined
  monitoring-agent/facade/API-authorization matrix passed with `270 passed`;
  Python compile and `git diff --check` passed. `0.5.0-test` has not yet been
  synchronized to or executed on the center.

### 2026-08-05 - Remote audit v1 found a target-loss timing blind interval

- Remote `0.5.0-test` audit v1 read the retained agent-owned state without
  network access or writes. It reported 405 observations in 135 complete
  three-endpoint cycles, with no trailing observations or endpoint-order
  mismatches.
- Outcomes were 90 healthy, 44 fully unreachable, and one partial-failure
  cycle. The 45 degraded cycles formed two closed episodes of one and 44
  cycles. Attempt bounds and retry exhaustion passed; 133 timeout observations
  exhausted three attempts and one success completed after retry.
- The latest heartbeat was healthy, matched the last complete cycle, and used
  the same configured observer instance as all observations. Historical
  heartbeat transitions and process identity remain explicitly unpersisted.
- Timing had no overlaps or early starts, but two intervals exceeded jitter.
  The maximum start-to-start interval was 4,545.121 seconds. The user confirmed
  that the monitored station, not the supervision center, was unavailable
  during this interval. This blocks formal failure-isolation closure because
  ordinary bounded target timeouts must not suspend observer cadence that long.
- Local `0.5.1-test` audit contract v2 now reports safe configured timeout
  budget, cycle-duration aggregates, the longest cycle, longest interval, and
  largest late interval. It can distinguish time accumulated inside the
  previous cycle from a between-cycle or wall-clock discontinuity without raw
  timestamps or identifiers and without repeating the outage.
- Reproducible `0.5.1-test` contains 12 declared files, no real `.env`, no
  unexpected entries, zero hash mismatches, and a valid manifest digest. ZIP
  SHA-256 is
  `85FFDEC8E807068DFF82AEE56422B2D0FB05C57D9C6D8F6902377519B24FBBE8`;
  manifest SHA-256 is
  `7B64B7579AB93B0A2A3BF82DB9473020FD3216ED3CB8E54BF8B97ABEFBDC78E3`.
- Focused tests passed with `50 passed`; the combined monitoring-agent,
  facade, and API-authorization matrix passed with `272 passed`.
- Next synchronize and verify `0.5.1-test`, then run `--audit-state` against
  the same retained state. Do not repeat the target outage before reviewing
  `longest_cycle`, `longest_interval`, and `largest_late_interval`.

### 2026-08-05 - Supervision restart identified and 0.6 lifecycle candidate prepared

- Remote audit contract v2 processed 549 observations in 183 complete cycles.
  Its longest request cycle was 31.816 seconds against a 31.5-second configured
  all-timeout budget and remained within the two-second audit tolerance.
- The 4,545.121-second interval ended at cycle 134 after a healthy 0.071-second
  cycle, exceeded the allowed 67 seconds by 4,478.121 seconds, and was
  classified `unexplained_between_cycles_or_clock_discontinuity`. Windows
  System event times matched a supervision-station shutdown/restart. The gap
  was not caused by a blocked target HTTP request.
- Local `0.6.0-test` assigns a new random run ID per process and persists it
  with cycle ID/sequence in observation contract 2 and the latest heartbeat.
  Append-only lifecycle contract 1 records process starts and controlled stops
  with local PID evidence.
- Audit contract 3 groups observations by run/cycle identity, retains partial
  cycles across abrupt restarts, and reports only aggregate process starts,
  clean/unclean restart counts, abandoned runs, stop reasons, sequence checks,
  and lifecycle consistency. Run IDs, PID values, timestamps, paths, and raw
  records remain excluded.
- `register_monitoring_agent_task.ps1` is included as an idempotent,
  `SupportsShouldProcess`-gated helper with `-WhatIf`. Its reviewed default is
  `SYSTEM` plus `AtStartup`, `StartWhenAvailable`, one-minute failure restarts,
  `IgnoreNew`, unlimited execution, and exact interpreter/working directory.
  It contains no secret command-line value and was parsed but not executed.
- A new empty state directory is mandatory; retained v0.5 state remains
  immutable evidence and cannot acquire retrospective process identity.
- Reproducible `0.6.0-test` contains 13 declared files, no real `.env`, no
  unexpected entries, zero hash mismatches, and a valid manifest digest. ZIP
  SHA-256 is
  `41636BDD70612F0A89471CC102B5640C59AADE9DCC63E5426789F39DD77481B3`;
  manifest SHA-256 is
  `F7361A19051145A6E7C03A30AC1BEAFC762026D12FD819FDA00EDC7A84E760F1`.
- Focused monitoring-agent tests passed with `55 passed`; the combined
  monitoring-agent/facade/API-authorization matrix passed with `277 passed`;
  Python compile, PowerShell parse, manifest/no-secret verification, and
  `git diff --check` passed.
- Next synchronize and re-verify `0.6.0-test`, provision a new empty remote
  state directory, and complete foreground lifecycle/audit checks. Preview
  startup registration only with `-WhatIf`; actual registration, task start,
  reboot proof, and rollback require separate approval.

### 2026-08-05 - Remote 0.6 lifecycle passed and cross-run timing corrected

- After switching away from incompatible v0.5 state, remote audit contract 3
  accepted observation contract 2 and lifecycle contract 1. It reported two
  healthy complete cycles from two process runs, valid endpoint/cycle order,
  a matching latest heartbeat, one abandoned unclosed run, and one controlled
  `once_completed` stop.
- The 46.83-second interval between those runs was incorrectly counted as
  `early_start_count=1` and classified `scheduled_interval`. This was limited
  to aggregate audit interpretation; polling, retries, lifecycle persistence,
  and target-health recognition remained valid.
- Local `0.6.1-test` raises the audit contract to 4. Scheduled interval,
  overlap, early/late, longest-interval, and largest-late findings now compare
  only consecutive cycles sharing one `run_id`. Cross-run timing is retained
  separately through safe `cross_run_*` aggregates and
  `process_run_transition` classification.
- Observation contract 2 and lifecycle contract 1 are unchanged, so the
  current remote 0.6 state must be reused. A new empty state remains mandatory
  only when migrating from pre-0.6.
- Reproducible `0.6.1-test` contains 13 declared files and no real `.env`.
  ZIP SHA-256 is
  `18B3A8784D37737365FF276CC4BE9D21E4A4CB844A31642D03642E36392D1EE0`;
  manifest SHA-256 is
  `E1F06F2363DEC0732F8BC7C27A9669DB119788EB590BB1B364392255CF274C38`.
  Manifest digest, declared content hashes/sizes, and exact allowlist passed.
- Focused monitoring-agent tests passed with `56 passed`; the combined
  monitoring-agent/facade/API-authorization matrix passed with `278 passed`.
  Scheduled Task registration, task start, supervision reboot proof, and
  rollback remain separate approval gates.

### 2026-08-05 - Remote overlap identified and 0.6.2 single-writer lock prepared

- Remote `0.6.1-test` audit v4 processed 72 successful observations in 24
  healthy cycles. The 20 same-run intervals averaged 62.268 seconds, ranged
  from 60.111 to 64.858 seconds, and had zero early, late, or overlap findings.
  Cross-run timing no longer contaminated scheduled cadence.
- Three distinct runs generated three run transitions. Lifecycle contained a
  later `keyboard_interrupt` stop for the earlier foreground run plus one
  `once_completed` stop, proving historical process interleaving even though
  individual HTTP cycles did not overlap.
- Local `0.6.2-test` holds a non-blocking OS file lock scoped to the state
  directory before lifecycle, heartbeat, observation, or HTTP activity. A
  multiprocess regression proved that a second writer exits with a sanitized
  error and creates no runtime file; forced process termination released the
  OS lock without deleting the persistent one-byte lock file.
- Audit contract 5 adds safe run-reentry and concurrent-start facts. The
  retained remote pattern is classified as one historical reentry and one
  concurrent start, not as an unclean restart. Observation contract 2 and
  lifecycle contract 1 remain unchanged and compatible.
- Reproducible `0.6.2-test` contains 13 declared files and no real `.env`.
  ZIP SHA-256 is
  `C14A694F650BED6948450BEFA3704BF62B29359537ADE51B67B25DC9A8DC8C5D`;
  manifest SHA-256 is
  `24CD22C4F41ED9A29FB74886EBF73ED8A1539917D34A96628CDE3BAEC99CB1D4`.
  Manifest digest, archive allowlist/content, and workspace-source equality
  passed with zero mismatches.
- Focused monitoring-agent tests passed with `59 passed`; the combined
  monitoring-agent/facade/API-authorization matrix passed with `281 passed`.
- Before remote 0.6.2 startup, stop every pre-lock 0.6.0/0.6.1 polling process.
  Then retain the existing state and verify rejection/release with two
  foreground consoles. Scheduled Task registration, task start, reboot proof,
  and rollback remain separate approval gates.

### 2026-08-05 - Remote 0.6.2 single-writer proof passed

- Audit v5 before contention contained four process runs, seven lifecycle
  events, one historical run reentry, one historical concurrent start, and no
  unclean restart. The active 0.6.2 foreground run was healthy.
- A concurrent `--once` exited with the sanitized expected error
  `agent startup error: state writer lock is unavailable`. While the rejected
  invocation was attempted, the first writer added four healthy cycles, but
  process-run, transition, lifecycle-event, start, and stop counts remained
  unchanged. The rejected process therefore made no runtime-state write.
- After the first writer stopped with Ctrl+C, a controlled `--once` acquired
  the released lock and completed successfully. Final audit v5 reported 47
  healthy cycles, 141 successful observations, five starts, five controlled
  stops, ten lifecycle events, zero unclosed/abandoned runs, and a matching
  healthy heartbeat.
- Historical `process_run_reentry_count=1` and `concurrent_start_count=1`
  remained unchanged, while `unclean_restart_count=0`. No new writer overlap
  was introduced by 0.6.2. The foreground single-writer rejection and release
  proof is complete.
- At this 2026-08-05 checkpoint Scheduled Task registration remained
  unexecuted and separately gated. The later 2026-08-06 entry records the
  approved registration and reboot proof.

### 2026-08-05 - Local 0.7 System Runtime endpoint prepared

- The private monitoring facade now reuses the existing safe System Runtime
  collector at authenticated GET-only
  `/api/v1/monitoring/health/system/runtime`.
- The client validates the complete source schema but retains only approved
  boot, startup-task, and listener facts. Free text, labels, local addresses,
  process IDs, and next-run data are discarded; schema mismatches fail closed
  without retry.
- Observation contract 3 records endpoint set 2 (`live`, `ready`,
  `system_scheduler`, `system_runtime`). Audit contract 6 supports both legacy
  contract-2/set-1 and current contract-3/set-2 cycles in the existing 0.6
  append-only state, with per-set ordering, heartbeat count, and timeout
  budgets.
- Focused monitoring-agent tests passed with `62 passed`; the combined
  monitoring-agent/facade/API-authorization matrix passed with `286 passed`,
  and the extended matrix including System Health collectors passed with
  `306 passed`.
  The reproducible 13-file ZIP SHA-256 is
  `0BA56B60FD8F5A229346D565FEA33F58F57F9239FE541F216C07E79E56D7BF20`;
  manifest SHA-256 is
  `39C06473793C92FB281D509C3468493E9562CF9CDB74F27DBEA4D249C4676ACB`.
- No API restart, remote synchronization, Scheduled Task registration, or
  external delivery was performed.

### 2026-08-05 - Pre-restart handoff for facade activation

- The operator confirmed that the monitored workstation's FastAPI/Caddy
  process tree is established by the Windows startup process. Loading the new
  System Runtime facade therefore requires a full restart of the monitored
  workstation; there is no supported independent API restart in the current
  workflow.
- The read-only pre-restart baseline on 2026-08-05 found Windows boot time
  `08:13:22 +02:00`; startup task `API_dashboard_caddy` last ran at
  `08:13:32 +02:00`, returned result `0`, and is currently `Ready`. Expected
  listeners are present on ports 80, 443, 2019, 8000, 8001, and tailnet-only
  9443; temporary ports 8010/8011 are absent. Local API liveness, readiness,
  and Streamlit health each returned HTTP 200.
- At this checkpoint the source contained the new route and local 0.7 agent,
  but the running production API still had the previous facade. The route was
  therefore undeployed on 2026-08-05; the later 2026-08-06 entry records its
  activation and verification.
- Leave the independent remote `0.6.2-test` foreground observer running through
  the monitored-station restart. It should record bounded target timeouts and
  then recovery while retaining the same observer process. Do not restart the
  supervision workstation for this step.
- After boot, verify aggregate-only facts: the startup task completed
  successfully, required API/proxy/private-facade listeners returned, existing
  facade liveness/readiness/scheduler routes recovered, and authenticated
  `/api/v1/monitoring/health/system/runtime` returns HTTP 200 with the expected
  safe schema. Do not print the bearer or raw operational response.
- If the new route is absent, unauthorized, or schema-invalid, keep the 0.7
  remote upgrade blocked. Preserve the current remote state and continue from
  the 0.6.2 baseline until the monitored facade is corrected and activated.
- Once the route passes, allow the old agent to record at least one healthy
  recovery cycle, stop it with Ctrl+C, and confirm no other writer remains.
  Transfer and integrity-check the 0.7 ZIP, reuse the same state directory and
  secret values, and change only `MONITORING_AGENT_ENDPOINT_KEYS` to
  `live,ready,system_scheduler,system_runtime`.
- Run `--check-config` first and require `endpoint_count=4`; then run one
  `--once` cycle and require four successful observations. Finally run
  `--audit-state` and require audit contract 6, valid cycle/endpoint ordering,
  retry invariants, a matching healthy heartbeat, legacy contract-2/set-1
  counts, and four new contract-3/set-2 observations. Historical
  single-writer validity may remain false because the old overlap evidence is
  immutable; no new reentry/concurrent-start finding may be introduced.
- Continuous 0.7 polling, `-WhatIf` startup review, actual task registration,
  supervision reboot, incident delivery, and remaining detailed
  Scheduler/Database endpoint extensions are later gates.
- The workspace remains intentionally non-clean with the cumulative monitoring
  source, documentation, scripts, tests, and versioned ZIP artifacts. No commit
  or push was performed in this handoff. The user-created
  `data/smartfuelpass/vypisy/` directory was not inspected or changed.

### 2026-08-06 - Remote 0.7 deployment, task registration, and reboot proof

- The monitored workstation completed its supported full restart. The existing
  local startup task and required runtime surfaces recovered, and the new
  authenticated monitoring System Runtime route returned HTTP 200 with the
  reviewed schema, `runtime_status=ok`, five expected listeners, zero non-OK
  expected listeners, and no temporary listener.
- The remote `0.6.2-test` writer was stopped cleanly after recording target
  recovery. Its audit had six starts and six stops, zero open/unclean runs, and
  the historical concurrent-start/run-reentry findings unchanged at one.
- The transferred `0.7.0-test` ZIP matched SHA-256
  `0BA56B60FD8F5A229346D565FEA33F58F57F9239FE541F216C07E79E56D7BF20`.
  The manifest matched SHA-256
  `39C06473793C92FB281D509C3468493E9562CF9CDB74F27DBEA4D249C4676ACB`.
  Corrected extracted verification found 13 declared files, 15 extracted
  entries including manifests, zero invalid relative paths, zero content or
  allowlist mismatches, and no real `.env`.
- An earlier archive verifier falsely reported path escapes because its Windows
  path containment test was incorrect; hash and manifest checks had already
  passed. The corrected verifier supersedes that tooling failure.
- The first configuration migration attempt tried to copy protected ACL
  metadata and failed with `PrivilegeNotHeldException`; rollback removed the
  incomplete target `.env`. The corrected migration recreated the file,
  preserved its full key set, credential, state path, and all other values,
  changed only the endpoint count from three to four, and applied restricted
  current-identity plus `SYSTEM` ACLs.
- `--check-config` returned environment contract 1, test mode, and four
  endpoints. A controlled `--once` produced four successes. Audit v6 then
  proved endpoint set 2, observation contract 3, a matching healthy
  four-observation heartbeat, valid order/retry/timing, and compatible retained
  contract-2/set-1 history. The first audit after promotion showed seven
  starts/seven stops and no open, unclean, or abandoned run.
- Continuous foreground 0.7 polling then produced three verified healthy
  cycles. Concurrent audit showed one current open writer, valid latest
  heartbeat, and no increment to the retained historical overlap counters.
- The 0.7 project received its own CPython 3.14 `.venv`. Static access checks
  proved `SYSTEM` read/execute access to project and interpreter and read access
  to `.env`. State Modify access initially failed; explicit inherited
  `SYSTEM:(OI)(CI)M` access was then applied and verified on five existing state
  objects. No secret or path was retained in the evidence.
- The checked-in task helper could not execute because effective PowerShell
  policy was `Restricted` and the script was unsigned. No policy scope was
  changed and no bypass was used. A first equivalent inline registration ran
  without elevation, failed `PermissionDenied`, and left the task absent. The
  same reviewed contract then ran in an elevated PowerShell and registered
  `MonitoringAgentTest` successfully in `Ready` state without starting it.
- The task contract uses `SYSTEM`, service-account logon, highest run level,
  one `AtStartup` trigger, the exact project `.venv` interpreter, only the
  quoted runner path as argument, the explicit project working directory,
  `StartWhenAvailable`, `IgnoreNew`, one-minute restart interval with count
  999, no execution time limit, and battery-safe settings. Its command line
  contains no bearer, credential, URL, token, or `.env` value.
- Before reboot, Ctrl+C produced the eighth controlled process stop. Audit
  showed eight starts/eight stops, zero open/unclean/abandoned runs, a healthy
  four-observation heartbeat, and no new historical writer finding. The task
  was `Ready`, the scheduler service was running, and no foreground agent
  process remained.
- The supervision center booted at `08:11:42 +02:00`; the task launched at
  `08:12:12`. Its venv launcher and interpreter appeared as two Python
  processes but one parent-child logical agent, both owned by `SYSTEM` and in
  continuous mode. The first lifecycle state change occurred at approximately
  `08:14:02`, about 110 seconds after task launch, so the initial 75-second
  postboot audit still showed the prior closed run.
- Later state metadata and audit proved continued Scheduled Task operation. The
  final aggregate contained 1,162 complete cycles: 1,155 healthy, 3 partial
  failure, and 4 unreachable; transport totals were 3,634 success, 12
  connection error, and 6 timeout. The latest degraded snapshot recovered on
  a subsequent complete cycle to a healthy four-observation heartbeat with
  zero transport failures.
- Final lifecycle was nine starts, eight stops, one current open run, zero
  unclean restarts, and zero abandoned runs. Historical
  `concurrent_start_count=1` and `process_run_reentry_count=1` remained
  unchanged. The supervision automatic-start and restart/resume proof is
  complete for the test pilot.
- Detailed next-phase boundaries are recorded in
  `../plans/monitoring/MONITORING_AGENT_REPORTING_LAYER_HANDOFF.md`. Reporting
  must begin with deterministic rules, thresholds, incident identity/state,
  bounded local persistence, and a pure renderer over normalized facts. No
  external delivery, interpretation-provider use, application mutation, or
  legacy-alert replacement is authorized.

### 2026-08-06 - Repository-root cleanup and hygiene contract

- The repository root was reviewed without reading secret values. The
  established production paths `main.py`, `Caddyfile`, and
  `start_api_dashboard.bat` remain in place; the ignored live `.env` remains a
  documented compatibility exception.
- The monitoring bundle runner source moved to
  `monitoring_agent/bundle_root/run_monitoring_agent.py` while preserving
  `run_monitoring_agent.py` as the ZIP-root destination. The dashboard
  compatibility launcher moved to `scripts/start_api_dashboard_compat.bat`,
  development notes moved from `run.txt` to
  `agents/runbooks/LOCAL_DEVELOPMENT_COMMANDS.md`, and the Windows shortcut
  moved under `scripts/shortcuts/` without changing its target.
- Three ignored monitoring credential-rotation backup files were retained
  without content inspection and moved from the repository root to protected
  external configuration storage.
- `AGENTS.md` and DEC-117 now require narrow subdirectory placement by default.
  `tests/test_repository_hygiene.py` enforces the explicit root-file allowlist.
- The user-approved monitoring implementation order is now maintained as a
  nine-item live checklist in
  `../plans/monitoring/MONITORING_AGENT_IMPLEMENTATION_ROADMAP.md`. No item is
  checked yet. Work starts with safe observation-contract expansion and the
  external public-web probe; the orchestrator remains deferred until two or
  three independently operable agents provide evidence of shared needs.

### 2026-08-06 - Local monitoring-agent 0.8 observation expansion

- Roadmap item 1 is locally implemented but remains unchecked pending runtime
  proof. Eight authenticated GET-only facade projections cover liveness,
  readiness, system scheduler, detailed scheduler, system runtime, database,
  proxy, and SmartFuelPass health. Dedicated safe response models exclude
  transient, identifying, sensitive, and capability-bearing fields before
  network serialization while reusing the existing collectors.
- A ninth `external_web` observation is performed directly from the
  supervision center. It requires a configured public HTTPS root outside
  loopback tests, sends no monitoring bearer, follows no redirect, reads no
  response body, expects HTTP 200 with HTML content type, and persists neither
  URL nor headers. TLS, redirect, HTTP, content-type, JSON, and schema failures
  fail closed; only connection errors and timeouts receive bounded retries.
- Environment contract 2 adds `MONITORING_AGENT_EXTERNAL_WEB_URL`.
  Observation contract 4 / endpoint set 3 uses the exact nine-key order and
  adds bounded absolute clock skew where source time exists. Audit contract 7
  enforces the exact contract-to-set mapping while preserving retained
  contract-2/set-1 and contract-3/set-2 append-only history.
- With nine serialized endpoints and the retained timeout/retry settings, the
  configured worst-case cycle budget is 94.5 seconds. A complete outage may
  extend the nominal 60-second cadence, but cycles remain bounded,
  non-overlapping, and protected by the existing single-writer lock.
- The targeted monitoring/facade/system-health/scheduler/root-hygiene matrix
  passed with 186 tests, and modified Python modules compiled successfully.
  The local `0.8.0-test` bundle contains 13 declared runtime files and 15 ZIP
  entries.
  ZIP SHA-256 is
  `29BEE64FEE267F1E74BE1AA89CA621E2930262E16C0C662580DA5D2B7EBF8EF0`;
  manifest SHA-256 is
  `282DFDDA162B4D4CB2C3CE656066D47E2B03504F1434277659E20CBCBB173ADF`.
  No real `.env` is present.
- No monitored-workstation restart, remote configuration change, task change,
  external delivery, or alert replacement was performed. The deployed
  supervision runtime remains `0.7.0-test`. Next activate and verify all eight
  facade routes through the supported monitored-workstation restart, then
  perform the controlled remote 0.8 migration and require a complete
  nine-observation cycle plus audit-v7 mixed-history proof before checking
  roadmap item 1 or starting item 2.

### 2026-08-06 13:35 +02:00 - Monitoring-agent 0.8 facade pre-restart handoff

Reason for restart:

- Load the locally reviewed 0.8 monitoring-facade expansion into the running
  FastAPI process. The established production FastAPI, Streamlit, scheduler,
  and Caddy process tree is created only by the Windows startup task, so a
  controlled full restart of the monitored main workstation is the supported
  activation path. Do not substitute an ad-hoc API-only restart.
- This restart activates only the target-side safe GET routes. It does not
  authorize stopping, restarting, upgrading, or reconfiguring the separate
  supervision workstation or its running `0.7.0-test` Scheduled Task.

Current task and conversation state:

- Completed: local `0.8.0-test` implementation of eight authenticated safe
  facade projections and one direct external-web probe; environment contract
  2; observation contract 4 / endpoint set 3; audit contract 7; synthetic and
  compatibility tests; documentation; deterministic bundle build.
- Completed verification: 186 targeted tests including repository-root
  hygiene passed, modified modules compiled, `git diff --check` passed, and a
  second bundle build reproduced the exact ZIP digest.
- Pending: restart only the monitored main workstation; prove normal runtime
  recovery and activation of all eight private facade routes; confirm the
  still-running remote 0.7 observer records target recovery. A controlled
  supervision-center migration to 0.8 remains a later, separate gate.
- Roadmap item 1 remains unchecked until the later remote 0.8 configuration
  check, complete nine-observation cycle, matching heartbeat, and audit-v7
  mixed-history proof all pass.
- First action after restart: read `AGENTS.md`,
  `agents/decisions/DECISIONS.md`, and this handoff; run
  `git status --short`; then confirm a Windows boot later than
  `2026-08-06 13:35 +02:00` and a successful postboot
  `API_dashboard_caddy` task run before testing application routes.

Working tree and deployment:

- The working tree is intentionally non-clean. Do not reset, checkout, clean,
  delete, overwrite, commit, push, or create a code-integrity baseline during
  restart handling.
- Monitoring implementation/documentation changes include `AGENTS.md`,
  `agents/decisions/DECISIONS.md`, `agents/history/SESSION_NOTES.md`,
  `agents/work/ACTIVE.md`, the monitoring plans/inventories/runbook,
  `monitoring_agent/`, `services/api/routes/monitoring.py`,
  `services/api/routes/scheduler_health.py`, the new
  `services/api/schemas/monitoring.py`, the new
  `services/api/services/monitoring_facade.py`, the new
  `services/api/services/scheduler_health.py`, the monitoring tests, the new
  repository-hygiene test, and versioned ZIPs under
  `artifacts/monitoring_agent/`.
- Root-hygiene work also leaves the intentional tracked moves/deletions of
  `run.txt`, root `run_monitoring_agent.py`, the duplicate dashboard launcher,
  and the shortcut, with replacements under `agents/runbooks/`,
  `monitoring_agent/bundle_root/`, and `scripts/`. Preserve these changes.
- Other already-present changed files include `.gitignore`,
  `agents/security/DASHBOARD_SECURITY_CHECKLIST.md`,
  `scripts/secret_hygiene_scan.py`, `tests/test_dashboard_security_config.py`,
  and `tests/test_production_runtime.py`. Do not infer that they belong to the
  restart or revert them.
- The user-owned untracked `data/smartfuelpass/vypisy/` directory was not
  inspected or modified and must remain untouched.
- The workspace bundle `monitoring-agent-0.8.0-test.zip` contains 13 declared
  runtime files and 15 entries, no real `.env`, and has SHA-256
  `29BEE64FEE267F1E74BE1AA89CA621E2930262E16C0C662580DA5D2B7EBF8EF0`;
  manifest SHA-256 is
  `282DFDDA162B4D4CB2C3CE656066D47E2B03504F1434277659E20CBCBB173ADF`.
- The separate supervision center remains deployed on `0.7.0-test`; its
  previously verified ZIP SHA-256 is
  `0BA56B60FD8F5A229346D565FEA33F58F57F9239FE541F216C07E79E56D7BF20`.
  Source presence or the local 0.8 ZIP does not prove remote deployment.
- The running main-workstation API still has the four-route 0.7 facade. Before
  restart, unauthenticated liveness, readiness, system-scheduler, and runtime
  routes returned 401, while the new detailed-scheduler, database, proxy, and
  SmartFuelPass routes returned 404. This is the expected pre-activation
  baseline; after restart all eight registered routes must return 401 without
  the monitoring identity.

Sensitive and runtime artifacts:

- Do not print, copy, replace, delete, commit, or expose the root `.env`, the
  protected monitoring-auth environment, dashboard proxy credentials, either
  station's bearer value, or the remote agent's ignored `.env`.
- Do not inspect, copy into Git, truncate, rewrite, or delete the remote
  observation JSONL, lifecycle JSONL, heartbeat, writer-lock file, or external
  state directory. Do not use lock-file modification time or a raw two-Python
  process count as writer identity.
- Do not retain raw authenticated Health responses, URLs, headers, process
  command lines, identifiers, or transient PIDs in the handoff. Record only
  the reviewed aggregate/schema facts.

Read-only pre-restart baseline:

- Captured at approximately `2026-08-06 13:28-13:35 +02:00`. Current Windows
  boot time is `2026-08-05 14:51:02 +02:00`.
- Startup task `API_dashboard_caddy` is `Ready`, last ran at
  `2026-08-05 14:51:12 +02:00`, and returned result 0.
- Exactly one `main.py` scheduler match, one Uvicorn/FastAPI match, one
  Streamlit match, and one Caddy process were found. Tailscale owns the private
  tailnet listeners.
- Expected listeners are present on TCP 80, 443, loopback 2019, loopback 8000,
  loopback 8001, and tailnet-only 9443. Temporary listeners 8010 and 8011 are
  absent.
- Local FastAPI `/health/live` and `/health/ready`, Streamlit
  `/_stcore/health`, and Caddy admin `/config/` each returned HTTP 200.
- Scheduler aggregate status is `ok`; the scheduler is running, its heartbeat
  is present and within TTL, all nine jobs are OK, and the aggregate has zero
  failures in the preceding 24 hours.
- Tracked and deployed Caddyfiles both have SHA-256
  `08CDF04AFC4F856FEC8DFE4AB2E07A746763B152CA91553E349CCCE8E6D3DF2C`.

Expected processes and listeners after restart:

- One FastAPI/Uvicorn runtime on `127.0.0.1:8000`.
- One Streamlit runtime on `127.0.0.1:8001`.
- One scheduler `main.py` runtime holding the scheduler process lock.
- One Caddy runtime owning TCP 80/443 and `127.0.0.1:2019`.
- Tailscale retains the existing tailnet-only 9443 facade listener and its
  existing tailnet 443 surface. Do not change Tailscale Serve configuration.
- TCP 8010/8011 remain absent.

Expected application state:

- FastAPI live/ready, Streamlit health, and Caddy admin return HTTP 200 after
  bounded startup convergence. A transient readiness 503 during startup is
  not itself a failed restart; wait for the established readiness contract.
- Scheduler reports `status=ok`, is running, has a fresh heartbeat within TTL,
  nine expected jobs, no non-OK job, and no new restart-related scheduler
  failure.
- Tracked and deployed Caddyfile hashes remain equal to the pre-restart hash.
- Public HTTP retains its HTTPS redirect. Public HTTPS retains the dashboard's
  existing authentication behavior. Main-workstation public-hostname hairpin
  failure is not sufficient to classify the public site unavailable; external
  reachability must be checked from the supervision center.
- Protected application APIs return HTTP 401 JSON without a bearer token.
- All eight `/api/v1/monitoring/health` facade routes return HTTP 401 without
  the dedicated monitoring identity. With that identity, each returns HTTP
  200 and only its reviewed safe schema. Do not print the identity or raw
  response.
- Existing external alerts remain authoritative. No email, outbox, agentic
  interpretation, remediation, manual job, data write, or alert replacement
  becomes enabled by this restart.

Required post-restart checks:

1. Confirm the boot is later than `2026-08-06 13:35 +02:00` and
   `API_dashboard_caddy` ran after that boot with result 0.
2. Confirm one expected FastAPI, Streamlit, scheduler, and Caddy runtime;
   listeners 80/443/2019/8000/8001 and tailnet-only 9443; and no 8010/8011
   listener. Do not use transient PIDs as durable evidence.
3. Require HTTP 200 from local FastAPI live/ready, Streamlit health, and Caddy
   admin. Stop and diagnose if readiness does not converge within its bounded
   startup allowance.
4. Verify the aggregate scheduler state: running, fresh heartbeat within TTL,
   nine expected jobs, no non-OK job, and no new 24-hour failure attributable
   to restart.
5. Recompute the tracked and deployed Caddyfile hashes and require equality.
   Check HTTP-to-HTTPS routing and public authentication without changing
   Caddy or Tailscale configuration.
6. Call all eight monitoring facade paths without credentials. Require 401 for
   every path; any remaining 404 means the new route set was not activated and
   blocks the 0.8 migration.
7. Using the existing dedicated monitoring identity without displaying it,
   require HTTP 200 and schema validity from liveness, readiness, system
   scheduler, detailed scheduler, system runtime, system database, system
   proxy, and system SmartFuelPass. Retain only aggregate pass/fail facts.
8. On the supervision center, leave `MonitoringAgentTest` running and use only
   the safe concurrent `--audit-state` diagnostic. Require fresh postboot
   four-endpoint cycles and a recovered healthy four-observation heartbeat;
   confirm no new concurrent-start, run-reentry, unclean, or abandoned-run
   evidence. Do not launch foreground continuous mode or `--once` beside the
   Scheduled Task.
9. If any target-side route, schema, listener, scheduler, Caddy, or recovery
   check fails, preserve the running remote 0.7 task and all state, block the
   0.8 migration, and diagnose the monitored runtime first.
10. Append the exact aggregate post-restart result to this file. Only after all
    target-side and 0.7 recovery checks pass may a separate handoff authorize
    stopping/updating the supervision task, migrating its protected
    environment to nine keys, or executing 0.8.

Known risks or accepted gaps:

- The working tree and deployment source are intentionally uncommitted. A
  restart loads this reviewed local source but does not make it committed or
  update the standalone public monitoring repository.
- The current 0.7 observer may record expected bounded target unreachability
  or partial failure during the main-workstation reboot. Require subsequent
  healthy recovery rather than treating the reboot samples as a new agent
  defect.
- New database, proxy, and SmartFuelPass collectors may expose a real degraded
  Health status while still returning a valid safe HTTP 200 schema. Record
  transport/schema success separately from payload health; do not suppress or
  rewrite a genuine degraded result.
- Public reachability from the main workstation remains an invalid substitute
  for the external supervision-station probe.
- No remote 0.8 deployment, incident persistence, reporting, email delivery,
  agentic interpretation, orchestration, remediation, or legacy-alert change
  is authorized by this handoff.

### 2026-08-06 14:18 +02:00 - Monitoring 0.8 target activation verified

- The monitored workstation booted at `13:40:32 +02:00` after the approved
  0.8-facade activation restart. `API_dashboard_caddy` ran at
  `13:40:43 +02:00` with result 0.
- FastAPI live/ready, Streamlit health, and Caddy admin returned HTTP 200.
  Expected listeners 80/443/2019/8000/8001 and tailnet-only 9443 were present;
  8010/8011 were absent. Runtime, database, and proxy safe projections were
  `ok`.
- Scheduler status was `ok`, its heartbeat was fresh within the 300-second
  TTL, all nine scheduled jobs were OK, and the 24-hour aggregate had zero
  failures. The first postboot `quarter_hour_job` succeeded at
  `13:47:13 +02:00`.
- Tracked and deployed Caddyfile hashes remained equal at
  `08CDF04AFC4F856FEC8DFE4AB2E07A746763B152CA91553E349CCCE8E6D3DF2C`.
  Local hostname/SNI returned dashboard HTTP 200 and HTTP redirect 308.
- All eight monitoring facade paths returned JSON HTTP 401 without the
  dedicated identity; the four new routes no longer returned 404. The API log
  contained at least 16 complete ordered four-endpoint remote 0.7 cycles with
  HTTP 200 after boot, proving target/private-path recovery without an observer
  restart.
- SmartFuelPass returned a schema-valid `error` payload because its import has
  been knowingly paused since the 2026-07-29 Cloudflare failure. The user
  confirmed this is not a restart incident. The later replacement will rename
  `Přihlášení SmartFuelPass` to `Import` and ingest an administrator-selected
  Excel file through a parser/database workflow, but all SmartFuelPass changes
  are deferred until the monitoring agent is finished.
- Roadmap item 1 remains open only for the supervision-center pre-migration
  audit, controlled 0.8 bundle/environment migration, one complete
  nine-observation cycle, and audit-v7 mixed-history proof. No remote task,
  agent state, credential, SmartFuelPass code/data, alert, or delivery setting
  was changed during this verification.

### 2026-08-06 - Monitoring 0.8.1 rolling-upgrade correction

- The supervision-center env-v1 configuration check passed with four
  endpoints. Audit v6 contained 1,389 complete cycles: 1,313 healthy, 71
  partial failure, and 5 unreachable. Its latest heartbeat was degraded with
  two failures; transport history included 68 schema errors and the global
  retry flag was false.
- Lifecycle remained valid with nine starts/eight stops/one current open run,
  zero unclean and abandoned runs, and unchanged historical concurrent-start
  and process-run-reentry counts of one.
- Exact inspection of the deployed 0.7 ZIP proved the failure boundary. Its
  `system_runtime` normalizer requires the former full nested response while
  the activated target correctly emits the strict server-side projection
  without transient details, labels, local addresses, next-run time, or PIDs.
- Local `0.8.1-test` now supports the exact env-v1/four-key configuration as
  observation contract 3/set 2 and the exact env-v2/nine-key configuration as
  contract 4/set 3. It rejects hybrids, keeps the safe target response, and
  adds current-run retry evidence to audit v7 without rewriting history.
- The focused monitoring/facade/system-health/scheduler/runtime/hygiene matrix
  passed 192 tests; modified Python modules compiled. The reproducible
  13-file/15-entry ZIP SHA-256 is
  `D17A88A10814D4CC645AD731B5C2B56B3B662E0662547ED9FCEA3443EF876884`;
  manifest SHA-256 is
  `18A3E477E724EEA61F3EFDCBE303BEBE4DC298A4D646D37FE643D6CD9C49CBB1`.
  Declared file hashes and the archive allowlist passed; no real `.env` is
  present.
- The remote 0.7 task and state remain unchanged and running. Do not deploy
  0.8.0. Transfer and SHA-256 verification of 0.8.1 may proceed while it runs.
  The stop mechanism is a separate lifecycle gate: `Stop-ScheduledTask` may
  terminate the process without the controlled lifecycle stop event, so it is
  not yet authorized as a clean stop. After a lifecycle-safe stop method or an
  explicitly qualified planned termination is approved, first prove a healthy
  unchanged-env-v1 bridge and audit-v7 current run, then migrate to env v2/nine
  keys and prove the final cycle/audit before restoring continuous Scheduled
  Task operation.

### 2026-08-07 - Monitoring 0.8.1 hash report and station correction

- A reported copy of `monitoring-agent-0.8.1-test.zip` matched the reviewed
  SHA-256 exactly:
  `D17A88A10814D4CC645AD731B5C2B56B3B662E0662547ED9FCEA3443EF876884`.
- A subsequent exact task lookup and broad Monitor/Agent task listing in the
  same console found no `MonitoringAgentTest`. The hash therefore does not
  prove transfer to the actual supervision center; the earlier provisional
  transfer conclusion is withdrawn.
- Repeat the hash and task-identity checks together on the station that
  produced audit v6. Before any stop, replacement, or restart, read that task's
  effective stop settings and separately approve a lifecycle-safe stop method
  or an explicitly qualified planned termination.
- The user then confirmed that this is the supervision station, that seamless
  observation continuity is not required during the test phase, and that the
  0.7 process may be terminated and `.env` transferred manually. The exact
  process tree must still be identified first; preserve state, do not display
  `.env`, and treat any new abandoned/unclean 0.7 run as explicitly planned
  migration evidence.
- The transferred 0.8.1 ZIP was located on that station and its reviewed hash
  was revalidated. The only two Python processes formed the known Session-0
  launcher/interpreter tree. An elevated fail-closed stop validated the old
  env file, ZIP, process identities, and parent/child relationship first.
  Afterward both targets and all Python processes were absent; env v1 remained
  present. This is the explicitly approved planned test migration stop. No
  Scheduled Task was created and no append-only state was altered.

### 2026-08-07 08:17 +02:00 - Monitoring 0.8.1 scheduler-detail timezone pre-restart handoff

Reason for restart:

- Activate a narrow target-side FastAPI fix required by remote
  `0.8.1-test`: `/api/v1/monitoring/health/scheduler` returned HTTP 200 but
  the remote client rejected it because `checked_at` was serialized without a
  timezone. The fix changes `collect_scheduler_health()` to use a
  timezone-aware `checked_at`. Under the current operating contract, the
  monitored workstation's FastAPI process is refreshed through the full
  Windows startup sequence, not an API-only restart.

Current task and conversation state:

- Completed: the supervision station intentionally started a new clean
  `monitoring-agent-state-ops002` state baseline for `0.8.1-test`.
  Env-v1 `--check-config`, `--once`, and `--audit-state` passed with one
  healthy four-endpoint bridge cycle and clean lifecycle.
- Completed: env-v2 `--check-config` passed. The nine-endpoint `--once`
  produced eight successes and one `schema_error` on `scheduler_detail`; a
  bounded diagnostic proved the schema error is
  `detailed scheduler payload.checked_at must include a timezone`.
  `external_web` succeeded and `system_smartfuelpass` remained a schema-valid
  known paused-import `error` payload.
- Completed locally: `services/api/services/scheduler_health.py` now writes
  timezone-aware `checked_at`; the targeted local matrix
  `tests/test_scheduler_metrics.py`, `tests/test_monitoring_facade.py`, and
  `tests/test_monitoring_agent.py` passed with 102 tests, and the modified
  service compiled.
- Pending: restart only the monitored main workstation to activate the
  target-side FastAPI fix. After it recovers, rerun the remote env-v2
  `--once` and `--audit-state` against the same clean state directory. Do not
  start continuous mode or register/return a Scheduled Task until the
  nine-endpoint proof is healthy.
- First action after restart: read `AGENTS.md`,
  `agents/decisions/DECISIONS.md`, and this handoff; run
  `git status --short`; then confirm a Windows boot later than
  `2026-08-07 08:17 +02:00` and a successful postboot
  `API_dashboard_caddy` task run before testing application routes.

Working tree and deployment:

- The working tree is intentionally non-clean from the monitoring-agent work.
  Do not reset, checkout, clean, delete, overwrite, commit, push, or create a
  code-integrity baseline during restart handling.
- Relevant new change for this restart:
  `services/api/services/scheduler_health.py` changed
  `checked_at=datetime.now()` to `checked_at=datetime.now().astimezone()`;
  `tests/test_scheduler_metrics.py` now asserts the scheduler-health
  `checked_at` has timezone information.
- Existing monitoring implementation, documentation, bundle artifacts, root
  hygiene changes, and unrelated previously changed files remain present and
  must not be reverted during this restart.
- No remote `.env`, bearer value, agent state file, credential, production
  database data, SmartFuelPass data, alert setting, or Scheduled Task was
  changed by the local code fix.

Sensitive and runtime artifacts:

- Do not print, copy, replace, delete, commit, or expose `.env`, the
  monitoring bearer, credential hashes, dashboard proxy credentials, raw
  authenticated Health responses, raw agent JSONL state, heartbeat/lifecycle
  identifiers, URLs from the private facade, process command lines, database
  rows, or SmartFuelPass/session data.
- The supervision station's clean state directory is now the intended
  `0.8.1` baseline and must not be deleted or rewritten. The earlier
  mistyped/pre-0.6 state remains historical/local evidence only.

Expected processes after restart:

- FastAPI/Uvicorn: one runtime on `127.0.0.1:8000`.
- Streamlit: one runtime on `127.0.0.1:8001`.
- Scheduler: one `main.py` runtime holding the scheduler process lock.
- Caddy: one runtime owning TCP 80/443 and `127.0.0.1:2019`.
- Tailscale retains the existing tailnet-only monitoring facade listener.
  Do not change Tailscale Serve configuration.

Expected application state:

- FastAPI live/ready: HTTP 200.
- Streamlit health: HTTP 200.
- Caddy admin: HTTP 200.
- Scheduler status: running, fresh heartbeat within TTL, expected jobs, and
  no new restart-related failures.
- Monitoring facade: all eight private facade paths return HTTP 401 without
  the dedicated monitoring identity. With that identity, the detailed
  scheduler route must return HTTP 200 with timezone-aware `checked_at` and
  validate under the 0.8.1 client.
- Public HTTP keeps HTTPS redirect behavior; public HTTPS dashboard keeps the
  existing authentication behavior. The monitored workstation's known
  public-hostname hairpin gap remains non-authoritative.

Required post-restart checks:

1. Confirm the boot is later than `2026-08-07 08:17 +02:00` and
   `API_dashboard_caddy` ran after that boot with result 0.
2. Confirm one expected FastAPI, Streamlit, scheduler, and Caddy runtime;
   listeners 80/443/2019/8000/8001 and the tailnet-only facade listener; and
   no temporary 8010/8011 listener.
3. Require HTTP 200 from local FastAPI live/ready, Streamlit health, and Caddy
   admin.
4. Verify scheduler aggregate health and a fresh heartbeat.
5. Verify the detailed monitoring scheduler facade no longer serializes naive
   `checked_at` and is accepted by the remote 0.8.1 client.
6. On the supervision station, keep using the same `.env` and
   `monitoring-agent-state-ops002`; run only env-v2 `--once` and
   `--audit-state`. Require nine successes, latest heartbeat healthy, clean
   lifecycle, endpoint order valid, and current-run retry/attempt facts valid.
7. Only after the nine-endpoint proof passes may a separate step restore
   continuous Scheduled Task operation. External delivery, incident/report
   layers, and legacy-alert replacement remain disabled.

Known risks or accepted gaps:

- This restart activates only the scheduler-detail timezone fix. It does not
  authorize remote task registration, email delivery, incident persistence,
  SmartFuelPass changes, manual scheduler jobs, database writes, or alert
  replacement.
- `system_smartfuelpass` may continue to report payload status `error` because
  the import is knowingly paused; this is not a transport/schema failure and
  must be qualified later by deterministic incident rules.

### 2026-08-07 - Monitoring 0.8.1 nine-endpoint proof and task-restore pause

- Post-restart local verification after the scheduler-detail timezone fix
  passed. The monitored workstation booted at `2026-08-07 08:20:55 +02:00`;
  `API_dashboard_caddy` ran at `08:21:05 +02:00` with result 0. FastAPI
  live/ready, Streamlit health, and Caddy admin returned HTTP 200. Expected
  listeners 80/443/2019/8000/8001 and tailnet-only 9443 were present, 8010
  and 8011 were absent, tracked and deployed Caddyfile hashes matched, local
  SNI HTTPS returned 200, and HTTP redirected to HTTPS with 308.
- All eight unauthenticated monitoring facade routes returned HTTP 401 on
  their correct `/api/v1/monitoring/health/system/...` paths. Earlier 404
  results were caused by using incorrect dashed paths, not by missing routes.
- The first postboot scheduler cycle succeeded at `08:35 +02:00`, including
  `check_database_availability`, `kalorimetry_db_import`,
  `score_new_kalorimetry_measurements`, `detect_kalorimetry_events_from_scores`,
  and `quarter_hour_job`. Scheduler heartbeat was fresh at
  `08:41:10 +02:00`; there were zero failure keys.
- On the supervision station, remote `0.8.1-test` env-v2 `--once` completed
  one nine-observation cycle with transport status `success`. Audit v7 then
  showed endpoint set 3, 27 contract-4 observations, three complete cycles,
  latest heartbeat `healthy`, nine latest observations, zero latest transport
  failures, valid endpoint/cycle order, valid retry contract, valid attempt
  bounds, clean lifecycle with three starts and three stops, and no
  concurrent-start, run-reentry, unclean, abandoned, incomplete, or writer
  evidence in the new clean state. The two earlier schema errors remain
  retained pre-fix env-v2 history; recovery is now proved.
- The standalone GitHub repository for the agent is
  `https://github.com/mtravnicekarmex/monitoring-agent-0.8.1.git`.
  PyCharm MCP was tested twice, but the available MCP backend remained bound
  to the main `monitorovaci_platforma` project and did not expose the remote
  `monitoring-agent-0.8.1-test` project or the user's test chat messages.
  Continue agent work through Git/repository evidence and explicit remote
  command output rather than MCP.
- The next approved step was to restore continuous operation through the
  reviewed `MonitoringAgentTest` Scheduled Task in
  `C:\Users\tra\PycharmProjects\monitoring-agent-0.8.1-test`.
  `.\register_monitoring_agent_task.ps1 -WhatIf` passed and reported the
  intended registration/update action. Running the registration from a
  non-elevated PowerShell failed with `Přístup byl odepřen` /
  `HRESULT 0x80070005`; no fallback user task was created.
- The supervision station entered maintenance and is unavailable until
  2026-08-08. Resume from this exact point: open elevated PowerShell on the
  supervision station, run
  `Set-Location C:\Users\tra\PycharmProjects\monitoring-agent-0.8.1-test`,
  then `.\register_monitoring_agent_task.ps1 -Confirm:$false`,
  `Start-ScheduledTask -TaskName MonitoringAgentTest`, wait 90-120 seconds,
  and run only read-only verification:
  `Get-ScheduledTask -TaskName MonitoringAgentTest | Select-Object TaskName,State,TaskPath`,
  `Get-ScheduledTask -TaskName MonitoringAgentTest | Get-ScheduledTaskInfo | Select-Object LastRunTime,LastTaskResult,NextRunTime`,
  and `py -3.14 run_monitoring_agent.py --audit-state`.
- Expected resume result: task `Running`, running task result such as
  `267009` / `0x41301`, audit v7 latest heartbeat healthy with nine
  observations, current continuous lifecycle unclosed, and no new
  concurrent-start, process-run-reentry, unclean, or abandoned evidence.
  Do not run foreground continuous mode or `--once` once the task is running;
  `--check-config` and `--audit-state` remain safe concurrent commands.

### 2026-08-07 14:11 +02:00 - Plynomery billing append-only pre-restart handoff

Reason for restart:

- Activate source changes for the admin-only `Plynomery / Fakturacni odecty`
  page after discovering that live entry overwrote rows instead of creating
  new records. The running Streamlit process may hold old imports and the
  database still has the old unique constraint; activation requires loading
  the new code and running the coordinated constraint drop under that code.

Current task and conversation state:

- Completed: repaired `.venv-production` after post-restart contamination; the
  dashboard stack and scheduler recovered.
- Completed in source: admin page for monthly plynomery billing readings;
  branch configuration; append-only billing table/model/service/report;
  report/submeter comparison uses branch-specific
  `previous_reading.reading_at` to `current_reading.reading_at` cutoffs;
  validation blocks missing readings, non-forward reading time, decreased
  cumulative state, and non-finite values; the latest saved row per
  meter/period is the effective current row.
- Pending: restart the workstation to load code and let the new
  `ensure_billing_readings_table()` remove
  `uq_plynomery_fakturacni_odecty_period`; then verify append-only behavior
  without overwriting existing rows.
- First action after restart: read `AGENTS.md`,
  `agents/decisions/DECISIONS.md`, this handoff, run `git status --short`,
  confirm boot after `2026-08-07 14:11 +02:00`, and confirm
  `API_dashboard_caddy` result 0 after boot.

Working tree and deployment:

- `git status --short` before this handoff:
  - `M moduly/apps/dashboard/navigation_config.py`
  - `M moduly/mereni/plynomery/database/models.py`
  - `M moduly/mereni/plynomery/database/plynomery_db_vse.py`
  - `M tests/test_dashboard_navigation_config.py`
  - `M tests/test_plynomery_model_rebuild_report.py`
  - `?? moduly/apps/dashboard/pages/34_plynomery_fakturacni_odecty.py`
  - `?? moduly/mereni/plynomery/branches.py`
  - `?? moduly/mereni/plynomery/reporting/monthly_billing_report.py`
  - `?? services/api/services/plynomery_billing.py`
  - `?? tests/test_plynomery_billing.py`
- Additional handoff files changed immediately before restart:
  `agents/decisions/DECISIONS.md`, `agents/work/ACTIVE.md`, and
  `agents/history/SESSION_NOTES.md`.
- Source changes are uncommitted and intentional. Do not reset, checkout,
  clean, or commit unless the user asks.
- Pre-restart runtime was healthy at `2026-08-07 14:11 +02:00`: Windows boot
  `2026-08-07 12:59:43 +02:00`; startup task `API_dashboard_caddy` last run
  `2026-08-07 13:08:42`, result 0; API live/ready 200; Streamlit 200; Caddy
  admin 200; protected `/api/v1/auth/me` without bearer 401; scheduler running
  with heartbeat `2026-08-07T14:08:44.956054`, quarter-hour job
  `2026-08-07T14:05:14.503530`, and zero failure keys.
- Tracked and deployed Caddyfile hashes both matched:
  `08CDF04AFC4F856FEC8DFE4AB2E07A746763B152CA91553E349CCCE8E6D3DF2C`.
- Production virtual-environment lock verification passed after repair.

Sensitive/runtime artifacts:

- Do not print, change, delete, or commit `.env`, database credentials, bearer
  tokens, cookies, ProgramData proxy credentials, raw authenticated Health
  responses, raw operational database rows, or SmartFuelPass/session data.
- Do not manually drop DB constraints while old code is still running.

Expected processes/listeners after restart:

- FastAPI/Uvicorn on `127.0.0.1:8000`.
- Streamlit on `127.0.0.1:8001`.
- Scheduler `main.py` holding the scheduler process lock.
- Caddy on TCP 80/443 and admin `127.0.0.1:2019`.
- Tailscale tailnet listeners 443 and 9443 retained; 8010/8011 absent.

Expected application state:

- API live/ready 200.
- Streamlit health 200.
- Caddy admin 200.
- Protected `/api/v1/auth/me` without bearer 401.
- Scheduler running, heartbeat fresh within 300 seconds, post-boot
  `quarter_hour_job` successful, and failure keys 0.
- Tracked/deployed Caddyfile hash remains equal to
  `08CDF04AFC4F856FEC8DFE4AB2E07A746763B152CA91553E349CCCE8E6D3DF2C`.
- Local Caddy/SNI HTTPS 200 and HTTP redirect 308; direct public hostname from
  this host may time out because of the known hairpin gap.
- The `Fakturacni odecty` page loads for an admin. New code removes the old
  unique constraint and subsequent saves append new rows; report creation
  remains blocked until valid current/previous reading pairs exist.

Required post-restart checks:

1. Confirm boot time is after `2026-08-07 14:11 +02:00` and
   `API_dashboard_caddy` ran after boot with result 0.
2. Confirm expected listeners 80/443/2019/8000/8001 plus tailnet 9443, with
   no 8010/8011.
3. Confirm local API live/ready, Streamlit, Caddy admin, and protected auth
   401 without bearer.
4. Confirm scheduler heartbeat is fresh and the first post-boot
   `quarter_hour_job`/database/import/scoring checks are successful with no
   new failure keys.
5. Verify the production virtual-environment lock still matches.
6. Verify tracked/deployed Caddyfile hashes match.
7. Trigger a read-only admin load of `Fakturacni odecty`; confirm the page
   renders fields and does not error.
8. Verify `ensure_billing_readings_table()` removed
   `uq_plynomery_fakturacni_odecty_period` after new code loaded. Use
   aggregate/schema evidence only; do not print raw rows.
9. Perform an explicit user-approved test save only if needed: save a harmless
   test/correction reading and verify row count increases rather than
   overwriting, then identify cleanup/rollback expectations before any test
   write. If not approved, stop after schema/source verification.
10. Re-run focused tests if appropriate from `.venv`, not `.venv-production`.

Known risks/gaps:

- Current changes are uncommitted.
- A manual test database write is not included in restart authorization.
- Browser/API boundary for this new Streamlit admin write remains a later
  hardening item; current source preserves the existing direct service pattern
  during this operational completion.
- Supervision-center monitoring task restoration remains a separate OPS-002
  gate and is not part of this restart.

### 2026-08-07 14:43 +02:00 - Plynomery billing report pre-restart handoff

Reason for restart:

- Activate the follow-up source fix for `Plynomery / Fakturacni odecty`.
  Saving is already append-only, but the running dashboard still shows
  `Report zatim nelze vytvorit` after the database corrections because the
  Streamlit process likely still has the old billing service import loaded.
- The source fix changes report input lookup from insertion/period-end
  ordering to actual `reading_at` semantics. For the July 2026 report,
  readings on `2026-07-01` are treated as the previous/start reading and
  readings on `2026-08-01` as the current/end reading.

Current task and conversation state:

- Completed: direct aggregate validation through the current source and
  production database returned `current_meter_count=7`,
  `previous_meter_count=7`, and `issue_count=0` for `[2026-07-01,
  2026-08-01)`.
- Completed: focused billing tests passed with `12 passed`, and
  `services/api/services/plynomery_billing.py` plus
  `tests/test_plynomery_billing.py` compiled.
- Pending: restart the monitored workstation through the existing whole-stack
  startup procedure so Streamlit loads the fixed billing service module.
- First action after restart: read `AGENTS.md`,
  `agents/decisions/DECISIONS.md`, and this handoff; run
  `git status --short`; confirm boot after `2026-08-07 14:43 +02:00` and
  confirm `API_dashboard_caddy` result 0 after boot.

Working tree and deployment:

- The working tree is intentionally non-clean from the plynomery billing work.
  Do not reset, checkout, clean, delete, overwrite, commit, push, or create a
  code-integrity baseline during restart handling.
- Relevant follow-up source changes:
  `services/api/services/plynomery_billing.py` now selects latest effective
  billing rows by `reading_at`, treats start-day readings as previous
  readings, and filters current lookup to configured billing meters.
  `tests/test_plynomery_billing.py` covers these cases.
- Current `git status --short` before this handoff:
  - `M agents/decisions/DECISIONS.md`
  - `M agents/history/SESSION_NOTES.md`
  - `M agents/work/ACTIVE.md`
  - `M moduly/apps/dashboard/navigation_config.py`
  - `M moduly/mereni/plynomery/database/models.py`
  - `M moduly/mereni/plynomery/database/plynomery_db_vse.py`
  - `M tests/test_dashboard_navigation_config.py`
  - `M tests/test_plynomery_model_rebuild_report.py`
  - `?? moduly/apps/dashboard/pages/34_plynomery_fakturacni_odecty.py`
  - `?? moduly/mereni/plynomery/branches.py`
  - `?? moduly/mereni/plynomery/reporting/monthly_billing_report.py`
  - `?? services/api/services/plynomery_billing.py`
  - `?? tests/test_plynomery_billing.py`
- Pre-restart runtime was healthy at `2026-08-07 14:43 +02:00`: Windows boot
  `2026-08-07 14:15:43 +02:00`; startup task `API_dashboard_caddy` last ran
  `2026-08-07 14:15:53` with result 0; API live/ready 200; Streamlit 200;
  Caddy admin 200; protected `/api/v1/auth/me` without bearer 401; scheduler
  running with heartbeat `2026-08-07T14:40:59.935885`, latest quarter-hour
  success `2026-08-07T14:35:13.650416`, latest database check success
  `2026-08-07T14:35:05.268077`, and zero failure keys.
- Tracked and deployed Caddyfile SHA-256 hashes both matched:
  `08CDF04AFC4F856FEC8DFE4AB2E07A746763B152CA91553E349CCCE8E6D3DF2C`.

Sensitive/runtime artifacts:

- Do not print, change, delete, or commit `.env`, database credentials, bearer
  tokens, cookies, ProgramData proxy credentials, raw authenticated Health
  responses, raw operational database rows, or SmartFuelPass/session data.
- The user corrected the E/F billing rows in the database; do not rewrite
  those values or perform additional test saves during restart verification
  unless explicitly approved.

Expected processes/listeners after restart:

- FastAPI/Uvicorn on `127.0.0.1:8000`.
- Streamlit on `127.0.0.1:8001`.
- Scheduler `main.py` holding the scheduler process lock.
- Caddy on TCP 80/443 and admin `127.0.0.1:2019`.
- Tailscale tailnet listeners 443 and 9443 retained; 8010/8011 absent.

Expected application state:

- API live/ready 200.
- Streamlit health 200.
- Caddy admin 200.
- Protected `/api/v1/auth/me` without bearer 401.
- Scheduler running, heartbeat fresh within 300 seconds, post-boot
  `quarter_hour_job` successful, and failure keys 0.
- Direct aggregate validation of the July 2026 plynomery billing report
  returns `current_meter_count=7`, `previous_meter_count=7`, and
  `issue_count=0`.
- The dashboard `Fakturacni odecty` page no longer shows
  `Report zatim nelze vytvorit` for the corrected July 2026 data and enables
  report creation.

Required post-restart checks:

1. Confirm boot time is after `2026-08-07 14:43 +02:00` and
   `API_dashboard_caddy` ran after boot with result 0.
2. Confirm expected listeners 80/443/2019/8000/8001 plus tailnet 9443, with
   no 8010/8011.
3. Confirm local API live/ready, Streamlit, Caddy admin, and protected auth
   401 without bearer.
4. Confirm scheduler heartbeat is fresh and the first post-boot
   `quarter_hour_job`/database/import/scoring checks are successful with no
   new failure keys.
5. Verify production virtual-environment lock still matches.
6. Verify tracked/deployed Caddyfile hashes match.
7. Re-run the aggregate July 2026 plynomery billing validation and require
   `issue_count=0`.
8. Load the admin `Fakturacni odecty` page and verify that report creation is
   available for the corrected July 2026 data. Do not perform a test database
   save during this check.

Known risks/gaps:

- Meter replacement/reset support for billing readings remains explicitly
  postponed; the current contract still rejects genuinely decreased
  cumulative states.
- Supervision-center monitoring task restoration remains a separate OPS-002
  gate and is not part of this restart.

### 2026-08-07 15:20 +02:00 - Plynomery billing PDF style pre-restart handoff

Reason for restart:

- Activate the follow-up PDF/HTML styling change for
  `Plynomery / Fakturacni odecty`. The report now creates successfully and the
  user confirmed the calculations are correct, but the running Streamlit
  process may still hold the previous report renderer import.
- The source renderer was changed to match the vodomery PDF report style:
  compact A4 layout, blue `#0f4c81` header line, centered ARMEX logo,
  right-side metadata, primary metric cards, and `branch-table` tables with
  blue headers.

Current task and conversation state:

- Completed: append-only billing-readings behavior, July 2026 current/previous
  reading lookup, report input validation, PDF generation, and calculation
  correctness were verified.
- Completed after the previous restart: table
  `monitoring.plynomery_fakturacni_odecty` existed, old unique constraint
  `uq_plynomery_fakturacni_odecty_period` was absent, July 2026 aggregate
  validation returned seven current readings, seven previous readings, and
  zero input issues.
- Completed in source: report presentation now reuses the vodomery visual
  structure and tests assert the key style classes.
- Pending: restart the monitored workstation through the existing whole-stack
  startup procedure so Streamlit loads the fixed report renderer.
- First action after restart: read `AGENTS.md`,
  `agents/decisions/DECISIONS.md`, and this handoff; run
  `git status --short`; confirm boot after `2026-08-07 15:20 +02:00` and
  confirm `API_dashboard_caddy` result 0 after boot.

Working tree and deployment:

- The working tree remains intentionally non-clean from the plynomery billing
  work. Do not reset, checkout, clean, delete, overwrite, commit, push, or
  create a code-integrity baseline during restart handling.
- Current `git status --short` before this handoff:
  - `M agents/decisions/DECISIONS.md`
  - `M agents/history/SESSION_NOTES.md`
  - `M agents/work/ACTIVE.md`
  - `M moduly/apps/dashboard/navigation_config.py`
  - `M moduly/mereni/plynomery/database/models.py`
  - `M moduly/mereni/plynomery/database/plynomery_db_vse.py`
  - `M tests/test_dashboard_navigation_config.py`
  - `M tests/test_plynomery_model_rebuild_report.py`
  - `?? moduly/apps/dashboard/pages/34_plynomery_fakturacni_odecty.py`
  - `?? moduly/mereni/plynomery/branches.py`
  - `?? moduly/mereni/plynomery/reporting/monthly_billing_report.py`
  - `?? services/api/services/plynomery_billing.py`
  - `?? tests/test_plynomery_billing.py`
- Relevant latest source changes:
  `moduly/mereni/plynomery/reporting/monthly_billing_report.py` was restyled;
  `tests/test_plynomery_billing.py` now asserts the report contains
  `page-header`, `page-logo`, `metric-card-primary`, `branch-table`, and the
  vodomery blue `#0f4c81`.
- Verification before restart: focused billing tests passed with `12 passed`;
  `monthly_billing_report.py` and `tests/test_plynomery_billing.py` compiled;
  a synthetic report HTML build produced the expected style classes.
- No production database row, billing reading, credential, Caddy runtime file,
  scheduler job, SmartFuelPass state, monitoring-agent state, or alert setting
  was changed by the styling fix.

Sensitive/runtime artifacts:

- Do not print, change, delete, or commit `.env`, database credentials, bearer
  tokens, cookies, ProgramData proxy credentials, raw authenticated Health
  responses, raw operational database rows, SmartFuelPass/session data, or
  monitoring-agent credentials/state.
- Do not perform a test database save during post-restart verification unless
  explicitly approved in a new instruction. It is not needed for this restart.

Expected processes/listeners after restart:

- FastAPI/Uvicorn on `127.0.0.1:8000`.
- Streamlit on `127.0.0.1:8001`.
- Scheduler `main.py` holding the scheduler process lock.
- Caddy on TCP 80/443 and admin `127.0.0.1:2019`.
- Tailscale tailnet listeners 443 and 9443 retained; 8010/8011 absent.

Expected application state:

- API live/ready 200.
- Streamlit health 200.
- Caddy admin 200.
- Protected `/api/v1/auth/me` without bearer 401.
- Scheduler running, heartbeat fresh within 300 seconds, post-boot
  `quarter_hour_job` successful, and failure keys 0.
- Production virtual-environment lock still matches
  `requirements-production.lock.txt`.
- Tracked/deployed Caddyfile hashes remain equal to
  `08CDF04AFC4F856FEC8DFE4AB2E07A746763B152CA91553E349CCCE8E6D3DF2C`.
- Direct aggregate validation of the July 2026 plynomery billing report
  returns `current_meter_count=7`, `previous_meter_count=7`, and
  `issue_count=0`.
- The dashboard `Fakturacni odecty` page can create/download the July 2026 PDF
  report and the PDF uses the vodomery-style visual treatment.

Pre-restart runtime status at `2026-08-07 15:20 +02:00`:

- Windows boot: `2026-08-07 14:45:47 +02:00`.
- Startup task `API_dashboard_caddy`: last run `2026-08-07 14:45:57 +02:00`,
  result 0.
- API live 200, API ready 200, Streamlit health 200, Caddy admin 200, and
  protected `/api/v1/auth/me` without bearer 401.
- Listeners 80/443/2019/8000/8001 were present; tailnet listeners 443 and
  9443 were present; temporary 8010/8011 were absent.
- Scheduler heartbeat `2026-08-07T15:16:05.060920`, `scheduler_running=True`,
  and failure key count 0.
- Latest relevant scheduler successes:
  `check_database_availability=2026-08-07T15:16:05.082137`,
  `kalorimetry_db_import=2026-08-07T15:16:13.450217`,
  `score_new_kalorimetry_measurements=2026-08-07T15:16:13.586755`,
  `detect_kalorimetry_events_from_scores=2026-08-07T15:16:13.613301`,
  and `quarter_hour_job=2026-08-07T15:16:13.653971`.
- Production virtual-environment verification returned
  `Production Python environment matches requirements-production.lock.txt.`
- Local Caddy/SNI HTTPS returned 200. Local HTTP returned 308 redirecting to
  `https://monitoring.armexholding.cz/`.

Required post-restart checks:

1. Confirm boot time is after `2026-08-07 15:20 +02:00` and
   `API_dashboard_caddy` ran after boot with result 0.
2. Confirm expected listeners 80/443/2019/8000/8001 plus tailnet 9443, with
   no 8010/8011.
3. Confirm local API live/ready, Streamlit health, Caddy admin, and protected
   auth 401 without bearer.
4. Confirm scheduler heartbeat is fresh and the first post-boot
   `quarter_hour_job`/database/import/scoring checks are successful with no
   new failure keys.
5. Verify production virtual-environment lock still matches.
6. Verify tracked/deployed Caddyfile hashes match.
7. Re-run aggregate July 2026 plynomery billing validation and require
   `current_meter_count=7`, `previous_meter_count=7`, and `issue_count=0`.
8. Load the admin `Fakturacni odecty` page, create/download the July 2026 PDF
   report, and verify the vodomery-style graphics are live. Do not perform a
   test database save.

Known risks/gaps:

- This restart is only for loading the report renderer styling into the live
  Streamlit process. It does not authorize database corrections, meter-reset
  billing support, alert/report delivery changes, Caddy changes, monitoring
  task restoration, or unrelated production writes.
- Supervision-center monitoring task restoration remains a separate OPS-002
  gate and is not part of this restart.

### 2026-08-10 07:37 +02:00 - Plynomery billing PDF style post-restart verification

- Windows booted at `2026-08-10 07:03:46 +02:00`, after the
  `2026-08-07 15:20 +02:00` pre-restart handoff. Startup task
  `API_dashboard_caddy` ran at `2026-08-10 07:03:56 +02:00` with result 0.
- Expected listeners 80, 443, 2019, 8000, 8001, and tailnet 9443 were
  present; temporary listeners 8010/8011 were absent. Sanitized port ownership
  showed Caddy on 80/2019, Caddy plus Tailscale on 443, Python on 8000/8001,
  and Tailscale on 9443.
- Local API live/ready, Streamlit health, and Caddy admin returned HTTP 200.
  Protected `/api/v1/auth/me` without a bearer token returned HTTP 401.
- Scheduler was running with fresh heartbeat `2026-08-10T07:29:02.429543`.
  The post-boot `quarter_hour_job`, database availability check, kalorimetry
  import, kalorimetry scoring, and kalorimetry event detection were successful
  at approximately 07:16 with zero 24-hour failure counts.
- Production virtual-environment verification returned
  `Production Python environment matches requirements-production.lock.txt.`
- Tracked and deployed Caddyfile SHA-256 hashes matched:
  `08CDF04AFC4F856FEC8DFE4AB2E07A746763B152CA91553E349CCCE8E6D3DF2C`.
  Local Caddy/SNI HTTPS returned 200 HTML, and local HTTP returned 308 to
  `https://monitoring.armexholding.cz/`.
- Read-only July 2026 plynomery billing validation returned
  `current_meter_count=7`, `previous_meter_count=7`, `branch_count=7`, and
  `issue_count=0`. The in-memory report HTML contained the reviewed style
  markers, and the in-memory PDF render produced valid PDF bytes.
- Focused billing regression passed: `13 passed` for
  `tests/test_plynomery_billing.py`.
- Authenticated browser loading/clicking of the Streamlit admin page was not
  performed from the agent environment because no admin browser session or
  credential was available. No test save, database write, runtime config
  change, secret readout, monitoring-agent state change, or unrelated
  production mutation was performed.

### 2026-08-10 - Plynomery billing PDF accepted as complete

- User confirmed the `Plynomery / Fakturacni odecty` PDF work is complete and
  satisfactory.
- Report creation remains a manual admin-dashboard action. No scheduler
  integration, scheduler manual-run entry, automatic email delivery, or report
  recipient configuration is needed.
- The report remains actual/billing-only, using manual billing readings and
  interval-bound submeter snapshots rather than prediction-profile data.
- `PLY-001` was moved from active work to completed work in the documentation.
  This documentation update changed no application code, production database
  row, runtime configuration, scheduler state, credential, or monitoring-agent
  state.

### 2026-08-10 - SmartFuelPass Excel import implemented

- The active SmartFuelPass dashboard workflow was changed from the paused
  Cloudflare/browser login page to `Nabijecky / Import`.
- Added an Excel parser for `ChargingSessions` `.xlsx` exports. It maps the
  workbook to the existing `monitoring.smartfuelpass_relace` shape, imports
  only `Stav = Dokončeno`, uses `Suma`, normalizes location to the existing
  short DB format, preserves existing interval time semantics, and sets
  `battery_status=NULL`.
- Added admin-only FastAPI preview/import endpoints. Preview is read-only and
  marks rows as new, existing, existing with differences, or ignored. Import is
  insert-only by `id_relace`; existing rows are never updated from Excel.
- The supplied sample was checked through the new preview path without writing
  to the database: 16 parsed rows, 4 completed rows, 2 new importable rows, 2
  existing rows with differences, and 12 ignored rows.
- Focused verification passed:
  `tests/test_smartfuelpass_excel_import.py`,
  `tests/test_smartfuelpass_interactive.py`,
  `tests/test_dashboard_navigation_config.py`, and
  `tests/test_api_authorization_regression.py` returned `263 passed`.
- `git diff --check` passed with only line-ending normalization warnings.
  Documentation was updated in AGENTS, decisions, backlog, completed work, and
  session notes. No production import/write was executed.

### 2026-08-10 - SmartFuelPass Excel import accepted as complete

- User confirmed the `Nabijecky / Import` page works as intended in operation.
- `SFP-001` remains completed; no further import-page work is tracked in the
  active or backlog work indexes.
- This update records operator acceptance only. The agent did not inspect raw
  imported data, read credentials/session artifacts, or execute a production
  import/write.

### 2026-08-10 - Plynomery billing PDF kalorimetry allocation added

- The manual `Plynomery / Fakturacni odecty` PDF now includes actual
  kalorimetry-based allocation detail for selected gas meters while remaining
  manual, actual/billing-only, and outside scheduler/report delivery.
- Static allocation mapping was added for `INNOGY_A` through `Amt1`-`Amt3`,
  `G_P1` through `Gmt1`-`Gmt5`, and `G_P3` through `Gmt6`-`Gmt8`. `Bmt1`-`Bmt3`
  were intentionally excluded because metadata identifies their source as the
  B-building electric boiler, not a gas meter.
- Allocation uses actual cumulative `spotreba_energie` snapshots from
  `monitoring.Mereni_kalorimetry_vse` at the same previous/current
  billing-reading timestamps as the gas comparison. It does not use
  kalorimetry predictions or selected-model/profile snapshots.
- Focused billing regression passed with `16 passed`; targeted modules
  compiled. A read-only July 2026 smoke check found seven branches, three
  allocation groups, 11 configured kalorimeters, no missing configured
  kalorimeters, complete `G_P1`/`G_P3` allocations, and a visible
  zero-energy-total state for `INNOGY_A`. The same read-only report rendered
  valid PDF bytes.
- No database write, scheduler change, runtime configuration change, report
  delivery, credential/session readout, or raw measurement dump was performed.

### 2026-08-11 11:57 +02:00 - Vodomery sustained high usage pre-restart handoff

Reason for restart:

- Load the new vodomery `SUSTAINED_HIGH_USAGE` event and alerting/UI allowlist
  changes into the production scheduler, FastAPI, and Streamlit processes.
- The supported production recovery model remains a whole Windows workstation
  restart through the existing `API_dashboard_caddy` startup task; do not stop
  or recreate individual production processes for this activation.

Current task and conversation state:

- Completed: diagnosed the missed 2026-08-10 `E_V1` alert as an alerting
  semantics gap. The old pipeline scored the data and created short resolved
  `SPIKE` events, but it did not have a direct prediction-relative sustained
  high-usage event.
- Completed in source: added `SUSTAINED_HIGH_USAGE`, defined as four
  consecutive 15-minute scores where actual consumption is at least 2.0 times
  the active prediction, absolute deviation is at least `0.05 m3`, and actual
  consumption is at least `0.08 m3`. Event duration starts at the first
  qualifying score.
- Completed in source: normal vodomery event detection and outlier-review
  event rebuild share the same trigger helper; vodomery alert-rule duration is
  inclusive; DB check constraints, API validation allowlists, and Streamlit
  labels/filters include the new event type.
- Pending: restart the workstation, verify the runtime stack, wait for one
  post-boot vodomery quarter-hour pipeline cycle, then configure the first
  production alert rule only after explicit operator confirmation of
  recipient, severity, and scope.
- First action after restart: read `AGENTS.md`,
  `agents/decisions/DECISIONS.md`, and this handoff; run
  `git status --short`; confirm boot after `2026-08-11 11:57 +02:00` and
  confirm `API_dashboard_caddy` result 0 after boot.

Working tree and deployment:

- The working tree is intentionally non-clean from the vodomery alerting work.
  Do not reset, checkout, clean, delete, overwrite, commit, push, or create a
  code-integrity baseline during restart handling.
- `git status --short` before writing this handoff showed:
  - `M AGENTS.md`
  - `M agents/decisions/DECISIONS.md`
  - `M agents/work/ACTIVE.md`
  - `M moduly/apps/dashboard/alerting_shared.py`
  - `M moduly/apps/dashboard/overview_shared.py`
  - `M moduly/apps/dashboard/pages/4_vodomery_anomalie_eventy.py`
  - `M moduly/apps/dashboard/pages/7_vodomery_alerting.py`
  - `M moduly/mereni/vodomery/alerting/service.py`
  - `M moduly/mereni/vodomery/database/alerting.py`
  - `M moduly/mereni/vodomery/database/models.py`
  - `M moduly/mereni/vodomery/database/outlier_review_apply.py`
  - `M moduly/mereni/vodomery/vodomery_events.py`
  - `M tests/test_dashboard_alerting_shared.py`
  - `M tests/test_vodomery_alert_rule_validation.py`
  - `?? tests/test_vodomery_alert_service.py`
  - `?? tests/test_vodomery_events.py`
- This handoff additionally modifies `agents/history/SESSION_NOTES.md`.
- Relevant source behavior:
  `moduly/mereni/vodomery/vodomery_events.py` owns the new event constants,
  trigger config, event-table ensure path, DB event check-constraint update,
  duration handling, and opening aggregate calculations.
  `moduly/mereni/vodomery/database/outlier_review_apply.py` uses the same
  trigger/duration helpers during event rebuilds. `moduly/mereni/vodomery/alerting/service.py`
  changed alert duration matching from strictly greater-than to inclusive.
  Dashboard pages and shared modules now expose `SUSTAINED_HIGH_USAGE`.
- Verification before restart: production compile passed for the touched
  vodomery/dashboard modules. Focused pytest in `.venv` passed with
  `13 passed`:
  `tests/test_vodomery_events.py`,
  `tests/test_vodomery_alert_service.py`,
  `tests/test_vodomery_alert_rule_validation.py`,
  `tests/test_dashboard_alerting_shared.py`, and
  `tests/test_dashboard_overview_shared.py`.
- No production alert rule was created, no historical events were backfilled,
  no email delivery was triggered, and no production database data row was
  intentionally changed by the implementation session.
- Runtime schema note: after the new code is loaded, the event engine and
  alert-rule write path may update PostgreSQL check constraints to allow
  `SUSTAINED_HIGH_USAGE`. This is the intended additive compatibility update;
  it is not a manual data backfill.

Sensitive and runtime artifacts:

- Do not print, change, delete, or commit `.env`, database credentials, bearer
  tokens, cookies, ProgramData proxy credentials, raw authenticated Health
  responses, raw meter data, scheduler locks, SmartFuelPass/session data,
  monitoring-agent credentials/state, or operational database row dumps.
- Do not create a test alert recipient, send a test email, run a historical
  event backfill, or execute unrelated manual scheduler/database operations
  during post-restart verification unless explicitly approved.

Expected processes/listeners after restart:

- FastAPI/Uvicorn on `127.0.0.1:8000`.
- Streamlit on `127.0.0.1:8001`.
- Scheduler `main.py` holding the scheduler process lock.
- Caddy on TCP 80/443 and admin `127.0.0.1:2019`.
- Tailscale tailnet listeners 443 and 9443 retained; temporary 8010/8011
  absent.

Expected application state:

- API live/ready: HTTP 200.
- Streamlit health: HTTP 200.
- Caddy admin `/config/`: HTTP 200.
- Protected `/api/v1/auth/me` without bearer token: HTTP 401.
- Scheduler running with a heartbeat newer than boot.
- First post-boot vodomery quarter-hour cycle should complete
  `check_database_availability`, `vodomery_db_import`,
  `score_new_measurements`, `detect_events_from_scores`, and
  `process_vodomery_alerts` successfully.
- Production virtual environment still matches `requirements-production.lock.txt`.
- Tracked and deployed Caddyfile SHA-256 hashes remain equal to
  `08CDF04AFC4F856FEC8DFE4AB2E07A746763B152CA91553E349CCCE8E6D3DF2C`.
- Dashboard/API alert-rule validation recognizes `SUSTAINED_HIGH_USAGE`.
- No `SUSTAINED_HIGH_USAGE` alert email is expected until an enabled
  production alert rule exists and a qualifying event is active.

Pre-restart runtime status at `2026-08-11 11:56 +02:00`:

- Windows boot: `2026-08-11 11:07:04 +02:00`.
- Startup task `API_dashboard_caddy`: `Ready`, last run
  `2026-08-11 11:07:14 +02:00`, result 0.
- Listeners were present on 80/443/2019/8000/8001 and tailnet 443/9443.
  Sanitized process names: Caddy owned 80/443/2019, Python owned 8000/8001,
  and Tailscale owned tailnet 443/9443. Temporary 8010/8011 were absent.
- API live 200, API ready 200, Streamlit health 200, Caddy admin 200, and
  protected `/api/v1/auth/me` without bearer 401.
- Scheduler was running with heartbeat `2026-08-11T11:52:20.871395`.
  Latest relevant successes: `check_database_availability`
  `2026-08-11T11:47:07.835505`, `vodomery_db_import`
  `2026-08-11T11:47:09.282869`, `score_new_measurements`
  `2026-08-11T11:47:14.774861`, `detect_events_from_scores`
  `2026-08-11T11:47:14.933628`, `process_vodomery_alerts`
  `2026-08-11T11:47:14.949453`, and `quarter_hour_job`
  `2026-08-11T11:47:16.573035`. No latest failure timestamp was present for
  those checked keys.
- Production virtual-environment verification returned
  `Production Python environment matches requirements-production.lock.txt.`
- Tracked and deployed Caddyfile SHA-256 hashes matched:
  `08CDF04AFC4F856FEC8DFE4AB2E07A746763B152CA91553E349CCCE8E6D3DF2C`.

Required post-restart checks:

1. Confirm Windows boot time is after `2026-08-11 11:57 +02:00` and
   `API_dashboard_caddy` ran after boot with result 0.
2. Confirm expected listeners 80/443/2019/8000/8001 plus tailnet 9443, with
   no 8010/8011.
3. Confirm local API live/ready, Streamlit health, Caddy admin, and protected
   auth 401 without bearer.
4. Confirm scheduler heartbeat is fresh and newer than boot.
5. Wait for the first post-boot vodomery quarter-hour cycle and require
   successful `check_database_availability`, `vodomery_db_import`,
   `score_new_measurements`, `detect_events_from_scores`,
   `process_vodomery_alerts`, and `quarter_hour_job`.
6. Verify production virtual-environment lock still matches.
7. Verify tracked/deployed Caddyfile hashes match.
8. Verify the loaded source recognizes `SUSTAINED_HIGH_USAGE` in
   `EVENT_CONFIG` and vodomery alert-rule `EVENT_TYPE_OPTIONS`.
9. In the admin dashboard, verify the vodomery alerting event-type selector
   contains `SUSTAINED_HIGH_USAGE`. If no authenticated browser session is
   available to the agent, record this as operator-verification required, not
   as a failed backend check.
10. After operator confirmation of recipient/severity/scope, create the pilot
    alert rule. Recommended initial rule:
    `event_type=SUSTAINED_HIGH_USAGE`, `send_on=ACTIVE`,
    `min_duration_minutes=0`, scoped either to `E_V1` or to the selected
    vodomery scope.

Known risks/gaps:

- The changes are uncommitted. A reset/checkout/clean before restart would
  remove the intended production activation.
- `SUSTAINED_HIGH_USAGE` will not necessarily appear immediately after
  restart; it requires qualifying post-checkpoint scores or later rebuilt
  history.
- A production alert rule still has to be created explicitly. Until then the
  new event type can be generated but will not send email.
- Public browser verification may require an existing admin session or
  operator action; do not print credentials or tokens to automate it.
- This restart does not authorize monitoring-agent task restoration,
  unrelated Caddy changes, database data corrections, historical alert
  delivery, or any non-vodomery production write.

### 2026-08-11 12:08 +02:00 - Vodomery sustained high usage post-restart verification

- Windows booted at `2026-08-11 12:00:51 +02:00`, after the
  `2026-08-11 11:57 +02:00` pre-restart handoff. Startup task
  `API_dashboard_caddy` was `Ready`, ran at `2026-08-11 12:01:01 +02:00`,
  and returned result 0.
- Expected listeners 80, 443, 2019, 8000, 8001, and tailnet 9443 were
  present. Temporary listeners 8010/8011 were absent. Sanitized ownership
  showed Caddy on 80/443/2019, Python on 8000/8001, and Tailscale on tailnet
  443/9443.
- Local API live/ready, Streamlit health, and Caddy admin returned HTTP 200.
  Protected `/api/v1/auth/me` without a bearer token returned HTTP 401. Local
  Caddy/SNI HTTPS returned 200 HTML, and local HTTP returned 308.
- Scheduler was running with fresh heartbeat `2026-08-11T12:06:06.132729`,
  newer than boot. The first post-boot vodomery cycle completed successfully:
  `check_database_availability` at `2026-08-11T12:05:05.086434`,
  `vodomery_db_import` at `2026-08-11T12:05:06.773278`,
  `score_new_measurements` at `2026-08-11T12:05:12.090305`,
  `detect_events_from_scores` at `2026-08-11T12:05:12.263307`,
  `process_vodomery_alerts` at `2026-08-11T12:05:12.292403`, and
  `quarter_hour_job` at `2026-08-11T12:05:13.945753`. No latest failure
  timestamp was present for those checked keys.
- Production virtual-environment verification returned
  `Production Python environment matches requirements-production.lock.txt.`
  Tracked and deployed Caddyfile SHA-256 hashes matched:
  `08CDF04AFC4F856FEC8DFE4AB2E07A746763B152CA91553E349CCCE8E6D3DF2C`.
- Production-venv imports confirmed `SUSTAINED_HIGH_USAGE` in vodomery
  `EVENT_CONFIG`, vodomery alert-rule `EVENT_TYPE_OPTIONS`, and dashboard
  alerting labels/options. PostgreSQL check constraints
  `ck_event_type_valid` and `ck_alert_rule_event_type_valid` also contain
  `SUSTAINED_HIGH_USAGE`.
- Authenticated Streamlit admin selector verification was not performed from
  the agent environment because no admin browser session or credential was
  available. Treat this as operator-verification required, not a backend
  failure.
- No production alert rule, historical backfill, email delivery, credential
  readout, raw operational row dump, runtime configuration change, unrelated
  production write, or monitoring-agent action was performed.

### 2026-08-11 - Vodomery sustained high usage operator confirmation

- User confirmed the `SUSTAINED_HIGH_USAGE` event type appeared in the
  dashboard alerting selector and configured a production rule from it.
- `VOD-001` was moved from active work to completed work. This documentation
  update records operator confirmation only; the agent did not create or edit
  the rule, inspect recipient details, send email, backfill history, or change
  production data.

### 2026-08-11 13:38 +02:00 - Plynomery long high usage pre-restart handoff

Reason for restart:

- Load the corrected plynomery `LONG_HIGH_USAGE` event timing and inclusive
  alert-duration matching into the production scheduler, FastAPI, and
  Streamlit processes.
- The supported production recovery model remains a whole Windows workstation
  restart through the existing `API_dashboard_caddy` startup task; do not stop
  or recreate individual production processes for this activation.

Current task and conversation state:

- Completed in source: existing plynomery `LONG_HIGH_USAGE` now stores
  event `start_time` at the first qualifying score in the consecutive run,
  not at the later eighth score that opens the event.
- Completed in source: opening `duration_minutes`, `max_z_score`,
  `avg_z_score`, and `total_deviation` are computed over the complete
  qualifying run that opened the event.
- Completed in source: plynomery alert-rule duration matching is inclusive,
  so a rule with `min_duration_minutes=30` matches a stored 30-minute event.
- Completed in source: normal plynomery event detection and outlier-review
  event rebuild share trigger, duration, and opening-stat helpers.
- Pending: restart the workstation and verify the runtime stack plus one
  post-boot plynomery quarter-hour cycle.
- First action after restart: read `AGENTS.md`,
  `agents/decisions/DECISIONS.md`, and this handoff; run
  `git status --short`; confirm boot after
  `2026-08-11 13:38 +02:00` and confirm `API_dashboard_caddy` result 0 after
  boot.

Working tree and deployment:

- The working tree is intentionally non-clean from the plynomery alert timing
  source update and documentation handoff. Do not reset, checkout, clean,
  delete, overwrite, commit, push, or create a code-integrity baseline during
  restart handling.
- Source changes:
  `moduly/mereni/plynomery/plynomery_events.py`,
  `moduly/mereni/plynomery/database/outlier_review_apply.py`,
  `moduly/mereni/plynomery/alerting/service.py`,
  `tests/test_plynomery_events.py`, and
  `tests/test_plynomery_alert_service.py`.
- Documentation changes:
  `agents/decisions/DECISIONS.md`, `agents/work/ACTIVE.md`,
  `agents/work/COMPLETED.md`, and `agents/history/SESSION_NOTES.md`.
- Verification before restart: direct plynomery alert/event tests passed with
  `14 passed`; broader adjacent regression for plynomery, outlier review,
  scheduler, dashboard alerting, and API authorization passed with
  `304 passed`; production Python compile passed; `git diff --check` passed
  with line-ending normalization warnings only.
- No production database row was intentionally changed, no historical event
  backfill was run, no alert email was sent, no alert rule or recipient was
  changed by the agent, and no runtime configuration was changed by the source
  update.
- Runtime rule context: one enabled plynomery rule exists for
  `LONG_HIGH_USAGE` with `severity_min=LOW`, `min_duration_minutes=30`, and
  `send_on=ACTIVE`; recipient details were not printed.

Sensitive and runtime artifacts:

- Do not print, change, delete, or commit `.env`, database credentials, bearer
  tokens, cookies, ProgramData proxy credentials, raw authenticated Health
  responses, raw meter data, scheduler locks, SmartFuelPass/session data,
  monitoring-agent credentials/state, or operational database row dumps.
- Do not send a test email, run historical event backfill, create or edit
  alert rules, or execute unrelated manual scheduler/database operations
  during post-restart verification unless explicitly approved.

Expected processes/listeners after restart:

- FastAPI/Uvicorn on `127.0.0.1:8000`.
- Streamlit on `127.0.0.1:8001`.
- Scheduler `main.py` holding the scheduler process lock.
- Caddy on TCP 80/443 and admin `127.0.0.1:2019`.
- Tailscale tailnet listeners 443 and 9443 retained; temporary 8010/8011
  absent.

Expected application state:

- API live/ready: HTTP 200.
- Streamlit health: HTTP 200.
- Caddy admin `/config/`: HTTP 200.
- Protected `/api/v1/auth/me` without bearer token: HTTP 401.
- Scheduler running with a heartbeat newer than boot.
- First post-boot plynomery quarter-hour cycle should complete
  `check_database_availability`, `plynomery_db_import`,
  `score_new_plynomery_measurements`,
  `detect_plynomery_events_from_scores`, `process_plynomery_alerts`, and
  `quarter_hour_job` successfully.
- Production virtual environment still matches `requirements-production.lock.txt`.
- Tracked and deployed Caddyfile SHA-256 hashes remain equal to
  `08CDF04AFC4F856FEC8DFE4AB2E07A746763B152CA91553E349CCCE8E6D3DF2C`.
- Loaded production source recognizes `EVENT_LONG_HIGH_USAGE`, stores
  qualified-run start time through the shared helper, and treats
  `min_duration_minutes` inclusively in plynomery alert matching.
- No plynomery alert email is expected until a qualifying active
  `LONG_HIGH_USAGE` event exists and matches an enabled rule.

Pre-restart runtime status at `2026-08-11 13:38 +02:00`:

- Windows boot: `2026-08-11 12:00:51 +02:00`.
- Startup task `API_dashboard_caddy`: `Ready`, last run
  `2026-08-11 12:01:01 +02:00`, result 0.
- Listeners were present on 80/443/2019/8000/8001 and tailnet 443/9443.
  Sanitized process names: Caddy owned 80/443/2019, Python owned 8000/8001,
  and Tailscale owned tailnet 443/9443. Temporary 8010/8011 were absent.
- API live 200, API ready 200, Streamlit health 200, Caddy admin 200, and
  protected `/api/v1/auth/me` without bearer 401.
- Scheduler was running with heartbeat `2026-08-11T13:36:07.039081`.
  Latest relevant successes: `check_database_availability`
  `2026-08-11T13:35:05.092367`, `plynomery_db_import`
  `2026-08-11T13:35:11.111572`, `score_new_plynomery_measurements`
  `2026-08-11T13:35:11.566749`,
  `detect_plynomery_events_from_scores`
  `2026-08-11T13:35:11.646509`, `process_plynomery_alerts`
  `2026-08-11T13:35:11.668035`, and `quarter_hour_job`
  `2026-08-11T13:35:12.344473`. No latest failure timestamp was present for
  those checked keys.
- Production virtual-environment verification returned
  `Production Python environment matches requirements-production.lock.txt.`
- Tracked and deployed Caddyfile SHA-256 hashes matched:
  `08CDF04AFC4F856FEC8DFE4AB2E07A746763B152CA91553E349CCCE8E6D3DF2C`.

Required post-restart checks:

1. Confirm Windows boot time is after `2026-08-11 13:38 +02:00` and
   `API_dashboard_caddy` ran after boot with result 0.
2. Confirm expected listeners 80/443/2019/8000/8001 plus tailnet 9443, with
   no 8010/8011.
3. Confirm local API live/ready, Streamlit health, Caddy admin, and protected
   auth 401 without bearer.
4. Confirm scheduler heartbeat is fresh and newer than boot.
5. Wait for the first post-boot plynomery quarter-hour cycle and require
   successful `check_database_availability`, `plynomery_db_import`,
   `score_new_plynomery_measurements`,
   `detect_plynomery_events_from_scores`, `process_plynomery_alerts`, and
   `quarter_hour_job`.
6. Verify production virtual-environment lock still matches.
7. Verify tracked/deployed Caddyfile hashes match.
8. Verify loaded production source imports `EVENT_LONG_HIGH_USAGE`, preserves
   the first qualifying timestamp through `_record_triggered_score`, and
   matches a plynomery alert rule when event duration equals
   `min_duration_minutes`.
9. Confirm no unexpected plynomery alert delivery failure appeared after the
   first post-boot cycle. Do not print recipient details or raw delivery rows.
10. Record the exact post-restart result here and stop to diagnose any
    listener, readiness, scheduler, import, event, alerting, hash, or
    authentication regression.

Known risks/gaps:

- The changes are uncommitted. A reset/checkout/clean before restart would
  remove the intended production activation.
- Corrected `LONG_HIGH_USAGE` timing does not rewrite existing historical
  event rows by itself. Future approved outlier-review rebuilds will use the
  corrected timing.
- A matching active event may not appear immediately after restart; it depends
  on future qualifying post-checkpoint scores.
- Public browser verification may require an existing admin session or
  operator action; do not print credentials or tokens to automate it.
- This restart does not authorize monitoring-agent task restoration,
  unrelated Caddy changes, database data corrections, historical alert
  delivery, or any non-plynomery production write.

### 2026-08-14 - Monitoring 0.8.1 continuous task restoration proof

- On the supervision station, elevated registration/start of
  `MonitoringAgentTest` from
  `C:\Users\tra\PycharmProjects\monitoring-agent-0.8.1-test` succeeded. The
  task was `Running`; `LastTaskResult=267009` / `0x41301` is the expected
  currently-running task status.
- The first audit after start retained degraded startup/recovery cycles with
  connection-error evidence. A later sanitized latest-cycle endpoint summary
  showed all nine endpoint keys (`live`, `ready`, `system_scheduler`,
  `scheduler_detail`, `system_runtime`, `system_database`, `system_proxy`,
  `system_smartfuelpass`, `external_web`) returning HTTP 200 / `success` on
  attempt 1.
- Audit v7 then reported eight complete contract-4/set-3 cycles, first
  recovery at cycle 5, latest heartbeat `healthy`, nine latest observations,
  zero latest transport failures, valid endpoint/cycle order, valid
  retry/attempt bounds, clean open continuous lifecycle, and no new
  concurrent-start, run-reentry, unclean, abandoned, incomplete, late/early, or
  overlap evidence.
- Roadmap item 1 is complete. Continue with roadmap item 2 only; do not run
  foreground continuous mode or `--once` while the Scheduled Task is running.
  `--check-config` and `--audit-state` remain safe concurrent diagnostics.
- The GitHub repository
  `https://github.com/mtravnicekarmex/monitoring-agent-0.8.1.git` is public at
  commit `02a90a4ae887867d20819e4b2b618d86f750c48d`; its manifest SHA-256
  matches
  `18A3E477E724EEA61F3EFDCBE303BEBE4DC298A4D646D37FE643D6CD9C49CBB1`.
  Runtime files matched the manifest with `core.autocrlf=false`, but
  `monitoring_agent/README.md` does not match the manifest and should be fixed
  before using GitHub checkout as a strict integrity source.

### 2026-08-14 - Monitoring item 2 incident lifecycle implemented locally

- `monitoring_agent/incidents.py` adds incident-rule version 1 as a pure local
  deterministic layer. It consumes already-normalized observation facts or
  complete-cycle snapshots and returns sanitized incident states/transitions.
  It does not read `.env`, perform network access, write state, create an
  outbox, send email, mutate the target application, or replace legacy alerts.
- The default rule table distinguishes `endpoint`, `target_wide_outage`,
  `observer_self_health`, and `supervision_center_blind_spot`. It defines
  confirmation thresholds, recovery thresholds, deterministic stale evidence
  checks, recurrence cooldown, target-wide suppression of per-endpoint
  retryable transport noise, and historical-evidence suppression for retained
  upgrade artifacts.
- `monitoring_agent/README.md` now records the item-2 rule table and explicit
  lifecycle semantics. `DEC-128` records the no-persistence/no-delivery
  boundary. `scripts/build_monitoring_agent_bundle.py` includes the new module
  in the future bundle allowlist, and the README warns not to rebuild changed
  source under the already verified 0.8.1 identity.
- Focused verification passed:
  `.venv\Scripts\python.exe -m pytest tests\test_monitoring_agent_incidents.py -q`
  returned `7 passed`; `.venv\Scripts\python.exe -m compileall
  monitoring_agent scripts\build_monitoring_agent_bundle.py` passed.
- Roadmap item 2 is complete locally. Continue with item 3 only: bounded
  incident store and delivery outbox. External delivery, report rendering,
  interpretation, process control, application/database writes, and
  legacy-alert replacement remain unauthorized.

### 2026-08-14 - Monitoring item 3 bounded incident store implemented locally

- `monitoring_agent/incident_store.py` adds bounded local
  `incident_state.json` persistence for normalized incident states, sanitized
  transition records, report references, and delivery-intent outbox items.
  The outbox has deterministic idempotency keys,
  pending/in-progress/sent/dead-letter state, due-claim state, retry backoff,
  and abandoned-claim
  recovery, but no sender adapter, recipients, credentials, message body,
  network access, or delivery authorization.
- Environment contract 3 now requires explicit local bounds for observation
  records, incident states, transition records, outbox items, delivery
  attempts, retry backoff, and abandoned-claim timeout. Legacy env v1/v2 remain
  loadable with conservative code defaults for controlled upgrade
  compatibility only.
- `ObserverStore.retain_recent_observations()` keeps whole recent cycles and
  atomically rewrites `observations.jsonl` after each runtime cycle. Corrupt
  incident state and corrupt observation history fail closed without overwrite.
- `monitoring_agent/.env.example`, `monitoring_agent/README.md`,
  `monitoring_agent/__main__.py`, `monitoring_agent/store.py`,
  `monitoring_agent/settings.py`, `monitoring_agent/__init__.py`, and
  `scripts/build_monitoring_agent_bundle.py` were updated for the candidate
  source. Do not rebuild or deploy this changed source under the already
  verified 0.8.1 identity.
- Focused verification passed:
  `.venv\Scripts\python.exe -m pytest tests\test_monitoring_agent_state_store.py -q`
  returned `8 passed`; `.venv\Scripts\python.exe -m pytest
  tests\test_monitoring_agent.py tests\test_monitoring_agent_incidents.py
  tests\test_monitoring_agent_state_store.py -q` returned `101 passed`;
  `.venv\Scripts\python.exe -m pytest tests\test_monitoring_facade.py
  tests\test_monitoring_agent.py tests\test_monitoring_agent_incidents.py
  tests\test_monitoring_agent_state_store.py -q` returned `114 passed`;
  `.venv\Scripts\python.exe -m compileall monitoring_agent
  scripts\build_monitoring_agent_bundle.py` passed.
- Roadmap item 3 is complete locally. Item 4 was completed later on
  2026-08-14; continue with item 5 only after separate delivery-boundary
  approval. External delivery, process control, application/database writes,
  recipient configuration, real email sending, and legacy-alert replacement
  remain unauthorized.

### 2026-08-14 - Monitoring item 4 pure report and draft prompt implemented locally

- `monitoring_agent/reporting.py` adds pure deterministic report and
  programming-agent prompt renderers over supplied normalized incident facts
  and optional bounded incident-store snapshots. The renderers do not read
  `.env`, inspect runtime state files, claim outbox items, send messages, open
  network connections, mutate incident state, or control processes.
- Reports separate verified facts, deterministic rule conclusions, historical
  qualifications/evidence gaps, and hypotheses. The outbox section reports
  delivery-disabled counts and never treats a pending outbox item as delivery
  authorization.
- The programming-agent prompt is bounded and explicitly draft-only. It asks
  for read-only diagnostic planning and does not authorize command execution,
  network contact, state mutation, service restart, delivery attempt, or
  legacy-alert replacement.
- Defensive redaction covers likely secret assignments, bearer values, URL
  query/fragment content, Windows user paths, and synthetic private
  identifiers. Raw credentials, `.env` contents, endpoint bodies, recipients,
  and private runtime state remain invalid report inputs.
- `monitoring_agent/README.md`, `monitoring_agent/__init__.py`,
  `scripts/build_monitoring_agent_bundle.py`, the roadmap, active work index,
  reporting handoff, `AGENTS.md`, and `DEC-130` were updated for the candidate
  source. Deployed 0.8.1 behavior is unchanged.
- Focused verification passed:
  `.venv\Scripts\python.exe -m pytest tests\test_monitoring_agent_reporting.py -q`
  returned `8 passed`; `.venv\Scripts\python.exe -m pytest
  tests\test_monitoring_agent.py tests\test_monitoring_agent_incidents.py
  tests\test_monitoring_agent_state_store.py tests\test_monitoring_agent_reporting.py -q`
  returned `109 passed`; `.venv\Scripts\python.exe -m pytest
  tests\test_monitoring_facade.py tests\test_monitoring_agent.py
  tests\test_monitoring_agent_incidents.py
  tests\test_monitoring_agent_state_store.py
  tests\test_monitoring_agent_reporting.py -q` returned `122 passed`;
  `.venv\Scripts\python.exe -m compileall -q monitoring_agent
  scripts\build_monitoring_agent_bundle.py
  tests\test_monitoring_agent_reporting.py` passed; `git diff --check` passed
  with line-ending normalization warnings only.
- Roadmap item 4 is complete locally. Continue with item 5 only: test-only
  delivery adapter design and approval. Production recipients, real delivery,
  programmer-agent execution, process control, application/database writes,
  and legacy-alert replacement remain unauthorized.

### 2026-08-14 - Monitoring item 5 delivery adapter source preflight implemented locally

- `monitoring_agent/delivery.py` adds a disabled-by-default test-only delivery
  adapter for incident outbox items. It is not wired into the polling loop and
  does not run unless called explicitly by a later operator-controlled
  workflow.
- Disabled mode does not claim outbox items, mutate `incident_state.json`,
  build a message, or call a transport. Enabled mode is restricted to
  `mode="test"` and requires one controlled test recipient from
  `DELIVERY_TEST_RECIPIENT`, an in-memory allowlist derived from the same
  recipient, supplied report text by `report_reference`, and an explicit
  transport object.
- Sanitized results include only outbox identity, incident key, action, report
  reference, recipient hash, attempt count, status, and coarse error code.
  Raw recipients, SMTP usernames, passwords, sender values, message bodies,
  credential values, and transport exception text are excluded from state and
  results.
- `OutlookEmailTransport` calls the standalone monitoring-agent
  `send_email_outlook()` function. It mirrors the existing local alarm-email
  Office365 STARTTLS pattern with TLS upgrade, login, send message, and retry
  only for known transient SMTP response codes, using `O_EMAIL` and `O_APP`
  for SMTP login/default sender, with `EMAIL`/`APP` accepted only as
  compatibility fallback. Tests use fake SMTP only; no real network connection
  or email send was performed.
- `monitoring_agent/delivery_cli.py` adds optional recipient hashing
  diagnostics, synthetic local outbox preparation, dry-run without claim, and
  confirmed `send-due` entry points. Synthetic preparation requires
  `--confirm PREPARE_SYNTHETIC_DELIVERY_TEST_STATE` and refuses an existing
  state file unless explicitly overridden. `send-due` requires
  `--confirm SEND_TEST_DELIVERY`, one exact `report_reference`, a claim id, a
  sanitized report file, `DELIVERY_TEST_RECIPIENT`, the existing alarm
  credential names `O_EMAIL` and `O_APP`, and optional exact `idempotency_key`;
  `.env` files are rejected as report input. No separate recipient-hash
  configuration is required. Delivery-test recipient variables use
  `DELIVERY_TEST_*`, not `MONITORING_AGENT_*`, to avoid the strict runtime
  schema. The polling runtime validates only `MONITORING_AGENT_*` keys from
  the env file, so `O_EMAIL`, `O_APP`, and `DELIVERY_TEST_RECIPIENT` may
  remain in the same local `.env` without changing the observer runtime
  contract.
- `monitoring_agent/README.md`, `monitoring_agent/__init__.py`,
  `monitoring_agent/.env.example`, `monitoring_agent/settings.py`,
  `scripts/build_monitoring_agent_bundle.py`, the roadmap, reporting handoff,
  active work index, `AGENTS.md`, and `DEC-131` were updated for the source
  preflight and the non-prefixed delivery-key env-loader compatibility.
- Focused verification passed:
  `.venv\Scripts\python.exe -m pytest
  tests\test_monitoring_agent_delivery_cli.py
  tests\test_monitoring_agent_delivery.py
  tests\test_monitoring_agent.py -q` returned `109 passed`; the broader
  monitoring matrix
  `.venv\Scripts\python.exe -m pytest tests\test_monitoring_facade.py
  tests\test_monitoring_agent.py tests\test_monitoring_agent_incidents.py
  tests\test_monitoring_agent_state_store.py
  tests\test_monitoring_agent_reporting.py tests\test_monitoring_agent_delivery.py
  tests\test_monitoring_agent_delivery_cli.py -q` returned `146 passed`;
  `.venv\Scripts\python.exe -m compileall -q monitoring_agent
  scripts\build_monitoring_agent_bundle.py tests\test_monitoring_agent.py
  tests\test_monitoring_agent_delivery.py
  tests\test_monitoring_agent_delivery_cli.py` passed.
- At this source-preflight point, roadmap item 5 remained open. Completion
  still required explicit approval of the exact recipient, credential boundary,
  runtime command, expected sanitized evidence, rollback/stop criteria, and one
  controlled message. The later same-day runtime proof is recorded below.
  Production recipients and legacy alerts remain unchanged.

### 2026-08-14 - Monitoring agent Git checkout update pushed

- The user chose direct Git iteration for the test-mode monitoring agent
  instead of creating a new ZIP/version for every change.
- The standalone repository
  `https://github.com/mtravnicekarmex/monitoring-agent-0.8.1.git` was cloned,
  updated with the local item 2-5 candidate source, committed, and pushed to
  `master` as `5cfc5916d3e83cdcc1eecd34f3f2719d62ec351c`
  (`Add monitoring agent test delivery flow`).
- The pushed checkout includes incident rules, bounded incident/outbox state,
  pure report/programming-agent prompt rendering, and the test-only delivery
  path using `O_EMAIL`, `O_APP`, and `DELIVERY_TEST_RECIPIENT`. `EMAIL`/`APP`
  remain accepted only as compatibility fallback.
- The standalone checkout compiled successfully. Runtime settings loaded from
  a synthetic env v3 file containing `O_EMAIL`, `O_APP`, and
  `DELIVERY_TEST_RECIPIENT`; delivery CLI `hash-recipient` loaded a synthetic
  env file and printed only a recipient hash.
- At push time, the next supervision-station step was to stop
  `MonitoringAgentTest`, pull `master`, run `--check-config`, then start the
  task again. The later same-day runtime proof is recorded below.

### 2026-08-14 - Monitoring item 5 controlled delivery test passed

- The supervision station verified `git rev-parse HEAD` at
  `5cfc5916d3e83cdcc1eecd34f3f2719d62ec351c` and `--check-config` returned
  configuration valid with endpoint count 9, env contract 2, and mode `test`.
- `hash-recipient --env-file .\.env` loaded `DELIVERY_TEST_RECIPIENT` and
  printed only the recipient hash.
- `prepare-synthetic` created one isolated synthetic
  `endpoint:system_database` outbox item and sanitized report under a temp
  delivery-test state, not the live agent state.
- `dry-run` for
  `controlled-test-report:v1:synthetic-endpoint-system-database` returned
  `due_count=1`, `mode="test"`, and `status="dry_run_ok"`.
- The explicitly confirmed `send-due` command returned sanitized success:
  `status="sent"`, `action="opened"`, `attempt_count=1`, and
  `error_code=null`.
- A follow-up `dry-run` for the same `idempotency_key` returned
  `due_count=0`, proving the sent synthetic outbox item was not pending for
  re-send.
- Roadmap item 5 is complete for the test-only delivery boundary. The polling
  loop remains unwired to automatic delivery; production recipients,
  production delivery channels, programmer-agent execution, remediation, and
  legacy-alert replacement remain unauthorized.

### 2026-08-14 - Monitoring item 6 draft interpretation contract implemented locally

- `monitoring_agent/interpretation.py` adds interpretation contract version 1
  over supplied `MonitoringReportSnapshot` objects.
- Interpretation runs only with explicit in-memory
  `InterpretationPolicy(enabled=True, mode="draft")`, an injected provider
  object, and at least one confirmed active incident. Candidate-only evidence,
  disabled policy, missing provider, provider exception, invalid output, or
  unsafe output falls back to the deterministic report.
- The policy records provider/model names, timeout, cost ceiling,
  prompt/output bounds, and item-count bounds. Permission-style flags for
  network, state mutation, process control, delivery, and alert suppression
  must remain false.
- The module adds no `.env` keys, provider credentials, network client,
  polling-loop integration, state writes, delivery, process control,
  remediation, or alert suppression. Real provider execution remains a later
  approval gate.
- `monitoring_agent/README.md`, `monitoring_agent/__init__.py`,
  `scripts/build_monitoring_agent_bundle.py`, roadmap, reporting handoff,
  active work index, `AGENTS.md`, and `DEC-134` were updated.
- Verification:
  `.venv\Scripts\python.exe -m pytest tests\test_monitoring_agent_interpretation.py -q`
  returned `9 passed`;
  `.venv\Scripts\python.exe -m pytest tests\test_monitoring_facade.py
  tests\test_monitoring_agent_interpretation.py
  tests\test_monitoring_agent_reporting.py tests\test_monitoring_agent_delivery.py
  tests\test_monitoring_agent_delivery_cli.py
  tests\test_monitoring_agent_incidents.py
  tests\test_monitoring_agent_state_store.py tests\test_monitoring_agent.py -q`
  returned `155 passed`; compileall passed; `git diff --check` passed with
  line-ending normalization warnings only.
- The standalone GitHub test repository was updated through the direct
  Git-pull workflow and pushed to `master` as
  `86ee42b058c74675976904c1e51a2f3677c5f138`
  (`Add draft interpretation contract`). The commit contains the new
  `monitoring_agent/interpretation.py`, package export, README updates, and
  regenerated manifest files with 19 declared runtime files.

### 2026-08-14 - Monitoring item 6 pulled and audited on supervision station

- The supervision station verified `git rev-parse HEAD` at
  `86ee42b058c74675976904c1e51a2f3677c5f138`.
- `py -3.14 run_monitoring_agent.py --check-config` returned configuration
  valid with endpoint count 9, env contract 2, and mode `test`.
- Audit-v7 reported endpoint set 3, 289 complete cycles, outcome counts
  283 healthy and 6 partial failure, latest heartbeat `healthy`, nine latest
  observations, zero latest transport failures, valid endpoint/cycle order,
  valid retry/attempt bounds, no incomplete/trailing observations, clean open
  continuous lifecycle, and zero concurrent-start, run-reentry, unclean,
  abandoned, or overlap evidence.
- This proves the pulled item-6 checkout did not regress the continuous
  observer. It does not authorize real interpretation-provider execution,
  automatic delivery, remediation, process control, or legacy-alert
  replacement.

### 2026-08-14 - Monitoring item 7 shadow comparison source preflight

- `monitoring_agent/shadow_pilot.py` adds shadow-pilot comparison contract
  version 1 for supplied sanitized monitoring-agent and legacy-alert
  detection/recovery events.
- The comparison is start-inclusive/end-exclusive by reviewed period,
  deduplicates each source stream, matches by `incident_key` inside a
  configured match window, and reports matched detections, confirmation delay,
  recoveries, recovery delay, duplicate counts/rates, false positives, false
  negatives, agent/legacy-only recoveries, and blind spots.
- Output is explicitly `mode="shadow_only"` and carries a safety boundary that
  legacy alerts remain authoritative.
- The module does not read `.env`, inspect databases, poll endpoints, call an
  interpretation provider, send email, mutate state, control processes,
  remediate, or suppress/replace legacy alerts. No new `.env` variables are
  required.
- `monitoring_agent/README.md`, `monitoring_agent/__init__.py`,
  `scripts/build_monitoring_agent_bundle.py`, roadmap, reporting handoff,
  active work index, `AGENTS.md`, and `DEC-135` were updated.
- Verification:
  `.venv\Scripts\python.exe -m pytest tests\test_monitoring_agent_shadow_pilot.py -q`
  returned `10 passed`;
  `.venv\Scripts\python.exe -m pytest tests\test_monitoring_facade.py
  tests\test_monitoring_agent_shadow_pilot.py
  tests\test_monitoring_agent_interpretation.py
  tests\test_monitoring_agent_reporting.py tests\test_monitoring_agent_delivery.py
  tests\test_monitoring_agent_delivery_cli.py
  tests\test_monitoring_agent_incidents.py
  tests\test_monitoring_agent_state_store.py tests\test_monitoring_agent.py -q`
  returned `165 passed`.
- The standalone GitHub test repository was updated through the direct
  Git-pull workflow and pushed to `master` as
  `3e7b94e9045527a1254b10066a3a34493577f025`
  (`Add shadow pilot comparison contract`). The commit contains the new
  `monitoring_agent/shadow_pilot.py`, package export, README updates, and
  regenerated manifest files with 20 declared runtime files. The new
  `manifest.sha256` is
  `80f0539d3a4de8410e137664cc7122cdc47b8baa4b7190d323d3eea9b3ca5155`.
- This was only the 2026-08-14 source preflight for item 7. The remaining
  reviewed-period requirement was completed later on 2026-08-17 by the
  no-event baseline and synthetic file-comparison proof.

### 2026-08-14 - Monitoring item 7 pulled and audited on supervision station

- The supervision station verified `git rev-parse HEAD` at
  `3e7b94e9045527a1254b10066a3a34493577f025`.
- `py -3.14 run_monitoring_agent.py --check-config` returned configuration
  valid with endpoint count 9, env contract 2, and mode `test`.
- `Start-ScheduledTask -TaskName MonitoringAgentTest` initially failed from a
  non-elevated PowerShell with access denied, then succeeded from an elevated
  shell. The task state was `Running`.
- Audit-v7 reported endpoint set 3, 323 complete cycles, outcome counts
  317 healthy and 6 partial failure, latest heartbeat `healthy`, nine latest
  observations, zero latest transport failures, valid endpoint/cycle order,
  valid retry/attempt bounds, no incomplete/trailing observations, clean open
  continuous lifecycle, and zero concurrent-start, run-reentry, unclean,
  abandoned, or overlap evidence.
- This proved the pulled item-7 checkout did not regress the continuous
  observer. At that time it did not complete the reviewed-period shadow pilot;
  the remaining item-7 comparison requirement was completed later on
  2026-08-17. It did not authorize automatic delivery, real
  interpretation-provider execution, remediation, process control, or
  legacy-alert replacement.

### 2026-08-14 - End-of-day monitoring handoff

- Stop point, later superseded on 2026-08-17: roadmap item 7 had source
  preflight and remote non-regression proof, but still needed the
  reviewed-period shadow pilot.
- Last verified supervision-station checkout:
  `3e7b94e9045527a1254b10066a3a34493577f025`.
- Last verified runtime: `MonitoringAgentTest` was running after elevated
  start; audit-v7 latest heartbeat was `healthy` with nine observations and
  zero latest transport failures.
- Last verified aggregate: 323 complete cycles, 317 healthy and 6 partial
  failure, no incomplete/trailing observations, valid retry/order/timing, and
  zero concurrent-start, run-reentry, unclean, abandoned, or overlap evidence.
- Current implementation boundary: incident lifecycle, bounded store/outbox,
  deterministic reporting, test-only delivery, draft-only interpretation, and
  shadow-only comparison source exist. Automatic delivery, production
  recipients, real interpretation provider execution, remediation, process
  control, and legacy-alert replacement remain unauthorized.
- That next-session instruction was completed on 2026-08-17 by confirming the
  task, adding runtime shadow/file comparison proof, and closing item 7. Do
  not launch `--once` or a foreground continuous writer while the Scheduled
  Task is running.
