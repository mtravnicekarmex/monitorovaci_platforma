# Local development commands

Development only. Run these commands from the repository root. Production
startup remains owned by the reviewed Windows startup path.

## API

The API signing secret is loaded from local configuration and must never be
placed in this file.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_api_dev.ps1
```

## Dashboard

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_dashboard_dev.ps1
```

## Experimental web frontend

```powershell
Set-Location frontend_next
npm run dev
```

## Scheduler

```powershell
.\.venv\Scripts\python.exe main.py
```
