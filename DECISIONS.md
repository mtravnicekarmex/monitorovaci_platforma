# DECISIONS.md

Purpose: durable project decisions for `monitorovaci_platforma`. Add new decisions instead of rewriting history. Mark superseded decisions explicitly.

## DEC-001: Current State Is the Baseline

Date: 2026-06-05

Decision: The current repository state reviewed on 2026-06-05 is the baseline for future sessions.

Rationale: The user explicitly requested a read-only review of the current project state and confirmed that this state should be treated as the starting point for future context documents.

Implications:

- Future sessions should read `AGENTS.md`, `DECISIONS.md`, and `SESSION_NOTES.md` first.
- Dirty working tree entries must be treated as real user/runtime state until clarified.
- Runtime artifacts and sensitive files should not be cleaned up without explicit approval.

## DEC-002: Active Runtime Surfaces

Date: 2026-06-05

Decision: The active runtime surfaces are the scheduler, FastAPI service, and Streamlit dashboard.

Rationale: The reviewed project structure shows `main.py` as scheduler entry, `services/api/main.py` as API entry, and `moduly/apps/dashboard/login.py` as active dashboard entry.

Implications:

- Changes to production dashboard behavior should target Streamlit unless the user explicitly asks for `frontend_next`.
- API-facing behavior should be implemented through FastAPI where practical.
- Scheduler changes should preserve the existing APScheduler/job structure.

## DEC-003: `frontend_next` Is Experimental

Date: 2026-06-05

Decision: `frontend_next/` is an experimental, currently unused Next.js MVP. It may be developed further in the future, but it is not the active dashboard today.

Rationale: The user explicitly clarified that `frontend_next` is only experimental and not currently used.

Implications:

- Do not infer current production behavior from `frontend_next/`.
- Do not spend verification effort on `frontend_next/` unless the task touches it.
- If future work revives this area, document the migration decision and expected parity with Streamlit.

## DEC-004: FastAPI Is the Preferred External Boundary

Date: 2026-06-05

Decision: New external or frontend-facing capabilities should prefer FastAPI endpoints over direct database or dashboard-only coupling.

Rationale: The project already has a structured FastAPI app with authentication dependencies, routers, and health endpoints.

Implications:

- Reusable business logic should live in modules/services and be exposed through API routes when useful.
- Dashboard pages should not become the only implementation of domain logic.
- API auth/permission dependencies should be reused instead of duplicated.

## DEC-005: Streamlit Navigation Is a Contract

Date: 2026-06-05

Decision: Streamlit navigation and permissions are governed by `moduly/apps/dashboard/navigation_config.py`.

Rationale: The project has explicit navigation/auth tests and a central navigation config.

Implications:

- Add or move dashboard pages through the central config.
- Keep section/page/device permissions consistent with dashboard user model.
- Run navigation/auth tests when changing dashboard access behavior.

## DEC-006: Database Schemas Have Domain Ownership

Date: 2026-06-05

Decision: PostgreSQL schemas retain domain ownership: `monitoring`, `dashboard`, `web_search`, and `revize` have separate responsibilities.

Rationale: The reviewed database bootstrap and model code separates measurement, dashboard, web-search, and revision responsibilities.

Implications:

- Do not mix dashboard permission data into measurement tables.
- Do not mix measurement data into web-search or revision schemas.
- New tables should be added to the schema that matches their domain.

## DEC-007: Time Semantics Must Be Preserved

Date: 2026-06-05

Decision: Existing time semantics are a project invariant and must not be simplified casually.

Rationale: Measurement imports and dashboards depend on explicit UTC/source-time metadata, timezone offsets, fold handling, and interval semantics.

Implications:

- Use `moduly/mereni/time_semantics.py` and `moduly/apps/dashboard/time_semantics.py` instead of ad-hoc conversion.
- Preserve canonical columns such as `time_utc`, `source_date`, `time_basis`, `source_timezone`, and related fields.
- Run targeted time/import tests when changing timestamp behavior.

## DEC-008: Scheduler Schedule Definitions Stay Centralized

Date: 2026-06-05

Decision: Scheduler cron definitions belong in `core/scheduler/job_schedule.py`.

Rationale: Centralized schedule definitions make manual run specs, tests, and operational review easier.

Implications:

- Do not scatter cron definitions across feature modules.
- Keep scheduler execution concerns in `core/scheduler/scheduler.py`.
- Update scheduler tests when adding or changing job timing.

## DEC-009: Imports Preserve Data Quality Behavior

Date: 2026-06-05

Decision: Import pipelines must preserve existing anomaly, expected-zero, outlier, and gap/reset behavior unless a task explicitly changes it.

Rationale: Metering domains use import-time normalization and downstream anomaly/event logic. Small changes can alter reports and alerts.

Implications:

- Inspect domain tests before changing imports.
- Prefer targeted tests for the affected domain.
- Treat source-specific behavior such as AREAL, SCVK, SOFTLINK, SmartFuelPass, and binary electric imports as domain contracts.

## DEC-010: Alerting and Outlier Review Are Shared Concepts

Date: 2026-06-05

Decision: Alerting, expected-zero windows, and outlier review should remain shared operational concepts across metering domains where applicable.

Rationale: Multiple domains contain similar alerting/outlier workflows, and dashboard/admin behavior relies on shared patterns.

Implications:

- Avoid duplicating admin concepts in isolated pages.
- Keep event and alert terminology consistent across dashboard, API, and reports.
- Run affected alerting/outlier tests when changing shared behavior.

## DEC-011: Report Recipients Require Explicit Configuration

Date: 2026-06-05

Decision: Email/report recipients and scheduler alert targets should remain explicit configuration, not hard-coded hidden behavior.

Rationale: The platform sends operational reports and alerts; recipient correctness is operationally sensitive.

Implications:

- Document recipient behavior when changing reports.
- Avoid embedding new addresses without user confirmation.
- Verify report generation paths after changing reporting logic.

## DEC-012: Context Files Are Part of Everyday Work

Date: 2026-06-05

Decision: `AGENTS.md`, `DECISIONS.md`, and `SESSION_NOTES.md` are adopted as persistent context files for future work.

Rationale: The user requested a workflow that allows each session to continue with project context and to automatically preserve relevant changes and decisions.

Implications:

- Agents should propose context-file updates after substantive work.
- Durable decisions belong in `DECISIONS.md`.
- Session-specific facts and handoff notes belong in `SESSION_NOTES.md`.
- Operating instructions belong in `AGENTS.md`.

## DEC-013: Runtime/Data Artifact Cleanup Needs Separate Approval

Date: 2026-06-05

Decision: Tracked runtime/data artifacts are recognized as a cleanup topic, but no cleanup is performed as part of the baseline documentation.

Rationale: Current working tree includes modified or untracked operational data. Removing or ignoring such files can affect local workflows.

Implications:

- Do not delete or untrack runtime artifacts without explicit user approval.
- Candidate cleanup items include SmartFuelPass session files, scheduler lock files, `frontend_next/tsconfig.tsbuildinfo`, and nested electric-meter data artifacts.
- If cleanup is approved later, document the exact files and `.gitignore` changes.

## DEC-014: Map Layers Are Admin-Configured Metadata

Date: 2026-06-05

Decision: Map-layer visibility, source table metadata, filterable columns, popup columns, draw order, and Leaflet style are managed as dashboard metadata in `dashboard.Map_Layers`.

Rationale: Map podklady will grow beyond Vodomery. Hardcoding every layer in one route would make adding contextual and device layers slow and error-prone.

Implications:

- Admins configure layer metadata, not arbitrary SQL.
- Backend validates configured source tables and columns through `information_schema`.
- Context layers are gated by page access.
- Device layers can use `restrict_to_allowed_devices=True` and a `device_section_key`; feature loading must still enforce assigned device IDs.
- Future map pages should consume the map-layer catalog instead of duplicating layer definitions in page-specific code.

## DEC-015: Map Device Photos Are Served Through an Authorized API Proxy

Date: 2026-06-05

Decision: Device photos in map popups are loaded through authenticated FastAPI endpoint `GET /api/v1/map/images` using `layer_id` and device identifier. The client must not send or control a raw filesystem path.

Rationale: Browser access to local or UNC paths is unreliable and unsafe. Serving images through the API allows the backend to enforce user permissions, layer availability, device assignment, file existence, and supported image types.

Implications:

- Map image endpoints must resolve paths server-side from trusted device metadata such as the `foto` detail column.
- Image access must reuse map-layer/device access checks and bearer token authentication.
- Empty or missing `foto` values should not render broken image placeholders in the dashboard.
- Direct arbitrary file serving based on a client-provided path is not allowed.
- Dashboard browser image fetches require CORS for the dashboard origin; local defaults cover Streamlit `8001` and Caddy/proxy `8080`, and other origins should be configured through `API_CORS_ORIGINS`.

Clarification (2026-06-09):

- Map GeoJSON exposes only a boolean photo-availability marker such as `has_photo`; raw and resolved photo paths stay server-side.
- Stored `P:\...` photo paths are translated server-side to the service-accessible `\\SERVER1A\Company\...` fallback because service processes may not inherit mapped drives.
- Browser photo requests use same-origin `/api/v1/map/images` through Caddy; Caddy routes `/api/*` to FastAPI and the remaining traffic to Streamlit.
- `DASHBOARD_BROWSER_API_BASE_URL` is an override for deployments where the browser must call FastAPI at another origin.

## DEC-016: Mobile Dashboard Uses Responsive Streamlit Pages

Date: 2026-06-09

Decision: Mobile optimization is implemented as responsive behavior in the active Streamlit pages, not as a separate mobile application or a switch to the experimental Next.js frontend.

Rationale: The desktop and mobile dashboard must keep the same authentication, permissions, data loading, and business behavior while adapting layout for narrow viewports.

Implications:

- Desktop layout remains the default; mobile rules apply below the shared `720px` breakpoint.
- The pilot covers `Overview`, `Vodomery / Prehled`, and `Mapove podklady / Mapa`.
- Mobile map geolocation is initiated explicitly by the user and rendered only in the Leaflet client.
- Phone coordinates are not sent to FastAPI or persisted.
- Remote mobile geolocation requires a trusted HTTPS dashboard origin.

## DEC-017: Public Caddy Runs Independently

Date: 2026-06-11

Decision: Caddy is operated as a separate process from `start_api_dashboard.bat`. The public dashboard hostname is `monitoring.armexholding.cz`.

Rationale: Separating the reverse proxy lifecycle from the application launcher avoids coupling Caddy restarts and configuration reloads to FastAPI, Streamlit, and scheduler startup.

Implications:

- `start_api_dashboard.bat` starts FastAPI, Streamlit, and the scheduler only.
- The public Caddy site uses its automatically managed public HTTPS certificate.
- Requests under `/api/*` must be proxied to FastAPI on `127.0.0.1:8000`; remaining requests are proxied to Streamlit on `127.0.0.1:8001`.
- Caddy startup, reload, and service recovery must be managed independently.

## DEC-018: Application Launcher Manages Program Files Caddy

Date: 2026-06-11

Supersedes: DEC-017

Decision: `start_api_dashboard.bat` again manages Caddy startup and reload. The runtime binary and configuration are `C:\Program Files\Caddy\caddy.exe` and `C:\Program Files\Caddy\Caddyfile`.

Rationale: Caddy and its operational files were consolidated into a stable system location, and the application launcher should restore the complete API, scheduler, dashboard, and HTTPS proxy runtime together.

Implications:

- The launcher checks that both Caddy files exist before starting application processes.
- FastAPI health is verified first, then Streamlit health, and only then Caddy is started or reloaded.
- Caddy validates the runtime configuration before every run or reload.
- If Caddy is already running, the launcher reloads it through `127.0.0.1:2019` instead of starting a competing listener on ports 80 and 443.
- The root project `Caddyfile` remains the tracked mirror and must stay synchronized with the runtime file under `C:\Program Files\Caddy`.

## DEC-019: Public Clients Use the Dashboard Hostname

Date: 2026-06-11

Decision: The only supported public client entry point is `https://monitoring.armexholding.cz`. Direct client access through the public IP address is not required or supported.

Rationale: All dashboard and API clients should use the stable HTTPS hostname so Caddy can apply the correct TLS certificate, hostname routing, and same-origin API behavior.

Implications:

- Operational verification should target `monitoring.armexholding.cz`, not a URL containing the public IP address.
- The public DNS record must continue to resolve the hostname to the current public endpoint.
- A same-server connection to the public IP is not a required health check and missing NAT loopback is not considered a dashboard failure.
- Caddy continues to route `/api/*` to FastAPI and all remaining hostname traffic to Streamlit.
- `main.py` remains only the scheduler entry point and is unrelated to public hostname routing.

## DEC-020: Dashboard Authentication Persists Across Browser Reloads

Date: 2026-06-11

Decision: A valid dashboard login is persisted in the browser through the `monitoring_dashboard_session` HttpOnly cookie and restored into Streamlit session state after a browser reload.

Rationale: Streamlit `session_state` alone is not durable across a hard browser reload. Requiring users to enter credentials again while their API bearer token is still valid creates unnecessary disruption.

Implications:

- FastAPI endpoints `POST /api/v1/auth/browser-session` and `DELETE /api/v1/auth/browser-session` own browser cookie creation and deletion.
- The cookie uses `HttpOnly`, `SameSite=Lax`, path `/`, token-aligned expiration, and `Secure` when the request is forwarded over HTTPS.
- Streamlit reads the cookie through `st.context.cookies`, validates the token through `/api/v1/auth/me`, and then rebuilds the authenticated user state.
- Logout and HTTP 401 token failures clear both Streamlit authentication state and the browser cookie.
- API outages do not automatically delete a potentially valid persisted cookie.
- The bearer token is not placed in a URL or client-readable local storage.

## DEC-021: Responsive Layout Applies to the Whole Streamlit Dashboard

Date: 2026-06-11

Clarifies: DEC-016

Decision: The shared `720px` responsive layout now applies to every active Streamlit dashboard page through the common `moduly/apps/dashboard/login.py` entry point.

Rationale: Maintaining responsive behavior page by page caused inconsistent mobile support and duplicated style injection. All active pages share the same Streamlit navigation and can use one common responsive layer.

Implications:

- The earlier three-page pilot scope in DEC-016 is complete and no longer limits mobile support.
- Shared responsive rules live in `moduly/apps/dashboard/responsive.py`; pages should add local mobile CSS only for genuinely page-specific behavior.
- General columns stack on mobile, while metric-only rows remain two cards wide.
- Tables and tab bars may scroll horizontally inside their own containers, but the page itself should not overflow horizontally.
- Charts, images, iframes, forms, expanders, dialogs, and action buttons must fit the mobile viewport.
- Existing desktop layouts remain unchanged above the breakpoint.

## DEC-022: API Signing Secrets Stay Outside Version Control

Date: 2026-06-11

Decision: `API_TOKEN_SECRET` must be supplied through an ignored local `.env` file or a protected service environment. Runtime launchers must not contain or assign an API signing secret.

Rationale: A tracked and predictable HMAC secret allows an attacker with source access to forge bearer tokens for dashboard users.

Implications:

- `start_api_dashboard.bat`, its tracked copy, `scripts/start_all_services.ps1`, and `run.txt` do not assign the secret and rely on application configuration.
- FastAPI startup fails when the secret is missing or remains set to the documented placeholder.
- Rotating the secret invalidates every bearer token signed with the previous value.
- Regression tests must prevent fixed API signing secrets from returning to tracked launchers.

## DEC-023: Public Login Has A Temporary Caddy Authentication Gate

Date: 2026-06-12

Decision: Until application-level login throttling is complete, Caddy requires
a temporary shared authentication gate for the Streamlit surface and the
public `/api/v1/auth/login` endpoint.

Rationale: The dashboard must remain available through its public hostname,
but unrestricted automated login attempts should not reach the application.
Stable corporate client IP ranges were not available, and switching to
Tailscale-only access would remove the supported public entry point.

Implications:

- Other `/api/*` routes are not placed behind Caddy Basic Auth because they
  use FastAPI Bearer tokens in the same HTTP `Authorization` header.
- The gate username and bcrypt hash are loaded from
  `C:\ProgramData\monitorovaci_platforma\caddy-dashboard-auth.env`.
- The plaintext credential handoff is stored separately under ProgramData with
  restrictive Windows ACL and must never be committed or printed in logs.
- `scripts/deploy_caddy_runtime.ps1` validates, backs up, deploys, and reloads
  the tracked Caddy configuration from an elevated PowerShell session.
- Tailscale remains the emergency access path.
- Remove the temporary gate only after login throttling and abuse protection
  are implemented and verified.

## DEC-024: Application Login Throttling Replaces The Caddy Gate

Date: 2026-06-12

Supersedes: DEC-023

Decision: The temporary Caddy Basic Auth gate is removed. The public Streamlit
page uses the normal dashboard login form, while FastAPI rate-limits
`/api/v1/auth/login` by normalized account identifier and trusted client IP.

Rationale: The second browser authentication prompt used unrelated credentials,
prevented dashboard administrator credentials from working at the first prompt,
and made the supported login flow confusing. Application-level throttling now
provides abuse protection at the actual authentication boundary.

Implications:

- Caddy no longer loads `DASHBOARD_GATE_USERNAME` or
  `DASHBOARD_GATE_PASSWORD_HASH`.
- Account failures trigger increasing temporary lockouts; IP failures also have
  a bounded temporary limit across different account identifiers.
- Unknown, inactive, and incorrect-password attempts return the same generic
  authentication response and perform password-hash work.
- Uvicorn trusts proxy headers only from `127.0.0.1`; the login route uses
  `request.client.host` and does not parse raw forwarded headers.
- Throttle state is process-local and resets when FastAPI restarts. The current
  production topology uses one API worker.
- The retired ProgramData gate credential files remain sensitive artifacts and
  must not be printed or deleted without explicit approval.

## DEC-025: Production Runtime Starts Through Windows Task Scheduler

Date: 2026-06-12

Decision: On the Windows production workstation, Windows Task Scheduler starts
`start_api_dashboard.bat` with the trigger `At system startup`. The current
supported method for renewing the complete FastAPI, Streamlit, scheduler, and
Caddy process set is a full workstation restart.

Rationale: The processes must recover after any workstation restart without
requiring an interactive user login. Processes launched by the scheduled task
run in a non-interactive session, so their console windows are not available
for later operational control.

Implications:

- Production startup does not depend on a user signing into Windows.
- Agents must not assume they can access, close, or recreate the scheduled
  process consoles from an interactive session.
- When a launcher change or complete process renewal is required, plan for a
  full workstation restart and the corresponding post-restart verification.
- Avoid starting duplicate FastAPI, Streamlit, scheduler, or Caddy instances
  manually while the scheduled runtime is active.
- A future migration to Windows services or separately controllable scheduled
  tasks requires an explicit operational decision and documented rollback.

## DEC-026: Every Workstation Restart Requires A Written Handoff

Date: 2026-06-12

Decision: Before every Windows workstation restart, the active session must
write a dated restart handoff to `SESSION_NOTES.md`. The handoff must record the
current work/conversation state and the expected runtime state after restart.

Rationale: A workstation restart is the supported way to renew the production
process set, but it also removes access to the active process state and can
interrupt unfinished work. A concrete handoff allows the next session to
continue without reconstructing assumptions or exposing the system to
incomplete post-restart verification.

Implications:

- The pre-restart handoff records the reason for restart, completed work,
  pending work, changed/uncommitted files, deployment state, known risks, and
  sensitive files that must remain untouched.
- It records expected FastAPI, Streamlit, scheduler, and Caddy processes,
  loopback/public listeners, configuration paths, and relevant scheduled-task
  behavior.
- It defines exact post-restart checks, including health endpoints, scheduler
  lock/heartbeat/job status, Caddy configuration/hash/listeners, HTTPS routing,
  authentication behavior, and checks specific to the change that triggered
  the restart.
- A restart must not be initiated or requested before the handoff is written
  and reviewed for completeness.
- After restart, the verification result is appended to `SESSION_NOTES.md`,
  including deviations from the expected state.

## DEC-027: Authentication Security Events Use A Protected Audit Log

Date: 2026-06-12

Decision: FastAPI authentication and account-security events are recorded as
structured JSONL outside the dashboard response surface, under
`C:\ProgramData\monitorovaci_platforma\logs\auth_audit.jsonl` by default.

Rationale: Successful and failed authentication, token revocation, password
changes, role changes, and activation changes must be retained for incident
investigation without exposing credentials or operational logs to dashboard
users.

Implications:

- Audit records contain UTC timestamp, normalized account identifiers, trusted
  source IP, result, reason category, and bounded security counters.
- Passwords, bearer tokens, and cookie values are never accepted as audit
  fields.
- The log rotates daily and retains 90 backups unless explicitly configured
  otherwise.
- Warning events are emitted at the account lockout threshold, the IP
  password-spray threshold, and after three administrator-account failures in
  15 minutes.
- Audit write failures must not change authentication responses or expose log
  content to clients.

## DEC-028: Dashboard Passwords Use A Shared 15-Character Policy

Date: 2026-06-12

Decision: Every supported dashboard password creation or change path uses one
shared validator. New passwords require at least 15 characters, permit Unicode,
spaces, passphrases and password-manager values, and are checked against a
local common/compromised password blocklist without composition rules or
periodic expiry.

Rationale: Password-only authentication needs sufficient length and breached
password screening while avoiding brittle character-class rules that reduce
usability and encourage predictable substitutions.

Implications:

- The shared validator is enforced at the database write boundary and reused
  by administrator, self-service, CLI, and Streamlit UI paths.
- Passwords are Unicode NFC-normalized before hashing.
- PBKDF2-HMAC-SHA256 uses 600,000 iterations for new hashes.
- Valid older PBKDF2 hashes remain accepted and are transparently rehashed
  after successful authentication without incrementing `token_version`.
- Existing users are not forced through a bulk password reset. The stronger
  length and blocklist policy applies when a password is created or changed.
- The tracked `moduly/apps/dashboard/password_blocklist.txt` is the local
  offline baseline and can be expanded as operational intelligence improves.

## DEC-029: Map Iframes Do Not Receive The Main API Token

Date: 2026-06-12

Clarifies: DEC-015

Decision: Map iframe HTML and JavaScript do not receive the dashboard bearer
token. `GET /api/v1/map/images` authenticates through the existing HttpOnly
dashboard session cookie and remains the only non-auth route that accepts that
cookie as credentials.

Rationale: Passing the main bearer token into generated iframe JavaScript
allowed any script executing in that iframe to reuse the token against admin
or unrelated API operations. The browser can attach an HttpOnly same-origin
cookie without exposing its value to JavaScript.

Implications:

- Map image requests must use same-origin `/api/v1/map/images` through Caddy.
- The image route validates token signature, expiry, user activity, and
  `token_version`, then reuses existing layer and device authorization.
- A bearer header without the dashboard session cookie is not accepted by the
  image endpoint.
- Other FastAPI routes continue to require bearer authentication and do not
  accept the dashboard session cookie.
- `DASHBOARD_BROWSER_API_BASE_URL` is removed; deployments must expose the API
  under the dashboard origin.
- Map HTML regression tests must reject the presence of the main token,
  `Authorization` headers, or token-bearing iframe arguments.

## DEC-030: Authenticated Dashboard JavaScript Is Application-Controlled

Date: 2026-06-12

Decision: Leaflet `1.9.4` JavaScript, CSS, and referenced images are pinned in
the repository and embedded into generated map iframe HTML. Authenticated
dashboard pages must not load executable JavaScript from public third-party
origins at runtime.

Rationale: A compromised CDN response or upstream package path could execute
with the privileges of an authenticated dashboard page or map iframe.
Repository-pinned assets can be reviewed, hashed, tested, and deployed with
the application.

Implications:

- Reviewed Leaflet assets live under
  `moduly/apps/dashboard/assets/leaflet/1.9.4` with their BSD license and
  source metadata.
- Vendored `leaflet.js` and `leaflet.css` must continue to match the recorded
  official SHA-256 SRI values unless an explicit reviewed upgrade changes the
  version and hashes.
- `map_shared.py` embeds Leaflet code, styles, and image data directly into
  the iframe and must not restore `unpkg.com` or another executable-code CDN.
- Regression coverage scans active dashboard Python and HTML sources for
  external HTTP(S) script tags.
- External map tile, weather, and API data endpoints remain allowed because
  they do not provide executable JavaScript.

## DEC-031: Browser Sessions Use Host-Bound Rolling Tokens

Date: 2026-06-12

Clarifies: DEC-020, DEC-029

Decision: Browser persistence uses the
`__Host-monitoring_dashboard_session` HttpOnly cookie and signed bearer tokens
with both a rolling request-inactivity expiry and a fixed absolute session
expiry.

Rationale: The previous cookie inherited one eight-hour bearer-token lifetime,
derived `Secure` from request headers, and did not revoke sessions for every
authorization change. A host-bound cookie, short rolling expiry, fixed
absolute limit, and centralized `token_version` revocation reduce the useful
lifetime of a stolen session and close privilege-change gaps.

Implications:

- The cookie is always `Secure`, `HttpOnly`, `SameSite=Lax`, `Path=/`, and has
  no `Domain` attribute. Direct HTTP browser persistence is unsupported.
- The default rolling request-inactivity limit is 30 minutes and the absolute
  session limit is 480 minutes.
- Active Streamlit sessions renew at most once every five minutes through
  `/api/v1/auth/session/refresh`; renewal never changes the original session
  start or absolute expiry.
- Tokens without the new signed time claims are rejected, so deployment
  invalidates sessions issued by the previous token format.
- Password, role, activation, section, page, and device-permission changes
  increment `token_version` once and revoke all existing sessions. Email-only
  changes do not revoke sessions.
- Logout explicitly deletes both the current and legacy cookies and clears
  origin cache and storage without requesting domain-wide cookie clearing.

## DEC-032: FastAPI Liveness Is Independent Of Database Readiness

Date: 2026-06-13

Decision: FastAPI completes application startup and exposes `/health/live`
without waiting for PostgreSQL dashboard-table initialization. Database
initialization runs in a background retry task, and `/health/ready` returns
HTTP 503 until initialization succeeds.

Rationale: The production launcher waits for FastAPI liveness before starting
Streamlit and Caddy. A synchronous database bootstrap in the FastAPI lifespan
made a PostgreSQL network outage prevent all three public runtime surfaces from
starting after a workstation restart, even though liveness itself does not
require database access.

Implications:

- `/health/live` reports whether the API process can serve requests and remains
  independent of database availability.
- `/health/ready` reports whether startup database initialization completed.
- Failed initialization attempts are retried without blocking the event loop or
  exposing raw connection details in the retry log.
- Authentication and data routes can remain unavailable while readiness is
  HTTP 503; callers must not interpret liveness as database readiness.
- The launcher can continue to start Streamlit and Caddy after API liveness is
  established, while readiness continues to expose the database outage.

## DEC-033: Scheduler Availability Alerts Contain Only Service Names

Date: 2026-06-13

Decision: Before each scheduled database job performs its database preflight,
the scheduler checks local API liveness, Streamlit health, and the Caddy admin
listener. Availability alert emails contain only the standardized
`Nedostupnost ...` service messages and no operational diagnostics.

Rationale: Availability alerts must be immediately readable and must not expose
connection errors, URLs, job identifiers, timestamps, stack traces, or other
runtime details. Technical diagnostics remain in protected scheduler logs.

Implications:

- PostgreSQL and MSSQL failures still prevent the scheduled data job from
  starting.
- Database alert email content is limited to `Nedostupnost POSTGRES` and/or
  `Nedostupnost MSSQL`.
- Runtime alert email content is limited to `Nedostupnost API`,
  `Nedostupnost DASHBOARD`, and/or `Nedostupnost CADDY`.
- Runtime failures do not block database jobs.
- Runtime probes are retried once to avoid alerts for a short reload.
- A runtime service alerts only on transition to unavailable; it may alert
  again after it recovers and subsequently becomes unavailable.
- `RUNTIME_ERROR_RECIPIENTS` is optional and falls back to
  `DATABASE_ERROR_RECIPIENTS`.

## DEC-034: Scheduler Alert Detail Depends On Active Admin Assignment

Date: 2026-06-13

Clarifies: DEC-033

Decision: Operational scheduler alerts select their content separately for
each recipient. A recipient email assigned to an active dashboard admin
account receives technical details. Every other recipient receives only the
brief alert text defined by DEC-033.

Rationale: Administrators need diagnostic context for incident response, while
non-admin recipients should receive a minimal operational notification without
internal targets, exception reasons, job identifiers, or timestamps.

Implications:

- The rule applies to scheduler job failure/misfire alerts, database
  availability alerts, and API/dashboard/Caddy availability alerts.
- Email matching is trimmed and case-insensitive.
- Admin classification requires both `is_admin=true` and `is_active=true`.
- The scheduler refreshes a local cache after a successful PostgreSQL
  preflight query. The cache stores only SHA-256 email hashes, never plaintext
  email addresses.
- The cache expires after 24 hours. Missing, invalid, stale, or unavailable
  classification fails closed to the brief non-admin alert.
- Technical details may include job or service identity, detection time,
  checked target, and sanitized exception reason. They must never include
  passwords, bearer tokens, cookies, signing secrets, or raw credentials.
- Domain measurement notifications and scheduled report emails keep their
  existing content rules and are not changed by this decision.

## DEC-035: Database Availability Alerts Use Local SQLite Transitions

Date: 2026-06-13

Decision: `quarter_hour_job` persists PostgreSQL and MSSQL availability in a
local SQLite database and sends database availability emails only for state
transitions. It sends one alert on transition to unavailable and one recovery
summary on transition back to available.

Rationale: Stateless database preflight alerting sent the same outage email
every quarter-hour while a database remained unavailable. A local store remains
available during PostgreSQL/MSSQL outages and preserves incident state across
scheduler and workstation restarts.

Implications:

- The runtime database is
  `core/scheduler/data/database_availability.sqlite3` and is ignored by Git.
- `database_availability_state` stores current service state, first observed
  outage time, latest check, latest sanitized reason, and failed-check count.
- `database_availability_events` stores transition events and delivery state.
  Delivered events remain as a small incident history; only transitions create
  rows.
- Initial availability creates baseline state without a recovery email.
  Initial unavailability creates one outage event.
- Repeated unavailable checks update state without creating another event or
  email.
- Recovery email content includes the first failed observation, first
  successful observation, and observed duration for each recovered database.
- Active admin recipients additionally receive the latest sanitized technical
  reason and failed-check count according to DEC-034.
- Transition events remain pending after failed email delivery and are retried
  by a later `quarter_hour_job`.
- Other scheduled jobs continue to skip when database preflight fails, but
  they do not record transitions or send database availability emails.
- SQLite registry failures are logged and do not change database-job preflight
  results. They suppress transition email handling rather than falling back to
  repeated stateless alerts.
- Incident boundaries have quarter-hour scheduler resolution and represent
  observation times, not exact database or network transition times.

## DEC-036: Privileged Dashboard Writes Use FastAPI Admin Boundaries

Date: 2026-06-14

Decision: Browser-initiated privileged mutations execute through authenticated
FastAPI operations with an admin authorization decision in both the route
dependency and the service function. Streamlit must not write revision or
device-administration records directly to PostgreSQL or MSSQL.

Rationale: Disabling controls for non-admin users is not an authorization
boundary. Direct Streamlit database helpers could be invoked without the API
role check and coupled browser-facing code to privileged database sessions.

Implications:

- Revision create/update operations use `/api/v1/admin/revize`.
- Water, gas, electricity, heat-meter, and pressure-device create/update
  operations use `/api/v1/admin/devices/{meter_key}`.
- Admin services reject non-admin contexts before opening a database session.
- Streamlit may retain read-only queries where already established, but new
  browser-facing mutations must use FastAPI.
- Local batch imports, scheduler jobs, database bootstrap, and trusted CLI
  administration remain separate non-browser execution surfaces and must keep
  their own explicit operational controls.
- Regression tests must verify route dependencies, service-level rejection,
  and absence of direct commits in the active revision/device Streamlit
  modules.

## DEC-037: FastAPI Authorization Inventory Is Executable

Date: 2026-06-15

Decision: FastAPI authorization coverage is maintained as an executable
inventory of registered operations and their public, admin, section, page, and
device boundaries.

Rationale: Hand-selected endpoint tests can remain green while a new route is
accidentally left public, assigned the wrong dependency, or returns a
validation response before authorization. Runtime route enumeration makes
authorization expectations fail closed when the API surface changes.

Implications:

- Every registered `/api/v1/*` and `/health/*` operation must be either in the
  explicit public allowlist or return HTTP 401 without authentication.
- Every operation using the admin dependency must be in the explicit admin
  inventory and return HTTP 403 for a valid non-admin bearer token.
- Section and configurable-page route groups have explicit dependency
  inventories and denial tests.
- Device-scoped routes must test both assigned and unassigned identifiers, and
  service functions must reject an unassigned identifier before database
  access.
- Permission changes must invalidate both previously issued bearer tokens and
  browser-session cookie tokens through `token_version`.
- Map catalog, feature, filter-option, and image paths must preserve device
  isolation; feature and filter queries must bind only assigned identifiers.
- Adding or changing an API route requires updating
  `tests/test_api_authorization_regression.py` as part of the same change.

## DEC-038: Public Responses Use Reviewed Security Headers

Date: 2026-06-15

Decision: Caddy applies a shared set of security response headers to the public
dashboard and same-origin FastAPI routes. Stable controls are enforced, while
the Streamlit-compatible Content Security Policy remains report-only.

Rationale: The public HTTPS surface should prevent MIME sniffing, reduce
referrer leakage, restrict framing and unused browser capabilities, and avoid
unnecessary server fingerprinting. Streamlit and embedded dashboard components
currently require inline scripts/styles, WebSockets, data/blob resources, and
same-origin frames, so CSP must be observed before enforcement.

Implications:

- HSTS uses `max-age=31536000` without `includeSubDomains` or preload because
  HTTPS support for unrelated subdomains is outside this application's scope.
- `X-Content-Type-Options: nosniff`,
  `Referrer-Policy: strict-origin-when-cross-origin`, and
  `X-Frame-Options: SAMEORIGIN` are enforced.
- `Permissions-Policy` disables unused browser capabilities and retains
  `geolocation=(self)` for the same-origin mobile map.
- `Content-Security-Policy-Report-Only` allows the current Streamlit runtime,
  WebSocket connection, local iframe components, map tiles, and data/blob
  resources while documenting the intended future policy.
- Moving CSP from report-only to enforcement requires authenticated browser
  verification of login, session renewal, downloads, photos, map rendering,
  and map geolocation.
- Caddy removes `Server` and `Via` from public responses while retaining
  functional protocol headers such as `Alt-Svc`.
- Tracked changes to these headers require Caddy configuration tests,
  validation, deployment through the backed-up runtime script, and live
  verification on both Streamlit and FastAPI responses.

## DEC-039: Production Runtime Uses an Exact Isolated Python Environment

Date: 2026-06-15

Decision: Production FastAPI, Streamlit, and scheduler processes use a
dedicated `.venv-production` built from an exact reviewed dependency lock.
Production Uvicorn runs one worker without reload; reload is confined to
explicit development launchers.

Rationale: The shared `.venv` had dependency metadata drift, missing declared
packages, and prerelease versions. Using it for both development and production
made startup behavior non-reproducible and allowed the Uvicorn file watcher in
the public runtime.

Implications:

- `requirements-production.in` records reviewed direct pins and
  `requirements-production.lock.txt` records exact direct and transitive pins
  for CPython 3.14 on Windows.
- `scripts/bootstrap_production_environment.ps1` creates
  `.venv-production`, pins pip, installs the lock, runs `pip check`, and
  verifies the resulting environment.
- Production startup fails closed on a Python, pip, package-version, missing
  package, or unlocked-package mismatch.
- `start_api_dashboard.bat`, `scripts/start_api.ps1`, and
  `scripts/start_all_services.ps1` are production launchers. Development
  reload belongs only in `scripts/start_api_dev.ps1` and
  `scripts/start_all_services_dev.ps1`.
- FastAPI and Streamlit bind only to loopback. Caddy remains the public
  boundary and its admin API remains loopback-only.
- API, Streamlit, and fresh-start Caddy output uses 10 MiB size rotation with
  10 backups under ProgramData. Existing scheduler and authentication audit
  retention policies remain unchanged.
- The scheduled task retries launcher-level failures, but does not supervise
  detached child processes. Full workstation restart remains the supported
  runtime recovery procedure.
- The current `tra`/`RunLevel=Highest` scheduled-task identity is an accepted
  least-privilege gap. Moving to a dedicated non-interactive account requires
  a separate rights and operational-access validation.

## DEC-040: Public API Surface Remains Minimal

Date: 2026-06-16

Decision: FastAPI documentation routes are disabled by default, and the public
Caddy hostname proxies only `/api/*` to FastAPI. The unauthenticated
`/api/v1/auth/users-exist` endpoint remains public because the active
Streamlit login page uses it before authentication to decide whether the
dashboard has any configured users.

Rationale: OpenAPI and interactive documentation are useful for local
development but unnecessary on the production runtime surface. The login
bootstrap endpoint returns only a minimal boolean and prevents a worse
unauthenticated fallback flow in the dashboard.

Implications:

- `/docs`, `/redoc`, and `/openapi.json` are registered only when
  `API_ENABLE_DOCS=true` is set explicitly.
- Health responses must stay minimal and must not expose database, scheduler,
  host, version, or exception details.
- `users-exist` remains in the explicit public API inventory and should not
  return user identifiers, counts, roles, timestamps, or operational details.
- Caddy should continue to route only `/api/*` to FastAPI and all other public
  paths to Streamlit unless a future reviewed endpoint exposure requires a
  narrower rule.

## DEC-041: Code Integrity Scan Uses An Approved Manifest Outside The Repository

Date: 2026-06-16

Decision: Unauthorized code-change detection uses a SHA-256 manifest of
approved tracked code and deployment configuration files stored outside the
repository under ProgramData. A scheduled scan compares the working tree
against that manifest and reports changed, missing, or unexpected source files.

Rationale: Dependency vulnerability scanning does not detect local code
tampering. A local manifest gives a repeatable baseline for the approved
deployment state without storing runtime data or secrets in the repository.

Implications:

- `scripts/code_integrity_scan.py` owns manifest creation and scan comparison.
- The default manifest path is
  `C:\ProgramData\monitorovaci_platforma\security\code_integrity_manifest.json`.
- Default scan reports are written under
  `C:\ProgramData\monitorovaci_platforma\logs\security`.
- Runtime data, scheduler locks/logs/local SQLite state, SmartFuelPass session
  artifacts, and known electric-meter source data artifacts are excluded from
  the code-integrity scope.
- Baseline creation should happen only after the current code state is
  reviewed and either committed or explicitly approved.
- This is a local integrity control, not a tamper-proof host intrusion
  detection system. An actor able to modify both the repository and the
  scheduled scan mechanism can still bypass it; stronger protection requires
  external monitoring or stricter OS-level controls.

## DEC-042: Dependency Audits Use An Isolated Security Toolchain

Date: 2026-06-18

Decision: Python dependency vulnerability scanning uses `pip-audit` from a
separate `.venv-security` environment, not from `.venv-production`.

Rationale: The production environment is deliberately exact-locked and startup
fails when unlocked packages are installed. Installing audit tooling into that
environment would weaken the runtime invariant and mix operational code with
security tooling.

Implications:

- `requirements-security.in` and `requirements-security.lock.txt` define the
  isolated security-tooling package set.
- `scripts/bootstrap_security_toolchain.ps1` creates `.venv-security` from the
  security lock.
- `scripts/run_dependency_audit.ps1` first verifies `.venv-production` against
  `requirements-production.lock.txt`, then audits both the production lock and
  the installed production `site-packages` path.
- Dependency audit reports are written under
  `C:\ProgramData\monitorovaci_platforma\logs\security` by default.
- Windows scheduled task `MonitoringDependencyAudit` runs the dependency audit
  daily. It is separate from the code-integrity scheduled task because code
  integrity depends on an approved manifest baseline.
- `pip-audit` and its transitive dependencies must not be added to
  `requirements-production.lock.txt` unless the production runtime itself
  starts requiring them.

## DEC-043: Secret Hygiene Reviews Use Redacted Metadata

Date: 2026-06-18

Decision: Secret and runtime-artifact hygiene reviews may scan tracked files
and Git history, but reports must contain only redacted metadata such as rule,
severity, path, line number, and commit. Raw secret values, cookies, bearer
tokens, passwords, credential payloads, and operational data must not be
printed or written into repository documentation.

Rationale: P2.16 requires review of tracked files and Git history for secrets
and private operational data. The review itself must not amplify exposure by
copying sensitive values into terminal output, notes, or commits.

Implications:

- `scripts/secret_hygiene_scan.py` reports `value=REDACTED` and intentionally
  skips raw content review for known sensitive session/auth files.
- `SECURITY_SECRET_INVENTORY.md` documents approved secret locations and
  access expectations without storing values.
- Current tracked SmartFuelPass session artifacts are treated as critical
  until their sessions are invalidated and the files are removed from Git by a
  separately approved cleanup.
- Historical hard-coded API signing secrets were already rotated on
  2026-06-12; other historical credential/session paths require external
  rotation only if the historical value is still valid.
- Git history rewrite is not part of P2.16. It requires a separate explicit
  approval because it rewrites repository history and affects collaborators or
  remotes.

## DEC-044: SmartFuelPass Sessions Are Not Persisted As JSON

Date: 2026-06-18

Decision: SmartFuelPass automation uses configured portal credentials to log
in for each portal run. The application no longer reads or writes reusable
SmartFuelPass browser/session cookies from JSON files.

Rationale: Reusable portal session JSON files are sensitive runtime artifacts
and were previously tracked. Password login per run keeps the approved secret
boundary in `.env` or the protected service environment instead of spreading a
second reusable credential into repository or runtime data files.

Implications:

- `SMARTFUELPASS_EMAIL` and `SMARTFUELPASS_PASSWORD` remain the supported
  authentication inputs for SmartFuelPass automation.
- `SMARTFUELPASS_SESSION_COOKIES_PATH`,
  `data/smartfuelpass/session_cookies.json`, and
  `data/smartfuelpass/auto_login_session.json` must not be restored as runtime
  session persistence.
- Existing public `cookie_path` parameters are compatibility no-ops until a
  later cleanup removes them from callers.
- Historical and local leftover SmartFuelPass session JSON files remain
  sensitive; do not read their contents, and expire portal sessions externally
  if old cookies may still be valid.

## DEC-045: Public Proxy Blocks Documentation Aliases Before Streamlit Fallback

Date: 2026-06-18

Decision: Public Caddy routing explicitly returns HTTP 404 for `/docs`,
`/redoc`, and `/openapi.json` before the general Streamlit fallback. Caddy
automatic HTTP redirects are disabled, and the HTTP listener owns the
HTTP-to-HTTPS redirect so response header stripping applies there too.

Rationale: FastAPI documentation routes are disabled, but the public proxy
fallback previously served the Streamlit shell for documentation-looking paths.
The public surface should not expose API docs and should not make those paths
look valid. Automatic Caddy redirects also exposed the `Server` header outside
the reviewed header block.

Implications:

- Keep explicit `http://monitoring.armexholding.cz` and
  `https://monitoring.armexholding.cz` site blocks in `Caddyfile`.
- Keep `auto_https disable_redirects` while the explicit HTTP redirect block is
  responsible for HTTP-to-HTTPS redirects.
- Keep `@fastapi_docs path /docs /redoc /openapi.json` followed by
  `respond @fastapi_docs 404` before the API and Streamlit handlers.
- Runtime `C:\Program Files\Caddy\Caddyfile` must be synchronized with the
  tracked `Caddyfile` before these rules affect production traffic.

## DEC-046: Map Photos Use A Dedicated Path-Scoped Cookie For Iframes

Date: 2026-06-25

Clarifies: DEC-015

Decision: Map photo requests may authenticate with the dedicated HttpOnly
`__Secure-monitoring_map_image_session` cookie in addition to the main
`__Host-monitoring_dashboard_session` cookie. The dedicated cookie is `Secure`,
uses `SameSite=None`, has no `Domain` attribute, and is scoped to
`/api/v1/map/images`.

Rationale: Streamlit renders the Leaflet map inside a browser iframe. Some
browsers do not attach the main `SameSite=Lax` dashboard session cookie to
iframe fetches, which causes authenticated map photos to fail while the map
data itself loads through the server-side bearer token. A path-scoped HttpOnly
cookie lets the iframe authenticate only the image endpoint without exposing
the main bearer token to JavaScript.

Implications:

- The main dashboard session cookie remains `SameSite=Lax` and `Path=/`.
- The main API bearer token must still not be passed into map iframe
  JavaScript.
- The map image route accepts either the main dashboard session cookie or the
  dedicated map image cookie.
- Logout and invalid-cookie cleanup must expire both current dashboard cookies.
- Do not restore a browser-configured cross-origin image API override; map
  images should still load from the dashboard origin under `/api/v1/map/images`.

## DEC-048: System Health Dashboard Uses Safe Admin Checks

Date: 2026-07-07

Decision: The new `Health systemu` dashboard page will collect post-restart
and operational checks through authenticated admin FastAPI endpoints. Checks
will be added incrementally, one reviewed item at a time.

Rationale: The post-restart shell checklist is useful but should be repeatable
from the dashboard without exposing secrets or raw operational data. FastAPI is
the right boundary for browser-facing operational checks because it can apply
admin authorization, sanitize outputs, and keep workstation-specific probing
server-side.

Implications:

- `Health systemu` lives in the Streamlit footer navigation as an admin-only
  page near `Health scheduleru`.
- Each check should have an explicit data source, status semantics, and display
  format before implementation.
- Browser code must not run local process, filesystem, PowerShell, or database
  probes directly.
- System health API responses must avoid secrets, environment values, bearer
  tokens, cookie values, raw process command lines, raw portal rows, raw device
  photo paths, and credential file contents.
- The first implemented check is runtime startup health: Windows boot time,
  startup scheduled task metadata, expected listeners, and absence of temporary
  listeners.
- Future checks can add proxy/routing, scheduler, production environment,
  database metadata, SmartFuelPass aggregates, and security scan status after
  separate review.

## DEC-047: SmartFuelPass Weekly Reports Use Synced PostgreSQL Rows

Date: 2026-06-26

Decision: SmartFuelPass nabíjecí relace se stahují denně po půlnoci v
`daily_job` do PostgreSQL tabulky `monitoring.smartfuelpass_relace`. Týdenní
SmartFuelPass email/PDF report se staví z těchto synchronizovaných databázových
řádků, ne přímým čtením portálu v okamžiku odesílání reportu.

Rationale: Denní databázový sync vytváří stabilní zdroj pravdy pro reporting.
Týdenní report pak není závislý na aktuálním stavu HTML tabulky portálu,
stránkování, dočasném filtrování portálu, ani na dalším portálovém loginu při
odesílání emailu.

Implications:

- `daily_job` zůstává odpovědný za stažení SmartFuelPass relací z portálu a
  jejich upsert do PostgreSQL.
- `smartfuelpass_weekly_report_job` volá emailový report, který čte z
  `monitoring.smartfuelpass_relace`.
- Synchronizace relací aktualizuje existující záznam podle `id_relace`, aby se
  opravené nebo doplněné hodnoty z portálu promítly do databáze.
- Týdenní období reportu je předchozí uzavřený kalendářní týden
  pondělí-neděle a report filtruje období podle ukončení relace.
- Schéma `monitoring.smartfuelpass_relace` obsahuje `connector_id`, aby report
  z databáze mohl počítat unikátní konektory.
- Přímý portálový builder zůstává diagnostická/ruční cesta, ale nesmí být
  výchozím zdrojem týdenního emailového reportu.
