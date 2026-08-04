# Scheduler Monitoring Agent Plan

Prepared: 2026-07-30

Status: design approved; unregistered synthetic test implementation started

Work item: `OPS-002`

## Purpose

Build the first application monitoring agent as an independent, read-only
supervisor of the existing scheduler and system health surfaces. The agent
must reuse the current health endpoints instead of duplicating their metric
collection. Its added value is evaluation over time, correlation, incident
memory, recovery detection, concise operational reporting, and preparation of
evidence-based programming tasks.

The first release is a test-mode observer. It does not replace the current
scheduler alert delivery.

## Existing sources of truth

The agent consumes safe, authenticated responses from the existing FastAPI
health boundary:

- `/health/system/scheduler`: scheduler heartbeat, aggregate status, scheduled
  job status, last/next run, duration, and 24-hour success/failure counts;
- `/health/scheduler`: detailed scheduled and internal-step metrics plus the
  expected 24-hour schedule; scheduler log and manual-run subroutes remain
  excluded;
- `/health/system/runtime`: Windows boot, startup task, required listeners,
  and temporary listener checks;
- `/health/system/database`: PostgreSQL availability, safe metadata, and
  expected schema status;
- `/health/system/proxy`: public routing and selected security checks;
- `/health/system/smartfuelpass`: aggregate synchronization and report status;
- `/health/live` and `/health/ready`: independent API liveness and readiness.

The initial agent must not parse raw measurements, query application
databases, inspect secrets, or reproduce the health collectors. A future
endpoint may be added only when a required, non-sensitive fact is unavailable
from the current API.

## Responsibility boundary

The existing layers retain these responsibilities:

- `main.py` and `core/scheduler/`: scheduling, job execution, locks, heartbeat,
  metrics, and current immediate scheduler alerts;
- health services and dashboard pages: deterministic current-state collection
  and administrator presentation;
- the monitoring agent: repeated observation, temporal rules, correlation,
  incident lifecycle, recovery tracking, reports, and programmer task drafts.

The agent must run on a different workstation from the `main.py` scheduler.
The remote runtime and private monitoring API boundary are defined in
`SCHEDULER_MONITORING_AGENT_REMOTE_RUNTIME_DESIGN.md`.

## Permission model

During test mode the agent may:

- authenticate to approved read-only health endpoints;
- write only to its own bounded state, audit, and report storage;
- redact and aggregate observations before retaining them;
- prepare local reports and draft programming tasks.

During test mode the agent must not:

- call manual-run endpoints;
- start, stop, restart, or reconfigure any process or Windows task;
- acquire or change scheduler locks;
- write application or operational database data;
- activate prediction, scoring, event, report, or alert workflows;
- send email, chat messages, tickets, pull requests, or other external
  notifications;
- read or reproduce tokens, credentials, cookies, DSNs, recipients, raw
  measurements, device identifiers, or full operational logs.

Authentication must use a dedicated least-privilege identity or an equivalent
approved mechanism. Reusing a human administrator session is not an accepted
production design.

## Evaluation model

Deterministic rules decide whether an observation is healthy, degraded,
failed, recovering, or unavailable. Agentic interpretation operates only on
the resulting safe facts.

The interpretation layer may:

- group related symptoms into one incident;
- describe impact and likely diagnostic areas;
- label hypotheses and confidence explicitly;
- recommend read-only checks;
- prepare a programming task with relevant modules, tests, and acceptance
  criteria.

It must not invent a root cause, silently change deterministic severity,
claim an unverified recovery, or turn a hypothesis into a fact.

## Incident lifecycle

Use stable incident identities derived from rule and affected component, not
from free-form generated text.

Minimum states:

1. `observed` - first failing or degraded observation;
2. `confirmed` - confirmation threshold has been met;
3. `monitoring` - incident persists without material change;
4. `recovering` - healthy observations have begun but recovery threshold is
   not yet met;
5. `resolved` - recovery threshold has been met;
6. `closed` - the report and follow-up disposition are complete.

Repeated observations update the same incident. They must not create a new
email-style alert for every polling cycle.

## Severity

Initial deterministic levels:

- `info`: recovery, expected transition, or non-actionable test observation;
- `warning`: degraded state, isolated job failure, or incomplete external
  verification with healthy local dependencies;
- `high`: confirmed missed critical execution, persistent readiness/database
  degradation, or correlated failure affecting scheduler work;
- `critical`: scheduler heartbeat lost beyond threshold together with
  independent runtime evidence, or loss of the monitoring path itself when no
  fallback observation remains.

Exact thresholds must be configured and tested per rule. A single transient
request failure must not automatically become a scheduler incident.

## Report contract

Each confirmed or resolved incident report contains:

- stable incident ID, state, severity, and rule version;
- first observation, confirmation, last observation, duration, and recovery;
- affected components and safe endpoint evidence;
- facts separated from hypotheses;
- confidence and known gaps;
- recommended read-only diagnostics;
- a programmer task draft naming likely code areas and tests;
- explicit prohibited actions;
- comparison with current legacy alerts during the pilot.

Periodic test summaries also report false positives, missed legacy alerts,
duplicate suppression, confirmation latency, recovery latency, and agent
availability.

## Implementation checklist

Complete one verified step at a time:

- [x] 1. Inventory the exact response contracts of all approved health
  endpoints and classify every field as retained, transient, sensitive, or
  unnecessary. Reviewed in
  `../../inventories/MONITORING_AGENT_HEALTH_ENDPOINT_INVENTORY.md`.
- [ ] 2. Define the independent runtime boundary and prove that stopping
  `main.py` or the complete monitored workstation does not stop the agent.
  The selected remote runtime and proof contract are documented in
  `SCHEDULER_MONITORING_AGENT_REMOTE_RUNTIME_DESIGN.md`; keep this item open
  until the executable non-production proof passes.
- [ ] 3. Design a dedicated least-privilege authentication identity and
  credential rotation path without exposing secrets in agent state or logs.
  The status-first authorization and strict setup patterns reviewed in
  `../../inventories/BOD_NULA_AGENT_LOGIN_SETUP_REVIEW.md` are accepted as
  design input; keep this item open until the facade service identity and
  rotation mechanism are selected and tested.
  The selected digest-only bearer design and two-slot rotation contract are
  documented in `MONITORING_AGENT_AUTHENTICATION_DESIGN.md`; keep this item
  open until provisioning, rejection, rotation, and remote HTTPS tests pass.
  Credential provisioning, unauthenticated rejection, monitoring/admin
  identity separation, and the first authenticated remote HTTPS observation
  passed on 2026-08-03. Rotation remains unproved, so this item stays open.
- [x] 4. Define polling intervals, request timeouts, jitter, bounded retries,
  and self-health behavior. Treat transport failure separately from an
  unhealthy scheduler response.
  Completed locally on 2026-08-04 with dotenv contract version 1: 60-second
  start-to-start cycles plus 0-5 seconds jitter, three-second request timeout,
  at most three attempts, and exponential 0.5/1.0-second backoff only for
  timeout or connection failure. HTTP/schema failures are not retried.
  Agent heartbeat records `polling`, `healthy`, or `degraded` independently
  from target application health. The monitoring/facade/authorization matrix
  passed with `253 passed`; remote HTTPS retry and recovery evidence remains
  part of steps 2, 9, and 15. The complete monitoring/facade/authorization
  matrix passed with `254 passed` after adding the reproducible bundle proof.
- [ ] 5. Define versioned deterministic rules for heartbeat staleness, missed
  critical runs, repeated job failures, database/readiness degradation,
  restart recovery, and partial public-route verification.
- [ ] 6. Define confirmation and recovery thresholds that suppress transient
  failures without hiding critical loss of heartbeat.
- [ ] 7. Define stable incident identity, lifecycle transitions, deduplication,
  correlation, reopening, and retention.
- [ ] 8. Select bounded agent-owned persistence for observations, incidents,
  reports, and rule versions. No production database writes are allowed.
- [ ] 9. Implement a safe endpoint client and normalized observation
  contracts. Reject unexpected schemas fail-closed. A minimal unauthenticated
  synthetic skeleton now covers liveness, readiness, and system-scheduler
  contracts; keep this item open until the private facade, service identity,
  complete approved endpoint set, retries, and remote HTTPS tests pass.
  The implemented three-route facade and `0.2.0-test` client completed one
  authenticated cross-workstation HTTPS cycle on 2026-08-03 with three
  schema-valid successful observations and an agent-owned heartbeat. Complete
  endpoint coverage and retry behavior remain open.
  Local retry, HTTP/schema fail-closed behavior, serialized cycle timing, and
  self-health are implemented in the clean PyCharm-oriented `0.4.0-test`
  bundle; keep this step open until that bundle passes the remote HTTPS
  loss-and-recovery proof.
- [ ] 10. Implement and unit-test the deterministic evaluation engine without
  an LLM dependency.
- [ ] 11. Implement incident state transitions and recovery detection with
  clock-controlled tests.
- [ ] 12. Implement the interpretation/report layer using only normalized safe
  facts, with facts and hypotheses rendered separately.
- [ ] 13. Implement programmer task drafts containing evidence, suspected
  modules, reproduction/read-only checks, test targets, acceptance criteria,
  and prohibited actions.
- [ ] 14. Add test-mode audit output and comparison against existing scheduler
  alerts. No external delivery is enabled.
- [ ] 15. Test healthy operation, scheduler death, API death, database
  degradation, stale metrics, one-off transport failures, restart recovery,
  repeated errors, and agent restart/resume.
- [ ] 16. Run the independent agent on an approved remote test workstation
  while current alerts remain authoritative.
- [ ] 17. Review pilot evidence for false positives, missed incidents,
  duplicate suppression, recovery behavior, report usefulness, secret
  hygiene, and resource usage.
- [ ] 18. Decide whether to extend observation from scheduler health to the
  complete Health system surface.
- [ ] 19. Prepare a separately approved rollout and rollback runbook for any
  production registration or external report delivery.
- [ ] 20. Consider replacing legacy alert delivery only after a defined
  parallel-run period, reviewed equivalence evidence, independent agent
  self-monitoring, and explicit approval.

## Verification gates

Test-mode implementation is acceptable only when:

- deterministic tests pass without network or model access;
- an agent or model failure cannot change application state;
- scheduler failure remains observable from the independent runtime;
- repeated identical failures produce one evolving incident;
- recovery requires the configured healthy confirmation threshold;
- generated reports contain no secrets or raw operational data;
- all hypotheses are labelled and traceable to safe facts;
- no external delivery or application write path is callable in test mode;
- current scheduler alerts remain unchanged and authoritative.

## Deferred decisions

The following require later explicit choices:

- remote workstation service-manager registration;
- polling and severity thresholds;
- agent-owned state format and retention;
- model/provider and data-processing boundary;
- report review UI and eventual delivery channels;
- ownership and on-call escalation;
- duration and success criteria of the parallel pilot;
- rollback and minimum fallback alerts after legacy alert replacement.

Registration, production deployment, external delivery, and replacement of
existing alerts are not authorized by this plan.
