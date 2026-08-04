# Monitoring Agent Authentication Design

Prepared: 2026-07-31

Status: credential provisioned and first remote HTTPS authorization proof
passed; rotation proof pending

## Identity boundary

The monitoring facade uses a dedicated non-human bearer credential. It does
not accept a dashboard account, dashboard cookie, administrator token,
Tailscale membership alone, or credentials embedded in a URL.

The bearer secret is generated on the supervision center and stored there in
the ACL-restricted local `.env` used by the standalone monitoring project.
The monitored workstation receives only its SHA-256 digest through
`MONITORING_AGENT_TOKEN_SHA256`. The API compares digests in constant time and
never needs the original secret.

The previous standalone credential-file detail is superseded for bundles
starting with `0.4.0-test`. The new runtime reads the `.env` directly and does
not export its values into persistent or session-level process environment
variables. The bundle contains only `.env.example`; `.gitignore` excludes the
real `.env`.

The facade remains closed with HTTP 503 when no valid digest is configured.
Missing, malformed, or incorrect bearer credentials return HTTP 401 without
revealing the expected value.

On 2026-08-03 the separately stored center credential authenticated over the
tailnet-only HTTPS listener on port `9443`. The three allowlisted GET routes
returned schema-valid HTTP 200 observations. An unauthenticated request was
HTTP 401, the same monitoring credential was HTTP 401 on the human-admin
Health route, an unknown monitoring route was HTTP 404, and POST on the
read-only liveness route was HTTP 405. No credential value was printed or
copied to the monitored workstation.

## Rotation

Rotation uses two server-side digest slots:

- `MONITORING_AGENT_TOKEN_SHA256`: current credential digest;
- `MONITORING_AGENT_PREVIOUS_TOKEN_SHA256`: temporary previous digest.

Provision and verify the new credential first, move the old digest into the
previous slot, atomically replace the center `.env`, verify polling, and then
remove the previous digest. Never store either bearer secret on the monitored
workstation or in repository files.

This rotation sequence has not yet been executed. Keep the authentication
checklist open until both-slot acceptance and old-credential revocation are
proved without logging either secret.

## Exposed surface

Only these authenticated GET routes are registered:

- `/api/v1/monitoring/health/live`;
- `/api/v1/monitoring/health/ready`;
- `/api/v1/monitoring/health/system/scheduler`.

The scheduler route reuses the existing sanitized system-health collector.
No POST, manual run, log, database, shell, process-control, configuration, or
application-write route is part of the facade.

## Network boundary

Authentication supplements Tailscale. The later remote proof must expose the
facade only on the dedicated tailnet HTTPS port `9443`, preserve the existing
Tailscale Serve port `443`, and deny ordinary LAN/public access.
