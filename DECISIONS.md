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
