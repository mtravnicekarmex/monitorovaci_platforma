# Monitoring Agent Remote Workstation Inventory

Reviewed: 2026-07-31

Status: skeleton bundle extracted and local synthetic proof passed; remote
network proof pending

Runtime design:
`../plans/monitoring/SCHEDULER_MONITORING_AGENT_REMOTE_RUNTIME_DESIGN.md`

## Confirmed facts

| Property | Reviewed value |
|---|---|
| Role | Agentic supervision center; scheduler observer is its first workload |
| Operating system | Windows 11 Pro |
| Python | CPython 3.14 available |
| Physical network | Same LAN as the monitored workstation |
| Tailscale | Installed on Windows host, joined to the same tailnet, and peer connectivity confirmed |
| Runtime lifecycle | Must be independent from the monitored workstation |
| Production writes | Forbidden |
| External delivery | Disabled during pilot |
| Repository clone | Forbidden; use reviewed minimal bundle |

No hostname, IP address, user name, token, credential, device ID, or other
secret/operational identifier is recorded in this inventory.

## Selected test runtime

For the first Windows pilot:

- use a dedicated Python virtual environment and lock file on the remote
  station;
- install only a reviewed supervision bundle, not this repository;
- run the observer non-interactively through its own Windows Scheduled Task;
- keep agent code, configuration, state, reports, logs, lock, and credentials
  in separate ACL-restricted locations;
- do not place the observer in a user startup folder or start it from the
  monitored application's launcher;
- do not grant local administrator, remote shell, database, network-share, or
  monitored-host filesystem permissions.

The Scheduled Task registration is a later reviewed implementation step. No
task is registered by this inventory.

## Selected network direction

### Offline and mock testing

Tailscale is not required for:

- unit tests;
- schema and redaction tests;
- deterministic incident-engine tests;
- a disposable fake API test with no production data.

If a same-LAN mock listener is temporarily required, it must:

- serve only synthetic responses;
- bind to a documented temporary port;
- be restricted by Windows Firewall to the test source;
- contain no application credential or production collector;
- be stopped and its firewall exception removed after the test.

Creating that listener or firewall exception requires explicit approval at
the time of the test.

### Production-like remote pilot

Use Tailscale or an equivalent approved encrypted overlay before the real
monitoring facade is exposed to the remote station.

Reasons:

- the monitored workstation already has an operational Tailscale surface
  recorded in project runbooks;
- overlay device identity is stronger than a reassigned LAN IP;
- access can be restricted by source, destination, and TCP port;
- the monitoring listener does not need to be exposed to the ordinary LAN or
  public dashboard origin;
- workstation restart and LAN addressing changes are easier to correlate
  through stable overlay identity.

Tailscale network authorization supplements rather than replaces the
application monitoring identity.

## Proposed Tailscale identity model

After installation and tailnet approval:

- assign a purpose-specific tag or equivalent managed device identity to the
  remote observer station;
- assign a separate target identity to the monitored workstation;
- grant only observer-to-target access on private monitoring HTTPS port
  `9443`;
- do not grant broad subnet, SSH, RDP, SMB, database, Caddy admin, FastAPI
  loopback, or application-management access;
- keep the default posture deny-by-default outside the explicit grant;
- verify denial from an unrelated tailnet device.

The exact tailnet policy and identifiers must be prepared without secret
values and reviewed before application.

Official design references:

- Tailscale Grants:
  https://tailscale.com/docs/features/access-control/grants
- Grants syntax:
  https://tailscale.com/kb/1538/grants-syntax
- Tailscale device identity:
  https://tailscale.com/docs/concepts/tailscale-identity

## Information still required

Before installing or registering anything, confirm:

- the remote station can join the same approved tailnet;
- who owns and may change the tailnet policy;
- whether device approval is required;
- whether a purpose-specific device tag is available;
- the remote station's clock synchronization is healthy;
- the station can remain powered and connected for the pilot;
- the approved local directory and operating account for agent runtime;
- whether the station reboots automatically after updates;
- whether endpoint protection permits a dedicated Python environment and
  non-interactive Scheduled Task.

Do not record credential or machine-identity values in repository Markdown.

## Initial verification sequence

1. Verify Windows 11 Pro and CPython 3.14 locally on the remote station.
2. Run offline deterministic tests without network access.
3. Confirm the remote station can join the approved tailnet.
4. Verify a deny-by-default network grant in dry-run/review form.
5. Install/join Tailscale only after approval.
6. Verify agent-to-target reachability on a disposable synthetic listener.
7. Verify unrelated devices and unapproved ports are denied.
8. Remove the disposable listener and confirm the port is closed.
9. Implement the private monitoring facade and application identity.
10. Begin shadow-mode polling with current alerts still authoritative.

## Current result

The remote station satisfies the known operating-system and Python
prerequisites. The user approved installing Tailscale on 2026-07-31 so all
cross-workstation tests can use the production-like encrypted overlay from the
start. The user confirmed the Windows-host installation and shared-tailnet
join on 2026-07-31. The monitored workstation independently reported its
Tailscale service and backend running and its local node online; no device
names, addresses, or IDs were recorded. A Tailscale ping from the remote
station to the monitored workstation returned a pong on 2026-07-31.

The monitored workstation already has a persistent Tailscale Serve HTTPS
listener on port 443 with one root handler proxying to an existing loopback
service. That configuration is outside the monitoring-agent scope and must not
be reset, replaced, or reused for destructive experiments. The monitoring
pilot reserves a separate tailnet-only HTTPS port `9443`.

On 2026-07-31 the reviewed `0.1.0-test` skeleton ZIP was transferred to and
extracted on the remote station without cloning the repository. CPython
3.14.0 loaded the package and its strict example configuration successfully.
The foreground local synthetic proof then passed:

- healthy liveness, readiness, and scheduler responses produced three
  successful normalized observations;
- stopped-scheduler evidence remained a successful transport observation
  with scheduler status `error`, `scheduler_running=false`, and a synthetic
  1,200-second heartbeat age;
- HTTP 503 readiness remained a successful transport observation with
  application status `unavailable`;
- stopping the synthetic server produced three sanitized
  `connection_error` observations;
- the center wrote its own heartbeat and JSONL observations only under the
  bundle-local test state directory.

This proves local package execution and basic state separation. It does not
yet prove remote HTTPS access, facade authentication, Tailscale authorization,
monitored-host shutdown isolation, persistence across center restart, or
Scheduled Task operation.

No task, persistent listener, firewall rule, credential, facade, tailnet
policy, external delivery, or monitored-application state was created or
changed. Tailscale installation and interactive tailnet login were performed
directly by the user on the remote station.
