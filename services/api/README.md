# FastAPI Migration

Tato slozka obsahuje paralelni API vrstvu, kterou budeme postupne nasazovat vedle existujiciho Streamlit dashboardu.

## Prvni spusteni

API vrstva neimportuje jen FastAPI moduly. Pri startu saha i do sdilenych DB/model vrstev, proto `requirements-api.txt`
obsahuje take `sqlalchemy`, `pandas`, `geoalchemy2` a DB drivery.

1. Vytvorit virtualni prostredi v koreni projektu:
   `py -m venv .venv`
2. Doinstalovat zavislosti do tohoto virtualniho prostredi:
   `.venv\Scripts\python.exe -m pip install -r requirements-api.txt`
3. Pripravit `.env` podle `.env.example` a vyplnit DB pristupy.
4. Nastavit `API_TOKEN_SECRET` v `.env` nebo v prostredi.
   Placeholder `change-me` je neplatny a API s nim zamerne nenastartuje.
5. Pro lokalni vyvoj spustit API skrz helper:
   `powershell -ExecutionPolicy Bypass -File scripts\start_api.ps1`

Poznamky:

- Helper skript ocekava virtualni prostredi v `.venv`.
- Pro endpointy, ktere sahaji do MSSQL, musi byt na stroji dostupny `ODBC Driver 18 for SQL Server`.
- Pokud chces API spustit bez helperu, pouzij:
  `.venv\Scripts\python.exe -m uvicorn services.api.main:app --host 127.0.0.1 --port 8000 --reload`

## Aktuální endpointy

- `GET /health/live`
- `GET /health/ready`
- `GET /health/scheduler` (admin auth)
- `POST /api/v1/auth/login`
- `GET /api/v1/auth/users-exist`
- `GET /api/v1/auth/me`
- `PATCH /api/v1/auth/me/email`
- `POST /api/v1/auth/me/password`
- `POST /api/v1/auth/logout`
- `GET /api/v1/admin/device-options`
- `GET /api/v1/admin/users`
- `POST /api/v1/admin/users`
- `PATCH /api/v1/admin/users/{username}`
- `DELETE /api/v1/admin/users/{username}`
- `POST /api/v1/web-search/preview`
- `GET /api/v1/web-search/monitors`
- `POST /api/v1/web-search/monitors`
- `PATCH /api/v1/web-search/monitors/{monitor_id}`
- `DELETE /api/v1/web-search/monitors/{monitor_id}`
- `GET /api/v1/web-search/results`
- `GET /api/v1/vodomery/devices`
- `GET /api/v1/vodomery/branch-day-overview`
- `GET /api/v1/vodomery/overview-metrics`
- `GET /api/v1/vodomery/measurement-series`
- `GET /api/v1/vodomery/prediction-profiles`
- `GET /api/v1/vodomery/recent-anomalies`
- `GET /api/v1/vodomery/open-events`
- `GET /api/v1/vodomery/resolved-events`
- `GET /api/v1/vodomery/event-history`
- `GET /api/v1/vodomery/device-detail`
- `GET /api/v1/vodomery/expected-zero`
- `PUT /api/v1/vodomery/expected-zero`
- `GET /api/v1/vodomery/alert-rules`
- `POST /api/v1/vodomery/alert-rules`
- `PATCH /api/v1/vodomery/alert-rules/{rule_id}`
- `DELETE /api/v1/vodomery/alert-rules/{rule_id}`

Další krok migrace je přepojení Streamlit loginu a prvních vodoměrových přehledů z přímého DB přístupu na tyto endpointy.
