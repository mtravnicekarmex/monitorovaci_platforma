# Monitoring Agent Implementation Roadmap

Prepared: 2026-08-06

Status: approved execution order; item 1 implementation and remote
nine-endpoint recovery proof passed with 0.8.1, but continuous Scheduled Task
restoration is still pending before starting item 2; no top-level roadmap item
completed yet

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

- [ ] 1. Extend the safe observation contracts and add an external web probe.

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
  four-endpoint HTTP-200 cycles. SmartFuelPass truthfully remains `error` as a
  known paused import state; successful transport/schema validation keeps
  observer self-health separate from that payload condition. Keep this item
  open only for the controlled remote 0.8 migration, one verified complete
  nine-observation cycle, and the audit-v7 mixed-history pass.

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
  denied (`HRESULT 0x80070005`). Resume on 2026-08-08 from elevated task
  registration, task start, 90-120 second wait, and read-only task/audit
  verification before starting item 2.

- [ ] 2. Define deterministic rules, thresholds, and the incident lifecycle.

  Specify versioned rules for confirmation, severity, deduplication, recovery,
  cooldown, recurrence, stale evidence, and historical-evidence qualification.
  Distinguish an endpoint incident, target-wide outage, observer self-health
  problem, and supervision-center blind spot.

  Completion requires reviewed rule tables, explicit transition semantics,
  deterministic clocks, and synthetic tests for opening, updating, recovering,
  reopening, and suppressing incidents.

- [ ] 3. Introduce a bounded incident store and delivery outbox.

  Persist only normalized incident state, transitions, report references, and
  delivery intent owned by the agent. Define bounded retention, atomic writes,
  idempotency keys, retry state, dead-letter handling, and crash recovery. The
  outbox must not itself imply that external sending is enabled.

  Completion requires retention and restart tests, duplicate-delivery
  prevention, corrupt-state fail-closed behavior, and proof that observation
  history cannot grow without a configured bound.

- [ ] 4. Implement a pure report and programming-agent prompt.

  Render a concise report from normalized facts without delivery side effects.
  Keep verified facts, rule conclusions, historical qualifications, and later
  hypotheses visibly separate. Produce a bounded programming-agent prompt that
  describes evidence, scope, safety constraints, requested diagnostics, and
  success criteria without embedding secrets or authorizing execution.

  Completion requires stable snapshot tests, redaction tests, useful healthy,
  degraded, incident, and recovery examples, and explicit confirmation that
  the prompt is a draft only.

- [ ] 5. Add the Outlook/SMTP adapter, initially with test delivery only.

  Reuse the approved email-delivery pattern already used on the main
  workstation after its configuration and credential boundary have been
  reviewed. Keep credentials outside Git and state, recipients allowlisted,
  sending disabled by default, and delivery driven only through the outbox.

  Completion requires an explicit delivery approval, one controlled message to
  a test recipient, sanitized success/failure evidence, idempotent retry proof,
  and confirmation that production recipients and legacy alerts are unchanged.

- [ ] 6. Add agentic interpretation above confirmed incidents.

  Invoke interpretation only for confirmed, normalized incidents. Treat its
  output as bounded hypotheses and recommended diagnostic steps, never as
  observed fact. Define provider/model configuration, timeout and cost bounds,
  prompt/output contracts, redaction, failure fallback, and audit metadata.

  Completion requires synthetic evaluation cases, safe fallback to the pure
  deterministic report, and proof that interpretation cannot mutate the
  monitored application, start remediation, or suppress deterministic alerts.

- [ ] 7. Run a shadow pilot against the current alerts.

  Operate the new incident, report, delivery-test, and interpretation layers in
  shadow mode while the existing alert path remains authoritative. Compare
  incident detection, confirmation delay, recoveries, duplicate rate, false
  positives, false negatives, and blind spots over a reviewed period.

  Completion requires a written comparison and separate approval before any
  legacy alert is replaced, disabled, or rerouted.

- [ ] 8. Build the first local agents on the same small contracts.

  Place data-bearing agents on the main workstation beside the sensitive data
  they need. Reuse the common versioned observation, incident, report, and
  capability envelopes, while keeping domain collection and evaluation local.
  Expose only safe aggregates to the supervision center.

  Completion requires each local agent to remain independently operable during
  a supervision-center or future-orchestrator outage and to retain its own
  bounded state and deterministic behavior.

- [ ] 9. After two or three agents, design the orchestrator from observed
  shared needs.

  Locate the orchestrator on the supervision workstation. Let it correlate
  safe agent results across domains, but initially give it no authority to
  start, stop, restart, reconfigure, or otherwise control individual agents.
  Do not move sensitive main-workstation data into the orchestrator.

  Completion requires evidence from at least two, preferably three, working
  agents; an inventory of genuinely shared contracts and workflows; failure
  isolation semantics; and a separately reviewed orchestrator architecture.

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
