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

- [ ] Apply one shared password validator to user creation, admin reset, CLI creation, and self-service changes.
- [ ] Require at least 15 characters while password-only authentication is used.
- [ ] Allow long passphrases, Unicode, spaces, password managers, and paste.
- [ ] Reject commonly used and compromised passwords using a local or privacy-preserving blocklist.
- [ ] Do not require arbitrary periodic password changes.
- [ ] Increase PBKDF2-HMAC-SHA256 from 390,000 to at least 600,000 iterations, or migrate to Argon2id.
- [ ] Rehash older hashes after a successful login.
- [ ] Add tests for every password entry path and hash migration.

Completion criteria:

- Weak passwords cannot be created through any supported path.
- Existing users migrate without a forced bulk password reset unless explicitly required.

### 6. Add MFA or corporate SSO

- [ ] Decide between corporate OIDC/SAML SSO and application-managed MFA.
- [ ] Require MFA at minimum for administrators.
- [ ] Define enrollment, recovery, revocation, and lost-device procedures.
- [ ] Require recent reauthentication for sensitive actions.
- [ ] Add tests for authentication and recovery flows.

Completion criteria:

- Compromise of a password alone is insufficient to access an administrator account.

## P1 - Session And Token Security

### 7. Remove the full bearer token from map iframe JavaScript

- [ ] Replace the token-bearing iframe flow with a design that does not expose the main API token to map JavaScript.
- [ ] Consider an authorized same-origin image endpoint using the browser session cookie.
- [ ] If a delegated token is necessary, make it short-lived and limited to a specific image and operation.
- [ ] Ensure the map cannot use credentials for admin or unrelated API calls.
- [ ] Add tests proving that generated map HTML contains no main bearer token.

Completion criteria:

- Inspecting or compromising map iframe JavaScript does not disclose a reusable dashboard API token.

### 8. Remove third-party executable JavaScript from authenticated pages

- [ ] Host the required Leaflet JavaScript and CSS locally.
- [ ] Pin reviewed versions in the repository or controlled static assets.
- [ ] Remove runtime loading from `unpkg.com`.
- [ ] Review all other authenticated pages for externally loaded scripts.
- [ ] Add a regression test preventing unapproved external script origins.

Completion criteria:

- Authenticated pages execute only application-controlled JavaScript.

### 9. Harden browser session handling

- [ ] Rename the session cookie with the `__Host-` prefix.
- [ ] Always set `Secure`, `HttpOnly`, `SameSite=Lax` or stricter, and `Path=/`.
- [ ] Do not derive security attributes from untrusted forwarded headers.
- [ ] Add an inactivity timeout appropriate for operational dashboard use.
- [ ] Keep an absolute timeout and consider periodic token renewal.
- [ ] Rotate or invalidate sessions after password, role, account-status, and permission changes.
- [ ] Consider `Clear-Site-Data` during logout where browser compatibility permits.
- [ ] Add session lifecycle tests.

Completion criteria:

- Stolen sessions have bounded lifetime and privilege changes revoke active access promptly.

## P1 - Authorization

### 10. Move all privileged writes behind server-side authorization

- [ ] Inventory Streamlit modules that write directly to PostgreSQL or MSSQL.
- [ ] Move privileged revision writes behind authenticated FastAPI endpoints.
- [ ] Enforce admin access inside the service/API operation, not only through disabled UI controls.
- [ ] Review device administration, imports, reports, and file operations for the same pattern.
- [ ] Add negative tests proving non-admin users cannot invoke write functions directly.

Known initial finding:

- `moduly/apps/dashboard/pages/28_revize.py`
- `moduly/apps/dashboard/revize_shared.py`

Completion criteria:

- Every privileged mutation has a server-side authorization decision at its execution boundary.

### 11. Expand authorization regression coverage

- [ ] Test all API routes without authentication.
- [ ] Test all admin routes with a non-admin token.
- [ ] Test every device-scoped route with an allowed and disallowed identifier.
- [ ] Test permission changes against already issued tokens.
- [ ] Test map catalog, features, filters, and images for cross-device access.

Completion criteria:

- Authorization tests cover route, role, page, section, and device boundaries.

## P2 - HTTP And Deployment Hardening

### 12. Add security response headers

- [ ] Add HSTS after confirming HTTPS is the only supported public access method.
- [ ] Add `X-Content-Type-Options: nosniff`.
- [ ] Add `Referrer-Policy: strict-origin-when-cross-origin`.
- [ ] Add clickjacking protection using CSP `frame-ancestors` and a compatible fallback where useful.
- [ ] Develop a Streamlit-compatible Content Security Policy, initially in report-only mode.
- [ ] Add a restrictive `Permissions-Policy`, while preserving map geolocation where required.
- [ ] Remove unnecessary server fingerprinting headers where practical.
- [ ] Add Caddy configuration tests and verify live response headers.

Completion criteria:

- Browser-facing responses carry reviewed security headers without breaking Streamlit or map behavior.

### 13. Harden production process configuration

- [ ] Remove Uvicorn `--reload` from production startup.
- [ ] Separate development and production launch configurations.
- [ ] Use deterministic dependency versions or a reviewed lock file.
- [ ] Define service restart, log retention, and least-privilege operating account behavior.
- [x] Document the current Windows startup and full-runtime recovery behavior.
- [x] Require a written pre-restart state and post-restart expectation handoff.
- [ ] Confirm FastAPI and Streamlit remain bound only to `127.0.0.1`.
- [ ] Confirm Caddy admin API remains bound only to loopback.

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

Completion criteria:

- Production starts without development reload behavior and with a reproducible dependency set.

### 14. Limit exposed public endpoints

- [ ] Decide whether `/api/v1/auth/users-exist` needs to remain public.
- [ ] Keep liveness/readiness responses minimal and avoid operational detail.
- [ ] Ensure `/docs`, `/redoc`, and `/openapi.json` are disabled or admin-restricted in production.
- [ ] Verify Caddy routes only intended public paths to FastAPI.
- [ ] Add route exposure tests against the public hostname.

Completion criteria:

- The public surface contains only endpoints required by browser clients and monitoring.

## P2 - Dependency And Operational Security

### 15. Add dependency vulnerability scanning

- [ ] Add `pip-audit` or an equivalent scanner to the development/security toolchain.
- [ ] Scan the installed environment and declared dependencies.
- [ ] Resolve or explicitly document accepted vulnerabilities.
- [ ] Add a repeatable CI or scheduled scan.
- [ ] Review direct CDN and browser asset dependencies separately.

Completion criteria:

- Dependency vulnerabilities are checked regularly with recorded results.

### 16. Review secret and runtime artifact hygiene

- [ ] Search tracked files and Git history for credentials, tokens, cookies, and private operational data.
- [ ] Rotate any exposed secrets before removing them from current files.
- [ ] Review tracked SmartFuelPass session artifacts separately with explicit approval.
- [ ] Confirm `.env` and generated secret files remain ignored.
- [ ] Document where each production secret is stored and who can access it.

Completion criteria:

- No active secret or reusable browser session is stored in tracked files.

### 17. Perform an external security verification

- [ ] Test from a network outside the server and corporate LAN.
- [ ] Verify TLS configuration and certificate chain.
- [ ] Run a security header assessment.
- [ ] Test login throttling, session expiry, logout, and token revocation.
- [ ] Test horizontal and vertical authorization boundaries.
- [ ] Test common XSS, CSRF, injection, path traversal, and file-serving scenarios.
- [ ] Record findings, remediation, and accepted residual risks.

Completion criteria:

- The public deployment has a dated security verification report with no unresolved critical or high-risk findings.

## Current Positive Controls

- [x] Public access uses HTTPS through Caddy.
- [x] Public login attempts are rate-limited by account identifier and trusted client IP.
- [x] Streamlit opens the application login directly without a second proxy credential prompt.
- [x] FastAPI and Streamlit bind to loopback interfaces.
- [x] Protected FastAPI endpoints require bearer authentication.
- [x] Domain API services enforce device filtering for non-admin users.
- [x] Admin API routes enforce server-side admin authorization.
- [x] Browser session cookie is currently `HttpOnly`, `Secure` over HTTPS, and `SameSite=Lax`.
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
