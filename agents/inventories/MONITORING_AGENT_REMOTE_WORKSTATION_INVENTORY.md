# Monitoring Agent Remote Workstation Inventory

Reviewed: 2026-08-06

Status: remote `0.7.0-test` remains the one scheduled `SYSTEM` writer but is
currently degraded by the diagnosed post-target-restart System Runtime schema
transition; local `0.8.1-test` provides the reviewed env-v1 recovery bridge and
later nine-endpoint migration; reporting, retention, credential rotation,
0.8.1 activation, and external delivery pending

Runtime design:
`../plans/monitoring/SCHEDULER_MONITORING_AGENT_REMOTE_RUNTIME_DESIGN.md`

## Confirmed facts

| Property | Reviewed value |
|---|---|
| Role | Agentic supervision center; scheduler observer is its first workload |
| Operating system | Windows 11 Pro |
| Python | CPython 3.14 available |
| Physical network | Same LAN as the monitored workstation |
| Tailscale | Installed on Windows host, joined to the same tailnet, and peer connectivity confirmed |
| Runtime lifecycle | Must be independent from the monitored workstation |
| Production writes | Forbidden |
| External delivery | Disabled during pilot |
| Repository boundary | Full platform clone forbidden; reviewed standalone minimal agent repository permitted |

No hostname, IP address, user name, token, credential, device ID, or other
secret/operational identifier is recorded in this inventory.

## Selected test runtime

For the first Windows pilot:

- use a dedicated Python virtual environment and lock file on the remote
  station;
- install only a reviewed minimal supervision project or its standalone
  repository, never the complete platform repository;
- run the observer non-interactively through its own Windows Scheduled Task;
- keep agent code, configuration, state, reports, logs, lock, and credentials
  in separate ACL-restricted locations;
- do not place the observer in a user startup folder or start it from the
  monitored application's launcher;
- do not grant local administrator, remote shell, database, network-share, or
  monitored-host filesystem permissions.

This runtime is now implemented for the test pilot. The registered task is
`MonitoringAgentTest`; its verified contract and reboot evidence are recorded
under the 2026-08-06 result below. The task is not a production-alert
replacement and has no external delivery or monitored-host mutation access.

## Selected network direction

### Offline and mock testing

Tailscale is not required for:

- unit tests;
- schema and redaction tests;
- deterministic incident-engine tests;
- a disposable fake API test with no production data.

If a same-LAN mock listener is temporarily required, it must:

- serve only synthetic responses;
- bind to a documented temporary port;
- be restricted by Windows Firewall to the test source;
- contain no application credential or production collector;
- be stopped and its firewall exception removed after the test.

Creating that listener or firewall exception requires explicit approval at
the time of the test.

### Production-like remote pilot

Use Tailscale or an equivalent approved encrypted overlay before the real
monitoring facade is exposed to the remote station.

Reasons:

- the monitored workstation already has an operational Tailscale surface
  recorded in project runbooks;
- overlay device identity is stronger than a reassigned LAN IP;
- access can be restricted by source, destination, and TCP port;
- the monitoring listener does not need to be exposed to the ordinary LAN or
  public dashboard origin;
- workstation restart and LAN addressing changes are easier to correlate
  through stable overlay identity.

Tailscale network authorization supplements rather than replaces the
application monitoring identity.

## Proposed Tailscale identity model

After installation and tailnet approval:

- assign a purpose-specific tag or equivalent managed device identity to the
  remote observer station;
- assign a separate target identity to the monitored workstation;
- grant only observer-to-target access on private monitoring HTTPS port
  `9443`;
- do not grant broad subnet, SSH, RDP, SMB, database, Caddy admin, FastAPI
  loopback, or application-management access;
- keep the default posture deny-by-default outside the explicit grant;
- verify denial from an unrelated tailnet device.

The exact tailnet policy and identifiers must be prepared without secret
values and reviewed before application.

Official design references:

- Tailscale Grants:
  https://tailscale.com/docs/features/access-control/grants
- Grants syntax:
  https://tailscale.com/kb/1538/grants-syntax
- Tailscale device identity:
  https://tailscale.com/docs/concepts/tailscale-identity

## Remaining operational inventory

The operating system, Python runtime, shared tailnet, local runtime directory,
`SYSTEM` task identity, project/interpreter/config access, and state Modify ACL
are confirmed. The following remain open:

- who owns and may change the tailnet policy;
- the station can remain powered and connected for the pilot;
- whether the station reboots automatically after updates;
- explicit clock-drift evidence and its reporting threshold;
- bounded state/report retention, backup, and storage-pressure behavior;
- credential rotation execution and rollback;
- an independent observer for loss of the supervision center itself;
- ownership, review workflow, and delivery channels for future reports.

Do not record credential or machine-identity values in repository Markdown.

## Initial verification sequence

1. Verify Windows 11 Pro and CPython 3.14 locally on the remote station.
2. Run offline deterministic tests without network access.
3. Confirm the remote station can join the approved tailnet.
4. Verify a deny-by-default network grant in dry-run/review form.
5. Install/join Tailscale only after approval.
6. Verify agent-to-target reachability on a disposable synthetic listener.
7. Verify unrelated devices and unapproved ports are denied.
8. Remove the disposable listener and confirm the port is closed.
9. Implement the private monitoring facade and application identity.
10. Begin shadow-mode polling with current alerts still authoritative.

## Current result

The remote station satisfies the known operating-system and Python
prerequisites. The user approved installing Tailscale on 2026-07-31 so all
cross-workstation tests can use the production-like encrypted overlay from the
start. The user confirmed the Windows-host installation and shared-tailnet
join on 2026-07-31. The monitored workstation independently reported its
Tailscale service and backend running and its local node online; no device
names, addresses, or IDs were recorded. A Tailscale ping from the remote
station to the monitored workstation returned a pong on 2026-07-31.

The monitored workstation already has a persistent Tailscale Serve HTTPS
listener on port 443 with one root handler proxying to an existing loopback
service. That configuration is outside the monitoring-agent scope and must not
be reset, replaced, or reused for destructive experiments. The monitoring
pilot reserves a separate tailnet-only HTTPS port `9443`.

On 2026-07-31 the reviewed `0.1.0-test` skeleton ZIP was transferred to and
extracted on the remote station without cloning the repository. CPython
3.14.0 loaded the package and its strict example configuration successfully.
The foreground local synthetic proof then passed:

- healthy liveness, readiness, and scheduler responses produced three
  successful normalized observations;
- stopped-scheduler evidence remained a successful transport observation
  with scheduler status `error`, `scheduler_running=false`, and a synthetic
  1,200-second heartbeat age;
- HTTP 503 readiness remained a successful transport observation with
  application status `unavailable`;
- stopping the synthetic server produced three sanitized
  `connection_error` observations;
- the center wrote its own heartbeat and JSONL observations only under the
  bundle-local test state directory.

This proves local package execution and basic state separation. It does not
yet prove remote HTTPS access, facade authentication, Tailscale authorization,
monitored-host shutdown isolation, persistence across center restart, or
Scheduled Task operation.

No task, persistent listener, firewall rule, credential, facade, tailnet
policy, external delivery, or monitored-application state was created or
changed. Tailscale installation and interactive tailnet login were performed
directly by the user on the remote station.

## 2026-08-03 remote HTTPS result

- The monitored workstation retained its existing Tailscale Serve HTTPS
  handler on port 443 and added a persistent tailnet-only HTTPS handler on
  reserved port `9443`, proxying to loopback FastAPI. No broad LAN listener on
  9443 was present.
- The reviewed `0.2.0-test` bundle transferred to the center with ZIP SHA-256
  `3E4C8CEBF5B8B61610373E45003742943F1625D9E494C769B09571AD2BE1838E`.
  Its manifest and all ten declared files verified exactly.
- The center used its separately stored bearer credential and CPython 3.14 to
  complete one foreground cycle over Tailscale HTTPS. Liveness, readiness,
  and system-scheduler observations were HTTP 200, schema-valid, and stored
  with `transport_status=success`; the center also wrote its own heartbeat.
- An unauthenticated remote request was HTTP 401. The monitoring credential
  was HTTP 401 on the human-admin scheduler Health route, an unknown
  monitoring route was HTTP 404, and POST on monitoring liveness was HTTP 405.
- No token value, raw response body, device DNS name, address, or operational
  identifier was recorded in the repository.

This proves the first real cross-workstation transport and authorization
boundary. It does not yet prove credential rotation, target shutdown
isolation, recovery after a new boot, long-running polling, center restart,
retention, or Scheduled Task operation.

## 2026-08-04 polling bundle ready

- The reproducible explicit-allowlist builder created `0.3.0-test` with the
  same ten runtime files plus `manifest.json` and `manifest.sha256`.
- ZIP SHA-256:
  `872F2277B5A03AA00807846E1EFA08F4F792AD29F8F7F65A4A93C745E9F3D57E`.
- Config contract version 2 adds bounded transport-only retries, exponential
  backoff, cycle jitter, and agent-owned `polling`/`healthy`/`degraded`
  heartbeat states. HTTP and schema failures are not retried, and unhealthy
  target evidence does not by itself degrade observer self-health.
- The monitoring/facade/authorization matrix passed with `254 passed`; the
  focused monitoring-agent file passed with `32 passed`. Python compile and
  `git diff --check` passed.
- The bundle has not been transferred or executed on the supervision center.
  Next use the side-by-side, foreground-only procedure in
  `../runbooks/MONITORING_AGENT_FAILURE_ISOLATION_TEST.md`. A target restart,
  credential rotation, and Scheduled Task registration remain separate
  approval gates.

## 2026-08-04 clean PyCharm runtime supersedes 0.3 setup

- At the user's direction, the incomplete 0.3 remote setup is not continued.
  New bundles use one local ignored `.env` rather than session variables, JSON
  configuration, and a separate credential file.
- `0.4.0-test` is a standalone minimal PyCharm project with one operator entry
  point, `run_monitoring_agent.py`. The same entry point is reserved for a
  later separately approved Windows automatic-start mechanism.
- The archive contains exactly 11 allowlisted project/runtime files plus both
  manifests and no real `.env`, credential, state, logs, PyCharm workspace, or
  repository metadata.
- ZIP SHA-256:
  `A6C9DCF82137D252519A05E705CF05D6B1252A4DCA74974037602231088FC767`.
- The focused monitoring-agent suite passed with `44 passed`; the combined
  monitoring/facade/authorization matrix passed with `267 passed`. Python
  compile and `git diff --check` passed.
- Transfer, remote `.env` creation/ACL verification, foreground execution,
  failure isolation, rotation, and automatic startup are not yet complete.

## 2026-08-05 remote foreground loss-and-recovery result

- The clean `0.4.0-test` project is installed and running in foreground test
  mode on the supervision center from an isolated Python environment.
- The minimal project is tracked separately at
  `https://github.com/mtravnicekarmex/monitoring_agent_0.4.0` on `master`
  commit `88158812000c9a91b9a7da1c61045737549a3363`. The repository contains
  the exact 11 manifest-declared runtime files plus manifests, but no real
  `.env`, credential, agent state, virtual environment, or IDE workspace.
  Its current `.gitignore` does not explicitly exclude `.venv/`; add that
  hygiene rule before the next standalone-project commit.
  This does not relax the prohibition on cloning the complete
  `monitorovaci_platforma` repository to the center.
- The foreground observer first recorded healthy three-endpoint cycles, then
  sustained `timeout` cycles while the monitored workstation was unavailable,
  one mixed `success`/`timeout` cycle during recovery, and stable successful
  cycles afterward without restarting the observer.
- The monitored workstation independently passed its 2026-08-05 post-restart
  local checks: startup task result 0, required local services and tailnet-only
  9443 present, monitoring facade protected by HTTP 401 without credentials,
  current scheduler heartbeat, and a successful 08:35 quarter-hour cycle.
- Functional cross-host target-loss and recovery behavior is therefore
  observed. Before closing the runbook, retain a sanitized summary proving
  bounded attempts, `degraded` to `healthy` heartbeat recovery, unchanged
  observer process identity, and serialized cycle timing.
- Credential rotation, bounded retention, center restart/resume, automatic
  startup registration, incident lifecycle, and external delivery remain
  unproved or separately gated.

## 2026-08-05 local 0.4.1 integrity repair ready

- Remote commit `08362ec3ff504986109180bb9d1c89ea096ae19b` safely added
  `.venv/` and changed no runtime code, but retained the preceding manifest.
- Local `0.4.1-test` regenerates the manifest from the exact 95-byte
  `.gitignore`, whose SHA-256 is
  `E4924A6E050E0769863BAB798E453493383CEEB636727CA2210CF24D70C45470`.
- The new ZIP SHA-256 is
  `1EEBB2E946A87E5300A72126AF9A3E358DC6EA121384D2BC8BBA568E3F5DB49B`;
  all 11 declared files, the manifest digest, the no-secret allowlist, and the
  absence of unexpected archive entries verified exactly.
- The combined monitoring-agent, monitoring-facade, and API-authorization
  matrix passed with `267 passed`. The bundle has not been synchronized to or
  run from the standalone repository on the center.

## 2026-08-05 remote audit v2 and local 0.6 restart/resume candidate

- Remote `master` commit `3c171cf49615cf792211f3c992320dade539ccc4`
  exactly synchronizes the `0.4.1-test` README and manifests. The manifest
  digest, hardened `.gitignore`, and absence of a real `.env` verified.
- Remote `0.5.0-test` added a network-free, write-free `--audit-state` command.
  It exposes only aggregate counts and booleans for retry, cycle, timing, and
  latest-heartbeat consistency and does not render paths, credentials,
  instance/PID values, UUIDs, timestamps, endpoint payloads, or raw records.
- Audit v1 processed 405 observations in 135 complete cycles: 90 healthy, 44
  unreachable, and one partial-failure cycle. Retry bounds, endpoint ordering,
  serialized execution, two degraded-to-healthy recoveries, and the final
  healthy heartbeat passed. Two intervals were late; the maximum start-to-start
  interval was 4,545.121 seconds. The user confirmed that the monitored, not
  supervision, station was unavailable during this gap.
- Remote audit v2 found the previous healthy cycle lasted only 0.071 seconds;
  the 4,545.121-second interval exceeded its 67-second allowed bound by
  4,478.121 seconds and was classified as a between-cycle/clock discontinuity.
  Local Windows event times matched a supervision-station shutdown/restart.
- Local `0.6.0-test` observation contract 2 records a fresh process `run_id`,
  cycle ID, and per-run sequence. Append-only lifecycle contract 1 records
  process starts and controlled stops with local PID evidence; audit contract
  3 exposes only aggregate clean/unclean transitions, abandoned runs,
  incomplete cycles, and consistency facts.
- The gated `register_monitoring_agent_task.ps1` helper uses `SYSTEM`,
  `AtStartup`, `StartWhenAvailable`, one-minute retries, `IgnoreNew`, explicit
  interpreter/working directory, and no secret command-line value. It has not
  been executed or registered.
- The 13-file ZIP SHA-256 is
  `41636BDD70612F0A89471CC102B5640C59AADE9DCC63E5426789F39DD77481B3`;
  all manifest/no-secret checks passed and the regression matrix passed with
  `277 passed`.
- A new empty state directory is mandatory. Historical v0.5 heartbeat and PID
  history remains unavailable; 0.6 process history begins prospectively.

## 2026-08-05 remote 0.6 audit and local 0.6.1 correction

- Remote `0.6.0-test` successfully loaded fresh observation contract 2 and
  audit contract 3. Two healthy complete cycles belonged to two process runs;
  lifecycle history consistently reported one abandoned unclosed run and one
  controlled `once_completed` stop.
- The 46.83-second start-to-start interval crossed a `run_id` boundary, but
  audit v3 counted it as `early_start_count=1` and classified it as a
  `scheduled_interval`. This was an audit semantic defect, not an observer
  polling or target-health failure.
- Local `0.6.1-test` raises the audit contract to 4. Scheduled interval,
  overlap, early, late, longest-interval, and largest-late findings now consume
  only consecutive complete cycles within one run. Cross-run timing remains
  visible only through sanitized `cross_run_*` aggregates and a
  `process_run_transition` diagnostic.
- Observation contract 2 and lifecycle contract 1 are unchanged. The existing
  0.6 remote state must be retained for continuity; no new state directory is
  required for the 0.6.0-to-0.6.1 upgrade.
- Reproducible `0.6.1-test` contains 13 declared files. ZIP SHA-256 is
  `18B3A8784D37737365FF276CC4BE9D21E4A4CB844A31642D03642E36392D1EE0`;
  manifest SHA-256 is
  `E1F06F2363DEC0732F8BC7C27A9669DB119788EB590BB1B364392255CF274C38`.
  Manifest digest, declared sizes/hashes, allowlist, and absence of a real
  `.env` passed; focused tests reported `56 passed` and the combined matrix
  `278 passed`.

## 2026-08-05 remote 0.6.1 audit and local 0.6.2 writer lock

- Remote audit v4 processed 72 successful observations in 24 healthy cycles.
  Twenty same-run intervals averaged 62.268 seconds, ranged from 60.111 to
  64.858 seconds, and had zero early, late, or overlap findings. The corrected
  scheduled/cross-run timing boundary passed.
- Three distinct process runs produced three run transitions. Lifecycle later
  contained `once_completed` and `keyboard_interrupt` stops with no abandoned
  run, proving that an older foreground process and a `--once` process had
  overlapped in lifetime even though their HTTP cycles did not overlap.
- Local `0.6.2-test` acquires a non-blocking state-scoped OS file lock before
  lifecycle, heartbeat, observation, or HTTP activity. A second writer exits
  with a sanitized startup error and no runtime/network write. The one-byte
  lock file may persist, while the OS lock is released automatically on normal
  exit or process termination.
- Audit contract 5 adds `process_run_reentry_count`,
  `single_writer_observation_history_valid`, `concurrent_start_count`, and
  lifecycle single-writer validity. It reclassifies the retained history as
  one concurrent start and one run reentry rather than an unclean restart.
  Historical invalidity remains visible after upgrade; new 0.6.2 evidence must
  not add another concurrent start or reentry.
- Existing observation contract 2 and lifecycle contract 1 remain compatible.
  Every 0.6.0/0.6.1 writer must be stopped before starting 0.6.2 because older
  processes do not acquire the new lock.
- Reproducible `0.6.2-test` contains 13 declared files. ZIP SHA-256 is
  `C14A694F650BED6948450BEFA3704BF62B29359537ADE51B67B25DC9A8DC8C5D`;
  manifest SHA-256 is
  `24CD22C4F41ED9A29FB74886EBF73ED8A1539917D34A96628CDE3BAEC99CB1D4`.
  Manifest, exact allowlist, workspace-source equality, and absence of a real
  `.env` passed; focused tests reported `59 passed` and the combined matrix
  `281 passed`.
- Remote foreground verification passed. A concurrent `--once` returned the
  expected sanitized lock error while the first writer continued through four
  more healthy cycles. Lifecycle stayed at 4 starts, 3 stops, and 7 events;
  observation process-run count stayed 4, proving zero rejected-writer state
  writes.
- After Ctrl+C, a clean `--once` acquired the released lock. Final audit v5
  reported 47 healthy cycles, 141 successful observations, 5 starts, 5 stops,
  10 events, zero unclosed/abandoned runs, a matching healthy heartbeat, one
  retained historical run reentry/concurrent start, and zero unclean restarts.
- Foreground single-writer rejection and release is verified. `-WhatIf`
  startup-helper review and `SYSTEM` access checks are next; actual task
  registration and reboot proof remain separately gated.

## 2026-08-05 local 0.7 System Runtime extension

- Local `0.7.0-test` adds the approved authenticated System Runtime facade and
  a strict safe client projection as the fourth endpoint. Observation contract
  3 records endpoint set 2; audit contract 6 continues to read the remote
  contract-2/set-1 three-endpoint history without rewriting it.
- The current `.env` state path and bearer remain reusable, but the endpoint
  key line must be updated from the exact set-1 tuple to the exact set-2 tuple
  before 0.7 startup. The monitored-station facade must be deployed first.
- The 13-file ZIP SHA-256 is
  `0BA56B60FD8F5A229346D565FEA33F58F57F9239FE541F216C07E79E56D7BF20`;
  manifest SHA-256 is
  `39C06473793C92FB281D509C3468493E9562CF9CDB74F27DBEA4D249C4676ACB`.
  Focused tests passed with `62 passed`; the combined matrix passed with
  `286 passed`, and the extended System Health matrix passed with `306 passed`.
- At this 2026-08-05 checkpoint the 0.7 facade and bundle were not deployed.
  No automatic-start registration, API restart, remote state mutation, or
  delivery change had been performed. The 2026-08-06 section below supersedes
  this checkpoint.
- The monitored workstation cannot activate the changed facade through a
  supported API-only restart; its FastAPI/Caddy runtime is created during
  Windows startup. The next target-side action is therefore a full monitored
  workstation restart. Keep the supervision workstation and remote 0.6.2
  observer running so they retain independent outage/recovery evidence.
- After target boot, verify the startup task, listeners, old facade routes, and
  the new authenticated System Runtime route before stopping 0.6.2. Only then
  update the remote project/configuration to 0.7 while reusing its current
  state. At this checkpoint the restart and remote upgrade had not occurred;
  both are completed in the dated result below.

## 2026-08-06 remote 0.7 deployment and scheduled restart result

### Facade and bundle activation

- The monitored workstation completed its supported full restart and loaded
  the new authenticated System Runtime facade. A safe remote check returned
  HTTP 200, valid schema, runtime status `ok`, five expected listeners with
  zero non-OK listeners, and zero temporary listeners.
- The old foreground 0.6.2 writer closed normally before agent migration. Its
  final audit had equal start/stop counts, no open or unclean run, and unchanged
  historical overlap facts.
- `monitoring-agent-0.7.0-test.zip` matched SHA-256
  `0BA56B60FD8F5A229346D565FEA33F58F57F9239FE541F216C07E79E56D7BF20`.
  Its manifest matched SHA-256
  `39C06473793C92FB281D509C3468493E9562CF9CDB74F27DBEA4D249C4676ACB`.
  Corrected extracted verification found all 13 declared files, both manifest
  entries, no invalid relative path, no content/allowlist mismatch, and no real
  `.env`.
- The first ZIP verification failure was caused by an incorrect Windows path
  containment expression in the operator-side verifier. It did not indicate a
  hash or content failure. The corrected extracted result is authoritative.

### Configuration and ACL migration

- A failed first migration attempted to copy privileged ACL metadata and
  returned `PrivilegeNotHeldException`; rollback left no target `.env`.
- The corrected migration created the target `.env`, preserved the exact key
  set, every non-endpoint value, the existing bearer credential, and resolved
  state path, changed only the endpoint set from three to four keys, and
  restricted access to the current identity plus `SYSTEM`.
- The current ordered endpoint set is `live`, `ready`, `system_scheduler`, and
  `system_runtime`. `--check-config` returned environment contract 1, test mode,
  and endpoint count 4. A controlled `--once` produced four successful
  observations.
- Static `SYSTEM` checks passed for project read/execute, `.env` read, and
  interpreter read/execute. State Modify initially failed. The corrected
  `SYSTEM:(OI)(CI)M` ACL was applied to the state directory and descendants;
  five existing state objects were checked and none lacked Modify access.

### Scheduled Task registration

- A project-local CPython 3.14 `.venv` was created and independently passed
  `--check-config`.
- The checked-in PowerShell helper is unsigned while the center's effective
  execution policy is `Restricted`. It could not execute, and no policy scope
  was changed or bypassed. Equivalent reviewed commands were used
  interactively instead.
- The first inline registration ran from a non-elevated shell, returned CIM
  `PermissionDenied`, and left the task absent. The elevated retry succeeded
  and left the task `Ready` without starting it.
- The registered task is named `MonitoringAgentTest`. It uses one `AtStartup`
  trigger; principal `SYSTEM`, service-account logon, and highest run level;
  the exact project-local `.venv` interpreter, quoted runner, and working
  directory; `StartWhenAvailable`; `IgnoreNew`; one-minute failure restart with
  count 999; no execution time limit; and battery-safe settings. The action
  includes no token, credential, bearer, URL, or `.env` value.

### Supervision-center reboot proof

- Before reboot, the foreground process ended with Ctrl+C. Audit v6 showed
  eight starts, eight controlled stops, no open/unclean/abandoned run, and a
  healthy four-observation heartbeat. The task was `Ready`, the Task Scheduler
  service was running, and no foreground agent remained.
- Windows boot time was `2026-08-06 08:11:42 +02:00`; the task started at
  `08:12:12`. The venv launcher appeared at `08:12:21` and its interpreter
  child at `08:12:30`. Both were owned by `SYSTEM` and used continuous mode.
  They form one logical agent process tree.
- The lifecycle file first changed at approximately `08:14:02`, roughly 110
  seconds after task launch. The initial 75-second postboot audit therefore
  still showed the prior closed run even though the task was running. Later
  observations and heartbeat state advanced normally. Postboot checks must
  require fresh state and allow bounded cold-start time.
- Task state remained `Running`; last-result decimal `267009` is the Windows
  running status. One logical agent root, one current lifecycle run, and
  `SYSTEM` ownership were confirmed without retaining PIDs or command lines.
- Final audit v6 contained 1,162 complete cycles: 1,155 healthy, 3 partial
  failure, and 4 unreachable. Transport totals were 3,634 success, 12
  connection error, and 6 timeout. The current heartbeat recovered to healthy
  with four observations and no transport failure.
- Lifecycle contained nine starts, eight stops, one current open run, zero
  unclean restarts, and zero abandoned runs. Historical concurrent-start and
  process-run-reentry counts stayed at one each; the new task and reboot did
  not add a writer conflict.
- The persistent writer-lock file retained its older modification time, which
  is expected. The actual exclusivity guarantee is the OS byte-range lock, not
  file freshness.

### Current operating boundary

- Do not run foreground continuous mode or `--once` while the task is active.
  `--check-config` and `--audit-state` remain safe concurrent diagnostics.
- The public minimal repository remains separately verified at its 0.4.1
  commit. The deployed 0.7 ZIP does not prove that repository was updated.
- Current alerts remain authoritative. The agent has no external delivery,
  process control, remote shell, application/database write, or manual-job
  path.
- Local `0.8.1-test` supersedes the undeployed 0.8.0 bundle. It retains
  endpoint set 3 with eight safe facade routes and a ninth direct external
  public-page probe, and adds the exact env-v1/four-endpoint recovery bridge.
  Its ZIP SHA-256 is
  `D17A88A10814D4CC645AD731B5C2B56B3B662E0662547ED9FCEA3443EF876884`;
  manifest SHA-256 is
  `18A3E477E724EEA61F3EFDCBE303BEBE4DC298A4D646D37FE643D6CD9C49CBB1`.
  It is not deployed and does not supersede the verified lifecycle facts above.
- Continue with roadmap item 1: first prove the 0.8.1 unchanged-env-v1 bridge
  under the single-writer gate, then migrate the remote configuration to v2
  and prove one nine-observation cycle plus audit-v7 mixed/current-run history.
  Bounded
  retention, credential rotation, independent center observation, report
  review/delivery, and rollback proof remain open.
