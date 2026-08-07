# Scheduler Monitoring Agent Remote Runtime Design

Prepared: 2026-07-31

Status: remote boundary and scheduled restart/resume proof accepted for test pilot

Parent plan:
`SCHEDULER_MONITORING_AGENT_PLAN.md`

## Decision summary

The monitoring agent will be the first workload in a dedicated agentic
supervision center on a different workstation in the private network. It must
not run on the workstation hosting `main.py`, FastAPI, Streamlit, Caddy, or the
operational databases.

This replaces the earlier same-host Scheduled Task proposal. The remote
workstation owns the agent process, state, reports, logs, credentials, and
startup mechanism but does not receive the complete application repository. A
shutdown or restart of the monitored workstation must not stop the agent.

The broader hub-and-spoke and distribution boundary is defined in
`AGENTIC_SUPERVISION_CENTER_ARCHITECTURE.md`.

No remote task, network listener, firewall rule, proxy route, credential, or
deployment is created by this design.

## Current network finding

The monitored workstation currently has the correct restrictive boundary:

- FastAPI binds only to `127.0.0.1:8000`;
- Streamlit binds only to `127.0.0.1:8001`;
- Caddy is the external boundary;
- the public Caddy site proxies `/api/*` to FastAPI;
- `/health/*` is not routed to FastAPI from the network and falls through to
  the Streamlit surface;
- detailed scheduler and system health endpoints require a full human
  administrator bearer identity.

Therefore a remote agent cannot safely use the current endpoint URLs as-is.
FastAPI must remain loopback-only and the existing admin Health endpoints must
not be exposed directly to the LAN or internet.

## Target topology

```text
Remote monitoring workstation
`-- monitoring agent
    |-- deterministic polling and incident engine
    |-- agent-owned state and reports
    `-- private authenticated HTTPS
         |
         v
Monitored workstation private/overlay address
`-- Caddy private monitoring listener
    `-- 127.0.0.1:8000
        `-- read-only monitoring API facade
            `-- existing Health collectors
```

Public dashboard traffic and monitoring traffic are separate trust
boundaries.

## Monitoring API facade

Create a dedicated read-only route namespace in a later implementation step,
for example:

```text
/api/v1/monitoring/health/live
/api/v1/monitoring/health/ready
/api/v1/monitoring/health/scheduler
/api/v1/monitoring/health/runtime
/api/v1/monitoring/health/database
/api/v1/monitoring/health/proxy
/api/v1/monitoring/health/smartfuelpass
```

The exact paths are provisional until the API design is implemented and
tested.

The facade must:

- call the existing Health collector functions rather than duplicate probes;
- expose only schemas approved in
  `../../inventories/MONITORING_AGENT_HEALTH_ENDPOINT_INVENTORY.md`;
- use GET only;
- omit scheduler logs, command lines, process IDs, secrets, raw data,
  recipients, business totals, manual-run capabilities, and mutation links;
- have a dedicated monitoring authorization dependency;
- remain usable for runtime and database diagnosis when the application user
  database is unavailable;
- return stable machine-readable error categories without raw exception
  details.

The existing dashboard routes and authorization remain unchanged.

## Private network boundary

### Required properties

The monitoring facade must be reachable only through a private network or
approved encrypted overlay between the two workstations.

The preferred order is:

1. an existing managed private/overlay network with device identity and ACLs;
2. a dedicated private HTTPS Caddy listener bound to a specific private
   address and restricted by host firewall to the monitoring workstation;
3. a mutually authenticated TLS listener when managed overlay identity is not
   available.

Do not expose the monitoring facade on the public dashboard hostname merely
because `/api/*` already exists there.

For the current two Windows workstations, Tailscale is the selected
production-like pilot direction because the monitored workstation already has
an operational Tailscale surface and the remote station can install it. Plain
LAN transport remains limited to disposable synthetic mock testing.

The existing Tailscale Serve HTTPS listener on port 443 has an unrelated root
proxy and must remain unchanged. Reserve tailnet-only HTTPS port `9443` for
the monitoring pilot. During the synthetic proof, Serve may proxy that port to
a temporary loopback-only mock listener. Any Serve configuration change and
its rollback require explicit approval and a captured pre-change sanitized
configuration fingerprint.

### Defense in depth

Network reachability is not authorization. Require:

- encrypted transport;
- source/device restriction at the network or firewall layer;
- a dedicated application monitoring identity;
- request timeouts and rate limits;
- safe access logging without credentials or response bodies;
- credential rotation and revocation;
- tests proving all non-monitoring clients receive denial.

IP allowlisting alone is not sufficient identity when addresses can be
reassigned.

## Remote agent runtime

### Process

Run one long-lived observer process on the remote workstation, for example:

```text
python -m monitoring_agent
```

The agent must not import the monitored application's scheduler
implementation or connect to its databases. Its only monitored-host data path
is the private monitoring API.

### Startup

Use the remote workstation's supported service manager:

- Windows Scheduled Task or Windows service on Windows;
- systemd service on Linux;
- another reviewed service manager if the station uses a different OS.

The final mechanism depends on the remote workstation inventory. It must:

- start independently of the monitored workstation;
- run non-interactively with least privilege;
- suppress duplicate instances;
- restart after bounded process failures;
- start even when the monitored workstation is unreachable;
- provide a safe disable and rollback path.

The Windows pilot now uses Scheduled Task `MonitoringAgentTest` with one
`AtStartup` trigger, `SYSTEM` service-account identity, highest run level,
`StartWhenAvailable`, `IgnoreNew`, a one-minute failure restart interval, and
the exact project-local virtual-environment interpreter and working directory.
Its command line contains only the runner path and no secret, URL, or `.env`
value. A 2026-08-06 supervision-center reboot proved automatic resume as one
logical writer. Detailed evidence and operator constraints are in
`MONITORING_AGENT_REPORTING_LAYER_HANDOFF.md`.

### Environment and storage

Use a separately locked agent environment on the remote workstation. Keep
agent state, reports, logs, locks, and credentials outside this application
repository and outside synced user folders.

The agent may write only to its own storage. It does not receive filesystem,
PowerShell, Task Scheduler, WinRM, SSH, database, or administrative access to
the monitored workstation.

## Failure domains

| Failure | Remote agent alive? | Expected evidence |
|---|---:|---|
| `main.py` exits | yes | scheduler heartbeat becomes stale |
| APScheduler loop stalls | yes | heartbeat or critical-run staleness |
| FastAPI exits | yes | monitoring API connection/proxy failure |
| FastAPI readiness becomes 503 | yes | readiness unavailable |
| PostgreSQL fails | yes | database health error if API is reachable |
| Caddy/private listener fails | yes | target reachable but monitoring transport fails, when distinguishable |
| monitored workstation restarts | yes | connection loss, then new boot time and recovery |
| monitored workstation powers off | yes | persistent host/API unreachability |
| monitored workstation loses network | yes | persistent target unreachability |
| remote agent process exits | no | remote service manager must restart it |
| remote monitoring workstation stops | no | requires a later independent self-heartbeat observer |
| link between stations fails | yes | network-path incident; target health is unknown |

Transport loss means `unknown/unreachable`, not proof that the scheduler
itself failed. Correlation and recovery rules must preserve that distinction.

## Remote failure-isolation proof

Parent-plan checklist step 2 remains open until the observed executable proof
has a retained sanitized evidence summary.

The executable procedure is prepared in
`../../runbooks/MONITORING_AGENT_FAILURE_ISOLATION_TEST.md`. It does not by
itself authorize a target restart, network change, or remote task
registration.

### Static proof

- no agent entry exists in `main.py`, APScheduler job specs, application
  startup launchers, FastAPI startup tasks, Streamlit, or Caddy process
  lifecycle;
- agent runtime files and state exist only on the remote station;
- monitored-host access is limited to the private read-only monitoring API;
- the agent has no mutation client, remote shell, database driver, or
  monitored-host filesystem credential.

### Automated non-production proof

Use two logical hosts or isolated test environments:

1. start a fake monitoring API on the target test host;
2. start the agent on a different test host;
3. verify process ancestry and host identity are different;
4. simulate scheduler failure in the target API;
5. verify the remote agent remains alive and produces one evolving incident;
6. make the complete target test host/API unreachable;
7. verify the agent reports target unreachability and scheduler state as
   unknown;
8. restore the target with a newer boot identity;
9. verify recovering and resolved transitions without restarting the agent;
10. stop the remote agent and verify the target remains unchanged.

### Network and authorization proof

- public dashboard origin does not expose the monitoring facade;
- direct connections to FastAPI ports remain impossible from the network;
- only the approved private listener is reachable from the agent station;
- an unauthenticated request is denied;
- an ordinary dashboard user and human admin token are not accepted as the
  monitoring service identity unless explicitly designed otherwise;
- the monitoring identity can call only allowlisted GET routes;
- log and manual-run routes remain unreachable;
- revoked credentials stop working without restarting the monitored
  application when technically practical;
- no secret value appears in logs, reports, exceptions, or dry-run output.

### Controlled restart proof

A later approved restart of the monitored workstation can provide the final
production-boundary evidence:

- agent heartbeat continues on the remote station;
- target becomes unreachable during restart;
- the agent detects a new boot after recovery;
- scheduler recovery is confirmed only after fresh heartbeat and normal job
  evidence;
- no agent restart is required.

This restart is not authorized by this design alone.

On 2026-08-05 a real monitored-workstation outage and recovery were observed
while the remote observer continued on the separate center. It recorded
sustained target timeouts, a mixed serial-poll recovery cycle, and stable
success without an observer restart. Audit v2 localized the separate
4,545.121-second blind interval to a supervision-center shutdown/restart rather
than a target request. Audit v4 corrected cross-run timing, and the 0.6.2 OS
lock proof rejected a second writer before state or network activity.

The monitored workstation later completed the supported restart required to
activate the fourth System Runtime facade. Remote 0.7 config, one-cycle,
mixed-history, and continuous polling checks passed. On 2026-08-06 the
supervision center itself restarted: the Scheduled Task resumed one logical
`SYSTEM` observer, state advanced by 126 complete four-endpoint cycles from the
pre-reboot checkpoint, and the latest heartbeat recovered to healthy. No new
concurrent start, process-run reentry, unclean restart, or abandoned run was
introduced. The controlled restart proofs are complete for the current test
boundary.

## Availability and blind spots

Moving the agent off-host and registering its startup task closes the largest
same-host and manual-resume blind spots, but the pilot still needs:

- an independent observer of remote-agent heartbeat loss;
- monitoring of the private network path;
- clock synchronization on both stations;
- bounded local retention during link failure;
- explicit `unknown` state when the target cannot be reached;
- a later decision on who watches the monitoring workstation itself.

The first pilot may store reports locally on the remote station. External
email, chat, ticket, or pull-request delivery remains disabled.

## Remaining operational evidence

The Windows runtime, Scheduled Task manager, Python 3.14 environment, shared
encrypted overlay, dedicated application identity, project/config/state ACLs,
and agent heartbeat are verified for the test pilot. Continue inventorying
without collecting secret values:

- tailnet/firewall ownership and change procedure;
- storage retention, backup, and pressure behavior;
- clock synchronization and drift thresholds;
- credential rotation and rollback execution;
- an independent observer for supervision-center heartbeat loss;
- report ownership, review workflow, and eventual delivery boundary.

The detailed inventory is recorded in
`../../inventories/MONITORING_AGENT_REMOTE_WORKSTATION_INVENTORY.md`.

## Acceptance criteria

The remote boundary is accepted when:

- the agent runs on a different workstation and lifecycle;
- loss or restart of the monitored workstation does not stop the agent;
- FastAPI remains loopback-only;
- monitoring data is available only through the private authenticated facade;
- the facade reuses existing collectors and contains no mutations;
- public and ordinary dashboard identities cannot access the facade;
- target unreachability is distinguished from scheduler failure;
- no production process is stopped during non-production proof;
- current alerts remain authoritative during the pilot.

## Current result and next action

The remote boundary is operational for the test pilot. A private tailnet-only
HTTPS facade and dedicated monitoring identity expose four strict GET-only
projections: liveness, readiness, system scheduler, and System Runtime. The
monitored workstation activated the fourth route through its supported full
restart. Remote schema and aggregate runtime checks passed without exposing
raw responses or credentials.

The supervision center runs verified bundle `0.7.0-test` through
`MonitoringAgentTest`. Its ZIP SHA-256 is
`0BA56B60FD8F5A229346D565FEA33F58F57F9239FE541F216C07E79E56D7BF20`;
manifest SHA-256 is
`39C06473793C92FB281D509C3468493E9562CF9CDB74F27DBEA4D249C4676ACB`.
The existing external state and credential were retained, and only the ordered
endpoint set changed. Audit v6 safely combines legacy contract-2/set-1 records
with current contract-3/set-2 records.

The 2026-08-06 reboot proof ended with task state `Running`, one logical
`SYSTEM` agent, nine lifecycle starts/eight stops/one current run, zero
unclean or abandoned runs, and a healthy four-observation heartbeat. The
append-only history still reports one pre-lock concurrent start and one run
reentry; those counts did not increment. Two Python processes are the one venv
launcher/interpreter parent-child tree and must not be treated as two writers.
The first fresh lifecycle write arrived roughly 110 seconds after task launch,
so postboot checks require fresh state and a bounded startup allowance.

Local `0.8.1-test` supersedes the undeployed 0.8.0 bundle. It prepares eight
strict private-facade projections and one credential-free direct external-web
probe as observation contract 4 / endpoint set 3, while supporting the exact
env-v1/contract-3/set-2 bridge needed to recover from the observed 0.7 Runtime
schema incompatibility without restoring excluded server fields. Its ZIP
SHA-256 is
`D17A88A10814D4CC645AD731B5C2B56B3B662E0662547ED9FCEA3443EF876884` and
manifest SHA-256 is
`18A3E477E724EEA61F3EFDCBE303BEBE4DC298A4D646D37FE643D6CD9C49CBB1`.
This is a local candidate, not a deployed result.

The next action is the separately controlled 0.8.1 unchanged-env-v1 bridge,
then the remote env-v2 configuration migration and one complete
nine-observation cycle plus audit-v7 mixed/current-run proof. Only then begin the
deterministic incident and reporting foundation. Retention, credential
rotation, independent observation of the center, interpretation providers,
external delivery, and legacy-alert replacement remain open. No
monitored-application mutation is authorized.
