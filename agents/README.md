# Agent workspace

This directory is the project control center for agent-assisted work and
future monitoring agents.

## Layout

- `registry/`: definitions and ownership of future monitoring agents.
- `work/`: small status indexes for active, blocked, queued, and completed work.
- `plans/`: stable implementation plans grouped by application domain.
- `runbooks/`: operational procedures and restart/deployment checklists.
- `inventories/`: reviewed consumer, security, and system inventories.
- `security/`: active security remediation and verification documents.
- `decisions/`: durable architectural, product, and workflow decisions.
- `history/`: short current handoff, templates, and immutable monthly session
  archives.

Plans keep stable paths throughout their lifecycle. Their current state belongs
in the files under `work/`; completed plans are not moved merely to express a
status change.

`AGENTS.md` intentionally remains in the repository root because agent tooling
discovers it there.
