# Restart handoff template

Complete this entry before every Windows workstation restart.

```markdown
### YYYY-MM-DD HH:MM TZ - Pre-restart handoff

Reason for restart:

- ...

Current task and conversation state:

- Completed: ...
- Pending: ...
- First action after restart: ...

Working tree and deployment:

- `git status --short`: ...
- Relevant changed files: ...
- Runtime-deployed files and hash/config state: ...

Sensitive and runtime artifacts:

- Do not print, change, delete, or commit: ...

Expected processes after restart:

- FastAPI/Uvicorn: one runtime on `127.0.0.1:8000`.
- Streamlit: one runtime on `127.0.0.1:8001`.
- Scheduler: one `main.py` runtime holding the scheduler process lock.
- Caddy: one runtime owning TCP 80/443 and `127.0.0.1:2019`.

Expected application state:

- FastAPI live/ready: HTTP 200.
- Streamlit health: HTTP 200.
- Scheduler heartbeat and job expectations: ...
- Tracked/runtime Caddyfile hash expectation: ...
- HTTP to HTTPS: expected redirect behavior ...
- HTTPS dashboard: expected status/behavior ...
- Protected API without bearer token: HTTP 401 JSON.
- Authentication or change-specific expectations: ...

Required post-restart checks:

- ...

Known risks or accepted gaps:

- ...
```
