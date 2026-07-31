# Monitoring Agent Health Endpoint Inventory

Reviewed: 2026-07-30

Status: approved input inventory for `OPS-002` test-mode implementation

Plan:
`../plans/monitoring/SCHEDULER_MONITORING_AGENT_PLAN.md`

## Scope and classification

This inventory covers the current response contracts available to the first
read-only monitoring agent. It is based on the FastAPI route and Pydantic
schema definitions, not on captured production responses.

Field classifications:

- **R - retained:** normalize and persist as bounded incident evidence;
- **T - transient:** may be used while evaluating one poll but do not persist
  the raw value; a derived boolean or category may be retained;
- **X - unnecessary:** drop before deterministic evaluation and never pass to
  the interpretation layer;
- **S - sensitive:** do not retain or pass to the interpretation layer.

Receiving a field in one JSON response does not authorize retaining it. The
safe client must explicitly project allowlisted fields into normalized
contracts and discard everything else.

## Endpoint summary

| Endpoint | Authentication now | Pilot use | Notes |
|---|---|---:|---|
| `GET /health/live` | public | yes | Independent API process reachability |
| `GET /health/ready` | public | yes | API initialization/readiness |
| `GET /health/system/scheduler` | admin bearer | yes | Primary deterministic scheduler summary |
| `GET /health/scheduler` | admin bearer | yes | Internal steps and expected 24-hour schedule |
| `GET /health/system/runtime` | admin bearer | yes | Restart and listener correlation |
| `GET /health/system/database` | admin bearer | yes | Database dependency correlation |
| `GET /health/system/proxy` | admin bearer | later pilot | Proxy/public-path correlation |
| `GET /health/system/smartfuelpass` | admin bearer | later pilot | Only safe job-health projection is relevant |
| `GET /health/scheduler/log` | admin bearer | no | Raw log content and local path are outside scope |
| `POST /health/scheduler/jobs/{job_id}/run` | admin bearer | forbidden | Mutating manual-run endpoint |

The current protected endpoints use `get_current_admin_user`. A dedicated
least-privilege monitoring identity or equivalent read-only authorization
boundary does not yet exist. A human administrator token is not an accepted
production credential for the agent.

The current URLs are local application contracts, not remote network
contracts. FastAPI is loopback-only and public Caddy routing does not proxy
`/health/*` to FastAPI. A remote agent must use the separately designed
private monitoring facade; do not expose these admin URLs directly.

## Public liveness and readiness

### `GET /health/live`

Success response is HTTP 200 with:

| Field | Type | Class | Use |
|---|---|---:|---|
| `status` | string, currently `ok` | R | Record normalized API liveness |

Transport outcome, HTTP status, request duration, poll timestamp, and client
error category are agent-generated observation metadata and must also be
retained. Response headers and bodies other than the allowlisted `status`
field are unnecessary.

### `GET /health/ready`

Responses:

- HTTP 200 with `{"status": "ready"}`;
- HTTP 503 with `{"status": "unavailable"}`.

| Field | Type | Class | Use |
|---|---|---:|---|
| `status` | string | R | Record normalized readiness |

Readiness failure is an application state, not a transport failure. The client
must preserve that distinction.

## Primary scheduler summary

### `GET /health/system/scheduler`

Response model: `SystemSchedulerHealthResponse`.

Top-level fields:

| Field | Type | Class | Use |
|---|---|---:|---|
| `status` | `ok/degraded/error` | R | Collector's deterministic aggregate |
| `checked_at` | datetime | R | Source observation time |
| `scheduler_running` | boolean | R | Primary process/heartbeat state |
| `last_heartbeat` | datetime/null | R | Temporal incident evidence |
| `heartbeat_age_seconds` | number/null | R | Source-derived staleness |
| `heartbeat_ttl_seconds` | integer | R | Rule input and source contract |
| `total_success_count_24h` | integer | R | Trend and correlation |
| `total_failure_count_24h` | integer | R | Failure confirmation |
| `jobs` | array | R | Project only allowlisted job fields below |

Each `jobs[]` item is `SystemSchedulerJobStatus`:

| Field | Type | Class | Use |
|---|---|---:|---|
| `job_id` | string | R | Stable component identity |
| `label` | string | T | Human display only |
| `status` | `ok/degraded/error` | R | Source classification |
| `last_status` | string | R | Last-run evidence |
| `last_run` | datetime/null | R | Missed/stale-run rules |
| `next_run` | datetime/null | R | Schedule consistency |
| `success_count_24h` | integer | R | Trend and comparison |
| `failure_count_24h` | integer | R | Confirmation and comparison |
| `last_duration_seconds` | number/null | R | Duration regression input |
| `detail` | string | T | Display/debug hint; do not use as identity |

The agent must not reproduce the endpoint's aggregate logic. It may add
versioned temporal rules and cross-endpoint correlation while retaining the
source status as evidence.

## Detailed Scheduler Health projection

### `GET /health/scheduler`

Response model: `SchedulerHealthResponse`. This is the endpoint used by the
existing Scheduler Health dashboard and is required for internal scheduler
steps not present in the system scheduler summary.

Top-level fields:

| Field | Type | Class | Use |
|---|---|---:|---|
| `status` | `ok/degraded/error` | R | Existing Scheduler Health aggregate |
| `scheduler_running` | boolean | R | Corroborates system scheduler state |
| `jobs` | array | R | Scheduled jobs, internal steps, manual catalog |
| `schedule` | array | R | Expected runs for the next 24 hours |
| `checked_at` | datetime | R | Source observation time |

Each `jobs[]` item is `SchedulerJobHealth`:

| Field | Type | Class | Use |
|---|---|---:|---|
| `id` | string | R | Stable component identity |
| `label` | string/null | T | Human display only |
| `description` | string/null | X | Not needed for rules; code-owned text |
| `is_scheduled` | boolean | R | Component classification |
| `is_manual_runnable` | boolean | X | Agent must never run jobs |
| `last_run` | datetime/null | R | Temporal evidence |
| `last_status` | string | R | Last-run evidence |
| `last_duration_seconds` | number/null | R | Duration evidence |
| `next_run` | datetime/null | R | Schedule consistency |
| `failure_rate_24h` | number `0..1` | R | Existing aggregate metric |
| `avg_duration_24h` | number/null | R | Duration baseline input |

Each `schedule[]` item is `SchedulerScheduledRun`:

| Field | Type | Class | Use |
|---|---|---:|---|
| `job_id` | string | R | Join to job identity |
| `job_label` | string | T | Human display only |
| `description` | string | X | Not needed for deterministic rules |
| `scheduled_at` | datetime | R | Expected-run evidence |

The `is_manual_runnable` field is dropped so the normalized client contract
does not expose operational capability to later layers.

## Runtime correlation

### `GET /health/system/runtime`

Response model: `SystemRuntimeHealthResponse`.

Top-level:

| Field | Type | Class | Use |
|---|---|---:|---|
| `status` | `ok/degraded/error` | R | Runtime aggregate |
| `checked_at` | datetime | R | Source observation time |
| `boot` | object | R | Restart correlation |
| `startup_task` | object | R | Supported startup evidence |
| `expected_listeners` | array | R | Required-surface evidence |
| `temporary_listeners` | array | R | Duplicate/test runtime evidence |

`boot` projection:

| Field | Type | Class | Use |
|---|---|---:|---|
| `status` | `ok/degraded/error` | R | Boot probe state |
| `boot_time` | datetime/null | R | Restart boundary |
| `detail` | string | T | Display hint |

`startup_task` projection:

| Field | Type | Class | Use |
|---|---|---:|---|
| `task_name` | string | R | Stable configured component |
| `status` | `ok/degraded/error` | R | Task state |
| `last_run_time` | datetime/null | R | Restart correlation |
| `next_run_time` | datetime/null | X | Startup task is boot-triggered |
| `last_task_result` | integer/null | R | Supported-start evidence |
| `detail` | string | T | Display hint |

Listener projection:

| Field | Type | Class | Use |
|---|---|---:|---|
| `key` | string | R | Stable listener identity |
| `label` | string | T | Human display only |
| `status` | `ok/degraded/error` | R | Listener state |
| `expected` | boolean | R | Expected/temporary classification |
| `present` | boolean | R | Availability evidence |
| `local_address` | string/null | T | Evaluate expected binding, do not retain |
| `local_port` | integer | R | Stable service evidence |
| `process_ids` | integer array | X | Volatile and unnecessary for incidents |
| `detail` | string | T | Display hint |

## Database correlation

### `GET /health/system/database`

Response model: `SystemDatabaseHealthResponse`.

Top-level:

| Field | Type | Class | Use |
|---|---|---:|---|
| `status` | `ok/degraded/error` | R | Database aggregate |
| `checked_at` | datetime | R | Source observation time |
| `postgres` | object | R | Connection evidence |
| `expected_schemas` | array | R | Required-schema evidence |

`postgres` projection:

| Field | Type | Class | Use |
|---|---|---:|---|
| `status` | `ok/degraded/error` | R | Connection classification |
| `connected` | boolean | R | Dependency state |
| `latency_ms` | number/null | R | Trend input |
| `server_time` | datetime/null | T | Clock comparison within one poll |
| `server_timezone` | string/null | T | Validate expected timezone |
| `server_version` | string/null | X | Inventory detail, not incident input |
| `transaction_read_only` | boolean/null | R | Write-capability degradation |
| `detail` | string | T | Display hint |

Each `expected_schemas[]` item:

| Field | Type | Class | Use |
|---|---|---:|---|
| `schema_name` | string | R | Stable dependency identity |
| `status` | `ok/degraded/error` | R | Schema classification |
| `present` | boolean | R | Required-schema evidence |
| `table_count` | integer/null | T | Detect gross change; do not retain raw |
| `detail` | string | T | Display hint |

## Proxy correlation

### `GET /health/system/proxy`

Response model: `SystemProxyHealthResponse`. This endpoint is approved for a
later pilot extension, not required by the first scheduler-only rule set.

Top-level:

| Field | Type | Class | Use |
|---|---|---:|---|
| `status` | `ok/degraded/error` | R | Proxy aggregate |
| `checked_at` | datetime | R | Source observation time |
| `public_host` | string | X | Configuration detail not needed in report |
| `routes` | array | R | Project allowlisted route results |
| `headers` | array | R | Project allowlisted header results |

Each `routes[]` item:

| Field | Type | Class | Use |
|---|---|---:|---|
| `key` | string | R | Stable probe identity |
| `label` | string | T | Human display only |
| `status` | `ok/degraded/error` | R | Probe result |
| `method` | string | T | Contract validation |
| `scheme` | string | T | Contract validation |
| `host` | string | X | Drop configured hostname |
| `path` | string | X | Drop route detail; use stable key |
| `expected_status_code` | integer | R | Expected response |
| `actual_status_code` | integer/null | R | Observed response |
| `expected_content_type_prefix` | string/null | T | One-poll validation |
| `actual_content_type` | string/null | T | One-poll validation |
| `expected_location` | string/null | X | May repeat public routing detail |
| `actual_location` | string/null | X | May repeat public routing detail |
| `detail` | string | T | Display hint |

Each `headers[]` item:

| Field | Type | Class | Use |
|---|---|---:|---|
| `key` | string | R | Stable header-probe identity |
| `header_name` | string | T | Display/contract validation |
| `status` | `ok/degraded/error` | R | Probe result |
| `expected` | `present/absent` | R | Expected security state |
| `present` | boolean | R | Observed state |
| `detail` | string | T | Display hint |

Public-route failure must be correlated with local liveness, readiness, and
runtime state. A workstation-specific external request failure is not by
itself proof of an application outage.

## SmartFuelPass projection

### `GET /health/system/smartfuelpass`

Response model: `SystemSmartFuelPassHealthResponse`. This is deferred until the
agent expands beyond scheduler supervision.

Retain only:

- top-level `status` and `checked_at`;
- `sync_job` and `weekly_report_job` fields `job_id`, `status`,
  `last_status`, `last_run`, `success_count_24h`, `failure_count_24h`, and
  `last_duration_seconds`;
- `table.status`, `table.table_present`,
  `table.missing_ended_at_utc_count`, `table.last_imported_at`, and
  `table.last_import_age_seconds`.

Use labels and details transiently. Drop `source`, `period_basis`,
`first_session_at`, `last_session_at`, session/location/connector counts, and
the complete `report_periods` array as unnecessary for the scheduler agent.

Treat monetary `total_amount` fields as **S**. They must not be retained or
passed to the interpretation layer.

## Explicitly excluded surfaces

### `GET /health/scheduler/log`

Excluded because it returns a local path and free-form log content that may
contain operational context outside the safe normalized contract. The first
agent prepares a recommendation for a programmer to inspect logs; it does not
ingest the logs itself.

### `POST /health/scheduler/jobs/{job_id}/run`

Forbidden because it changes runtime state and may trigger imports, scoring,
reports, or email. No client method for this route may exist in the monitoring
agent package.

## Normalized observation envelope

Every endpoint poll should produce this agent-owned metadata:

| Field | Purpose |
|---|---|
| `observation_id` | Locally generated stable unique ID |
| `observer_instance_id` | Independent agent instance identity |
| `endpoint_key` | Stable allowlisted endpoint identity, not a free URL |
| `poll_started_at` / `poll_finished_at` | Agent clock evidence |
| `http_status` | Distinguish application state from transport failure |
| `transport_status` | `success/timeout/connection_error/tls_error/schema_error` |
| `attempt_count` | Bounded retry evidence |
| `contract_version` | Normalized schema version |
| `source_checked_at` | Endpoint timestamp where available |
| `clock_skew_seconds` | Derived, bounded diagnostic value |
| `payload` | Only the endpoint-specific retained projection |

Do not persist bearer tokens, cookies, authorization headers, full request
URLs, response headers, raw bodies, exception strings containing connection
details, or fields not allowlisted above.

## Contract findings

1. The scheduler page and System Health page expose complementary contracts;
   neither alone covers the intended first agent.
2. Liveness and readiness are public, but every detailed health endpoint
   currently requires a full administrator bearer token.
3. The current API has no dedicated monitoring role or service identity.
4. The scheduler log and manual-run routes share the `/health/scheduler`
   namespace but are explicitly outside the agent boundary.
5. Current Pydantic models validate response production, but the future agent
   still needs its own strict normalized input models and must reject
   unexpected schemas fail-closed.
6. Existing endpoints contain enough safe facts for the first deterministic
   scheduler rules; no new metric collector or database query is required for
   the initial implementation.

## Step 1 result

Checklist step 1 is complete at the design/inventory level. The next step is
to define the independent runtime boundary and a failure-isolation proof. The
least-privilege authorization gap remains assigned to checklist step 3.
