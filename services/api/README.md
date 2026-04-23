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

## Autentizace

API používá JWT tokeny pro autentikaci.

### Login flow
```bash
# 1. Získání tokenu
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "uzivatel", "password": "heslo"}'

# 2. Použití tokenu v hlavičce
curl http://localhost:8000/api/v1/vodomery/devices \
  -H "Authorization: Bearer eyJ..."
```

### Oprávnění

| Dependency | Popis |
|------------|-------|
| `get_current_user` | jakýkoliv přihlášený uživatel |
| `get_current_vodomery_user` | uživatel s přístupem k vodoměrům |
| `get_current_manometry_user` | uživatel s přístupem k manometrům |
| `get_current_admin_user` | administrátor |

## API Dokumentace

Automaticky generovaná dokumentace je dostupná na:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **OpenAPI JSON**: http://localhost:8000/openapi.json

### Endpointy přehled

#### Health
| Metoda | Cesta | Popis |
|--------|-------|-------|
| GET | `/health/live` | Liveness check |
| GET | `/health/ready` | Readiness check |
| GET | `/health/scheduler` | Stav scheduleru (admin) |

#### Auth
| Metoda | Cesta | Popis |
|--------|-------|-------|
| GET | `/api/v1/auth/users-exist` | Kontrola existence uživatelů |
| POST | `/api/v1/auth/login` | Přihlášení |
| GET | `/api/v1/auth/me` | Profil přihlášeného uživatele |
| PATCH | `/api/v1/auth/me/email` | Změna e-mailu |
| POST | `/api/v1/auth/me/password` | Změna hesla |
| POST | `/api/v1/auth/logout` | Odhlášení |

#### Admin
| Metoda | Cesta | Popis |
|--------|-------|-------|
| GET | `/api/v1/admin/device-options` | Seznam všech zařízení |
| GET | `/api/v1/admin/users` | Seznam uživatelů |
| POST | `/api/v1/admin/users` | Vytvoření uživatele |
| PATCH | `/api/v1/admin/users/{username}` | Úprava uživatele |
| DELETE | `/api/v1/admin/users/{username}` | Smazání uživatele |

#### Web Search
| Metoda | Cesta | Popis |
|--------|-------|-------|
| GET | `/api/v1/web-search/monitors` | Seznam monitorů |
| POST | `/api/v1/web-search/preview` | Náhled hledání |
| GET | `/api/v1/web-search/results` | Výsledky hledání |
| POST | `/api/v1/web-search/monitors` | Vytvoření monitoru |
| PATCH | `/api/v1/web-search/monitors/{id}` | Úprava monitoru |
| DELETE | `/api/v1/web-search/monitors/{id}` | Smazání monitoru |

#### Vodoměry
| Metoda | Cesta | Popis |
|--------|-------|-------|
| GET | `/api/v1/vodomery/devices` | Seznam vodoměrů |
| GET | `/api/v1/vodomery/overview-metrics` | Přehledové metriky |
| GET | `/api/v1/vodomery/measurement-series` | Časová řada měření |
| GET | `/api/v1/vodomery/prediction-profiles` | Predikční profily |
| GET | `/api/v1/vodomery/recent-anomalies` | Nedávné anomálie |
| GET | `/api/v1/vodomery/open-events` | Otevřené eventy |
| GET | `/api/v1/vodomery/resolved-events` | Vyřešené eventy |
| GET | `/api/v1/vodomery/event-history` | Historie eventů |
| GET | `/api/v1/vodomery/device-detail` | Detail zařízení |
| GET | `/api/v1/vodomery/branch-day-overview` | Přehled větví |
| GET | `/api/v1/vodomery/outlier-reviews` | Outlier recenze (admin) |
| PATCH | `/api/v1/vodomery/outlier-reviews/{id}` | Aktualizace outlier (admin) |
| GET | `/api/v1/vodomery/expected-zero` | Seznam nulové spotřeby (admin) |
| PUT | `/api/v1/vodomery/expected-zero` | Nastavení nulové spotřeby (admin) |
| GET | `/api/v1/vodomery/alert-rules` | Alert pravidla (admin) |
| POST | `/api/v1/vodomery/alert-rules` | Vytvoření alert pravidla (admin) |
| PATCH | `/api/v1/vodomery/alert-rules/{id}` | Úprava alert pravidla (admin) |
| DELETE | `/api/v1/vodomery/alert-rules/{id}` | Smazání alert pravidla (admin) |

#### Manometry
| Metoda | Cesta | Popis |
|--------|-------|-------|
| GET | `/api/v1/manometry/devices` | Seznam manometrů |
| GET | `/api/v1/manometry/measurement-series` | Časová řada měření |
| GET | `/api/v1/manometry/device-detail` | Detail zařízení a lifetime statistiky |

#### Plynoměry
| Metoda | Cesta | Popis |
|--------|-------|-------|
| GET | `/api/v1/plynomery/devices` | Seznam plynoměrů |
| GET | `/api/v1/plynomery/recent-anomalies` | Nedávné anomálie |
| GET | `/api/v1/plynomery/open-events` | Otevřené eventy |
| GET | `/api/v1/plynomery/resolved-events` | Vyřešené eventy |
| GET | `/api/v1/plynomery/outlier-reviews` | Outlier recenze (admin) |
| PATCH | `/api/v1/plynomery/outlier-reviews/{id}` | Aktualizace outlier (admin) |
| GET | `/api/v1/plynomery/expected-zero` | Seznam nulové spotřeby (admin) |
| PUT | `/api/v1/plynomery/expected-zero` | Nastavení nulové spotřeby (admin) |
| GET | `/api/v1/plynomery/alert-rules` | Alert pravidla (admin) |
| POST | `/api/v1/plynomery/alert-rules` | Vytvoření alert pravidla (admin) |
| PATCH | `/api/v1/plynomery/alert-rules/{id}` | Úprava alert pravidla (admin) |
| DELETE | `/api/v1/plynomery/alert-rules/{id}` | Smazání alert pravidla (admin) |

## Konfigurace

Konfigurace se načítá z proměnných prostředí (viz `.env.example`):

| Proměnná | Popis |
|----------|-------|
| `API_TITLE` | Název API |
| `API_VERSION` | Verze API |
| `API_TOKEN_SECRET` | Tajný klíč pro JWT tokeny |
| `API_TOKEN_EXPIRE_MINUTES` | Platnost tokenu v minutách |
| `DATABASE_URL` | Připojení k databázi |

Další krok migrace je přepojení Streamlit loginu a prvních vodoměrových přehledů z přímého DB přístupu na tyto endpointy.
