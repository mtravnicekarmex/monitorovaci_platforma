# Active work

## OPS-002 - Independent scheduler monitoring agent

- Status: remote `0.8.1-test` now uses the intentional clean
  `monitoring-agent-state-ops002` baseline. The env-v1 four-endpoint bridge
  passed, the target-side scheduler-detail timezone fix was activated by
  monitored-workstation restart, and the env-v2 nine-endpoint `--once` plus
  audit-v7 proof passed. Continuous Scheduled Task restoration is the only
  remaining gate before moving to roadmap item 2; the first non-elevated
  registration attempt failed with Windows access denied and the supervision
  station is unavailable for maintenance until 2026-08-08.
- Priority: normal
- Plan: `../plans/monitoring/SCHEDULER_MONITORING_AGENT_PLAN.md`
- Runtime design:
  `../plans/monitoring/SCHEDULER_MONITORING_AGENT_REMOTE_RUNTIME_DESIGN.md`
- Reporting handoff:
  `../plans/monitoring/MONITORING_AGENT_REPORTING_LAYER_HANDOFF.md`
- Implementation roadmap/checklist:
  `../plans/monitoring/MONITORING_AGENT_IMPLEMENTATION_ROADMAP.md`
- Previous continuous runtime: `0.7.0-test` ran on the separate Windows 11
  supervision center through Scheduled Task `MonitoringAgentTest`. The task uses one
  `AtStartup` trigger, `SYSTEM`, the exact project-local Python 3.14 virtual
  environment and working directory, `IgnoreNew`, `StartWhenAvailable`, and
  one-minute failure restarts. It contains no credential, URL, or `.env` value
  on its command line. The complete platform repository remains absent from
  the center.
- Integrity and configuration: the verified 13-file ZIP SHA-256 is
  `0BA56B60FD8F5A229346D565FEA33F58F57F9239FE541F216C07E79E56D7BF20`;
  manifest SHA-256 is
  `39C06473793C92FB281D509C3468493E9562CF9CDB74F27DBEA4D249C4676ACB`.
  Archive and extracted-content verification passed with no real `.env`.
  Configuration migration retained the existing credential, state path, and
  all non-endpoint values while changing only the ordered endpoint set to
  `live`, `ready`, `system_scheduler`, and `system_runtime`.
- Facade/runtime proof: the monitored workstation was restarted through its
  supported boot-created FastAPI/Caddy boundary. The authenticated new System
  Runtime route returned HTTP 200 with the expected schema, runtime status
  `ok`, five expected listeners with none non-OK, and no temporary listener.
  One controlled 0.7 cycle produced four successes, and audit v6 validated
  retained observation-contract-2/set-1 history plus new
  observation-contract-3/set-2 history without rewriting it.
- Supervision restart proof: before reboot, 0.7 closed cleanly with eight
  starts and eight stops. After the 2026-08-06 reboot, the task started one
  logical `SYSTEM` writer. Windows exposes it as a two-process venv
  launcher/interpreter tree; this is not a second writer. The first lifecycle
  write arrived roughly 110 seconds after task launch, so postboot checks must
  require fresh state rather than task state alone.
- Latest retained aggregate: audit v6 reached 1,389 complete cycles: 1,313
  healthy, 71 partial failure, and 5 unreachable. Transport totals were 4,430
  success, 12 connection error, 50 timeout, and 68 schema error. The latest
  four-observation heartbeat is degraded with two failures because the new
  target runtime schema is incompatible with the deployed 0.7 client.
  Lifecycle was
  nine starts, eight stops, one active run, zero unclean restarts, and zero
  abandoned runs. Historical concurrent-start and process-run-reentry counts
  remain one each from immutable pre-lock history and did not increment.
- Local 0.8.1 candidate: eight authenticated GET-only facade projections now
  cover liveness, readiness, system scheduler, detailed scheduler, runtime,
  database, proxy, and SmartFuelPass health. A ninth direct external-web probe
  runs without the facade bearer, follows no redirect, reads no body, and
  retains no URL or headers. Environment contract 2, observation contract 4 /
  endpoint set 3, and audit contract 7 retain exact compatibility with sets 1
  and 2. The original 0.8.0 ZIP SHA-256 was
  `29BEE64FEE267F1E74BE1AA89CA621E2930262E16C0C662580DA5D2B7EBF8EF0`;
  manifest SHA-256 is
  `282DFDDA162B4D4CB2C3CE656066D47E2B03504F1434277659E20CBCBB173ADF`.
  The original 0.8.0 bundle is superseded and must not be deployed. 0.8.1 adds
  a strict env-v1/contract-3/set-2 bridge before env-v2/contract-4/set-3 while
  preserving the existing credential, state, timing, and endpoint identity.
  Its focused matrix passed 192 tests. ZIP SHA-256 is
  `D17A88A10814D4CC645AD731B5C2B56B3B662E0662547ED9FCEA3443EF876884`;
  manifest SHA-256 is
  `18A3E477E724EEA61F3EFDCBE303BEBE4DC298A4D646D37FE643D6CD9C49CBB1`.
- Target activation proof: the supported 2026-08-06 restart recovered all
  expected services/listeners and scheduler state, activated all eight facade
  paths, and produced repeated complete HTTP-200 route sequences from the
  still-running remote 0.7 observer. The later client audit showed those HTTP
  responses did not constitute schema recovery. Runtime, database, and proxy
  safe payloads are `ok`; SmartFuelPass truthfully reports the known
  paused-import error and must be qualified later rather than rewritten.
- Remote audit finding: lifecycle remains valid with no unclean/abandoned run,
  but the latest heartbeat is degraded and history added 68 schema errors
  because deployed 0.7 expects the former full System Runtime schema. Do not
  restore excluded server fields and do not deploy 0.8.0.
- Remote bundle transfer: a matching 0.8.1 ZIP SHA-256 was reported on
  2026-08-07, but the same console had no `MonitoringAgentTest` task. This does
  not prove that the bundle reached the actual supervision center.
- Test-stage stop authorization: the user accepts a one-time planned
  observation discontinuity and hard termination if no Ctrl+C console is
  available. Preserve state and qualify any resulting abandoned/unclean 0.7
  run as migration evidence. Manual `.env` transfer is allowed without
  displaying its contents.
- Executed stop: the only two Python processes formed the expected Session-0
  launcher/interpreter tree. The elevated fail-closed stop required the old
  `.env`, exact ZIP hash, both process identities, and parent/child relation;
  afterward the exact targets and all Python processes were absent.
- Current remote 0.8.1 proof: the new clean state directory
  `monitoring-agent-state-ops002` is the intentional state baseline to carry
  across later agent versions. Env-v1 `--check-config`, `--once`, and
  `--audit-state` passed with four successes, one complete healthy cycle, and
  clean lifecycle. After the monitored workstation restart activated the
  timezone-aware `scheduler_detail` fix, env-v2 `--once` completed one
  nine-observation cycle with transport status `success`. Audit v7 reported
  endpoint set 3, valid endpoint and cycle order, latest heartbeat `healthy`,
  nine latest observations, zero latest transport failures, valid retry and
  attempt bounds, and clean lifecycle. The two retained env-v2 schema errors
  are historical pre-fix evidence and recovery is proved; `system_smartfuelpass`
  remains a schema-valid known paused-import `error` payload.
- Next step: restore continuous operation through the reviewed
  `MonitoringAgentTest` Scheduled Task on the supervision station. A
  non-mutating `.\register_monitoring_agent_task.ps1 -WhatIf` preview passed;
  the actual non-elevated registration failed with access denied
  (`HRESULT 0x80070005`) and created no fallback user task. When the station is
  available again on 2026-08-08, run elevated PowerShell in
  `C:\Users\tra\PycharmProjects\monitoring-agent-0.8.1-test`,
  execute `.\register_monitoring_agent_task.ps1 -Confirm:$false`, start the
  task, wait 90-120 seconds, then verify task state/info and read-only
  `py -3.14 run_monitoring_agent.py --audit-state`. Require task `Running`,
  a healthy nine-observation latest heartbeat, an expected open continuous
  lifecycle run, and no new concurrent-start, run-reentry, unclean, or
  abandoned evidence before moving to roadmap item 2. Keep legacy alerts
  authoritative and external delivery disabled.
- Restrictions: no external delivery, general process control, manual jobs,
  application/database writes, or replacement of current alerts. The only
  process-control exception is the explicitly authorized, exact 0.7
  monitoring-agent process tree during this test migration. Do not launch
  foreground continuous mode or `--once` while the task is running;
  `--check-config` and `--audit-state` remain safe concurrent commands.
- Open gates: continuous 0.8.1 Scheduled Task restoration/proof, credential
  rotation, bounded retention, independent observation of the supervision
  center, reporting review UI, delivery channels, and any legacy alert
  replacement.
- Updated: 2026-08-07
