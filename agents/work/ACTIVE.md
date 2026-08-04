# Active work

## OPS-002 - Independent scheduler monitoring agent

- Status: active test-mode implementation
- Priority: normal
- Plan: `../plans/monitoring/SCHEDULER_MONITORING_AGENT_PLAN.md`
- Runtime design:
  `../plans/monitoring/SCHEDULER_MONITORING_AGENT_REMOTE_RUNTIME_DESIGN.md`
- Latest verified result: the clean PyCharm-oriented `0.4.0-test` bundle uses
  one ignored local `.env` and one `run_monitoring_agent.py` entry point. Its
  strict dotenv, polling, retry, self-health, bundle, facade, and authorization
  matrix passed with `267 passed`.
- Next step: replace the incomplete remote 0.3 setup with a fresh side-by-side
  0.4 project, create and ACL-protect its local `.env`, then run config and
  foreground HTTPS verification from PyCharm. Obtain separate approval before
  target-loss testing or Windows automatic-start registration.
- Restrictions: no external delivery, process control, manual jobs,
  application/database writes, or replacement of current alerts.
- Updated: 2026-08-04
