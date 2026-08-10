# Completed work

This is a concise index, not a duplicate session log. Detailed evidence remains
in the relevant plan, decision record, inventory, or session history.

## OPS-001 - Agent workspace organization

- Status: done
- Completed: 2026-07-30
- Result: project Markdown documentation moved from the repository root to
  stable thematic paths under `agents/`; `AGENTS.md` remains discoverable in
  the root.
- Verification: documentation references checked, targeted tests passed
  (`9 passed`), full regression suite passed (`1239 passed`), and
  `git diff --check` passed.

## DOC-002 - Split session history into bounded archives

- Status: done
- Completed: 2026-07-30
- Result: replaced the monolithic session journal with a short current
  baseline, two immutable monthly archives, a preserved legacy preamble, and
  separate session/restart templates.
- Preservation: 271 dated entry blocks retained exactly once by SHA-256
  fingerprint: 98 entries for 2026-06 and 173 entries for 2026-07.
- Verification: archival dry-run and post-write counts passed, focused tests
  passed (`10 passed`), full regression passed (`1240 passed`), and
  `git diff --check` passed.

## KAL-025 - Kalorimetry scheduler integration and activation rollout

- Status: done
- Completed: 2026-08-04
- Result: current-week active snapshots, latest-only anomaly scoring, the two
  approved event types, quarter-hour processing, and forecast-gated weekly
  rebuild are active without kalorimetry alert or report delivery.
- Verification: the final whole-stack restart loaded the distinct scheduler
  metric identities; runtime, authorization, snapshots, exact profile groups,
  score links, checkpoints, event state, and read-only historical
  reconciliation passed with zero production mismatches or 24-hour failures.
- Evidence: exact regression counts and production aggregates remain in
  `../plans/kalorimetry/KALORIMETRY_PREDICTION_PIPELINE_PLAN.md` and
  `../history/SESSION_NOTES.md`.

## PLY-001 - Plynomery fakturacni odecty

- Status: done
- Completed: 2026-08-10
- Result: admin-only manual Streamlit workflow for append-only monthly gas
  billing readings and manual PDF creation/download. The user accepted the
  final PDF result.
- Operating boundary: the PDF remains manual, actual/billing-only, and outside
  scheduler automation, scheduler manual runs, automatic email delivery, and
  report recipient configuration.
- Verification: post-restart stack checks passed; July 2026 read-only billing
  validation returned seven current readings, seven previous readings, seven
  branches, and zero input issues; in-memory HTML/PDF rendering passed;
  focused billing regression passed with `13 passed`; user acceptance closed
  the remaining page/PDF verification gap.
