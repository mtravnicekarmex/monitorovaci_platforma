# Monitoring Agent Cross-Host Failure-Isolation Test

Prepared: 2026-08-04

Status: procedure ready; execution requires explicit approval and access to
the supervision center

Parent plan:
`../plans/monitoring/SCHEDULER_MONITORING_AGENT_PLAN.md`

## Purpose

Prove that the test-mode observer on the supervision center remains alive,
records target transport loss as unknown/unreachable rather than scheduler
failure, and observes recovery without being restarted. Current scheduler
alerts remain authoritative throughout the proof.

This runbook does not authorize a monitored-workstation restart, credential
rotation, Scheduled Task registration, external delivery, application write,
or network/proxy reconfiguration.

## Preconditions

- The supervision center is the Windows 11/CPython 3.14 station already
  enrolled in the approved tailnet.
- Tailnet-only HTTPS port 9443 still reaches only the read-only monitoring
  facade; existing port 443 remains unchanged.
- The center stores all runtime values in one ACL-restricted local `.env`.
  Do not display, copy, hash, or record its content.
- Bundle `0.4.0-test` and its repository-recorded ZIP SHA-256 match before
  transfer.
  Expected ZIP SHA-256 is
  `A6C9DCF82137D252519A05E705CF05D6B1252A4DCA74974037602231088FC767`.
- Install side by side with prior test bundles; do not delete or overwrite
  their immutable verification evidence.
- Use a new empty agent-owned state directory for this proof.

## Phase 1 - Offline bundle verification

On the supervision center, using paths selected locally by its operator:

1. Verify the transferred ZIP SHA-256 against the repository-recorded value.
2. Extract into a new versioned directory.
3. Confirm the archive matches the exact manifest allowlist and contains
   `.env.example`, `.gitignore`, `run_monitoring_agent.py`, the runtime
   package, `manifest.json`, and `manifest.sha256`, but no real `.env`.
4. Verify `manifest.sha256`, then verify every file size and SHA-256 declared
   by `manifest.json`.
5. Copy `.env.example` to `.env`, edit only the local copy, and restrict its
   ACL. Keep agent state outside the extracted project directory.
6. Run `py -3.14 run_monitoring_agent.py --check-config`.
7. Confirm the safe output reports environment contract version 1, test mode,
   and three
   endpoints. Stop if any extra file, manifest mismatch, secret field, or
   configuration error appears.

## Phase 2 - Foreground healthy HTTPS cycle

1. Use the local `.env` containing the approved tailnet HTTPS base URL, the
   existing bearer, an agent instance label, a new agent-owned state
   directory, the reviewed polling values, and the three endpoint keys.
2. Run one foreground cycle with
   `py -3.14 run_monitoring_agent.py --once`. Never paste the bearer into the
   command line, PyCharm run configuration, console, or report.
3. Require three observations with `transport_status=success`, HTTP 200,
   schema-valid normalized payloads, and `attempt_count=1`.
4. Require the agent heartbeat to finish as `healthy`, with three observations
   and zero transport failures.
5. Confirm no response body, Authorization header, credential, target machine
   identifier, or raw operational value was printed.

## Phase 3 - Long-running observer baseline

1. Start the observer in the foreground without `--once`.
2. Observe at least three completed cycles without restarting the process.
3. Record only safe aggregates: cycle timestamps, endpoint keys, transport
   statuses, attempt counts, and heartbeat status.
4. Confirm cycle starts are separated by the configured start-to-start
   interval plus bounded jitter and that cycles do not overlap.
5. Record the observer process identity locally for continuity comparison;
   do not place machine or account identifiers in repository notes.

## Phase 4 - Approved target-loss proof

This phase is a hard approval gate. Use either an approved disposable
cross-host synthetic target or a separately approved whole monitored-host
restart. Do not stop `main.py`, FastAPI, Caddy, Tailscale, or the workstation
merely to satisfy this runbook without that approval.

While the foreground observer continues unchanged:

1. Make the approved target path unavailable.
2. Require each endpoint observation to end as `connection_error` or `timeout`
   after no more than three attempts with only the configured bounded
   backoff.
3. Require the observer heartbeat to remain current and become `degraded`.
4. Classify scheduler state as unknown/unreachable. Do not claim the scheduler
   stopped because transport evidence cannot prove that fact.
5. Confirm the observer process and supervision workstation remain alive and
   the monitored target receives no mutation request.

## Phase 5 - Recovery proof

1. Restore the approved target without restarting the observer.
2. If the monitored workstation restarted, require a newer safe boot identity
   when runtime coverage is later available; with the current three-route
   facade, record this as a known evidence gap.
3. Require subsequent observations to return to HTTP 200 and
   `transport_status=success` with schema-valid payloads.
4. Require the observer heartbeat to return from `degraded` to `healthy`.
5. Confirm the observer process identity is unchanged from the baseline.
6. Stop the foreground observer normally after evidence is captured and
   confirm the monitored target remains unchanged.

## Evidence to retain

- bundle version and ZIP/manifest verification result;
- config version and non-secret polling parameters;
- count and timing of healthy, unavailable, and recovered cycles;
- endpoint transport statuses and attempt counts;
- observer heartbeat state transitions;
- proof that the observer process continued across target loss and recovery;
- explicit known gaps and confirmation that no external delivery or mutation
  occurred.

Do not retain bearer values, credential paths, tailnet names or addresses,
hostnames, user names, process command lines, raw response bodies, or raw
operational payloads.

## Pass criteria

- The observer runs on the separate supervision center throughout the proof.
- Target loss produces bounded transport retries and `degraded` observer
  self-health while scheduler state remains unknown.
- Recovery is observed without restarting the observer.
- Repeated cycles remain serialized and within the configured timing bounds.
- Only agent-owned state changes; the monitored application remains read-only.
- No secret or operational identifier appears in retained evidence.

Scheduled Task registration, credential rotation, full endpoint expansion,
incident lifecycle behavior, and external delivery remain separate gates.
