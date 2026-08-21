# Monitoring orchestrator design

Date: 2026-08-17

Status: accepted architecture baseline for roadmap item 9. File-only CLI
implementation and pilot artifacts are recorded below. No runtime deployment,
live polling, remote polling-set change, production delivery, remediation, or
alert replacement is approved by this document. The later 2026-08-21
`DELIVERY_AUTOMATION_ENABLED=true` change is a separate controlled
test-recipient delivery gate for the remote monitoring agent, not orchestrator
delivery authority.

Related work: roadmap item 9 in
`MONITORING_AGENT_IMPLEMENTATION_ROADMAP.md`.

Review status: approved step by step with the user on 2026-08-17. Approved
topics were purpose/scope, evidence baseline, shared contracts, non-goals,
placement/data flow, registry and snapshot contract, correlation rules,
failure isolation, and pilot sequence.

## Purpose

Design the first monitoring orchestrator from observed shared needs across the
verified agents. The orchestrator is a correlation and reporting layer on the
supervision workstation. It is not a lifecycle manager and is not a
remediation controller.

## Evidence baseline

The design is based on three working agent surfaces:

| Agent surface | Location | Current runtime proof | Data boundary |
| --- | --- | --- | --- |
| External monitoring agent `MonitoringAgentTest` | Supervision workstation | Continuous remote `0.8.1-test`, latest checkpoint `b6f4e047...`, audit-v8 healthy, nine observations, shadow incidents present, controlled test delivery enabled, pending outbox zero | Polls approved GET-only monitoring facade endpoints and a credential-free external web probe; owns center-side observation/incident and test-delivery state |
| DB availability local agent | Main workstation | Shared local task `MonitoringLocalAgents`, DB availability aggregate `status="ok"`, no evidence gaps | Reads scheduler-owned SQLite availability state read-only; exposes sanitized aggregate only |
| Scheduler metrics local agent | Main workstation | Shared local task `MonitoringLocalAgents`, scheduler metrics aggregate `status="degraded"`, zero failures in the last 24 hours, no evidence gaps | Reads scheduler metrics JSON read-only; exposes sanitized aggregate only |

This is enough evidence to design shared contracts. It is not approval to move
raw main-workstation data to the supervision workstation.

## Observed shared needs

Only the following needs are genuinely shared across the current agents:

| Need | Why it is shared | v1 contract direction |
| --- | --- | --- |
| Stable agent identity | Correlation requires distinguishing remote health, DB availability, and scheduler metrics evidence | `agent_key`, `agent_kind`, `location`, `contract_version`, optional `source_version` |
| Bounded status vocabulary | Remote and local agents need comparable rollups without erasing domain meaning | Preserve source status; orchestrator rollup uses `ok`, `degraded`, `error`, `unavailable`, `unknown` |
| Freshness and staleness | A stale local aggregate is different from a healthy aggregate | Require `observed_at`, source `checked_at`/`state_updated_at`, age seconds, and stale threshold when available |
| Evidence gaps | Missing heartbeat, stale state, contract mismatch, or unavailable source must be visible without raw logs | Bounded string identifiers such as `source_unavailable`, `source_stale`, `source_contract_mismatch`, `clock_skew_suspected` |
| Safe aggregate projection | The center must correlate without receiving local raw data | Consume only approved facade responses or center-owned agent audit summaries |
| Single-writer/lifecycle proof | Duplicate writers and stale tasks are operationally important across agents | Record source lifecycle summary when provided; never infer raw process control authority |
| Incident/report references | Future reports need stable cross-agent references without message bodies or raw evidence | Use opaque `incident_key`, `report_reference`, and hashed/digest identifiers only |
| Shadow comparison | Existing item-7 proof showed file-only comparisons are useful and safe | Orchestrator pilot starts with file-only snapshots before live polling expansion |

## Non-shared boundaries

The following remain agent-specific and must not be centralized in v1:

- raw SQLite rows, scheduler metrics files, logs, SQL, file paths, labels,
  descriptions, skipped reasons, raw reports, raw measurements, device data,
  recipients, credentials, tokens, or `.env` values;
- domain-specific rule internals for DB availability, scheduler metrics,
  endpoint polling, incident confirmation, and recovery;
- agent writer locks, state write formats, retention internals, and local
  recovery procedures;
- Windows Scheduled Task registration details for individual local agents;
- delivery transports, interpretation providers, remediation actions, and
  legacy alert routing.

## Placement

The orchestrator belongs on the supervision workstation.

```text
Supervision workstation
|-- MonitoringAgentTest
|   |-- endpoint observations
|   |-- deterministic incident state
|   `-- audit/report summaries
|-- Monitoring orchestrator v1
|   |-- reads approved safe snapshots
|   |-- correlates status/freshness/evidence gaps
|   |-- writes orchestrator-owned summary state
|   `-- prepares draft operator summaries only
|
`-- no authority to control agents
       |
       | approved authenticated GET-only reads only
       v
Main workstation monitoring facade
|-- local-agents/database-availability
`-- local-agents/scheduler-metrics
```

The main workstation remains the only place where local data-bearing agents
read sensitive local sources. The facade remains the only cross-workstation
boundary for their results.

## Orchestrator v1 responsibilities

The v1 orchestrator may:

- read center-owned monitoring-agent audit/state summaries;
- read approved safe facade endpoints after a separate runtime-contract
  approval;
- consume file-only sanitized snapshots during the first pilot;
- validate schema/contract versions and reject invalid source payloads;
- compute per-agent freshness and status;
- correlate related degraded/error/unavailable evidence across agents;
- write orchestrator-owned bounded state and audit files on the supervision
  workstation;
- render draft operator summaries and programmer-task drafts that explicitly
  state their evidence gaps and non-authoritative status.

The v1 orchestrator may not:

- start, stop, restart, register, unregister, or reconfigure any agent or
  application task;
- connect to operational databases, shares, raw local files, logs, browser
  sessions, or secret stores;
- invoke delivery transports or interpretation providers;
- mutate application state, scheduler state, local-agent state, monitoring
  agent state, source code, or remote workstation configuration;
- suppress, replace, downgrade, reroute, or acknowledge legacy alerts;
- treat missing data as healthy.

## Agent registry contract

The orchestrator should use an explicit static registry in v1. Discovery is
not dynamic.

Minimum registry fields:

- `agent_key`: stable unique key, for example `external_health`,
  `database_availability`, `scheduler_metrics`;
- `agent_kind`: `remote_observer`, `local_facade_agent`, or future reviewed
  kind;
- `location`: `supervision_center` or `main_workstation`;
- `contract_version_min` and `contract_version_max`;
- `source`: file-only fixture, center-owned audit file, or approved facade
  endpoint;
- `stale_after_seconds`;
- `status_mapping_version`;
- `enabled`: explicit boolean.

Duplicate `agent_key` values are a fail-closed configuration error.

## Snapshot contract

The orchestrator should normalize every source into an internal
`AgentSnapshot` with these fields:

- `orchestrator_contract_version`;
- `agent_key`;
- `agent_kind`;
- `location`;
- `source_contract_version`;
- `observed_at`;
- `source_checked_at`;
- `source_state_updated_at`;
- `source_age_seconds`;
- `stale_after_seconds`;
- `status`;
- `freshness_status`: `fresh`, `stale`, `missing`, or `invalid`;
- `summary_counts`: bounded numeric counts only;
- `evidence_gaps`: bounded strings only;
- `source_digest`: hash of the normalized sanitized payload, not raw content.

The orchestrator must retain the original sanitized payload digest and enough
normalized aggregate fields to support audit, but must not persist raw local
payloads if they contain fields not on the explicit allowlist.

## Correlation rules v1

The first rule set should remain small:

1. If a source is missing, stale, or contract-invalid, mark only that source
   as unavailable/degraded and add an evidence gap. Do not degrade unrelated
   agents solely because one source is missing.
2. If external endpoint polling reports database failures and the local DB
   availability aggregate is also degraded/unavailable for the same period,
   classify the correlation as `database_path_confirmed`.
3. If scheduler endpoint polling is degraded while scheduler metrics reports
   zero recent failures but historical error job states, classify as
   `scheduler_status_mixed_evidence`.
4. If all sources are fresh and only scheduler metrics is degraded because of
   historical last-error states with zero 24h failures, keep the global rollup
   at `degraded`, not `error`.
5. If the facade itself is unavailable, do not infer that local agents failed;
   classify the local-agent evidence as `source_unavailable`.

These rules create operator context only. They do not change incident delivery
or legacy alert behavior.

## Failure isolation

| Failure | Required behavior |
| --- | --- |
| Orchestrator process fails | Remote monitoring agent and local agents continue independently; no local state is modified |
| One local agent state is stale | Mark that agent stale/unavailable; preserve other agents' latest valid status |
| Facade transport fails | Record transport/evidence gap; do not read local files directly |
| Contract mismatch | Reject the source payload and keep a bounded contract-mismatch evidence gap |
| Clock skew or timestamp regression | Preserve source timestamps, use `observed_at`, and record `clock_skew_suspected`; do not rewrite history |
| Duplicate agent identity | Fail closed before writing a new orchestrator snapshot |
| Orchestrator state write fails | Exit non-zero after source validation; do not retry by mutating agent-owned state |

## State and artifacts

Initial orchestrator state should be center-owned and separate from both the
remote monitoring agent state and local-agent state.

Proposed files for a later implementation:

- `orchestrator_state.json`: latest normalized aggregate snapshot;
- `orchestrator_history.jsonl`: append-only normalized source/correlation
  records;
- `orchestrator_audit.json`: current audit summary;
- `orchestrator_reports/`: draft markdown summaries only.

All files must be bounded or retained by explicit retention policy before
continuous scheduling.

## Pilot sequence

1. Review and accept this design. Completed on 2026-08-17.
2. Implement a file-only orchestrator CLI over sanitized sample snapshots.
   Source completed locally on 2026-08-17 in
   `monitoring_agent/orchestrator.py` and
   `monitoring_agent/orchestrator_cli.py`.
3. Add tests for registry validation, contract mismatch, staleness, duplicate
   agent keys, and correlation rules. Completed locally on 2026-08-17 in
   `tests/test_monitoring_agent_orchestrator.py`.
4. Run the file-only pilot with current remote audit and local facade
   aggregates exported manually. Completed on 2026-08-18.
5. Only after separate approval, add approved live GET-only facade reads for
   local-agent endpoints to the supervision-center runtime contract.
6. Run shadow-only live correlation; legacy alerts remain authoritative.
7. Review evidence before any delivery, interpretation-provider, or
   alert-layer integration.

## Acceptance criteria for roadmap item 9

Roadmap item 9 closed on 2026-08-17 after:

- this architecture was reviewed and accepted;
- the observed shared contract inventory above was retained;
- failure isolation semantics were accepted;
- no process-control/remediation/delivery/alert-replacement capability was
  introduced;
- the next implementation step was scoped as file-only orchestrator CLI over
  sanitized sample snapshots.

## File-only CLI implementation status

Implemented locally on 2026-08-17:

- `monitoring_agent/orchestrator.py` defines the file-only registry,
  normalized `AgentSnapshot`, bounded correlation findings, source
  freshness/status handling, sanitized payload digesting, and the approved v1
  correlation rules.
- `monitoring_agent/orchestrator_cli.py` provides
  `python -m monitoring_agent.orchestrator_cli run` over a supplied registry
  and supplied sanitized source files.
- `monitoring_agent/orchestrator_export_cli.py` provides
  `python -m monitoring_agent.orchestrator_export_cli wrap-remote-audit` for
  file-only wrapping of supplied sanitized remote `--audit-state` JSON with an
  explicit `captured_at` timestamp.
- Supported payload kinds are `agent_snapshot_v1`,
  `local_agent_facade_v1`, and `remote_agent_audit_v8`.
- Duplicate `agent_key` values fail closed before a snapshot is produced.
  Contract mismatch, stale source, invalid JSON, or missing source is isolated
  to the affected source with bounded evidence gaps.
- Source files named `.env` are rejected.

Verification on 2026-08-17:

- `tests/test_monitoring_agent_orchestrator.py` returned `8 passed`.
- The focused monitoring-agent/local-agent/facade set returned `49 passed`.

Still not approved:

- live polling;
- deployment or packaging;
- orchestrator Scheduled Task registration;
- remote `.env` or polling-set changes;
- delivery, interpretation-provider execution, remediation, process control,
  or alert replacement.

## File-only pilot progress

2026-08-18 local-only preflight:

- The shared local runner was executed once to refresh local agent-owned
  sanitized state. It returned DB availability `status="ok"` and scheduler
  metrics `status="degraded"` with `failure_count_24h=0`,
  `error_job_count=2`, and `job_count=51`.
- `scripts/export_monitoring_orchestrator_local_inputs.py` exported sanitized
  local facade aggregate snapshots under
  `artifacts/monitoring/orchestrator/2026-08-18-file-only-pilot/`.
- `python -m monitoring_agent.orchestrator_cli run` over the local-only
  registry wrote `orchestrator-local-preflight.json` and
  `orchestrator-local-preflight.md`.
- The local-only preflight result was `status="degraded"` with two fresh
  sources, no evidence gaps, and one correlation:
  `scheduler_historical_error_states_no_recent_failures`.

This is not the full three-surface pilot because the current remote
supervision-station audit JSON was not present on the main workstation. The
full file-only pilot remains pending a supplied sanitized
`run_monitoring_agent.py --audit-state` JSON export from the supervision
station.

2026-08-18 full three-surface file-only pilot:

- The supervision station supplied a sanitized `run_monitoring_agent.py
  --audit-state` JSON with audit contract 8. The latest heartbeat was
  `healthy`, with nine latest observations and zero latest transport failures.
- The remote audit also reported `shadow_incidents.present=true`,
  `mode="shadow_only"`, `delivery_enabled=false`,
  `shadow_outbox_pending_count=2`, and
  `shadow_transition_record_count=2000`.
- `scripts/export_monitoring_orchestrator_local_inputs.py` copied that audit
  into the pilot artifact directory and wrote a full three-agent registry.
- `python -m monitoring_agent.orchestrator_cli run` wrote
  `orchestrator-full-pilot.json` and `orchestrator-full-pilot.md`.
- The full pilot result had three fresh sources, two `ok` sources, one
  `degraded` source, no unavailable/error/invalid/stale sources, and overall
  `status="degraded"`.
- `external_health` was `ok` with evidence gaps
  `heartbeat_transition_history_not_persisted` and
  `source_timestamp_missing`. The latter is expected for the raw
  `--audit-state` JSON because it does not include a generated/checked
  timestamp.
- `database_availability` was `ok` with no evidence gaps.
- `scheduler_metrics` was `degraded` with no evidence gaps,
  `failure_count_24h=0`, `error_job_count=2`, and `job_count=51`.
- The only correlation was
  `scheduler_historical_error_states_no_recent_failures`.

This completed the approved file-only pilot. It did not add live polling,
deployment, packaging, scheduling, remote `.env` or polling-set changes,
delivery, provider execution, remediation, process control, or alert
replacement.

2026-08-18 remote-audit timestamp follow-up:

- `monitoring_agent/orchestrator_export_cli.py` was added so the supplied
  sanitized remote `--audit-state` JSON can be wrapped with `captured_at`
  before orchestration. The helper accepts file or stdin input, rejects `.env`
  paths, rejects non-`agent_state_audit` payloads, and mutates only the copied
  JSON output.
- The orchestrator remote-audit parser now uses `captured_at` before falling
  back to `checked_at` or `generated_at`.
- The full pilot was rerun with the wrapped remote audit and wrote
  `orchestrator-full-pilot-captured.json` and
  `orchestrator-full-pilot-captured.md`.
- The rerun result remained overall `status="degraded"` with
  `external_health status="ok"`, `database_availability status="ok"`,
  `scheduler_metrics status="degraded"`, and correlation
  `scheduler_historical_error_states_no_recent_failures`.
- `external_health` retained only the real evidence gap
  `heartbeat_transition_history_not_persisted`; `source_timestamp_missing`
  was removed.
- Verification returned `18 passed` for the focused
  orchestrator/export/input-helper tests, `190 passed` for the broader
  monitoring-agent/local-agent set, Python compileall passed, and
  `git diff --check` passed.
