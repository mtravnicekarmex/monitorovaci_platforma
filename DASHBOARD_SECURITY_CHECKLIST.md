# Dashboard Security Checklist

Date: 2026-06-11

Purpose: tracked remediation plan for securing the public Streamlit and FastAPI dashboard at `https://monitoring.armexholding.cz`.

Status values:

- `[ ]` Not started
- `[-]` In progress
- `[x]` Completed and verified
- `[!]` Blocked or requires a decision

## P0 - Immediate

### 1. Replace the hard-coded API token secret

- [x] Generate a long cryptographically random production `API_TOKEN_SECRET`.
- [x] Store the secret outside Git, for example in the local `.env` or a protected service environment.
- [x] Remove the fixed secret from:
  - `start_api_dashboard.bat`
  - `start_api_dashboard - kopie.bat`
  - `scripts/start_all_services.ps1`
  - `run.txt`
- [x] Make startup fail clearly when the production secret is missing.
- [x] Restart FastAPI so tokens signed with the old secret stop working.
- [x] Verify that a newly issued token works and an old token returns HTTP 401.
- [x] Add regression tests preventing a fixed development secret from returning to tracked launchers.

Completed on 2026-06-12:

- FastAPI restarted and loaded the new 384-bit random secret from the ignored local `.env`.
- FastAPI live and ready endpoints returned HTTP 200.
- Streamlit health returned HTTP 200.
- A token signed by the running application with the current secret returned HTTP 200 from `/api/v1/auth/me`.
- A token signed with the previous known development secret returned HTTP 401 with a signature mismatch.
- The public-hostname Caddy route returned the Streamlit dashboard and routed an unauthenticated protected API request to FastAPI as HTTP 401 JSON.

Completion criteria:

- No tracked runtime launcher contains an API signing secret.
- The running API uses a secret generated outside the repository.
- Previously issued tokens are invalid.

### 2. Restrict public access until login protection is complete

- [x] Decide on the temporary access restriction:
  - Tailscale only
  - Corporate source IP allowlist
  - Additional authentication at the reverse proxy
- [x] Apply the selected restriction in Caddy or the network perimeter.
- [x] Verify authorized access and rejection of unauthorized public traffic.
- [x] Document rollback and emergency access.

Completed on 2026-06-12:

- Selected temporary additional authentication at the Caddy reverse proxy.
- Caddy requires the shared gate for the Streamlit surface and
  `/api/v1/auth/login`.
- Other `/api/*` routes are excluded from the Basic Auth gate because they use
  FastAPI Bearer tokens in the same `Authorization` header.
- Gate credentials are generated locally and stored outside Git under
  `C:\ProgramData\monitorovaci_platforma` with ACL access limited to the
  operating account, Administrators, and SYSTEM.
- Requests without gate credentials and requests with invalid credentials
  returned HTTP 401.
- A request with valid gate credentials reached Streamlit with HTTP 200.
- A gated login request reached FastAPI and returned schema validation JSON,
  while an unauthenticated protected Bearer API request continued to return
  FastAPI HTTP 401 JSON.
- Rollback and emergency access are documented in
  `PUBLIC_HTTPS_DEPLOYMENT.md`; Tailscale remains the backup access path.

Superseded later on 2026-06-12:

- The temporary Caddy gate was removed after P1.3 application login throttling
  was implemented and verified.
- The public dashboard again opens the normal Streamlit login page without a
  separate browser Basic Auth prompt.

Completion criteria:

- Automated login attacks cannot reach the application from the unrestricted internet.

## P1 - Authentication

### 3. Add login throttling and abuse protection

- [x] Rate-limit `/api/v1/auth/login` by both account identifier and client IP.
- [x] Use increasing delays or temporary lockouts after repeated failures.
- [x] Avoid permanent denial of service through attacker-triggered account lockout.
- [x] Return the same generic response for unknown, inactive, and incorrect-password accounts.
- [x] Reduce timing differences between unknown-user and wrong-password attempts.
- [x] Define trusted proxy handling before accepting `X-Forwarded-For`.
- [x] Add tests for limits, reset windows, proxy headers, and successful login after expiry.

Completed on 2026-06-12:

- Five failed attempts for one normalized account start a 30-second lockout;
  repeated failures increase the lockout up to 15 minutes.
- Twenty failures from one trusted client IP within 15 minutes trigger a
  15-minute IP lockout across account identifiers.
- Lockouts are temporary and failure history expires after 15 minutes.
- Unknown, inactive, and incorrect-password accounts return one generic
  authentication error. Unknown accounts verify against a dummy PBKDF2 hash to
  reduce password-check timing differences.
- Uvicorn accepts forwarded client information only from loopback Caddy, and
  the application uses `request.client.host` instead of raw forwarded headers.
- The temporary Caddy Basic Auth gate was removed after targeted tests passed.
- Throttle state is in memory and resets on FastAPI restart; the current
  production API uses one worker.
- Live verification returned HTTP 401 for attempts 1-4 and HTTP 429 with
  `Retry-After: 30` for attempt 5 against a disposable test identifier.

Completion criteria:

- Repeated attempts are throttled predictably.
- Account enumeration is not practical through response content or timing.

### 4. Add authentication audit logging and alerts

- [x] Log successful and failed logins without logging passwords or bearer tokens.
- [x] Record timestamp, normalized username identifier, source IP, result, and reason category.
- [x] Log token revocation, password changes, role changes, and account activation changes.
- [x] Protect logs from dashboard users and avoid returning sensitive log content through errors.
- [x] Define alert thresholds for brute force, password spraying, and repeated admin-account failures.

Completed on 2026-06-12:

- FastAPI writes structured JSONL authentication audit events to
  `C:\ProgramData\monitorovaci_platforma\logs\auth_audit.jsonl` by default.
- The file is outside the dashboard/API response surface, inherits the
  restricted ProgramData ACL, rotates daily, and retains 90 backups.
- Login records include UTC timestamp, normalized account identifier, trusted
  source IP, success/failure result, internal reason category, and bounded
  failure counters. Passwords, bearer tokens, and cookie values are not passed
  to the audit service.
- Password changes, logout and other token revocations, administrator password
  resets, role changes, activation changes, account creation, and account
  deletion are audited. The supported local user-management CLI writes the
  same security events.
- Security warning events are emitted when an account enters its five-attempt
  brute-force lockout, an IP reaches the 20-attempt password-spray lockout, or
  an administrator account receives three failed attempts within 15 minutes.
- Audit write failures are logged internally and do not expose log content or
  alter authentication responses.

Completion criteria:

- Authentication attacks can be detected and investigated from retained logs.

### 5. Strengthen password policy

- [x] Apply one shared password validator to user creation, admin reset, CLI creation, and self-service changes.
- [x] Require at least 15 characters while password-only authentication is used.
- [x] Allow long passphrases, Unicode, spaces, password managers, and paste.
- [x] Reject commonly used and compromised passwords using a local or privacy-preserving blocklist.
- [x] Do not require arbitrary periodic password changes.
- [x] Increase PBKDF2-HMAC-SHA256 from 390,000 to at least 600,000 iterations, or migrate to Argon2id.
- [x] Rehash older hashes after a successful login.
- [x] Add tests for every password entry path and hash migration.

Completed on 2026-06-12:

- `moduly/apps/dashboard/security.py` owns one password validator used by the
  database write boundary, administrator create/reset flows, self-service
  password changes, Streamlit forms, and the local user-management CLI.
- New passwords require 15 to 1024 characters. Spaces, Unicode, long
  passphrases, browser paste, and password-manager generated values remain
  supported. No uppercase/lowercase/digit/symbol composition rule or periodic
  password expiry was introduced.
- Passwords are normalized to Unicode NFC before hashing. Blocklist matching is
  case-insensitive and whitespace-normalized so trivial padding does not bypass
  the tracked local common/compromised password list or username-derived
  values.
- New hashes use PBKDF2-HMAC-SHA256 with 600,000 iterations. Existing valid
  390,000-iteration hashes continue to authenticate and are rehashed
  automatically after the next successful login without changing
  `token_version` or requiring a bulk password reset.
- The bootstrap CLI prompts for a password without exposing it in process
  arguments when `--password` is omitted; the argument remains available for
  existing controlled automation.
- On the production workstation, a 600,000-iteration test hash took
  approximately 0.126 seconds and verification approximately 0.132 seconds.
- Targeted password-policy, hash-migration, authentication, audit, Caddy,
  navigation, and responsive-layout tests passed: 84 tests.

Completion criteria:

- Weak passwords cannot be created through any supported path.
- Existing users migrate without a forced bulk password reset unless explicitly required.

### 6. Add MFA or corporate SSO

Status: Skipped by user decision on 2026-06-18. This item is an accepted
residual risk and is not a blocker for the remaining P2 checklist work.

- [!] Decide between corporate OIDC/SAML SSO and application-managed MFA.
- [!] Require MFA at minimum for administrators.
- [!] Define enrollment, recovery, revocation, and lost-device procedures.
- [!] Require recent reauthentication for sensitive actions.
- [!] Add tests for authentication and recovery flows.

Reason for deferral:

- The project will continue with the remaining P1 security items before
  selecting and operating a new identity or second-factor system.
- No corporate identity-provider integration details have been confirmed.
- Application-managed MFA would introduce enrollment, recovery, revocation,
  and support responsibilities that should not be implemented without an
  explicit operating decision.

Accepted residual risk:

- Compromise of a dashboard administrator password can still be sufficient to
  access that account.
- Existing password hardening, login throttling, audit logging, temporary
  lockouts, and token revocation reduce but do not remove this risk.

Revisit:

- When corporate OIDC/SAML capabilities and ownership are known.
- Before materially expanding administrator access or dashboard exposure.
- When the accepted residual password-only administrator risk changes.

Completion criteria:

- Compromise of a password alone is insufficient to access an administrator account.

## P1 - Session And Token Security

### 7. Remove the full bearer token from map iframe JavaScript

- [x] Replace the token-bearing iframe flow with a design that does not expose the main API token to map JavaScript.
- [x] Consider an authorized same-origin image endpoint using the browser session cookie.
- [x] If a delegated token is necessary, make it short-lived and limited to a specific image and operation.
- [x] Ensure the map cannot use credentials for admin or unrelated API calls.
- [x] Add tests proving that generated map HTML contains no main bearer token.

Completed on 2026-06-12:

- `build_leaflet_map_html` no longer accepts or serializes an access token.
- Map photo requests use same-origin `/api/v1/map/images` with browser-managed
  credentials. JavaScript cannot read the HttpOnly dashboard session cookie.
- The image endpoint has a dedicated cookie dependency that validates the
  existing token signature, expiry, user activity, and `token_version`.
- OpenAPI describes the image operation with an `APIKeyCookie` security scheme
  using `monitoring_dashboard_session`.
- The image endpoint continues to enforce map-layer and device authorization.
- A bearer header without the dashboard session cookie is rejected by the
  image endpoint. Other protected API routes continue to require bearer
  authentication and do not accept the cookie.
- No delegated token was needed. The cookie credential is accepted only at
  the map image operation.
- The cross-origin `DASHBOARD_BROWSER_API_BASE_URL` image override was removed;
  deployments must expose `/api/v1/map/images` under the dashboard origin.
- Image responses use private caching and vary on the cookie.
- Generated map HTML tests reject the main token, bearer text,
  `Authorization` headers, and token-bearing iframe arguments.
- Targeted map, authentication, and device authorization tests passed:
  66 tests.
- Live verification after Uvicorn reload returned HTTP 401 for both a
  no-cookie request and a bearer-only request to the image endpoint, while
  the normal map catalog continued to use bearer authentication.

Completion criteria:

- Inspecting or compromising map iframe JavaScript does not disclose a reusable dashboard API token.

### 8. Remove third-party executable JavaScript from authenticated pages

- [x] Host the required Leaflet JavaScript and CSS locally.
- [x] Pin reviewed versions in the repository or controlled static assets.
- [x] Remove runtime loading from `unpkg.com`.
- [x] Review all other authenticated pages for externally loaded scripts.
- [x] Add a regression test preventing unapproved external script origins.

Completed on 2026-06-12:

- Leaflet `1.9.4` is vendored under
  `moduly/apps/dashboard/assets/leaflet/1.9.4`.
- The vendored `leaflet.js` and `leaflet.css` match the official SHA-256 SRI
  values published by Leaflet. The BSD 2-Clause license and source metadata
  are stored beside the assets.
- `map_shared.py` reads the reviewed assets through an in-process cache and
  embeds them into the map iframe. The browser no longer loads Leaflet code or
  styles from `unpkg.com` or another runtime CDN.
- Leaflet CSS image dependencies and default marker images are embedded as
  local data URIs, so the iframe does not depend on a public asset route.
- Active dashboard Python and HTML sources were reviewed for external
  executable script tags. The remaining external map tile and weather
  endpoints provide data or images, not executable JavaScript.
- Regression tests verify the Leaflet hashes, reject external HTTP(S) script
  tags in active dashboard sources, and confirm generated map HTML contains no
  external script source or unbundled Leaflet image reference.
- The combined P1.7/P1.8 map, authentication, authorization, and security
  suite passed all 73 tests. Python compilation and live FastAPI/Streamlit
  health checks also passed.

Completion criteria:

- Authenticated pages execute only application-controlled JavaScript.

### 9. Harden browser session handling

- [x] Rename the session cookie with the `__Host-` prefix.
- [x] Always set `Secure`, `HttpOnly`, `SameSite=Lax` or stricter, and `Path=/`.
- [x] Do not derive security attributes from untrusted forwarded headers.
- [x] Add an inactivity timeout appropriate for operational dashboard use.
- [x] Keep an absolute timeout and consider periodic token renewal.
- [x] Rotate or invalidate sessions after password, role, account-status, and permission changes.
- [x] Consider `Clear-Site-Data` during logout where browser compatibility permits.
- [x] Add session lifecycle tests.

Completed on 2026-06-12:

- The browser cookie is now
  `__Host-monitoring_dashboard_session`. FastAPI always sets it with
  `Secure`, `HttpOnly`, `SameSite=Lax`, and `Path=/`, and never sets a
  `Domain` attribute.
- Cookie security no longer depends on `X-Forwarded-Proto` or another request
  header. The supported browser entry point remains the public HTTPS hostname.
- Tokens now contain signed issue, session-start, rolling-expiry, and
  absolute-expiry timestamps. The default rolling request-inactivity limit is
  30 minutes and the absolute limit is 480 minutes.
- Active Streamlit sessions renew at most once every five minutes through
  `POST /api/v1/auth/session/refresh`. Renewal preserves the original
  session-start timestamp and cannot extend the absolute limit.
- Tokens created before this claim format are rejected. The first dashboard
  access after deployment therefore requires one new login.
- Password, role, activation, allowed-section, allowed-page, and
  allowed-device changes increment `token_version` once and immediately revoke
  existing bearer tokens and browser sessions. Email-only changes do not
  revoke sessions.
- Logout deletes both the current `__Host-` cookie and the retired legacy
  cookie. The browser-session deletion response also clears origin cache and
  storage through `Clear-Site-Data`; cookies are deleted explicitly to avoid
  domain-wide cookie clearing behavior.
- Focused lifecycle tests passed 50 tests, the broader security/dashboard/map
  suite passed 154 tests, and the full suite passed 492 of 494 tests. The two
  remaining failures are the previously documented unrelated failures in
  `tests/test_vodomery_reports.py`.
- Live verification confirmed the new OpenAPI cookie name and refresh route,
  rejected a synthetic legacy-format token with HTTP 401, and kept FastAPI,
  Streamlit, HTTPS dashboard routing, and unauthenticated image protection
  healthy.

Completion criteria:

- Stolen sessions have bounded lifetime and privilege changes revoke active access promptly.

## P1 - Authorization

### 10. Move all privileged writes behind server-side authorization

- [x] Inventory Streamlit modules that write directly to PostgreSQL or MSSQL.
- [x] Move privileged revision writes behind authenticated FastAPI endpoints.
- [x] Enforce admin access inside the service/API operation, not only through disabled UI controls.
- [x] Review device administration, imports, reports, and file operations for the same pattern.
- [x] Add negative tests proving non-admin users cannot invoke write functions directly.

Completed on 2026-06-14:

- Revision creation and update now use authenticated admin endpoints under
  `/api/v1/admin/revize`; the Streamlit revision page no longer opens a
  PostgreSQL write session.
- Device creation and update for water, gas, electricity, heat, and pressure
  meters now use authenticated admin endpoints under
  `/api/v1/admin/devices/{meter_key}`; the shared Streamlit device-list module
  no longer opens an MSSQL write session.
- Both API services call `require_admin_access()` before payload processing or
  database-session creation. The route layer independently requires
  `get_current_admin_user`.
- Server-side revision validation still checks required fields, duplicate
  revisions, evidence-table existence, linked device IDs, and building
  consistency before committing.
- Server-side device writes accept only fields configured for the selected
  meter type and preserve existing SQLAlchemy type coercion and required-field
  validation.
- Existing user administration, password/profile changes, map-layer
  administration, scheduler controls, web-search mutation, and alerting
  mutation paths were already behind authenticated FastAPI operations.
- Dashboard report modules perform read-only database queries and generate
  browser downloads. Revision file operations only read, preview, download, or
  request an operating-system open action; no browser-triggered server-side
  file mutation was found.
- Revision Excel import modules remain batch/off-dashboard workflows and are
  not exposed as browser-invokable Streamlit mutations.
- Negative tests verify that non-admin service calls fail before a PostgreSQL
  or MSSQL session is opened, every new route declares the admin dependency,
  and active Streamlit revision/device modules no longer define direct write
  functions or commits.
- Focused P1.10 tests passed 42 tests; the broader authentication, session,
  navigation, map, startup, revision, and device suite passed 136 tests.
- The complete suite passed 525 of 527 tests. The two remaining failures are
  the previously documented unrelated failures in
  `tests/test_vodomery_reports.py`.
- Live OpenAPI exposed all four mutation operations with `HTTPBearer`
  security. Unauthenticated revision and device creation requests returned
  HTTP 401, while FastAPI live/ready and Streamlit health remained HTTP 200.

Completion criteria:

- Every privileged mutation has a server-side authorization decision at its execution boundary.

### 11. Expand authorization regression coverage

- [x] Test all API routes without authentication.
- [x] Test all admin routes with a non-admin token.
- [x] Test every device-scoped route with an allowed and disallowed identifier.
- [x] Test permission changes against already issued tokens.
- [x] Test map catalog, features, filters, and images for cross-device access.

Completed on 2026-06-15:

- Added an executable FastAPI operation inventory covering all 75 registered
  `/api/v1/*` and `/health/*` operations. The five intentionally public
  operations are explicit; all 70 protected operations are invoked through the
  ASGI application without credentials and must return HTTP 401.
- Added an explicit inventory of all 37 admin operations across scheduler,
  admin, kalorimetry, plynomery, and vodomery routes. Every operation is invoked
  with a valid signed non-admin bearer token and must return HTTP 403 before
  endpoint validation or database access.
- Added route inventories and denial tests for all vodomery, manometry,
  plynomery, and web-search section/page dependencies, plus positive dependency
  tests for assigned sections and the configurable web-search page.
- Added allowed/disallowed identifier tests for every non-admin API route that
  accepts a device identifier, with direct service tests verifying that an
  unassigned identifier is rejected before a PostgreSQL or MSSQL session opens.
- Added bearer-token and browser-cookie regression tests proving that section,
  page, device, role, and activation changes invalidate tokens issued before
  the permission change.
- Added map authorization coverage proving that the catalog hides unavailable
  device layers, feature and filter SQL parameters contain only assigned device
  identifiers, and image resolution allows an assigned identifier while
  rejecting a different device.
- The new coverage found three vodomery routes where `AuthorizationError`,
  which subclasses `ValueError`, was incorrectly converted to HTTP 422.
  Exception ordering was corrected so cross-device requests return HTTP 403.
- The focused P1.11 suite passed all 222 tests and the broader authorization,
  authentication, navigation, token, startup, admin, and map suite passed all
  304 tests.
- The complete suite passed 702 of 704 tests. The two remaining failures are
  the previously documented unrelated failures in
  `tests/test_vodomery_reports.py`.

Completion criteria:

- Authorization tests cover route, role, page, section, and device boundaries.

## P2 - HTTP And Deployment Hardening

### 12. Add security response headers

- [x] Add HSTS after confirming HTTPS is the only supported public access method.
- [x] Add `X-Content-Type-Options: nosniff`.
- [x] Add `Referrer-Policy: strict-origin-when-cross-origin`.
- [x] Add clickjacking protection using CSP `frame-ancestors` and a compatible fallback where useful.
- [x] Develop a Streamlit-compatible Content Security Policy, initially in report-only mode.
- [x] Add a restrictive `Permissions-Policy`, while preserving map geolocation where required.
- [x] Remove unnecessary server fingerprinting headers where practical.
- [x] Add Caddy configuration tests and verify live response headers.

Completed on 2026-06-15:

- Caddy now applies the same reviewed headers to Streamlit and same-origin
  FastAPI responses.
- HSTS is enforced for one year without `includeSubDomains` or preload because
  unrelated subdomains were not reviewed as part of this dashboard change.
- MIME sniffing is disabled, referrers use
  `strict-origin-when-cross-origin`, and framing is restricted to the same
  origin through `X-Frame-Options: SAMEORIGIN`.
- The report-only CSP documents a future enforcement baseline while allowing
  the current Streamlit inline scripts/styles, WebSockets, local iframe
  components, HTTPS map tiles, and data/blob images and workers.
- `Permissions-Policy` disables browsing topics, camera, microphone, payment,
  and USB access while retaining `geolocation=(self)` for the map page.
- Public `Server` and `Via` headers are removed. Caddy's functional HTTP/3
  advertisement remains unchanged.
- The tracked configuration passed Caddy 2.11.4 validation and four Caddy
  regression tests.
- The broader Caddy, authentication, session, authorization, map, and
  responsive-dashboard regression suite passed all 273 tests.
- The backed-up deployment script synchronized and reloaded the runtime
  configuration. Tracked and runtime SHA-256 values matched after deployment.
- Live dashboard HTTP 200 and protected API HTTP 401 responses carried the
  complete header set without `Server` or `Via`.
- Streamlit health remained HTTP 200 and a direct WebSocket handshake returned
  HTTP 101 after deployment.

Accepted limitation:

- CSP is intentionally report-only. Converting it to enforcement requires a
  separate authenticated browser pass covering login/session renewal,
  downloads, device photos, map rendering, and mobile map geolocation.

Completion criteria:

- Browser-facing responses carry reviewed security headers without breaking Streamlit or map behavior.

### 13. Harden production process configuration

- [x] Remove Uvicorn `--reload` from production startup.
- [x] Separate development and production launch configurations.
- [x] Use deterministic dependency versions or a reviewed lock file.
- [x] Define service restart, log retention, and least-privilege operating account behavior.
- [x] Document the current Windows startup and full-runtime recovery behavior.
- [x] Require a written pre-restart state and post-restart expectation handoff.
- [x] Confirm FastAPI and Streamlit remain bound only to `127.0.0.1`.
- [x] Confirm Caddy admin API remains bound only to loopback.

Current operational constraint documented on 2026-06-12:

- Windows Task Scheduler launches `start_api_dashboard.bat` at system startup,
  so the runtime starts without an interactive user login.
- The resulting process consoles are not available from a later interactive
  session.
- The supported way to renew the complete production process set is a full
  Windows workstation restart followed by post-restart health verification.
- Do not start duplicate production processes manually. A migration to
  independently controllable Windows services or scheduled tasks remains a
  future hardening decision.
- Before every restart, append a dated handoff to `SESSION_NOTES.md` with the
  active task state, dirty working tree, runtime deployment state, expected
  processes/listeners, and exact post-restart checks.
- Do not initiate or request the restart until the handoff is complete. After
  restart, append actual verification results and any deviations.

Implementation prepared on 2026-06-15:

- Production launchers use `.venv-production`, one Uvicorn worker, explicit
  loopback bindings, and no development reload behavior.
- Development reload remains available only through explicitly named
  `scripts/start_api_dev.ps1` and `scripts/start_all_services_dev.ps1`.
- `requirements-production.in` contains reviewed direct pins and
  `requirements-production.lock.txt` contains 82 exact direct and transitive
  pins for CPython 3.14 on Windows. Startup rejects version drift and unlocked
  packages.
- API, Streamlit, and fresh-start Caddy output rotates in ProgramData at
  10 MiB with 10 backups. Scheduler retains 14 daily log backups and the
  authentication audit retains its separate 90-day policy.
- The startup task retries launcher failures three times after one minute but
  does not supervise a child process after launcher completion. Full
  workstation restart remains the supported recovery path.
- The task currently runs as `tra` with password logon and
  `RunLevel=Highest`. This is an accepted gap pending a separately validated
  dedicated non-interactive account with only the required filesystem,
  database, network-share, listener, and Caddy-certificate rights.
- Existing listeners were confirmed at `127.0.0.1:8000`,
  `127.0.0.1:8001`, and `127.0.0.1:2019`. A temporary production Uvicorn
  instance also returned HTTP 200 on loopback port 8010 without `--reload`.

Activation status:

- The isolated environment was built successfully and passed `pip check`,
  exact-lock verification, application imports, launcher dry-run, and focused
  regression tests.
- The scheduled production process set still uses the pre-change command line
  until the mandatory handoff is complete and the workstation is restarted.
  Completion criteria therefore require post-restart verification.

Startup resilience correction on 2026-06-13:

- Diff review confirmed that P1.3-P1.9 did not introduce the synchronous
  `ensure_dashboard_tables()` FastAPI lifespan call or the API liveness gate in
  the launcher. Those behaviors predated the security checklist.
- The cold-start failure was caused by their interaction: PostgreSQL was
  unavailable, FastAPI never exposed liveness, and the launcher therefore did
  not start Streamlit or Caddy.
- FastAPI now exposes liveness independently, retries dashboard database
  initialization in the background, and returns HTTP 503 from readiness until
  initialization succeeds.
- The focused startup, authentication, session, map, Caddy, and security suite
  passed 57 tests. Live verification during the continuing database outage
  returned HTTP 200 for liveness and HTTP 503 for readiness.
- Scheduler availability alerts were subsequently restricted to service-name
  messages only. Database alert emails contain only `Nedostupnost POSTGRES`
  and/or `Nedostupnost MSSQL`; runtime alert emails contain only
  `Nedostupnost API`, `Nedostupnost DASHBOARD`, and/or
  `Nedostupnost CADDY`. Diagnostic details remain in protected logs.

Completion criteria:

- Production starts without development reload behavior and with a reproducible dependency set.

### 14. Limit exposed public endpoints

- [x] Decide whether `/api/v1/auth/users-exist` needs to remain public.
- [x] Keep liveness/readiness responses minimal and avoid operational detail.
- [x] Ensure `/docs`, `/redoc`, and `/openapi.json` are disabled or admin-restricted in production.
- [x] Verify Caddy routes only intended public paths to FastAPI.
- [x] Add route exposure tests against the public hostname.

Implementation prepared on 2026-06-16:

- `/api/v1/auth/users-exist` remains public by decision because the active
  Streamlit login page uses it before authentication to decide whether the
  dashboard has any configured users. The endpoint returns only the existing
  minimal boolean bootstrap state.
- Health responses remain limited to `{"status": "ok"}`,
  `{"status": "ready"}`, or `{"status": "unavailable"}` and do not expose
  database, scheduler, host, version, or exception details.
- FastAPI documentation routes are now disabled by default. `/docs`, `/redoc`,
  and `/openapi.json` are registered only when `API_ENABLE_DOCS=true` is set
  explicitly, intended for local development rather than production.
- The public Caddy configuration continues to proxy only `/api/*` to FastAPI;
  `/docs`, `/redoc`, and `/openapi.json` are not routed to the API by the
  public hostname.
- Regression coverage verifies the FastAPI documentation route setting,
  minimal health responses, Caddy route exposure, and the existing
  authorization inventory.
- Runtime activation of the FastAPI documentation setting requires the next
  normal API restart because production Uvicorn does not run with reload.

Completion criteria:

- The public surface contains only endpoints required by browser clients and monitoring.

## P2 - Dependency And Operational Security

### 15. Add dependency vulnerability and code integrity scanning

- [x] Add `pip-audit` or an equivalent scanner to the development/security toolchain.
- [x] Scan the installed environment and declared dependencies.
- [x] Resolve or explicitly document accepted vulnerabilities.
- [x] Add a repeatable CI or scheduled scan.
- [x] Review direct CDN and browser asset dependencies separately.
- [x] Add a repeatable local code integrity scanner for tracked code and
  deployment configuration files.
- [x] Add a Windows scheduled-task registration script for the code integrity
  scanner.
- [ ] Create the approved production code integrity baseline after the current
  code changes are reviewed and committed or explicitly approved.
- [ ] Register and run the scheduled code integrity scan against that approved
  baseline.

Completion criteria:

- Dependency vulnerabilities and code integrity are checked regularly with
  recorded results.

Dependency audit implementation completed on 2026-06-18:

- Added isolated security tooling through `.venv-security`,
  `requirements-security.in`, and `requirements-security.lock.txt`.
  `pip-audit==2.10.1` is not installed into `.venv-production`, so the
  production runtime exact-lock check remains meaningful.
- Added `scripts/bootstrap_security_toolchain.ps1`,
  `scripts/run_dependency_audit.ps1`, and
  `scripts/register_dependency_audit_task.ps1`.
- `scripts/run_dependency_audit.ps1` verifies `.venv-production` against
  `requirements-production.lock.txt`, audits the production lock with
  `pip-audit --no-deps`, audits the installed production `site-packages`
  path, and writes JSON reports under
  `C:\ProgramData\monitorovaci_platforma\logs\security` by default.
- The first audit found `pypdf==6.12.2` affected by `CVE-2026-54531` and
  `CVE-2026-54530`, both fixed in `pypdf==6.13.0`.
- Updated `requirements-production.in`, `requirements-production.lock.txt`,
  and the local `.venv-production` installation to `pypdf==6.13.0`.
- After the update, `.venv-production` passed exact-lock verification and
  `pip check`, and the dependency audit returned no known vulnerabilities for
  both the lock and installed environment.
- Registered Windows scheduled task `MonitoringDependencyAudit` for a daily
  03:40 run and executed it once through Task Scheduler on 2026-06-18 with
  result `0`; the next run is scheduled for 2026-06-19 03:40.
- Reviewed active dashboard browser asset references. Leaflet remains
  vendored; no active dashboard source loads external executable JavaScript.
  Remaining external browser endpoints are data/image endpoints such as
  Open-Meteo and map tile providers.
- The audit intentionally uses fully pinned requirements with `--no-deps`.
  Hash-pinned dependency files remain a possible later hardening step.

Code integrity implementation prepared on 2026-06-16:

- `scripts/code_integrity_scan.py` creates a SHA-256 manifest for tracked
  code and deployment configuration files and compares later scans against
  that approved manifest.
- The default manifest path is outside the repository under ProgramData:
  `C:\ProgramData\monitorovaci_platforma\security\code_integrity_manifest.json`.
- Scan reports are written under
  `C:\ProgramData\monitorovaci_platforma\logs\security` by default.
- Runtime data, scheduler locks/logs/local SQLite state, SmartFuelPass session
  artifacts, and known electric-meter source data artifacts are excluded from
  the code integrity scope.
- New untracked source/configuration files are reported as unexpected unless
  they match an excluded runtime/data path.
- Source/configuration detection includes requirements `.in` files, so a new
  untracked dependency input is not silently missed.
- Baseline creation refuses to run while scanned files are dirty unless
  `--allow-dirty` is passed after explicit approval, so an unreviewed change is
  not silently promoted to the approved state.
- `scripts/run_code_integrity_scan.ps1` runs the scanner through
  `.venv-production`.
- `scripts/register_code_integrity_scan_task.ps1` registers a daily Windows
  scheduled task named `MonitoringCodeIntegrityScan`.
- Activation is still pending: no production baseline was created and no
  code-integrity scheduled task was registered because the working tree
  contains current uncommitted code changes.

### 16. Review secret and runtime artifact hygiene

- [x] Search tracked files and Git history for credentials, tokens, cookies, and private operational data.
- [!] Rotate any exposed secrets before removing them from current files.
- [x] Review tracked SmartFuelPass session artifacts separately with explicit approval.
- [x] Confirm `.env` and generated secret files remain ignored.
- [x] Document where each production secret is stored and who can access it.

Completion criteria:

- No active secret or reusable browser session is stored in tracked files.

Partial completion on 2026-06-18:

- Added `scripts/secret_hygiene_scan.py`, which scans the current tracked and
  untracked source working tree plus reachable Git history while reporting
  only redacted metadata. Raw matched values are not printed or stored in repo
  documentation.
- Added regression coverage proving current and historical secret matches are
  redacted and known session paths are reported without reading their cookie
  payloads.
- Added `SECURITY_SECRET_INVENTORY.md` documenting non-secret production
  secret, credential, session, and sensitive runtime artifact locations and
  access expectations.
- Confirmed `.env`, `.env.*`, SmartFuelPass session JSON files, SOFTLINK auth
  JSON, scheduler locks, frontend build info, nested electric-meter source
  data, and `run.txt` are ignored for future additions. Some of those files
  remain tracked and require explicit cleanup.
- Redacted scan on 2026-06-18 reported current tracked critical paths:
  `data/smartfuelpass/session_cookies.json` and
  `data/smartfuelpass/auto_login_session.json`.
- User approved retiring SmartFuelPass JSON session persistence on 2026-06-18.
  SmartFuelPass automation now logs in with `SMARTFUELPASS_EMAIL` and
  `SMARTFUELPASS_PASSWORD` for each portal run instead of reading or writing a
  session cookie JSON file.
- `data/smartfuelpass/session_cookies.json` and
  `data/smartfuelpass/auto_login_session.json` were removed from the Git index
  and remain ignored for any local leftover copies.
- Redacted rescan after untracking reported no current SmartFuelPass session
  JSON findings. Current findings are limited to tracked electric-meter source
  files, scheduler lock files, and `frontend_next/tsconfig.tsbuildinfo`.
- Remaining current tracked private/runtime data artifacts are:
  `moduly/mereni/elektromery/data/old/*.ts`,
  `moduly/mereni/elektromery/data/old/*.xlsx`,
  `core/scheduler/locks/*.lock`, and
  `frontend_next/tsconfig.tsbuildinfo`.
- Git history still contains historical `.env` paths, historical hard-coded
  `API_TOKEN_SECRET` assignments in launch scripts and `run.txt`, historical
  SmartFuelPass session JSON paths, historical SOFTLINK auth path, and
  historical meter source/runtime/build artifacts.
- The historical API signing secret exposure was already remediated by the
  2026-06-12 production secret rotation. No current hard-coded API signing
  secret was reported by the final redacted scan.

Open remediation:

- Expire historical SmartFuelPass portal sessions externally if any old session
  cookies might still be valid. Local ignored leftover JSON files can be
  deleted manually after operational review, but application code no longer
  reads them.
- Rotate SOFTLINK credentials/session externally if the historical
  `lds_auth.json` value is still valid.
- Remove tracked runtime/data/build artifacts from Git only after explicit
  approval.
- Do not rewrite Git history without a separate explicit history-rewrite
  decision and backup/remote coordination.

### 17. Perform an external security verification

- [!] Test from a network outside the server and corporate LAN.
- [-] Verify TLS configuration and certificate chain.
- [-] Run a security header assessment.
- [-] Test login throttling, session expiry, logout, and token revocation.
- [-] Test horizontal and vertical authorization boundaries.
- [-] Test common XSS, CSRF, injection, path traversal, and file-serving scenarios.
- [-] Record findings, remediation, and accepted residual risks.

Completion criteria:

- The public deployment has a dated security verification report with no unresolved critical or high-risk findings.

Partial verification on 2026-06-18:

- Direct requests from the server to `https://monitoring.armexholding.cz/` and
  `http://monitoring.armexholding.cz/` timed out, so this environment still
  does not satisfy the required outside-server/outside-LAN test. A real
  external-network check remains required.
- Loopback SNI route with
  `curl --resolve monitoring.armexholding.cz:443:127.0.0.1` verified that the
  HTTPS dashboard returns HTTP 200 and certificate validation succeeds without
  `-k`.
- Reviewed HTTPS response headers through the same loopback hostname:
  HSTS, `nosniff`, `Referrer-Policy`, `X-Frame-Options`,
  `Permissions-Policy`, and CSP report-only were present; `Server` and `Via`
  were absent on HTTPS responses.
- Public `users-exist` returned HTTP 200 with only the minimal boolean payload.
- `POST /api/v1/auth/session/refresh` without bearer returned HTTP 401.
- `/api/v1/map/images` without the dashboard session cookie returned HTTP 401.
- Runtime finding: HTTP redirect responses still included `Server: Caddy`.
  Tracked `Caddyfile` was updated to disable Caddy automatic redirects and use
  an explicit HTTP redirect block with `-Server` and `-Via`.
- Runtime finding: public `/docs`, `/redoc`, and `/openapi.json` fell through
  to the Streamlit shell with HTTP 200. Tracked `Caddyfile` was updated to
  respond HTTP 404 for those paths before the Streamlit fallback.
- Follow-up on 2026-06-18: the public Caddy routing rules were wrapped in an
  explicit `route` block so Caddy preserves the `/docs`, `/redoc`, and
  `/openapi.json` 404 rule before the Streamlit fallback after adaptation.
  The tracked configuration was deployed to
  `C:\Program Files\Caddy\Caddyfile` from an elevated PowerShell process and
  reloaded successfully.
- Runtime remediation on 2026-06-18 verified that tracked and runtime
  Caddyfile hashes matched, runtime Caddy validation passed, HTTP redirect
  responses no longer exposed `Server` or `Via`, and `/docs`, `/redoc`, and
  `/openapi.json` returned HTTP 404 through the public hostname loopback
  route.
- Automated security regression on 2026-06-18 covered login throttling,
  session refresh/logout/token revocation behavior, admin and device
  authorization boundaries, map image access controls, and device photo path
  handling:
  `.venv\Scripts\python.exe -m pytest tests\test_auth_routes.py
  tests\test_login_throttle.py tests\test_auth_audit.py
  tests\test_admin_auth_audit.py tests\test_dashboard_auth_state.py
  tests\test_dashboard_session_security.py
  tests\test_api_authorization_regression.py
  tests\test_admin_write_authorization.py tests\test_map_routes.py
  tests\test_map_layers_service.py tests\test_device_map_service.py
  tests\test_dashboard_map_shared.py tests\test_dashboard_device_photo.py
  tests\test_api_public_exposure.py tests\test_caddy_config.py -q --tb=short`
  passed 283 tests.

## Current Positive Controls

- [x] Public access uses HTTPS through Caddy.
- [x] Public login attempts are rate-limited by account identifier and trusted client IP.
- [x] Streamlit opens the application login directly without a second proxy credential prompt.
- [x] FastAPI and Streamlit bind to loopback interfaces.
- [x] Protected FastAPI endpoints require bearer authentication.
- [x] Domain API services enforce device filtering for non-admin users.
- [x] Admin API routes enforce server-side admin authorization.
- [x] Browser session cookie uses the `__Host-` prefix and is always `Secure`,
  `HttpOnly`, `SameSite=Lax`, and scoped to `Path=/`.
- [x] Passwords are salted and hashed with PBKDF2-HMAC-SHA256.
- [x] Password changes and logout increment `token_version` and revoke older tokens.
- [x] Map image paths are resolved server-side and are not supplied directly by clients.

## Verification Baseline

Verified through 2026-06-12:

- Public-hostname local TLS request returned HTTP 200.
- An unauthenticated protected map API request returned HTTP 401.
- The rotated API signing secret is active and tokens signed with the previous secret are rejected.
- Public dashboard returned HTTP 200 without a Basic Auth challenge after the
  temporary gate was removed.
- Live login throttling returned HTTP 429 with `Retry-After` at the configured
  account threshold.
- Authentication audit logging produced five failed-login records and one
  `account_brute_force` warning for a disposable identifier. The test password
  was absent from the JSONL file, whose ACL allows only SYSTEM,
  Administrators, and the operating account.
- Targeted Caddy, security, authentication, responsive-layout, and navigation
  tests passed: 55 tests.
- Targeted authentication-audit, admin-audit, CLI-audit, auth-route, throttle,
  auth-state, security-config, Caddy, navigation, and responsive-layout tests
  passed: 65 tests.
- Password-policy and compatible hash-migration coverage passed together with
  the broader security/dashboard suite: 84 tests.
- The complete suite passed 471 of 473 tests. Two independently reproducible
  failures remain in `tests/test_vodomery_reports.py`; no vodomery reporting
  source or test file was changed by P1.5.
- P1.9 session lifecycle coverage passed 50 focused tests and 154 broader
  security/dashboard/map tests.
- The full suite after P1.9 passed 492 of 494 tests. The same two unrelated
  `tests/test_vodomery_reports.py` failures remain.
- No dependency vulnerability scan was run because `pip-audit` was not installed.

## References

- OWASP Authentication Cheat Sheet:
  <https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html>
- OWASP Password Storage Cheat Sheet:
  <https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html>
- OWASP Session Management Cheat Sheet:
  <https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html>
- OWASP HTTP Headers Cheat Sheet:
  <https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html>
- NIST SP 800-63B:
  <https://pages.nist.gov/800-63-4/sp800-63b.html>
