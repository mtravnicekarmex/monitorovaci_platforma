# Monitoring agent registry

No autonomous monitoring agents are registered yet.

Each future agent should have its own directory containing:

- purpose and owned runtime surface;
- read-only checks it may perform;
- alert conditions and severity;
- required credentials or permissions without secret values;
- escalation and recovery procedure;
- schedule, timeout, and retry policy;
- tests and a safe disable procedure.

Creating an entry here does not itself authorize production writes, restarts,
alerts, or external messages.
