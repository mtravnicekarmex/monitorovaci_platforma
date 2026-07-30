# SESSION_NOTES.md

Purpose: short current project baseline and handoff for
`monitorovaci_platforma`. Detailed historical entries are stored in
`archive/`.

## Current baseline

Date: 2026-07-30

- Production surfaces are the scheduler from `main.py`, FastAPI from
  `services/api/main.py`, Streamlit from `moduly/apps/dashboard/login.py`, and
  Caddy using the tracked root `Caddyfile`.
- `frontend_next/` remains experimental and is not the production dashboard.
- Durable operating rules are in `../../AGENTS.md`.
- Durable architecture and product decisions are in
  `../decisions/DECISIONS.md`.
- Work status is tracked in `../work/ACTIVE.md`, `../work/BACKLOG.md`,
  `../work/BLOCKED.md`, and `../work/COMPLETED.md`.
- Plans retain stable thematic paths under `../plans/`; lifecycle state does
  not move a plan between directories.

## Active handoff

- Active product work: `KAL-025`, the separately approval-gated kalorimetry
  scheduler integration.
- Required procedure:
  `../runbooks/KALORIMETRY_ACTIVATION_RUNBOOK.md`.
- Activation remains subject to the runbook's forecast, snapshot, scoring,
  event, scheduler, regression, restart, and post-rollout gates.
- Do not infer approval for production snapshots, scoring/event tables,
  scheduler writes, alert delivery, reports, or email from implementation
  readiness alone.
- The historical session split (`DOC-002`) was completed on 2026-07-30 with
  271 entries preserved: 98 in the June archive and 173 in the July archive.
- Archive preservation checks, focused tests (`10 passed`), the complete
  regression suite (`1240 passed`), and `git diff --check` all passed.

## Latest runtime verification

The read-only check immediately after the 2026-07-30 13:10:04 restart found:

- startup task `API_dashboard_caddy` completed with result 0;
- expected listeners 80, 443, 2019, 8000, and 8001 were present;
- local FastAPI live/ready, Streamlit health, and Caddy admin returned HTTP
  200;
- scheduler heartbeat was fresh and the protected kalorimetry prediction route
  returned the expected HTTP 401 without credentials;
- the public hostname timed out from the agent environment and was not
  independently verified there;
- the check occurred before the first scheduled quarter-hour execution after
  that restart, so that execution was not confirmed by this check.

Treat this as a dated observation, not a guarantee of current runtime health.

## History index

- `archive/LEGACY_PREAMBLE.md`: original baseline, architecture snapshot,
  cleanup list, completed shared-prediction checklist, and templates that
  preceded the old monolithic session log.
- `archive/2026-06.md`: 98 session entries dated 2026-06-05 through
  2026-06-26.
- `archive/2026-07.md`: 173 session entries dated 2026-07-07 through
  2026-07-30.

Monthly archives are immutable historical evidence. Corrections belong in a
new current entry or durable decision, not in silent archive rewrites.

## Recording new work

For substantive sessions:

1. Update the applicable work index.
2. Add or supersede a durable decision when architecture, product behavior, or
   workflow changes.
3. Append only a concise current handoff here when future sessions need facts
   not already captured by `AGENTS.md`, decisions, plans, or work indexes.
4. Move accumulated dated entries into a monthly archive through the verified
   archival workflow before this file becomes a long-running journal again.

Restart handoffs must follow `templates/RESTART_HANDOFF.md`.
General session entries may use `templates/SESSION_ENTRY.md`.
