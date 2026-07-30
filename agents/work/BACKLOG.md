# Backlog

## OPS-002 - Register application monitoring agents

- Status: planned
- Priority: normal
- First agent:
  `../plans/monitoring/SCHEDULER_MONITORING_AGENT_PLAN.md`
- Approved scope: independent read-only scheduler/system observer in test
  mode, using existing health endpoints and producing local incident reports
  and programmer task drafts.
- Next step: inventory the exact health endpoint response contracts before
  choosing the independent runtime or implementing the endpoint client.
- Restrictions: current alerts remain authoritative; no production
  registration, external delivery, process control, manual jobs, or
  application/database writes are authorized.
- Candidate surfaces: scheduler, FastAPI, Streamlit, Caddy, databases, imports,
  and prediction pipelines.
- Updated: 2026-07-30
