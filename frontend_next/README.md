# Next.js Frontend MVP

Prvni migracni krok noveho internetoveho dashboardu nad existujicim FastAPI.

## Rozsah MVP

- login pres existujici `POST /api/v1/auth/login`
- session v `HttpOnly` cookie
- ochrana route `/vodomery`
- prvni overview stranka vodomeru nad API endpointy:
  - `GET /api/v1/auth/me`
  - `GET /api/v1/vodomery/devices`
  - `GET /api/v1/vodomery/overview-metrics`
- prvni detail vodomeru na route `/vodomery/[identifikace]`:
  - `GET /api/v1/vodomery/device-detail`
  - `GET /api/v1/vodomery/measurement-series`
  - `GET /api/v1/vodomery/event-history`

## Spusteni

1. Vytvor `.env.local` podle `.env.example`
2. Nainstaluj zavislosti:
   `npm install`
3. Spust dev server:
   `npm run dev`

Frontend ocekava bezici FastAPI na `BACKEND_API_BASE_URL`.
