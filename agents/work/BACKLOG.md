# Backlog

## OPS-002 - Register application monitoring agents

- Status: test skeleton validated locally on remote station
- Priority: normal
- First agent:
  `../plans/monitoring/SCHEDULER_MONITORING_AGENT_PLAN.md`
- Approved scope: independent read-only scheduler/system observer in test
  mode, using existing health endpoints and producing local incident reports
  and programmer task drafts.
- Completed design step: health endpoint response contracts and field
  retention classifications are recorded in
  `../inventories/MONITORING_AGENT_HEALTH_ENDPOINT_INVENTORY.md`.
- Runtime design: the observer will run on a different network workstation;
  its private API boundary and failure-isolation proof are specified in
  `../plans/monitoring/SCHEDULER_MONITORING_AGENT_REMOTE_RUNTIME_DESIGN.md`.
- Remote station inventory: Windows 11 Pro, CPython 3.14, same LAN, with
  Tailscale selected and user-approved for installation so all remote tests
  use the production-like overlay; see
  `../inventories/MONITORING_AGENT_REMOTE_WORKSTATION_INVENTORY.md`.
- Next step: design the dedicated least-privilege monitoring identity and
  private facade, then run the first HTTPS observation over Tailscale port
  `9443`. Keep runtime checklist step 2 open until the executable remote
  observer passes its cross-host isolation proof.
- Test implementation: `monitoring_agent/` contains an unregistered
  standard-library observer and loopback-only synthetic Health server.
  Focused safety/contract tests pass (`20 passed`; `40 passed` together with
  system-health tests); no Tailscale Serve route,
  task, credential, facade, or production collector is connected.
- Distribution boundary: the clean remote workstation is the agentic
  supervision center and receives only a reviewed minimal bundle, never the
  complete repository. Architecture:
  `../plans/monitoring/AGENTIC_SUPERVISION_CENTER_ARCHITECTURE.md`.
- Distribution proof: the manually assembled explicit-allowlist
  `0.1.0-test` ZIP contains nine runtime files plus manifest verification.
  It was extracted on the remote Windows station and passed configuration,
  healthy, scheduler-stopped, readiness-unavailable, and connection-loss
  foreground tests. A reproducible bundle-builder script, virtual-environment
  bootstrap, ACL setup, upgrade/rollback, and task registration remain open.
- Restrictions: current alerts remain authoritative; no production
  registration, external delivery, process control, manual jobs, or
  application/database writes are authorized.
- Candidate surfaces: scheduler, FastAPI, Streamlit, Caddy, databases, imports,
  and prediction pipelines.
- Updated: 2026-07-31
