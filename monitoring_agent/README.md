# Monitoring agent test project

This is the independent read-only observer for `OPS-002`. The test bundle is
designed to be opened and managed as its own small PyCharm project on the
remote supervision workstation. It is not registered for automatic startup
by extraction alone and does not replace existing scheduler alerts. An
existing reviewed Scheduled Task may be upgraded only through the separate
stop/configure/verify/start procedure.

## Project contract

The remote project contains:

- `run_monitoring_agent.py`, the only operator entry point;
- `register_monitoring_agent_task.ps1`, a separately gated, idempotent Windows
  Scheduled Task registration helper with `-WhatIf` support;
- the `monitoring_agent/` standard-library package;
- `.env.example`, the complete non-secret configuration template;
- `.gitignore`, which excludes the real `.env`, PyCharm state, Python caches,
  virtual environments, and local agent state;
- bundle manifests for offline integrity verification.

The real `.env` exists only on the supervision workstation. It contains all
runtime values, including the private HTTPS base URL, public page root URL,
and monitoring bearer credential. The program reads the file directly; it
does not require the operator to create persistent or session-level
environment variables.

Never commit, bundle, display, transmit, or paste the real `.env`. Restrict
its Windows ACL to the operating identity and `SYSTEM` before any automatic
startup registration.

## First setup in PyCharm

1. Open the extracted bundle root as a PyCharm project.
2. Select CPython 3.14. No third-party package installation is required.
3. Copy `.env.example` to `.env`.
4. Edit `.env` locally and replace the private base URL and bearer placeholder.
   Verify the configured public HTTPS page root without adding credentials,
   query parameters, fragments, or a non-root path.
5. Keep `MONITORING_AGENT_MODE=test`.
6. Use a state directory outside the extracted code directory. A new empty
   directory is mandatory when migrating from a pre-0.6 bundle; an existing
   observation-contract-2/lifecycle-contract-1 state from `0.6.0-test` through
   `0.7.0-test` is compatible with `0.8.1-test` and should be retained for
   continuity. `0.8.1-test` supports a two-phase rolling upgrade. First retain
   the exact environment-contract-1 file and four endpoint keys unchanged;
   this runs the new safe client as observation contract 3 / endpoint set 2
   and proves recovery against the strict server-side projections. Only after
   that bridge cycle and audit pass, migrate the environment contract from 1
   to 2, add `MONITORING_AGENT_EXTERNAL_WEB_URL`, and update
   `MONITORING_AGENT_ENDPOINT_KEYS` to the exact nine-key value from the new
   `.env.example`. Preserve the existing bearer, instance ID, state path,
   timeouts, retry policy, interval, jitter, and private base URL.

Validate without network access or state writes:

```powershell
py -3.14 run_monitoring_agent.py --check-config
```

Expected safe output before the environment migration:

```json
{"endpoint_count":4,"env_contract_version":1,"event":"configuration_valid","mode":"test"}
```

Expected safe output after the environment migration:

```json
{"endpoint_count":9,"env_contract_version":2,"event":"configuration_valid","mode":"test"}
```

Run one foreground HTTPS cycle:

```powershell
py -3.14 run_monitoring_agent.py --once
```

Start continuous foreground polling for interactive testing:

```powershell
py -3.14 run_monitoring_agent.py
```

Audit existing agent-owned state without network access or state writes:

```powershell
py -3.14 run_monitoring_agent.py --audit-state
```

Audit contract version 7 prints only versioned aggregate counts, retry
invariants, inferred cycle transitions, serialized timing checks, the latest
heartbeat status, and sanitized diagnostics for the longest cycle and the
largest interval. It distinguishes a long-running cycle from an unexplained
between-cycle or wall-clock discontinuity within one process run. Intervals
that cross a `run_id` boundary are reported separately as `cross_run_*`
diagnostics and never affect scheduled interval, early-start, late-start, or
overlap findings. It also reports aggregate process starts, clean and unclean
restart transitions, abandoned runs, incomplete cycles, and lifecycle
consistency without exposing raw timestamps or IDs.
It retains the audit-v5 distinction between historical process-run reentry and
concurrent starts separately from a missing controlled stop. Existing 0.6
history may therefore retain `single_writer_*_valid=false` after upgrade; that
is immutable evidence of the earlier overlap, not a claim that the 0.6.2 lock
failed.

Observation contract 4 adds bounded `clock_skew_seconds` and
`endpoint_set_version=3` for the nine-endpoint cycle. Audit v7 reads legacy
contract-2/set-1 three-endpoint cycles, contract-3/set-2 four-endpoint cycles,
and current contract-4/set-3 nine-endpoint cycles from the same append-only
state. It enforces the exact contract-to-set mapping and evaluates each cycle
against its own order and timeout budget. This compatibility is intentional;
do not rewrite or discard retained 0.6/0.7 observations.

It never prints the `.env`, state path, bearer, observer instance, process ID,
cycle/observation IDs, timestamps, endpoint payloads, or raw JSONL records.
Each process creates a new random `run_id`. Observation contracts 2 through 4
record the run, cycle identity, and per-run cycle sequence. The append-only
local `observer_lifecycle.jsonl` records process starts and controlled stops, while
the atomic heartbeat remains the latest-state snapshot. The audit never
renders the recorded run ID or PID. Historical heartbeat transitions remain
an explicit gap; process-run history is available only for 0.6 state created
after this contract was installed.

The PyCharm run configuration uses `run_monitoring_agent.py` as the script,
the extracted bundle root as the working directory, and either `--once` or no
parameters. Do not copy `.env` values into the PyCharm run configuration.

## Polling and self-health contract

The initial `.env.example` defines:

- serialized 60-second start-to-start cycles plus 0-5 seconds random jitter;
- a three-second request timeout and at most three attempts;
- exponential 0.5/1.0-second backoff only for connection errors and timeouts;
- no retry for HTTP authorization/status errors, TLS errors, invalid JSON, or
  schema errors;
- approved HTTP 503 readiness retained as application evidence, not a
  transport failure;
- agent heartbeat written as `polling` at cycle start and `healthy` or
  `degraded` at completion;
- target scheduler degradation kept separate from observer self-health.

The client calls only the compiled-in GET allowlist. It has no manual-job,
database, shell, process-control, application-write, model, email, or external
delivery capability.

The current ordered endpoint set is exactly `live`, `ready`,
`system_scheduler`, `scheduler_detail`, `system_runtime`, `system_database`,
`system_proxy`, `system_smartfuelpass`, and `external_web`. The authenticated
facade projects only retained machine fields before they cross the network.
It excludes labels, descriptions, free-form details, local addresses, process
IDs, manual-run capability, database server inventory, configured public host
and paths, SmartFuelPass monetary totals, and report-period/business
aggregates.

The `external_web` request goes directly from the supervision workstation to
the configured public page root. It sends no facade bearer, follows no
redirect, reads no response body, requires HTTP 200 plus `text/html`, and
retains only transport/HTTP metadata and a normalized success flag. The full
URL and response headers are never written to observation state. Deploy all
matching authenticated facade routes on the monitored workstation before
starting 0.8; an absent route is a non-retryable HTTP failure.

Only one polling writer may use a state directory at a time. The process holds
a non-blocking operating-system file lock for its entire polling lifetime and
acquires it before lifecycle, heartbeat, observation, or HTTP activity. A
second `--once` or continuous invocation exits fail-closed with a sanitized
startup error and makes no runtime-state or network write. The one-byte
`observer_writer.lock` file may remain in the state directory, but the OS lock
itself is released when the process exits or is killed, so it is not a stale
PID-file contract. `--check-config` and `--audit-state` remain read-only and do
not take the writer lock.

## Monitored-station activation order

On the monitored workstation the FastAPI/Caddy runtime is created by the
Windows startup process. Under the current operating contract there is no
separately supported API-only restart path. Activating a newly added monitoring
facade route therefore requires a full restart of the monitored workstation.
This does not require restarting the separate supervision workstation.

For the 0.8.1 upgrade, keep the remotely running `0.7.0-test` observer active
during the monitored-workstation restart so it records target loss and
recovery. After Windows startup, first verify the startup task, expected
listeners, existing facade routes, and the new authenticated detailed
scheduler, database, proxy, and SmartFuelPass routes. Do not expose the bearer
or raw responses while checking them. Only after all routes succeed should the
remote operator stop the `MonitoringAgentTest` task and confirm no writer
remains. Install 0.8.1 side by side, retain the existing state directory and
unchanged env-v1 file, then run `--check-config`, `--once`, and `--audit-state`.
Require a healthy four-observation compatibility cycle and valid current-run
evidence. Only then migrate `.env` to contract 2 / nine keys and run the same
three commands again before returning to continuous task operation. Historical
0.7 schema failures remain append-only evidence and may keep global retry
history false; the new audit-v7 `observations.current_run` result must pass.

The stop mechanism is a separate migration gate. Do not assume that
`Stop-ScheduledTask` records a controlled observer stop: Windows Task Scheduler
may terminate a task without allowing the Python `finally` path to append its
lifecycle stop event. Transfer and hash verification may proceed while 0.7 is
running, but do not stop, replace, or restart the task until the operator has
approved a lifecycle-safe stop method or an explicitly qualified planned
termination. The 0.8.1 package does not itself authorize process control.

This procedure records the required ordering but does not authorize or perform
the workstation restart, API deployment, remote synchronization, or Scheduled
Task registration.

## Scheduled Task review gate

The bundle contains a registration helper, but the task is not registered by
extracting or running the observer. Preview its validated paths and intended
mutation without registering anything:

```powershell
.\register_monitoring_agent_task.ps1 -WhatIf
```

New registration and changes to an existing task remain separate explicit
approvals. The reviewed default uses the bundle's `.venv\Scripts\python.exe`,
an explicit working directory, the `SYSTEM` service identity, an `AtStartup` trigger,
`StartWhenAvailable`, one-minute failure restarts, and `IgnoreNew` duplicate
handling. No bearer, URL, or `.env` value appears in the task command line.
Before approval, verify that `SYSTEM` can read the ACL-restricted `.env`, write
the configured state directory, and execute the project and virtual
environment. Rollback is removal of the named `MonitoringAgentTest` task; it
does not delete code, `.env`, or state.

## Synthetic scenarios

The optional loopback-only synthetic server supports:

- `healthy`;
- `scheduler_stopped`;
- `readiness_unavailable`;
- `unauthorized`;
- `invalid_schema`.
- `external_redirect`.

It refuses non-loopback binds and exposes no mutation endpoint.

## Bundle build

Build the reviewed explicit-allowlist ZIP without staging unrelated files:

```powershell
.\.venv-production\Scripts\python.exe `
    scripts\build_monitoring_agent_bundle.py `
    --version 0.8.1-test `
    --created-date 2026-08-06 `
    --output artifacts\monitoring_agent\monitoring-agent-0.8.1-test.zip
```

The builder uses deterministic ZIP metadata. It includes `.env.example` but
rejects any design that would include the real `.env`, state, logs,
credentials from an operating station, PyCharm workspace state, or repository
metadata.

## Source-repository verification

Run this before packaging from the full source repository. The standalone
remote project does not include the test suite.

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_monitoring_agent.py -q
```

Automatic Windows startup registration or modification remains a separate
approval gate. Use the same `run_monitoring_agent.py` entry point for
foreground validation, the `-WhatIf` preview, and any later reviewed Scheduled
Task registration or upgrade.
