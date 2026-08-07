# Monitoring Agent Reporting Layer Handoff

Prepared: 2026-08-06

Status: monitored-workstation safe facade expansion activated; remote 0.7
running but degraded by a diagnosed runtime-schema rolling incompatibility;
local 0.8.1 recovery/migration candidate verified; reporting and incident
layers not implemented

Parent plan: `SCHEDULER_MONITORING_AGENT_PLAN.md`

Runtime design: `SCHEDULER_MONITORING_AGENT_REMOTE_RUNTIME_DESIGN.md`

Approved implementation checklist: `MONITORING_AGENT_IMPLEMENTATION_ROADMAP.md`

## Purpose

This handoff fixes the verified input boundary for the next monitoring-agent
phase. It records what is actually running on the separate supervision center,
which evidence is trustworthy, which historical findings must not be
misinterpreted, and what the reporting layer may consume.

It does not authorize external delivery, application writes, incident
auto-remediation, process control, manual jobs, or replacement of the current
scheduler alerts.

## Verified deployed runtime

As of 2026-08-06, the supervision center runs the extracted
`0.7.0-test` bundle as a Windows Scheduled Task named
`MonitoringAgentTest`. The complete platform repository is not present on the
center. The standalone public minimal repository remains at its separately
verified older `0.4.1-test` baseline; the deployed 0.7 directory came from the
verified ZIP and is not evidence that the public repository was advanced.
The README packaged inside that immutable ZIP describes the pre-registration
installation gate and therefore still says automatic startup is unregistered.
For current operational status, this handoff, the remote-workstation
inventory, and `SESSION_NOTES.md` supersede that installation-time statement;
do not edit the deployed bundle merely to update its prose.

The deployed archive has these verified identities:

- bundle version: `0.7.0-test`;
- declared runtime files: 13;
- ZIP entries including both manifest files: 15;
- ZIP SHA-256:
  `0BA56B60FD8F5A229346D565FEA33F58F57F9239FE541F216C07E79E56D7BF20`;
- manifest SHA-256:
  `39C06473793C92FB281D509C3468493E9562CF9CDB74F27DBEA4D249C4676ACB`;
- manifest digest, declared file hashes, extracted allowlist, and relative-path
  validation: passed;
- live `.env` in the archive: absent.

An early archive check falsely reported path escapes because its verifier
handled Windows path normalization incorrectly. The corrected verifier
reported zero invalid relative paths, zero content mismatches, and zero
allowlist mismatches. Treat the corrected result as authoritative; the first
failure was tooling error, not bundle corruption.

## Original local 0.8.0 candidate and activated target facade

Local `0.8.0-test` extends the safe input boundary to nine ordered
observations: `live`, `ready`, `system_scheduler`, `scheduler_detail`,
`system_runtime`, `system_database`, `system_proxy`,
`system_smartfuelpass`, and `external_web`. The first eight use dedicated
authenticated GET-only projections. The external observation is executed
directly from the supervision center, sends no facade bearer, follows no
redirect, reads no body, requires HTTPS outside loopback tests, and persists
neither URL nor headers.

Environment contract 2 adds the configured public root URL. Observation
contract 4 / endpoint set 3 adds a bounded clock-skew diagnostic where the
source supplies time. Audit contract 7 reads retained contracts 2/set 1 and
3/set 2 alongside contract 4/set 3 without rewriting history. With the current
serial timeout/retry values, the nine-endpoint worst-case timeout budget is
94.5 seconds; a complete outage may lengthen the nominal cadence but cannot
overlap cycles or create a second writer.

The candidate archive has 13 declared runtime files and 15 entries. Its ZIP
SHA-256 is
`29BEE64FEE267F1E74BE1AA89CA621E2930262E16C0C662580DA5D2B7EBF8EF0`;
manifest SHA-256 is
`282DFDDA162B4D4CB2C3CE656066D47E2B03504F1434277659E20CBCBB173ADF`.
The targeted local matrix, including repository-root hygiene, passed with 186
tests. The monitored workstation then restarted through its supported full
startup boundary on 2026-08-06 and activated the eight-route facade. This
bundle is now superseded by the 0.8.1 rolling-upgrade correction documented
below and must not be deployed.

### 2026-08-06 monitored-workstation activation proof

- Windows booted at `13:40:32 +02:00`; `API_dashboard_caddy` ran at
  `13:40:43 +02:00` with result 0.
- FastAPI liveness/readiness, Streamlit health, and Caddy admin returned HTTP
  200. Expected listeners 80/443/2019/8000/8001 and tailnet-only 9443 were
  present; temporary listeners 8010/8011 were absent.
- Scheduler status was `ok`, its heartbeat was within the 300-second TTL, all
  nine scheduled jobs were OK, and the preceding 24 hours contained zero
  failures. The first postboot `quarter_hour_job` succeeded at
  `13:47:13 +02:00`.
- Tracked and deployed Caddyfile SHA-256 remained equal at
  `08CDF04AFC4F856FEC8DFE4AB2E07A746763B152CA91553E349CCCE8E6D3DF2C`.
  Local hostname/SNI returned dashboard HTTP 200 and HTTP-to-HTTPS redirect
  308. The known on-host public-address hairpin gap remains non-authoritative.
- Every one of the eight monitoring facade paths returned JSON HTTP 401
  without the dedicated identity; none retained the pre-activation 404.
  Direct safe-model validation reported runtime, database, and proxy `ok`.
- SmartFuelPass returned a valid safe schema but payload status `error`. This
  is the known intentionally paused import state after the 2026-07-29
  Cloudflare failure, not a restart regression. Preserve the payload truth;
  observer heartbeat health remains based on transport/schema success, and
  later incident rules must qualify the planned condition rather than rewrite
  it.
- The postboot API log contained at least 16 complete ordered remote 0.7
  cycles (`live`, `ready`, `system_scheduler`, `system_runtime`) with HTTP 200,
  proving target and private-path recovery without restarting the observer.
- The dedicated bearer exists only on the supervision center. Final
  authenticated HTTP/schema proof for the four new routes and audit-v7 state
  proof therefore belong to the controlled remote 0.8 migration gate.

### 2026-08-06 post-activation 0.7 audit and 0.8.1 correction

- The safe concurrent remote configuration check passed with environment
  contract 1, endpoint set 2/count 4, and test mode. Audit v6 retained 1,389
  complete cycles: 1,313 healthy, 71 partial failure, and 5 unreachable.
- Lifecycle remained structurally healthy: nine starts/eight stops/one current
  open run, zero unclean and abandoned runs, and unchanged historical
  concurrent-start and process-run-reentry counts of one each.
- The latest heartbeat was degraded with two failures. Append-only transport
  totals now included 68 schema errors, and eight final non-retryable outcomes
  followed earlier attempts, so the aggregate historical retry flag was false.
- Exact comparison against the deployed 0.7 ZIP identified the deterministic
  cause. Its System Runtime client requires the former full nested schema,
  including transient `detail`, labels, local addresses, next-run time, and
  process IDs. The activated 0.8 target route correctly removes those fields
  before network serialization. HTTP 200 therefore became a 0.7 client
  `schema_error`; this is not a SmartFuelPass finding and not evidence that the
  safe projection should be weakened.
- `0.8.1-test` provides a two-phase bridge without restoring unsafe fields or
  rewriting state. With the exact existing env-v1 file it uses four keys and
  writes contract 3/set 2 against the new safe schema. After a healthy bridge
  cycle and current-run audit pass, env v2 adds the external URL and exact nine
  keys for contract 4/set 3.
- Audit v7 retains the global historical result and additionally reports
  sanitized `observations.current_run` attempt/retry evidence. The bridge and
  final nine-key runs must have valid current-run bounds/retry facts even when
  immutable global history remains qualified by the 0.7 schema transition.
- Focused monitoring/facade/system-health/scheduler/runtime/hygiene tests
  passed 192/192 and modified Python modules compiled. The deterministic
  13-file/15-entry `0.8.1-test` ZIP has SHA-256
  `D17A88A10814D4CC645AD731B5C2B56B3B662E0662547ED9FCEA3443EF876884`;
  manifest SHA-256 is
  `18A3E477E724EEA61F3EFDCBE303BEBE4DC298A4D646D37FE643D6CD9C49CBB1`.
  All declared content hashes and the entry allowlist passed, a second build
  was byte-identical, and no real `.env` is present.
- Do not deploy the superseded 0.8.0 ZIP. Keep the current 0.7 task running
  until a separately controlled stop begins the exact 0.8.1 two-phase
  migration.
- On 2026-08-07 a ZIP hash matching the exact reviewed SHA-256 was reported:
  `D17A88A10814D4CC645AD731B5C2B56B3B662E0662547ED9FCEA3443EF876884`.
  A subsequent read-only task inventory in the same console found no
  `MonitoringAgentTest` task, so the console was not proved to be the actual
  supervision center and the hash does not yet prove remote transfer. Repeat
  both checks together on the station that produced the audit-v6 state. The
  stop method itself remains an explicit lifecycle gate:
  `Stop-ScheduledTask` must
  not be treated as a controlled Python shutdown because Task Scheduler can
  terminate the process before the append-only stop event is written. Do not
  stop, replace, restart, or reconfigure the task until that method, or a
  deliberately qualified planned termination, is separately approved.
- On 2026-08-07 the user approved the latter test-stage option: continuity is
  not required for this cutover, so the exact 0.7 process tree may be hard
  stopped if its original Ctrl+C console is unavailable. Preserve all state
  and qualify the resulting abandoned/unclean run as planned migration
  evidence. Manual `.env` transfer is also approved, without printing its
  contents and with an unchanged env-v1 bridge before the env-v2 phase.
- The remote ZIP was then found and reverified at the supervision station.
  The only two Python processes formed the expected Session-0
  launcher/interpreter tree. An elevated fail-closed command validated the
  preserved old `.env`, ZIP hash, both process identities, and parent/child
  relation before stopping them. The exact targets and all Python processes
  were absent afterward; env v1 remained present. No task was created and no
  state was deleted or rewritten.

## Runtime configuration and access

The local 0.7 project has its own CPython 3.14 virtual environment. Its ignored,
ACL-restricted `.env` retained the existing credential, state path, and every
non-endpoint value from the 0.6 runtime. Only the endpoint set changed from
three to four ordered keys:

1. `live`;
2. `ready`;
3. `system_scheduler`;
4. `system_runtime`.

Configuration validation reports environment contract 1, test mode, and four
endpoints. The first controlled 0.7 cycle returned four successful transport
observations. Audit contract 6 then verified mixed retained history:

- legacy observation contract 2 / endpoint set 1 remains append-only;
- current observation contract 3 / endpoint set 2 is used for every new
  four-endpoint cycle;
- per-set endpoint order, cycle grouping, timeout budgets, and retry bounds are
  evaluated against the contract carried by each observation;
- no history was rewritten during migration.

The monitored workstation exposes the new authenticated GET-only System
Runtime projection through the private tailnet facade. Remote verification
returned HTTP 200, the expected schema, runtime status `ok`, five expected
listeners with zero non-OK listeners, and no temporary listener. The facade
continues to reject unauthenticated access, and the agent receives no command,
database, filesystem, or manual-job capability.

Before task registration, access checks established that `SYSTEM` can read and
execute the project and interpreter, read `.env`, and modify the external
agent-owned state directory. State ACL inheritance was corrected explicitly;
five existing state objects were verified with `SYSTEM` Modify permission.
No secret value or state path is recorded here.

## Scheduled Task contract

The approved task has this exact semantic contract:

- name `MonitoringAgentTest`;
- principal `SYSTEM`, service-account logon, highest run level;
- one `AtStartup` trigger;
- exact project-local `.venv\Scripts\python.exe` action;
- only the quoted project-local `run_monitoring_agent.py` path as arguments;
- explicit project working directory;
- `StartWhenAvailable` enabled;
- multiple instances set to `IgnoreNew`;
- restart on failure once per minute, with restart count 999;
- execution time limit disabled;
- allowed to start on batteries and not stopped when switching to batteries;
- no bearer, credential, URL, token, or `.env` value on the command line.

The checked-in helper is unsigned and the supervision center's effective
PowerShell execution policy is `Restricted`. The policy was not changed or
bypassed. Registration used the reviewed equivalent commands interactively in
an elevated PowerShell. A first non-elevated attempt failed with
`PermissionDenied` and created no task; the elevated retry registered the
contract successfully without starting it.

## Restart and single-writer proof

The foreground 0.7 writer was stopped with Ctrl+C before the supervision
restart. The pre-reboot audit showed eight starts, eight controlled stops, no
open run, no unclean restart, and a healthy four-observation heartbeat. The
task was `Ready`, the scheduler service was running, and no agent process
remained.

The supervision center then booted on 2026-08-06 at `08:11:42 +02:00`. The
task was launched at `08:12:12` and reached the running observer lifecycle at
approximately `08:14:02`. The roughly 110-second cold-start interval means an
immediate postboot state audit can still show the prior closed run. Operational
checks must allow bounded startup time and require a fresh postboot lifecycle
or observation before declaring success. This observed delay is evidence for
future threshold design, not yet an incident threshold.

Windows exposes two Python processes for the running virtual-environment
invocation. Sanitized process-tree verification proved they are one
parent-child launcher/interpreter pair, both owned by `SYSTEM`, in continuous
mode. They represent one logical agent, not two writers. A raw process count of
two must therefore not be used as duplicate-instance evidence; verify logical
roots, task state, lifecycle, and the OS writer lock together.

The final postrestart proof found:

- task state `Running` and current task result `267009` (`0x00041301`, running);
- one logical `SYSTEM` agent;
- audit lifecycle: nine starts, eight stops, one current open run;
- zero unclean and zero abandoned runs;
- retained historical concurrent-start count 1 and process-run reentry count 1,
  unchanged by the 0.7 deployment or restart;
- 1,162 complete cycles total;
- cycle outcomes: 1,155 healthy, 3 partial failure, 4 unreachable;
- transport outcomes: 3,634 success, 12 connection error, 6 timeout;
- latest heartbeat healthy with four observations and zero transport failures;
- cycle sequence, endpoint sequence, retry, attempt-bound, and configured
  timing checks valid.

Compared with the last clean pre-reboot audit at 1,036 cycles, the scheduled
runtime added 126 complete four-endpoint cycles: 121 healthy, two partial
failure, and three unreachable. Those cycles added 490 successes, 12
connection errors, and two timeouts. The last observed degraded heartbeat
recovered on a later complete cycle without restarting the agent.

`single_writer_observation_history_valid=false` and
`single_writer_history_valid=false` remain expected because immutable 0.6.1
history contains one pre-lock `A-B-A-C` process interleaving. The current 0.7
runtime did not add another interleaving, concurrent start, run reentry,
unclean restart, or abandoned run. Reporting must present the old finding as a
historical evidence qualification, not as a current outage.

The persistent one-byte `observer_writer.lock` file can retain its old
modification time. Exclusivity is held by the operating-system byte-range lock,
not by file freshness or PID text. Do not delete or rewrite the lock file as a
health check.

## Safe reporting input boundary

The reporting layer may consume only versioned, normalized, agent-owned facts
that have already crossed the strict endpoint projections. Development and
tests in this repository must use synthetic fixtures or sanitized aggregates;
do not copy remote `.env`, JSONL state, heartbeat files, lifecycle records,
paths, identifiers, timestamps tied to identities, bearer values, or raw
endpoint bodies into Git.

The current runtime provides these usable inputs:

- normalized observations with transport outcome, HTTP/schema classification,
  approved endpoint projection, attempt count, run/cycle identity, and endpoint
  set version;
- an atomic latest observer heartbeat with self-health and latest-cycle
  consistency facts;
- append-only process lifecycle starts and controlled stops;
- aggregate audit v6 facts for outcomes, transitions, retries, ordering,
  cadence, cross-run intervals, lifecycle, mixed contract history, and known
  evidence gaps;
- System Runtime boot/startup-task/listener facts sufficient for safe restart
  correlation.

The reporting layer must not infer more than these contracts prove:

- transport loss means the target or path is unreachable; it does not prove
  scheduler failure;
- an unhealthy target payload with successful transport is distinct from
  observer self-health degradation;
- `heartbeat_transition_history_not_persisted` remains an explicit gap;
- the current audit is aggregate evidence, not an incident store;
- no bounded retention or report-store policy has been selected;
- detailed Scheduler Health and System Database projections are not yet part
  of the remote four-endpoint cycle;
- the public-hostname hairpin path from the monitored workstation remains
  unverified and is not the agent's private tailnet route;
- the supervision center still has no independent outside observer watching
  loss of the center itself.

## Next implementation boundary

First finish roadmap item 1. Activate the eight facade routes through the
monitored workstation's supported full restart, verify their safe schemas,
then migrate the supervision center to 0.8 under its single-writer contract.
Require `--check-config` with nine endpoints, one complete successful
nine-observation cycle, a matching heartbeat, and an audit-v7 mixed-history
pass. Until then, the 0.7 four-endpoint facts above remain the verified runtime
boundary.

After that proof, continue with parent-plan steps 5-8 and 10-12, not with an
email or ticket integration:

1. define versioned deterministic rules and confirmation/recovery thresholds
   over the verified normalized nine-endpoint facts;
2. define stable incident identity, transitions, deduplication, reopening, and
   bounded agent-owned incident/report persistence;
3. implement the deterministic evaluator with clock-controlled synthetic
   tests;
4. implement a pure local report model and renderer that keeps facts,
   hypotheses, confidence, gaps, and prohibited actions separate;
5. compare local test reports with legacy scheduler alerts during the shadow
   pilot;
6. add interpretation or programmer-task drafting only after the deterministic
   incident facts are stable;
7. request separate approval for any external delivery channel or production
   alert replacement.

While the Scheduled Task is running, do not launch foreground continuous mode
or `--once` against the same state. `--check-config` and `--audit-state` remain
the safe concurrent operator commands. Current legacy alerts remain
authoritative throughout reporting-layer development.
