# Monitoring Agent Implementation Roadmap

Prepared: 2026-08-06

Status: approved execution order; items 1, 2, 3, 4, 5, and 6 completed on
2026-08-14; item 7 completed on 2026-08-17.
Item 1 completed after remote 0.8.1 nine-endpoint recovery and continuous
Scheduled Task restoration proof. Item 2 completed as a local pure
incident-rule/lifecycle source layer with synthetic tests. Item 3 completed
as a local bounded incident state/outbox and observation-retention source
layer with restart, idempotency, retry/dead-letter, corrupt-state, and
retention tests. Item 4 completed as a local pure report and draft-only
programming-agent prompt renderer with snapshot, example, redaction, and bound
tests. Item 5 completed after a separately approved controlled synthetic
Outlook delivery test from the supervision station returned sanitized
`status="sent"` evidence. Item 6 completed as a local pure interpretation
contract over confirmed incidents only, with provider/model/time/cost bounds,
fallback to deterministic reports, redaction, and mutation/delivery/process
control denial tests.
Item 7 completed as a healthy no-event reviewed pilot plus file-only
synthetic comparison proof for matched detection/recovery, delay,
false-positive, false-negative, duplicate, blind-spot, and safety-boundary
metrics. Legacy alerts remain authoritative and no replacement is approved.

Parent plan: `SCHEDULER_MONITORING_AGENT_PLAN.md`

Verified runtime handoff: `MONITORING_AGENT_REPORTING_LAYER_HANDOFF.md`

## How to use this checklist

- Work through the nine top-level items in order unless a later reviewed
  decision explicitly changes the sequence.
- Check a top-level item only after its implementation, focused tests, and
  required runtime or synthetic proof are complete.
- When checking an item, add the completion date and links to the decisive
  evidence directly below it.
- A checked item must preserve the current read-only, least-privilege, safe
  projection, single-writer, and independently operable runtime boundaries.
- Email delivery, agentic interpretation, remediation, and orchestration do
  not become authorized merely because their later checklist item exists.

## Recommended implementation order

- [x] 1. Extend the safe observation contracts and add an external web probe.

  Cover the remaining approved Scheduler Health and System Health facts through
  versioned, allowlisted, read-only projections. Add a probe executed from the
  supervision workstation against the public monitoring page, because its
  true external availability cannot be established from the monitored main
  workstation. Do not retain raw response bodies, secrets, identifiers, or
  unrestricted logs.

  Completion requires schema validation, compatibility rules, synthetic tests,
  bounded timeout/retry behavior, and a verified remote cycle containing all
  newly approved observations.

  Progress 2026-08-06: local 0.8 source implements eight strict authenticated
  facade projections plus the direct credential-free external probe,
  environment contract 2, observation contract 4 / endpoint set 3, bounded
  clock skew, and audit contract 7 compatibility with retained sets 1 and 2.
  The targeted local matrix, including repository-root hygiene, passed with
  186 tests. The deterministic 13-file/15-entry bundle has ZIP SHA-256
  `29BEE64FEE267F1E74BE1AA89CA621E2930262E16C0C662580DA5D2B7EBF8EF0` and
  manifest SHA-256
  `282DFDDA162B4D4CB2C3CE656066D47E2B03504F1434277659E20CBCBB173ADF`.
  The supported 2026-08-06 monitored-workstation restart then activated all
  eight facade routes. Local live/readiness/dashboard/Caddy checks passed,
  runtime/database/proxy safe projections were `ok`, all eight unauthenticated
  facade calls returned JSON HTTP 401 instead of the previous four-route 404
  baseline, and the remote 0.7 observer recovered to repeated complete
  four-endpoint HTTP-200 cycles. The then-current SmartFuelPass payload
  truthfully remained `error` as a known paused import state; the
  2026-08-10 application change replaces that active import condition with
  manual Excel import health while still keeping observer self-health separate
  from target payload status. Keep this item open only for the controlled
  remote 0.8 migration, one verified complete nine-observation cycle, and the
  audit-v7 mixed-history pass.

  Compatibility correction 2026-08-06: the first postrestart remote audit
  showed that 0.7 still required the former full `system/runtime` schema while
  the activated safe server projection correctly removed transient details,
  local addresses, and process IDs. The append-only state therefore gained 68
  schema errors and the latest four-observation heartbeat was degraded. Do not
  restore the excluded fields or skip the recovery gate. Local `0.8.1-test`
  supersedes the undeployed 0.8.0 bundle and accepts the exact env-v1/four-key
  configuration as a strict contract-3/set-2 upgrade bridge before the later
  env-v2/nine-key switch. Audit v7 now reports current-run retry evidence
  separately from immutable historical findings. The 192-test focused matrix,
  compilation, reproducible bundle build, file-hash validation, and archive
  allowlist passed. The new ZIP SHA-256 is
  `D17A88A10814D4CC645AD731B5C2B56B3B662E0662547ED9FCEA3443EF876884`;
  manifest SHA-256 is
  `18A3E477E724EEA61F3EFDCBE303BEBE4DC298A4D646D37FE643D6CD9C49CBB1`.

  Remote recovery proof 2026-08-07: after the monitored workstation restart
  activated the timezone-aware `scheduler_detail` fix, the supervision
  station's env-v2 `--once` completed one nine-observation cycle with
  transport status `success`. Audit v7 reported endpoint set 3, valid endpoint
  and cycle order, latest heartbeat `healthy`, nine latest observations, zero
  latest transport failures, valid retry/attempt invariants, clean lifecycle,
  and no concurrent-start, run-reentry, unclean, abandoned, incomplete, or
  writer evidence in the new clean state. Two schema errors remain as retained
  pre-fix env-v2 history and are no longer current failures. Continuous
  `MonitoringAgentTest` restoration was attempted only after the proof:
  `-WhatIf` passed, but non-elevated registration failed with Windows access
  denied (`HRESULT 0x80070005`).

  Continuous Scheduled Task restoration proof 2026-08-14: elevated
  registration of `MonitoringAgentTest` in
  `C:\Users\tra\PycharmProjects\monitoring-agent-0.8.1-test` succeeded and
  the task was `Running`; `LastTaskResult` was `267009` / `0x41301`, meaning
  the task was currently running. After four retained startup/recovery degraded
  cycles with connection-error evidence, the latest endpoint summary showed
  all nine endpoint keys (`live`, `ready`, `system_scheduler`,
  `scheduler_detail`, `system_runtime`, `system_database`, `system_proxy`,
  `system_smartfuelpass`, and `external_web`) returned HTTP 200 / `success`
  on attempt 1. Audit v7 reported recovery at cycle 5, latest heartbeat
  `healthy`, nine latest observations, zero latest transport failures, valid
  endpoint/cycle order, valid retry/attempt bounds, no incomplete state, clean
  open continuous lifecycle, and zero new concurrent-start, run-reentry,
  unclean, abandoned, or overlap evidence. Item 1 is complete; item 2 is now
  the next approved work.

- [x] 2. Define deterministic rules, thresholds, and the incident lifecycle.

  Specify versioned rules for confirmation, severity, deduplication, recovery,
  cooldown, recurrence, stale evidence, and historical-evidence qualification.
  Distinguish an endpoint incident, target-wide outage, observer self-health
  problem, and supervision-center blind spot.

  Completion requires reviewed rule tables, explicit transition semantics,
  deterministic clocks, and synthetic tests for opening, updating, recovering,
  reopening, and suppressing incidents.

  Completion 2026-08-14: `monitoring_agent/incidents.py` adds pure
  incident-rule version 1 without persistence, outbox, external delivery,
  network access, `.env` reads, target mutation, or legacy-alert replacement.
  The default rule table distinguishes endpoint incidents, target-wide facade
  transport outage, observer/facade self-health problems, and
  supervision-center blind spots. It defines confirmation thresholds,
  recovery thresholds, deterministic stale evidence checks, recurrence
  cooldown, target-wide suppression of per-endpoint retryable transport noise,
  and historical-evidence suppression for retained upgrade artifacts. Focused
  synthetic tests cover opening, updating, recovering, reopening, suppressing,
  stale blind-spot recovery, observer self-health, and sanitized conversion
  from observations. The module is bundled only as candidate source for the
  next reviewed package version; deployed 0.8.1 behavior is unchanged.

- [x] 3. Introduce a bounded incident store and delivery outbox.

  Persist only normalized incident state, transitions, report references, and
  delivery intent owned by the agent. Define bounded retention, atomic writes,
  idempotency keys, retry state, dead-letter handling, and crash recovery. The
  outbox must not itself imply that external sending is enabled.

  Completion requires retention and restart tests, duplicate-delivery
  prevention, corrupt-state fail-closed behavior, and proof that observation
  history cannot grow without a configured bound.

  Completion 2026-08-14: `monitoring_agent/incident_store.py` adds a bounded
  local `incident_state.json` contract for normalized incident states,
  transition records, report references, and delivery-intent outbox items.
  The outbox has deterministic idempotency keys, due-claim state, duplicate
  claim suppression, retry backoff, dead-letter state, and abandoned-claim
  recovery, but no sender adapter, recipient list, credential, message body,
  network access, or delivery authorization. Environment contract 3 adds
  explicit local bounds for observation records, incident states, transition
  records, outbox items, delivery attempts, retry backoff, and claim timeout;
  legacy env v1/v2 remain loadable only with conservative code defaults for
  controlled upgrade compatibility. `ObserverStore.retain_recent_observations`
  keeps whole recent cycles and atomically rewrites `observations.jsonl` after
  each runtime cycle. Corrupt incident state and corrupt observation history
  fail closed without overwrite. Focused tests cover persistence after
  restart, duplicate delivery-intent prevention, retry/dead-letter, abandoned
  claim recovery, transition/outbox retention, corrupt-state fail-closed
  behavior, configured observation retention, and runner retention after
  `--once`. This is candidate source only; deployed 0.8.1 behavior is
  unchanged until a separately reviewed new bundle is built and activated.

- [x] 4. Implement a pure report and programming-agent prompt.

  Render a concise report from normalized facts without delivery side effects.
  Keep verified facts, rule conclusions, historical qualifications, and later
  hypotheses visibly separate. Produce a bounded programming-agent prompt that
  describes evidence, scope, safety constraints, requested diagnostics, and
  success criteria without embedding secrets or authorizing execution.

  Completion requires stable snapshot tests, redaction tests, useful healthy,
  degraded, incident, and recovery examples, and explicit confirmation that
  the prompt is a draft only.

  Completion 2026-08-14: `monitoring_agent/reporting.py` adds pure
  deterministic report and programming-agent prompt renderers over supplied
  normalized incident facts and optional bounded incident-store snapshots.
  Reports keep verified facts, rule conclusions, historical qualifications,
  evidence gaps, and hypotheses in separate sections, and always state that
  delivery is disabled. The programming-agent prompt is bounded and explicitly
  marked draft-only; it requests read-only diagnostic planning and does not
  authorize command execution, network contact, state mutation, process
  control, delivery, or legacy-alert replacement. Defensive redaction covers
  likely secret assignments, bearer values, URL query/fragment data, Windows
  user paths, and synthetic private identifiers. Focused tests cover a stable
  healthy snapshot, degraded candidate, active incident with pending outbox,
  recovery, historical-only evidence, redaction, prompt bounds, and draft-only
  wording. This is candidate source only; deployed 0.8.1 behavior is unchanged
  until a separately reviewed new bundle is built and activated.

- [x] 5. Add the Outlook/SMTP adapter, initially with test delivery only.

  Reuse the approved email-delivery pattern already used on the main
  workstation after its configuration and credential boundary have been
  reviewed. Keep credentials outside Git and state, recipients allowlisted,
  sending disabled by default, and delivery driven only through the outbox.

  Completion requires an explicit delivery approval, one controlled message to
  a test recipient, sanitized success/failure evidence, idempotent retry proof,
  and confirmation that production recipients and legacy alerts are unchanged.

  Source preflight 2026-08-14: `monitoring_agent/delivery.py` adds a
  disabled-by-default test-only delivery adapter, in-memory delivery policy,
  in-memory envelope builder, sanitized delivery attempt result, an in-memory
  allowlist derived from the exact controlled test recipient, outbox-driven
  due-claim/send/result workflow, and a standalone `send_email_outlook()`
  backend called through `OutlookEmailTransport`. That backend mirrors the
  existing local alarm-email Office365 STARTTLS pattern and reads `O_EMAIL`
  and `O_APP` from the already-loaded `.env` or process environment for SMTP
  login/default sender, with `EMAIL`/`APP` accepted only as compatibility
  fallback. Disabled policy does not claim outbox items or mutate state.
  Enabled mode is restricted to `test`, requires
  `DELIVERY_TEST_RECIPIENT`, and never writes recipients, credentials, sender,
  message body, or transport exception text to `incident_state.json` or
  sanitized results. `monitoring_agent/delivery_cli.py` adds operator entry
  points for optional recipient hashing diagnostics, synthetic local outbox
  preparation, dry-run without claim, and confirmed `send-due`; synthetic
  preparation requires `--confirm PREPARE_SYNTHETIC_DELIVERY_TEST_STATE` and
  refuses an existing state file unless explicitly overridden. `send-due`
  rejects `.env` report files, requires
  `--confirm SEND_TEST_DELIVERY`, reads `.env` by default but loads only the
  delivery keys required by the selected command without printing values,
  requires `DELIVERY_TEST_RECIPIENT`, `O_EMAIL`, and `O_APP`, and claims only
  an exact `report_reference` and optional `idempotency_key`.
  Delivery-test recipient variables intentionally avoid the `MONITORING_AGENT_`
  prefix so they do not collide with the strict runtime schema; the polling
  runtime now validates only `MONITORING_AGENT_*` keys, allowing non-prefixed
  delivery keys to remain in the same local `.env`. Focused tests cover
  disabled no-op behavior,
  allowlist failure without claim, sent-once idempotence, missing report
  failure, retry/dead-letter state, exact claim filtering, CLI confirm-before
  credentials/report behavior, synthetic prepare confirm/no-write behavior,
  synthetic outbox/report creation, body redaction/bounds, and
  `send_email_outlook()` STARTTLS/retry behavior using fake SMTP only.

  Git test-checkout update 2026-08-14: after the user selected direct Git
  pulls instead of a new ZIP/version for every test change, the candidate
  source was pushed to
  `https://github.com/mtravnicekarmex/monitoring-agent-0.8.1.git` on
  `master` as commit `5cfc5916d3e83cdcc1eecd34f3f2719d62ec351c`. Treat the
  Git commit hash as the active test-checkout identity; the original 0.8.1 ZIP
  identity remains historical release evidence only until a new bundle is
  explicitly built.

  Controlled remote delivery proof 2026-08-14: the supervision station
  confirmed the active checkout at commit
  `5cfc5916d3e83cdcc1eecd34f3f2719d62ec351c`. The user had added
  `O_EMAIL`, `O_APP`, and `DELIVERY_TEST_RECIPIENT` to the station-local
  `.env` without printing values. `hash-recipient` printed only the recipient
  hash. `prepare-synthetic` created one isolated
  `endpoint:system_database` outbox item and sanitized report with
  `report_reference="controlled-test-report:v1:synthetic-endpoint-system-database"`;
  `dry-run` returned `due_count=1`; and the explicitly confirmed
  `send-due` command returned sanitized success evidence:
  `status="sent"`, `action="opened"`, `attempt_count=1`, and
  `error_code=null`. A follow-up dry-run for the same `idempotency_key`
  returned `due_count=0`, proving the synthetic item was no longer pending for
  re-send. This completes item 5 for the test-only delivery boundary.
  The adapter is not wired into the polling loop, no production recipient was
  introduced, no automatic delivery was enabled, and legacy alerts remain
  unchanged.

- [x] 6. Add agentic interpretation above confirmed incidents.

  Invoke interpretation only for confirmed, normalized incidents. Treat its
  output as bounded hypotheses and recommended diagnostic steps, never as
  observed fact. Define provider/model configuration, timeout and cost bounds,
  prompt/output contracts, redaction, failure fallback, and audit metadata.

  Completion requires synthetic evaluation cases, safe fallback to the pure
  deterministic report, and proof that interpretation cannot mutate the
  monitored application, start remediation, or suppress deterministic alerts.

  Completion 2026-08-14: `monitoring_agent/interpretation.py` adds
  interpretation contract version 1 as a pure draft-only layer over supplied
  `MonitoringReportSnapshot` objects. It invokes an injected provider only
  when policy is explicitly enabled in `mode="draft"` and the snapshot
  contains at least one confirmed active incident. Candidate-only evidence,
  disabled policy, missing provider, provider exception, invalid output, or
  unsafe output all fall back to the deterministic report from
  `monitoring_agent/reporting.py`. The policy records provider name, model
  name, timeout, prompt/output limits, item-count limits, and cost ceiling,
  while requiring `allow_network`, `allow_state_mutation`,
  `allow_process_control`, `allow_delivery`, and `allow_alert_suppression` to
  remain false. The module adds no `.env` keys, no provider credentials, no
  network client, no polling-loop integration, and no state writes. Results
  retain deterministic summary status, confirmed incident keys, prompt hash,
  prompt length, provider/model audit metadata, sanitized hypotheses,
  recommended read-only checks, evidence gaps, coarse error code, and an
  explicit safety boundary; prompts and provider exception text are not
  persisted in result dictionaries. Focused tests cover disabled and
  candidate skip behavior, confirmed active invocation, missing-provider and
  provider-exception fallback, unsafe-output rejection, redaction/bounds,
  permission-flag rejection, and prompt gating.

  Git test-checkout update 2026-08-14: item 6 source was pushed to
  `https://github.com/mtravnicekarmex/monitoring-agent-0.8.1.git` on
  `master` as commit `86ee42b058c74675976904c1e51a2f3677c5f138`
  (`Add draft interpretation contract`). The standalone manifest now declares
  19 runtime files including `monitoring_agent/interpretation.py`.

  Remote checkout proof 2026-08-14: the supervision station verified
  `git rev-parse HEAD` at `86ee42b058c74675976904c1e51a2f3677c5f138`.
  `--check-config` returned endpoint count 9, env contract 2, and mode
  `test`. Audit-v7 then reported 289 complete cycles, latest heartbeat
  `healthy`, nine latest observations, zero latest transport failures, valid
  endpoint/cycle order, valid retry/attempt bounds, no incomplete state, clean
  open continuous lifecycle, and zero new concurrent-start, run-reentry,
  unclean, abandoned, or overlap evidence.

- [x] 7. Run a shadow pilot against the current alerts.

  Operate the new incident, report, delivery-test, and interpretation layers in
  shadow mode while the existing alert path remains authoritative. Compare
  incident detection, confirmation delay, recoveries, duplicate rate, false
  positives, false negatives, and blind spots over a reviewed period.

  Completion requires a written comparison and separate approval before any
  legacy alert is replaced, disabled, or rerouted.

  Source preflight 2026-08-14: `monitoring_agent/shadow_pilot.py` adds
  shadow-pilot comparison contract version 1. It consumes supplied sanitized
  `monitoring_agent` and `legacy_alert` detection/recovery events for a
  start-inclusive/end-exclusive reviewed period, deduplicates each stream with
  a configured duplicate window, matches agent and legacy events by
  `incident_key` inside a configured match window, and produces
  `mode="shadow_only"` metrics for matched detections, confirmation delay,
  matched recoveries, recovery delay, duplicate counts/rates, false positives,
  false negatives, agent/legacy-only recoveries, and blind spots. The module
  has no `.env` reads, DB access, endpoint polling, delivery, provider calls,
  state writes, process control, remediation, or alert-suppression capability.
  `events_from_incident_evaluation()` converts current incident lifecycle
  transitions into comparable shadow events, and
  `render_shadow_pilot_comparison()` renders a bounded redacted operator
  summary. Focused tests cover matching, mismatches, duplicates, recoveries,
  period boundaries, blind spots, sanitization, event conversion, and input
  immutability. This was source preflight only until the 2026-08-17 no-event
  baseline and synthetic mechanics proofs below completed the item-7
  comparison scope.

  Git test-checkout update 2026-08-14: item 7 source was pushed to
  `https://github.com/mtravnicekarmex/monitoring-agent-0.8.1.git` on
  `master` as commit `3e7b94e9045527a1254b10066a3a34493577f025`
  (`Add shadow pilot comparison contract`). The standalone manifest now
  declares 20 runtime files including `monitoring_agent/shadow_pilot.py`;
  `manifest.sha256` is
  `80f0539d3a4de8410e137664cc7122cdc47b8baa4b7190d323d3eea9b3ca5155`.

  Remote checkout proof 2026-08-14: the supervision station verified
  `git rev-parse HEAD` at `3e7b94e9045527a1254b10066a3a34493577f025`.
  `--check-config` returned endpoint count 9, env contract 2, and mode
  `test`. After an elevated `Start-ScheduledTask`, audit-v7 reported
  323 complete cycles, outcome counts 317 healthy and 6 partial failure,
  latest heartbeat `healthy`, nine latest observations, zero latest transport
  failures, valid endpoint/cycle order, valid retry/attempt bounds, no
  incomplete state, clean open continuous lifecycle, and zero new
  concurrent-start, run-reentry, unclean, abandoned, or overlap evidence. This
  proved the pulled item-7 checkout did not regress the observer. The remaining
  reviewed-period requirement was completed later on 2026-08-17.

  Source update 2026-08-17: `monitoring_agent/runtime_shadow.py` wires the
  deterministic incident lifecycle into the polling loop in shadow mode. After
  each completed observation cycle, the runner evaluates the current cycle
  with previous persisted incident states, applies the result to
  `IncidentStateStore`, persists bounded `incident_state.json`, and prints a
  sanitized `shadow_incidents` summary in the `observation_cycle` event. This
  creates normalized incident states, sanitized transition records, and
  delivery-intent outbox items only; the polling loop still does not claim
  outbox items, send email, call an interpretation provider, mutate the
  monitored application, control processes, remediate, or suppress/replace
  legacy alerts. No new `.env` variables are required; env v1/v2 continue to
  use conservative default incident/outbox limits and env v3 can set explicit
  limits. `--audit-state` now uses audit contract 8 and adds aggregate
  `shadow_incidents` counts with `mode="shadow_only"` and
  `delivery_enabled=false`; raw transitions, report bodies, recipients,
  credentials, and endpoint payloads are not printed. Local verification
  passed with `91 passed` for targeted runtime-shadow/agent tests and
  `169 passed` for the broader monitoring-agent matrix. The source was pushed
  to the standalone Git repository on `master` as commit
  `207fc1d38d066cdc642dc86bc0cc0b2b6c817cfc`
  (`Wire shadow incident persistence`). The Git manifest keeps
  `bundle_version="0.8.1-test-git"`, declares 21 runtime files including
  `monitoring_agent/runtime_shadow.py`, and has manifest SHA-256
  `4011bb7de330b30371199123dca41aabaaddecd267293dadf990c91f57445287`.
  This remains unproved on the supervision station until pulled and audited
  there.

  Remote activation finding 2026-08-17: the supervision station pulled
  `207fc1d38d066cdc642dc86bc0cc0b2b6c817cfc`, but `MonitoringAgentTest`
  exited with `LastTaskResult=1` and foreground `--once` reported
  `client setup error: external web URL is required by the endpoint set`.
  Root cause: env contract 2 includes `MONITORING_AGENT_EXTERNAL_WEB_URL`, but
  `RuntimeSettings.load()` loaded it only for env v3. Commit
  `e23f5f893d76951995a8b6df833e60aadb96a858`
  (`Load external web URL for env v2`) fixes the source by loading and
  validating that URL for env v2 as well; no `.env` change is required. The
  new Git manifest declares 21 runtime files and has SHA-256
  `b15c3d6288352c051a30e5693ea710b19b826d7c62bd6e803be0b79163e7d113`.

  Remote proof 2026-08-17: the supervision station pulled
  `e23f5f893d76951995a8b6df833e60aadb96a858`. `--check-config` stayed valid
  with env contract 2, endpoint count 9, and mode `test`. Foreground `--once`
  completed one nine-observation success cycle and created
  `incident_state.json`; audit-v8 then reported
  `shadow_incidents.present=true`, `mode="shadow_only"`,
  `delivery_enabled=false`, `state_count=0`, and `outbox_count=0`. After
  restarting `MonitoringAgentTest`, the task was `Running` and audit-v8
  retained latest heartbeat `healthy`, nine latest observations, zero latest
  transport failures, and updated shadow state at
  `2026-08-17T07:00:53.832229+00:00`. The retained lifecycle/sequence
  findings (`unclean_restart_count=2`, `start_while_prior_run_open_count=2`,
  `abandoned_unclosed_run_count=1`, `cycle_sequence_valid=false`) are
  qualified as planned activation artifacts from the stopped long-running
  process and foreground `--once`, not as current writer or delivery
  failures. This remained short of item-7 completion until the file-based
  reviewed comparison workflow was pulled and proved.

  Source update 2026-08-17: `monitoring_agent/shadow_pilot_cli.py` adds
  file-based operator entry points for the reviewed-period comparison.
  `export-agent-events` reads an explicit agent-owned `incident_state.json`
  and emits comparable `monitoring_agent` events for a supplied reviewed
  period. `compare` consumes either those exported agent events or the state
  file plus a supplied sanitized `legacy_alert` event JSON file and can write
  bounded JSON/Markdown comparison outputs. The CLI does not read `.env`,
  inspect production DBs or mailboxes, poll endpoints, send email, claim
  outbox items, call providers, mutate state, control processes, remediate,
  or suppress/replace alerts. Focused shadow-pilot tests now pass with
  `13 passed`; the `tests/test_monitoring_agent*.py` matrix passes with
  `159 passed`; Python compileall passed; `git diff --check` passed with
  line-ending warnings only. The standalone Git repository was pushed on
  `master` as commit `3c6502c74d478a7518d3bbc37f7799951bbbaba4`
  (`Add shadow pilot file comparison CLI`) with a 22-file Git manifest
  SHA-256
  `f10e0392b2e294956f522f62df270859fad7c153ba4dee6a7fbac2fbba760c11`.
  Remote proof 2026-08-17: the supervision station pulled
  `3c6502c74d478a7518d3bbc37f7799951bbbaba4`; `--check-config` stayed valid
  with env contract 2, endpoint count 9, and mode `test`. Audit-v8 reported
  latest heartbeat `healthy`, nine latest observations, zero latest transport
  failures, current-run observation count 315, and
  `shadow_incidents.present=true`, `mode="shadow_only"`,
  `delivery_enabled=false`, `state_count=0`, `outbox_count=0`, updated at
  `2026-08-17T07:34:19.759021+00:00`. The retained lifecycle/sequence
  findings remain planned activation artifacts. This proved the source and
  remote runtime needed for item-7 comparison execution.

  Local legacy input update 2026-08-17:
  `scripts/export_database_availability_shadow_events.py` exports delivered
  database-availability events from the local SQLite store as sanitized
  `legacy_alert` JSON for `endpoint:system_database`, without `.env`, email,
  raw `reason` text, or state mutation. Local inspection found six delivered
  historical DB-availability events on 2026-06-13 and 2026-07-18, outside the
  current shadow-runtime period; current scheduler logs did not show matching
  alert/error patterns. Exporter/CLI/shadow tests passed with `15 passed`.

  Remote no-event baseline comparison 2026-08-17: for reviewed period
  `2026-08-17T07:00:00+00:00 <= event <
  2026-08-17T07:35:00+00:00`, the supervision station exported agent events
  from `incident_state.json`, supplied an explicitly empty sanitized
  `legacy_alert` event file, and generated a comparison report at
  `2026-08-17T07:52:10.639549+00:00`. All matched detection, false-positive,
  false-negative, recovery, duplicate, and blind-spot counts were zero. This
  proved the CLI/report workflow for a no-event period and the healthy
  current-alert baseline.

  Remote synthetic mechanics proof 2026-08-17: because the real monitored
  system was healthy and no current incident/legacy alert was available or
  desirable to wait for, the supervision station ran a file-only synthetic
  comparison for `2026-08-17T08:00:00+00:00 <= event <
  2026-08-17T09:00:00+00:00`. The synthetic input produced one matched
  `endpoint:system_database` detection, one matched recovery, one
  agent-only `endpoint:system_proxy` detection, and one legacy-only
  `endpoint:system_scheduler` detection. The generated report at
  `2026-08-17T08:07:12.386903+00:00` reported matched detections 1,
  false positives 1, false negatives 1, matched recoveries 1, recovery-only
  mismatches 0, duplicate counts 0/0, blind spots 0/0/0, and both
  confirmation and recovery delay as agent later by 60 seconds. The safety
  boundary stated that legacy alerts remain authoritative and that no alert
  may be replaced, disabled, rerouted, or downgraded without separate
  approval.

  Item-7 completion 2026-08-17: the real reviewed period proved the healthy
  no-event case against current alerts, and the file-only synthetic comparison
  proved the mismatch/delay/recovery metrics without inducing or waiting for
  an operational incident. This completes item 7 for the test-stage
  monitoring agent. It does not authorize legacy alert replacement,
  production delivery, real interpretation-provider execution, remediation,
  process control, or item-8 local agents.

- [x] 8. Build the first local agents on the same small contracts.

  Place data-bearing agents on the main workstation beside the sensitive data
  they need. Reuse the common versioned observation, incident, report, and
  capability envelopes, while keeping domain collection and evaluation local.
  Expose only safe aggregates to the supervision center.

  Completion requires each local agent to remain independently operable during
  a supervision-center or future-orchestrator outage and to retain its own
  bounded state and deterministic behavior.

  Source/local proof 2026-08-17: the first local data-bearing agent is
  `local_monitoring_agents/database_availability.py`. It reads the scheduler's
  local `database_availability.sqlite3` store in SQLite read-only mode,
  derives deterministic aggregate status/counts, and writes only bounded
  sanitized agent-owned state under the ignored
  `.local-monitoring-agent-state/` directory with its own writer lock.
  `scripts/run_database_availability_local_agent.py` runs that agent once
  without registering a task. The authenticated monitoring facade now exposes
  the safe aggregate at
  `/api/v1/monitoring/health/local-agents/database-availability`; the route
  reads local-agent state only and does not mutate scheduler/application
  state. The projection omits raw `reason`, service labels, SQLite paths, SQL,
  credentials, logs, and file contents.

  Local one-shot proof 2026-08-17: running the script against the real local
  store returned sanitized `status="ok"`, `service_count=2`,
  `pending_event_count=0`, `unavailable_service_count=0`, and
  `stale_service_count=0`. Focused verification returned `19 passed` for
  `tests/test_database_availability_local_agent.py` and
  `tests/test_monitoring_facade.py`; compileall passed for the new local
  agent, runner, route, schema, projector, and tests.

  Item 8 remains open after this first local-agent proof. Do not advance to
  item 9/orchestrator design until at least one additional local-agent
  candidate and controlled local scheduling/facade polling proof exist. Do not
  add the new local-agent endpoint to the supervision center's polling set or
  change remote `.env` without a separate controlled runtime-contract step.

  Source/local proof update 2026-08-17: the second local data-bearing agent is
  `local_monitoring_agents/scheduler_metrics.py`. It reads the local scheduler
  metrics JSON in read-only mode, interprets naive scheduler timestamps as
  Europe/Prague local time, normalizes raw job `last_status` values into
  bounded classes, and writes sanitized agent-owned state under
  `.local-monitoring-agent-state/`. The authenticated monitoring facade now
  also exposes
  `/api/v1/monitoring/health/local-agents/scheduler-metrics`, limited to safe
  aggregate scheduler/job counts, heartbeat age, job IDs, normalized job
  statuses, and 24h success/failure counts. The projection omits labels,
  descriptions, raw skipped reasons, logs, paths, `.env`, raw metrics JSON,
  and file contents.

  Controlled scheduling helper update 2026-08-17:
  `scripts/register_database_availability_local_agent_task.ps1` can register
  the first local agent as a limited current-user recurring task with
  `IgnoreNew`, project-root working directory, and a two-minute execution
  limit. The helper itself does not start/stop/unregister tasks.

  Local proof update 2026-08-17: the DB-availability one-shot/facade proof
  remained `status="ok"` with two services and zero pending/unavailable/stale
  counts. The scheduler-metrics one-shot/facade proof returned
  `status="degraded"`, `scheduler_running=true`, `job_count=51`,
  `success_count_24h=2594`, `failure_count_24h=0`, `error_job_count=2`, and
  `degraded_job_count=0`; this is fail-visible historical last-error evidence,
  not a 24h failure count. Focused local-agent/facade/shadow verification
  returned `40 passed`; compileall passed.

  At this source/local-proof point, item 8 still remained open for controlled
  local Scheduled Task execution and facade polling evidence. Do not advance
  to item 9/orchestrator design and do not add local-agent endpoints to the
  supervision center polling set without a separate controlled runtime-contract
  step.

  Local Scheduled Task proof 2026-08-17: the first local agent was registered
  as `MonitoringDatabaseAvailabilityLocalAgent` using
  `scripts/register_database_availability_local_agent_task.ps1`. The task uses
  the project `.venv` Python, project-root working directory, current-user
  limited principal, `IgnoreNew`, `StartWhenAvailable`, five-minute
  repetition, and a two-minute execution limit. A manual run completed with
  `LastTaskResult=0`; the first automatic trigger ran at
  `2026-08-17 13:23:21 +02:00` with `LastTaskResult=0`,
  `NumberOfMissedRuns=0`, and next run `2026-08-17 13:28:21 +02:00`. The
  local facade aggregate after the scheduled run remained `status="ok"`,
  `service_count=2`, `pending_event_count=0`,
  `unavailable_service_count=0`, and `stale_service_count=0`.

  Item 8 remains open after this proof for the scheduler-metrics task/facade
  runtime proof or a reviewed decision to run both local agents through one
  shared local runner. The supervision center polling set and remote `.env`
  remain unchanged.

  Shared-runner decision/proof 2026-08-17: the selected direction is one
  shared local runner for approved local agents, not one Scheduled Task per
  agent. `scripts/run_local_monitoring_agents.py` runs DB availability and
  scheduler metrics in deterministic order while each agent keeps its own
  state file and writer lock. The runner prints only a sanitized aggregate
  `local_monitoring_agents_cycle`; agent-reported `degraded` or `error` is
  monitoring evidence and does not make the runner fail. Runner failure is
  reserved for execution/schema exceptions.

  `scripts/register_local_monitoring_agents_task.ps1` can register the shared
  runner as a limited current-user recurring task with `IgnoreNew`,
  project-root working directory, and a three-minute execution limit. It was
  parsed successfully.

  Manual shared-runner proof against real local sources returned overall
  `status="degraded"` with DB availability `status="ok"` and scheduler
  metrics `status="degraded"`, `scheduler_running=true`, `job_count=51`,
  `success_count_24h=2594`, `failure_count_24h=0`, `error_job_count=2`, and
  `degraded_job_count=0`. Verification returned `43 passed`, shared registrar
  parse OK, and compileall passed.

  Shared Scheduled Task migration proof 2026-08-17:
  `MonitoringDatabaseAvailabilityLocalAgent` was retired and verified absent.
  `MonitoringLocalAgents` was registered as the active local monitoring task
  with project `.venv` Python, project-root working directory, current-user
  limited principal, `IgnoreNew`, `StartWhenAvailable`, five-minute
  repetition, and a three-minute execution limit. Manual run proof completed
  at `2026-08-17 13:41:50 +02:00` with `LastTaskResult=0`. The first
  automatic trigger completed at `2026-08-17 13:42:32 +02:00` with
  `LastTaskResult=0`, `NumberOfMissedRuns=0`, and next run
  `2026-08-17 13:47:32 +02:00`.

  Sanitized facade projections after the automatic trigger had no evidence
  gaps. DB availability reported `status="ok"`, `service_count=2`,
  `pending_event_count=0`, `unavailable_service_count=0`, and
  `stale_service_count=0`. Scheduler metrics reported `status="degraded"`,
  `scheduler_running=true`, `job_count=51`, `success_count_24h=2594`,
  `failure_count_24h=0`, `error_job_count=2`, and `degraded_job_count=0`.
  The degraded scheduler-metrics result is fail-visible historical last-error
  evidence with zero failures in the last 24 hours.

  Item 8 is complete. The supervision center polling set and remote `.env`
  remain unchanged until a separate runtime-contract step.

- [x] 9. After two or three agents, design the orchestrator from observed
  shared needs.

  Locate the orchestrator on the supervision workstation. Let it correlate
  safe agent results across domains, but initially give it no authority to
  start, stop, restart, reconfigure, or otherwise control individual agents.
  Do not move sensitive main-workstation data into the orchestrator.

  Completion requires evidence from at least two, preferably three, working
  agents; an inventory of genuinely shared contracts and workflows; failure
  isolation semantics; and a separately reviewed orchestrator architecture.

  Design update 2026-08-17:
  `MONITORING_ORCHESTRATOR_DESIGN.md` records the accepted item-9
  architecture baseline based on three verified agent surfaces: the remote external
  monitoring agent, the DB-availability local agent, and the scheduler-metrics
  local agent. It inventories the observed shared needs, including
  stable agent identity, bounded status vocabulary, freshness/staleness,
  evidence gaps, safe aggregate projections, lifecycle/single-writer proof,
  incident/report references, and shadow comparison workflows.

  The accepted design places the orchestrator on the supervision workstation and limits
  v1 to read-only correlation over center-owned audit summaries, file-only
  sanitized snapshots, and later approved GET-only facade reads. It explicitly
  excludes local raw data, dynamic discovery, process control, remediation,
  delivery, interpretation-provider execution, remote `.env` changes,
  polling-set changes, and legacy-alert replacement.

  The architecture was reviewed and accepted step by step with the user on
  2026-08-17. The next approved implementation scope is file-only/shadow-only
  orchestrator CLI over sanitized sample snapshots, with no live polling,
  scheduling, delivery, provider execution, remediation, process control, or
  alert replacement.

  File-only source update 2026-08-17:
  `monitoring_agent/orchestrator.py` and
  `monitoring_agent/orchestrator_cli.py` implement the approved
  file-only/shadow-only orchestrator CLI. It consumes a static registry and
  sanitized source snapshot files, supports `agent_snapshot_v1`,
  `local_agent_facade_v1`, and `remote_agent_audit_v8`, normalizes
  status/freshness/evidence gaps/counts, computes bounded correlation
  findings, rejects duplicate agent identities, and rejects `.env` source
  files. `monitoring_agent/orchestrator_export_cli.py` later added
  file-only wrapping of supplied sanitized remote `--audit-state` JSON with
  `captured_at`. These components perform no live polling, `.env` reads,
  state mutation, delivery, provider execution, process control, remediation,
  scheduling, deployment, or alert replacement.

  Verification returned `8 passed` for
  `tests/test_monitoring_agent_orchestrator.py` and `49 passed` for the
  focused orchestrator/shadow/local-agent/facade set before the timestamp
  wrapper; the later wrapper verification is recorded below.

  Local-only preflight 2026-08-18:
  `scripts/export_monitoring_orchestrator_local_inputs.py` exports the two
  local sanitized facade aggregates and writes a static local-only registry.
  After refreshing local agent state through the shared runner, the preflight
  wrote artifacts under
  `artifacts/monitoring/orchestrator/2026-08-18-file-only-pilot/` and
  produced an orchestrator result with two fresh sources, no evidence gaps,
  overall `status="degraded"`, and correlation
  `scheduler_historical_error_states_no_recent_failures`. At that point the
  full three-surface file-only pilot still required a current sanitized
  remote audit JSON from the supervision station; it completed later on
  2026-08-18.

  Full file-only pilot 2026-08-18: the supervision station supplied a
  sanitized audit-v8 `--audit-state` JSON. The full registry consumed
  `external_health`, `database_availability`, and `scheduler_metrics` from
  files only and wrote `orchestrator-full-pilot.json` and
  `orchestrator-full-pilot.md`. The result had three fresh sources, two
  `ok` sources, one `degraded` source, no unavailable/error/invalid/stale
  sources, and overall `status="degraded"`. `external_health` was `ok` with
  evidence gaps `heartbeat_transition_history_not_persisted` and
  `source_timestamp_missing`; DB availability was `ok`; scheduler metrics was
  `degraded` with `failure_count_24h=0`, `error_job_count=2`, and
  `job_count=51`. The only correlation was
  `scheduler_historical_error_states_no_recent_failures`. This completed the
  approved file-only pilot without live polling, deployment, scheduling,
  remote `.env` or polling-set change, delivery, provider execution,
  remediation, process control, or alert replacement.

  Captured-audit rerun 2026-08-18:
  the supplied remote audit was wrapped with `captured_at` through
  `python -m monitoring_agent.orchestrator_export_cli wrap-remote-audit` and
  the file-only pilot was rerun, writing
  `orchestrator-full-pilot-captured.json` and
  `orchestrator-full-pilot-captured.md`. The overall result remained
  `status="degraded"` with `external_health status="ok"`,
  `database_availability status="ok"`, `scheduler_metrics status="degraded"`,
  and correlation `scheduler_historical_error_states_no_recent_failures`.
  `external_health` retained only
  `heartbeat_transition_history_not_persisted`; `source_timestamp_missing`
  was removed. Verification returned `18 passed` for focused
  orchestrator/export/helper tests, `190 passed` for the broader
  monitoring-agent/local-agent set, Python compileall passed, and
  `git diff --check` passed.

  Standalone Git publication 2026-08-21:
  after the supervision station reported `No module named
  monitoring_agent.orchestrator_export_cli`, the item-9 orchestrator/export
  modules were published to the standalone repository on `master` as commit
  `f6583d80a77695b3f4a094337251c6835b389b59`
  (`Add orchestrator file-only export CLI`). The commit adds
  `monitoring_agent/orchestrator.py`,
  `monitoring_agent/orchestrator_cli.py`, and
  `monitoring_agent/orchestrator_export_cli.py`, updates README, and
  regenerates `manifest.json`/`manifest.sha256` with 25 runtime files and
  manifest SHA-256
  `37e2967efa4edbf5cfcfdeaa5a9bb8e073ef417fd2499ed058cf7085a8daf61b`.
  Temporary standalone verification compiled the package, loaded wrapper
  help, wrapped a sample stdin audit with `captured_at`, and verified all
  manifest-declared hashes. The supervision station then verified the pull on
  2026-08-21: `git rev-parse HEAD` returned
  `f6583d80a77695b3f4a094337251c6835b389b59`,
  `run_monitoring_agent.py --check-config` returned endpoint count 9, env
  contract 2, and mode `test`, and
  `monitoring_agent.orchestrator_export_cli wrap-remote-audit` wrote
  `remote-audit.json` with `event="agent_state_audit"`,
  `audit_contract_version=8`, and
  `captured_at="2026-08-21T05:21:19.603716Z"`.

  Remote runtime sample 2026-08-21:
  after a 180-second wait, the supervision station reported
  `MonitoringAgentTest` `State=Running` and audit contract 8. Latest heartbeat
  was `healthy` with nine latest observations, zero latest transport failures,
  and consistency with the last complete cycle/run. Endpoint sequence,
  retry/attempt bounds, timing budget, and single-writer history were valid;
  there were no in-progress/incomplete observations, concurrent starts,
  run-reentries, overlaps, or process-run transitions. Retained lifecycle
  artifacts were `unclean_restart_count=3`,
  `start_while_prior_run_open_count=3`, and
  `abandoned_unclosed_run_count=2`. Shadow incidents remained
  `mode="shadow_only"` and `delivery_enabled=false`, with
  `active_state_count=1`, `resolved_state_count=2`, `state_count=3`,
  `outbox_pending_count=11`, and update time
  `2026-08-21T05:28:14.530041+00:00`.
  Follow-up sanitized incident-state inspection on 2026-08-21 confirmed the
  active incident as `endpoint:system_scheduler`, opened at
  `2026-08-20T00:17:37.512339+02:00`, with
  `last_reason="endpoint_payload_status:degraded"`. The user tied this to the
  last two days' midnight `daily_job` failure in
  `SOFTLINK_save_to_database_all`. The outbox has only one pending `opened`
  item for this scheduler incident, so the pending count is not repeated
  email-delivery creation. Commit
  `601a50587c73627835d4860b2212a82a92670f12` was pushed on 2026-08-21 to
  collapse unchanged repeated `updated` transition records, document the
  steady-state five-minute polling profile (`300` second interval, `30`
  second jitter), and regenerate the 25-file Git manifest with SHA-256
  `07e08ccd56275a30e0169b863c60aee07241ba2f1c7126fb19989382c2c1a349`.
  Local verification passed. The supervision station then verified the pull,
  valid config, latest healthy audit, zero latest transport failures, a new
  310.977-second scheduled interval inside the 332-second allowed maximum,
  and no new repeated unchanged `endpoint:system_scheduler` `updated`
  transition records after the restarted 300-second runtime began.

  Automatic test-delivery follow-up 2026-08-21:
  commit `b6f4e047d59d14d0e34ac61c1a4e270b386f6ae9` was pushed to the
  standalone repository after the historical outbox was reviewed, one
  scheduler-opened test message was manually confirmed sent, and the remaining
  14 historical pending intents were operator-skipped. The commit adds
  `monitoring_agent/runtime_delivery.py`, an explicit
  `DELIVERY_AUTOMATION_ENABLED` gate, runtime delivery after completed cycles,
  and documentation for controlled automatic test delivery. The supervision
  station pulled the commit, enabled `DELIVERY_AUTOMATION_ENABLED=true`,
  restarted `MonitoringAgentTest`, and audit-v8 reported `State=Running`,
  latest heartbeat `healthy`, nine latest observations, zero latest transport
  failures, `delivery_enabled=true`, `outbox_pending_count=0`,
  `outbox_sent_count=1`, and `outbox_dead_letter_count=14`.
  This does not approve production recipients, provider execution,
  remediation, process control, alert suppression, or legacy-alert
  replacement. The agent is intentionally left running in this test mode for
  observation before further delivery-layer decisions.

## Agreed architecture direction

Complete one high-quality end-to-end monitoring agent first. Define only the
small common contracts already justified by that work. Add local agents next,
allow each agent to function when the supervision center or orchestrator is
unavailable, and build the full orchestrator only after two or three verified
agents reveal the real shared coordination needs.

The intended topology is:

- the supervision workstation hosts the external monitoring agent and later
  the orchestrator;
- local agents on the main workstation process sensitive data locally and
  expose only safe aggregates;
- the orchestrator correlates agent results but is not initially their
  lifecycle manager or remediation controller;
- loss of the orchestrator must not stop observation, deterministic incident
  evaluation, local state persistence, or independently configured delivery.
