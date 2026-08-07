# Agentic Supervision Center Architecture

Prepared: 2026-07-31

Status: first scheduled workload installed and restart-verified; reporting pending

The first-login and setup design is informed by the bounded review in
`../../inventories/BOD_NULA_AGENT_LOGIN_SETUP_REVIEW.md`. The center adopts
explicit status-first authorization, post-login identity verification, and
strict profile validation, while retaining a non-human facade identity and a
fixed read-only runtime permission boundary.

## Purpose

Create one independent agentic supervision center on a clean remote
workstation. The center supervises application health and future local domain
agents without receiving the complete `monitorovaci_platforma` repository,
operational databases, raw measurements, or remote-control privileges.

The scheduler monitoring observer is the first supervision workload.

## Topology

```text
Agentic supervision center
|-- deterministic health polling
|-- incident lifecycle and correlation
|-- agentic report and programmer-task preparation
|-- center self-heartbeat
`-- center-owned state, reports, audit, and package inventory
       |
       | private authenticated HTTPS over Tailscale
       v
Monitored workstation
|-- read-only monitoring facade
|-- main.py scheduler and Health collectors
|-- future local anomaly/consumption agents
|-- safe local-agent heartbeat/report projections
`-- operational data and application code remain local
```

## Deployment boundary

The remote center must not receive:

- the complete `monitorovaci_platforma` Git repository or its `.git`
  metadata;
- `.env`, credentials, cookies, browser sessions, DSNs, or application
  secrets;
- operational database drivers or connection strings;
- raw measurements, device identifiers, recipients, photos, or reports;
- scheduler logs or application logs;
- application launchers, Caddy configuration, migration tools, backfill
  scripts, or manual-job clients;
- source code for unrelated application modules.

It receives only a reviewed supervision bundle containing:

- the observer runtime package;
- strict normalized API contracts;
- deterministic rules and rule versions;
- report templates;
- a launcher and safe local configuration schema;
- an offline self-test;
- an immutable manifest of included files and SHA-256 hashes;
- installation, upgrade, rollback, and disable instructions.

## Hub-and-spoke responsibilities

### Supervision center

The center may poll approved read-only endpoints through Tailscale, maintain
its own incident state, correlate health, create local summaries, prepare
programmer tasks, and record its own heartbeat and package version.

The center may not execute actions on monitored stations, invoke local agents,
start jobs, connect to operational databases or shares, open remote shells,
send external messages during test mode, or modify application source.

### Local application agents

Future agents that require raw measurements or close application coupling
remain on the monitored workstation. Examples include consumption anomaly,
prediction-quality, and domain-specific data-quality agents.

Each local agent:

- owns only its approved domain and local data boundary;
- exposes a sanitized heartbeat and aggregate report projection;
- retains raw evidence locally;
- does not accept arbitrary prompts or commands from the center;
- cannot broaden center access to databases or files;
- has its own lifecycle, lock, state, tests, and safe disable procedure.

### Monitoring facade

The facade is the only data boundary between the center and monitored
workstation. It reuses existing safe collectors, later aggregates safe
local-agent heartbeats, uses versioned GET-only schemas, and never proxies
logs, raw records, arbitrary files, SQL, or commands.

## Tailscale model

Tailscale makes the center location-independent as long as it remains an
approved tailnet device, Grants allow only center-to-facade traffic on the
dedicated port, and dedicated application authentication is also required.
The center is not trusted merely because it is connected to the tailnet.

## Minimal distribution bundle

```text
monitoring-agent\
|-- .env.example
|-- .gitignore
|-- run_monitoring_agent.py
|-- register_monitoring_agent_task.ps1
|-- README.md
|-- monitoring_agent\
|   |-- __init__.py
|   |-- __main__.py
|   |-- audit.py
|   |-- client.py
|   |-- observer.py
|   |-- settings.py
|   |-- store.py
|   `-- synthetic_server.py
|-- manifest.json
`-- manifest.sha256
```

The bundle contains no live credential. The operator creates one ignored,
ACL-restricted `.env` locally from `.env.example`; the same Python entry point
is used in PyCharm foreground testing and the approved Windows test-pilot
Scheduled Task. Any future task or service change requires separate review.

## Packaging contract

A deterministic packaging tool must:

1. use an explicit file allowlist;
2. reject symlinks, unexpected files, secrets, and runtime state;
3. compile and test the observer before packaging;
4. generate per-file SHA-256 hashes;
5. include package, rule, and contract versions;
6. omit repository paths and usernames;
7. verify the archive in a temporary directory;
8. run its offline self-test from the extracted bundle;
9. print aggregate results without file contents or secrets.

No production package may be built from an unreviewed dirty source state.
Synthetic packages must identify themselves as test builds.

## Installation contract

On the clean Windows 11 Pro center:

- create a dedicated application directory outside synced user profiles;
- create an isolated Python 3.14 environment;
- create separate ACL-restricted state, report, log, and credential paths;
- run the offline self-test before network configuration;
- verify the manifest before every start and upgrade;
- register a non-interactive task only after dry-run review;
- retain the previous verified bundle for rollback.

Installation must not clone the complete `monitorovaci_platforma` repository.
A separately reviewed minimal agent repository is permitted only when its
tracked runtime files match the approved manifest and it excludes live
configuration, credentials, state, virtual environments, and IDE workspace
data.

Installation, non-secret configuration, facade authorization, optional
interpretation-provider authorization, diagnostics, and foreground test
execution are separate phases. Interactive provider login must never occur
inside the unattended scheduled task. Deterministic-only operation remains a
valid mode when no interpretation provider is authorized.

## Center self-monitoring

Record process heartbeat, last poll cycle, package/rule/contract versions,
observation outcomes, storage availability, last report, and network-path
status. A later independent mechanism must observe center heartbeat loss.

## Adding future local agents

Every local-agent integration requires an owner, safe aggregate inventory,
versioned schema, deterministic rules, retention classification, no-raw-data
proof, authorization tests, shadow pilot, rollback, and explicit approval.
Adding an agent never grants the center write authority.

## Pilot sequence

1. Package the synthetic scheduler observer without the repository.
2. Transfer the test bundle through an approved channel.
3. Verify hashes and run offline self-tests on the center.
4. Configure the dedicated Tailscale Grant and synthetic Serve port.
5. Run cross-workstation healthy/failure/recovery tests.
6. Implement the monitoring facade and service identity.
7. Run shadow monitoring while legacy alerts remain authoritative.
8. Add center self-heartbeat observation.
9. Review pilot evidence.
10. Register future local agents one at a time.

## Current boundary

The second workstation is designated as the agentic supervision center.
Windows 11 Pro, Python 3.14, Tailscale installation, shared-tailnet membership,
and peer connectivity are confirmed.

The private GET-only monitoring facade, digest-verified service identity, and
tailnet-only HTTPS listener on reserved port 9443 are operational. The current
`0.7.0-test` observer is installed with a local ignored `.env`, an isolated
Python 3.14 virtual environment, and agent-owned state outside the code
directory. Its four endpoint projections are liveness, readiness, system
scheduler, and System Runtime.

The minimal remote project is tracked separately in public repository
`mtravnicekarmex/monitoring_agent_0.4.0`. Current `master` commit
`3c171cf49615cf792211f3c992320dade539ccc4` matches the verified
`0.4.1-test` manifest and contains no live `.env`, credential, state, virtual
environment, or IDE workspace. Remote audit v2 and local Windows events
attribute the 4,545.121-second observation gap to supervision-station
shutdown/restart, not a blocked target request. Remote `0.6.0-test` validated
prospective process lifecycle/restart evidence. Remote `0.6.1-test` audit
contract 4 prevented cross-run intervals from
becoming scheduled-cadence findings and exposed historical writer
interleaving. Remote `0.6.2-test` verified state-scoped OS writer exclusivity,
lock release, and audit-v5 concurrent-start/run-reentry evidence.

The monitored workstation completed the supported full restart needed to
activate the System Runtime facade, after which the center migrated to 0.7
without changing the credential or state path. The 0.7 ZIP and manifest,
four-endpoint config, one controlled cycle, mixed-history audit, and continuous
polling passed. The complete platform repository remains absent from the
center; the separately verified public minimal repository remains at its older
0.4.1 baseline.

`MonitoringAgentTest` now owns the observer lifecycle as a Windows Scheduled
Task under `SYSTEM`. A 2026-08-06 center reboot proved automatic resume, one
logical venv launcher/interpreter process tree, continued state updates, and a
healthy current heartbeat. Lifecycle contained nine starts, eight stops, one
active run, and no unclean or abandoned run. Historical pre-lock overlap facts
remain visible but did not increment. The roughly 110-second cold-start delay
requires postboot checks to wait for fresh lifecycle/observation evidence
rather than trusting task state alone.

Local `0.8.1-test` supersedes the undeployed 0.8.0 bundle and prepares the
complete approved observation expansion: eight strict private-facade
projections plus a direct credential-free external-web probe, with observation
contract 4 / endpoint set 3 and audit contract 7. It also provides the exact
env-v1/contract-3/set-2 bridge required to recover from the observed 0.7
Runtime schema transition without weakening the safe target projection. It is
not deployed. The next gate is the controlled bridge recovery followed by the
env-v2 remote migration and a verified nine-observation mixed/current-run
cycle. Only then does the next layer become deterministic incident evaluation
and local reporting using `MONITORING_AGENT_REPORTING_LAYER_HANDOFF.md`.
Bounded retention, credential rotation, independent observation of center
loss, interpretation-provider authorization, external delivery, and
future-agent onboarding remain open or separately gated. Current scheduler
alerts remain authoritative.
