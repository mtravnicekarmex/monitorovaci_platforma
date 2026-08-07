# Monitoring Agent Cross-Host Failure-Isolation Test

Prepared: 2026-08-04

Status: all eight test-pilot phases completed through remote 0.7 deployment,
Scheduled Task registration, and supervision-center reboot proof

Parent plan:
`../plans/monitoring/SCHEDULER_MONITORING_AGENT_PLAN.md`

## Purpose

Prove that the test-mode observer on the supervision center remains alive,
records target transport loss as unknown/unreachable rather than scheduler
failure, and observes recovery without being restarted. Current scheduler
alerts remain authoritative throughout the proof.

This runbook did not authorize a monitored-workstation restart or Scheduled
Task registration by itself; those actions were executed only after their
separate approvals. It still does not authorize credential rotation, external
delivery, application write, another restart, or network/proxy reconfiguration.

The phases below preserve the completed 0.6 failure-isolation proof and the
subsequent 0.7 endpoint-set/restart evidence. The monitored workstation had to
restart fully because FastAPI/Caddy is created by its Windows startup process
and no supported API-only restart path exists. The remote 0.6.2 observer stayed
running through that target restart, after which the authenticated System
Runtime facade was verified before the agent changed. ZIP SHA-256
`0BA56B60FD8F5A229346D565FEA33F58F57F9239FE541F216C07E79E56D7BF20`,
retention of the existing 0.6 state, endpoint-key configuration
`live,ready,system_scheduler,system_runtime`, and safe config output with
`endpoint_count=4` all passed. One `--once` cycle contained four successes,
and audit v6 reported both legacy set 1 and current set 2 without sequence or
cycle mismatches.

## Preconditions

- The supervision center is the Windows 11/CPython 3.14 station already
  enrolled in the approved tailnet.
- Tailnet-only HTTPS port 9443 still reaches only the read-only monitoring
  facade; existing port 443 remains unchanged.
- The center stores all runtime values in one ACL-restricted local `.env`.
  Do not display, copy, hash, or record its content.
- Bundle `0.6.2-test` and its repository-recorded ZIP SHA-256 match before
  transfer.
  Expected ZIP SHA-256 is
  `C14A694F650BED6948450BEFA3704BF62B29359537ADE51B67B25DC9A8DC8C5D`.
- Install side by side with prior test bundles; do not delete or overwrite
  their immutable verification evidence.
- Retain the existing agent-owned observation-contract-2 and
  lifecycle-contract-1 state when upgrading from 0.6.0 to 0.6.1. Use a new
  empty state only when migrating from pre-0.6; never append 0.6 records to
  retained v0.5 state.
- Stop every 0.6.0/0.6.1 polling process before starting 0.6.2. Older
  processes do not acquire the new writer lock and can otherwise still overlap
  a new process.

## Phase 1 - Offline bundle verification

On the supervision center, using paths selected locally by its operator:

1. Verify the transferred ZIP SHA-256 against the repository-recorded value.
2. Extract into a new versioned directory.
3. Confirm the archive matches the exact manifest allowlist and contains
   `.env.example`, `.gitignore`, `run_monitoring_agent.py`, the runtime
   package, `manifest.json`, and `manifest.sha256`, but no real `.env`.
4. Verify `manifest.sha256`, then verify every file size and SHA-256 declared
   by `manifest.json`.
5. Copy `.env.example` to `.env`, edit only the local copy, and restrict its
   ACL. Keep agent state outside the extracted project directory.
6. Run `py -3.14 run_monitoring_agent.py --check-config`.
7. Confirm the safe output reports environment contract version 1, test mode,
   and three
   endpoints. Stop if any extra file, manifest mismatch, secret field, or
   configuration error appears.

## Phase 2 - Foreground healthy HTTPS cycle

1. Use the local `.env` containing the approved tailnet HTTPS base URL, the
   existing bearer, an agent instance label, the compatible agent-owned 0.6
   state directory, the reviewed polling values, and the three endpoint keys.
2. Run one foreground cycle with
   `py -3.14 run_monitoring_agent.py --once`. Never paste the bearer into the
   command line, PyCharm run configuration, console, or report.
3. Require three observations with `transport_status=success`, HTTP 200,
   schema-valid normalized payloads, and `attempt_count=1`.
4. Require the agent heartbeat to finish as `healthy`, with three observations
   and zero transport failures.
5. Confirm no response body, Authorization header, credential, target machine
   identifier, or raw operational value was printed.

## Phase 3 - Long-running observer baseline

1. Start the observer in the foreground without `--once`.
2. Observe at least three completed cycles without restarting the process.
3. Record only safe aggregates: cycle timestamps, endpoint keys, transport
   statuses, attempt counts, and heartbeat status.
4. Confirm cycle starts are separated by the configured start-to-start
   interval plus bounded jitter and that cycles do not overlap.
5. Record the observer process identity locally for continuity comparison;
   do not place machine or account identifiers in repository notes.

## Phase 4 - Approved target-loss proof

This phase is a hard approval gate. Use either an approved disposable
cross-host synthetic target or a separately approved whole monitored-host
restart. Do not stop `main.py`, FastAPI, Caddy, Tailscale, or the workstation
merely to satisfy this runbook without that approval.

While the foreground observer continues unchanged:

1. Make the approved target path unavailable.
2. Require each endpoint observation to end as `connection_error` or `timeout`
   after no more than three attempts with only the configured bounded
   backoff.
3. Require the observer heartbeat to remain current and become `degraded`.
4. Classify scheduler state as unknown/unreachable. Do not claim the scheduler
   stopped because transport evidence cannot prove that fact.
5. Confirm the observer process and supervision workstation remain alive and
   the monitored target receives no mutation request.

## Phase 5 - Recovery proof

1. Restore the approved target without restarting the observer.
2. If the monitored workstation restarted, require a newer safe boot identity
   when runtime coverage is later available; with the current three-route
   facade, record this as a known evidence gap.
3. Require subsequent observations to return to HTTP 200 and
   `transport_status=success` with schema-valid payloads.
4. Require the observer heartbeat to return from `degraded` to `healthy`.
5. Confirm the observer process identity is unchanged from the baseline.
6. Stop the foreground observer normally after evidence is captured and
   confirm the monitored target remains unchanged.

## 2026-08-05 observed execution

- The standalone `0.4.0-test` observer ran in one foreground console session
  on the separate supervision center while current alerts remained
  authoritative.
- Healthy three-endpoint cycles preceded sustained three-endpoint `timeout`
  cycles during monitored-workstation unavailability.
- One recovery cycle contained both `success` and `timeout`, which is expected
  when the three serial endpoint polls straddle target recovery.
- Subsequent cycles returned to three successful observations without an
  observer restart. Independent target-side checks confirmed the restarted
  workstation, private facade, and scheduler were healthy after recovery.
- The functional target-loss and recovery behavior passed. Audit v1 later
  retained 405 observations in 135 complete cycles: 90 healthy, 44 fully
  unreachable, and one partial-failure cycle. Retry bounds, endpoint order,
  inferred recovery, and the latest healthy heartbeat passed.
- Audit v2 found that the maximum 4,545.121-second interval followed a healthy
  0.071-second cycle, exceeded its allowed bound by 4,478.121 seconds, and was
  not a long HTTP cycle. Local Windows event times matched a
  supervision-station shutdown/restart. Target loss/recovery remains a
  functional pass; automatic supervision restart/resume was absent and
  historical process identity is unavailable for v0.5 state. Do not retain or
  paste raw state.

## Evidence to retain

- bundle version and ZIP/manifest verification result;
- config version and non-secret polling parameters;
- count and timing of healthy, unavailable, and recovered cycles;
- endpoint transport statuses and attempt counts;
- observer heartbeat state transitions;
- proof that the observer process continued across target loss and recovery;
- explicit known gaps and confirmation that no external delivery or mutation
  occurred.

After synchronizing and verifying `0.6.2-test`, run the aggregate audit from
the project root while the observer may continue in foreground:

```powershell
.\.venv\Scripts\python.exe .\run_monitoring_agent.py --audit-state
```

Retain only this sanitized JSON output. Do not attach or paste `.env`, state
paths, `observations.jsonl`, `observer_heartbeat.json`, or raw payloads.

Audit contract v5 must additionally include aggregate `lifecycle` evidence,
distinct process-run counts, clean/unclean restart counts, abandoned runs, and
incomplete-cycle counts. Scheduled `interval_*`, overlap, early, late, longest,
and largest-late findings must include only consecutive cycles from the same
run. Cross-run durations must appear only under sanitized `cross_run_*` facts
with `process_run_transition` classification. The audit must never output run
IDs, PID values, timestamps, or lifecycle records.

## Phase 6 - Foreground single-writer proof

1. Confirm all pre-lock 0.6.0/0.6.1 polling processes are stopped. Preserve
   their state and controlled-stop evidence.
2. Start one 0.6.2 foreground polling process and wait for a healthy cycle.
3. From a second console, run `run_monitoring_agent.py --once` with the same
   `.env`. Require the sanitized failure
   `agent startup error: state writer lock is unavailable`.
4. Confirm the rejected invocation made no HTTP request and added no lifecycle,
   heartbeat, observation, process-run, or cycle record. The first process
   must continue normally.
5. Stop the first process with Ctrl+C, then run one controlled `--once` cycle.
   This must succeed, proving the OS lock was released without deleting the
   persistent one-byte lock file.
6. Rerun audit v5. Historical reentry/concurrent-start counts may remain one,
   but the rejected 0.6.2 invocation must not increment them.

Observed on 2026-08-05: pass. The rejected invocation left process-run count 4
and lifecycle counts 4 starts, 3 stops, and 7 events while the first writer
continued from 39 to 43 healthy cycles. After Ctrl+C, a clean `--once` acquired
the released lock. Final audit reported 5 starts, 5 stops, 10 events, 47
healthy cycles, zero open/abandoned runs, historical reentry/concurrent counts
unchanged at one, and zero unclean restarts.

The included `register_monitoring_agent_task.ps1` may be previewed only with
`-WhatIf` during this phase. Actual Scheduled Task registration, task start,
supervision-station reboot, and rollback are separate explicit approval gates.

Do not retain bearer values, credential paths, tailnet names or addresses,
hostnames, user names, process command lines, raw response bodies, or raw
operational payloads.

## Phase 7 - Monitored-station restart and 0.7 endpoint-set handoff

Status: completed on 2026-08-06. The text below retains the procedure and stop
conditions; the observed result follows it. The 2026-08-05 pre-restart baseline
was boot `08:13:22 +02:00`, startup task run `08:13:32 +02:00` with result
0/state `Ready`, listeners on 80/443/2019/8000/8001/9443, no temporary
8010/8011 listener, and HTTP 200 from local API liveness/readiness plus
Streamlit health.

Before the monitored-station restart:

1. Confirm exactly one remote 0.6.2 writer owns the existing state and is
   producing complete three-endpoint cycles. Do not stop it and do not restart
   the supervision workstation.
2. Optionally capture one read-only audit-v5 aggregate as the before-state.
   Never copy raw JSONL, heartbeat, lifecycle, `.env`, or bearer content into
   the handoff.
3. Confirm the changed source is on the monitored workstation runtime path.
   Source presence alone does not prove the new route is active.
4. Restart the whole monitored workstation only after explicit operator
   approval. Do not substitute an unsupported ad-hoc API process restart.

After Windows returns:

1. Confirm the new boot time and successful execution/state of the established
   `API_dashboard_caddy` startup task. Verify the configured API, dashboard,
   proxy/admin, and tailnet-only facade listeners without printing process
   command lines or machine identifiers.
2. Require existing authenticated monitoring liveness, readiness, and
   system-scheduler routes to recover. A transient readiness 503 during startup
   is application state; wait for the established readiness contract before
   proceeding.
3. Using the dedicated monitoring identity without displaying it, require
   `GET /api/v1/monitoring/health/system/runtime` to return HTTP 200 and the
   reviewed `SystemRuntimeHealthResponse` schema. Verify only aggregate/schema
   facts; do not retain the raw response.
4. Confirm the still-running remote 0.6.2 observer recorded bounded target
   transport failure during the restart and at least one complete healthy
   recovery cycle afterward. A restart of that observer would invalidate this
   continuity check.

Only after all target-side checks pass:

1. Stop the remote 0.6.2 foreground writer with Ctrl+C and confirm it recorded
   a controlled stop. Ensure no second writer remains.
2. Transfer `monitoring-agent-0.7.0-test.zip`, verify its repository-recorded
   ZIP and manifest digests plus all declared file hashes, and extract it side
   by side. Do not overwrite or delete earlier verified bundles.
3. Reuse the existing external 0.6 state directory and existing secret values.
   Change only the endpoint-key line to
   `live,ready,system_scheduler,system_runtime`; do not replace the remote
   `.env` with `.env.example`.
4. Run `--check-config` and require exactly environment contract 1, test mode,
   and `endpoint_count=4`, with no URL, path, identity, or secret output.
5. Run one `--once` cycle. Require four observations, all
   `transport_status=success`, no retries under healthy conditions, a healthy
   four-observation heartbeat, and a controlled `once_completed` lifecycle
   stop.
6. Run `--audit-state`. Require audit contract 6, configuration endpoint set
   2/count 4, observation contract/set counts for both retained v2/set-1 and
   new v3/set-2 records, zero endpoint/cycle sequence mismatches, valid retry
   bounds, no trailing incomplete cycle, and a latest heartbeat matching the
   final complete cycle. The first successful 0.7 `--once` contributes exactly
   four contract-3/set-2 observations.
7. Retained historical `process_run_reentry_count=1`,
   `concurrent_start_count=1`, and false historical single-writer validity are
   expected from pre-lock evidence. They must not increment during this
   handoff. New lifecycle records must not create an unclean or abandoned run.

Stop conditions and rollback boundary:

- If the startup task, required listener, established facade route, or new
  System Runtime route fails, do not stop or upgrade the remote 0.6.2 observer.
  Correct and separately reactivate the monitored runtime first.
- If ZIP/manifest/config verification fails, do not execute 0.7 and do not
  alter the existing state.
- If the 0.7 `--once` cycle or audit fails, do not start continuous 0.7
  polling. Preserve all evidence and the old bundle/state; do not truncate,
  rewrite, or delete mixed history.
- At the time Phase 7 was written, `-WhatIf` registration review, actual remote
  Scheduled Task registration, supervision-workstation restart, and continuous
  0.7 promotion required later decisions. Their approved results are recorded
  below; remaining endpoint coverage and external delivery are still open.

Observed result:

- The monitored workstation restarted through its supported boot-created
  runtime boundary. Established listeners and routes recovered, and the new
  authenticated System Runtime facade returned HTTP 200 with valid schema,
  runtime status `ok`, five expected listeners with none non-OK, and no
  temporary listener.
- The remote 0.6.2 writer recorded recovery and stopped cleanly. The verified
  0.7 ZIP and manifest were extracted side by side with no content/allowlist
  mismatch and no real `.env`.
- Configuration migration retained the credential, external state path, and
  every non-endpoint value while changing only the exact four-key endpoint
  tuple. Config validation, one four-success cycle, and audit-v6 mixed-history
  checks passed. Continuous 0.7 polling then passed as one current writer.
- Retained historical `process_run_reentry_count=1` and
  `concurrent_start_count=1` did not increment. No unclean or abandoned run was
  created. Phase 7 passed.

## Phase 8 - Supervision Scheduled Task and reboot proof

Status: completed on 2026-08-06.

1. Create and validate the project-local Python 3.14 `.venv`.
2. Verify `SYSTEM` read/execute access to the project and interpreter, read
   access to `.env`, and Modify access to the external state directory and its
   existing children.
3. Register only the reviewed `MonitoringAgentTest` contract: `SYSTEM`, one
   `AtStartup` trigger, exact interpreter/runner/working directory,
   `StartWhenAvailable`, `IgnoreNew`, one-minute failure restart, no execution
   limit, and no secret command-line value. Registration must not start it.
4. Stop foreground 0.7 with Ctrl+C. Require a closed lifecycle run, task state
   `Ready`, and zero foreground agent process before reboot.
5. Restart the supervision center only after explicit approval. Do not start
   the agent manually after boot.
6. Require task state `Running`, a fresh postboot lifecycle or observation, one
   logical `SYSTEM` writer, one current open lifecycle run, and a current
   healthy four-observation heartbeat. Do not use raw Python process count as
   writer count because Windows venv may create a launcher/interpreter pair.
7. Compare historical overlap/reentry counts with the pre-reboot audit and
   require no increment, zero unclean restart, zero abandoned run, valid
   ordering/retry checks, and state advancement after boot.

Observed result:

- Effective PowerShell policy was `Restricted` and the reviewed helper was
  unsigned. The policy was not changed or bypassed. Equivalent reviewed
  registration commands succeeded from an elevated PowerShell after a first
  non-elevated `PermissionDenied` attempt left the task absent.
- `SYSTEM` project/config/interpreter access passed. State Modify initially
  failed, then the corrected inherited ACL passed on all five existing state
  objects.
- Pre-reboot audit contained eight starts/eight controlled stops, no open,
  unclean, or abandoned run, and a healthy four-observation heartbeat.
- The task launched after the 2026-08-06 boot. The venv launcher and its
  interpreter child were both `SYSTEM` continuous-mode processes but formed
  one logical parent-child runtime. The first lifecycle change arrived about
  110 seconds after task launch, so an earlier 75-second audit was correctly
  treated as premature rather than a pass.
- Final audit reached 1,162 complete cycles, with 1,155 healthy, 3 partial
  failure, and 4 unreachable. The latest degraded heartbeat recovered to
  healthy with four observations and zero transport failures. Lifecycle was
  nine starts/eight stops/one active run, zero unclean and abandoned runs, and
  unchanged historical overlap/reentry counts. Phase 8 passed.

## Pass criteria

- The observer runs on the separate supervision center throughout the proof.
- Target loss produces bounded transport retries and `degraded` observer
  self-health while scheduler state remains unknown.
- Recovery is observed without restarting the observer.
- Repeated cycles remain serialized and within the configured timing bounds.
- A second polling writer for the same state is rejected before runtime or
  network activity, and the lock is recoverable after process exit.
- The Scheduled Task resumes one logical writer after a supervision-center
  reboot and produces fresh lifecycle/observation evidence.
- Only agent-owned state changes; the monitored application remains read-only.
- No secret or operational identifier appears in retained evidence.

Credential rotation, full endpoint expansion, bounded retention, independent
center observation, incident lifecycle/reporting behavior, and external
delivery remain separate gates.
