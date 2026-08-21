# Monitoring agent test project

This is the independent read-only observer for `OPS-002`. The test project is
designed to be opened and managed as its own small PyCharm project on the
remote supervision workstation. It may be transferred as a reviewed bundle or,
for fast test-stage iteration after 2026-08-14, updated through the standalone
Git repository. It is not registered for automatic startup by extraction or
Git pull alone and does not replace existing scheduler alerts. An existing
reviewed Scheduled Task may be upgraded only through the separate
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

## Test-stage Git iteration workflow

The active test-stage repository is:

```text
https://github.com/mtravnicekarmex/monitoring-agent-0.8.1.git
```

For test iterations, the supervision station treats the pulled Git commit hash
as the active checkout identity. Commit
`5cfc5916d3e83cdcc1eecd34f3f2719d62ec351c` contains the item 2-5 candidate
source, including incident rules, bounded incident/outbox state, pure
report/prompt rendering, and the `O_EMAIL`/`O_APP`/
`DELIVERY_TEST_RECIPIENT` test-only delivery path. Commit
`86ee42b058c74675976904c1e51a2f3677c5f138` adds item 6
draft/fallback interpretation source. Commit
`3e7b94e9045527a1254b10066a3a34493577f025` adds item 7
shadow-pilot comparison source and regenerated manifest files with 20
declared runtime files. Later item-7 commits add runtime shadow incident
persistence, the env-v2 external-web compatibility fix, and the file-based
shadow-pilot comparison CLI used to prepare the reviewed-period comparison.
Commit `f6583d80a77695b3f4a094337251c6835b389b59` adds the item-9
file-only orchestrator modules and
`monitoring_agent.orchestrator_export_cli wrap-remote-audit` so supplied
remote `--audit-state` JSON can be wrapped with `captured_at` before
orchestration.

Before pulling changed source on the supervision station:

1. Stop `MonitoringAgentTest`.
2. Run `git pull` in the standalone project checkout.
3. Verify the active identity with `git rev-parse HEAD`.
4. Run `py -3.14 run_monitoring_agent.py --check-config`.
5. Start `MonitoringAgentTest`.
6. Verify with `py -3.14 run_monitoring_agent.py --audit-state`.

Do not change source beneath a running Scheduled Task process. The real `.env`
and state files remain local to the supervision station and must not be
committed, printed, copied into reports, or packaged. The original 0.8.1 ZIP
identity remains historical release evidence only until a new reviewed release
bundle is explicitly built.

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
   to 3, add `MONITORING_AGENT_EXTERNAL_WEB_URL`, update
   `MONITORING_AGENT_ENDPOINT_KEYS` to the exact nine-key value from the new
   `.env.example`, and set the explicit local state retention/outbox limits.
   Preserve the existing bearer, instance ID, state path, timeouts, retry
   policy, interval, jitter, and private base URL.

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
{"endpoint_count":9,"env_contract_version":3,"event":"configuration_valid","mode":"test"}
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

The steady-state `.env.example` defines:

- serialized 300-second start-to-start cycles plus 0-30 seconds random jitter;
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

## Incident rule and lifecycle contract

Incident rule version 1 is a pure deterministic layer in
`monitoring_agent/incidents.py`. It consumes already-normalized observation
facts or complete-cycle snapshots and returns sanitized incident states and
transitions. It does not read `.env`, perform network access, write state,
send email, mutate the target application, or replace legacy alerts. Bounded
incident persistence and an outbox remain the separate roadmap item 3.

Default rule table:

| Kind | Opens after | Recovers after | Evidence | Suppression |
| --- | ---: | ---: | --- | --- |
| `endpoint` | 2 consecutive cycles | 2 healthy cycles | isolated retryable endpoint transport failure, external-web failure, or payload status `unavailable`/`degraded`/`error` | retryable facade endpoint failures are suppressed when the same cycle qualifies as target-wide |
| `target_wide_outage` | 2 consecutive cycles | 2 healthy cycles | every observed facade endpoint fails with retryable transport status `connection_error` or `timeout` | suppresses matching per-endpoint transport noise |
| `observer_self_health` | 1 cycle | 2 healthy cycles | facade `http_error`, `schema_error`, or `tls_error`, which indicates observer/facade contract, authorization, or trust-boundary trouble rather than application payload status | none |
| `supervision_center_blind_spot` | 1 stale check | 1 fresh cycle | no complete cycle or the latest complete cycle older than the deterministic stale threshold, default 130 seconds | none |

Lifecycle semantics are explicit: a pre-threshold condition is a `candidate`
and emits only a suppressed transition; a confirmed condition opens an
`active` incident; repeated matching evidence updates that incident; a
configured number of healthy cycles recovers it; later confirmed recurrence
reopens it after the recurrence cooldown. Historical retained evidence must be
passed as `historical=True`; it is qualified and suppressed, so immutable
upgrade artifacts such as old schema errors cannot open a current incident.

## Bounded incident store and delivery outbox contract

Environment contract 3 requires explicit local bounds for observations,
incident states, transition records, outbox items, delivery attempts, retry
backoff, and abandoned-claim recovery. Legacy contract 1 and 2 files remain
loadable only for controlled upgrade compatibility and receive conservative
code defaults; new deployments should use contract 3 so the bounds are visible
in `.env.example`. Contract 2 still owns the nine-endpoint set and therefore
must read and validate `MONITORING_AGENT_EXTERNAL_WEB_URL`; otherwise the
`external_web` endpoint cannot start.

`monitoring_agent/incident_store.py` persists one agent-owned
`incident_state.json` file with:

- normalized current incident states;
- bounded sanitized transition records, with redundant unchanged `updated`
  transitions collapsed so a long-running active incident does not evict
  meaningful open/recover/suppression history;
- bounded delivery-intent outbox items;
- deterministic idempotency keys;
- retry/dead-letter state;
- in-progress claim recovery after a configured timeout.

The outbox is only intent state. It has no sender adapter, recipient list,
credential, message body, network access, or delivery authorization. Later
delivery work must consume this store through a separately approved adapter.
Atomic replace is used for snapshot writes. Invalid or corrupt incident state
fails closed and is not overwritten.

Observation history is retained separately by `ObserverStore` after each
completed cycle. Retention keeps whole recent cycles and atomically rewrites
`observations.jsonl`; invalid observation JSON fails closed without rewrite.
This intentionally changes future source behavior from unbounded append-only
observation history to bounded agent-owned local history. Lifecycle and
heartbeat semantics remain separate.

## Pure report and programming-agent prompt contract

`monitoring_agent/reporting.py` renders deterministic text only from supplied
normalized incident facts and optional incident-store snapshots. It does not
read `.env`, inspect local state files, perform network access, send email,
claim outbox items, mutate incident state, control processes, or replace
legacy alerts.

The report keeps these sections visibly separate:

- verified facts, such as rule version, heartbeat summary, incident-state
  counts, transition counts, and delivery-disabled outbox counts;
- deterministic rule conclusions, such as candidate, active, opened, updated,
  recovered, or suppressed incident facts;
- historical qualifications and evidence gaps, including retained
  upgrade/migration evidence that must not open a current incident;
- hypotheses that are not verified facts.

The programming-agent prompt renderer is also pure and bounded. It explicitly
labels the output as a draft only, asks only for read-only diagnostic planning,
and states that no command execution, network contact, state mutation,
service restart, delivery attempt, or alert replacement is authorized.

Both renderers apply defensive redaction for likely secret assignments,
bearer values, URL query/fragment content, Windows user paths, and synthetic
private identifiers. Redaction is a safety net, not a license to pass raw
credentials, raw `.env`, raw endpoint bodies, recipients, or private runtime
state into report inputs.

## Agentic interpretation contract

`monitoring_agent/interpretation.py` adds interpretation contract version 1 as
a pure layer above confirmed normalized incidents. It is not wired into the
polling loop, does not read `.env`, does not contact a model provider by
itself, and cannot mutate the monitored application, incident state, outbox,
delivery state, scheduler alerts, services, or processes.

Interpretation is gated by an explicit in-memory `InterpretationPolicy`.
Current item-6 source supports only:

- `enabled=False`, which returns the deterministic report fallback without
  calling any provider;
- `enabled=True` with `mode="draft"`, an injected provider object, provider
  name, model name, timeout, prompt/output size bounds, item-count bounds, and
  a cost ceiling.

Every permission-style flag in the policy must remain false:
`allow_network`, `allow_state_mutation`, `allow_process_control`,
`allow_delivery`, and `allow_alert_suppression`. The module deliberately adds
no provider credentials and no `MONITORING_AGENT_*` runtime configuration
keys.

The interpreter is invoked only when the supplied report snapshot contains at
least one `active` incident state. Candidate-only degraded evidence is skipped
with a deterministic fallback. Missing provider, provider exception, invalid
provider output, or unsafe provider text also falls back to the pure
deterministic report. Provider exception text is never included in the
sanitized result.

Provider output is accepted only as bounded hypotheses, recommended read-only
checks, and evidence gaps. It is defensively redacted and rejected if it tries
to authorize commands, network actions, state writes, service restarts,
delivery attempts, remediation, or alert suppression. The result carries only
audit metadata such as provider/model names, timeout/cost bounds, prompt hash,
prompt length, confirmed incident keys, status, and coarse error code; it does
not persist prompts, call external systems, suppress deterministic incident
rules, or replace legacy alerts.

## Shadow pilot comparison contract

`monitoring_agent/shadow_pilot.py` adds shadow-pilot comparison contract
version 1 for roadmap item 7. It compares supplied normalized monitoring-agent
events with supplied normalized legacy-alert events for one reviewed period.
It does not read `.env`, inspect databases, poll endpoints, call an
interpretation provider, send email, mutate state, control processes, or
replace legacy alerts.

The comparison boundary is intentionally narrow:

- `ShadowPilotEvent` represents one comparable detection or recovery event
  from either `monitoring_agent` or `legacy_alert`.
- `events_from_incident_evaluation()` converts existing agent incident
  lifecycle output to comparable shadow events, keeping only `opened`,
  `reopened`, and `recovered` transitions.
- `build_shadow_pilot_comparison()` uses a start-inclusive/end-exclusive
  period, one configurable match window, and one configurable duplicate
  window.
- `render_shadow_pilot_comparison()` produces a bounded redacted text summary
  for operator review.

The output is always `mode="shadow_only"`. It reports matched detections,
matched recoveries, agent-only detections as false positives, legacy-only
detections as false negatives, agent-minus-legacy confirmation and recovery
delays, duplicate counts/rates, and blind-spot counts. Duplicates are counted
separately and are not used to inflate false-positive or false-negative
counts. Defensive redaction is applied to optional summaries, but comparison
inputs must still be sanitized facts rather than raw email bodies, raw `.env`,
credentials, recipients, endpoint payloads, or private runtime files.

The operator helper `python -m monitoring_agent.shadow_pilot_cli` provides
read-only file-based entry points for the reviewed-period comparison. It does
not use `.env`.

Export comparable agent events from the local agent-owned state file:

```powershell
python -m monitoring_agent.shadow_pilot_cli export-agent-events `
  --agent-state-file "C:\Path\To\state\incident_state.json" `
  --period-start "2026-08-17T00:00:00+00:00" `
  --period-end "2026-08-18T00:00:00+00:00" `
  --json-output ".\artifacts\shadow-agent-events.json"
```

Compare those events with a supplied sanitized legacy-alert event file:

```powershell
python -m monitoring_agent.shadow_pilot_cli compare `
  --agent-events-file ".\artifacts\shadow-agent-events.json" `
  --legacy-events-file ".\artifacts\legacy-alert-events.json" `
  --period-start "2026-08-17T00:00:00+00:00" `
  --period-end "2026-08-18T00:00:00+00:00" `
  --json-output ".\artifacts\shadow-comparison.json" `
  --markdown-output ".\artifacts\shadow-comparison.md"
```

The legacy event file may be either an array of events or an object with an
`events` array. Each event must contain only sanitized fields:
`incident_key`, `action`, `occurred_at`, optional `source="legacy_alert"`,
optional `severity`, optional `summary`, optional `event_reference`, and
optional `contract_version=1`.

This source preflight does not complete the real item-7 shadow pilot. Item 7
requires a reviewed operating period, a written comparison against the current
alerts, and separate approval before any legacy alert is replaced, disabled,
rerouted, downgraded, or suppressed.

## File-only orchestrator CLI

`monitoring_agent/orchestrator.py` and
`python -m monitoring_agent.orchestrator_cli` implement the first
file-only/shadow-only orchestrator proof. The CLI consumes only a supplied
registry JSON file and supplied sanitized source snapshot files. It does not
poll endpoints, read `.env`, send email, call interpretation providers,
mutate state, control processes, register tasks, or replace alerts.

The registry is static; there is no dynamic discovery. Every enabled agent
entry must define a stable `agent_key`, `agent_kind`, `location`,
`payload_kind`, supported contract-version range, source file, and
`stale_after_seconds`. Duplicate `agent_key` values fail closed before a
snapshot is produced. Source files named `.env` are rejected.

Supported file-only payload kinds are:

- `agent_snapshot_v1`: already-normalized sanitized orchestrator source
  snapshot;
- `local_agent_facade_v1`: sanitized local-agent facade response;
- `remote_agent_audit_v8`: sanitized remote monitoring-agent audit summary.

Remote `run_monitoring_agent.py --audit-state` output does not include a
capture timestamp by itself. Before passing that JSON to the orchestrator,
wrap it with the file-only export helper so `captured_at` is explicit:

```powershell
python -m monitoring_agent.orchestrator_export_cli wrap-remote-audit `
  --input ".\artifacts\remote-audit-raw.json" `
  --output ".\artifacts\remote-audit.json"
```

The helper accepts stdin when `--input` is omitted and writes wrapped JSON to
stdout when `--output` is omitted. It rejects `.env` paths, requires
`event="agent_state_audit"`, adds only `captured_at`, and does not poll
endpoints, read `.env`, send email, mutate state, or control tasks.

Run a file-only correlation:

```powershell
python -m monitoring_agent.orchestrator_cli run `
  --registry-file ".\artifacts\orchestrator-registry.json" `
  --json-output ".\artifacts\orchestrator-snapshot.json" `
  --markdown-output ".\artifacts\orchestrator-snapshot.md"
```

The output is a bounded orchestrator snapshot with normalized agent rollups,
freshness, evidence gaps, aggregate counts, sanitized payload digests, and
correlation findings. A missing, stale, or contract-invalid source is isolated
to that source and reported with a bounded evidence gap. The orchestrator
output is operator context only; legacy alerts remain authoritative.

On the main workstation, export the local sanitized facade aggregates for a
file-only pilot:

```powershell
python scripts\export_monitoring_orchestrator_local_inputs.py `
  --artifact-dir ".\artifacts\monitoring\orchestrator\2026-08-18-file-only-pilot"
```

Without a supplied remote audit this writes a local-only registry for
preflight. It is not the full three-surface pilot. After wrapping a sanitized
remote `run_monitoring_agent.py --audit-state` JSON file with
`orchestrator_export_cli wrap-remote-audit`, run the same helper with
`--remote-audit-file` pointing to the wrapped file to write the full registry.

## Runtime shadow incident persistence

`monitoring_agent/runtime_shadow.py` wires the deterministic incident lifecycle
into the polling process in shadow mode. After each completed observation
cycle, the runner converts the cycle's normalized observations into an
incident evaluation, applies it to the bounded `IncidentStateStore`, and
prints a sanitized `shadow_incidents` summary in the `observation_cycle`
console event.

The persisted file is `incident_state.json` under the configured agent-owned
state directory. It contains normalized incident states, sanitized transition
records, and delivery-intent outbox items only. The outbox remains intent
state; nothing claims or sends those items from the polling loop.

Runtime shadow persistence uses the existing runtime settings. It adds no new
`.env` variable. Env contract 3 can set explicit incident/outbox limits;
legacy env contracts 1 and 2 continue to use conservative code defaults.

`--audit-state` now uses audit contract 8 and includes an aggregate
`shadow_incidents` section with counts, outbox status counts, `present`,
`history_valid`, `mode="shadow_only"`, and `delivery_enabled=false`. The audit
does not print raw transition payloads, report bodies, recipients, credentials,
or endpoint payloads. A corrupt `incident_state.json` fails closed as an audit
or runtime error and is not overwritten.

## Test-only delivery adapter contract

`monitoring_agent/delivery.py` contains the source-only delivery adapter for
the next controlled test gate. It is not wired into the polling loop and does
not run unless called explicitly by an operator-controlled workflow.

The default policy is disabled. In disabled mode the adapter does not claim
outbox items, does not mutate `incident_state.json`, does not build a message,
and does not call a transport. Enabled delivery is restricted to `mode="test"`
and requires:

- one in-memory test recipient;
- an in-memory allowlist derived by the controlled operator path from that
  exact recipient;
- a supplied report body keyed by the outbox item's `report_reference`;
- an explicit transport object.

Sanitized delivery results include outbox identity, incident key, action,
report reference, recipient hash, attempt count, status, and coarse error
code. They do not include the raw recipient, SMTP username, password, sender,
message body, transport exception text, or any credential value. Message body
and recipient address exist only in the in-memory envelope passed to the
transport.

`OutlookEmailTransport` is the only operator SMTP backend. It calls
`send_email_outlook()`, mirroring the existing local alarm-email pattern:
Office365/Outlook SMTP on `smtp.office365.com:587`, EHLO, STARTTLS, EHLO,
login, send message, and retry only for known transient SMTP response codes.
The standalone monitoring-agent implementation reads `O_EMAIL` and `O_APP`
from the already-loaded `.env` or process environment for login/default
sender; `EMAIL` and `APP` remain accepted only as a compatibility fallback.
Those values are never written to Git or agent state.

Automatic runtime delivery remains test-only and opt-in. It is enabled only
when the non-`MONITORING_AGENT_` key `DELIVERY_AUTOMATION_ENABLED=true` is
present in the local `.env`. When enabled, the polling loop sends at most one
due pending outbox item after a completed observation cycle, using
`DELIVERY_TEST_RECIPIENT`, `O_EMAIL`/`O_APP`, the existing retry/dead-letter
state, and a sanitized deterministic report body generated from
`incident_state.json`. It does not support production recipients, recipient
lists, provider interpretation, remediation, process control, alert
suppression, or legacy-alert replacement.

Item 5 is complete only for the test-only Outlook delivery boundary. On
2026-08-14 the supervision station verified commit
`5cfc5916d3e83cdcc1eecd34f3f2719d62ec351c`, loaded the controlled recipient
only as a hash, prepared an isolated synthetic outbox/report, dry-ran one due
item, and sent one explicitly confirmed synthetic email through `send-due`.
The sanitized result was `status="sent"`, `action="opened"`,
`attempt_count=1`, and no error code. A follow-up `dry-run` for the same
`idempotency_key` returned `due_count=0`, proving the sent synthetic outbox
item was not pending for re-send. Production recipients, automatic delivery,
production delivery channels, and legacy scheduler-alert replacement remain
unauthorized.

The operator helper `python -m monitoring_agent.delivery_cli` provides the
controlled test entry points. By default it reads `.env` from the current
working directory, but loads only the delivery keys needed by the selected
command and never prints the loaded values.

- `hash-recipient` reads the recipient from `DELIVERY_TEST_RECIPIENT` and
  prints only its SHA-256 hash for optional diagnostics.
- `dry-run` validates the in-memory recipient policy and counts matching
  due outbox items without claiming, mutating, or sending.
- `review-outbox` reads `incident_state.json` and prints a sanitized
  read-only outbox summary for alert-email review. It does not read `.env`,
  does not require a recipient, does not claim items, and does not call SMTP.
- `skip-outbox` marks explicitly selected pending outbox items as
  operator-skipped without sending. It requires
  `--confirm SKIP_PENDING_OUTBOX`, an exact filter or `--created-before`
  cutoff, and a positive `--limit`. The persisted terminal status is the
  existing `dead_letter` with `last_error_code="operator_skipped"` so the
  `incident_state.json` schema and audit contract stay compatible.
- `prepare-synthetic` creates one local synthetic outbox item plus a sanitized
  report file for a local end-to-end adapter test. It requires
  `--confirm PREPARE_SYNTHETIC_DELIVERY_TEST_STATE` and refuses to reuse an
  existing state file unless explicitly overridden.
- `send-due` requires `--confirm SEND_TEST_DELIVERY`, one exact
  `--report-reference`, `--claim-id`, a sanitized `--report-file`, the
  existing alarm SMTP credentials, and `DELIVERY_TEST_RECIPIENT`. It rejects
  `.env` files as report input, creates the in-memory recipient allowlist
  internally from the same recipient, calls `send_email_outlook()` through
  `OutlookEmailTransport`, and defaults to one outbox item per invocation.

Use these delivery-test keys in `.env` or as process environment variables:

- `O_EMAIL`: Office365/Outlook SMTP login and default sender address.
- `O_APP`: SMTP app password/secret for `O_EMAIL`.
- `DELIVERY_TEST_RECIPIENT`: exact controlled test recipient.
- optional `DELIVERY_TEST_SENDER_ALIAS`: only when the mailbox is known to be
  allowed to send as this alias.
- optional `DELIVERY_AUTOMATION_ENABLED=true`: enables automatic test-only
  runtime delivery of at most one due pending outbox item after each completed
  polling cycle. The default and missing value is disabled.

These keys intentionally do not use the `MONITORING_AGENT_` prefix. The
polling runtime validates only `MONITORING_AGENT_*` keys, so these delivery
keys may live in the same local `.env` without changing the observer runtime
schema. Do not add delivery-test keys with the `MONITORING_AGENT_` prefix;
that prefix is reserved for the strict monitoring-agent configuration schema.

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
    --version 0.8.2-test `
    --created-date 2026-08-14 `
    --output artifacts\monitoring_agent\monitoring-agent-0.8.2-test.zip
```

The builder uses deterministic ZIP metadata. It includes `.env.example` but
rejects any design that would include the real `.env`, state, logs,
credentials from an operating station, PyCharm workspace state, or repository
metadata.
Do not rebuild or deploy changed source under the already verified
`0.8.1-test` identity; any package containing the incident-rule source needs a
new reviewed bundle version and hash.

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
