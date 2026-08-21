# DECISIONS.md

Purpose: durable project decisions for `monitorovaci_platforma`. Add new decisions instead of rewriting history. Mark superseded decisions explicitly.

## DEC-001: Current State Is the Baseline

Date: 2026-06-05

Decision: The current repository state reviewed on 2026-06-05 is the baseline for future sessions.

Rationale: The user explicitly requested a read-only review of the current project state and confirmed that this state should be treated as the starting point for future context documents.

Implications:

- Future sessions should read `AGENTS.md`, `agents/decisions/DECISIONS.md`, and
  `agents/history/SESSION_NOTES.md` first.
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

Decision: `AGENTS.md`, `agents/decisions/DECISIONS.md`, and
`agents/history/SESSION_NOTES.md` are adopted as persistent context files for
future work.

Rationale: The user requested a workflow that allows each session to continue with project context and to automatically preserve relevant changes and decisions.

Implications:

- Agents should propose context-file updates after substantive work.
- Durable decisions belong in `agents/decisions/DECISIONS.md`.
- Session-specific facts and handoff notes belong in
  `agents/history/SESSION_NOTES.md`.
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
write a dated restart handoff to `agents/history/SESSION_NOTES.md`. The handoff
must record the
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
- After restart, the verification result is appended to
  `agents/history/SESSION_NOTES.md`,
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
- `agents/inventories/SECURITY_SECRET_INVENTORY.md` documents approved secret
  locations and
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

## DEC-049: Prediction Models Move Toward A Shared Core

Date: 2026-07-08

Decision: Meter prediction work will move incrementally toward a shared
prediction core with media-specific adapters, candidate model plugins, and
rolling weekly backtests for every candidate. The migration will proceed one
documented checklist step at a time.

Rationale: Vodomery currently have multiple candidate models selected during
weekly rebuild, but the implementation is domain-specific and validates over a
single recent window. Future tuning should compare candidates consistently
across water, gas, and electricity while preserving each medium's data
semantics.

Implications:

- `moduly/mereni/prediction/` is the intended home for shared prediction
  contracts, rolling backtest logic, candidate selection, and reusable metrics.
- Each medium should expose a small adapter for measurements, profile storage,
  active model lookup, scoring integration, and selection metadata.
- Candidate models should be implemented behind a common interface so new
  models can be measured without changing dashboard/report consumers.
- Vodomery are the first migration target. Existing models 1-3 must keep
  compatible outputs and production behavior until an explicit step changes
  selection behavior.
- A fourth vodomery candidate may be added as a 12-month seasonal yearly blend.
  It should initially be measured in rebuild reports without being eligible for
  automatic activation until enough weekly backtest evidence is reviewed.
- Rolling weekly backtests should evaluate all candidates with coverage, MAE,
  RMSE, bias, and a normalized error metric such as WAPE.
- The active implementation checklist lives in `agents/history/SESSION_NOTES.md`; do not
  skip ahead or mark a step done until implementation and targeted
  verification for that step are complete.

Clarification (2026-07-08):

- The target architecture should support both global model selection and future
  per-identifier model selection. Per-identifier activation must remain
  disabled until the shared backtest, storage, reporting, and operational
  review steps explicitly support it.
- After the first live rebuild with rolling metrics, vodomery also add a
  measured-only `Model 5 - long recency weighted blend` candidate. It reuses
  the Model 3 recency-weighted blend shape with a 12-month training window and
  a 90-day half-life, and remains ineligible for automatic activation until
  weekly results are reviewed.
- Prediction rebuild runtime is secondary to prediction quality because these
  jobs run outside operational peak hours. Vodomery are the pilot domain for
  pipeline quality, including per-identifier backtest storage and reporting
  before any per-identifier activation.
- Future electricity prediction should use the same shared pipeline shape, but
  its operational cadence is monthly: calculate predictions around the middle
  of the calendar month for the entire following calendar month.

## DEC-050: Prediction Selection Becomes Per-Identifier And Horizon-Aware

Date: 2026-07-09

Decision: The prediction pipeline will move from one global active model per
medium toward per-identifier model selection for the next forecast period. The
same shared pipeline must support new candidate models, parameter variants of
existing models, media-specific adapters, and configurable forecast horizons.

Rationale: The 2026-07-09 vodomery rebuild showed `Model 3 - recency weighted
blend` as the best global model, while many individual identifiers performed
better with another candidate. Electricity prediction will need the same
selection discipline before production use, and its cadence is monthly rather
than weekly.

Implications:

- The global active model remains an operational fallback and comparison
  signal, but the target production scoring path is selected model per medium,
  identifier, and forecast period.
- Forecast-period semantics are part of the shared contract. Vodomery start
  with weekly periods; elektromery will use monthly next-month periods
  calculated around the middle of the current calendar month.
- Candidate plugins must have stable metadata for model key, version, name,
  parameters, training window, horizon compatibility, and selection
  eligibility.
- A parameter variant of an existing algorithm can be a separate candidate when
  it produces materially different forecasts.
- Per-identifier selection must be persisted as a snapshot for the upcoming
  forecast period. Later rebuilds must not silently rewrite historical
  selections for already evaluated periods.
- Measured-only candidates may appear in reports and backtests, but must not
  be used for production selection until a documented enablement step makes
  them eligible.
- Scoring must retain a safe fallback to the global active model when
  per-identifier selection is missing, below coverage thresholds, or otherwise
  not eligible.
- The detailed rollout plan lives in
  `agents/plans/prediction/PREDICTION_PIPELINE_PLAN.md`; the executable step
  checklist remains in `agents/history/SESSION_NOTES.md`.

Clarification (2026-07-09):

- Vodomery production scoring is enabled to use `active` per-identifier
  selected-model snapshots for the current forecast period when scoring the
  global active model.
- The selected per-identifier model controls only the source profile used for
  expected values. Inserted anomaly scores still use the global active
  `model_version`, preserving the existing event detection and alerting
  contract.
- If an `active` snapshot or selected source profile is missing, vodomery
  scoring falls back to the global active model profile for that measurement
  slot.
- Non-active vodomery candidate scoring remains pure per-candidate scoring so
  comparison and diagnostics stay available.

## DEC-051: Prediction Selection Requires A Deployable Profile

Date: 2026-07-24

Decision: A vodomery candidate may be selected for an identifier and forecast
period only when that rebuild produced a deployable profile for the same
identifier and model. If the metric winner has no profile, selection uses the
next best eligible candidate with sufficient coverage and records
`missing_profile`. If no eligible candidate has a profile, the rebuild fails
before selections or profile snapshots are committed.

Rationale: Historical verification found three consecutive selected Model 2
pairs for one identifier without profile snapshots. Recalculation showed that
none of the candidate models produced a deployable profile for that identifier
in those weeks. A selection without a profile cannot be executed, while
copying a later or stale profile would misrepresent the historical model
state.

Implications:

- Weekly rebuild and historical backfill selection must query the profile pairs
  actually produced in the current transaction.
- `missing_profile` may select a non-global deployable runner-up; other fallback
  reasons continue to select the global model.
- Absence of every candidate profile is a fail-closed condition.
- Historical gaps remain visible when no contemporaneous profile existed.
  Later or stale profiles must not be copied merely to make archive coverage
  complete.
- A future carry-forward policy requires a separate decision with an explicit
  staleness limit and auditable source-period metadata.

## DEC-052: Historical Charts Use Period-Bounded Archived Profiles

Date: 2026-07-24

Decision: When a vodomery dashboard request includes a historical date range,
prediction values come only from selected profile snapshots whose forecast
period contains each measurement timestamp. The current active profile must
not be projected backward into historical periods, and missing archive
coverage remains missing.

Rationale: Reusing the current profile for old measurements creates a
historically false expected-consumption curve. The profile snapshot archive
now preserves the concrete selected profile values and weekly validity bounds
needed to reproduce the prediction that was available for that period.

Implications:

- The prediction-profile API remains backward compatible without date
  parameters and returns the current active profile for those callers.
- A paired `start_date` and `end_date` switches the API to read-only archive
  lookup with `[valid_from, valid_to)` validity metadata.
- Dashboard joins include interval, weekday, slot, and timestamp validity.
- Missing archived weeks are visible as gaps and are not filled from current,
  later, or stale profiles.
- Duplicate archived slot identities are resolved deterministically in favor
  of the highest archive version and newest stored row.

## DEC-053: Periodic Vodomery PDF Predictions Use Archived Per-Identifier Profiles

Date: 2026-07-24

Decision: Expected-consumption values in daily, weekly, and monthly vodomery
branch PDFs come from `active` selected profile snapshots for each identifier
whose forecast period overlaps the report day. Reports must not project the
current global profile backward into historical periods.

Rationale: The dashboard already reproduces historical expectations from
period-bounded selected profiles, but periodic branch reports still loaded one
current global `model_version` for every identifier and every historical day.
That made PDF predictions inconsistent with the model actually selected for a
specific vodomery identifier and forecast week.

Implications:

- `load_branch_day_overview()` is the shared prediction boundary for daily,
  weekly, and monthly branch reports.
- Each report day can use different selected model versions for different
  identifiers.
- Weekly and monthly reports retain their existing daily aggregation, but each
  constituent day reads the archived profile valid on that day.
- Duplicate archived slot identities resolve in favor of the highest archive
  version and newest stored row.
- Missing archive coverage is not filled with the current, later, or stale
  global profile.
- Vodomery billing-summary PDFs inherit the corrected branch report inputs.
  Reports that contain only actual consumption or billing values and do not
  render prediction values are unchanged.

## DEC-054: Undefined Per-Identifier WAPE Falls Back To The Deployable Global Model

Date: 2026-07-27

Decision: When a vodomery identifier has matched rolling-validation data and
defined MAE, RMSE, and bias but WAPE is undefined because actual consumption
is zero, it is not eligible for per-identifier WAPE ranking. Selection falls
back to the globally selected model only when that identifier/model profile
was produced in the current rebuild transaction.

Rationale: The first live weekly rebuild with deployable-profile enforcement
failed for three zero-consumption identifiers. All candidate profiles existed,
but undefined WAPE caused the identifiers to be treated as if no deployable
profile were available. Undefined ranking data and missing deployable profile
are distinct states.

Implications:

- WAPE remains required for per-identifier candidate ranking.
- MAE, RMSE, and bias may establish that validation metrics exist even when
  WAPE is mathematically undefined.
- Zero-consumption identifiers use the deployable global model and record
  `no_identifier_metrics`.
- A genuinely missing global profile still fails closed; this decision does
  not weaken deployable-profile enforcement.

## DEC-055: Vodomery Models 4 And 5 Require A Five-Percent Challenger Margin

Date: 2026-07-27

Decision: Vodomery models 4 and 5 are production candidates, but may be
selected only when their rolling WAPE is at least 5 percent lower than the
best eligible model 1-3 and their rolling MAE is also strictly lower. The
condition applies independently to the global selection and every
per-identifier selection.

Rationale: Shadow results showed material and repeatable improvements for a
small set of identifiers, while many other model-5 wins were below a few
percent. Enabling both candidates under the previous minimum-WAPE policy
would create low-value model switches without a meaningful error margin.

Implications:

- Models 4 and 5 remain rebuilt and measured on every weekly run.
- Coverage and deployable-profile requirements continue to apply before the
  challenger margin.
- Exactly 5 percent lower WAPE qualifies; equal or higher MAE does not.
- If no valid model 1-3 benchmark exists, models 4 and 5 cannot enter
  production through the conditional policy.
- Selection metadata records the conditional versions, WAPE margin, and MAE
  requirement for auditability.

## DEC-056: Current Vodomery Dashboard Profiles Use The Active Per-Identifier Snapshot

Date: 2026-07-27

Decision: Vodomery profile API requests without an explicit date range use
the `active` per-identifier profile snapshot valid at the current Prague time.
When overlapping snapshots exist, the snapshot period with the latest start
is selected deterministically. The current global profile is used only when
no active snapshot covers the current instant.

Rationale: Date-ranged dashboard graphs and periodic branch PDFs already used
period-bounded per-identifier profile snapshots, but the vodomery detail page
called the backward-compatible no-date API branch, which still loaded the
global model profile. Selecting by the whole current date could also return
two periods when legacy and calendar-aligned forecast intervals overlap.

Implications:

- Main and detail vodomery dashboard views now follow the same per-identifier
  production selection as scoring and PDF reports.
- Historical date-ranged requests remain snapshot-only and never fall back to
  a current or global profile.
- Snapshot reads explicitly require `selection_mode = 'active'`; dry-run rows
  cannot appear in dashboard predictions.
- The current no-date fallback remains available for operational continuity
  when a valid active snapshot is absent.

## DEC-057: Vodomery Overview Graphs Preserve The Full Forecast Horizon

Date: 2026-07-27

Decision: Vodomery overview prediction curves are generated independently for
the complete selected date range at the selected hourly, daily, or monthly
granularity. Actual and cumulative-actual curves end at the last available
measurement and are not extended with future zero values.

Rationale: When a currently running week was selected, predictions were joined
only to existing measurement timestamps, except for a special single-day
hourly case. The prediction curve therefore ended with the latest import even
though profile snapshots covered the rest of the selected week.

Implications:

- Future forecast buckets remain visible through the end of the selected
  period.
- Missing future measurements remain missing rather than appearing as zero
  consumption.
- Period prediction construction respects profile validity and resolves
  overlapping snapshots in favor of the latest period start.

## DEC-058: Plynomery Use The Current Prague Calendar Week

Date: 2026-07-27

Decision: Plynomery selected-model and profile snapshots use the current
Prague calendar week from Monday 00:00 inclusive through the following Monday
00:00 exclusive. The weekly rebuild remains scheduled for Monday at 06:10
Prague time and writes the snapshot for the week already in progress.

Rationale: This matches the established vodomery weekly period boundary,
produces stable historical and dashboard date ranges, and avoids making
snapshot identity depend on the exact scheduler start or rebuild duration.
The first hours of Monday are already measured by the time the scheduled
rebuild starts.

Implications:

- A manual rebuild during the same calendar week targets the same forecast
  period and shared conflict rules prevent duplicate snapshot slots.
- Rolling validation for per-identifier selection must use seven-day windows
  aligned to completed Prague calendar weeks.
- Weather-adjusted profile coefficients are independent of the forecast
  weather rows. Future expected values may use hourly weather forecasts only
  where the required HDD inputs are available.
- The current meteorological sync requests a rolling seven-day hourly
  forecast, which does not guarantee that every hour through the end of the
  current calendar week is available at Monday rebuild time. Dashboard
  activation therefore requires an explicit, tested missing-future-weather
  fallback; missing weather must not be silently interpreted as zero HDD.

## DEC-059: New Plynomery Without Sufficient History Have No Prediction

Date: 2026-07-27

Decision: A plynomery identifier that does not have enough valid history to
produce any deployable candidate profile is an expected unavailable state, not
a rebuild failure. The rebuild persists an auditable selected-model snapshot
with `fallback_reason='insufficient_history'` and
`metadata.prediction_available=false`, but intentionally persists no profile
snapshot for that identifier and forecast period.

Rationale: Newly installed gas meters can have valid measurements while still
being below the minimum profile-history thresholds. Generating a zero, copied,
or synthetic profile would misrepresent the forecast. Failing the complete
rebuild would also prevent established meters from receiving valid snapshots.

Implications:

- Missing profiles remain a hard error for identifiers marked as prediction
  available.
- Scoring, API, dashboard, and report consumers must treat
  `insufficient_history` as `Nedostupné`, never as zero consumption and never
  as permission to use a stale profile.
- Winner/model distributions exclude unavailable identifiers; unavailable
  counts are reported separately.
- Once enough history exists, a later rebuild may create a deployable profile
  and replace the unavailable state for the new forecast period.
- The current plynomery UI has no prediction view and the project has no
  plynomery prediction PDF. Their future implementations must consume this
  availability contract.

## DEC-060: Plynomery Per-Identifier Lookup Requires A Period-Valid Decision

Date: 2026-07-27

Decision: When plynomery per-identifier selection is enabled, a measurement
may use a candidate profile only from a selected-model snapshot whose
half-open forecast period contains the measurement timestamp. Overlapping
snapshots resolve by latest forecast-period start, then latest creation time,
then highest snapshot id. A recorded fallback decision may select the global
model. If no period-valid snapshot exists, lookup returns
`no_selection_snapshot` and no profile; it must not silently use the current
global profile.

Rationale: Silent global fallback would hide missing selection coverage and
could project a current or stale profile into a period for which no decision
was made. Explicit unavailability keeps scoring, dashboard, and report
behavior auditable.

Implications:

- The lookup remains disabled by default behind
  `PLYNOMERY_PER_IDENTIFIER_MODEL_SELECTION_ENABLED`.
- `insufficient_history` and `no_selection_snapshot` both resolve to no
  prediction profile, but retain distinct reasons.
- Candidate versions referenced only by unavailable snapshots are not loaded.
- Step 10 must advance the scoring checkpoint when either unavailable state is
  encountered.

## DEC-061: Plynomery Mixed Scoring Retains The Global Score Identity

Date: 2026-07-27

Decision: When per-identifier plynomery selection is enabled for the globally
active scoring stream, one batch may evaluate identifiers through either the
static baseline profile or the weather-adjusted profile selected by their
period-valid snapshots. Persisted anomaly scores retain the globally active
`model_version`, regardless of the source profile version.

Rationale: Existing event, alert, checkpoint, and uniqueness flows identify
the production scoring stream by the global active model version. Changing
that identity per identifier would fragment downstream processing. The source
profile selection is already auditable through selected-model and profile
snapshots.

Implications:

- Static profiles are loaded only for selected static versions.
- Weather profiles and HDD inputs are loaded only when at least one available
  measurement selects the weather-adjusted model; HDD is calculated only for
  those measurements.
- `insufficient_history`, `no_selection_snapshot`, a missing selected profile,
  or missing HDD produces no score for that measurement but still advances
  the global stream checkpoint.
- Non-active candidate streams remain pure per-candidate scoring for model
  comparison.
- Production behavior remains disabled until step 11 explicitly activates the
  per-identifier flag and completes alert/event verification.

## DEC-062: Plynomery Weekly Rebuilds Publish Active Per-Identifier Snapshots

Date: 2026-07-27

Decision: The default full plynomery rebuild publishes selected-model and
matching profile snapshots with `selection_mode='active'`. Dry-run publication
remains available only through an explicit rebuild argument. Scheduler scoring
and alerting pass active per-identifier selection only to the globally active
candidate; non-active candidates remain isolated comparison streams.

Rationale: The reviewed dry-run and insufficient-history behavior passed the
production aggregate gate. Publishing active snapshots is required before the
scoring stream can consume period-valid per-identifier decisions.

Implications:

- Active selected-model decisions without sufficient history intentionally
  have no profile snapshot.
- Every decision marked prediction available must have a matching active
  profile pair.
- Persisted anomaly scores continue to use the global active model version.
- The current running scheduler does not load these code changes until the
  supported full-workstation restart in rollout step 24.
- Step 12 may perform a controlled manual scoring verification without
  sending alerts or running unrelated scheduler jobs.

## DEC-063: Plynomery Profile API Returns Explicit Availability

Date: 2026-07-27

Decision: Authenticated plynomery measurement and prediction-profile API
endpoints require section and device authorization. The current profile
endpoint reads only the period-valid `active` selected-model decision and its
matching profile snapshot. It returns an explicit availability status and
empty profile rows for `insufficient_history`, `no_selection_snapshot`, or
`missing_profile`; it never substitutes zero or the current global profile.

Rationale: Dashboard consumers need to distinguish a real zero prediction
from the absence of a trustworthy prediction. Device-level authorization must
also be enforced before database access because measurements and profiles are
operationally sensitive.

Implications:

- The measurement endpoint uses canonical UTC bounds derived from the selected
  Prague local date range and returns the stored time-semantics fields.
- Weather-adjusted profile responses preserve `profile_kind`, `base_mean`,
  `hdd_slope`, and `hdd_24h_mean`.
- The current endpoint resolves overlapping decisions by latest period start,
  creation time, and snapshot id.
- Historical date-range profile loading remains step 14 and must not project a
  current profile backward.
- Both routes are included in the explicit API authorization inventory and
  must return HTTP 401 without authentication and HTTP 403 without device
  access.

## DEC-064: Historical Plynomery Profiles Are Period-Bounded And Snapshot-Only

Date: 2026-07-27

Decision: Plynomery prediction-profile requests with a date range return only
overlapping `active` selected-model and profile snapshots. Each availability
period and profile row carries its own validity bounds and selection run.
Ranges containing both available and unavailable periods report `partial`.
When no active historical decision exists, the API returns
`no_selection_snapshot` with no rows and does not read a current or global
profile.

Rationale: A current profile can encode a different model, weather
relationship, or training window than the profile that was valid historically.
Projecting it backward would create predictions that were never selected for
that period and would hide genuine history gaps.

Implications:

- `start_date` and `end_date` must be supplied together and use an inclusive
  Prague local-date request converted to a half-open timestamp range.
- Current requests without dates continue to resolve at the exact current
  Prague timestamp.
- Current overlap precedence remains latest forecast-period start, latest
  creation time, then highest snapshot id.
- Historical consumers receive validity metadata and must resolve any
  overlapping periods deterministically when constructing time series.
- No historical API branch may fall back to
  `plynomery_anomaly_profiles` or `plynomery_weather_model_profiles`.
## DEC-065: Plynomery prediction-series construction is period-valid and weather-strict

Date: 2026-07-27

Status: Accepted

Clarifies: DEC-068, DEC-069

Decision:

- One shared plynomery helper constructs hourly, daily, and monthly prediction
  series from active profile snapshot rows.
- A timestamp covered by overlapping profile snapshots uses the latest
  `valid_from`, then the highest `selection_run_id`, followed by deterministic
  validity/model ordering.
- Static profiles use `expected_mean`.
- Weather-adjusted profiles use `base_mean + hdd_slope * hdd_24h`, matching
  production anomaly scoring.
- The 24-hour HDD value is calculated from hourly weather inputs using the
  same partial rolling-window semantics as scoring. Historical weather can
  override forecast input before it reaches the helper.
- Missing HDD, profile coefficients, or a period-valid profile creates no
  prediction value. The helper must not substitute `hdd_24h_mean`, zero, or a
  stale/global profile.

Consequences:

- Dashboard and report consumers can share one deterministic construction
  path.
- Consumers remain responsible for displaying explicit availability from the
  profile API; absent constructed rows are not interpreted as zero.
## DEC-066: Plynomery overview predictions use a device-scoped API series

Date: 2026-07-27

Status: Accepted

Decision:

- `Plynomery / Prehled` loads constructed predictions from
  `GET /api/v1/plynomery/prediction-series`.
- The endpoint enforces both plynomery section access and per-device access
  before database reads.
- Weather history and forecast inputs remain server-side. Historical weather
  overrides forecast values for the same UTC hour before rolling HDD is
  calculated.
- The overview requests hourly output for raw/hourly display, daily output for
  daily detail, and month-end output for monthly detail.
- The prediction is constructed independently across the complete selected
  date range. Actual and cumulative-actual data continue to end at the latest
  real measurement.
- `insufficient_history` and other fully unavailable states display
  `Nedostupné`. Partial profile or weather coverage is displayed as partial
  and is never filled with zero, training HDD, or a stale/global profile.

Consequences:

- Browser code receives only authorized, constructed prediction data and no
  raw weather-table access.
- The same endpoint and construction helper can be reused by the detail page
  and later report work.
## DEC-067: Plynomery detail reuses the overview prediction contract

Date: 2026-07-27

Status: Accepted

Decision:

- `Plynomery / Detail` uses the same authenticated, device-scoped
  prediction-series endpoint and shared construction helper as
  `Plynomery / Prehled`.
- The last-7-days and last-31-days charts consume daily series. The
  24-month history consumes month-end series.
- The page requests only its defined display windows. It does not load a
  current profile and project it backward across the complete measurement
  history.
- A fully unavailable prediction displays `Nedostupné`; an
  `insufficient_history` state includes a short explanation. Partial
  snapshot/weather coverage remains explicitly partial.
- Prediction lines are layered onto existing charts without changing the
  measurement, device metadata, reset, average-consumption, or permission
  behavior.

Consequences:

- Overview and detail cannot choose different profile sources for the same
  identifier and timestamp.
- Existing actual-history charts remain bounded by actual measurements, while
  prediction availability is evaluated independently.
## DEC-068: No legacy plynomery consumption report requires prediction conversion

Date: 2026-07-27

Status: Accepted

Decision:

- The tracked plynomery reporting inventory contains no consumption PDF and no
  scheduled daily, weekly, or monthly consumption report.
- The weekly plynomery email is a model-rebuild performance/audit report, not a
  consumption forecast.
- The overview Excel export remains intentionally actual-only. Device lists,
  measurement/detail tables, anomaly/event views, outlier review, and alert
  emails also remain non-prediction outputs.
- Steps 16-17 cover the only current user-facing gas consumption predictions:
  `Plynomery / Prehled` and `Plynomery / Detail`.
- Step 19 is therefore a regression-backed no-op confirmation. It must not
  invent a new PDF, email recipient, report, or scheduler job.
- Remaining direct candidate-profile reads belong to scoring, candidate
  evaluation, rebuild, or outlier repair and must be explicitly retained or
  corrected in step 20.

Consequences:

- Future gas consumption reports must use the shared period-valid series and
  explicit unavailable-state contract.
- `agents/inventories/PLYNOMERY_REPORT_CONSUMER_INVENTORY.md` is the review
  baseline for steps
  19-20.
## DEC-069: Future plynomery PDFs must adopt the prediction contract at creation

Date: 2026-07-27

Status: Accepted

Decision:

- The user confirmed that plynomery currently have no PDF reports and that
  these reports may be added in the future.
- Step 19 is complete without creating or converting a report.
- A future prediction-bearing gas PDF must use the shared period-valid
  per-identifier series for each report timestamp.
- `insufficient_history`, missing snapshot, missing profile, and missing
  required weather remain unavailable states. The PDF must display
  `Nedostupné` and must not substitute zero, the current profile, or a
  stale/global profile.
- A future report addition must update
  `agents/inventories/PLYNOMERY_REPORT_CONSUMER_INVENTORY.md`,
  report/scheduler registration, and
  regression coverage before recipients or delivery are enabled.

Consequences:

- The current reporting package remains limited to model-rebuild reporting.
- The regression guard intentionally fails when a new report module is added
  until its classification and contract are reviewed.
## DEC-070: Active outlier repair follows per-identifier selection

Date: 2026-07-27

Status: Accepted

Decision:

- Rebuilding plynomery scores after an outlier-review status change must use
  period-valid active per-identifier model selection for the globally active
  score identity.
- The repair path shares score-row construction with normal active scoring,
  including mixed baseline/weather profiles and HDD requirements.
- Repaired rows retain the global active `model_version`, preserving event,
  alert, and candidate identity compatibility.
- An unavailable selection, insufficient history, missing selected profile,
  or missing HDD produces no score. There is no active global-profile
  fallback.
- Non-active versions continue to rebuild from their own candidate profile
  tables. This is intentional candidate evaluation, not a user-facing or
  active-production fallback.
- Rebuild/backtest internals and explicitly disabled per-identifier
  compatibility scoring retain direct candidate-profile reads. User-facing
  prediction APIs and dashboard consumers do not.

Consequences:

- Outlier correction can no longer silently change the active model source for
  an identifier relative to normal scheduler scoring.
- Candidate comparison remains available after a correction.

## DEC-071: Plynomery historical predictions use a weekly per-identifier backfill

Date: 2026-07-28

Status: Accepted

Decision:

- Historical gas prediction coverage begins at the requested date
  `2026-04-21`; the first stored forecast period is the containing calendar
  week beginning `2026-04-20`.
- Backfill periods are Monday-to-Monday calendar weeks and use only
  measurements and weather information available before each forecast week.
- Each week independently evaluates gas candidate models v1 and v2 through
  the same rolling-backtest and deployable-profile selection policy as the
  live pipeline.
- A historical week atomically stores an `active` selected-model decision,
  the selected period-valid profile with
  `archive_source=historical_backfill`, and versioned candidate metrics.
- Historical decisions use `selection_run_id=NULL`; they cannot change the
  current runtime model identity or supersede the live weekly rebuild.
- Backfill planning requires three months of identifier history. Identifiers
  without that history remain unavailable and receive no synthetic, copied,
  current, or global profile.
- Write mode holds the `quarter_hour_job` process lock, commits only complete
  weeks, is insert-only under the shared snapshot identities, and prints
  aggregate results without identifiers.

Consequences:

- `Plynomery / Prehled` and `Plynomery / Detail` can render period-valid
  historical expected-consumption curves from 2026-04-21 for eligible
  identifiers.
- Re-running the same archive version is resumable and does not overwrite
  existing snapshot identities.

## DEC-072: Plynomery per-identifier prediction pipeline is the production contract

Date: 2026-07-28

Status: Accepted

Decision:

- The 25-step plynomery prediction pipeline plan is complete.
- Active scoring, active outlier-review repair, authenticated prediction APIs,
  and dashboard prediction consumers use period-valid active per-identifier
  selected-model and profile snapshots.
- Direct reads of baseline and weather candidate profile tables remain
  permitted only for rebuild/backtest internals, non-active candidate
  comparison, and explicitly documented candidate repair.
- Unavailable history, selection, profile, or required weather input remains
  unavailable; production consumers must not substitute a global, current,
  stale, copied, synthetic, or zero profile.
- The weekly live rebuild and the controlled historical weekly backfill are
  the supported ways to publish active gas prediction coverage.

Consequences:

- Future plynomery prediction-bearing consumers must adopt the shared
  period-valid prediction-series contract.
- Adding a new direct candidate-profile consumer requires classification in
  `agents/inventories/PLYNOMERY_REPORT_CONSUMER_INVENTORY.md` and regression
  coverage.
- The two water-specific follow-up items remain outside the completed
  plynomery plan.

Retained consequence from DEC-071:
- Missing historical eligibility remains visible as `Nedostupné`.

## DEC-073: Vodomery insufficient history is explicitly unavailable

Date: 2026-07-28

Status: Accepted

Decision:

- A vodomery identifier without valid rolling fallback metrics is persisted
  with `fallback_reason=insufficient_history`.
- The unavailable decision retains model identity only for audit
  compatibility; it does not publish a selected profile and does not produce
  an active anomaly score.
- The scoring checkpoint advances past unavailable measurements so one new
  meter cannot block later eligible measurements.
- Prediction APIs, the overview dashboard, and daily, weekly, and monthly
  branch PDF reports preserve unavailable values and display `Nedostupné`
  instead of zero.
- A decision not marked unavailable must have its selected profile. Missing
  profiles for available decisions are hard errors and must not fall back to a
  global, current, copied, synthetic, or stale profile.

Consequences:

- New water meters cannot create misleading zero predictions or alerts before
  sufficient history exists.
- Overlapping decisions resolve by the latest forecast-period start and newest
  run before availability is evaluated.
- The change becomes active only after the pending supported runtime restart.

## DEC-074: Vodomery active outlier repair follows per-identifier selection

Date: 2026-07-28

Status: Accepted

Decision:

- After an outlier-review change, the globally active water score identity is
  rebuilt through the same period-valid active per-identifier selected-model
  path as normal production scoring.
- The score row retains the globally active output `model_version`; the
  selected snapshot determines which identifier profile supplies its expected
  values for each measurement timestamp.
- An unavailable or missing selection produces no active repaired score.
  `insufficient_history` remains unavailable, and a selected available profile
  missing its required slot is a hard error.
- Non-active model versions continue to rebuild directly from their own
  candidate profiles solely for intentional model comparison.

Consequences:

- Outlier repair cannot silently replace historical selected profiles with a
  global, current, stale, copied, or synthetic profile.
- Event rebuilds consume the repaired scores under their existing model
  identities.
- The change becomes active only after the pending supported runtime restart.

## DEC-075: All prediction media share Prague calendar-week boundaries

Date: 2026-07-28

Status: Accepted

Decision:

- Production prediction snapshots use a half-open Prague calendar-week
  validity period: Monday 00:00 inclusive through the following Monday 00:00
  exclusive.
- Plynomery and vodomery construct this period through one shared prediction
  helper. Default period resolution uses current Europe/Prague wall time, not
  UTC.
- The future kalorimetry and elektromery prediction pipelines must reuse the
  same period helper and the established per-identifier selection, profile
  snapshot, availability, scoring, API, dashboard, and consumer contracts.
- A manual rebuild at any instant within the same Prague calendar week targets
  the same snapshot period. Stored and queried timestamps remain half-open;
  Sunday is represented by its prediction buckets, not by an inclusive
  `23:59:59.999999` period end.

Consequences:

- DST and the Sunday-to-Monday UTC offset cannot move a manual rebuild into a
  different forecast week.
- Media-specific candidate models may differ, but period identity and consumer
  semantics must not diverge between plynomery, vodomery, kalorimetry, and
  elektromery.

## DEC-076: SmartFuelPass portal import requires an explicit interactive login

Date: 2026-07-28

Status: Accepted

Decision:

- Remove SmartFuelPass portal synchronization from the unattended
  `daily_job` and its generic scheduler manual-run registry.
- An authenticated dashboard administrator starts only one fixed FastAPI
  operation. FastAPI starts a dedicated Windows task configured for an
  interactive logged-on desktop session.
- The task opens a visible temporary Chrome/Chromium context. The
  administrator completes Cloudflare and portal login manually; automation
  resumes only after the portal leaves the login path.
- The existing table normalization and idempotent PostgreSQL upsert by
  `id_relace` remain authoritative.
- Status shared with FastAPI and Streamlit contains only safe aggregate counts,
  timestamps, state, and sanitized error categories. Credentials, cookies,
  browser storage, portal HTML, raw session rows, and Cloudflare clearance
  values are not persisted or exposed.
- The scheduled weekly report remains database-backed and does not access the
  portal.

Consequences:

- Portal data freshness now depends on an administrator completing the
  interactive import.
- The workflow requires a logged-on and unlocked Windows desktop session on
  the production workstation.
- Cloudflare protection is not bypassed or automated, and no reusable portal
  session is restored.

## DEC-077: SmartFuelPass portal integration is paused pending a supported access path

Date: 2026-07-29

Status: Accepted

Decision:

- The SmartFuelPass portal integration is temporarily closed as active work
  after the Cloudflare challenge could not be completed manually from the
  production workstation.
- Do not retry the portal import, automate or bypass Cloudflare, change network
  identity to evade the restriction, or restore persistent cookies or browser
  sessions.
- Keep the interactive import task available but idle and without an automatic
  trigger. The unattended portal sync remains removed from `daily_job`.
- Return to SmartFuelPass only when a supported access path is available,
  preferably after coordination with the portal operator or through an
  official API/export.
- The scheduled weekly report remains database-backed and may continue using
  the last successfully imported rows. Its output must not imply that portal
  data are current when no new import has succeeded.

Consequences:

- SmartFuelPass data freshness is intentionally paused and must remain visible
  as an open follow-up.
- No further portal action is authorized by the current implementation work.
- Resuming the integration requires a new review of the supported access
  method and a controlled verification plan.

## DEC-078: Kalorimetry prediction uses explicit purpose-specific row quality

Date: 2026-07-29

Status: Accepted

Decision:

- Kalorimetry prediction and scoring use normalized interval energy `delta`;
  cumulative `spotreba_energie` remains meter state and cumulative `objem`
  remains a separate diagnostic.
- A model/scoring observation must have an identifier, timestamp, positive
  interval length, finite cumulative energy state, `platne=true`,
  `reset_detected=false`, and a finite non-negative delta.
- Model input and scoring additionally exclude both `synthetic=true` and
  `gap_detected=true`. These flags are independent in persisted data and must
  not be treated as aliases.
- Consumption display may retain valid synthetic and gap-affected deltas to
  preserve the existing continuity view. Meter-state display may retain a
  finite cumulative state even when the row is invalid, reset, or lacks a
  usable delta.
- A zero delta is a valid measured observation. Heating-season, shutdown, and
  expected-zero behavior must be modeled explicitly; zero rows must not be
  discarded merely to improve candidate metrics.
- Pending or confirmed outliers continue to be represented through the
  existing import/rebuild validity and delta semantics. A confirmed
  consumption becomes eligible only after the reviewed rebuild publishes it
  as a normal valid delta.

Consequences:

- Training, backtests, profile construction, and scoring share one testable
  eligibility contract and reason taxonomy.
- Dashboard continuity and model quality intentionally use different,
  explicit purposes.
- Later SQL loaders must reproduce this contract and receive regression
  coverage against the pure classifier.

## DEC-079: Kalorimetry model 1 is a complete weekly slot baseline

Date: 2026-07-29

Status: Accepted

Decision:

- Kalorimetry model 1 is a calendar baseline keyed by identifier, 15-minute
  interval, weekday, and slot.
- It trains on 12 months of DEC-078-eligible observations and publishes 672
  points per identifier for the shared Prague calendar week.
- Every slot requires at least eight historical observations. If any slot is
  missing or below this threshold, the identifier publishes no partial
  profile and remains explicitly `insufficient_history`.
- Zero energy deltas remain valid profile inputs. Non-finite, negative,
  non-15-minute, and malformed observations cannot satisfy coverage.
- Mean, median, p10, and p90 are clamped to non-negative energy; standard
  deviation retains a small positive floor for downstream anomaly math.
- The candidate is selection-eligible but must not become production-active
  before rolling backtests, per-identifier selection, snapshot persistence,
  and controlled review are complete.

Consequences:

- Profile completeness is deterministic and auditable at 672 points per
  eligible identifier.
- The baseline intentionally does not claim to model heating-season or
  weather response. Those are evaluated separately.
- Table bootstrap is idempotent and occurs only when the candidate rebuild is
  intentionally run; defining or testing the candidate performs no production
  database write.

## DEC-080: Kalorimetry weather model is a per-identifier challenger

Date: 2026-07-29

Status: Accepted

Decision:

- Kalorimetry model 2 is an HDD-adjusted challenger, not a global replacement
  for calendar baseline model 1.
- It fits a non-negative linear HDD slope per identifier and exact
  weekday/15-minute slot using a trailing 24-hour mean of historical heating
  degree hours. The feature window ends at the observation hour and must not
  use future weather.
- Each weather profile follows the same 672-point completeness and
  eight-samples-per-slot threshold as model 1. Low HDD variance yields a zero
  slope; it does not manufacture a weather relationship.
- Model 2 may be selected only through leakage-safe per-identifier rolling
  metrics. Evidence showed aggregate improvement but heterogeneous
  per-identifier results, so it must not be activated globally merely because
  its aggregate WAPE is lower.
- A deploy profile requires applicable weather for every hour mapped from the
  complete half-open Prague forecast period. Any missing or non-finite weather
  makes the candidate explicitly unavailable for that deploy period.
- Missing future weather must never fall back to zero, the training HDD mean,
  historical weather, stale forecast data, or model 1 under the identity of
  model 2.

Consequences:

- Candidate selection can retain model 1 for identifiers or weeks where model
  2 is worse or not deployable.
- Weather fit metadata is stored separately from static profile statistics
  and is carried into later shared snapshots.
- Weather forecast synchronization must be reviewed before activation so its
  horizon reliably covers all weather-dependent forecast models.

## DEC-081: Kalorimetry candidate selection metrics use weekly rolling folds

Date: 2026-07-29

Status: Accepted

Decision:

- Kalorimetry model comparison uses leakage-safe rolling folds with the same
  half-open Prague calendar-week shape as production.
- Each fold trains only on its preceding 12-month window. Validation
  observations never contribute to that fold's baseline or HDD fit.
- Persist global diagnostics and per-identifier validation total, matched
  count, coverage, MAE, RMSE, bias, WAPE, observed fold count, and matched
  fold count.
- Coverage is measured against all DEC-078-eligible validation observations.
  Weather actuals are loaded independently from weather matches, so missing
  HDD remains an unmatched prediction and lowers coverage.
- A zero actual remains in MAE, RMSE, bias, and coverage. WAPE is unavailable
  only when the matched absolute actual sum is zero; it must not be replaced
  by zero or another metric.
- Metric persistence is transaction-scoped to a validation run. It does not
  commit independently of the rebuild transaction.

Consequences:

- Candidate 2 cannot gain apparent coverage by dropping rows with missing
  weather.
- Later selection policy can require both minimum fold count and coverage
  before ranking by per-identifier WAPE.
- Production metrics are not written until the controlled dry-run stage.

## DEC-082: Kalorimetry selection considers only complete deployable profiles

Date: 2026-07-29

Status: Accepted

Decision:

- Before selection, build one deployable catalog entry for every
  candidate/identifier pair.
- An available entry must contain exactly 672 unique weekday/15-minute slots
  for one identifier and model version, with complete weekly coverage,
  finite non-negative expected statistics, ordered p10/p90, and positive
  sample sizes.
- An unavailable entry contains no profile and records an explicit reason:
  `insufficient_history`, `missing_forecast_weather`, `incomplete_profile`,
  or `invalid_profile`.
- Weather unavailability affects model 2 only. The catalog must not copy,
  relabel, or expose model 1 as a weather profile.
- Selection may rank only entries marked available. An available metric winner
  whose deploy profile fails validation is not selectable.

Consequences:

- Partial or malformed profiles fail before selection or snapshot
  persistence.
- Candidate availability and metric performance remain separate audit
  dimensions.
- Later selection can choose the next eligible candidate without hiding why
  another candidate was unavailable.

## DEC-083: Kalorimetry per-identifier selection is eligibility-gated and auditable

Date: 2026-07-29

Status: Accepted

Decision:

- Kalorimetry candidate selection first requires finite WAPE, MAE, RMSE, and
  bias, coverage of at least 85 percent, at least eight matched weekly folds,
  and an available deployable-catalog profile.
- Eligible candidates rank deterministically by WAPE, MAE, RMSE, absolute
  bias, descending matched-observation count, and stable model version.
- The candidate with the best metrics is audited independently from profile
  deployability. If it cannot be deployed, the next eligible candidate may be
  selected, while the unavailable candidate's explicit profile reason remains
  the decision fallback reason.
- If no candidate is eligible, the identifier remains unavailable with an
  explicit reason. Selection must not synthesize, copy, relabel, or silently
  substitute a profile.
- Step 9 is a pure dry-run contract. It performs no database persistence,
  snapshot publication, production activation, scoring, or alerting.

Consequences:

- A weather candidate cannot win by reporting metrics for rows or folds that
  do not meet the production coverage contract.
- Missing forecast weather can legitimately leave model 2 unavailable while
  allowing model 1 to be selected under its own identity.
- Atomic persistence of the selected decision, candidate audit, and exact
  period-valid profile remains a separate step and must fail before commit if
  an available selection has no profile.

## DEC-084: Kalorimetry decisions and profiles publish as one validated snapshot batch

Date: 2026-07-29

Status: Accepted

Decision:

- Kalorimetry uses the shared selected-model and prediction-profile snapshot
  tables with `medium_key='kalorimetry'`; no medium-specific snapshot archive
  is introduced.
- Construct and validate the entire persistence plan before the first SQL
  statement. Each available decision must resolve to the exact identifier,
  model version, model key, forecast period, and complete validated 672-point
  deployable profile.
- An available decision with a missing, unavailable, mismatched, partial, or
  invalid profile aborts before persistence. An explicitly unavailable
  identifier is reported by the batch but is not stored as a selected model.
- Preserve the shared fallback enum for consumer compatibility and retain the
  exact kalorimetry fallback/profile reason plus complete candidate audit in
  snapshot metadata.
- Insert selected-model rows and profile rows inside one nested transaction.
  The helper flushes but does not commit; the caller owns the surrounding
  rebuild transaction and atomic commit or rollback.

Consequences:

- Consumers cannot observe a newly selected kalorimetry model without its
  matching period-valid profile from a successfully committed rebuild.
- Idempotent shared-table conflict handling is retained without weakening
  profile completeness validation.
- Production table bootstrap and the first snapshot publication remain
  controlled later rollout actions, not side effects of defining this
  contract.

## DEC-085: Kalorimetry performance reporting reuses the shared aggregate surface

Date: 2026-07-29

Status: Accepted

Decision:

- Register kalorimetry as a weekly medium in the existing admin-only
  prediction-performance API and Streamlit dashboard instead of creating a
  separate monitoring page.
- Publish only candidate catalog metadata, aggregate validation metrics,
  snapshot winner/fallback distributions, coverage, availability totals, and
  a bounded worst-identifier list. Do not expose raw measurements, profile
  points, weather rows, or operational credentials.
- Candidate performance for a selection run uses the latest persisted
  validation run per model whose reference boundary is no later than the
  selection deploy start.
- Before the relevant tables and first controlled run exist, the medium
  reports `not_run` rather than failing the whole cross-media response.
- The kalorimetry rebuild report is a pure aggregate data builder plus escaped
  HTML renderer. It does not send email or establish recipients; delivery
  requires a later explicit consumer decision.

Consequences:

- The existing prediction-performance dashboard automatically renders
  kalorimetry with the same candidate, selection, history, and catalog
  structure as other media.
- Winner counts and fallback reasons derive from the shared period-valid
  snapshots, while pre-persistence dry-run availability remains visible in
  the rebuild report.
- Step 12 can review one production dry-run through aggregate outputs without
  enabling scoring, alerting, report delivery, or active consumption.

## DEC-086: The first kalorimetry production dry-run blocks activation

Date: 2026-07-29

Status: Accepted

Decision:

- Treat the 2026-07-29 production dry-run as a successful read-only pipeline
  safety review but not as model or snapshot activation approval.
- PostgreSQL kalorimetry data ended at 2026-05-18 07:45:13. Consequently both
  candidates had zero validation observations across the eight current weekly
  folds, and every one of 14 identifiers remained
  `no_identifier_metrics`.
- Calendar baseline deployment profiles were complete for all 14 identifiers.
  The coherent forecast run at 2026-07-26 22:17:28 produced only 145 of 168
  required trailing-24-hour HDD features, so weather deployment was
  unavailable for all identifiers.
- Before repeating an activation-eligible current-period dry-run, complete a
  separately reviewed kalorimetry measurement backlog import and correct and
  verify the weather forecast horizon.
- Do not persist a selected-model snapshot, activate scoring, send alerts, or
  deliver a rebuild report from this dry-run result.

Consequences:

- Empty current metrics cannot silently fall back to an otherwise complete
  baseline profile.
- The required weather forecast follow-up is now a demonstrated production
  blocker rather than a theoretical risk.
- Historical-backfill implementation may proceed independently, but any
  production apply must preserve its separate approval and must not disguise
  the stale current import state.

## DEC-087: Kalorimetry historical snapshots are recomputed at each weekly boundary

Date: 2026-07-29

Status: Accepted

Decision:

- Kalorimetry historical backfill is a sequence of immutable Prague
  Monday-to-Monday identifier/week calculations, not a projection of a
  current profile into the past.
- Before candidate evaluation, exclude every measurement and historical
  weather observation at or after the forecast-period start. Recompute both
  eight-fold candidates and deployable profiles independently for each week.
- Historical weather deployment requires an explicit forecast issue timestamp
  strictly earlier than the forecast week. Missing provenance or a forecast
  issued at/after the boundary is invalid; missing/incomplete eligible
  forecast coverage leaves the weather candidate unavailable.
- Prepare two candidate audit metric rows per evaluated identifier, one
  selected-model decision when available, and the exact selected 672-point
  profile.
- Shared historical snapshots use `selection_mode='active'`,
  `archive_source='historical_backfill'`, a versioned archive identity, and
  `selection_run_id=NULL`. They must not change the current selection run or
  runtime model identity.
- Step 13 contains no production apply function. Dry-run, apply, resume,
  conflict detection, and verification are a separate reviewed step.

Consequences:

- Future measurements, corrected later observations, or later weather cannot
  leak into an already calculated historical week.
- A lack of archived pre-week forecast data can make model 2 unavailable
  historically without blocking a valid baseline snapshot.
- Production backfill remains non-authorized until the step 14 controls are
  implemented and explicitly approved.

## DEC-088: Kalorimetry backfill resumes only from exact immutable identities

Date: 2026-07-29

Status: Accepted

Decision:

- Backfill workflow has separate `dry_run`, `apply`, `resume`, and `verify`
  behavior. Dry-run and verify perform no writes. Apply requires an explicit
  confirmation argument and pre-existing reviewed shared tables.
- Classify each planned weekly batch as `absent`, `complete`, or `conflict`.
  An empty reviewed identity is absent. Complete requires exact equality of
  selected decisions, candidate rows, selected flags, profile model/count
  pairs, and deterministic content fingerprints.
- Fingerprint selected-decision metrics and fallback identity, candidate
  eligibility/ranking/metrics, and every profile slot/statistic. Equal row
  counts with different content are a conflict.
- Treat partial state, non-null historical decision/profile selection-run
  references, a non-historical profile source, missing subsets, extra rows,
  or any changed fingerprint as conflict. Never patch a conflict in place.
- For an absent week, insert selected decisions, both candidate metrics, and
  selected profiles inside one savepoint. Require insert counts to equal the
  calculated batch exactly before flush and weekly commit; otherwise roll
  back.
- Resume skips only a complete week. It must not rewrite it or infer
  completeness from an archive run label alone.

Consequences:

- Interrupted runs can continue deterministically without duplicating or
  silently modifying immutable historical weeks.
- Concurrent insertion or an unexpected idempotent conflict becomes an insert
  count mismatch and rolls back rather than producing a partial commit.
- The presence of an apply function is not authorization to execute it.
  Step 15 production execution remains separately approval-gated.

## DEC-089: The first controlled kalorimetry historical backfill is baseline-only

Date: 2026-07-29

Status: Accepted

Decision:

- After explicit execution approval, apply and verify the immutable
  kalorimetry historical archive for `[2025-07-28, 2026-05-18)`, covering 42
  complete Prague calendar weeks and 588 identifier-weeks.
- Accept only the exact verified final state: 430 selected decisions, 1,176
  candidate metric rows, and 288,960 profile points. Every selected profile
  contains exactly 672 quarter-hour points and all 42 weekly identities are
  complete with zero conflicts.
- Retain baseline model 1 for all 430 available decisions. Model 2 remains
  historically unavailable because no evaluated week has a complete coherent
  forecast archive issued before the week boundary.
- Preserve explicit unavailability: 13 of 14 identifiers receive historical
  snapshots; the other identifier retains candidate audit metrics without a
  fabricated selection or profile.
- Keep `selection_run_id=NULL` on every historical decision and profile. Do
  not create or populate current kalorimetry selection, active-profile, weather
  profile, or validation tables as part of the backfill, and do not run
  scoring, events, alerts, or report delivery.

Consequences:

- Period-valid historical consumers can proceed to implementation against a
  complete, verified baseline archive without changing current runtime model
  identity.
- Historical absence of forecast weather remains visible and cannot be hidden
  by later observations, stale weather, zero, or a training mean.
- Current activation remains blocked by the stale measurement import and
  incomplete current forecast horizon identified by DEC-086.

## DEC-090: Kalorimetry profile lookup is period-valid and exact-slot only

Date: 2026-07-29

Status: Accepted

Decision:

- Load kalorimetry selected decisions and profile snapshots in bounded batches
  scoped by medium, explicit selection mode, identifiers, and overlapping
  timestamp range.
- Treat forecast validity as half-open. For overlapping decisions choose the
  latest forecast-period start, then newest creation time, then highest row id.
- After selecting a decision, accept only a profile row with the same
  identifier, exact forecast boundaries, selected model version, interval,
  Prague weekday, and slot. Resolve duplicate archive candidates by highest
  archive version, newest creation time, and highest row id.
- Return explicit unavailability for `no_selection_snapshot`,
  `insufficient_history`, and `missing_profile`. Never substitute a global,
  current, stale, zero, or different-model profile.
- This lookup is read-only. Step 16 does not create active scoring rows,
  checkpoints, events, or alerts.

Consequences:

- Historical scoring can consume the immutable backfill without projecting a
  current profile backward or crossing a weekly validity boundary.
- An available decision with a missing exact profile remains observable as a
  data-integrity failure for the next scoring step instead of silently
  changing model identity.
- Step 17 may implement anomaly scoring against this lookup while preserving
  explicit unavailable rows as no-score observations.

## DEC-091: Kalorimetry scoring separates stream identity from selected model identity

Date: 2026-07-29

Status: Accepted

Decision:

- Use `model_version=1` as the stable identity of the kalorimetry
  active-selection scoring stream. Store the actual per-identifier selected
  candidate version, selected-decision snapshot id, and exact profile snapshot
  id on every score row.
- Score only observations accepted by the kalorimetry `SCORING` quality
  contract and the exact period-valid lookup from DEC-090.
- For invalid observations, `no_selection_snapshot`, or
  `insufficient_history`, write no score and advance the stream checkpoint
  through the processed batch. Never substitute another profile.
- Treat `missing_profile` for an otherwise available decision as a hard
  integrity error. Abort before either score insertion or checkpoint
  advancement.
- Insert scores idempotently by measurement id and stable scoring identity.
  Persist score rows and checkpoint advancement in one transaction.
- Step 17 adds table models and bootstrap code but does not authorize creating
  the production tables or running production scoring. Activation and
  historical reconciliation remain later reviewed steps.

Consequences:

- Events and downstream consumers can retain one stable active scoring stream
  while every score remains traceable to the exact candidate decision and
  immutable profile point that produced it.
- Missing history does not block later measurements from being processed, but
  corrupt available snapshot state cannot be silently skipped.
- The current stale-import and forecast-horizon blockers remain unchanged.

## DEC-092: Kalorimetry events are heat-specific and alert delivery remains disabled

Date: 2026-07-29

Status: Accepted

Decision:

- Detect only `SPIKE` and `SUSTAINED_HIGH_USAGE` from kalorimetry anomaly
  scores. A spike requires z-score above 5; sustained high usage requires
  eight consecutive z-scores above 3.
- Do not inherit gas/water night-usage or expected-zero event semantics without
  a separately reviewed heat-domain contract.
- Persist event state, created/resolved event changes, processed-score flags,
  and the event-engine checkpoint in one transaction.
- Produce deterministic `CREATED` and `RESOLVED` alert transition plans with
  `delivery_enabled=False`. Do not add recipients, delivery records, email
  sending, API mutation, or scheduler execution before an aggregate dry-run is
  reviewed and alert sending receives explicit approval.
- When an outlier-review change rebuilds kalorimetry measurements, delete and
  rebuild only the stable active scoring stream from the affected timestamp
  using exact period-valid selected profiles. If scoring has not been
  activated and its table does not exist, score repair is a no-op.
- Do not persist any non-active candidate repair through the active scoring
  table. Candidate comparison remains isolated in candidate metrics/profiles.

Consequences:

- Event semantics reflect heat behavior instead of mechanically copying all
  water/gas alert categories.
- Review corrections cannot reintroduce global or current-profile fallback
  into historical active scores and do not move the global scoring checkpoint.
- Step 18 creates no production state. Step 19 must reconcile expected
  historical score/event effects in dry-run mode before any activation.

## DEC-093: Kalorimetry historical score/event reconciliation is an impact estimate

Date: 2026-07-29

Status: Accepted

Decision:

- Reconcile only the controlled historical range
  `[2025-07-28, 2026-05-18)` in a PostgreSQL read-only transaction, processing
  measurements in bounded batches and rolling the transaction back.
- Treat absent score/event tables as an empty persisted baseline. Never create
  schema or call score/event apply paths from the dry-run.
- Record the reviewed aggregate result: 401,363 measurements; 395,149
  scoring-eligible; 6,214 ineligible; 285,766 expected scores; 109,383
  eligible observations without an available period-valid selection; and
  115,597 intentionally unscored observations in total.
- Expected event impact is 3,456 created and 3,456 resolved episodes. With no
  persisted score/event tables, persisted counts are zero, all 285,766 scores
  and 3,456 created episodes are missing, and unexpected/mismatched/flag/
  severity/event-mismatch counts are zero.
- Interpret zero mismatch and change counts only as absence of overlapping
  persisted state, not as validation of an activated scoring/event database.
- This dry-run is not apply or alert-delivery approval.

Consequences:

- Historical activation impact is quantified before any score, checkpoint,
  event, alert, or email state exists.
- The large intentionally-unscored population remains explicit and cannot be
  filled from global or stale profiles.
- API/dashboard work may proceed independently while score/event activation
  remains a later explicitly reviewed operation.

## DEC-094: Kalorimetry measurement and profile API reads are device-scoped

Date: 2026-07-29

Status: Accepted

Decision:

- Expose bearer-authenticated kalorimetry measurement-series and
  prediction-profile GET endpoints through FastAPI.
- Require `kalorimetry` section access in the route dependency and repeat
  section plus requested-device authorization in the service before opening a
  database session.
- Convert measurement date ranges from Prague local dates to half-open UTC
  boundaries and retain canonical source/time metadata in the response.
- A profile request without dates reads only the active decision covering the
  current Prague instant. A dated request requires both boundaries and returns
  only overlapping active snapshot periods with explicit per-period
  availability.
- Resolve profile duplicates only within the exact selected decision/model/
  period/slot by highest archive version, newest creation time, and highest row
  id.
- Return `no_selection_snapshot`, `insufficient_history`, or
  `missing_profile` explicitly. Do not read a global profile or project a
  current/stale profile into an uncovered historical period.
- Keep the existing `/kalorimetry/devices` route admin-only for outlier-review
  administration; step 20 does not broaden that endpoint.

Consequences:

- Kalorimetry browser consumers receive the same authorization boundary and
  historical availability semantics established for gas.
- Current stale import state appears as explicit current-profile
  unavailability rather than a misleading historical fallback.
- Prediction-series construction remains isolated to step 21.

## DEC-095: Kalorimetry prediction series are period-valid and cumulative

Date: 2026-07-30

Status: Accepted

Decision:

- Expose hourly, daily, and monthly kalorimetry prediction series through a
  bearer-authenticated, section- and device-scoped FastAPI endpoint.
- Build every interval only from the selected profile snapshot whose half-open
  validity covers that timestamp. Never fill uncovered timestamps from a
  global, current, stale, copied, or zero profile.
- Clamp negative expected interval consumption to zero before aggregation.
- Derive expected cumulative consumption over the complete chronologically
  ordered requested range; do not reset it at weekly snapshot boundaries.
- Preserve explicit unavailable/partial status and model/profile-kind audit
  metadata for consumers.

Consequences:

- Overview and detail pages can share one trusted series contract in steps 22
  and 23.
- Historical weekly snapshot boundaries do not create artificial cumulative
  resets.
- Missing historical coverage remains visible instead of being silently
  manufactured.

## DEC-096: Kalorimetry overview consumes the shared prediction-series API

Date: 2026-07-30

Status: Accepted

Decision:

- `Kalorimetry / Přehled` obtains expected consumption only from the
  authenticated, device-scoped kalorimetry prediction-series endpoint.
- Present actual consumption, expected consumption, absolute deviation, and
  percentage deviation while retaining heat-specific labels and existing
  energy value formatting.
- Draw expected interval and cumulative consumption in light gray below the
  actual series. Derive the displayed cumulative expectation from the complete
  chronologically ordered API response and never reset it at snapshot
  boundaries.
- Display `Nedostupné` for unavailable predictions and a visible warning for
  partial coverage. Do not substitute current, global, stale, or zero
  profiles.

Consequences:

- The overview has no privileged direct prediction-profile database path.
- Actual measurements remain usable when prediction coverage is unavailable.
- Step 23 can reuse the same API and presentation semantics in the detail
  page.

## DEC-097: Kalorimetry detail reuses daily and monthly prediction series

Date: 2026-07-30

Status: Accepted

Decision:

- `Kalorimetry / Detail` reads expected consumption only through the shared
  authenticated, device-scoped prediction-series dashboard loader.
- Use daily prediction rows for the seven-day and 31-day views and monthly
  prediction rows for the 24-month history.
- Align predictions only to the calendar days or months already represented
  by each chart. Draw the light-gray prediction below the actual energy bars.
- Keep unavailable, `insufficient_history`, and partial coverage explicit.
  Do not fill gaps from current, global, stale, copied, or zero profiles.
- Preserve existing device metadata, photograph, reset/change history,
  measurement tables, and responsive layout.

Consequences:

- Overview and detail now share one authorization and historical-availability
  contract.
- Prediction unavailability does not hide actual measurements or device
  information.
- Downstream-consumer inventory can proceed as step 24 without introducing a
  second dashboard prediction path.

## DEC-098: Only two current kalorimetry outputs are prediction-bearing

Date: 2026-07-30

Status: Accepted

Decision:

- Treat `Kalorimetry / Přehled` and `Kalorimetry / Detail` as the only current
  user-facing prediction-bearing kalorimetry outputs. Both must retain the
  authenticated device-scoped prediction-series API.
- Keep dashboard exports, measurement/state tables, device metadata and list,
  reset history, and global monitoring-health summaries intentionally
  actual-only.
- Keep the scheduled JORDAN monthly report actual-only. Its kalorimetry row is
  a difference between two valid cumulative energy states; do not add a
  prediction, recipient, or new report without separate approval.
- Keep score/event/outlier paths classified as anomaly/event and candidate,
  backfill, reconciliation, performance, and rebuild-report paths classified
  as model rebuild/audit.
- Candidate profile tables must remain internal to candidate adapter/rebuild
  code and must not become direct dashboard or consumption-report sources.

Consequences:

- Step 25 scheduler work has an explicit boundary and cannot use the inventory
  as authorization for report or alert delivery.
- Existing actual-only outputs remain stable and are not forced to display a
  prediction merely because snapshot data exists.
- Future prediction-bearing reports require an inventory update and explicit
  product/delivery approval.

## DEC-099: Weather forecasts are archived by issuance and cover nine days

Date: 2026-07-30

Status: Accepted

Decision:

- Request nine forecast days from Open-Meteo so a Sunday synchronization can
  cover the complete following Prague Monday-to-Monday period plus the
  trailing 24-hour HDD input window.
- Store forecast rows by composite identity `(forecast_run_at,
  datetime_hour)`. Never overwrite an older issuance merely because a newer
  run contains the same target hour.
- A current kalorimetry deployment may use only one coherent forecast run
  issued strictly before the forecast-period start. It must contain every raw
  hour needed to derive all 168 trailing-24-hour HDD values.
- Consumers that need the latest operational forecast for a target hour must
  resolve the newest issuance deterministically now that multiple runs are
  retained.
- Do not reconstruct or activate the already-started current week from a run
  issued after Monday.

Consequences:

- Historical forecast provenance is retained for leakage-safe backfill and
  audit.
- The daily 00:15 synchronization creates an eligible Sunday run before the
  next weekly Monday rebuild.
- Existing gas weather consumers remain deterministic with archived runs.

## DEC-100: Agent documentation uses stable thematic paths

Date: 2026-07-30

Status: Accepted

Decision:

- Keep `AGENTS.md` in the repository root so agent tooling can discover the
  project operating instructions.
- Store other agent-facing project documentation under `agents/`, grouped by
  stable purpose: decisions, history, plans, runbooks, inventories, security,
  work indexes, and future agent registrations.
- Track lifecycle state in `agents/work/` instead of moving implementation
  plans whenever their status changes.
- Keep `agents/history/SESSION_NOTES.md` intact during the structural move.
  Splitting its older content into bounded archives is a separately verified
  backlog task.
- Registering a future monitoring agent does not itself authorize production
  writes, restarts, alert delivery, or external messages.

Consequences:

- The repository root contains only the required agent entry point rather than
  the complete Markdown documentation set.
- Documentation links, tests, and integrity tooling must use the stable
  `agents/` paths.
- Active, blocked, queued, and completed work have concise dedicated indexes
  without duplicating detailed plans or session history.

## DEC-101: Session history is archived in immutable monthly files

Date: 2026-07-30

Status: Accepted

Supersedes the monolithic-log parts of DEC-006 and DEC-046.

Decision:

- Keep `agents/history/SESSION_NOTES.md` short. It contains only the current
  baseline, active handoff, latest relevant verification, and archive index.
- Store completed dated session entries in immutable monthly files under
  `agents/history/archive/`.
- Track current lifecycle state in `agents/work/` and durable behavior in this
  decisions file. Do not duplicate those records into a growing session
  journal.
- Use `agents/history/templates/SESSION_ENTRY.md` for general entries and
  `agents/history/templates/RESTART_HANDOFF.md` for mandatory restart
  handoffs.
- Archive extraction must verify that every dated entry block is represented
  exactly once using count and SHA-256 fingerprint equality.
- Historical archive corrections require a new explicit correction record;
  never silently rewrite an archive.

Consequences:

- Routine session startup reads a small current file rather than the complete
  operational history.
- Detailed evidence remains searchable by month without consuming normal
  working context.
- The legacy preamble is preserved separately for audit but is no longer
  treated as the current project baseline.

## DEC-102: The first monitoring agent is an independent read-only supervisor

Date: 2026-07-30

Status: Accepted

Decision:

- Build the first monitoring agent as a runtime independent from `main.py`.
  It consumes the existing authenticated scheduler and system health
  endpoints instead of duplicating their collectors or querying operational
  databases directly.
- Begin in test mode. The agent may persist only its own bounded incident
  state, audit data, and local reports. It may not change application state,
  run jobs, control processes, send external messages, or replace current
  scheduler alerts.
- Use deterministic, versioned rules for health classification, confirmation,
  recovery, severity, correlation, and incident lifecycle. Agentic
  interpretation may explain safe facts and prepare programmer task drafts,
  but it may not invent root causes or override deterministic state.
- Group repeated observations into stable incidents and produce reports rather
  than blindly sending one email per failing poll.
- Keep current scheduler alerts authoritative during a reviewed parallel
  pilot. Replacing alert delivery for Scheduler Health or System Health
  requires separate evidence, rollout and rollback plans, independent
  self-monitoring, and explicit approval.

Consequences:

- Scheduler Health remains the source of current scheduler facts; the agent
  adds temporal supervision, correlation, recovery tracking, reporting, and
  actionable diagnostic preparation.
- A scheduler-process failure can remain observable because the agent does not
  share the `main.py` runtime.
- Least-privilege authentication, agent-owned storage, thresholds, hosting,
  delivery, and pilot duration remain explicit design and approval gates.
- The implementation checklist lives in
  `agents/plans/monitoring/SCHEDULER_MONITORING_AGENT_PLAN.md`.

## DEC-103: The monitoring agent runs on a different network workstation

Date: 2026-07-31

Status: Accepted

Decision:

- Run the first monitoring agent on a different workstation from `main.py`,
  FastAPI, Streamlit, Caddy, and the operational databases. The remote station
  owns the agent lifecycle, state, reports, logs, and credentials.
- Keep FastAPI bound to loopback. Do not expose the existing admin
  `/health/*` routes directly to the LAN or public internet.
- Add a future private, authenticated, GET-only monitoring API facade that
  reuses existing Health collectors and returns only the reviewed field
  allowlist. Logs, process command lines, raw data, business totals, manual
  jobs, and mutations remain excluded.
- Carry monitoring traffic over an approved encrypted private or overlay
  network with device/source restrictions and a dedicated least-privilege
  application identity.
- Treat loss of the target network path as `unknown/unreachable`, not as proof
  that the scheduler failed.
- Keep current alerts authoritative until the remote pilot and separately
  approved replacement gates pass.

Consequences:

- Restart, power loss, network loss, or process failure on the monitored
  workstation does not stop the agent.
- The remote agent can observe machine-level unavailability but requires its
  own self-heartbeat and a later decision about who monitors the monitoring
  workstation.
- The earlier same-host Scheduled Task proposal is superseded before
  implementation or registration.
- Network listener, firewall, proxy, authentication, credential, service, and
  deployment changes remain separately reviewed implementation steps.

## DEC-104: The remote workstation is a minimal agentic supervision center

Date: 2026-07-31

Status: Accepted

Decision:

- Designate the clean remote Windows workstation as the agentic supervision
  center. The scheduler observer is its first workload.
- Do not clone or transfer the complete `monitorovaci_platforma` repository to
  the center. Distribute only a reviewed, manifest-verified supervision bundle
  built from an explicit allowlist.
- Keep future agents that require raw measurements or application-local logic
  on the monitored workstation. Expose only their versioned, sanitized
  heartbeat and aggregate report projections through the private monitoring
  facade.
- Use Tailscale as the location-independent private transport, while retaining
  dedicated application authentication and GET-only authorization.
- The center correlates incidents and prepares reports/programmer tasks but
  cannot command local agents, access operational data, run jobs, or change
  application state.

Consequences:

- The center can move to another approved tailnet-connected workstation
  without moving the monitored application or its data.
- Packaging, manifest verification, upgrade, rollback, and center
  self-monitoring become explicit platform responsibilities.
- Every future local agent requires its own safe response inventory,
  authorization tests, shadow pilot, and registration.
- Repository access, remote shell, database access, external delivery, and
  remediation remain outside the test-mode center boundary.

## DEC-105: Kalorimetry uses forecast-gated weekly snapshots and active-only scoring

Date: 2026-08-03

Status: Accepted

Decision:

- Rebuild current kalorimetry snapshots in the Monday weekly scheduler only
  after the complete coherent pre-week forecast, observation freshness, model
  policy, and 672-slot profile gates pass.
- Treat an exact already persisted week as a verified idempotent no-op. Reject
  incomplete or conflicting decisions, profiles, model identities, or
  selection-run links without overwrite or fallback.
- After each kalorimetry import, score only through the exact period-valid
  active selection/profile snapshot using stable output model version 1, then
  process only `SPIKE` and `SUSTAINED_HIGH_USAGE` events.
- Keep kalorimetry alert delivery and new report/email delivery disabled until
  separately designed and approved.

Consequences:

- Six identifiers that currently lack eligible selection metrics remain
  explicitly unavailable and advance the scoring checkpoint without scores.
- Scheduler restarts and manual reruns cannot duplicate or silently replace a
  weekly active snapshot.
- Historical score/event reconciliation remains read-only and is not inferred
  from current-period scheduler activation.

## DEC-106: The supervision-center test runtime uses one local dotenv contract

Date: 2026-08-04

Status: Accepted

Decision:

- Package the monitoring observer as a small standalone PyCharm project with
  one operator entry point, `run_monitoring_agent.py`.
- Store all remote runtime settings, including the private HTTPS base URL and
  bearer credential, in one ACL-restricted `.env` file local to the
  supervision center. Read it directly rather than requiring persistent or
  session-level process environment variables.
- Include only `.env.example` and a `.gitignore` rule in the reviewed bundle.
  Never bundle, commit, print, transmit, or record the real `.env`.
- Keep agent state outside the code/config directory. The strict parser
  rejects missing, duplicate, unexpected, placeholder, malformed, or unsafe
  values and never renders the credential in summaries or dataclass repr.
- Use the same Python entry point for PyCharm foreground testing and any later
  separately approved Windows automatic-start registration.

Consequences:

- The earlier split between JSON configuration and a standalone credential
  file is superseded for new supervision-center bundles. Existing 0.2/0.3
  artifacts remain immutable rollback/test evidence but are not extended.
- Credential rotation updates the local `.env` atomically while the server
  retains the two-digest overlap contract. Rotation proof remains open.
- Windows ACL setup, Scheduled Task registration, restart policy, rollback,
  and background operation remain separate gates after foreground behavior
  and failure isolation pass.

## DEC-107: The remote test project may use a standalone minimal repository

Date: 2026-08-05

Status: Accepted

Decision:

- Track the supervision-center `0.4.0-test` project in the standalone public
  repository `mtravnicekarmex/monitoring_agent_0.4.0`. The reviewed baseline
  is `master` commit `88158812000c9a91b9a7da1c61045737549a3363`.
- Permit repository metadata only for this minimal agent project. The complete
  `monitorovaci_platforma` repository, unrelated application source, runtime
  data, and operational tooling remain forbidden on the center.
- Keep the real `.env`, bearer credential, agent-owned state, virtual
  environment, IDE workspace, logs, and reports outside version control. The
  tracked file set must remain bounded by the reviewed runtime manifest.
- Validate future runtime changes against the main repository's tests and the
  explicit bundle manifest before updating or running them on the center.

Consequences:

- The remote test project gains ordinary version history and a precise commit
  identity without distributing the full monitored application.
- Public repository visibility does not permit secrets, machine identifiers,
  operational payloads, or local state to be committed.
- Pulling or running a newer remote commit is an explicit reviewed upgrade,
  not an automatic deployment or approval for background registration.

## DEC-108: Every tracked remote-project change requires a new verified bundle

Date: 2026-08-05

Status: Accepted

Decision:

- Treat changes to any manifest-declared file, including non-runtime hygiene
  files such as `.gitignore`, as a new supervision bundle revision.
- Do not repair a changed `0.4.0-test` file by silently rewriting its existing
  manifest. Build `0.4.1-test` from the synchronized allowlist source and
  regenerate `manifest.json`, `manifest.sha256`, and the ZIP together.
- Require the remote repository commit to match every declared file size and
  SHA-256 before it becomes the new integrity baseline or before retained
  state audit evidence is accepted.

Consequences:

- The original `0.4.0-test` ZIP and hash remain immutable evidence.
- Remote commit `08362ec3ff504986109180bb9d1c89ea096ae19b` is safe source
  hygiene but not an approved integrity baseline because it retains the old
  manifest.
- Locally verified `0.4.1-test` is the next synchronization candidate. Its ZIP
  SHA-256 is
  `1EEBB2E946A87E5300A72126AF9A3E358DC6EA121384D2BC8BBA568E3F5DB49B`.

## DEC-109: Remote state audit output is aggregate, read-only, and explicit about gaps

Date: 2026-08-05

Status: Accepted

Decision:

- Add a `--audit-state` test-mode command that reads only the configured
  agent-owned observation and heartbeat files. It performs no network request
  and makes no state write.
- Validate observation and heartbeat schemas fail-closed, then emit only
  versioned aggregate retry, cycle, transition, timing, and latest-heartbeat
  facts.
- Never render the `.env`, state path, bearer, observer instance, PID value,
  UUID, timestamp, endpoint key, normalized payload, or raw JSONL record in
  audit output or validation errors.
- Report process ID only as a presence boolean. Because the current atomic
  heartbeat persists only its latest snapshot, explicitly report that
  heartbeat-transition and process-identity history are unavailable.

Consequences:

- The failure-isolation evidence can be reviewed without copying operational
  records or machine identifiers from the supervision center.
- Cycle health transitions derived from immutable observations are labelled
  as inferred; they do not masquerade as persisted heartbeat history.
- Proving unchanged PID and actual heartbeat state at every historical cycle
  requires a separately designed bounded history format and remains open.
- The first implementation is packaged as local `0.5.0-test`, whose ZIP
  SHA-256 is
  `739B6C57BE2BAF24CA2F4219F7FBF358859DE53D8AC5BAC07A5B6E4F420DB748`.

## DEC-110: Timing audit distinguishes long cycles from between-cycle gaps

Date: 2026-08-05

Status: Accepted

Decision:

- Treat the remote audit-v1 maximum start-to-start interval of 4,545.121
  seconds as an unresolved monitoring blind interval, not as the duration of
  monitored-target unavailability. The user confirmed that the monitored
  station, not the supervision center, was unavailable.
- Extend `--audit-state` contract version 2 with non-secret request timeout,
  retry-backoff, and configured all-timeout cycle-budget facts; aggregate
  cycle-duration statistics; and sanitized diagnostics for the longest cycle,
  longest interval, and largest late interval.
- Report only safe cycle indexes, durations, outcome classes, expected/allowed
  bounds, and excess durations. Continue to exclude timestamps, endpoint keys,
  identifiers, paths, and raw state.
- Classify an interval within the previous cycle's recorded runtime as
  `long_running_previous_cycle`. Classify excess time outside the previous
  cycle, configured polling interval, jitter, and tolerance as
  `unexplained_between_cycles_or_clock_discontinuity`.

Consequences:

- The retained audit-v1 state can identify whether the blind interval arose
  inside a request cycle or between cycles without repeating the target
  outage or exporting raw operational data.
- A long-running cycle routes diagnosis toward request, DNS, TLS, socket, or
  wall-clock behavior during a request. An unexplained between-cycle gap
  routes diagnosis toward process pause/restart, scheduling, supervision-host
  availability, or wall-clock continuity.
- Neither classification proves historical process identity; the explicit
  heartbeat/PID history gaps from DEC-109 remain.
- The implementation is packaged as local `0.5.1-test`, whose ZIP SHA-256 is
  `85FFDEC8E807068DFF82AEE56422B2D0FB05C57D9C6D8F6902377519B24FBBE8`.

## DEC-111: Process lifecycle evidence is prospective and startup registration stays gated

Date: 2026-08-05

Status: Accepted

Decision:

- Supersede DEC-110's provisional causal association between the blind
  interval and monitored-target loss. Remote audit v2 proved that the
  4,545.121-second interval followed a 0.071-second healthy cycle and occurred
  outside request runtime. Local Windows System event times matched a
  supervision-station shutdown/restart.
- Introduce observation contract version 2 with a fresh random `run_id` for
  every process, an explicit cycle ID, and a per-run cycle sequence. Use a new
  empty state directory; never mix observation contracts in one JSONL file.
- Add append-only lifecycle contract version 1 with process-start and
  controlled process-stop records. Persist run ID and PID locally, but expose
  only aggregate clean/unclean restart, abandoned-run, lifecycle consistency,
  and incomplete-cycle facts through audit contract version 3.
- Keep the atomic latest heartbeat. Add run identity to it, but retain
  `heartbeat_transition_history_not_persisted` as an explicit gap.
- Include an idempotent PowerShell Scheduled Task registration helper using
  the exact project interpreter and working directory, `SYSTEM`, `AtStartup`,
  `StartWhenAvailable`, one-minute failure restart, and `IgnoreNew`. Require
  `SupportsShouldProcess`/`-WhatIf`; do not register the task as part of bundle
  creation, extraction, foreground tests, or this decision.

Consequences:

- Future power-loss and restart tests can distinguish a controlled process
  stop from a new start following an abandoned run, without rendering the
  actual run ID, PID, timestamp, state path, or raw record.
- A process killed after writing only part of a cycle no longer corrupts later
  cycle grouping; the audit counts the incomplete cycle and resumes grouping
  by run/cycle identity.
- Historical v0.5 process identity cannot be reconstructed and remains an
  accepted evidence gap. New lifecycle evidence begins only in a fresh 0.6
  state directory.
- The helper itself has no bearer, URL, password, or `.env` value on its task
  command line. Actual registration and reboot verification remain separate
  privileged approval gates.
- The implementation is packaged as local `0.6.0-test`. Its 13-file ZIP
  SHA-256 is
  `41636BDD70612F0A89471CC102B5640C59AADE9DCC63E5426789F39DD77481B3`.

## DEC-112: Scheduled timing is scoped to one process run

Date: 2026-08-05

Status: Accepted

Decision:

- Treat start-to-start cadence, overlap, early-start, late-start, longest
  interval, and largest-late findings as scheduled timing only when two
  consecutive complete cycles share the same `run_id`.
- Preserve intervals across a `run_id` boundary as separate sanitized
  `cross_run_*` aggregates and a `process_run_transition` diagnostic. Do not
  compare them with the polling interval or jitter and do not expose run IDs,
  timestamps, or raw lifecycle records.
- Raise the aggregate audit contract to version 4. Keep observation contract
  2 and lifecycle contract 1 unchanged so existing 0.6 state remains
  compatible and retains continuity evidence.

Consequences:

- The remote v3 result whose two process runs began 46.83 seconds apart no
  longer creates a false early scheduled start. The duration remains visible
  as cross-run evidence, while lifecycle aggregates separately identify clean
  or unclean process transitions.
- Upgrading from `0.6.0-test` to `0.6.1-test` must reuse the current 0.6 state;
  a fresh state is required only for migration from pre-0.6 contracts.
- The reproducible 13-file `0.6.1-test` ZIP SHA-256 is
  `18B3A8784D37737365FF276CC4BE9D21E4A4CB844A31642D03642E36392D1EE0`;
  its manifest SHA-256 is
  `E1F06F2363DEC0732F8BC7C27A9669DB119788EB590BB1B364392255CF274C38`.
  Scheduled Task registration and reboot proof remain separately gated.

## DEC-113: Agent state has one OS-enforced polling writer

Date: 2026-08-05

Status: Accepted

Decision:

- Acquire a non-blocking operating-system file lock scoped to the configured
  state directory before writing process lifecycle, heartbeat, observations,
  or making an HTTP request. Hold it for the entire polling process.
- Reject a second `--once` or continuous writer with a sanitized startup error
  and no lifecycle, heartbeat, observation, or network activity. Keep
  `--check-config` and `--audit-state` read-only and outside the writer lock.
- Use a one-byte lock file with an OS-held lock rather than PID/stale-file
  ownership. The file may persist, but normal exit, forced termination, or OS
  process cleanup releases the actual lock.
- Raise the audit contract to version 5. Report process-run reentry and
  lifecycle concurrent starts separately from an unclean restart. Do not
  expose run IDs, PIDs, timestamps, lock paths, or raw lifecycle records.

Consequences:

- The remote 0.6.1 history with three distinct runs and three transitions is
  retained as one run reentry and one concurrent start. Its historical
  single-writer validity remains false; this does not imply a new 0.6.2 lock
  failure.
- Every pre-lock 0.6.0/0.6.1 writer must be stopped before starting 0.6.2,
  because an older process does not participate in the new lock.
- Observation contract 2 and lifecycle contract 1 remain compatible; the
  existing state is reused.
- The reproducible 13-file `0.6.2-test` ZIP SHA-256 is
  `C14A694F650BED6948450BEFA3704BF62B29359537ADE51B67B25DC9A8DC8C5D`;
  its manifest SHA-256 is
  `24CD22C4F41ED9A29FB74886EBF73ED8A1539917D34A96628CDE3BAEC99CB1D4`.
  Scheduled Task registration and reboot proof remain separately gated.

## DEC-114: Endpoint-set evolution preserves versioned observation history

Date: 2026-08-05

Status: Accepted

Decision:

- Extend the private GET-only monitoring facade and remote client with the
  approved System Runtime projection. Retain only aggregate status/source
  time, boot status/time, startup-task identity/status/last-run/result, and
  listener identity/status/expected/present/port. Validate but discard free
  text, labels, local addresses, process IDs, and startup-task next-run data.
- Define ordered endpoint set 1 as the legacy `live`, `ready`, and
  `system_scheduler` cycle. Define set 2 as those three plus
  `system_runtime`. Runtime configuration must exactly match current set 2.
- Raise the observation contract to 3 and persist `endpoint_set_version=2` on
  every new observation. Raise the aggregate audit contract to 6 and evaluate
  each cycle against the endpoint order and timeout budget declared by its
  observation contract/set.
- Permit audit v6 to read legacy contract-2/set-1 observations and current
  contract-3/set-2 observations in the same append-only 0.6 state. This
  narrowly supersedes DEC-111's prohibition on mixed observation contracts;
  unsupported contracts, unknown endpoint sets, or endpoint-set changes
  inside one cycle remain fail-closed. Pre-0.6 state still requires a new
  directory.

Consequences:

- The 0.6 history is retained without rewriting records. Audit output exposes
  only aggregate contract/set counts and continues to suppress raw IDs,
  timestamps, paths, payloads, and process data.
- The monitored workstation must deploy the matching authenticated System
  Runtime facade before remote 0.7 polling begins. A missing route is a
  non-retryable HTTP failure, not silently omitted from the cycle.
- Detailed Scheduler Health and System Database remain approved future client
  extensions; incident rules, external delivery, and Scheduled Task
  registration remain separate gates.
- The reproducible 13-file local `0.7.0-test` ZIP SHA-256 is
  `0BA56B60FD8F5A229346D565FEA33F58F57F9239FE541F216C07E79E56D7BF20`;
  its manifest SHA-256 is
  `39C06473793C92FB281D509C3468493E9562CF9CDB74F27DBEA4D249C4676ACB`.

## DEC-115: Monitoring facade changes activate through a monitored-station restart

Date: 2026-08-05

Status: Accepted

Decision:

- Treat the monitored workstation's FastAPI/Caddy runtime as boot-created by
  the existing Windows startup process. Under the current supported operating
  workflow, a changed monitoring facade is activated by restarting the whole
  monitored workstation, not by an independent API-only restart.
- Keep the separate supervision workstation and its current `0.6.2-test`
  foreground observer running during that restart. The resulting target
  transport loss and recovery are expected observation evidence, not a reason
  to restart the observer.
- After the monitored workstation returns, verify its startup task, required
  listeners, established facade routes, and the new authenticated System
  Runtime route before changing the remote observer.
- Stop the 0.6.2 writer before starting 0.7, retain the existing 0.6 state,
  update only the exact endpoint-key configuration, and then execute
  `--check-config`, `--once`, and `--audit-state`. Do not start continuous 0.7
  polling if the new route or mixed-history audit is invalid.

Consequences:

- A source-code change alone does not mean the new route is live. Before the
  monitored workstation restart, the production runtime still serves the old
  facade even though local 0.7 source and its bundle are prepared.
- The monitored-station restart and the remote-agent upgrade are distinct
  checkpoints. Failure of the new route keeps the remote upgrade blocked and
  leaves the existing 0.6.2 observer/state as the operational test baseline.
- This decision does not authorize a restart. Automatic startup registration
  for the remote agent, a supervision-workstation restart, external delivery,
  and remaining endpoint extensions stay separately gated.

## DEC-116: The supervision-center pilot uses one audited startup task

Date: 2026-08-06

Status: Accepted

Decision:

- Accept the restart-verified Windows Scheduled Task `MonitoringAgentTest` as
  the lifecycle owner for the remote `0.7.0-test` pilot. It runs as `SYSTEM`
  with an `AtStartup` trigger, `StartWhenAvailable`, `IgnoreNew`, one-minute
  bounded failure restarts, no execution time limit, the exact project-local
  virtual-environment interpreter and working directory, and no secret or URL
  on its command line.
- Keep the Scheduled Task as the only continuous polling invocation. While it
  is running, operators and later reporting tools may use read-only
  `--check-config` and `--audit-state`, but must not launch another continuous
  process or `--once` against the same state.
- Interpret the two Windows Python processes created by one virtual-environment
  invocation as one logical runtime only when sanitized evidence confirms one
  parent-child process tree, one task instance, the `SYSTEM` owner, continuous
  mode, one open lifecycle run, and no increment in concurrent-start or
  process-run-reentry counts. Raw process count alone is not writer identity.
- Preserve the existing external agent state and its historical audit facts.
  The retained pre-lock concurrent-start and run-reentry counts remain
  historical qualifications; they do not describe the current task unless
  they increment.
- Treat a fresh postboot lifecycle record or observation as the startup proof.
  Task state `Running` alone is insufficient because the first verified cold
  start took approximately 110 seconds before the lifecycle file changed.

Consequences:

- The remote observer now resumes independently after a supervision-center
  reboot. The 2026-08-06 proof produced one active logical `SYSTEM` writer,
  continued four-endpoint cycles, healthy recovery, and zero unclean or
  abandoned runs.
- The checked-in unsigned helper remains useful as the reviewed semantic
  definition, but it was not executed under the center's `Restricted`
  PowerShell policy. Equivalent elevated registration was used without
  changing or bypassing policy.
- `single_writer_observation_history_valid=false` and
  `single_writer_history_valid=false` remain expected for the append-only
  historical state. Reporting must label them as historical evidence gaps and
  must also show current task/lifecycle facts before asserting a live writer
  conflict.
- This decision authorizes neither report delivery nor incident remediation.
  Deterministic incident rules, bounded incident/report storage,
  interpretation, delivery channels, credential rotation, and replacement of
  legacy alerts remain separate work and approval gates.

## DEC-117: The repository root uses an explicit minimal allowlist

Date: 2026-08-06

Status: Accepted

Decision:

- Keep new source, documentation, generated artifacts, shortcuts, backups, and
  runtime files in the narrowest appropriate subdirectory instead of the
  repository root whenever tooling and runtime contracts permit it.
- Enforce the approved root-file set with a regression test. Root placement
  outside that set requires a concrete external-tool or runtime-path reason,
  corresponding documentation, and an allowlist update in the same review.
- Retain `main.py`, `Caddyfile`, and `start_api_dashboard.bat` as established
  runtime-path exceptions. Retain the ignored root `.env` only as the current
  local configuration compatibility contract; additional secret backups must
  use protected storage outside the repository.
- Keep the monitoring distribution's root runner as an archive path, but store
  its source template under `monitoring_agent/bundle_root/`. Keep the legacy
  dashboard compatibility launcher under `scripts/`, local development notes
  under `agents/runbooks/`, and the Windows convenience shortcut under
  `scripts/shortcuts/`.

Consequences:

- Accidental root files fail `tests/test_repository_hygiene.py` instead of
  silently becoming a new convention.
- Existing integrations that require an approved root path remain unchanged.
  The monitoring bundle still extracts `run_monitoring_agent.py` at its own
  project root, and the production dashboard task still targets the existing
  root launcher.
- Root-level monitoring credential-rotation backups found during this cleanup
  are retained without reading their values and moved to protected external
  storage rather than into a tracked repository subdirectory.

## DEC-118: Monitoring endpoint set 3 covers both Health pages and external reachability

Date: 2026-08-06

Status: Accepted

Decision:

- Define observation contract 4 and ordered endpoint set 3 as `live`, `ready`,
  `system_scheduler`, `scheduler_detail`, `system_runtime`, `system_database`,
  `system_proxy`, `system_smartfuelpass`, and `external_web`.
- Expose the eight monitored-host observations through dedicated monitoring
  response models that remove transient, unnecessary, sensitive, and
  capability-bearing fields before network serialization. Reuse the existing
  collectors; do not create parallel metric or database collectors.
- Execute `external_web` directly from the supervision workstation against one
  configured credential-free public HTTPS root. Send no monitoring bearer,
  follow no redirect, read no body, require HTTP 200 plus HTML content type,
  and retain neither URL nor headers.
- Raise the environment contract to 2 by adding the external public-page URL.
  Raise the aggregate audit to contract 7 and bind observation contracts 2,
  3, and 4 exactly to endpoint sets 1, 2, and 3 respectively. Preserve the
  append-only state rather than rewriting the deployed 0.6/0.7 history.
- Add a bounded absolute clock-skew diagnostic to contract 4. Derive it from
  the endpoint source time and request midpoint, cap it at 86,400 seconds, and
  use null when the endpoint has no source timestamp.

Consequences:

- Detailed scheduler data cannot expose manual-run capability, descriptions,
  or labels. Runtime cannot expose process IDs or binding addresses. Database
  cannot expose server inventory. Proxy cannot expose configured host/path or
  response location. SmartFuelPass cannot expose monetary, period, session,
  location, or connector aggregates.
- With the retained three-second timeout, three attempts, and 0.5/1.0-second
  backoff, the serialized nine-endpoint worst-case timeout budget is 94.5
  seconds. A complete outage can therefore lengthen the nominal 60-second
  start-to-start cadence, but cycles remain serialized and bounded; they never
  overlap or start a second writer.
- HTTP, TLS, redirect, JSON/content-type, and schema failures are fail-closed
  and non-retryable. Only connection failures and timeouts use bounded retry.
- The monitored workstation still runs the four-endpoint 0.7 facade and the
  supervision center still runs `0.7.0-test` until a separately approved main
  workstation restart, remote configuration migration, and 0.8 runtime proof
  are completed. Roadmap item 1 remains unchecked until that proof passes.
- The deterministic local `0.8.0-test` bundle contains 13 declared runtime
  files and 15 ZIP entries. Its ZIP SHA-256 is
  `29BEE64FEE267F1E74BE1AA89CA621E2930262E16C0C662580DA5D2B7EBF8EF0`;
  manifest SHA-256 is
  `282DFDDA162B4D4CB2C3CE656066D47E2B03504F1434277659E20CBCBB173ADF`.
  Neither identity is deployment evidence by itself.

## DEC-119: SmartFuelPass portal import stays paused until an Excel replacement is reviewed

Date: 2026-08-06

Status: Accepted

Decision:

- Keep the current SmartFuelPass interactive portal-import workflow unchanged
  and paused while the monitoring agent remains unfinished. Do not retry the
  Cloudflare flow or alter its page, task, parser, state, or database behavior
  during the monitoring-agent workstream.
- After the monitoring-agent work reaches a separate reviewed handoff, replace
  the page `Přihlášení SmartFuelPass` with `Import`. The future page will accept
  an administrator-selected Excel file, parse its supported contract, and
  persist the resulting records through the authenticated FastAPI/database
  boundary.
- Define the workbook schema, validation and rejection behavior, idempotent row
  identity, preview/confirmation flow, aggregate result evidence, and
  reconciliation/rollback boundary before implementing the replacement.
- Preserve the database-backed weekly report and the existing data while the
  import path is paused.
- Monitoring must retain the current SmartFuelPass Health payload as truthful
  evidence. The known planned error is an incident-rule qualification, not a
  reason to alter the collector or serialize a false `ok` status.

Consequences:

- No SmartFuelPass source, page, Windows task, production data, or runtime
  configuration changes are part of the current monitoring-agent work.
- Roadmap item 1 may pass with a transport/schema-healthy nine-observation
  cycle even when the SmartFuelPass application payload remains `error`;
  observer self-health and target application health stay separate.
- Deterministic incident rules in roadmap item 2 must represent this planned
  condition explicitly so it does not become an unexpected incident while
  still preserving the underlying observation.

## DEC-120: Monitoring 0.8 uses a strict two-phase rolling upgrade

Date: 2026-08-06

Status: Accepted

Decision:

- Do not restore transient System Runtime details, labels, local addresses,
  next-run time, or process IDs to the network facade merely to satisfy the
  deployed 0.7 exact-schema client. Preserve the new server-side safe
  projection as the target contract.
- Supersede the undeployed 0.8.0 bundle with `0.8.1-test`. The new code accepts
  both exact environment contracts: env v1 means the original four ordered
  keys and observation contract 3/set 2; env v2 means the exact nine ordered
  keys and observation contract 4/set 3. No hybrid key set is accepted.
- Upgrade in two phases against the same retained state. First install 0.8.1
  with the existing env-v1 file unchanged and require a healthy four-endpoint
  bridge cycle. Then add only the reviewed env-v2 external URL/key changes and
  require a healthy nine-endpoint cycle.
- Keep global append-only audit findings unchanged. Audit v7 additionally
  reports retry/attempt evidence for the heartbeat's current run, so a new
  runtime can prove valid behavior without relabeling historical schema
  transition records.

Consequences:

- The 68 schema errors already written by 0.7 remain historical evidence; they
  are not deleted, rewritten, or reclassified. Global retry history may remain
  false because final schema errors can follow earlier retryable attempts.
- Both upgrade phases require `--check-config`, one writer-exclusive `--once`,
  and `--audit-state` while the Scheduled Task is stopped. The task must not be
  returned to continuous operation until the nine-endpoint phase passes.
- This decision does not authorize a particular stop command. In particular,
  `Stop-ScheduledTask` must not be assumed to produce the observer's controlled
  lifecycle stop event; the initial 0.7 stop remains a separately reviewed
  migration gate.
- The `0.8.1-test` ZIP SHA-256 is
  `D17A88A10814D4CC645AD731B5C2B56B3B662E0662547ED9FCEA3443EF876884`;
  manifest SHA-256 is
  `18A3E477E724EEA61F3EFDCBE303BEBE4DC298A4D646D37FE643D6CD9C49CBB1`.
  These identities are local build evidence, not remote deployment proof.

## DEC-121: The test-stage 0.7 to 0.8.1 cutover may use one planned hard stop

Date: 2026-08-07

Status: Accepted

Decision:

- The user explicitly accepts an observation discontinuity during this test
  migration. If the 0.7 process has no attached console for a clean Ctrl+C,
  it may be terminated after its exact process tree is identified.
- Preserve the append-only state. A resulting abandoned/unclean 0.7 run is
  qualified as expected migration evidence, not deleted or rewritten and not
  treated as proof of a spontaneous observer failure.
- Manual `.env` transfer is allowed without displaying its contents. The first
  0.8.1 proof must use the copied env-v1 file unchanged; env v2/nine endpoints
  remains a second phase after the bridge passes.
- Do not infer a running Scheduled Task where none is listed, do not create a
  replacement task before the writer-exclusive bridge/final proofs pass, and
  never start a second writer while an identified 0.7 process remains alive.

Consequences:

- This decision supersedes only DEC-120's still-open authorization gate for
  the initial 0.7 stop. The strict two-phase configuration, preserved safe API
  schema, retained state, and audit-v7 proof requirements remain unchanged.
- Process termination remains limited to the exact monitoring-agent process
  tree on the supervision center. It does not authorize stopping application
  services, the monitored workstation, or unrelated Python processes.

## DEC-122: Plynomery monthly billing readings are append-only and time-bound

Date: 2026-08-07

Status: Accepted

Decision:

- Store manual plynomery billing readings as append-only rows in
  `monitoring.plynomery_fakturacni_odecty`; do not overwrite a prior row for
  the same `identifikace` and billing month.
- Treat the latest saved row per `(identifikace, period_start, period_end)` as
  the current effective reading for page prefill and report selection, while
  preserving older rows as operational history.
- Use each billing meter's actual previous/current `reading_at` interval when
  loading submeter snapshots for monthly comparison. Do not use calendar-month
  boundaries for submeter consumption when manual reading timestamps are
  available.
- Reject report creation when a current or previous billing reading is
  missing, the current reading time is not after the previous reading time, or
  the current cumulative state is lower than the previous state.

Consequences:

- The old unique DB constraint `uq_plynomery_fakturacni_odecty_period` must be
  removed only with the new append-only code loaded. Dropping it while old
  `ON CONFLICT ON CONSTRAINT` code is still running would break saving.
- Existing single overwritten rows remain valid as the initial effective
  history; future corrections are new rows.
- The active dashboard/Streamlit process may need a whole-stack restart to
  load the new service module and run the migration.

## DEC-123: Plynomery billing PDF remains a manual dashboard workflow

Date: 2026-08-10

Status: Accepted

Decision:

- Treat the `Plynomery / Fakturacni odecty` PDF as complete and accepted in
  its current manual form.
- Operators create and download the report from the admin dashboard after
  entering or checking billing readings. Do not add this PDF to the scheduler,
  scheduler manual-run registry, automatic email delivery, or recipient
  configuration.
- Keep the report actual/billing-only. It uses manual billing readings and
  submeter snapshots from the applicable reading interval; it is not a
  prediction-bearing gas consumption report.

Consequences:

- No cron entry, scheduled job, report email, automatic delivery path, or
  startup/runtime change is required for this completed feature.
- Future automation of this report would be a separate product decision and
  must receive explicit approval before scheduler or delivery code changes.
- The completed manual billing PDF is the intentional later report addition
  anticipated by DEC-069, but because it is actual/billing-only and manual, it
  does not trigger prediction conversion or scheduler registration.
- DEC-122 remains in force for append-only reading storage and time-bound
  report input validation.

## DEC-124: SmartFuelPass database filling uses manual Excel import

Date: 2026-08-10

Status: Accepted

Decision:

- Replace the active SmartFuelPass dashboard workflow with a manual
  administrator-selected `ChargingSessions` `.xlsx` import. The page formerly
  named `Přihlášení SmartFuelPass` is now `Import`.
- Preview is mandatory before import. The preview parses all workbook rows,
  compares supported `id_relace` values against
  `monitoring.smartfuelpass_relace`, and marks rows as new, already existing,
  existing with differences, or ignored.
- Import writes only new completed rows. Existing rows identified by
  `id_relace` are never updated, upserted, or re-imported from the Excel file,
  even if parsed values differ from the database.
- The parser maps `Nákup` to `id_relace`, accepts only `Stav = Dokončeno`,
  maps `Energie` to `kwh`, `Suma` to `suma`, `Čas spuštění`/`Čas ukončení` to
  the existing interval time semantics, normalizes `Název EV lokace` to the
  existing short location format, stores connector/tariff when present, and
  sets `battery_status=NULL` because the supported export does not carry that
  value.
- Browser-initiated writes must go through authenticated admin FastAPI
  endpoints; the Streamlit page must not write directly to PostgreSQL.

Consequences:

- This supersedes the active-work portion of DEC-119. The Cloudflare/browser
  portal path stays paused/retired and must not be retried or bypassed.
- The existing database-backed weekly SmartFuelPass report remains scheduled
  and continues to read only `monitoring.smartfuelpass_relace`.
- The old interactive helper/task code may remain as legacy compatibility or
  diagnostic code, but it is not the active dashboard import workflow.
- `daily_job` remains free of SmartFuelPass portal synchronization and the new
  Excel import is intentionally not scheduler-driven.

Acceptance note (2026-08-10):

- User confirmed the `Nabijecky / Import` page works as intended. `SFP-001` is
  complete and no remaining page-completion gate is tracked for this workflow.

## DEC-125: Plynomery billing PDF includes actual kalorimetry allocations

Date: 2026-08-10

Status: Accepted

Decision:

- Extend the manual `Plynomery / Fakturacni odecty` PDF with actual
  kalorimetry-based allocation tables for selected gas meters.
- Keep the report manual, actual/billing-only, and outside scheduler
  automation, scheduler manual runs, automatic email delivery, and recipient
  configuration.
- Calculate calorimetry allocation from actual cumulative
  `monitoring.Mereni_kalorimetry_vse.spotreba_energie` snapshots at the same
  previous/current billing-reading timestamps used for the gas comparison.
  Use only valid non-synthetic kalorimetry rows and fail visible allocation
  values to unavailable when source gas consumption, a calorimeter state, or a
  positive complete energy total is unavailable.
- Keep allocation mapping explicit in `moduly/mereni/plynomery/branches.py`.
  `INNOGY_A` is allocated by `Amt1`, `Amt2`, and `Amt3`; `G_P1` is allocated
  by `Gmt1` through `Gmt5`; `G_P3` is allocated by `Gmt6` through `Gmt8`.
  `Bmt1` through `Bmt3` are not included in gas allocation because their
  source metadata is the B-building electric boiler, not a gas meter.

Consequences:

- The new tables are an explanatory allocation detail for selected gas meters;
  they do not change the branch billing consumption, direct-submeter total, or
  scheduler/report-delivery contract.
- This remains outside the plynomery prediction-series contract. Do not read
  kalorimetry prediction profiles or selected-model snapshots for this PDF.
- A zero or incomplete calorimetry energy total must be shown as an unavailable
  allocation state rather than hidden or replaced by equal shares, stale data,
  predictions, or a fallback constant.

## DEC-126: Vodomery sustained high usage is a prediction-relative event

Date: 2026-08-11

Status: Accepted

Decision:

- Add vodomery event type `SUSTAINED_HIGH_USAGE` for longer elevated
  consumption relative to the active prediction profile.
- The default trigger is four consecutive 15-minute scores where actual
  consumption is at least 2.0 times `expected_mean`, the absolute deviation is
  at least `0.05 m3`, and actual consumption is at least `0.08 m3`. If
  `expected_mean <= 0`, the material absolute guards still apply.
- Event duration starts at the first qualifying score in the consecutive run,
  not at the later opening score after `min_consecutive` is reached.
- Vodomery alert-rule duration checks are inclusive. A rule with
  `min_duration_minutes=60` matches an event whose stored duration is exactly
  60 minutes.
- For the first operational alert rule, prefer `min_duration_minutes=0`
  because the event itself already gates approximately one hour of sustained
  high usage. Raising the alert rule duration is a separate additional delay.
- This source change does not create a production alert rule, backfill
  historical events, send historical emails, or change recipients.

Consequences:

- Short one-slot spikes remain represented by `SPIKE`; sustained consumption
  such as roughly double the prediction for about an hour can become its own
  event without relying only on high z-score runs.
- The normal event engine and the outlier-review rebuild path must share the
  same trigger helper so event history can be rebuilt deterministically after
  review changes.
- Database event-type check constraints and alert-rule allowlists must include
  `SUSTAINED_HIGH_USAGE`. Runtime ensure paths may update those constraints
  after the new code is loaded.
- Production activation requires the supported whole-workstation restart so
  the scheduler, FastAPI, and Streamlit processes import the updated source.
  A production alert rule still needs explicit operator configuration after
  the restart.

## DEC-127: Plynomery long high usage timing uses the first qualifying score

Date: 2026-08-11

Status: Accepted

Decision:

- Keep the existing plynomery event type `LONG_HIGH_USAGE`, defined by eight
  consecutive scores above the configured z-score threshold, but store the
  event start at the first qualifying score in the consecutive run rather than
  at the later score that opens the event.
- Compute opening `duration_minutes`, `max_z_score`, `avg_z_score`, and
  `total_deviation` across the complete qualifying run that caused the event
  to open.
- Plynomery alert-rule duration checks are inclusive. A rule with
  `min_duration_minutes=30` matches an event whose stored duration is exactly
  30 minutes.
- The normal plynomery event engine and the outlier-review rebuild path must
  share the same trigger, duration, and opening-stat helpers so review repair
  remains deterministic.
- This source change does not create a new production alert rule, change an
  existing rule, backfill historical events, send historical emails, alter
  recipients, or execute production database writes by itself.

Consequences:

- `LONG_HIGH_USAGE` alert timing now reflects the full observed high-usage run
  instead of being delayed by the event opening threshold.
- Existing historical event rows are not rewritten merely by deploying the
  source. Rebuilt event history after future approved outlier-review repairs
  will use the corrected timing.
- Production activation requires the supported whole-workstation restart so
  the scheduler, FastAPI, and Streamlit processes import the updated source.

## DEC-128: Monitoring incident rules are pure before persistence and delivery

Date: 2026-08-14

Status: Accepted

Decision:

- Monitoring incident-rule version 1 lives in `monitoring_agent/incidents.py`
  as a pure deterministic lifecycle layer over normalized observation facts or
  complete-cycle snapshots.
- It distinguishes four incident kinds: endpoint incident, target-wide facade
  transport outage, observer/facade self-health problem, and supervision-center
  blind spot.
- It defines confirmation thresholds, recovery thresholds, deterministic stale
  evidence checks, recurrence cooldown, target-wide suppression of matching
  per-endpoint retryable transport noise, and suppression of historical-only
  retained evidence.
- This layer must not read `.env`, perform network access, write state, create
  an outbox, send email, mutate the monitored application, run process control,
  or replace legacy alerts.

Consequences:

- Roadmap item 2 can be verified by synthetic tests without changing the
  deployed 0.8.1 continuous observer.
- Bounded incident persistence, retention, outbox state, retry/dead-letter
  handling, report rendering, delivery, and legacy-alert replacement remain
  separate later gates.
- Any bundle containing this new source must use a new reviewed version and
  hash; do not rebuild changed source under the already verified 0.8.1
  identity.

## DEC-129: Monitoring item 3 uses bounded local incident/outbox state

Date: 2026-08-14

Status: Accepted

Decision:

- Monitoring environment contract 3 requires explicit local bounds for
  retained observation records, incident states, incident transition records,
  outbox items, delivery attempts, retry backoff, and abandoned-claim timeout.
- `monitoring_agent/incident_store.py` owns one local
  `incident_state.json` snapshot containing only normalized incident states,
  sanitized transition records, report references, and delivery-intent outbox
  items.
- Outbox items use deterministic idempotency keys,
  pending/in-progress/sent/dead-letter status, due-claim state, retry backoff,
  and abandoned-claim
  recovery. The outbox is not a sender and contains no recipients,
  credentials, message body, network access, or delivery authorization.
- `ObserverStore.retain_recent_observations()` bounds future observation
  history by retaining whole recent cycles and atomically rewriting
  `observations.jsonl` after each runtime cycle.
- Corrupt incident state or corrupt observation history must fail closed and
  must not be overwritten by retention or outbox operations.

Consequences:

- Future bundles containing item-3 source must use a new reviewed version and
  hash, not the already verified 0.8.1 identity.
- Deployed 0.8.1 remains unchanged until that separately reviewed bundle is
  built, transferred, and activated.
- Report rendering, programming-agent prompts, actual email/Outlook/SMTP
  sending, recipient configuration, and legacy-alert replacement remain
  separate later roadmap gates.

## DEC-130: Monitoring reports and programming-agent prompts are pure drafts

Date: 2026-08-14

Status: Accepted

Decision:

- `monitoring_agent/reporting.py` renders reports and programming-agent
  prompts only from supplied normalized incident facts and optional bounded
  incident-store snapshots.
- Reports must keep verified facts, deterministic rule conclusions,
  historical qualifications/evidence gaps, and hypotheses in visibly separate
  sections.
- The programming-agent prompt must be bounded and explicitly marked as a
  draft only. It may request read-only diagnostic planning, but it must not
  authorize command execution, network contact, state mutation, process
  control, delivery attempts, or legacy-alert replacement.
- Rendering must not read `.env`, read runtime state files, claim outbox
  items, send messages, open network connections, mutate incident state, or
  control processes.
- Defensive redaction is required for likely secret assignments, bearer
  values, URL query/fragment content, Windows user paths, and synthetic
  private identifiers. Redaction is only a safety net; raw credentials,
  recipients, `.env` contents, endpoint bodies, and private runtime state must
  not be supplied as report inputs.

Consequences:

- Roadmap item 4 is locally complete without changing the deployed 0.8.1
  continuous observer.
- Any future delivery adapter must consume separately approved outbox state;
  a rendered report or draft prompt is not delivery authorization.
- Any bundle containing this source must use a new reviewed version and hash,
  not the already verified 0.8.1 identity.

## DEC-131: Monitoring delivery adapter remains disabled and test-only until explicit send approval

Date: 2026-08-14

Status: Accepted; superseded in part by DEC-133 for the later controlled
runtime send proof.

Decision:

- `monitoring_agent/delivery.py` defines only a source-level, disabled-by
  default, test-only delivery adapter for monitoring incident outbox items.
- Disabled delivery must not claim outbox items, mutate incident state, build
  messages, call SMTP, or contact any external system.
- Enabled delivery is restricted to `mode="test"` and requires one controlled
  test recipient. The operator path reads that recipient from
  `DELIVERY_TEST_RECIPIENT` and derives the in-memory recipient allowlist from
  the same value; no separate recipient-hash environment variable is required.
- Delivery is driven only by claimed outbox items and supplied report text
  keyed by `report_reference`; the adapter must not invent production
  recipients, scan state files for message bodies, or bypass the outbox.
- Sanitized delivery results may include outbox identity, incident key, action,
  report reference, recipient hash, attempt count, status, and coarse error
  code. They must not include raw recipient addresses, SMTP usernames,
  passwords, sender values, message bodies, credentials, or raw transport
  exception text.
- The monitoring-agent SMTP backend is `send_email_outlook()`, called by
  `OutlookEmailTransport`. It mirrors the existing local Office365 STARTTLS
  alarm-email pattern and reads `O_EMAIL` and `O_APP` from the already-loaded
  `.env` or process environment for login/default sender. `EMAIL` and `APP`
  remain accepted only as a compatibility fallback. Credentials are not
  persisted to Git or agent state by this module.
- The operator CLI may expose recipient hashing, synthetic local outbox
  preparation, dry-run, and confirmed `send-due` commands. Synthetic
  preparation must require its own explicit confirmation. A real send command
  must require an exact `report_reference`, `--confirm SEND_TEST_DELIVERY`,
  `DELIVERY_TEST_RECIPIENT`, the existing alarm credential names `O_EMAIL` and
  `O_APP`, and a sanitized report file; `.env` files must not be accepted as
  report input.
- Delivery-test recipient variables must avoid the `MONITORING_AGENT_` prefix
  because that prefix is reserved for the strict runtime configuration schema.
- The polling runtime validates only `MONITORING_AGENT_*` keys from the env
  file. Non-prefixed delivery keys such as `O_EMAIL`, `O_APP`, and
  `DELIVERY_TEST_RECIPIENT` may live in the same local `.env` without changing
  the observer runtime contract.

Consequences:

- The 2026-08-14 source preflight did not complete roadmap item 5 because no
  real controlled message had yet been approved or sent. The later controlled
  runtime proof is recorded separately in DEC-133.
- Before the later DEC-133 runtime proof, a controlled email test still
  required separate approval of the exact recipient, credential boundary,
  command, expected sanitized evidence, and rollback/stop criteria.
- Production recipients, current scheduler alerts, and deployed 0.8.1 behavior
  remain unchanged.

## DEC-132: Monitoring-agent test iterations may use direct Git pulls

Date: 2026-08-14

Status: Accepted

Decision:

- For the test-mode standalone monitoring agent, the user selected direct Git
  iteration through
  `https://github.com/mtravnicekarmex/monitoring-agent-0.8.1.git` instead of
  creating a new ZIP/version for every source change.
- The active test-checkout identity is the Git commit hash pulled on the
  supervision station. Commit
  `5cfc5916d3e83cdcc1eecd34f3f2719d62ec351c` on `master` contains the local
  item 2-5 candidate source and the `O_EMAIL`/`O_APP`/
  `DELIVERY_TEST_RECIPIENT` delivery-test path.
- Commit `86ee42b058c74675976904c1e51a2f3677c5f138` on `master` contains the
  item-6 draft/fallback interpretation source and regenerated manifest files.
- Commit `3e7b94e9045527a1254b10066a3a34493577f025` on `master` contains the
  item-7 shadow-pilot comparison source and regenerated manifest files.
- Commit `207fc1d38d066cdc642dc86bc0cc0b2b6c817cfc` on `master` contains the
  item-7 runtime shadow incident persistence source, audit contract 8, and a
  21-file Git manifest SHA-256
  `4011bb7de330b30371199123dca41aabaaddecd267293dadf990c91f57445287`.
- Commit `e23f5f893d76951995a8b6df833e60aadb96a858` on `master` contains the
  env-v2 external-web URL compatibility fix and a 21-file Git manifest
  SHA-256
  `b15c3d6288352c051a30e5693ea710b19b826d7c62bd6e803be0b79163e7d113`.
- Stop the `MonitoringAgentTest` Scheduled Task before `git pull`; do not
  change source beneath a running process. After pulling, run `--check-config`
  before starting the task again.
- The original 0.8.1 ZIP and manifest identities remain historical release
  evidence only. A future stable release may still use an explicitly reviewed
  ZIP/version/hash when the user asks for a release bundle.

Consequences:

- Direct Git pulls are acceptable for fast test iteration, but they did not by
  themselves complete the delivery gate or authorize a real `send-due` test.
  The later controlled delivery proof is recorded separately in DEC-133.
- The real `.env`, state files, credentials, and runtime data remain local to
  the supervision station and must not be committed or printed.
- Before the later DEC-133 runtime proof, a controlled email test still
  required separate approval of recipient, command, expected sanitized
  evidence, and rollback/stop criteria.

## DEC-133: Controlled monitoring test email proves item-5 delivery boundary only

Date: 2026-08-14

Status: Accepted

Decision:

- Roadmap item 5 is complete for the test-only delivery boundary after one
  explicitly approved synthetic email was sent from the supervision station.
- The supervision station first verified active Git checkout
  `5cfc5916d3e83cdcc1eecd34f3f2719d62ec351c`, then `hash-recipient` loaded
  `DELIVERY_TEST_RECIPIENT` from `.env` and printed only the recipient hash.
- `prepare-synthetic` created an isolated synthetic outbox/report outside the
  live agent state, and `dry-run` returned exactly one due item for
  `controlled-test-report:v1:synthetic-endpoint-system-database`.
- The explicitly confirmed `send-due` command returned sanitized success
  evidence: `status="sent"`, `action="opened"`, `attempt_count=1`, and
  `error_code=null`. The result exposed only the recipient hash, not the raw
  recipient, sender, credentials, report body, or SMTP exception text.
- A follow-up `dry-run` for the same `idempotency_key` returned `due_count=0`,
  proving the sent synthetic outbox item was not pending for re-send.

Consequences:

- This proves only the controlled Outlook/SMTP test path using `O_EMAIL`,
  `O_APP`, and `DELIVERY_TEST_RECIPIENT`.
- The monitoring polling loop remains unwired to automatic delivery; legacy
  scheduler alerts remain authoritative.
- No production recipient, production delivery channel, automatic outbox
  sender, scheduled delivery job, interpretation provider, remediation action,
  or alert replacement is authorized by this test.
- Any further external message requires separate explicit approval with exact
  command scope and expected sanitized evidence.

## DEC-134: Monitoring interpretation is draft/fallback only before real provider approval

Date: 2026-08-14

Status: Accepted

Decision:

- `monitoring_agent/interpretation.py` defines interpretation contract version
  1 as a pure layer over supplied `MonitoringReportSnapshot` objects.
- Interpretation may run only when an in-memory `InterpretationPolicy` is
  explicitly enabled in `mode="draft"` and the supplied deterministic snapshot
  contains at least one confirmed active incident.
- The policy records provider name, model name, timeout, prompt/output bounds,
  item-count bounds, and cost ceiling. Permission-style flags for network,
  state mutation, process control, delivery, and alert suppression must remain
  false.
- Candidate-only evidence, disabled policy, missing provider, provider
  exception, invalid output, or unsafe provider output must fall back to the
  deterministic report.
- Provider output may contain only bounded hypotheses, recommended read-only
  checks, and evidence gaps. It must be redacted and rejected if it attempts
  to authorize commands, network actions, state writes, service restarts,
  delivery attempts, remediation, or alert suppression.
- Result dictionaries may include provider/model audit metadata, timeout/cost
  bounds, prompt hash, prompt length, confirmed incident keys, status, coarse
  error code, sanitized hypotheses/checks/gaps, and the deterministic fallback
  report. They must not include provider exception text or provider
  credentials.

Consequences:

- Roadmap item 6 is complete locally without adding `.env` keys, provider
  credentials, a network client, polling-loop integration, state writes,
  delivery, process control, remediation, or alert replacement.
- Real model/provider execution remains a separate approval gate.
- Deterministic incident rules, report facts, outbox state, and legacy alerts
  remain authoritative; interpretation cannot suppress or replace them.

## DEC-135: Shadow pilot comparison is read-only and shadow-only

Date: 2026-08-14

Status: Accepted

Decision:

- `monitoring_agent/shadow_pilot.py` defines shadow-pilot comparison contract
  version 1 for roadmap item 7.
- The contract consumes supplied sanitized `monitoring_agent` and
  `legacy_alert` detection/recovery events over a reviewed
  start-inclusive/end-exclusive period.
- It deduplicates each source stream with a configured duplicate window and
  matches agent and legacy events by `incident_key` inside a configured match
  window.
- The output is explicitly `mode="shadow_only"` and reports matched
  detections, confirmation delay, matched recoveries, recovery delay,
  duplicate counts/rates, false positives, false negatives,
  agent/legacy-only recoveries, and blind spots.
- `events_from_incident_evaluation()` converts existing deterministic agent
  incident lifecycle transitions into comparable shadow events, and
  `render_shadow_pilot_comparison()` renders a bounded redacted operator
  summary.
- The module has no `.env` reads, database access, endpoint polling, delivery
  transport, interpretation-provider call, state write, process control,
  remediation, or alert-suppression capability.

Consequences:

- Item 7 had a source-preflight comparison contract at this decision point.
  DEC-139 records the later 2026-08-17 reviewed-period and synthetic mechanics
  proof that closes item 7.
- Legacy alerts remain authoritative. No legacy alert may be replaced,
  disabled, rerouted, downgraded, or suppressed from this output without
  separate approval.
- No new `.env` variable is required for this source change.

## DEC-136: Runtime shadow incident persistence is agent-owned and delivery-disabled

Date: 2026-08-17

Status: Accepted

Decision:

- `monitoring_agent/runtime_shadow.py` wires the deterministic monitoring
  incident lifecycle into the polling loop after each completed observation
  cycle.
- The runtime reads previous local incident state, evaluates the current
  normalized cycle, writes bounded `incident_state.json`, and emits only a
  sanitized aggregate `shadow_incidents` summary in `observation_cycle`
  console output.
- `--audit-state` advances to audit contract 8 and includes aggregate
  `shadow_incidents` counts, `present`, `history_valid`,
  `mode="shadow_only"`, and `delivery_enabled=false`.
- The polling loop must not claim outbox items, send email, call an
  interpretation provider, mutate the monitored application, control
  processes, remediate, or suppress/replace legacy alerts.
- No new `.env` variable is required. Env contracts 1 and 2 continue to use
  conservative built-in incident/outbox limits; env contract 3 may set
  explicit bounded-store limits.
- A corrupt `incident_state.json` fails closed as runtime/audit error and
  must not be overwritten silently.

Consequences:

- This is the runtime source needed to let item 7 collect shadow incident
  evidence during normal polling. DEC-139 records the later reviewed-period
  and synthetic mechanics proof that closes item 7.
- Legacy alerts remain authoritative until a separate decision explicitly
  changes alert ownership.
- Runtime shadow evidence may create delivery-intent outbox records, but
  those records are not delivery authorization.

## DEC-137: Env contract 2 must load the external-web URL for nine-endpoint runtime

Date: 2026-08-17

Status: Accepted

Decision:

- Environment contract 2 remains a controlled compatibility contract for the
  nine-endpoint monitoring-agent runtime without explicit v3 retention/outbox
  bounds.
- Because endpoint set 3 includes `external_web`, env contract 2 must read
  and validate `MONITORING_AGENT_EXTERNAL_WEB_URL` exactly like env contract
  3.
- `--check-config` is not sufficient if `RuntimeSettings` can be internally
  inconsistent with `HealthClient`; source must keep settings validation and
  client construction invariants aligned.

Consequences:

- The 2026-08-17 failed activation of commit
  `207fc1d38d066cdc642dc86bc0cc0b2b6c817cfc` is classified as a source
  compatibility bug, not a missing remote `.env` value.
- No new `.env` variable is required for the supervision station.
- Regression coverage now asserts env-v2 loading of
  `MONITORING_AGENT_EXTERNAL_WEB_URL`; standalone commit
  `e23f5f893d76951995a8b6df833e60aadb96a858` contains the fix and was
  remotely proved on 2026-08-17 with foreground `--once`, running
  `MonitoringAgentTest`, and audit-v8 `shadow_incidents.present=true`.

## DEC-138: Shadow pilot comparison consumes explicit sanitized files

Date: 2026-08-17

Status: Accepted

Decision:

- Roadmap item 7 comparison execution uses explicit file inputs, not direct
  production email, database, `.env`, endpoint, or mailbox access from the
  monitoring-agent runtime.
- `monitoring_agent.shadow_pilot_cli` may export comparable
  `monitoring_agent` events from the agent-owned `incident_state.json` and
  compare them with a supplied sanitized `legacy_alert` event JSON file for a
  reviewed start-inclusive/end-exclusive period.
- `scripts/export_database_availability_shadow_events.py` may prepare that
  sanitized `legacy_alert` JSON from delivered local
  `database_availability_events` rows without using the scheduler email
  pipeline or raw `reason` text.
- The CLI may write only operator-requested JSON/Markdown comparison output.
  It must not poll endpoints, read `.env`, send email, claim outbox items,
  call interpretation providers, mutate agent or application state, control
  processes, remediate, or suppress/replace legacy alerts.

Consequences:

- Legacy-alert collection remains a separate reviewed input-preparation step.
  The initial robust structured legacy source is the existing database
  availability event store; scheduler/runtime email-only evidence must be
  normalized into sanitized events before comparison.
- Standalone commit `3c6502c74d478a7518d3bbc37f7799951bbbaba4` contains the
  CLI, parser/export helpers, README instructions, and 22-file Git manifest
  SHA-256 `f10e0392b2e294956f522f62df270859fad7c153ba4dee6a7fbac2fbba760c11`.
- The supervision station pulled and verified that commit on 2026-08-17 with
  valid env-v2 configuration, healthy audit-v8 latest heartbeat, zero latest
  transport failures, and `shadow_incidents.present=true`.
- This file-based comparison contract enabled the 2026-08-17 item-7
  no-event baseline and synthetic mechanics proofs recorded in DEC-139.

## DEC-139: Monitoring roadmap item 7 closes on no-event pilot plus synthetic comparison proof

Date: 2026-08-17

Status: Accepted

Decision:

- Do not wait for or induce a real operational incident solely to complete
  monitoring roadmap item 7 while the monitored system is healthy.
- Item 7 is considered complete for the test-stage monitoring agent based on:
  a real reviewed no-event period against current alerts, and a file-only
  synthetic comparison proving matched detection/recovery, confirmation and
  recovery delay, false-positive, false-negative, duplicate, blind-spot, and
  safety-boundary behavior.
- The real no-event reviewed period was
  `2026-08-17T07:00:00+00:00 <= event <
  2026-08-17T07:35:00+00:00`; both monitoring-agent and legacy-alert streams
  were empty and all comparison counts were zero.
- The synthetic file-only comparison period was
  `2026-08-17T08:00:00+00:00 <= event <
  2026-08-17T09:00:00+00:00`; it produced one matched detection, one matched
  recovery, one agent-only detection, one legacy-only detection, no duplicate
  or blind-spot events, and 60-second agent-later confirmation/recovery
  delays.

Consequences:

- Roadmap item 7 is checked complete on 2026-08-17.
- Legacy alerts remain authoritative. No legacy alert is replaced, disabled,
  rerouted, downgraded, or suppressed by this decision.
- Production delivery, real interpretation-provider execution, remediation,
  process control, and item-8 local agents remain separate approvals/work.

## DEC-140: First local monitoring agent uses read-only local data and safe aggregates

Date: 2026-08-17

Status: Accepted

Decision:

- Roadmap item 8 starts with a local database-availability agent on the main
  workstation, not on the supervision center.
- The agent reads only the scheduler-owned
  `core/scheduler/data/database_availability.sqlite3` store in SQLite
  read-only mode.
- The agent writes only its own bounded sanitized state below the ignored
  `.local-monitoring-agent-state/` directory and uses its own writer lock.
- The authenticated monitoring facade may expose this local-agent state only
  as safe aggregates: version/mode/agent identity, timestamps and ages,
  service counts/statuses, pending/delivered/recent event counts, service
  keys, availability booleans, failed-check counts, and bounded evidence-gap
  identifiers.
- The local agent and facade projection must not expose raw `reason` text,
  service labels, SQLite paths, SQL, credentials, logs, file contents, raw
  event rows, or local filesystem topology.

Consequences:

- `local_monitoring_agents/database_availability.py` and
  `scripts/run_database_availability_local_agent.py` are the first item-8
  source/local proof.
- `/api/v1/monitoring/health/local-agents/database-availability` is an
  authenticated GET-only safe aggregate projection, not a command endpoint.
- No `.env` key, delivery, interpretation-provider execution,
  scheduler/application mutation, process control, remediation, or alert
  replacement is authorized by this local-agent proof.
- Do not add this endpoint to the supervision center polling set or change the
  remote `.env` without a separate controlled runtime-contract step.

## DEC-141: Second local monitoring agent uses scheduler metrics as sanitized aggregate input

Date: 2026-08-17

Status: Accepted

Decision:

- The second roadmap item-8 local agent is a scheduler-metrics agent on the
  main workstation.
- It reads only `core/scheduler/logs/scheduler_metrics.json` in read-only
  mode and writes only its own sanitized bounded state below
  `.local-monitoring-agent-state/`.
- Naive scheduler metrics timestamps are interpreted as Europe/Prague local
  time before age calculations.
- Raw job `last_status` strings are normalized into bounded classes
  (`success`, `error`, `skipped`, `unknown`, `other`) before persistence or
  facade projection.
- The monitoring facade may expose this local-agent state only as safe
  aggregate fields: version/mode/agent identity, state/heartbeat timestamps
  and ages, scheduler-running boolean, job counts, 24h success/failure counts,
  error/degraded job counts, job IDs, normalized job status classes, and
  failure rates.
- The DB-availability task registrar is an explicit operator-run helper only;
  adding the script does not register or start a task.

Consequences:

- The scheduler-metrics local agent and facade projection must not expose
  labels, descriptions, raw skipped reasons, logs, file paths, raw metrics
  JSON, raw event rows, `.env`, credentials, or file contents.
- A current running scheduler with historical last-error job states but zero
  24h failures is reported as `degraded`, not `error`, to avoid a false
  critical signal while still making the condition visible.
- No delivery, interpretation-provider execution, scheduler/application
  mutation, process control, remediation, or alert replacement is authorized.
- At this decision point, item 8 remained open for controlled local task
  execution and facade polling evidence. DEC-142 records the later first-task
  runtime proof; remaining item-8 work is scheduler-metrics task/facade proof
  or a reviewed shared local runner decision before item 9/orchestrator design.

## DEC-142: First local agent Scheduled Task is limited and locally owned

Date: 2026-08-17

Status: Accepted

Decision:

- `MonitoringDatabaseAvailabilityLocalAgent` is accepted as the first
  controlled local Scheduled Task proof for roadmap item 8.
- The task runs on the main workstation as the current user with limited run
  level, uses the project `.venv` Python executable, uses the project root as
  working directory, ignores overlapping starts, starts when available, repeats
  every five minutes, and has a two-minute execution limit.
- The task runs only the read-only DB-availability local agent runner and
  writes only sanitized agent-owned state below `.local-monitoring-agent-state/`.

Consequences:

- The task is not a supervision-center command channel and does not give the
  center authority to start, stop, reconfigure, or remediate local agents.
- The first automatic trigger proof on 2026-08-17 completed with
  `LastTaskResult=0` and a fresh facade aggregate of `status="ok"`.
- The supervision-center polling set and remote `.env` remain unchanged.
- Item 8 remains open for scheduler-metrics task/facade proof or a reviewed
  shared local runner decision before item 9/orchestrator design.

## DEC-143: Item 8 local agents use one shared local runner

Date: 2026-08-17

Status: Accepted

Decision:

- Roadmap item 8 proceeds with one shared local runner for approved local
  agents instead of a separate Windows Scheduled Task per agent.
- `scripts/run_local_monitoring_agents.py` runs approved local agents in a
  deterministic order. Each agent retains its own read-only source boundary,
  sanitized state file, and writer lock.
- The shared runner emits only the sanitized aggregate
  `local_monitoring_agents_cycle`.
- Agent-reported `degraded` or `error` status is monitoring evidence and does
  not by itself make the runner fail. The runner exits non-zero only for
  execution, lock, schema, or other runtime exceptions that prevent a valid
  cycle result.
- `scripts/register_local_monitoring_agents_task.ps1` is the selected
  operator-run registrar for the eventual recurring local task
  `MonitoringLocalAgents`.

Consequences:

- `MonitoringDatabaseAvailabilityLocalAgent` remains a valid first-task proof
  but is not the desired steady item-8 runtime shape once multiple local
  agents are active.
- Do not run the DB-only task and the shared task long-term together, because
  that would create duplicate DB-availability local-agent executions.
- Controlled migration must stop or replace the DB-only task, register
  `MonitoringLocalAgents`, prove one manual run, prove one automatic trigger,
  and verify facade freshness for both DB availability and scheduler metrics.
- This decision does not authorize remote `.env` changes, supervision-center
  polling-set changes, delivery, interpretation-provider execution,
  scheduler/application mutation, process control, remediation, or legacy
  alert replacement.

## DEC-144: Shared local Scheduled Task supersedes the DB-only local task

Date: 2026-08-17

Status: Accepted

Decision:

- `MonitoringLocalAgents` is the active local monitoring Scheduled Task for
  roadmap item 8.
- `MonitoringDatabaseAvailabilityLocalAgent` is retired after serving as the
  first DB-availability task proof.
- The active shared task runs `scripts/run_local_monitoring_agents.py` through
  the project `.venv` Python executable from the project-root working
  directory, as the current user with limited run level, `IgnoreNew`,
  `StartWhenAvailable`, five-minute repetition, and a three-minute execution
  limit.
- A successful manual run and a successful first automatic trigger are
  required evidence for accepting the migration.

Consequences:

- Do not reintroduce `MonitoringDatabaseAvailabilityLocalAgent` while
  `MonitoringLocalAgents` is active, because that would duplicate the
  DB-availability local-agent cycle.
- Additional approved local agents should be added to the shared runner and
  facade contracts rather than creating a new recurring task by default.
- The accepted migration proof on 2026-08-17 had manual
  `LastTaskResult=0`, automatic `LastTaskResult=0`, `NumberOfMissedRuns=0`,
  no local-agent facade evidence gaps, DB availability `status="ok"`, and
  scheduler metrics `status="degraded"` with zero failures in the last
  24 hours.
- This decision does not authorize remote `.env` changes, supervision-center
  polling-set changes, delivery, interpretation-provider execution,
  scheduler/application mutation, process control, remediation, or legacy
  alert replacement.

## DEC-145: Monitoring orchestrator v1 is read-only supervision correlation

Date: 2026-08-17

Status: Accepted

Decision:

- `agents/plans/monitoring/MONITORING_ORCHESTRATOR_DESIGN.md` is accepted as
  the roadmap item-9 architecture baseline.
- The v1 orchestrator is a supervision-center-local dohledový/korelační
  agent. It is not a lifecycle manager, remediation controller, delivery
  system, interpretation-provider runner, or alert-layer replacement.
- The accepted evidence baseline is the verified remote external monitoring
  agent plus the two local data-bearing agents: DB availability and scheduler
  metrics.
- The accepted shared contract is intentionally minimal: stable agent
  identity, agent kind, location, source contract version, bounded status
  vocabulary, freshness/staleness fields, bounded evidence gaps, aggregate
  counts, and sanitized payload digest.
- The first implementation step must be file-only: a CLI over sanitized sample
  snapshots with tests for registry validation, contract mismatch, staleness,
  duplicate keys, and correlation rules.

Consequences:

- The orchestrator may correlate center-owned audit summaries, file-only
  sanitized snapshots, and later separately approved GET-only facade reads.
- It may not start, stop, restart, register, unregister, or reconfigure
  agents, Scheduled Tasks, or application processes.
- It may not read raw local files, logs, SQLite rows, metrics JSON, SQL,
  measurements, device data, credentials, tokens, recipients, report bodies,
  or `.env` values.
- It may not mutate application state, scheduler state, monitoring-agent
  state, local-agent state, source code, or workstation configuration.
- It may not invoke delivery transports or interpretation providers, and may
  not suppress, replace, downgrade, reroute, or acknowledge legacy alerts.
- Remote polling-set changes, live facade reads from the supervision center,
  deployment, scheduling, delivery, provider execution, remediation, and alert
  integration remain separate approvals.

## DEC-146: Monitoring-agent steady polling and compact transition history

Date: 2026-08-21

Status: Accepted

Decision:

- The remote monitoring agent's steady-state polling profile is five-minute
  serialized cycles with 0-30 seconds jitter:
  `MONITORING_AGENT_POLL_INTERVAL_SECONDS=300` and
  `MONITORING_AGENT_POLL_JITTER_SECONDS=30`.
- This uses existing `.env` variables only. No new runtime schema key is
  required.
- The deterministic incident lifecycle may still evaluate every completed
  cycle, but `incident_state.json` must not retain an unchanged `updated`
  transition record for every cycle of a long-running active incident.
- The incident store retains meaningful transition history by keeping all
  delivery-intent transitions (`opened`, `reopened`, `recovered`), all
  suppressions, the first `updated` after a prior non-`updated` transition,
  and later `updated` transitions only when bounded incident attributes such
  as reason, status, or severity change.
- Delivery-intent outbox behavior is unchanged: outbox items are still created
  only for `opened`, `reopened`, and `recovered`, and the polling loop remains
  delivery-disabled.

Consequences:

- The five-minute profile reduces normal nine-endpoint request volume while
  preserving a practical detection window for scheduler/database events that
  occur on roughly 15-minute operational intervals.
- Long-running incidents such as an active `endpoint:system_scheduler`
  degradation no longer evict useful open/recovery/suppression evidence from
  the bounded transition history with repeated identical `updated` records.
- This decision does not authorize automatic delivery, production recipients,
  interpretation-provider execution, scheduler/application mutation, process
  control, remediation, remote polling-set expansion, or legacy-alert
  replacement.

## DEC-147: Pause scheduled SOFTLINK electric-meter imports until login is rebuilt

Date: 2026-08-21

Status: Accepted

Decision:

- Pause `SOFTLINK_save_to_database_all` and
  `elektromery_softlink_monitoring_import` from the scheduled `daily_job` and
  from the manual scheduler registry because the SOFTLINK credentials/login
  path changed.
- Keep the callable import functions in source, but lazy-load the
  credential-dependent SOFTLINK modules only when
  `SOFTLINK_save_to_database_all()` is explicitly called.
- While SOFTLINK is paused, scheduled `daily_job` runs only `meteo_sync`.
- `daily_job` uses an independent-step runner: each configured independent
  step is attempted, failures are logged as continuing failures, and one
  aggregate `SchedulerContextError` is raised after all attempted steps if any
  failed.
- SOFTLINK may be re-added only after `SOFTLINK_data_z_dotazu.py` is rebuilt
  to use the robust saved-session/API-validation pattern already used by
  `SOFTLINK_data_zarizeni.py` and the changed login path is verified.

Consequences:

- A SOFTLINK login failure no longer blocks the remaining active midnight
  `daily_job` work.
- Scheduler startup no longer depends on importing SOFTLINK modules that read
  `SOFTUSE`/`SOFTPASS` at import time.
- The paused SOFTLINK steps cannot be accidentally triggered through the
  scheduler manual-run registry.
- This decision does not delete SOFTLINK source, change SOFTLINK credentials,
  print cookie/session data, write electric-meter rows, or authorize any
  unrelated scheduler/job behavior change.

## DEC-148: Enable automatic monitoring-agent delivery only for controlled test recipient

Date: 2026-08-21

Status: Accepted

Decision:

- The remote `0.8.1-test` monitoring agent may run automatic runtime delivery
  only in controlled test mode.
- The explicit activation gate is the local non-`MONITORING_AGENT_` key
  `DELIVERY_AUTOMATION_ENABLED=true`; missing or `false` disables automatic
  runtime delivery.
- Runtime delivery may use only `DELIVERY_TEST_RECIPIENT`, the existing
  Outlook test credentials (`O_EMAIL`/`O_APP`, with `EMAIL`/`APP` only as
  compatibility fallback), and sanitized deterministic report text generated
  from agent-owned `incident_state.json`.
- At most one due pending outbox item may be attempted after each completed
  observation cycle.
- Historical pending outbox intents should be reviewed or operator-skipped
  before enabling the gate so activation does not send stale alerts.

Consequences:

- DEC-146's delivery-disabled statement is superseded only for this controlled
  test-recipient runtime gate.
- Production recipients, recipient lists, provider-generated interpretation,
  monitored-target mutation, remediation, process control, alert suppression,
  and legacy-alert replacement remain unauthorized.
- While `MonitoringAgentTest` is running, operators should not manually claim
  or send outbox items against the same state. Use `--audit-state` and
  sanitized outbox review commands for observation.
- The expected activation baseline on 2026-08-21 is
  `delivery_enabled=true`, `outbox_pending_count=0`,
  `outbox_sent_count=1`, and `outbox_dead_letter_count=14`; any later
  increase in sent count should be correlated with the incident/action that
  produced it.
