# Scheduler Monitoring Agent Plan

Prepared: 2026-07-30

Status: remote scheduled 0.7 writer has a diagnosed safe-runtime schema
incompatibility; local 0.8.1 two-phase recovery and complete Health observation
candidate awaiting remote proof

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
- [x] 2. Define the independent runtime boundary and prove that stopping
  `main.py` or the complete monitored workstation does not stop the agent.
  The selected remote runtime and proof contract are documented in
  `SCHEDULER_MONITORING_AGENT_REMOTE_RUNTIME_DESIGN.md`. The 2026-08-05
  foreground proof showed the remote observer remaining alive through complete
  monitored-workstation loss and recovery. Audit contracts 2-5 localized a
  separate blind interval to a supervision-center restart, corrected cross-run
  cadence, and verified current writer exclusivity. On 2026-08-06 the new
  `MonitoringAgentTest` Scheduled Task survived an actual supervision-center
  reboot, resumed four-endpoint observations as one logical `SYSTEM` process
  tree, and recovered to healthy without new overlap, unclean, or abandoned-run
  evidence. The independent runtime boundary is therefore proved for the test
  pilot.
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
  from target application health. The remote foreground process observed
  target timeouts and automatic recovery on 2026-08-05; retained safe audit
  evidence remains part of steps 2, 9, 14, and 15. The latest complete local
  monitoring/facade/authorization matrix passed with `267 passed`.
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
  bundle. Remote HTTPS loss and recovery were functionally observed on
  2026-08-05. Keep this step open for complete approved endpoint coverage and
  retained audit evidence. Remote `0.4.1-test` integrity is verified. Audit v1
  confirmed bounded retries and recovery. Audit v2 proved the 4,545.121-second
  gap occurred after a short healthy cycle, and Windows events identified a
  supervision-station shutdown/restart. Remote `0.6.0-test` validated
  prospective process/cycle lifecycle evidence but counted a 46.83-second
  process transition as an early scheduled start. Remote `0.6.1-test` audit v4
  corrected same-run cadence and exposed historical `A-B-A-C` writer
  interleaving. Remote `0.6.2-test` verified fail-closed second-writer rejection
  with no lifecycle/observation writes and successful lock release after
  Ctrl+C. Audit v5 concurrent-start/run-reentry facts and the 281-test local
  matrix passed. `0.7.0-test` adds the approved System Runtime facade
  and strict client projection as endpoint set 2. Observation contract 3 and
  audit v6 preserve retained contract-2/set-1 cycles without rewriting them;
  62 focused, 286 combined, and 306 extended System Health tests passed. The
  monitored workstation activated the facade through its supported full
  restart, and the remote 0.7 bundle now runs four endpoints from the retained
  state. Config, one-cycle, mixed-history audit, continuous polling, task
  registration, and supervision restart/resume checks passed on 2026-08-06.
  Local `0.8.1-test` supersedes the undeployed 0.8.0 bundle and adds strict
  safe projections for detailed Scheduler
  Health, System Database, Proxy, and SmartFuelPass, plus a direct external
  public-page probe. Observation contract 4 / endpoint set 3 contains nine
  ordered observations, environment contract 2 adds the external root URL,
  and audit v7 preserves exact set-1/set-2 compatibility. It also supports the
  exact env-v1/four-key bridge required by the observed 0.7 Runtime schema
  incompatibility and reports current-run retry evidence separately from
  historical findings. The focused matrix passed with 192 tests. Keep this
  checklist item open until the remote bridge recovery and nine-observation
  cycle plus mixed/current-run audit pass.
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
  alerts. No external delivery is enabled. Remote audit v1 retained aggregate
  retry, cycle, recovery, timing, and latest-heartbeat evidence with explicit
  history gaps and no raw output. Remote audit v2 localized the blind interval
  to a supervision-host restart. Remote audit v3 added prospective
  clean/unclean process restart and incomplete-cycle evidence; remote audit v4
  corrected scheduled timing and identified process interleaving. Remote audit
  v5 distinguishes concurrent starts/run reentry from an unclean restart, and
  remote single-writer rejection/release passed. Keep this step open for
  incident audit and comparison with existing alerts.
- [ ] 15. Test healthy operation, scheduler death, API death, database
  degradation, stale metrics, one-off transport failures, restart recovery,
  repeated errors, and agent restart/resume. Healthy remote polling,
  sustained target timeouts, partial-cycle recovery, stable recovery,
  controlled restart lock release, and duplicate-writer rejection passed in
  foreground on 2026-08-05. Scheduled automatic agent restart/resume, one
  logical `SYSTEM` writer after center reboot, continued observations, and
  recovery from transient postboot transport failures passed on 2026-08-06.
  Scheduler-process-only death, database degradation, stale metrics, and
  repeated deterministic incident behavior remain open.
- [x] 16. Run the independent agent on an approved remote test workstation
  while current alerts remain authoritative. The remote `0.7.0-test` observer
  now runs continuously through `MonitoringAgentTest` on the separate
  supervision center. Its restart/resume proof passed on 2026-08-06, and
  current alerts remain unchanged and authoritative.
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

## Reporting-layer handoff

The verified deployment, local 0.8 candidate, and safe input boundary are
detailed in `MONITORING_AGENT_REPORTING_LAYER_HANDOFF.md`. First complete
roadmap item 1 by activating and remotely proving endpoint set 3. The following
implementation sequence is then steps 5-8 and 10-12:

1. version deterministic rules and confirmation/recovery thresholds over the
   normalized nine-endpoint observations;
2. define stable incident identities, transition semantics, deduplication,
   reopening, and bounded agent-owned persistence;
3. implement the deterministic evaluator with synthetic clock-controlled
   tests;
4. define a pure local report contract and renderer with facts, hypotheses,
   confidence, evidence gaps, diagnostics, and prohibited actions separated;
5. compare test reports with current legacy alerts before adding any
   interpretation provider or external delivery.

The current audit is a sanitized aggregate diagnostic, not an incident store.
The retained raw state must stay on the supervision center and outside Git.
Repository development uses synthetic fixtures. While the Scheduled Task is
running, do not invoke foreground continuous mode or `--once`; only
`--check-config` and `--audit-state` are safe concurrent operator commands.

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

- polling and severity thresholds;
- agent-owned state format and retention;
- model/provider and data-processing boundary;
- report review UI and eventual delivery channels;
- ownership and on-call escalation;
- duration and success criteria of the parallel pilot;
- rollback and minimum fallback alerts after legacy alert replacement.

Production promotion, reporting delivery, and replacement of existing alerts
are not authorized by this plan. The only registered runtime is the verified
remote test-pilot task described above.
