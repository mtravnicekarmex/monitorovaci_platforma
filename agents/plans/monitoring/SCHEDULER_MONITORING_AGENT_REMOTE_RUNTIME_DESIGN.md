# Scheduler Monitoring Agent Remote Runtime Design

Prepared: 2026-07-31

Status: remote boundary selected; network and executable proof pending

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

Parent-plan checklist step 2 remains open until executable proof passes.

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

## Availability and blind spots

Moving the agent off-host closes the largest same-host blind spot, but the
pilot still needs:

- a self-heartbeat for the remote agent;
- monitoring of the private network path;
- clock synchronization on both stations;
- bounded local retention during link failure;
- explicit `unknown` state when the target cannot be reached;
- a later decision on who watches the monitoring workstation itself.

The first pilot may store reports locally on the remote station. External
email, chat, ticket, or pull-request delivery remains disabled.

## Information required before implementation

Inventory the remote workstation without collecting secret values:

- operating system and supported service manager;
- stable private/overlay network identity;
- whether both stations already share an approved encrypted network;
- firewall ownership and change procedure;
- certificate or device-identity mechanism;
- Python/runtime availability;
- storage location, ACLs, backup, and retention;
- clock synchronization;
- how the remote agent itself will expose a safe heartbeat.

The initial inventory is recorded in
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

The remote runtime boundary is selected. The previous same-host Scheduled Task
proposal is superseded.

Next:

1. confirm tailnet ownership, device approval, and policy-change authority;
2. design the dedicated monitoring identity and facade authorization;
3. define the private Tailscale listener and network-grant contract;
4. implement a minimal safe facade and remote observer skeleton;
5. execute the non-production isolation and authorization proof.

No network, proxy, firewall, credential, task, service, or runtime change has
been authorized or performed.
