# Monitoring agent test skeleton

This package is the independent read-only observer skeleton for `OPS-002`.
It is not registered as an autonomous or production agent.

Current capabilities:

- loads a strict, versioned, non-secret JSON configuration;
- polls only the compiled-in GET allowlist;
- accepts plain HTTP only for loopback synthetic tests;
- accepts remote targets only through HTTPS;
- bypasses ambient HTTP proxy configuration;
- validates exact synthetic response schemas fail-closed;
- drops non-retained labels and detail text;
- writes normalized observations and its own heartbeat only to the explicitly
  supplied state directory;
- contains no authentication, model, email, manual-job, database, remote
  shell, process-control, or application-write capability.

## Local synthetic test

Terminal 1:

```powershell
.\.venv\Scripts\python.exe -m monitoring_agent.synthetic_server `
    --scenario healthy
```

Terminal 2:

```powershell
Copy-Item monitoring_agent\config.example.json `
    .\monitoring-agent.test.json

.\.venv\Scripts\python.exe -m monitoring_agent `
    --config .\monitoring-agent.test.json `
    --once
```

The example uses a disposable `.local-state` directory beside the copied
configuration. Validate setup without network access or state writes with:

```powershell
.\.venv\Scripts\python.exe -m monitoring_agent `
    --config .\monitoring-agent.test.json `
    --check-config
```

Do not put credentials, tokens, or URLs containing credentials into the
configuration. The production-like
Tailscale test will use HTTPS port `9443` only after an explicit Serve and
network-policy approval.

Available synthetic scenarios:

- `healthy`;
- `scheduler_stopped`;
- `readiness_unavailable`.

The synthetic server refuses non-loopback binds and implements no control,
log, manual-run, or mutation endpoint.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_monitoring_agent.py -q
```

Runtime design and security gates remain authoritative in:

- `agents/plans/monitoring/SCHEDULER_MONITORING_AGENT_PLAN.md`;
- `agents/plans/monitoring/SCHEDULER_MONITORING_AGENT_REMOTE_RUNTIME_DESIGN.md`;
- `agents/inventories/MONITORING_AGENT_HEALTH_ENDPOINT_INVENTORY.md`.
