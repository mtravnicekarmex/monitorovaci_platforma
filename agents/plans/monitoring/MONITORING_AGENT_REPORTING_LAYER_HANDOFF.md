# Monitoring Agent Reporting Layer Handoff

Prepared: 2026-08-06

Last updated: 2026-08-17

Status: remote 0.8.1 continuous observer is running healthy on the supervision
center; roadmap items 1-7 are complete. Incident rules, bounded
incident/outbox state, bounded observation retention, pure report/prompt
rendering, the disabled-by-default test-only Outlook delivery adapter, and a
pure draft-only interpretation contract are present locally as candidate
source. One explicitly confirmed synthetic test email was sent successfully
from the supervision station on 2026-08-14. The 2026-08-17 item-7 shadow pilot
was closed by a healthy no-event reviewed comparison plus a file-only
synthetic comparison mechanics proof. Automatic/production delivery, real
provider execution, programmer-agent execution, remediation, process control,
and legacy-alert replacement are not implemented or authorized.

Parent plan: `SCHEDULER_MONITORING_AGENT_PLAN.md`

Runtime design: `SCHEDULER_MONITORING_AGENT_REMOTE_RUNTIME_DESIGN.md`

Approved implementation checklist: `MONITORING_AGENT_IMPLEMENTATION_ROADMAP.md`

## Purpose

This handoff fixes the verified input boundary for the next monitoring-agent
phase. It records what is actually running on the separate supervision center,
which evidence is trustworthy, which historical findings must not be
misinterpreted, and what the reporting layer may consume.

It does not authorize additional external delivery, application writes,
incident auto-remediation, process control, manual jobs, or replacement of the
current scheduler alerts.

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
- the deployed 0.8.1 audit is aggregate runtime evidence, not an activated
  automatic incident sender;
- the active candidate source now defines bounded observation retention,
  `incident_state.json`, delivery-intent outbox state, pure report/prompt
  rendering, a disabled-by-default test-only delivery adapter, and pure
  draft-only interpretation over confirmed incidents; delivery and
  interpretation are not wired into the polling loop;
- detailed Scheduler Health, System Database, Proxy, SmartFuelPass, and
  external-web observations are part of the remote nine-endpoint cycle;
- the public-hostname hairpin path from the monitored workstation remains
  unverified and is not the agent's private tailnet route;
- the supervision center still has no independent outside observer watching
  loss of the center itself.

## Next implementation boundary

Roadmap items 1-6 are complete as of 2026-08-14. Item 5 added a
disabled-by-default test-only Outlook/SMTP adapter that consumes the outbox
only when explicitly enabled, reads the controlled test recipient from
`DELIVERY_TEST_RECIPIENT`, derives the in-memory recipient allowlist from that
same value, returns sanitized results, and stores no credentials, recipients,
sender, or message body in agent state. The operator CLI copies the existing
alarm SMTP method through the standalone monitoring-agent
`send_email_outlook()` function: Office365 STARTTLS on port 587 using
`O_EMAIL` and `O_APP` from `.env` for login/default sender, with `EMAIL`/`APP`
accepted only as compatibility fallback. Delivery-test recipient variables use
`DELIVERY_TEST_*`, not the reserved `MONITORING_AGENT_` runtime prefix, and no
separate recipient-hash configuration is required. The polling runtime
validates only `MONITORING_AGENT_*` keys from the env file, so these
non-prefixed delivery keys may live in the same local `.env` without changing
the observer runtime contract.

For test iterations after 2026-08-14, the user selected direct Git pulls from
`https://github.com/mtravnicekarmex/monitoring-agent-0.8.1.git` instead of a
new ZIP/version for every change. Commit
`5cfc5916d3e83cdcc1eecd34f3f2719d62ec351c` on `master` contains the local
item 2-5 candidate source. Commit
`86ee42b058c74675976904c1e51a2f3677c5f138` on `master` adds item 6
draft/fallback interpretation source and regenerated manifest files. Treat
the pulled commit hash as the active test-checkout identity when the
supervision station pulls it; the original 0.8.1 ZIP identity remains
historical release evidence only. The supervision station pulled
`86ee42b058c74675976904c1e51a2f3677c5f138`; `--check-config` stayed valid
with nine endpoints, env contract 2, and test mode, and audit-v7 retained a
healthy nine-observation latest heartbeat with zero latest transport failures,
valid ordering/retry/timing, clean open lifecycle, and no new lifecycle or
writer anomalies.

Controlled item-5 proof on 2026-08-14: the supervision station verified this
commit, loaded the configured recipient only as a hash, prepared an isolated
synthetic outbox/report, dry-ran one due item, and sent one explicitly
confirmed synthetic email through `send-due`. The sanitized result was
`status="sent"`, `action="opened"`, `attempt_count=1`, and no error code.
A follow-up dry-run for the same `idempotency_key` returned `due_count=0`,
proving the synthetic item was no longer pending for re-send. This proof does
not enable automatic delivery or production recipients.

Item 6 adds pure draft-only interpretation over confirmed incidents. It uses
an in-memory `InterpretationPolicy` with provider/model names, timeout,
prompt/output bounds, item-count bounds, and cost ceiling, but adds no `.env`
keys, no provider credentials, no network client, no polling-loop integration,
and no state writes. Interpretation is skipped for candidate-only evidence and
falls back to the deterministic report when disabled, unconfigured, failed, or
unsafe. Permission-style flags for network, mutation, process control,
delivery, and alert suppression must remain false.

Item 7 source preflight added
`monitoring_agent/shadow_pilot.py`: a pure shadow-only comparison contract for
supplied sanitized monitoring-agent events and supplied sanitized legacy-alert
events over one reviewed period. It reports matched detections, confirmation
delay, recoveries, duplicate counts/rates, false positives, false negatives,
agent/legacy-only recoveries, and blind spots, and renders a bounded redacted
operator summary. It does not read `.env`, inspect databases, poll endpoints,
call interpretation providers, send email, mutate state, control processes,
or suppress/replace legacy alerts. The standalone GitHub test repository was
pushed on 2026-08-14 as commit
`3e7b94e9045527a1254b10066a3a34493577f025`
(`Add shadow pilot comparison contract`); the regenerated standalone
`manifest.sha256` is
`80f0539d3a4de8410e137664cc7122cdc47b8baa4b7190d323d3eea9b3ca5155`
with 20 declared runtime files. The supervision station then pulled and
audited this commit: `--check-config` stayed valid with nine endpoints, env
contract 2, and test mode; audit-v7 reported 323 complete cycles, latest
heartbeat `healthy`, nine latest observations, zero latest transport
failures, valid ordering/retry/timing, clean open lifecycle, and no new
lifecycle or writer anomalies. This is historical runtime non-regression
proof for the source preflight. Item 7 was completed later on 2026-08-17 by
the reviewed no-event baseline and synthetic file-comparison proof recorded
below.

The next later gates remain separate:

1. collect additional current-alert comparison evidence before any later
   replacement decision;
2. request separate approval for any real interpretation provider execution;
3. request separate approval for any further external delivery, production
   recipient, programmer-agent execution, or production alert replacement.

While the Scheduled Task is running, do not launch foreground continuous mode
or `--once` against the same state. `--check-config` and `--audit-state` remain
the safe concurrent operator commands. Current legacy alerts remain
authoritative throughout reporting-layer development.

## 2026-08-14 stop point, superseded 2026-08-17

At the 2026-08-14 stop point, the correct next work was roadmap item 7:
the comparison code existed and the pulled checkout was healthy, but the
actual shadow pilot still needed a reviewed operating period and sanitized
legacy-alert event input. The then-verified remote checkout was
`3e7b94e9045527a1254b10066a3a34493577f025`; the last audit-v7 proof reported
323 complete cycles, latest heartbeat `healthy`, nine latest observations,
zero latest transport failures, and no lifecycle/writer anomalies.

This stop point was superseded on 2026-08-17. Item 7 now has a written
comparison covering incident detection, confirmation delay, recoveries,
duplicate rate, false positives, false negatives, and blind spots. That
comparison supports closing the item-7 mechanics gate only; it does not
replace, disable, reroute, downgrade, or suppress any legacy alert.

## 2026-08-17 runtime shadow source update and remote proof

Local source now includes runtime shadow incident persistence:
`monitoring_agent/runtime_shadow.py` is called by the polling loop after each
completed observation cycle. It evaluates the current cycle against previous
persisted incident states, writes bounded `incident_state.json`, and emits a
sanitized `shadow_incidents` summary in each `observation_cycle` event.
`--audit-state` is now audit contract 8 and includes aggregate
`shadow_incidents` counts. This adds no `.env` variable and does not enable
delivery, provider execution, remediation, process control, or legacy-alert
replacement. Local verification passed with `91 passed` for targeted
runtime-shadow/agent tests and `169 passed` for the broader monitoring-agent
matrix.

The standalone Git repository was pushed on 2026-08-17 as commit
`207fc1d38d066cdc642dc86bc0cc0b2b6c817cfc`
(`Wire shadow incident persistence`). The regenerated Git manifest keeps
`bundle_version="0.8.1-test-git"`, declares 21 runtime files including
`monitoring_agent/runtime_shadow.py`, and has manifest SHA-256
`4011bb7de330b30371199123dca41aabaaddecd267293dadf990c91f57445287`.

This exact commit was not the final remote proof because its activation found
the env-v2 compatibility bug described below. Follow-up commit
`e23f5f893d76951995a8b6df833e60aadb96a858` provided the remote-proved runtime
shadow source.

Remote activation finding 2026-08-17: after pulling
`207fc1d38d066cdc642dc86bc0cc0b2b6c817cfc`, `--check-config` passed with env
contract 2 and nine endpoints, but the Scheduled Task exited with
`LastTaskResult=1`. Foreground `--once` exposed the cause:
`client setup error: external web URL is required by the endpoint set`.
`RuntimeSettings.load()` accepted the env-v2 key set but loaded
`MONITORING_AGENT_EXTERNAL_WEB_URL` only for env v3. This is a source bug, not
a missing remote `.env` variable. Fix before retry: env v2 and env v3 must
both read/validate `MONITORING_AGENT_EXTERNAL_WEB_URL`.

Fix pushed 2026-08-17: standalone commit
`e23f5f893d76951995a8b6df833e60aadb96a858`
(`Load external web URL for env v2`) changes `RuntimeSettings.load()` to read
`MONITORING_AGENT_EXTERNAL_WEB_URL` whenever that key belongs to the accepted
env contract, including env v2. The Git manifest still declares 21 runtime
files and has SHA-256
`b15c3d6288352c051a30e5693ea710b19b826d7c62bd6e803be0b79163e7d113`.
Local targeted env-v2/runner tests passed with `3 passed`; the broader
monitoring-agent matrix passed with `169 passed`.

Remote proof 2026-08-17: the supervision station pulled
`e23f5f893d76951995a8b6df833e60aadb96a858`; `--check-config` returned env
contract 2, nine endpoints, and test mode. With the Scheduled Task stopped,
foreground `--once` completed one nine-observation cycle with transport
status `success` and wrote `incident_state.json`:
`shadow_incidents.present=true`, `mode="shadow_only"`,
`delivery_enabled=false`, `state_count=0`, and `outbox_count=0`. After
`MonitoringAgentTest` was started again, the task was `Running`; audit-v8
reported latest heartbeat `healthy`, nine latest observations, zero latest
transport failures, `shadow_incidents.present=true`, and updated shadow state
at `2026-08-17T07:00:53.832229+00:00`. The retained
`unclean_restart_count=2`, `start_while_prior_run_open_count=2`,
`abandoned_unclosed_run_count=1`, and `cycle_sequence_valid=false` are the
planned activation/restart/foreground-once artifacts from replacing the
previous long-running process, not evidence that current shadow persistence is
unhealthy. Current legacy alerts remain authoritative; delivery remains
disabled.

## 2026-08-17 file-based comparison CLI remote proof

`monitoring_agent/shadow_pilot_cli.py` now provides read-only operator entry
points for item 7. It can export comparable monitoring-agent events from an
explicit `incident_state.json` and compare them with supplied sanitized
`legacy_alert` event JSON for a reviewed start-inclusive/end-exclusive
period. Outputs are only operator-requested JSON/Markdown comparison files.

The CLI does not read `.env`, inspect production DBs or mailboxes, poll
endpoints, send email, claim outbox items, call providers, mutate state,
control processes, remediate, or suppress/replace legacy alerts. The initial
structured legacy source is the existing database-availability event store;
scheduler/runtime email-only evidence still needs a reviewed sanitization
step before it can be used as comparison input.

Standalone Git commit
`3c6502c74d478a7518d3bbc37f7799951bbbaba4`
(`Add shadow pilot file comparison CLI`) was pushed to `master` with a
22-file Git manifest SHA-256
`f10e0392b2e294956f522f62df270859fad7c153ba4dee6a7fbac2fbba760c11`.
Local checks: focused shadow-pilot tests `13 passed`,
`tests/test_monitoring_agent*.py` `159 passed`, Python compileall passed, and
`git diff --check` passed with line-ending warnings only.

The supervision station pulled and verified this commit on 2026-08-17.
`git rev-parse HEAD` matched
`3c6502c74d478a7518d3bbc37f7799951bbbaba4`; `--check-config` returned env
contract 2, nine endpoints, and test mode. Audit-v8 reported latest heartbeat
`healthy`, nine latest observations, zero latest transport failures,
current-run observation count 315, and `shadow_incidents.present=true`,
`mode="shadow_only"`, `delivery_enabled=false`, `state_count=0`,
`outbox_count=0`, updated at `2026-08-17T07:34:19.759021+00:00`. Retained
unclean/restart/sequence findings remain planned activation artifacts from
the earlier stopped process and foreground `--once`.

## 2026-08-17 local legacy DB-availability export helper

`scripts/export_database_availability_shadow_events.py` exports delivered
events from the local
`core/scheduler/data/database_availability.sqlite3` store as sanitized
`legacy_alert` shadow-pilot event JSON. It maps `unavailable` to `alerted`,
`recovered` to `resolved`, and defaults the comparison incident key to
`endpoint:system_database`, so duplicate per-database events are counted by
the shadow-pilot duplicate logic instead of inflating false negatives.

The exporter selects only delivered events by default, does not read `.env`,
does not call the email backend, does not change the SQLite store, and omits
raw `reason` text. Local proof found six delivered historical DB-availability
events in the store: MSSQL unavailable/recovered on 2026-06-13, PostgreSQL
unavailable/recovered on 2026-06-13, and PostgreSQL unavailable/recovered on
2026-07-18. No matching scheduler/runtime alert patterns were found in the
local scheduler logs during the current shadow-runtime period.

Focused verification passed:
`tests/test_database_availability_shadow_export.py`,
`tests/test_monitoring_agent_shadow_pilot_cli.py`, and
`tests/test_monitoring_agent_shadow_pilot.py` returned `15 passed`; Python
compileall passed for the exporter and its test.

## 2026-08-17 no-event baseline comparison

The supervision station ran the file-based comparison workflow for
`2026-08-17T07:00:00+00:00 <= event < 2026-08-17T07:35:00+00:00`. Agent
events were exported from the local `incident_state.json`; the legacy input
was an explicitly empty sanitized `legacy_alert` event JSON file. The
generated report timestamp was `2026-08-17T07:52:10.639549+00:00`.

Result: matched detections 0, agent-only detections/false positives 0,
legacy-only detections/false negatives 0, matched recoveries 0, agent-only
recoveries 0, legacy-only recoveries 0, duplicate events 0/0, and blind spots
0/0/0. This proves the comparison mechanics and safety boundary for a healthy
no-event reviewed period.

## 2026-08-17 synthetic comparison mechanics proof

Because the monitored system was healthy and there was no reason to wait for
or induce a real incident solely to exercise the comparison branches, the
supervision station ran a file-only synthetic comparison for
`2026-08-17T08:00:00+00:00 <= event < 2026-08-17T09:00:00+00:00`. The
generated report timestamp was `2026-08-17T08:07:12.386903+00:00`.

The supplied sanitized streams contained one matched database detection,
one matched database recovery, one agent-only proxy detection, and one
legacy-only scheduler detection. Result: matched detections 1,
agent-only detections/false positives 1, legacy-only detections/false
negatives 1, confirmation delay count 1 with average/min/max 60 seconds and
agent later than legacy, matched recoveries 1, agent-only recoveries 0,
legacy-only recoveries 0, recovery delay count 1 with average/min/max
60 seconds and agent later than legacy, duplicate events 0/0, duplicate rates
0/0, and blind spots 0/0/0.

This completes roadmap item 7 together with the healthy no-event baseline.
Legacy alerts remain authoritative. No production delivery, real provider
execution, programmer-agent execution, remediation, process control, or alert
replacement is approved by this result. The next roadmap work is item 8.

## 2026-08-17 item 8 first local-agent source/local proof

The first local data-bearing agent is
`local_monitoring_agents/database_availability.py`. It stays on the main
workstation beside the scheduler-owned database-availability SQLite store,
opens that store read-only, derives deterministic aggregate state, and writes
only bounded sanitized agent-owned state below the ignored
`.local-monitoring-agent-state/` directory. It uses its own writer lock and
does not require a supervision-center connection to run.

`scripts/run_database_availability_local_agent.py` runs the agent once and
prints only a sanitized aggregate summary. The authenticated monitoring facade
adds `/api/v1/monitoring/health/local-agents/database-availability`, which
reads the local-agent state and exposes only safe aggregate fields:
contract/mode, agent key, checked/state timestamps and ages, service counts,
pending/delivered/recent event counts, service keys, availability booleans,
failed-check counts, and bounded evidence-gap identifiers.

The local agent and facade projection omit raw `reason` text, service labels,
SQLite paths, SQL, credentials, logs, file contents, and raw event rows. They
do not read `.env`, send email, call interpretation providers, mutate
scheduler/application state, control processes, remediate, or replace/suppress
legacy alerts.

Local proof on 2026-08-17: the one-shot runner against the real local store
returned sanitized `status="ok"`, `service_count=2`,
`pending_event_count=0`, `unavailable_service_count=0`, and
`stale_service_count=0`. Focused verification returned `19 passed` for the
local-agent and monitoring-facade tests; compileall passed. Item 8 remains
open until additional local-agent and controlled facade-polling evidence
exists. Do not change the supervision center endpoint set or remote `.env`
for this endpoint without a separate controlled runtime-contract step.

## 2026-08-17 item 8 second local-agent source/local proof

`local_monitoring_agents/scheduler_metrics.py` is the second local
data-bearing agent. It reads the scheduler metrics JSON from the main
workstation in read-only mode, interprets naive scheduler timestamps as
Europe/Prague local time, normalizes raw job `last_status` strings into
bounded classes, and writes only sanitized agent-owned state below
`.local-monitoring-agent-state/`.

`scripts/run_scheduler_metrics_local_agent.py` runs the agent once and prints
only a sanitized aggregate summary. The authenticated monitoring facade adds
`/api/v1/monitoring/health/local-agents/scheduler-metrics`, which exposes only
safe aggregate fields: version/mode/agent key, state and heartbeat timestamps
and ages, scheduler-running boolean, job counts, 24h success/failure counts,
error/degraded job counts, job IDs, normalized job status classes, and failure
rates.

The scheduler-metrics local agent and facade projection omit labels,
descriptions, raw skipped reasons, logs, file paths, raw metrics JSON, raw
event rows, `.env`, credentials, and file contents. They do not send email,
call interpretation providers, mutate scheduler/application state, control
processes, remediate, or replace/suppress legacy alerts.

Local proof on 2026-08-17: the one-shot runner against the real local metrics
store returned `status="degraded"`, `scheduler_running=true`, `job_count=51`,
`success_count_24h=2594`, `failure_count_24h=0`, `error_job_count=2`, and
`degraded_job_count=0`. This is fail-visible evidence of historical
last-error job states while the 24h failure count is zero.

The first local agent also received
`scripts/register_database_availability_local_agent_task.ps1`, an explicit
operator-run Scheduled Task registrar using a limited current-user principal,
`IgnoreNew`, project-root working directory, and a two-minute execution limit.
The helper itself does not start, stop, or unregister tasks. Focused
local-agent/facade/shadow verification returned `40 passed`; compileall
passed.

## 2026-08-17 item 8 first local Scheduled Task runtime proof

The first local agent was registered as
`MonitoringDatabaseAvailabilityLocalAgent` using the reviewed helper. The task
uses the project `.venv` Python executable, the project-root working
directory, a current-user limited principal, `IgnoreNew`,
`StartWhenAvailable`, five-minute repetition, and a two-minute execution
limit.

A manual task start completed with `LastTaskResult=0`. The first automatic
trigger ran at `2026-08-17 13:23:21 +02:00`, completed with
`LastTaskResult=0`, had `NumberOfMissedRuns=0`, and scheduled the next run for
`2026-08-17 13:28:21 +02:00`. The facade aggregate after that scheduled run
was `status="ok"`, `service_count=2`, `pending_event_count=0`,
`unavailable_service_count=0`, and `stale_service_count=0`.

This proves the first local agent's controlled local task execution and local
facade state freshness. Item 8 remains open for scheduler-metrics task/facade
runtime proof or a reviewed shared local runner decision before
item 9/orchestrator design. The supervision-center polling set and remote
`.env` remain unchanged.

## 2026-08-17 item 8 shared local runner proof

The selected item-8 runtime direction is a shared local runner for approved
local agents rather than one Scheduled Task per agent.
`scripts/run_local_monitoring_agents.py` runs DB availability and scheduler
metrics sequentially in deterministic order. Each local agent still keeps its
own source boundary, state file, and writer lock.

The shared runner emits only a sanitized aggregate
`local_monitoring_agents_cycle`. A local agent returning `degraded` or `error`
is monitoring evidence, not a runner failure; the runner exits non-zero only
for execution/schema exceptions.

`scripts/register_local_monitoring_agents_task.ps1` can register the shared
runner as a limited current-user recurring task with `IgnoreNew`, project-root
working directory, and a three-minute execution limit. The registrar was
parsed successfully.

Manual shared-runner proof against real local sources returned overall
`status="degraded"` with DB availability `status="ok"` and scheduler metrics
`status="degraded"`, `scheduler_running=true`, `job_count=51`,
`success_count_24h=2594`, `failure_count_24h=0`, `error_job_count=2`, and
`degraded_job_count=0`. Verification returned `43 passed`; compileall passed.

## 2026-08-17 item 8 shared Scheduled Task migration proof

The controlled migration from the DB-only local task to the shared local task
completed. `MonitoringDatabaseAvailabilityLocalAgent` was stopped/removed and
verified absent. `MonitoringLocalAgents` was registered as the active local
monitoring task with the project `.venv` Python executable, project-root
working directory, current-user limited principal, `IgnoreNew`,
`StartWhenAvailable`, five-minute repetition, and a three-minute execution
limit.

A manual task run completed at `2026-08-17 13:41:50 +02:00` with
`LastTaskResult=0`. The first automatic trigger completed at
`2026-08-17 13:42:32 +02:00` with `LastTaskResult=0`,
`NumberOfMissedRuns=0`, and next run `2026-08-17 13:47:32 +02:00`.

The sanitized facade projections after the automatic trigger had no evidence
gaps. DB availability reported `status="ok"`, `service_count=2`,
`pending_event_count=0`, `unavailable_service_count=0`, and
`stale_service_count=0`. Scheduler metrics reported `status="degraded"`,
`scheduler_running=true`, `job_count=51`, `success_count_24h=2594`,
`failure_count_24h=0`, `error_job_count=2`, and `degraded_job_count=0`.

Roadmap item 8 is complete. The next step is item 9: design the orchestrator
from observed shared needs. The supervision-center polling set and remote
`.env` remain unchanged until a separate runtime-contract step.

## 2026-08-17 item 9 orchestrator accepted-design handoff

`MONITORING_ORCHESTRATOR_DESIGN.md` is the accepted architecture baseline for
roadmap item 9. It is based on the verified remote external monitoring agent,
DB-availability local agent, and scheduler-metrics local agent. The draft
limits orchestrator v1 to read-only correlation on the supervision
workstation over center-owned audit summaries, file-only sanitized snapshots,
and later separately approved GET-only facade reads.

The draft explicitly excludes raw main-workstation data, dynamic discovery,
agent lifecycle control, remediation, delivery, interpretation-provider
execution, remote `.env` changes, polling-set changes, and legacy-alert
replacement. The user reviewed and accepted purpose/scope, evidence baseline,
shared contracts, non-goals, placement/data flow, registry and snapshot
contract, correlation rules, failure isolation, and pilot sequence. Roadmap
item 9 is complete.

The next approved implementation scope is file-only/shadow-only orchestrator
CLI over sanitized sample snapshots. Live polling, scheduling, remote
polling-set changes, `.env` changes, delivery, provider execution,
remediation, process control, and alert replacement remain separate
approvals.

## 2026-08-17 item 9 file-only orchestrator CLI handoff

The approved file-only CLI scope was implemented locally.
`monitoring_agent/orchestrator.py` defines the static registry,
normalized agent snapshots, freshness/status/evidence-gap/count handling,
sanitized payload digests, bounded correlation findings, duplicate-key
fail-closed behavior, `.env` source rejection, and the approved v1
correlation rules.

`monitoring_agent/orchestrator_cli.py` provides
`python -m monitoring_agent.orchestrator_cli run` over a supplied registry and
supplied sanitized source snapshot files. Supported payload kinds are
`agent_snapshot_v1`, `local_agent_facade_v1`, and `remote_agent_audit_v8`.
Missing, stale, invalid, or contract-mismatched source files are isolated to
the affected source with bounded evidence gaps; duplicate agent identities
fail closed before output is produced.

Verification returned `8 passed` for
`tests/test_monitoring_agent_orchestrator.py` and `49 passed` for the focused
orchestrator/shadow/local-agent/facade set.

This source was later extended by
`monitoring_agent/orchestrator_export_cli.py`, which wraps supplied sanitized
remote `--audit-state` JSON with `captured_at` before orchestration. Do not
add live polling, schedule the orchestrator, alter remote `.env` or polling
sets, invoke delivery or providers, control processes, remediate, or replace
alerts without separate approval.

## 2026-08-18 item 9 local-only orchestrator preflight

The local side of the file-only pilot was prepared and run. The shared local
runner refreshed sanitized local state and returned DB availability
`status="ok"` plus scheduler metrics `status="degraded"`,
`failure_count_24h=0`, `error_job_count=2`, and `job_count=51`.

`scripts/export_monitoring_orchestrator_local_inputs.py` exported local facade
aggregate snapshots into
`artifacts/monitoring/orchestrator/2026-08-18-file-only-pilot/`. Running
`python -m monitoring_agent.orchestrator_cli run` over
`orchestrator-registry-local-only.json` produced
`orchestrator-local-preflight.json` and `orchestrator-local-preflight.md`.
The local-only preflight had two fresh sources, no evidence gaps, overall
`status="degraded"`, and correlation
`scheduler_historical_error_states_no_recent_failures`.

This is not the full three-surface pilot. To complete the approved file-only
pilot, supply the current sanitized remote
`run_monitoring_agent.py --audit-state` JSON from the supervision station and
rerun the export helper with `--remote-audit-file`.

## 2026-08-18 item 9 full file-only orchestrator pilot

The supervision station supplied a sanitized audit-v8
`run_monitoring_agent.py --audit-state` JSON. The full file-only registry
consumed three sources: `external_health`, `database_availability`, and
`scheduler_metrics`. The orchestrator wrote
`artifacts/monitoring/orchestrator/2026-08-18-file-only-pilot/orchestrator-full-pilot.json`
and `orchestrator-full-pilot.md`.

Result:

- three fresh sources;
- two `ok` sources and one `degraded` source;
- no unavailable, error, invalid, or stale sources;
- overall `status="degraded"`;
- `external_health status="ok"` with evidence gaps
  `heartbeat_transition_history_not_persisted` and
  `source_timestamp_missing`;
- DB availability `status="ok"` with no evidence gaps;
- scheduler metrics `status="degraded"` with no evidence gaps,
  `failure_count_24h=0`, `error_job_count=2`, and `job_count=51`;
- one correlation:
  `scheduler_historical_error_states_no_recent_failures`.

Remote latest heartbeat was healthy with nine latest observations and zero
latest transport failures. Shadow incidents remained `mode="shadow_only"` and
`delivery_enabled=false`, with two pending outbox intents. The
`source_timestamp_missing` gap is expected for raw `--audit-state` JSON
because that payload has no generated/checked timestamp.

This completes the approved file-only pilot. Live polling, deployment,
scheduling, remote `.env` or polling-set changes, delivery, provider
execution, remediation, process control, and alert replacement remain separate
approvals.

## 2026-08-18 item 9 remote-audit captured timestamp follow-up

`monitoring_agent/orchestrator_export_cli.py` was added with
`python -m monitoring_agent.orchestrator_export_cli wrap-remote-audit`. It
wraps a supplied sanitized `agent_state_audit` JSON object from file or stdin
with a timezone-aware `captured_at` timestamp, rejects `.env` paths and wrong
events, and writes only a copied JSON output. It does not poll endpoints, read
`.env`, send email, mutate state, control tasks, or change runtime
configuration.

The orchestrator remote-audit parser now uses `captured_at` before falling
back to `checked_at` or `generated_at`. The full pilot was rerun with the
wrapped remote audit and wrote
`artifacts/monitoring/orchestrator/2026-08-18-file-only-pilot/orchestrator-full-pilot-captured.json`
and `orchestrator-full-pilot-captured.md`.

Result:

- overall `status="degraded"` remained unchanged;
- `external_health status="ok"` retained only
  `heartbeat_transition_history_not_persisted`;
- `source_timestamp_missing` was removed;
- DB availability remained `status="ok"` with no evidence gaps;
- scheduler metrics remained `status="degraded"` with no evidence gaps;
- the only correlation remained
  `scheduler_historical_error_states_no_recent_failures`.

Verification returned `18 passed` for focused orchestrator/export/helper
tests, `190 passed` for the broader monitoring-agent/local-agent set, Python
compileall passed, and `git diff --check` passed.

## 2026-08-21 standalone Git publication for item 9 wrapper

The supervision station reported `No module named
monitoring_agent.orchestrator_export_cli` because its checkout was still at
the last remote-proved commit
`3c6502c74d478a7518d3bbc37f7799951bbbaba4`. The item-9 wrapper source had
only existed in the local full repository.

Standalone repository
`https://github.com/mtravnicekarmex/monitoring-agent-0.8.1.git` was updated
on `master` to commit `f6583d80a77695b3f4a094337251c6835b389b59`
(`Add orchestrator file-only export CLI`). The commit adds:

- `monitoring_agent/orchestrator.py`;
- `monitoring_agent/orchestrator_cli.py`;
- `monitoring_agent/orchestrator_export_cli.py`;
- updated `monitoring_agent/README.md`;
- regenerated `manifest.json` and `manifest.sha256`.

The Git manifest now declares 25 runtime files and has SHA-256
`37e2967efa4edbf5cfcfdeaa5a9bb8e073ef417fd2499ed058cf7085a8daf61b`.
Temporary standalone verification compiled the package, loaded wrapper help,
wrapped a sample stdin audit with `captured_at`, and verified all
manifest-declared file hashes.

The supervision station verified this pull on 2026-08-21:

- `git rev-parse HEAD` returned
  `f6583d80a77695b3f4a094337251c6835b389b59`;
- `run_monitoring_agent.py --check-config` returned endpoint count 9, env
  contract 2, and mode `test`;
- `monitoring_agent.orchestrator_export_cli wrap-remote-audit` wrote
  `remote-audit.json` with `event="agent_state_audit"`,
  `audit_contract_version=8`, and
  `captured_at="2026-08-21T05:21:19.603716Z"`.

This proves the wrapper/module availability and configuration compatibility
on the supervision station. At that point, a separate long-running
audit/status sample was still required before treating this as a fresh
continuous-runtime health proof.

Follow-up runtime sample on 2026-08-21 closed that immediate gap for the
pulled checkout. After a 180-second wait, `MonitoringAgentTest` was
`Running`; audit-v8 latest heartbeat was `healthy` with nine latest
observations and zero latest transport failures. Endpoint sequence, retry
contract, attempt bounds, timing budget, and single-writer history were valid.
There were no in-progress/incomplete observations, concurrent starts,
run-reentries, overlaps, or process-run transitions in the sample. Retained
lifecycle history still includes `unclean_restart_count=3`,
`start_while_prior_run_open_count=3`, and `abandoned_unclosed_run_count=2`.
Shadow incidents remained `mode="shadow_only"` and `delivery_enabled=false`,
with `active_state_count=1`, `resolved_state_count=2`, `state_count=3`,
`outbox_pending_count=11`, and update time
`2026-08-21T05:28:14.530041+00:00`. The active/pending shadow counts should
be inspected before any delivery or alert-layer work; they do not authorize
mail delivery or legacy-alert replacement.

Sanitized follow-up inspection on 2026-08-21 identified the active incident as
`endpoint:system_scheduler`, opened at
`2026-08-20T00:17:37.512339+02:00`, with
`last_reason="endpoint_payload_status:degraded"`. The user identified the
operational source as the last two days' midnight `daily_job` failure in
`SOFTLINK_save_to_database_all`. Only one pending outbox item belongs to this
incident (`opened`); the rest are older `system_runtime` and
`target_wide_outage` intents. Follow-up source work on 2026-08-21 found the
SOFTLINK failure in the old measurement login flow waiting for visible
`text=Odhlásit` after login submission. The user confirmed changed SOFTLINK
credentials. The local scheduler now pauses `SOFTLINK_save_to_database_all`
and `elektromery_softlink_monitoring_import` from scheduled/manual scheduler
execution; scheduled `daily_job` currently runs only `meteo_sync` through an
independent-step runner that continues after failed independent steps and
raises one aggregate error afterward. Re-add SOFTLINK only after the
measurement fetcher is rebuilt to the robust saved-session/API-validation
pattern used by `SOFTLINK_data_zarizeni.py` and login is verified. Standalone commit
`601a50587c73627835d4860b2212a82a92670f12` was pushed on 2026-08-21 to
collapse unchanged repeated `updated` transition records, document the
steady-state five-minute polling profile (`300` second interval, `30` second
jitter), and regenerate the 25-file Git manifest with SHA-256
`07e08ccd56275a30e0169b863c60aee07241ba2f1c7126fb19989382c2c1a349`. The
supervision station verified the pull on 2026-08-21: valid config, latest
heartbeat `healthy`, zero latest transport failures, a new 310.977-second
scheduled interval inside the 332-second allowed maximum, and no new repeated
unchanged `endpoint:system_scheduler` `updated` transition records after the
restarted 300-second runtime began.

The 2026-08-21 local workstation pre-restart handoff is recorded in
`agents/history/SESSION_NOTES.md`. After that restart, continue remote-agent
work from standalone checkout `601a50587c73627835d4860b2212a82a92670f12`.
Use only safe concurrent checks while `MonitoringAgentTest` is running
(`--check-config` and `--audit-state`). The remote agent remains
`shadow_only`, `delivery_enabled=false`, and not authorized for provider
execution, delivery, remediation, process control, or legacy-alert
replacement. A remaining `endpoint:system_scheduler` active state after the
restart must first be correlated with retained scheduler metrics from the old
SOFTLINK-backed `daily_job` failure.

## 2026-08-21 automatic test-delivery activation handoff

This section supersedes the preceding `601a5058...` / `delivery_enabled=false`
pause point for remote-agent follow-up.

Standalone repository
`https://github.com/mtravnicekarmex/monitoring-agent-0.8.1.git` was updated
on `master` to commit `b6f4e047d59d14d0e34ac61c1a4e270b386f6ae9`
(`Add automatic test delivery gate`). The commit adds
`monitoring_agent/runtime_delivery.py`, wires it after completed observation
cycles, adds the explicit non-`MONITORING_AGENT_`
`DELIVERY_AUTOMATION_ENABLED` gate, refreshes shadow outbox counts after
sent/failed attempts, and documents automatic test-only delivery. The Git
manifest declares 26 files and has SHA-256
`429fac118d8e67bbadd8e1b53b55154953eba0a07aafd1225ec3ed40f68371cc`.

Safety boundary:

- automatic delivery is disabled unless `DELIVERY_AUTOMATION_ENABLED=true`;
- runtime delivery uses only `DELIVERY_TEST_RECIPIENT`;
- at most one due pending outbox item is attempted per completed polling
  cycle;
- report text is sanitized and deterministic from `incident_state.json`;
- no production recipient, provider execution, monitored-target mutation,
  remediation, process control, alert suppression, or legacy-alert replacement
  is authorized.

Before this activation, the supervision station had reviewed the outbox,
manually sent exactly one confirmed test message for
`endpoint:system_scheduler/opened`, and operator-skipped the remaining 14
historical pending intents to `dead_letter` with
`last_error_code="operator_skipped"`. This left the outbox with
`pending=0`, `sent=1`, and `dead_letter=14`.

Local/standalone verification for `b6f4e047...`:

- 19 runtime-delivery/shadow/delivery tests passed;
- 89 main monitoring-agent tests passed;
- compileall passed for changed runtime modules;
- standalone env-v2 `--check-config` passed;
- fake-transport smoke proved one due pending item is marked `sent` without
  SMTP.

The supervision station pulled commit `b6f4e047...`, validated config,
enabled `DELIVERY_AUTOMATION_ENABLED=true` in the local `.env`, restarted
`MonitoringAgentTest`, and ran audit-v8. Latest supplied state on
2026-08-21:

- `MonitoringAgentTest`: `Running`;
- latest heartbeat: `healthy`;
- latest observation count: 9;
- latest transport failures: 0;
- `shadow_incidents.mode="shadow_only"`;
- `shadow_incidents.delivery_enabled=true`;
- `active_state_count=1`;
- `resolved_state_count=2`;
- `outbox_count=15`;
- `outbox_pending_count=0`;
- `outbox_sent_count=1`;
- `outbox_dead_letter_count=14`;
- shadow update time: `2026-08-21T11:08:28.897356+00:00`.

No immediate automatic email is expected because the pending outbox is empty.
The current active state is still the scheduler incident tied to the old
SOFTLINK-backed `daily_job` failure. If that incident later recovers, the
runtime should create a recovery intent and automatically send one recovery
message to the configured test recipient only.

Retained lifecycle counters increased during the controlled stop/start/pull
work (`unclean_restart_count=7`, `start_while_prior_run_open_count=7`,
`abandoned_unclosed_run_count=6`), but the latest audit still had
`concurrent_start_count=0`, `process_run_reentry_count=0`, and
`overlap_count=0`. Treat those retained counters as historical restart
artifacts unless a future audit shows current overlap/reentry evidence.

Next return checks after letting the agent run:

1. Use only safe concurrent commands while the task is running:
   `py -3.14 run_monitoring_agent.py --check-config` and
   `py -3.14 run_monitoring_agent.py --audit-state`.
2. Confirm latest heartbeat stays `healthy`, latest observation count remains
   9, and latest transport failures stay 0.
3. Confirm `shadow_incidents.delivery_enabled=true`.
4. Confirm no unexpected pending buildup. Expected steady state before a new
   incident/recovery is `outbox_pending_count=0`,
   `outbox_sent_count=1`, and `outbox_dead_letter_count=14`.
5. If `outbox_sent_count` increases, inspect which incident/action produced
   the new sent item before treating automatic delivery as fully proved.
