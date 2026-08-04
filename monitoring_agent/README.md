# Monitoring agent test project

This is the independent read-only observer for `OPS-002`. The test bundle is
designed to be opened and managed as its own small PyCharm project on the
remote supervision workstation. It is not registered for automatic startup
and does not replace existing scheduler alerts.

## Project contract

The remote project contains:

- `run_monitoring_agent.py`, the only operator entry point;
- the `monitoring_agent/` standard-library package;
- `.env.example`, the complete non-secret configuration template;
- `.gitignore`, which excludes the real `.env`, PyCharm state, Python caches,
  and local agent state;
- bundle manifests for offline integrity verification.

The real `.env` exists only on the supervision workstation. It contains all
runtime values, including the private HTTPS base URL and monitoring bearer
credential. The program reads the file directly; it does not require the
operator to create persistent or session-level environment variables.

Never commit, bundle, display, transmit, or paste the real `.env`. Restrict
its Windows ACL to the operating identity and `SYSTEM` before any automatic
startup registration.

## First setup in PyCharm

1. Open the extracted bundle root as a PyCharm project.
2. Select CPython 3.14. No third-party package installation is required.
3. Copy `.env.example` to `.env`.
4. Edit `.env` locally and replace the private base URL and bearer placeholder.
5. Keep `MONITORING_AGENT_MODE=test`.
6. Use a state directory outside the extracted code directory.

Validate without network access or state writes:

```powershell
py -3.14 run_monitoring_agent.py --check-config
```

Expected safe output:

```json
{"endpoint_count":3,"env_contract_version":1,"event":"configuration_valid","mode":"test"}
```

Run one foreground HTTPS cycle:

```powershell
py -3.14 run_monitoring_agent.py --once
```

Start continuous foreground polling for interactive testing:

```powershell
py -3.14 run_monitoring_agent.py
```

The PyCharm run configuration uses `run_monitoring_agent.py` as the script,
the extracted bundle root as the working directory, and either `--once` or no
parameters. Do not copy `.env` values into the PyCharm run configuration.

## Polling and self-health contract

The initial `.env.example` defines:

- serialized 60-second start-to-start cycles plus 0-5 seconds random jitter;
- a three-second request timeout and at most three attempts;
- exponential 0.5/1.0-second backoff only for connection errors and timeouts;
- no retry for HTTP authorization/status errors, invalid JSON, or schema
  errors;
- approved HTTP 503 readiness retained as application evidence, not a
  transport failure;
- agent heartbeat written as `polling` at cycle start and `healthy` or
  `degraded` at completion;
- target scheduler degradation kept separate from observer self-health.

The client calls only the compiled-in GET allowlist. It has no manual-job,
database, shell, process-control, application-write, model, email, or external
delivery capability.

## Synthetic scenarios

The optional loopback-only synthetic server supports:

- `healthy`;
- `scheduler_stopped`;
- `readiness_unavailable`;
- `unauthorized`;
- `invalid_schema`.

It refuses non-loopback binds and exposes no mutation endpoint.

## Bundle build

Build the reviewed explicit-allowlist ZIP without staging unrelated files:

```powershell
.\.venv-production\Scripts\python.exe `
    scripts\build_monitoring_agent_bundle.py `
    --version 0.4.0-test `
    --created-date 2026-08-04 `
    --output artifacts\monitoring_agent\monitoring-agent-0.4.0-test.zip
```

The builder uses deterministic ZIP metadata. It includes `.env.example` but
rejects any design that would include the real `.env`, state, logs,
credentials from an operating station, PyCharm workspace state, or repository
metadata.

## Verification

```powershell
.\.venv\Scripts\pytest.exe tests\test_monitoring_agent.py -q
```

Automatic Windows startup remains a later gate. After foreground behavior,
failure isolation, recovery, retention, and restart/resume tests pass, the
same `run_monitoring_agent.py` entry point can be registered through a
separately reviewed Windows Scheduled Task with an explicit interpreter,
working directory, operating identity, restart policy, and rollback path.
