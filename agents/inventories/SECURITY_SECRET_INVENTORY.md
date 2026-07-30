# Security Secret Inventory

Date: 2026-06-18

Purpose: non-secret inventory of production secret and sensitive runtime
artifact locations for `monitorovaci_platforma`. This document must never
include secret values, cookie values, bearer tokens, passwords, credential
hashes, or raw operational data.

## Access Model

- Repository files are not an approved secret store.
- Local secret files should be readable only by the operating Windows account,
  local Administrators, and SYSTEM.
- ProgramData secret and security-log paths should inherit restricted
  `C:\ProgramData\monitorovaci_platforma` ACLs.
- Browser sessions, portal cookies, auth audit logs, code-integrity manifests,
  and dependency/security scan reports are sensitive even when they are not
  credentials.

## Active Secret Locations

| Secret or artifact | Approved location | Access expectation | Notes |
| --- | --- | --- | --- |
| `API_TOKEN_SECRET` | Ignored local `.env` or protected service environment | Operating account, Administrators, SYSTEM | Rotating this value invalidates all existing dashboard bearer tokens and browser sessions. |
| Database connection settings | Ignored local `.env` or protected service environment | Operating account, Administrators, SYSTEM | Includes PostgreSQL and MSSQL connection details consumed by `python-decouple`. |
| Email credentials and report sender settings | Ignored local `.env` or protected service environment | Operating account, Administrators, SYSTEM | Used by scheduler/reporting code; never log credential values. |
| SmartFuelPass credentials | Ignored local `.env` or protected service environment | Operating account, Administrators, SYSTEM | Used only for controlled SmartFuelPass automation. |
| SOFTLINK auth/session file | Ignored local `moduly/mereni/elektromery/SOFTLINK/lds_auth.json` | Operating account, Administrators, SYSTEM | Historical Git path exists; rotate externally if the historical credential/session is still valid. |
| Caddy certificate private keys | Caddy-managed runtime data directory | Operating account that runs Caddy, Administrators, SYSTEM | Exact storage is controlled by Caddy runtime configuration and must stay outside Git. |
| Retired Caddy dashboard gate credentials | `C:\ProgramData\monitorovaci_platforma\caddy-dashboard-auth.env` and `C:\ProgramData\monitorovaci_platforma\dashboard-proxy-credentials.txt` | Operating account, Administrators, SYSTEM | Retired after application login throttling, but still sensitive if present. |

## Sensitive Non-Secret Locations

| Artifact | Location | Notes |
| --- | --- | --- |
| Authentication audit log | `C:\ProgramData\monitorovaci_platforma\logs\auth_audit.jsonl` | Must not contain passwords, bearer tokens, or cookie values. |
| Dependency audit reports | `C:\ProgramData\monitorovaci_platforma\logs\security` | Reports vulnerability metadata and paths, not secret values. |
| Code-integrity manifest | `C:\ProgramData\monitorovaci_platforma\security\code_integrity_manifest.json` | Approved baseline hash manifest, not a secret, but security-sensitive. |
| Code-integrity reports | `C:\ProgramData\monitorovaci_platforma\logs\security` | Reports changed/missing/unexpected paths. |

## Current Findings

Redacted scan on 2026-06-18 found no current hard-coded secret values in active
source code after false-positive review. The scan intentionally does not print
raw matched values.

SmartFuelPass session cookie JSON persistence was retired on 2026-06-18.
Automation uses password login for each portal run and no longer reads or
writes `data/smartfuelpass/session_cookies.json` or
`data/smartfuelpass/auto_login_session.json`. Those paths were removed from
the Git index and remain ignored if local leftover files are present. A
redacted rescan after untracking reported no current SmartFuelPass session JSON
findings.

Current tracked sensitive/runtime artifacts still requiring cleanup:

- `moduly/mereni/elektromery/data/old/*.ts`
- `moduly/mereni/elektromery/data/old/*.xlsx`
- `core/scheduler/locks/*.lock`
- `frontend_next/tsconfig.tsbuildinfo`

Git history still contains sensitive or operational paths:

- Historical `.env` entries.
- Historical hard-coded `API_TOKEN_SECRET` assignments in launch scripts and
  `run.txt`; the API signing secret was rotated on 2026-06-12.
- Historical SmartFuelPass session JSON paths.
- Historical `SOFTLINK/lds_auth.json` path.
- Historical meter source data, scheduler lock, and frontend build artifacts.

## Open Remediation

- Expire historical SmartFuelPass portal sessions externally if old cookies may
  still be valid. Application code no longer uses session JSON files.
- Rotate SOFTLINK credentials/session externally if the historical
  `lds_auth.json` value is still valid.
- Remove tracked runtime/data/build artifacts from Git only after explicit
  user approval.
- History rewrite is not planned during P2.16. If required later, use a
  separate reviewed operation because it rewrites repository history and
  affects collaborators/remotes.
