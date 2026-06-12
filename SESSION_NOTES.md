# SESSION_NOTES.md

Purpose: current project baseline, handoff notes, and session log for `monitorovaci_platforma`.

## Latest Baseline

Date: 2026-06-05

The user requested a read-only review of the current project state and confirmed this state should be treated as the baseline for future work. The review covered the repository root and subdirectories without intentionally modifying project files.

Baseline working tree observed before creating these context files:

```text
 M data/smartfuelpass/session_cookies.json
?? moduly/mereni/elektromery/data/
```

Observed untracked electric-meter data artifacts:

```text
moduly/mereni/elektromery/data/old/19891.ts
moduly/mereni/elektromery/data/old/19892.ts
moduly/mereni/elektromery/data/old/20445.ts
moduly/mereni/elektromery/data/old/23582.ts
moduly/mereni/elektromery/data/old/39443.ts
moduly/mereni/elektromery/data/old/FVE 2026-02.xlsx
moduly/mereni/elektromery/data/old/LDS 2026-02.xlsx
```

Do not inspect or clean these artifacts unless the user explicitly asks.

## Entry Points

- Scheduler: `main.py`
- Scheduler schedules: `core/scheduler/job_schedule.py`
- Scheduler runtime: `core/scheduler/scheduler.py`
- Scheduler metrics: `core/scheduler/metrics.py`
- FastAPI app: `services/api/main.py`
- API auth tokens: `services/api/core/tokens.py`
- API dependencies: `services/api/core/dependencies.py`
- Streamlit dashboard: `moduly/apps/dashboard/login.py`
- Streamlit navigation: `moduly/apps/dashboard/navigation_config.py`
- Streamlit auth: `moduly/apps/dashboard/auth.py`
- Dashboard DB model: `moduly/apps/dashboard/database/models.py`
- Dashboard DB bootstrap: `moduly/apps/dashboard/database/db_init.py`
- Streamlit config: `.streamlit/config.toml`
- Reverse proxy config: `Caddyfile`
- Experimental Next.js area: `frontend_next/`

## Current Architecture Snapshot

- The active dashboard is Streamlit.
- `frontend_next/` is experimental, not currently used in daily operation, and may be developed further later.
- FastAPI exposes health, scheduler health, auth, admin, kalorimetry, manometry, plynomery, vodomery, and web-search routers.
- PostgreSQL is the normalized storage layer for monitoring/dashboard/web-search/revision data.
- MSSQL connections exist for source or legacy operational data.
- Scheduler definitions are centralized in `core/scheduler/job_schedule.py`.
- Scheduler runtime uses locks, metrics, manual run specs, and email alerts.
- Dashboard permissions are centralized around navigation config and dashboard user records.

## Database and Schema Notes

Known schema responsibilities:

- `monitoring`: normalized measurements, anomaly scores/events, alerting/outlier data, SmartFuelPass, meteo data.
- `dashboard`: Streamlit users and permissions.
- `web_search`: monitors and search results.
- `revize`: revision/evidence records.
- `dbo`: source or legacy operational tables.
- `evidence`: QGIS/evidence device metadata.

Important time columns and concepts:

- `source_date`
- `time_utc`
- `time_basis`
- `source_timezone`
- `source_utc_offset_minutes`
- `time_fold`
- `timestamp_position`
- SmartFuelPass start/end UTC/source interval semantics.

## Domain Notes

- `vodomery`: water meters, AREAL/SCVK sources, anomaly models v1/v2/v3, event handling, alerting, outlier review, reports, billing.
- `plynomery`: gas meters, baseline and weather-adjusted models, expected-zero/outlier/alerting behavior.
- `elektromery`: electricity meters, SOFTLINK and binary imports, OTE reporting, new device discovery.
- `kalorimetry`: heat meter imports, normalization, outlier review.
- `manometry`: pressure imports, dashboard/API surfaces.
- `smartfuelpass`: card/fuel imports and reports with browser/session artifacts.
- `web_search`: monitored searches and persisted results.

Water event examples:

- `NIGHT_USAGE`
- `SPIKE`
- `LONG_LEAK`
- `ZERO_FLOW`
- `EXPECTED_ZERO_USAGE`
- `OUTLIER_REVIEW`

## Current Functional Notes

- The water-meter dashboard page for anomalies/events contains event-type filtering for currently open and historical event sections.
- The selectors support filtering examples such as `SPIKE` and `NIGHT_USAGE`.
- The active Streamlit sidebar navigation is disabled through `.streamlit/config.toml` with custom dashboard navigation handling.
- Caddy is configured to reverse proxy port `:8080` to `127.0.0.1:8001`.

## Test Inventory

Read-only inventory found:

- 52 test files.
- 335 test functions.

High-value test areas:

- Scheduler behavior.
- Measurement imports, gaps, resets, outliers, and time semantics.
- Dashboard navigation, authentication, and auto refresh.
- Reports and billing.
- SmartFuelPass import/report workflow.
- Web search workflow.

Common verification commands:

```powershell
python -m pytest tests -v --tb=short
python -m pytest tests\test_scheduler.py -v --tb=short
python -m pytest tests\test_vodomery_db_import.py -v --tb=short
python -m pytest tests\test_dashboard_navigation_config.py -v --tb=short
```

Experimental frontend verification:

```powershell
cd frontend_next
npm run typecheck
```

Use frontend verification only when the task touches `frontend_next/`.

## Open Questions and Cleanup Topics

These are recognized topics, not approved changes:

- Decide whether SmartFuelPass session files should remain tracked.
- Decide whether scheduler lock files should remain tracked.
- Decide whether `frontend_next/tsconfig.tsbuildinfo` should be untracked/ignored.
- Decide whether `.gitignore` should ignore nested electric-meter data artifacts such as `moduly/mereni/elektromery/data/old/*.ts`.
- Decide whether context-file updates should be committed together with code changes or as separate documentation commits.

## Session Log Template

Use this format for future entries:

```text
### YYYY-MM-DD

Scope:
- ...

Changed:
- ...

Verified:
- ...

Not verified:
- ...

Decisions/notes:
- ...

Follow-up:
- ...
```

## Restart Handoff Template

This entry is mandatory before every Windows workstation restart:

```text
### YYYY-MM-DD HH:MM - Pre-restart handoff

Reason for restart:
- ...

Current task/conversation state:
- Completed: ...
- Pending: ...
- First action after restart: ...

Working tree and deployment:
- `git status --short`: ...
- Relevant changed files: ...
- Runtime-deployed files and hash/config state: ...

Sensitive/runtime artifacts:
- Do not print/change/delete/commit: ...

Expected processes after restart:
- FastAPI/Uvicorn: one runtime on `127.0.0.1:8000`
- Streamlit: one runtime on `127.0.0.1:8001`
- Scheduler: one `main.py` runtime holding `scheduler_process` lock
- Caddy: one runtime owning TCP 80/443 and `127.0.0.1:2019`

Expected application state:
- FastAPI live/ready: HTTP 200
- Streamlit health: HTTP 200
- Scheduler heartbeat/job expectations: ...
- Tracked/runtime Caddyfile hash expectation: ...
- HTTP -> HTTPS: 308
- HTTPS dashboard: expected status/behavior ...
- Protected API without bearer token: HTTP 401 JSON
- Authentication/change-specific expectations: ...

Required post-restart checks:
- ...

Known risks or accepted gaps:
- ...
```

## Session Log

### 2026-06-05

Scope:
- Created persistent context workflow for future sessions.
- Performed read-only baseline review of the project.
- Added approved root documentation files.

Changed:
- Added `AGENTS.md`.
- Added `DECISIONS.md`.
- Added `SESSION_NOTES.md`.

Verified:
- Confirmed the context files did not already exist before writing.
- Checked working tree status before writing.

Not verified:
- No test suite was run for these documentation-only changes.

Decisions/notes:
- The current state is the baseline for future sessions.
- `frontend_next/` is experimental and not currently used in daily operation.
- Existing runtime/data artifacts were intentionally left unchanged.

Follow-up:
- Review cleanup topics only after explicit user approval.

### 2026-06-05

Scope:
- Added the first Streamlit/FastAPI map MVP for the Vodomery dashboard section.
- Added contextual building polygons to the same Leaflet layer control used for base-map switching.
- Investigated dashboard login failure caused by an unresponsive API process on port `8000`.

Changed:
- Added a configurable Streamlit page `vodomery_map`.
- Added FastAPI map endpoints for Vodomery map data.
- Added a map bundle endpoint returning `Vodomery` and `Budovy` layers.
- Added `evidence.BUDOVY` as a contextual polygon overlay with `fid`, `budova`, and `pocet_podlazi` properties.
- Added OSM and CUZK `ORTOFOTO_WM` base-map switching in the Leaflet layer control.
- Set local `.env` `DASHBOARD_API_BASE_URL` to `http://127.0.0.1:8002` because port `8000` is held by an unresponsive process that could not be terminated from the current session.

Verified:
- Targeted map/navigation/API tests passed: `tests\test_dashboard_map_shared.py`, `tests\test_dashboard_navigation_config.py`, and `tests\test_device_map_service.py`.
- Real map service load returned `Vodomery` as 59 `Point` features and `Budovy` as 30 `Polygon` features, both transformed to target SRID `4326`.
- API health checks on `http://127.0.0.1:8002/health/live` and `/health/ready` returned HTTP 200.
- Dashboard API client resolved `DASHBOARD_API_BASE_URL` to `http://127.0.0.1:8002` and `/api/v1/auth/users-exist` returned HTTP 200.

Not verified:
- Full test suite was not run.
- Actual dashboard login with user credentials was not tested.

Decisions/notes:
- Vodomery map data uses `evidence.vodoměry.identifikace` for geometry mapping and enriches details from `dbo.Zarizeni_vodomery.identifikace`.
- Vodomery map page access is controlled through configurable page permission `vodomery_map`.
- The `Budovy` layer is a contextual map layer and is not filtered by device permissions; access is gated by the `vodomery_map` page permission.
- API startup initially failed because `.venv` had `pydantic-core 2.47.0` while `pydantic 2.13.4` requires `pydantic-core 2.46.4`; the local venv was corrected to `pydantic-core 2.46.4`.

Follow-up:
- If the existing Streamlit process still uses the old API URL, restart Streamlit so it reloads `.env`.
- Investigate or terminate the stale process holding port `8000` from the account or privilege level that started it.
- Decide whether the temporary local API port `8002` should remain documented as a workaround or be reverted after port `8000` is released.

### 2026-06-05

Scope:
- Continued the Vodomery map MVP with another contextual evidence layer.
- Added `evidence.MÍSTNOSTI` as a room polygon overlay.
- Drafted the intended cross-layer filtering direction for buildings, floors, rooms, and devices.

Changed:
- Added `MISTNOSTI_MAP_LAYER` using `evidence.MÍSTNOSTI` columns `fid`, `mistnost_id`, `místnost`, `patro`, `budova`, `nájemce`, `popis`, and `plocha`.
- Included map layers in contextual-to-device draw order: `Budovy`, `Místnosti`, `Vodoměry`.
- Added Leaflet styling and popup fields for the `mistnosti` overlay.
- Added a Streamlit map metric for room count.
- Added tests for room GeoJSON serialization, room layer config, endpoint layer ordering, and Leaflet overlay output.

Verified:
- Targeted tests passed: `.venv\Scripts\python.exe -m pytest tests\test_device_map_service.py tests\test_dashboard_map_shared.py tests\test_dashboard_navigation_config.py -v --tb=short`.
- Real map service load returned `Budovy` as 30 `Polygon` features, `Místnosti` as 114 `MultiPolygon` features, and `Vodoměry` as 59 `Point` features, all transformed from source SRID `3857` to target SRID `4326`.

Not verified:
- Full test suite was not run.
- Live Streamlit/browser interaction was not tested.

Decisions/notes:
- The user stated the port `8000` blockage was resolved by restart.
- Contextual layers (`Budovy`, `Místnosti`) remain gated by the `vodomery_map` page permission, not by device permissions.
- Device layers such as `Vodoměry` remain restricted by existing device permissions.

Follow-up:
- Add a server-side map filter request model before broadening the map to more device domains.
- Candidate filters are `layer_ids`, `budova`, `patro`, `mistnost_id`, optional geometry/bbox, and eventually device domain/type.

### 2026-06-05

Scope:
- Started the general map-layer configuration foundation for future `Mapove podklady`.
- Added admin-managed map-layer settings in the `Sprava` area.
- Kept user visibility direction aligned with device permissions and per-layer `map_enabled`.

Changed:
- Added dashboard table model `dashboard.Map_Layers`.
- Added idempotent seed defaults for `budovy`, `mistnosti`, and `vodomery`.
- Added admin FastAPI CRUD endpoints under `/api/v1/admin/map-layers`.
- Added dashboard API client helpers for map-layer administration.
- Added Streamlit admin page `map_layers_admin` at `pages/35_mapove_vrstvy.py`.
- Added configurable metadata to map runtime responses: `layer_kind`, `device_section_key`, `map_enabled`, `default_visible`, `draw_order`, `filter_columns`, `popup_columns`, and `style`.
- Connected existing Vodomery map bundle to enabled layer configs instead of hardcoding every layer directly in the route.
- Updated Leaflet rendering to use configured style, popup columns, and default visibility.

Verified:
- Targeted tests passed: `.venv\Scripts\python.exe -m pytest tests\test_map_layers_service.py tests\test_device_map_service.py tests\test_dashboard_map_shared.py tests\test_dashboard_navigation_config.py -v --tb=short`.
- API app import passed: `.venv\Scripts\python.exe -c "import services.api.main; print('ok')"`.
- Python compile checks passed for changed map/admin modules.
- `git diff --check` reported no whitespace errors, only existing CRLF warnings.

Not verified:
- Full test suite was not run.
- Live admin page interaction in Streamlit was not tested.
- DB bootstrap/seed was not executed manually; it will run through API startup via `ensure_dashboard_tables()`.

Decisions/notes:
- Admins configure layer metadata, not arbitrary SQL.
- Source schema/table/column names are validated through `information_schema`.
- Device layers can be marked `restrict_to_allowed_devices=True` and assigned `device_section_key`, currently seeded for `vodomery`.
- Context layers remain page-gated; device layers remain constrained by assigned devices during feature loading.

Follow-up:
- Add a public/general map API for `Mapove podklady`, separate from `/api/v1/vodomery/map-layers`.
- Add server-side filter request handling for multiselect filters per layer.
- Add a dedicated `Mapove podklady` section and a general `Mapa` page using the layer catalog.

### 2026-06-05

Scope:
- Added the general map API for the future `Mapove podklady` page.
- Added layer catalog and selected-feature loading outside the Vodomery-specific route.
- Added server-side multiselect filter normalization for configured layer filters.

Changed:
- Added `services/api/routes/map.py` with `GET /api/v1/map/layers/catalog` and `POST /api/v1/map/features`.
- Registered the map router in `services/api/main.py`.
- Added map catalog/request schemas in `services/api/schemas/device_map.py`.
- Added dashboard API client helpers `get_map_layer_catalog` and `get_map_features`.
- Added user-level layer availability checks for device layers using `device_section_key`, `restrict_to_allowed_devices`, and assigned devices.
- Added filter support to `load_map_layer_features`; multiple values are loaded with SQL `IN`, multiple filters are combined with `AND`.
- Fixed map-layer seed fallback so disabled DB-configured layers are not reintroduced from defaults.
- Added tests for map route contracts, catalog filtering, device-layer availability, and filter normalization.

Verified:
- Targeted tests passed: `.venv\Scripts\python.exe -m pytest tests\test_map_routes.py tests\test_map_layers_service.py tests\test_device_map_service.py tests\test_dashboard_map_shared.py tests\test_dashboard_navigation_config.py -v --tb=short`.
- Python compile checks passed for changed map/API modules.
- API app import passed: `.venv\Scripts\python.exe -c "import services.api.main; print('ok')"`.
- `git diff --check` reported no whitespace errors, only CRLF warnings.

Not verified:
- Full test suite was not run.
- Live HTTP calls against a running API were not tested.
- DB bootstrap/seed was not executed manually in this step.

Decisions/notes:
- `GET /api/v1/map/layers/catalog` returns only map-enabled layers available to the current authenticated user.
- `POST /api/v1/map/features` accepts per-layer filters; filter keys can use configured source columns or property aliases.
- Unknown filters are rejected server-side instead of silently ignored.
- Device layers remain constrained by assigned devices during feature loading.

Follow-up:
- Build the `Mapove podklady` dashboard section and `Mapa` page against the new catalog/features API.
- Add endpoint or API mode for filter option values, e.g. distinct `budova`, `patro`, `mistnost_id` per layer.
- Replace the Vodomery-specific map page once the general map page is ready.

### 2026-06-05

Scope:
- Added the dashboard entry point for the general map experience.
- Created the `Mapove podklady` section and the configurable `Mapa` page.
- Connected the page to the general map catalog/features API.

Changed:
- Added dashboard section `mapove_podklady` with `requires_device_permissions=False`.
- Added page `mapove_podklady_map` at `pages/36_mapove_podklady.py`.
- Added layer selection UI using the map-layer catalog.
- Added per-layer multiselect filters derived from loaded GeoJSON properties.
- Added final filtered map rendering through the shared Leaflet helper.
- Added shared dashboard map helpers for catalog normalization, feature request creation, and filter option extraction.
- Updated navigation tests and map helper tests.

Verified:
- Targeted tests passed: `.venv\Scripts\python.exe -m pytest tests\test_dashboard_navigation_config.py tests\test_dashboard_map_shared.py tests\test_map_routes.py tests\test_map_layers_service.py -v --tb=short`.
- Python compile checks passed for `pages/36_mapove_podklady.py`, `map_shared.py`, and `navigation_config.py`.
- API app import passed: `.venv\Scripts\python.exe -c "import services.api.main; print('ok')"`.
- `git diff --check` reported no whitespace errors, only CRLF warnings.

Not verified:
- Full test suite was not run.
- Live Streamlit interaction was not tested.
- Live HTTP calls from the page against a running API were not tested.

Decisions/notes:
- The new `Mapove podklady` section does not require device permissions at section level.
- Device-layer availability remains enforced by the general map API and `allowed_devices`.
- Filter options are currently derived from unfiltered selected features; a dedicated distinct-options endpoint remains a follow-up.

Follow-up:
- Add a dedicated filter-options endpoint to avoid loading full unfiltered layers only to populate multiselect values.
- Decide whether to retire or redirect the Vodomery-specific map page after the general map page is validated live.

### 2026-06-05

Scope:
- Removed the obsolete Vodomery-specific map page after the general map page was introduced.
- Adjusted the `Mapove podklady` map layout to prioritize map width and height.

Changed:
- Removed `vodomery_map` from dashboard navigation.
- Removed `pages/34_vodomery_mapa.py`.
- Removed obsolete dashboard API helpers for `/api/v1/vodomery/map-features` and `/api/v1/vodomery/map-layers`.
- Removed obsolete tests for the Vodomery-specific map page and route.
- Narrowed the `Mapove podklady` filter/layer column and widened the map column.
- Increased the rendered map iframe height from 740 px to 900 px and Leaflet map height to 880 px.

Verified:
- Targeted tests passed: `.venv\Scripts\python.exe -m pytest tests\test_dashboard_navigation_config.py tests\test_dashboard_map_shared.py tests\test_map_routes.py tests\test_map_layers_service.py tests\test_device_map_service.py -v --tb=short`.
- Python compile checks passed for the changed dashboard/API map modules.
- API app import passed: `.venv\Scripts\python.exe -c "import services.api.main; print('ok')"`.
- `git diff --check` reported no whitespace errors, only CRLF warnings.

Not verified:
- Full test suite was not run.
- Live Streamlit layout was not checked in a browser.

Decisions/notes:
- Vodomery map display should now go through `Mapove podklady / Mapa`.
- General map API remains the supported path for map layers and filtering.

Follow-up:
- Validate the wider map layout in the running Streamlit UI.

### 2026-06-05

Scope:
- Added server-side distinct filter options for the general `Mapove podklady` map page.
- Removed the need for the page to load full unfiltered GeoJSON layers only to populate multiselects.

Changed:
- Added `POST /api/v1/map/filter-options`.
- Added request/response schemas for map filter options.
- Added service logic for per-layer distinct options with the same access checks as feature loading.
- Added faceted option loading: active filters are applied to other fields while calculating each field's options.
- Added dashboard API/client helpers for filter options.
- Updated `pages/36_mapove_podklady.py` to use the new endpoint before loading filtered map features.
- Added targeted tests for route contracts, service access behavior, and dashboard option normalization.

Verified:
- Python compile passed for the changed map/API/dashboard/test modules.
- Targeted tests passed: `.venv\Scripts\python.exe -m pytest tests\test_map_routes.py tests\test_map_layers_service.py tests\test_dashboard_map_shared.py tests\test_dashboard_navigation_config.py tests\test_device_map_service.py -v --tb=short`.
- API app import passed: `.venv\Scripts\python.exe -c "import services.api.main; print('ok')"`.
- `git diff --check` reported no whitespace errors, only CRLF warnings.

Not verified:
- Full test suite was not run.
- Live Streamlit/browser interaction was not tested.
- Live HTTP calls against a running API were not tested.

Decisions/notes:
- Filter options use catalog filter keys/source columns so the same keys can be sent back in feature filters.
- Device layers remain restricted by assigned devices during both option loading and feature loading.
- No new durable decision was added; this follows DEC-014.

Follow-up:
- Validate the filter UX in the running Streamlit UI with a building/floor/device scenario.

### 2026-06-05

Scope:
- Added photo rendering to map popups for device features.

Changed:
- Updated Leaflet popup HTML generation so `foto` is not rendered as a text table row.
- Added a popup image block for non-empty `properties.foto`.
- Added client-side photo source normalization for URL, relative, Windows drive, and UNC-style paths.
- Added a dashboard map helper test for popup photo rendering.

Verified:
- Python compile passed for `moduly/apps/dashboard/map_shared.py` and `tests/test_dashboard_map_shared.py`.
- Targeted tests passed: `.venv\Scripts\python.exe -m pytest tests\test_dashboard_map_shared.py tests\test_device_map_service.py -v --tb=short`.
- Broader map test set passed: `.venv\Scripts\python.exe -m pytest tests\test_map_routes.py tests\test_map_layers_service.py tests\test_dashboard_map_shared.py tests\test_dashboard_navigation_config.py tests\test_device_map_service.py -v --tb=short`.

Not verified:
- Full test suite was not run.
- Live browser display of local or network photo paths was not tested.

Decisions/notes:
- Empty `foto` values intentionally render nothing.
- If browser security blocks direct local/UNC file paths, add a secured image-serving endpoint or thumbnail proxy in a later step.

Follow-up:
- Validate with real `foto` values in the running Streamlit UI.

### 2026-06-05

Scope:
- Added a secured API image endpoint for map device photos.
- Connected the `Mapove podklady` Leaflet popup to the endpoint.

Changed:
- Added `GET /api/v1/map/images?layer_id=...&identifier=...`.
- Added server-side image resolution for Vodomery device photos from the `foto` detail column.
- Added access checks so image loading respects active map layer availability and assigned device identifiers.
- Added image file validation for supported image suffixes and existing local/UNC-style file paths.
- Added CORS configuration for local dashboard/proxy origins so browser fetch can send `Authorization`.
- Updated popup rendering to fetch images with bearer auth and display blob URLs instead of direct local paths.
- Added tests for image route behavior, service access checks, file validation, and dashboard popup HTML.

Verified:
- Python compile passed for changed API, service, dashboard, and test modules.
- Targeted map test set passed: `.venv\Scripts\python.exe -m pytest tests\test_map_routes.py tests\test_map_layers_service.py tests\test_dashboard_map_shared.py tests\test_dashboard_navigation_config.py tests\test_device_map_service.py -v --tb=short`.
- API app import passed: `.venv\Scripts\python.exe -c "import services.api.main; print('ok')"`.

Not verified:
- Full test suite was not run.
- Live browser loading of real `foto` files was not tested.

Decisions/notes:
- The image endpoint does not accept a file path from the client; it accepts only `layer_id` and `identifier` and resolves the path server-side.
- Default API CORS origins cover local Streamlit `8001` and Caddy/proxy `8080`; override with `API_CORS_ORIGINS` if the dashboard is opened from another origin.

Follow-up:
- Validate with real device photo paths in the running Streamlit UI.

### 2026-06-05

Scope:
- Persisted current map architecture and image proxy context into the project documentation files.

Changed:
- Updated `AGENTS.md` with map API/service/dashboard entry points, map-image safety notes, CORS notes, and the targeted map test command.
- Added `DEC-015` to `DECISIONS.md` for authorized API proxy serving of map device photos.

Verified:
- Documentation files were updated in the working tree.

Not verified:
- No tests were run for documentation-only changes.

Decisions/notes:
- `SESSION_NOTES.md` already contained detailed implementation logs for map layers, filter options, popup photos, and the image endpoint.

Follow-up:
- Use `AGENTS.md`, `DECISIONS.md`, and `SESSION_NOTES.md` as the continuation context in the next session.

### 2026-06-08

Scope:
- Added a monthly consumption report for the JORDAN site.
- Generalized the existing B1 report implementation for reusable site-level meter reports.

Changed:
- Added JORDAN report meters `G_V2`, `Gmt2`, and `G-2.3`.
- Added JORDAN to `monthly_job` and the manual scheduler run registry.
- Added `MONTHLY_JORDAN_CONSUMPTION_REPORT_RECIPIENTS` to `.env.example`.
- Added shared PostgreSQL loaders for water and calorimeter cumulative states and the existing MSSQL electricity total loader.

Verified:
- Targeted report, recipient configuration, and scheduler tests passed.
- Python compile checks passed for the changed report and scheduler modules.
- Read-only dry run for May 2026 found usable start and end states for all three JORDAN meters without printing measurement values or sending email.

Not verified:
- No real email was sent.
- The full test suite was not run.

Decisions/notes:
- Site-level monthly reports use a shared report specification instead of duplicating period, SQL, HTML, and delivery logic.
- The user confirmed that calorimeter `Gmt2` should be displayed in `kWh`.
- Recipient keys are `MONTHLY_B1_CONSUMPTION_REPORT_RECIPIENTS` and `MONTHLY_JORDAN_CONSUMPTION_REPORT_RECIPIENTS` because both reports combine multiple meter domains.

Follow-up:
- None for the JORDAN report.

### 2026-06-09

Scope:
- Investigated stale-looking data on the Streamlit page `Přehled větve`.
- Corrected scheduler-aligned refresh and current-hour chart timestamps.
- Added the cumulative chart Y-axis label while preserving X-axis alignment between both branch graphs.
- Restored authorized Vodoměry photo loading on `Mapové podklady`.

Changed:
- Dashboard refresh now derives the exact `quarter_hour_job` run minutes and refreshes at `:06`, `:17`, `:36`, and `:48`.
- Current incomplete hourly buckets are plotted at the latest actual measurement timestamp.
- The upper cumulative graph uses the Y-axis label `Spotřeba [m³]`.
- The map image resolver translates stored `P:\...` paths to the `\\SERVER1A\Company\...` fallback.
- Vodoměry GeoJSON exposes `has_photo` instead of the raw `foto` path.
- Added and updated targeted tests for refresh timing, chart timestamp alignment, map rendering, and image resolution.

Verified:
- Scheduler and import metrics showed a successful water import on 2026-06-09 and current source measurements.
- Refresh, timestamp helper, and related service tests: 14 passed.
- Related dashboard tests: 24 passed.
- Targeted map tests: 64 passed.
- Read-only map diagnostic returned 59 Vodoměry features, 4 with photos, all 4 resolvable, and no raw photo paths exposed.
- Python compile checks and `git diff --check` passed; only existing line-ending warnings were reported.

Not verified:
- The full pytest suite was not run.
- Live browser rendering after a FastAPI process restart was not verified.

Decisions/notes:
- Dashboard refreshes must follow exact central scheduler slots rather than assume regular quarter-hour spacing.
- Mapped drives are not reliable for service processes; device photo paths are translated server-side.
- Map clients receive photo availability only and load image bytes through the authenticated API endpoint.

Follow-up:
- Restart or reload FastAPI if required, then validate the photo popup in the running `Mapové podklady` page.

### 2026-06-09

Scope:
- Diagnosed the failed map photo load for device `F_V1`.
- Corrected browser routing for authenticated map image requests.

Changed:
- Caddy now routes `/api/*` to FastAPI and all other requests to Streamlit.
- Map image requests default to same-origin `/api/v1/map/images` instead of the server-internal `127.0.0.1:8000` URL.
- Added `DASHBOARD_BROWSER_API_BASE_URL` as an optional override for deployments without same-origin API routing.
- Reloaded the running Caddy configuration.

Verified:
- Server-side resolution for `F_V1` found an existing JPEG.
- Authenticated live request through Caddy returned HTTP 200, `image/jpeg`, and a valid JPEG signature.
- Targeted map tests passed: 44 passed.
- Python compile checks and Caddy validation passed.

Not verified:
- The popup was not clicked in a real remote browser after the change.
- The full pytest suite was not run.

Decisions/notes:
- Same-origin proxying avoids remote-browser localhost failures and removes CORS from the normal Caddy deployment path.

Follow-up:
- Refresh the `Mapove podklady / Mapa` page so Streamlit renders the updated map HTML.

### 2026-06-09

Scope:
- Added a monthly consumption report for water meter `B1_V1`.
- Added Czech business-day scheduling and exact intraday report boundaries.

Changed:
- Added `monthly_b1_v1_consumption_report_job`, scheduled at 13:03 near month end and guarded to run only on the last Czech business day.
- The report interval starts at 13:15 on the previous month's last Czech business day and ends at 13:00 on the current month's last Czech business day.
- The scheduled job refreshes water-meter data before calculating the report.
- Added `MONTHLY_B1_V1_CONSUMPTION_REPORT_RECIPIENTS` with fallback to the existing B1 monthly report recipients.
- Added Czech fixed and Easter holiday handling.

Verified:
- Report, recipient, and scheduler tests passed: 57 tests.
- Read-only dry run for the latest completed interval found start, end, and consumption values for `B1_V1`.
- Effective recipients are configured through the B1 fallback without printing addresses.
- Python compile checks and `git diff --check` passed; only line-ending warnings were reported.

Not verified:
- No email was sent.
- The full test suite was not run.

Decisions/notes:
- Measurements within the requested boundary minute can contain non-zero seconds, so internal cutoffs use the end of the `13:15` and `13:00` minutes while email labels retain the requested minute values.

Follow-up:
- Restart the scheduler process so it loads the new job definition.

### 2026-06-09

Scope:
- Improved photo viewing and usable map space on `Mapove podklady / Mapa`.

Changed:
- Clicking a device photo opens a large lightbox over the map.
- The lightbox can be closed by button, backdrop click, or Escape and offers opening the photo in a new browser tab.
- Removed the page title, explanatory caption, `Vrstvy` heading, and the three map metrics.
- The map now starts at the top of the page beside the layer and filter controls.

Verified:
- Python compile checks passed for the changed dashboard map modules.
- Targeted map and navigation tests passed: 68 map tests after the photo lightbox change and 32 dashboard map/navigation tests after the layout change.
- `git diff --check` reported no whitespace errors, only line-ending warnings.
- The installed Streamlit iframe configuration includes popup permission needed for opening the photo in a new tab.

Not verified:
- Live browser interaction and final visual layout were not tested.
- The full pytest suite was not run.

Decisions/notes:
- Authorized image loading remains unchanged and continues to use the existing FastAPI image proxy and temporary browser blob URLs.
- No durable architectural decision was added.

Follow-up:
- Candidate space improvements are a map fullscreen control, a collapsible layer/filter panel, and viewport-based map height.

### 2026-06-09

Scope:
- Added the mobile optimization pilot for `Overview`, `Vodomery / Prehled`, and `Mapove podklady / Mapa`.
- Added optional display of the phone position in the Leaflet map.

Changed:
- Added shared responsive styles with a `720px` mobile breakpoint.
- Pilot page columns stack on mobile while KPI groups use two columns.
- Overview weather cards and dense headers adapt to narrow screens.
- The mobile map is displayed before its Streamlit filter panel and Leaflet controls use mobile sizing.
- Added a mobile-only `Moje poloha` map control with accuracy circle and permission/error feedback.
- Device location remains browser-only and is not sent to the API.

Verified:
- Python compile checks passed for all changed dashboard modules.
- Responsive, map, navigation, overview, and Vodomery targeted tests passed.
- Full targeted map suite passed: 71 tests.
- Generated map JavaScript passed Chromium syntax validation.
- `git diff --check` reported no whitespace errors, only existing line-ending warnings.

Not verified:
- Live interaction on a physical phone was not tested.
- Geolocation was not tested through a deployed trusted HTTPS origin.
- The full pytest suite was not run.

Decisions/notes:
- Mobile and desktop use the same Streamlit pages; layout changes are CSS responsive rules, not separate page implementations.
- Remote mobile browser geolocation requires HTTPS. The current plain HTTP `:8080` Caddy listener will show an explanatory error instead of requesting location.

Follow-up:
- Configure a trusted HTTPS dashboard origin before validating phone geolocation in production.

### 2026-06-09

Scope:
- Changed the mobile layout order on `Mapove podklady / Mapa`.

Changed:
- The layer selection and layer filters now render above the map on screens up to the shared `720px` breakpoint.
- Removed the obsolete note that said the map was displayed above the filter panel.
- Added a regression test for the mobile column order.

Verified:
- Python compile checks passed for the changed map page and its layout test.
- Targeted responsive, map, and navigation tests passed: 36 tests.
- `git diff --check` reported no whitespace errors, only the existing line-ending warning.

Not verified:
- Live rendering on a physical phone was not tested.
- The full pytest suite was not run.

Decisions/notes:
- Desktop map layout remains unchanged.
- No durable architectural decision was added.

Follow-up:
- None.

### 2026-06-10

Scope:
- Diagnosed mobile geolocation failure on `Mapove podklady / Mapa`.
- Added an HTTPS dashboard entry point required by mobile browser geolocation.

Changed:
- Caddy now serves the dashboard and `/api/*` on HTTPS for `server2a.armex.local`, `server2a`, and `192.168.3.250`.
- HTTPS certificates are issued by the local Caddy CA.
- The public local CA certificate is downloadable from `http://server2a:8080/caddy-local-root.crt`.
- Added a Domain/Private Windows Firewall rule for inbound TCP 443.
- Added a regression test for the HTTPS and CA-download Caddy configuration.

Verified:
- Streamlit 1.57 already delegates `geolocation` to its HTML iframe.
- Caddy validation and reload passed.
- HTTPS dashboard requests through the local proxy returned HTTP 200.
- The CA download returned the expected X.509 certificate response.
- The targeted responsive and map tests passed.

Not verified:
- The CA certificate was not installed and trusted on a physical phone.
- Live geolocation was not tested on a physical phone.
- The full pytest suite was not run.

Decisions/notes:
- Plain LAN HTTP cannot provide browser geolocation; the phone must use the trusted URL `https://server2a.armex.local`.
- Trusting the local Caddy CA is a one-time device setup and does not expose the CA private key.

Follow-up:
- Install and trust `monitoring-dashboard-local-ca.crt` on each phone that needs dashboard geolocation.

### 2026-06-10

Scope:
- Diagnosed failed HTTPS and local CA download URLs.
- Corrected the dashboard HTTPS endpoint to the actual server identity.

Changed:
- Caddy now serves HTTPS for `server4a.armex.local`, `server4a`, and `192.168.3.249`.
- The local CA is available as both `/caddy-local-root.crt` and `/caddy-local-port.crt`.
- The CA download is also exposed over HTTPS on port 443.

Verified:
- The machine identity is `SERVER4A`; `server2a.armex.local` resolves to the unavailable address `192.168.3.250`.
- Caddy validation and reload passed.
- Dashboard and CA download requests returned HTTP 200 through `192.168.3.249`.
- The targeted Caddy configuration test passed.

Not verified:
- Access from a physical phone was not tested.
- TCP 8080 could not be added to Windows Firewall because the current process lacks administrator rights.

Decisions/notes:
- Use `https://192.168.3.249` as the reliable LAN dashboard URL.
- The CA can be downloaded through `https://192.168.3.249/caddy-local-root.crt` after bypassing the initial trust warning.

Follow-up:
- An administrator can allow inbound TCP 8080 if plain-HTTP CA download is still required.

### 2026-06-10 - Restart handoff

Current state:
- The machine is `SERVER4A`, with the monitoring LAN address `192.168.3.249`.
- `server2a.armex.local` incorrectly targets `192.168.3.250` and must not be used for this dashboard.
- Caddy is configured for `server4a.armex.local`, `server4a`, and `192.168.3.249`.
- Caddy was validated and reloaded before the restart.

Verified URLs:
- Dashboard: `https://192.168.3.249`
- Dashboard by name: `https://server4a.armex.local`
- CA download: `https://192.168.3.249/caddy-local-root.crt`
- Compatible CA alias: `https://192.168.3.249/caddy-local-port.crt`
- All URLs returned HTTP 200 locally; TLS verification passed against the Caddy root CA with Windows revocation checking disabled.

Pending after restart:
- Confirm Caddy, FastAPI on `127.0.0.1:8000`, and Streamlit on `127.0.0.1:8001` started.
- Test the dashboard and CA download from the phone.
- Install and trust the downloaded local CA on the phone.
- If plain HTTP download on `http://192.168.3.249:8080/...` is required, create an inbound TCP 8080 firewall rule from an elevated administrator session. The previous attempt failed with Windows error 5 (access denied).

Working tree warning:
- Existing user/runtime changes remain present. Do not revert them.
- Relevant work from this session is in `Caddyfile`, `tests/test_caddy_config.py`, and `SESSION_NOTES.md`.

### 2026-06-10

Scope:
- Added `armex.monitoring` as the preferred HTTPS dashboard hostname.

Changed:
- Added `armex.monitoring` to the Caddy HTTPS site while retaining the existing server-name and IP aliases.
- Updated the Caddy configuration regression test.

Verified:
- Caddy validation and reload passed.
- The targeted Caddy configuration test passed.
- A local HTTPS request for `https://armex.monitoring` returned HTTP 200 with the Caddy root CA.

Not verified:
- `armex.monitoring` does not yet resolve through network DNS.
- Access from another device was not tested.

Decisions/notes:
- Network DNS must map `armex.monitoring` to `192.168.3.249` before other devices can use the new name.
- The internal DNS server is `192.168.3.252` (`server1a.armex.local`); it serves `armex.local`, but no `monitoring` zone currently exists.
- The exact hostname requires a `monitoring` DNS zone with an `armex` A record targeting `192.168.3.249`.
- `main.py` is unrelated to the dashboard hostname and was not changed.

### 2026-06-10

Scope:
- Prepared a step-by-step plan for publishing the dashboard to the public internet over HTTPS.

Changed:
- Added `PUBLIC_HTTPS_DEPLOYMENT.md` with preparation, security, DNS, router, Caddy, verification, rollback, and HTTP shutdown checklists.

Verified:
- The plan reflects the current public IP `77.95.46.168`, internet-facing server address `192.168.2.249`, and localhost-only FastAPI/Streamlit listeners.

Not verified:
- No production DNS, router, firewall, or public Caddy changes were made.

Decisions/notes:
- Tailscale remains the service and rollback access during public HTTPS deployment.
- Public port `8080` must remain only temporarily and be removed after successful HTTPS verification.

### 2026-06-11

Scope:
- Separated Caddy startup from the FastAPI, Streamlit, and scheduler launcher.
- Added the public HTTPS dashboard hostname.

Changed:
- `start_api_dashboard.bat` no longer contains or invokes the Caddy startup branch.
- The launcher now exits after starting Streamlit instead of falling through into a second API invocation.
- Replaced the old LAN/internal-CA Caddy configuration with the single public hostname `monitoring.armexholding.cz`.
- The public site routes `/api/*` to FastAPI and remaining requests to Streamlit.

Verified:
- Added a Caddy configuration regression test for the public hostname and separate API/Streamlit routing.
- Caddy configuration validation passed.
- Local TLS verification for `monitoring.armexholding.cz` returned HTTP 200 for the dashboard.
- Public DNS resolves `monitoring.armexholding.cz` to `77.95.46.168`.

Not verified:
- HTTPS access through the public IP from an external network was not tested; the same-server public-IP request timed out, consistent with unavailable NAT loopback.
- The live Caddy process did not accept the updated configuration because its admin API reload remained blocked and timed out.
- The live `/api/v1/map/layers/catalog` request still returns Streamlit HTTP 200 HTML instead of FastAPI authentication JSON.

Decisions/notes:
- Caddy is now an independently managed runtime process.
- The public dashboard URL is `https://monitoring.armexholding.cz`.
- The independently managed Caddy process must be restarted or successfully reloaded with the project `Caddyfile` before same-origin map API calls work through the public domain.

### 2026-06-11

Scope:
- Moved Caddy runtime ownership back into `start_api_dashboard.bat`.
- Adopted the Caddy installation and runtime configuration under `C:\Program Files\Caddy`.

Changed:
- Added explicit `CADDY_DIR`, `CADDY_EXE`, and `CADDY_CONFIG` paths to the launcher.
- Added preflight checks for the Caddy executable and configuration.
- Added a Streamlit `/_stcore/health` readiness check before Caddy startup.
- Added Caddy configuration validation before both first start and reload.
- Existing Caddy processes are reloaded through `127.0.0.1:2019`; otherwise Caddy runs in the foreground of its launcher window.
- Synchronized the deployed `C:\Program Files\Caddy\Caddyfile` with the tracked project configuration.
- The deployed proxy routes `/api/*` to FastAPI on port `8000` and all remaining traffic to Streamlit on port `8001`.

Verified:
- Caddy 2.11.4 was found at `C:\Program Files\Caddy\caddy.exe`.
- Project and deployed Caddyfile SHA-256 hashes matched after synchronization.
- Runtime Caddy configuration validation passed.
- Caddy was stopped and restarted through `start_api_dashboard.bat caddy`.
- The running command line uses `run --config "C:\Program Files\Caddy\Caddyfile" --adapter caddyfile`.
- Ports 80, 443, and 2019 are owned by the new Caddy process.
- Local TLS checks returned dashboard HTTP 200, unauthenticated API HTTP 401 JSON, and HTTP-to-HTTPS redirect 308.
- Re-running `start_api_dashboard.bat caddy` completed a successful reload without starting a second Caddy process.
- Targeted Caddy configuration and launcher tests passed.

Not verified:
- The complete launcher was not run because FastAPI, Streamlit, and the scheduler were already active and a full run would start duplicate application processes.
- External access from a separate internet connection was not tested.

Decisions/notes:
- DEC-018 supersedes the earlier independent-Caddy decision DEC-017.
- The root `Caddyfile` is the tracked mirror; the launcher reads the deployed copy under `C:\Program Files\Caddy`.

### 2026-06-11 - Restart handoff

Current state before workstation restart:
- `start_api_dashboard.bat` starts FastAPI, scheduler, Streamlit, and then Caddy.
- FastAPI must pass `http://127.0.0.1:8000/health/live`.
- Streamlit must pass `http://127.0.0.1:8001/_stcore/health`.
- Caddy runs from `C:\Program Files\Caddy\caddy.exe`.
- Caddy loads `C:\Program Files\Caddy\Caddyfile`.
- The deployed and tracked project Caddyfile SHA-256 hashes matched before restart.
- Caddy routes `/api/*` to FastAPI on `127.0.0.1:8000` and remaining traffic to Streamlit on `127.0.0.1:8001`.

Expected processes and listeners after restart:
- FastAPI/Uvicorn on `127.0.0.1:8000`.
- Streamlit on `127.0.0.1:8001`.
- Scheduler running `main.py`.
- Caddy from `C:\Program Files\Caddy\caddy.exe` on TCP 80 and 443 with admin endpoint `127.0.0.1:2019`.

Checks for the next session:
- Confirm the four runtime processes started without duplicate instances.
- Confirm `http://127.0.0.1:8000/health/live` returns HTTP 200.
- Confirm `http://127.0.0.1:8001/_stcore/health` returns HTTP 200.
- Confirm `http://monitoring.armexholding.cz` redirects to HTTPS.
- Confirm `https://monitoring.armexholding.cz` returns the Streamlit dashboard.
- Confirm unauthenticated `https://monitoring.armexholding.cz/api/v1/map/layers/catalog` returns FastAPI HTTP 401 JSON rather than Streamlit HTML.
- Confirm Caddy command line uses `run --config "C:\Program Files\Caddy\Caddyfile" --adapter caddyfile`.

Last verified before restart:
- Dashboard HTTPS returned HTTP 200.
- Unauthenticated map API returned HTTP 401 with `application/json`.
- HTTP returned redirect 308 to HTTPS.
- Re-running `start_api_dashboard.bat caddy` successfully reloaded the existing Caddy process.
- Targeted tests passed: `tests/test_caddy_config.py` with 2 tests.

Working tree warning:
- Existing user/runtime changes remain present and must not be reverted.
- Relevant restart work is in `start_api_dashboard.bat`, `Caddyfile`, `tests/test_caddy_config.py`, `AGENTS.md`, `DECISIONS.md`, `PUBLIC_HTTPS_DEPLOYMENT.md`, and `SESSION_NOTES.md`.

### 2026-06-11 - Post-restart runtime verification

Scope:
- Verified the complete runtime after the workstation restart.
- Confirmed the supported public access policy.

Changed:
- Updated persistent context to state that `https://monitoring.armexholding.cz` is the only supported public client entry point.
- Recorded that direct client access through the public IP address is not required or supported.

Verified:
- FastAPI live and ready endpoints on `127.0.0.1:8000` returned HTTP 200.
- Streamlit health on `127.0.0.1:8001` returned HTTP 200.
- The scheduler held its process lock, refreshed its heartbeat, and completed the 2026-06-11 14:16 quarter-hour job successfully.
- The water, gas, and pressure imports executed by that job completed successfully.
- Exactly one persistent Caddy process was running.
- Caddy owned TCP ports 80 and 443 and its admin endpoint on `127.0.0.1:2019`.
- The tracked and deployed Caddyfile SHA-256 hashes matched and the deployed configuration validated successfully.
- HTTP for `monitoring.armexholding.cz` redirected to HTTPS with status 308.
- HTTPS returned the Streamlit dashboard with status 200.
- An unauthenticated `/api/*` request returned FastAPI HTTP 401 JSON rather than Streamlit HTML.
- The served certificate used TLS 1.3, matched `monitoring.armexholding.cz`, had a valid Let's Encrypt chain, and was valid from 2026-06-11 through 2026-09-09.

Not verified:
- Direct access through the public IP address was not treated as a required check.
- External access from a separate internet connection was not tested during this session.

Decisions/notes:
- All public client connections use `https://monitoring.armexholding.cz`.
- DNS still maps the hostname to the public endpoint, but clients do not connect using the IP address as the URL.
- `main.py` remains the scheduler entry point and requires no change for public HTTPS routing.

### 2026-06-11 - Persistent login and dashboard-wide mobile layout

Scope:
- Fixed dashboard logout after a browser reload.
- Extended the existing mobile dashboard behavior from the three-page pilot to all active Streamlit pages.
- Added hot-reload handling for shared authentication and responsive modules in the common dashboard entry point.

Changed:
- Added the shared browser session cookie name in `app/dashboard_session.py`.
- Added FastAPI browser-session endpoints for setting and deleting the authenticated HttpOnly cookie.
- Added HTTP status metadata to `DashboardApiError` so Streamlit can distinguish invalid authentication from temporary API outages.
- Added Streamlit authentication restore, cookie synchronization, logout cleanup, and invalid-token cleanup.
- Applied shared responsive styles globally from `moduly/apps/dashboard/login.py`.
- Expanded responsive CSS for mobile columns, metric grids, tables, charts, images, tabs, forms, dialogs, sidebars, and full-width touch actions.
- Removed duplicate responsive style calls from `Overview`, `Vodomery / Prehled`, and `Mapove podklady / Mapa`.
- Added authentication-route, authentication-state, and responsive-layout regression tests.

Verified:
- Dashboard authentication and navigation tests passed: 29 tests.
- Dashboard-focused tests passed: 105 tests.
- Final targeted responsive, map-layout, and navigation tests passed: 26 tests.
- Python compilation passed for the dashboard package and changed authentication modules.
- Live Streamlit login rendered without `ImportError`.
- Headless Chromium at a `390x844` viewport confirmed mobile page padding, full-width login action, stacked content columns, two-column metric rows, and no JavaScript errors.
- Local FastAPI and Streamlit health endpoints returned HTTP 200.
- Browser-session deletion returned HTTP 204 with `Secure`, `HttpOnly`, and `SameSite=Lax` cookie attributes when `X-Forwarded-Proto` was HTTPS.
- The complete test suite result was 422 passed and 2 failed.

Not verified:
- Authenticated navigation through every dashboard page was not exercised manually on a physical phone.
- External HTTPS access from a separate network was not retested during this work.

Known unrelated test failures:
- `tests/test_vodomery_reports.py::test_build_consumption_curve_day_aggregates_water_measurements`
- `tests/test_vodomery_reports.py::test_build_vodomery_report_html_contains_expected_sections`
- Both failures reproduce when `tests/test_vodomery_reports.py` is run alone and are outside the authentication and responsive-layout changes.

Decisions/notes:
- DEC-020 records persistent dashboard login behavior.
- DEC-021 expands DEC-016 from the mobile pilot to the complete active Streamlit dashboard.
- `main.py` remains only the scheduler entry point and was not changed.

### 2026-06-11 - Dashboard security remediation P0.1

Scope:
- Started the dashboard security checklist with API token signing-key rotation.
- Removed the known development signing secret from tracked runtime launchers.

Changed:
- `start_api_dashboard.bat` now loads `API_TOKEN_SECRET` through application configuration.
- Removed the same fixed secret from `start_api_dashboard - kopie.bat`, `scripts/start_all_services.ps1`, and `run.txt`.
- Generated a new 384-bit random secret in the ignored local `.env`.
- Added `tests/test_dashboard_security_config.py`.
- Added `DASHBOARD_SECURITY_CHECKLIST.md` progress and DEC-022.

Verified:
- The old known signing secret produced a token accepted by the currently running API before rotation.
- A temporary loopback-only FastAPI instance loaded the new `.env` secret and accepted a newly signed token.
- The temporary API instance was stopped and port `18000` was released.
- Security, Caddy, browser-session, auth-state, auth-service, and navigation targeted tests passed: 36 tests.

Not verified:
- The running API on port `8000` could not be restarted because Windows denied terminating its privileged process tree.
- The live API therefore still uses the old signing secret until restarted from its original administrative context or after a workstation restart.
- Live rejection of an old-secret token remains pending after that restart.

Decisions/notes:
- API signing secrets must remain outside version control and must not be assigned by tracked launchers.
- `main.py`, Streamlit, scheduler, and Caddy were not restarted or changed by this step.

Follow-up:
- Restart FastAPI or the workstation, then verify health, a new token, and HTTP 401 for an old-secret token.

### 2026-06-11 - Security P0.1 restart handoff

Current state before workstation restart:
- The tracked launchers no longer assign `API_TOKEN_SECRET`.
- The previous known development secret is absent from tracked runtime files.
- A new 384-bit random `API_TOKEN_SECRET` is stored in the ignored local `.env`; its value was not printed or added to tracked documentation.
- A temporary FastAPI instance on `127.0.0.1:18000` successfully loaded the new secret and validated a newly signed token.
- The temporary instance was stopped and port `18000` was released.
- The existing privileged FastAPI process on `127.0.0.1:8000` could not be terminated from the current session.
- Immediately before restart, the live API and Streamlit health endpoints returned HTTP 200.
- Immediately before restart, the live API still accepted a token signed with the old known secret.

Expected state after restart:
- `start_api_dashboard.bat` starts FastAPI without assigning a secret in the launcher.
- FastAPI loads `API_TOKEN_SECRET` from the ignored local `.env`.
- Tokens signed with the old known secret fail signature validation with HTTP 401.
- Users must log in again because existing browser bearer tokens were signed with the previous secret.

Required post-restart checks:
- Confirm FastAPI health at `http://127.0.0.1:8000/health/live`.
- Confirm Streamlit health at `http://127.0.0.1:8001/_stcore/health`.
- Confirm public HTTPS dashboard access at `https://monitoring.armexholding.cz`.
- Confirm a fresh dashboard login succeeds and persists across a browser reload.
- Confirm an old-secret test token returns HTTP 401 from `/api/v1/auth/me`.
- Update `DASHBOARD_SECURITY_CHECKLIST.md` P0.1 restart and old-token verification items to completed.

Verification already completed:
- Targeted security, Caddy, browser-session, auth-state, auth-service, and navigation tests: 36 passed.
- `git diff --check` reported no whitespace errors.

Files changed for security P0.1:
- `start_api_dashboard.bat`
- `start_api_dashboard - kopie.bat`
- `scripts/start_all_services.ps1`
- `run.txt`
- `tests/test_dashboard_security_config.py`
- `DASHBOARD_SECURITY_CHECKLIST.md`
- `PUBLIC_HTTPS_DEPLOYMENT.md`
- `DECISIONS.md`
- `SESSION_NOTES.md`

### 2026-06-12 - Security P0.1 post-restart completion

Scope:
- Verified the complete runtime after restart.
- Completed the API signing-key rotation checks.

Changed:
- Marked the remaining P0.1 checklist items as completed.

Verified:
- FastAPI live and ready endpoints returned HTTP 200.
- Streamlit health returned HTTP 200.
- A token issued with the current `.env` secret returned HTTP 200 from `/api/v1/auth/me`.
- A token signed with the previous known secret returned HTTP 401 because its signature did not match.
- Caddy returned the Streamlit dashboard over local public-hostname TLS and routed protected `/api/*` traffic to FastAPI.
- The scheduler process lock was held, its heartbeat was current, and the 2026-06-12 06:35 quarter-hour job completed successfully with no new scheduler errors after restart.

Not verified:
- Public HTTPS was not tested from a separate external network because this server does not have NAT loopback.
- A credential-based browser login was not automated because no user password was read or requested.

Decisions/notes:
- P0.1 is complete.
- P0.2 must not apply HTTP Basic Auth to all `/api/*` requests because FastAPI uses the same `Authorization` header for bearer tokens.

### 2026-06-12 - Dashboard security remediation P0.2

Scope:
- Added a temporary second authentication gate at Caddy.
- Restricted unrestricted access to Streamlit and the public login endpoint.

Changed:
- Added scoped Caddy Basic Auth for all non-`/api/*` paths and
  `/api/v1/auth/login`.
- Added local Caddy auth env loading to `start_api_dashboard.bat`.
- Added `scripts/deploy_caddy_runtime.ps1` with validation, timestamped backup,
  reload, and automatic rollback on deployment failure.
- Added Caddy and launcher regression checks.
- Documented credentials, deployment, emergency access, and rollback.
- Added DEC-023.

Runtime state:
- Caddy username and bcrypt hash are stored outside Git in
  `C:\ProgramData\monitorovaci_platforma\caddy-dashboard-auth.env`.
- The plaintext credential handoff is stored in
  `C:\ProgramData\monitorovaci_platforma\dashboard-proxy-credentials.txt`.
- Both files and their parent directory allow access only to the operating
  account, Administrators, and SYSTEM.
- The credential value was not printed in command output or documentation.

Verified:
- Project and deployed Caddyfile SHA-256 hashes match.
- The deployed configuration validates with the local auth env file.
- Caddy reloaded successfully and remained a single process on ports 80, 443,
  and the loopback admin endpoint 2019.
- Dashboard requests without credentials and with invalid credentials returned
  HTTP 401.
- A dashboard request with valid credentials returned HTTP 200 HTML.
- `/api/v1/auth/login` without gate credentials returned HTTP 401.
- A gated login request reached FastAPI and returned HTTP 422 JSON for an empty
  test payload.
- An unauthenticated protected Bearer API route remained FastAPI HTTP 401 JSON.
- FastAPI live/ready and Streamlit health endpoints remained HTTP 200.

Not verified:
- Access was not tested from a separate external network.
- Browser credential prompting and WebSocket behavior were not exercised
  manually in a graphical browser.

Decisions/notes:
- P0.2 uses the additional reverse-proxy authentication option.
- Tailscale remains the emergency access path.
- Remove the temporary gate only after P1 login throttling is complete.

### 2026-06-12 - Security P0 restart handoff

Current state before workstation restart:
- Security checklist items P0.1 and P0.2 are completed.
- FastAPI uses the rotated `API_TOKEN_SECRET` from the ignored local `.env`.
- Tokens signed with the previous development secret are rejected with HTTP 401.
- Caddy requires temporary shared authentication for the Streamlit surface and
  `/api/v1/auth/login`.
- Other `/api/*` routes remain under FastAPI Bearer authentication and are not
  placed behind the Caddy Basic Auth gate.
- The tracked and deployed Caddyfile SHA-256 hashes match.
- At 2026-06-12 08:27 CEST, the scheduler heartbeat was current, the latest
  quarter-hour status was `success`, and the next run was scheduled for 08:35.

Sensitive local runtime files:
- `C:\ProgramData\monitorovaci_platforma\caddy-dashboard-auth.env` contains the
  Caddy username and bcrypt hash.
- `C:\ProgramData\monitorovaci_platforma\dashboard-proxy-credentials.txt`
  contains the plaintext operational credential handoff.
- Do not print, commit, move, or delete these files.
- Their ACL permits only the operating account, Administrators, and SYSTEM.

Expected startup behavior:
- `start_api_dashboard.bat` starts FastAPI, scheduler, and Streamlit.
- After both health checks pass, it starts or reloads Caddy.
- The launcher reads the Caddy gate settings from
  `C:\ProgramData\monitorovaci_platforma\caddy-dashboard-auth.env`.
- Missing or incomplete Caddy auth settings must stop Caddy startup rather than
  expose the dashboard without the temporary gate.

Required post-restart checks:
- Confirm one FastAPI/Uvicorn listener on `127.0.0.1:8000`.
- Confirm one Streamlit listener on `127.0.0.1:8001`.
- Confirm one scheduler instance holds the `scheduler_process` lock and has a
  current heartbeat.
- Confirm one Caddy process owns TCP 80, 443, and loopback admin port 2019.
- Confirm FastAPI `/health/live` and `/health/ready` return HTTP 200.
- Confirm Streamlit `/_stcore/health` returns HTTP 200.
- Confirm tracked and deployed Caddyfile hashes still match.
- Confirm HTTP redirects to HTTPS with status 308.
- Confirm HTTPS dashboard access without gate credentials returns HTTP 401 with
  a Basic authentication challenge.
- Confirm valid gate credentials return the Streamlit dashboard with HTTP 200.
- Confirm `/api/v1/auth/login` without gate credentials returns HTTP 401.
- Confirm valid gate credentials allow the login request to reach FastAPI.
- Confirm an unauthenticated protected non-login `/api/*` route returns FastAPI
  HTTP 401 JSON, not a Caddy Basic Auth response or Streamlit HTML.

Verification completed before restart:
- Targeted Caddy, security, authentication, and navigation suite: 37 passed.
- FastAPI live/ready and Streamlit health endpoints returned HTTP 200.
- Caddy configuration validation and reload passed.
- Live gate checks passed for missing, invalid, and valid credentials.
- `git diff --check` reported no whitespace errors.

Working tree at handoff:
- Security work remains uncommitted in `AGENTS.md`, `Caddyfile`,
  `DASHBOARD_SECURITY_CHECKLIST.md`, `DECISIONS.md`,
  `PUBLIC_HTTPS_DEPLOYMENT.md`, `SESSION_NOTES.md`,
  `start_api_dashboard.bat`, `tests/test_caddy_config.py`,
  `tests/test_dashboard_security_config.py`, and
  `scripts/deploy_caddy_runtime.ps1`.
- `data/smartfuelpass/session_cookies.json` is a separate sensitive runtime
  change and must not be inspected, reverted, or included with security work
  without explicit approval.

Next security step:
- Continue with P1.3, login throttling and abuse protection.
- Preserve the temporary Caddy gate until application-level throttling is
  implemented and verified.

### 2026-06-12 - Application login throttling and Caddy gate removal

Scope:
- Restored the standard Streamlit login flow without a browser Basic Auth
  prompt.
- Replaced the temporary Caddy gate with FastAPI login throttling.

Changed:
- Added process-local login limits by normalized account and trusted client IP.
- Added increasing temporary account lockouts and a bounded IP lockout.
- Added generic authentication failures and dummy PBKDF2 work for unknown
  accounts.
- Restricted Uvicorn forwarded-header trust to loopback Caddy.
- Removed Caddy gate directives and gate environment loading from the launcher
  and deployment script.
- Added DEC-024 and marked P1.3 complete.

Verified:
- Targeted login, authentication, Caddy, security, responsive-layout, and
  navigation tests: 55 passed.
- Python compilation passed for the changed authentication modules.
- The tracked Caddy configuration validated successfully.
- `git diff --check` reported no whitespace errors.
- The tracked and deployed Caddyfile hashes match after deployment.
- Public HTTPS returns the Streamlit page with HTTP 200 and no Basic Auth
  challenge.
- An empty public login request reaches FastAPI and returns HTTP 422 JSON.
- A validly encoded invalid login returns the generic HTTP 401 response.
- Live attempts 1-4 for a disposable account returned HTTP 401; attempt 5
  returned HTTP 429 with `Retry-After: 30`.
- Protected non-login API routes remain FastAPI HTTP 401 JSON.
- FastAPI live/ready and Streamlit health endpoints remain HTTP 200.

Not verified:
- Credential-based dashboard login was not automated because no dashboard
  password was read or requested.

Decisions/notes:
- DEC-024 supersedes the temporary gate decision DEC-023.
- Retired ProgramData gate credential files remain sensitive and were not
  deleted.

### 2026-06-12 - Windows scheduled startup operating constraint

Scope:
- Recorded how the production runtime starts and how it must currently be
  renewed after operational changes.

Changed:
- Added DEC-025.
- Updated `AGENTS.md`, `PUBLIC_HTTPS_DEPLOYMENT.md`, and
  `DASHBOARD_SECURITY_CHECKLIST.md` with the scheduled-start and recovery
  contract.

Decisions/notes:
- Windows Task Scheduler launches `start_api_dashboard.bat` with the trigger
  `At system startup`.
- FastAPI, Streamlit, the scheduler, and Caddy therefore start without a user
  logging into Windows.
- These processes run in a non-interactive session and their console windows
  cannot be accessed later.
- The current supported way to renew the complete production runtime is to
  restart the whole Windows workstation.
- Future agents must not start a duplicate runtime set manually or assume that
  individual scheduled processes can be safely restarted from an interactive
  session.
- Launcher and startup-argument changes require a workstation restart before
  the scheduled runtime uses them.

### 2026-06-12 - Mandatory restart handoff workflow

Scope:
- Added a mandatory state-preservation workflow before every Windows
  workstation restart.

Changed:
- Added DEC-026.
- Added the `Restart Handoff Template` to `SESSION_NOTES.md`.
- Updated operating instructions, deployment documentation, and the security
  checklist.

Decisions/notes:
- Before every restart, the active conversation/task state and expected
  post-restart process state must be written to `SESSION_NOTES.md`.
- The handoff must include the dirty working tree, runtime deployment state,
  sensitive artifacts, expected processes/listeners, scheduler state, Caddy
  state, exact HTTP expectations, and change-specific verification.
- A restart must not be initiated or requested before the handoff is complete.
- Actual post-restart verification and deviations must be appended afterward.

### 2026-06-12 09:23 CEST - Pre-restart handoff

Reason for restart:
- Renew the complete production runtime through the supported Windows
  Task Scheduler startup path.
- Ensure the scheduled runtime loads the current `start_api_dashboard.bat`,
  including trusted loopback proxy-header arguments, current login throttling,
  and the Caddy configuration without the retired Basic Auth gate.

Current task/conversation state:
- Completed API signing-secret rotation and old-token rejection.
- Removed the temporary Caddy Basic Auth browser prompt.
- Restored the standard Streamlit dashboard login.
- Added application login throttling by normalized account and trusted client
  IP, generic authentication errors, and dummy PBKDF2 verification for unknown
  users.
- Added DEC-024, DEC-025, and DEC-026.
- Documented Windows Task Scheduler startup and the mandatory restart handoff
  workflow.
- Pending: perform all checks below after restart and record actual results.
- First action after restart: read `AGENTS.md`, `DECISIONS.md`, and
  `SESSION_NOTES.md`, run `git status --short`, then execute the post-restart
  checks in this handoff.
- After successful verification, continue the dashboard security checklist;
  the next unfinished authentication item is P1.4 audit logging and alerts.

Working tree and deployment:
- `git status --short` immediately before restart:

```text
 M AGENTS.md
 M Caddyfile
 M DASHBOARD_SECURITY_CHECKLIST.md
 M DECISIONS.md
 M PUBLIC_HTTPS_DEPLOYMENT.md
 M SESSION_NOTES.md
 M data/smartfuelpass/session_cookies.json
 M moduly/apps/dashboard/api_client.py
 M moduly/apps/dashboard/auth.py
 M moduly/apps/dashboard/database/users.py
 M moduly/apps/dashboard/login.py
 M services/api/routes/auth.py
 M start_api_dashboard.bat
 M tests/test_auth_routes.py
 M tests/test_caddy_config.py
 M tests/test_dashboard_auth_service.py
 M tests/test_dashboard_auth_state.py
 M tests/test_dashboard_security_config.py
?? scripts/deploy_caddy_runtime.ps1
?? services/api/core/login_throttle.py
?? tests/test_login_throttle.py
```

- Security/login/runtime changes remain uncommitted.
- `data/smartfuelpass/session_cookies.json` is a separate sensitive runtime
  change. Do not inspect, revert, delete, print, or include it with the
  security work without explicit approval.
- The tracked root `Caddyfile` is deployed to
  `C:\Program Files\Caddy\Caddyfile`.
- Tracked and deployed Caddyfile SHA-256 before restart:
  `F41D3B31EA03308CB4345B1D11F0488B11D1FE527CBF135B0E1E166E5E7BC9BE`.
- The deployed Caddy configuration validated successfully before restart.
- Targeted login, authentication, Caddy, security, responsive-layout, and
  navigation tests passed: 55 tests.
- `git diff --check` reported no whitespace errors.

Sensitive/runtime artifacts:
- Do not print, change, delete, or commit the ignored local `.env` containing
  `API_TOKEN_SECRET`.
- Do not print, change, delete, or commit
  `data/smartfuelpass/session_cookies.json`.
- The retired files
  `C:\ProgramData\monitorovaci_platforma\caddy-dashboard-auth.env` and
  `C:\ProgramData\monitorovaci_platforma\dashboard-proxy-credentials.txt`
  remain sensitive even though Caddy no longer uses them.
- Do not print bearer tokens, passwords, cookie values, or raw operational
  data during verification.

Windows scheduled startup expectation:
- Scheduled task name: `API_dashboard_caddy`.
- Executable:
  `C:\Users\tra\PycharmProjects\monitorovaci_platforma\start_api_dashboard.bat`.
- Trigger: Windows boot (`MSFT_TaskBootTrigger`, `At system startup`).
- Principal: user `tra`, password logon type, highest run level.
- The task starts the runtime without an interactive Windows login.

Expected processes and listeners after restart:
- One FastAPI/Uvicorn runtime owns the single listener
  `127.0.0.1:8000`. Uvicorn reload mode may create a parent/child process tree,
  but there must be only one listener.
- One Streamlit runtime owns the single listener `127.0.0.1:8001`.
- One scheduler runtime runs `main.py`, holds the `scheduler_process` lock,
  and updates `core/scheduler/logs/scheduler_metrics.json`.
- One Caddy runtime from `C:\Program Files\Caddy\caddy.exe` owns TCP 80 and
  443 plus the loopback admin endpoint `127.0.0.1:2019`.
- Tailscale may separately own its Tailscale-interface port 443 listeners; this
  is expected and is not a duplicate public Caddy listener.

Expected application state after restart:
- FastAPI `/health/live`: HTTP 200 JSON.
- FastAPI `/health/ready`: HTTP 200 JSON.
- Streamlit `/_stcore/health`: HTTP 200.
- Scheduler metrics report `scheduler_running=true`, a heartbeat no older than
  the configured 300-second TTL, and no duplicate process lock owner.
- Before restart, the last `quarter_hour_job` run was
  `2026-06-12T09:16:07.877981`, status `success`, with 0 failures in 24 hours;
  the pre-restart next run was `2026-06-12T09:35:05+02:00`. After restart,
  confirm the next applicable scheduled slot and at least one successful job.
- The tracked and deployed Caddyfile hashes remain equal to the SHA-256 above.
- The deployed Caddy configuration validates.
- `http://monitoring.armexholding.cz` returns HTTP 308 to HTTPS.
- `https://monitoring.armexholding.cz` returns the Streamlit page with HTTP 200
  and no `WWW-Authenticate` Basic challenge or browser credential popup.
- An unauthenticated protected non-login `/api/*` route returns FastAPI HTTP
  401 JSON, not Streamlit HTML.
- `/api/v1/auth/login` reaches FastAPI directly.
- A validly encoded invalid login returns generic HTTP 401 JSON without account
  enumeration detail.
- A disposable test account returns HTTP 429 with `Retry-After` on the fifth
  failed attempt; do not use a real dashboard account for this test.
- A real dashboard credential login should be tested manually by the user;
  no password should be read or requested by the agent.

Required post-restart checks:
- Confirm scheduled task startup completed and no duplicate listeners exist.
- Confirm listeners on 8000, 8001, 80, 443, and 2019 match the expectations.
- Confirm FastAPI live/ready and Streamlit health endpoints.
- Confirm scheduler lock, heartbeat, latest status, and next run.
- Confirm tracked/runtime Caddyfile hash equality and configuration validation.
- Confirm HTTP 308, HTTPS dashboard 200 without Basic challenge, and protected
  API 401 JSON.
- Confirm generic invalid-login response and disposable-account throttling.
- Confirm the working tree still contains the expected uncommitted changes and
  no files were lost or unexpectedly modified by startup.
- Append a dated post-restart verification entry with all results and
  deviations.

Known risks or accepted gaps:
- Uvicorn production startup still uses `--reload`; removal remains P2.13.
- Login throttle state is process-local and resets on restart; production
  currently uses one API worker.
- External access from a separate network and a real credential-based browser
  login have not been automated.
- The complete pytest suite was not rerun; the targeted security/dashboard set
  passed 55 tests.

### 2026-06-12 09:52 CEST - Post-restart verification

Scope:
- Verified the scheduled production runtime after the workstation restart
  requested in the 09:23 CEST handoff.

Verified:
- Scheduled task `API_dashboard_caddy` ran at 09:25:23 with result `0`, uses a
  boot trigger, and points to the tracked `start_api_dashboard.bat`.
- FastAPI listens only on `127.0.0.1:8000`, Streamlit only on
  `127.0.0.1:8001`, and one Caddy runtime owns public TCP 80/443 plus
  `127.0.0.1:2019`. Separate Tailscale-interface 443 listeners remain expected.
- FastAPI live/ready and Streamlit health endpoints returned HTTP 200.
- The scheduler process lock was held. Metrics reported a running scheduler,
  a current heartbeat, and a successful first post-restart
  `quarter_hour_job` at 09:35:08 with zero failures in 24 hours.
- Tracked and deployed Caddyfile SHA-256 values both equal
  `F41D3B31EA03308CB4345B1D11F0488B11D1FE527CBF135B0E1E166E5E7BC9BE`.
- The deployed Caddy configuration validated successfully.
- HTTP returned 308 to HTTPS. HTTPS returned the Streamlit page with HTTP 200
  and no Basic Auth challenge.
- An unauthenticated protected API route returned FastAPI HTTP 401 JSON.
- A validly encoded invalid login returned the generic HTTP 401 response.
- A disposable account returned HTTP 401 on attempts 1-4 and HTTP 429 with
  `Retry-After: 30` on attempt 5.
- The working tree still contained the expected pre-restart changes; no
  tracked file was lost or unexpectedly modified by startup.

Not verified:
- Public access from a separate external network was not tested because the
  server does not have NAT loopback.
- A real credential-based browser login was not automated or requested.

Deviations:
- None. A second Caddy process observed during parallel inspection was the
  short-lived `caddy validate` command; only one Caddy process owned listeners.

### 2026-06-12 - Authentication audit logging and alerts

Scope:
- Completed dashboard security checklist item P1.4.

Changed:
- Added structured authentication audit logging with daily rotation and
  90-backup retention.
- Added internal login reason categories while preserving one generic external
  authentication failure response.
- Added audit events for login success/failure/throttling, password changes,
  token revocation, administrator password resets, role changes, activation
  changes, account creation, and account deletion.
- Added the same account/password/role/activation audit coverage to the
  supported local user-management CLI.
- Added warning events for account brute force, IP password spraying, and
  repeated administrator-account failures.
- Added DEC-027 and documented the protected audit path and thresholds.

Runtime state:
- The default audit file is
  `C:\ProgramData\monitorovaci_platforma\logs\auth_audit.jsonl`.
- Its ACL allows only SYSTEM, Administrators, and `ARMEX\tra`.
- A live disposable-account test produced five failed-login records and one
  `account_brute_force` warning record.
- The disposable test password was absent from the matching JSONL records.

Verified:
- Authentication-audit, admin-audit, CLI-audit, auth-route, login-throttle,
  auth-state, security-config, Caddy, navigation, and responsive-layout tests
  passed: 65 tests.
- Python compilation passed for all changed authentication and admin modules.
- FastAPI live and ready endpoints remained HTTP 200 after Uvicorn reloaded the
  changed source.

Not verified:
- A successful real-user login audit was not tested because no dashboard
  password was read or requested.
- Live IP password-spray and administrator-account alert thresholds were not
  triggered to avoid blocking the production source IP or touching a real
  administrator account; both are covered by unit tests.

### 2026-06-12 - Password policy hardening

Scope:
- Completed dashboard security checklist item P1.5.

Changed:
- Added one shared password validator for administrator creation/reset,
  self-service changes, local CLI management, Streamlit forms, and the
  database password-write boundary.
- Added a tracked local common/compromised password blocklist including
  deployment-specific expected values.
- Required 15 to 1024 characters while preserving Unicode, spaces, long
  passphrases, password-manager values, and paste.
- Added Unicode NFC normalization before password hashing.
- Increased PBKDF2-HMAC-SHA256 from 390,000 to 600,000 iterations.
- Added transparent rehash of older valid PBKDF2 hashes after successful login
  without incrementing token version or requiring a bulk reset.
- Changed the bootstrap CLI to use a hidden password prompt when `--password`
  is omitted.
- Added DEC-028 and deployment documentation.

Verified:
- Password-policy, blocklist, Unicode normalization, work-factor, legacy
  verification, automatic rehash, admin create/reset, self-service, CLI, UI
  wiring, authentication, audit, Caddy, navigation, and responsive tests
  passed: 84 tests.
- The full test suite passed 471 of 473 tests.
- FastAPI application import and Python compilation of changed modules passed.
- On this workstation, 600,000-iteration PBKDF2 hashing took approximately
  0.126 seconds and verification approximately 0.132 seconds.
- FastAPI live/ready, Streamlit health, and the public invalid-login path
  remained operational after Uvicorn reloaded the change.

Not verified:
- No real dashboard user password was read, changed, or used for login.
- Existing production hash iteration counts were not enumerated because
  migration occurs safely on successful login and raw password hashes remain
  sensitive.
- Two full-suite failures reproduce independently in
  `tests/test_vodomery_reports.py`: the day consumption curve expectation and
  an outdated report-heading expectation. P1.5 did not change vodomery report
  code or tests, so those failures were left outside this security task.

### 2026-06-12 11:43 CEST - Pre-restart handoff

Reason for restart:
- Renew the complete production runtime through the supported Windows
  Task Scheduler boot path.
- Verify dashboard security checklist item P1.5 from a cold application start,
  including the shared password policy, 600,000-iteration PBKDF2 hashes, and
  compatible legacy-hash handling.

Current task/conversation state:
- Completed and committed P1.5 password policy hardening in commit
  `ff7513d` (`security check P1.5 hotovo`).
- P1.5 code, tests, checklist, DEC-028, and deployment documentation are
  complete.
- Pending: restart Windows, run all checks below, and append a dated
  post-restart verification entry with any deviations.
- First action after restart: read `AGENTS.md`, `DECISIONS.md`, and
  `SESSION_NOTES.md`, then run `git status --short`.

Working tree and deployment:
- `git status --short --untracked-files=all` was empty before this handoff.
- At restart, the only expected uncommitted change is this appended
  `SESSION_NOTES.md` handoff.
- Relevant deployed source is commit `ff7513d`; no Caddy configuration was
  changed by P1.5.
- Tracked and deployed Caddyfile SHA-256 values both equal
  `F41D3B31EA03308CB4345B1D11F0488B11D1FE527CBF135B0E1E166E5E7BC9BE`.
- `C:\Program Files\Caddy\Caddyfile` validated successfully immediately before
  restart.
- Scheduled task `API_dashboard_caddy` was `Ready`; its last run was
  2026-06-12 09:25:23 CEST with result `0`. It has a boot trigger, runs as
  user `tra` with highest run level, and executes the tracked
  `start_api_dashboard.bat`.

Sensitive/runtime artifacts:
- Do not print, change, delete, or commit the ignored local `.env` containing
  `API_TOKEN_SECRET`.
- Do not inspect, print, change, delete, or commit
  `data/smartfuelpass/session_cookies.json` or other browser session data.
- Do not print raw authentication audit records from
  `C:\ProgramData\monitorovaci_platforma\logs\auth_audit.jsonl`.
- The retired ProgramData Caddy gate credential files remain sensitive and
  must not be printed, changed, or deleted.
- Do not read or request real dashboard passwords, bearer tokens, cookies, or
  stored password hashes during verification.

Expected processes and listeners after restart:
- One FastAPI/Uvicorn runtime owns the single listener
  `127.0.0.1:8000`. Reload mode may create a parent/child process tree, but
  there must be only one listener.
- One Streamlit runtime owns the single listener `127.0.0.1:8001`.
- One scheduler runtime runs `main.py`, holds the `scheduler_process` lock,
  and updates `core/scheduler/logs/scheduler_metrics.json`.
- One Caddy runtime from `C:\Program Files\Caddy\caddy.exe` owns TCP 80 and
  443 plus `127.0.0.1:2019`.
- Tailscale may separately own its interface-specific TCP 443 listeners; that
  is expected and is not a duplicate public Caddy listener.

Expected application state:
- FastAPI `/health/live` and `/health/ready`: HTTP 200.
- Streamlit `/_stcore/health`: HTTP 200.
- Scheduler reports `scheduler_running=true`, holds the process lock, and has
  a heartbeat no older than the configured 300-second TTL.
- Immediately before restart, `quarter_hour_job` last ran successfully at
  `2026-06-12T11:35:08.501241`, had 0 failures and 96 successes in 24 hours,
  and its next run was `2026-06-12T11:47:05+02:00`.
- Tracked and runtime Caddyfile hashes remain equal to the SHA-256 above and
  the runtime configuration validates.
- Local hostname routing through Caddy returns HTTP 308 from HTTP to HTTPS,
  HTTP 200 for the HTTPS Streamlit page, and FastAPI HTTP 401 JSON for a
  protected API request without a bearer token.
- A validly encoded invalid login returns the same generic HTTP 401 JSON
  response without account-enumeration detail.
- P1.5 constants remain 15-character minimum, 1024-character maximum, and
  600,000 PBKDF2-HMAC-SHA256 iterations. The tracked password blocklist loads,
  weak/short test values are rejected, and a generated non-production Unicode
  passphrase is accepted and hashed with the current work factor.
- Existing valid legacy PBKDF2 hashes remain accepted and are rehashed only
  after successful login. Do not test this against a real user automatically.

Required post-restart checks:
- Confirm the scheduled task ran after boot with result `0`.
- Confirm exactly one listener each on 8000, 8001, 80, 443, and 2019, allowing
  the documented Tailscale-interface 443 listeners.
- Confirm FastAPI live/ready and Streamlit health endpoints.
- Confirm scheduler lock ownership, heartbeat age, latest job status, next
  run, and at least one successful post-restart scheduled job.
- Confirm tracked/runtime Caddyfile hash equality and run `caddy validate`.
- Confirm local Caddy hostname routing with explicit loopback resolution:
  HTTP 308, HTTPS dashboard 200, and protected API 401 JSON.
- Import `services.api.main` and run a non-production password-policy smoke
  check without reading the database or any real credential.
- Confirm a public invalid login remains generic HTTP 401; use only a
  disposable identifier and avoid triggering a throttle threshold unless
  specifically needed.
- Confirm `git status --short` shows only the expected handoff change and no
  startup-generated tracked changes.
- Append the actual verification results and deviations to this file.

Known risks or accepted gaps:
- Uvicorn production startup still uses `--reload`; removal remains P2.13.
- No real credential-based dashboard login or live legacy-hash migration will
  be automated.
- Existing production hash iteration counts were not enumerated.
- The full suite has two independently reproducible, unrelated failures in
  `tests/test_vodomery_reports.py`; P1.5 targeted coverage passed 84 tests and
  the full suite passed 471 of 473 tests.
- Direct access through the public endpoint from this server may lack NAT
  loopback; local Caddy verification uses the production hostname resolved
  explicitly to `127.0.0.1`.

### 2026-06-12 12:19 CEST - Post-restart verification

Scope:
- Verified the cold production runtime and P1.5 password-policy deployment
  after the workstation restart described in the 11:43 CEST handoff.

Verified:
- Windows boot completed at 11:44:55 CEST. Scheduled task
  `API_dashboard_caddy` ran at 11:45:05 CEST with result `0`, uses the boot
  trigger, and points to the tracked `start_api_dashboard.bat`.
- FastAPI had one listener on `127.0.0.1:8000`, Streamlit had one listener on
  `127.0.0.1:8001`, and one Caddy runtime owned TCP 80/443 and
  `127.0.0.1:2019`. Separate Tailscale-interface TCP 443 listeners were
  present as expected.
- FastAPI live/ready and Streamlit health endpoints returned HTTP 200.
- Scheduler metrics reported `scheduler_running=true`; the
  `scheduler_process` file lock was held and the heartbeat was within the
  configured 300-second TTL.
- The first checked post-restart `quarter_hour_job` completed successfully at
  12:16:10 CEST, with 0 failures and 96 successes in 24 hours; its next run
  was scheduled for 12:35:05 CEST.
- Tracked and runtime Caddyfile SHA-256 values both remained
  `F41D3B31EA03308CB4345B1D11F0488B11D1FE527CBF135B0E1E166E5E7BC9BE`.
  The runtime Caddy configuration validated successfully.
- Local hostname routing through Caddy returned HTTP 308 from HTTP to HTTPS,
  HTTP 200 for the HTTPS Streamlit page, and FastAPI HTTP 401 JSON for an
  unauthenticated protected API route.
- A valid disposable invalid-login request returned the generic FastAPI HTTP
  401 JSON response without account-enumeration detail.
- FastAPI imported successfully. The password-policy smoke check confirmed
  the 15/1024 character limits, loaded blocklist, 600,000 PBKDF2 iterations,
  weak-password rejection, Unicode passphrase support, current-hash
  verification, and verification/rehash detection for a synthetic
  390,000-iteration legacy hash.
- Targeted password-policy and security-configuration tests passed:
  24 tests.
- `git status --short --untracked-files=all` contained only the expected
  `SESSION_NOTES.md` handoff/verification change.

Not verified:
- No real dashboard password, production password hash, bearer token, or
  browser session was read or used.
- External access from a separate network was not tested.
- The full pytest suite was not rerun because P1.5 already passed its broader
  84-test set and the full-suite baseline before restart.

Deviations:
- None.

### 2026-06-12 - MFA/SSO deferred

Scope:
- Reviewed dashboard security checklist item P1.6.

Decisions/notes:
- The user deferred selection and implementation of corporate OIDC/SAML SSO
  or application-managed MFA.
- P1.6 remains open and is not considered completed.
- The accepted residual risk is that a compromised administrator password can
  still be sufficient for account access.
- Existing password hardening, throttling, audit logging, temporary lockouts,
  and token revocation remain compensating controls.
- Revisit P1.6 when corporate identity-provider capabilities are known, before
  materially expanding administrator access or public exposure, or after the
  currently actionable P1 items are addressed.

Follow-up:
- Continue with P1.7: remove the full bearer token from map iframe JavaScript.

### 2026-06-12 - Map iframe bearer token removal

Scope:
- Completed dashboard security checklist item P1.7.

Changed:
- Removed the main bearer token and `Authorization` header from generated map
  iframe HTML and JavaScript.
- Changed map photo loading to same-origin `/api/v1/map/images` with
  browser-managed credentials.
- Added a dedicated FastAPI dependency that accepts the existing HttpOnly
  dashboard session cookie only for the map image endpoint.
- Preserved token signature, expiry, user activity, `token_version`, map-layer,
  and device authorization checks.
- Kept all other protected FastAPI routes on bearer authentication.
- Removed `DASHBOARD_BROWSER_API_BASE_URL` and its `.env.example` entry because
  map image authentication now requires same-origin routing.
- Added DEC-029 and updated the operating context and security checklist.

Verified:
- Targeted map, map-layer, device-image, authentication-route, and dashboard
  auth-state tests passed: 66 tests.
- Python compilation passed for all changed application modules.
- FastAPI application import passed.
- FastAPI live/ready and Streamlit health endpoints returned HTTP 200 after
  Uvicorn reloaded the changes.
- The live image endpoint returned HTTP 401 with the missing-cookie response
  both without credentials and with a bearer header alone.
- A normal protected map catalog request with an invalid bearer token still
  followed bearer validation, confirming that cookie authentication was not
  enabled globally.
- OpenAPI exposes `GET /api/v1/map/images` with the dedicated `APIKeyCookie`
  scheme and keeps the normal `HTTPBearer` scheme for other protected routes.
- `git diff --check` reported no whitespace errors.

Not verified:
- A real authenticated device photo was not opened in a browser because no
  dashboard credential or browser cookie was read or requested.
- The full pytest suite was not run; verification focused on the changed map,
  authentication, and authorization surfaces.

Decisions/notes:
- Compromise of map iframe JavaScript no longer exposes a reusable dashboard
  API token.
- P1.8 remains important because Leaflet JavaScript is still loaded from
  `unpkg.com` and executes in the authenticated map iframe.

Follow-up:
- Continue with P1.8: host Leaflet JavaScript and CSS locally.

### 2026-06-12 12:51 CEST - Pre-restart handoff

Reason for restart:
- Renew the complete production runtime through the supported Windows Task
  Scheduler boot path.
- Verify dashboard security checklist item P1.7 from a cold application start,
  especially the dedicated cookie authentication for map images and the
  absence of the main bearer token from map iframe JavaScript.

Current task/conversation state:
- Completed implementation and targeted verification of P1.7.
- Deferred P1.6 MFA/SSO by explicit user decision; it remains open.
- P1.7 removes the main bearer token from generated map HTML, authenticates
  only `GET /api/v1/map/images` with the HttpOnly dashboard session cookie,
  and keeps all other protected API routes on bearer authentication.
- P1.7 changes are not committed. The current HEAD remains
  `ff7513d` (`security check P1.5 hotovo`).
- Pending: restart Windows, execute all checks below, append actual
  post-restart results and deviations, then continue with P1.8 local Leaflet
  hosting.
- First action after restart: read `AGENTS.md`, `DECISIONS.md`, and
  `SESSION_NOTES.md`, then run `git status --short --untracked-files=all`.

Working tree and deployment:
- `git status --short --untracked-files=all` immediately before this handoff:

```text
 M .env.example
 M AGENTS.md
 M DASHBOARD_SECURITY_CHECKLIST.md
 M DECISIONS.md
 M SESSION_NOTES.md
 M moduly/apps/dashboard/api_client.py
 M moduly/apps/dashboard/map_shared.py
 M moduly/apps/dashboard/pages/36_mapove_podklady.py
 M services/api/core/dependencies.py
 M services/api/routes/map.py
 M tests/test_dashboard_map_page_layout.py
 M tests/test_dashboard_map_shared.py
 M tests/test_map_routes.py
```

- All listed changes belong to the current restart handoff, the previously
  recorded P1.6 deferral, or the P1.7 implementation. Do not discard or
  overwrite them after restart.
- Uvicorn reload already loaded the changed Python source in the current
  runtime, but the restart will verify a cold scheduled-task startup.
- No Caddy configuration change is part of P1.7.
- Tracked and deployed Caddyfile SHA-256 values both equal
  `F41D3B31EA03308CB4345B1D11F0488B11D1FE527CBF135B0E1E166E5E7BC9BE`.
- The deployed Caddy configuration validated successfully before restart.
- Targeted P1.7 map, authentication, and authorization tests passed:
  66 tests.
- Python compilation and FastAPI import passed.
- `git diff --check` reported no whitespace errors.

Sensitive/runtime artifacts:
- Do not print, change, delete, or commit the ignored local `.env` containing
  `API_TOKEN_SECRET`.
- Do not inspect, print, change, delete, or commit SmartFuelPass cookies or
  other browser session artifacts.
- Do not print raw authentication audit records from
  `C:\ProgramData\monitorovaci_platforma\logs\auth_audit.jsonl`.
- Do not read or print the value of the
  `monitoring_dashboard_session` HttpOnly cookie, any bearer token, password,
  or stored password hash during verification.
- The retired ProgramData Caddy gate credential files remain sensitive and
  must not be printed, changed, or deleted.

Windows scheduled startup expectation:
- Scheduled task name: `API_dashboard_caddy`.
- Executable:
  `C:\Users\tra\PycharmProjects\monitorovaci_platforma\start_api_dashboard.bat`.
- Trigger: Windows boot (`MSFT_TaskBootTrigger`).
- Principal: user `tra`, highest run level.
- Before restart the task was `Ready`; its previous run at
  2026-06-12 11:45:05 CEST completed with result `0`.

Expected processes and listeners after restart:
- One FastAPI/Uvicorn runtime owns the single listener
  `127.0.0.1:8000`. Reload mode may create a parent/child process tree, but
  there must be only one listener.
- One Streamlit runtime owns the single listener `127.0.0.1:8001`.
- One scheduler runtime runs `main.py`, holds the `scheduler_process` lock,
  and updates `core/scheduler/logs/scheduler_metrics.json`.
- One Caddy runtime from `C:\Program Files\Caddy\caddy.exe` owns TCP 80 and
  443 plus `127.0.0.1:2019`.
- Tailscale may separately own interface-specific TCP 443 listeners; those are
  expected and are not duplicate public Caddy listeners.

Expected application state:
- FastAPI `/health/live` and `/health/ready`: HTTP 200.
- Streamlit `/_stcore/health`: HTTP 200.
- Scheduler reports `scheduler_running=true`, holds the process lock, and has
  a heartbeat no older than the configured 300-second TTL.
- Immediately before restart, `quarter_hour_job` last ran successfully at
  `2026-06-12T12:47:08.170524`, had 0 failures and 96 successes in 24 hours,
  and its next run was `2026-06-12T13:05:05+02:00`.
- Tracked and runtime Caddyfile hashes remain equal to the SHA-256 above and
  the runtime configuration validates.
- Local hostname routing through Caddy returns HTTP 308 from HTTP to HTTPS,
  HTTP 200 for the HTTPS Streamlit page, and FastAPI HTTP 401 JSON for an
  unauthenticated protected bearer API route.
- `GET /api/v1/map/images` without the dashboard session cookie returns HTTP
  401 JSON with the missing-cookie response.
- Sending a bearer header without the session cookie to the image endpoint
  still returns the missing-cookie HTTP 401 response.
- Other protected API routes continue to use bearer validation and do not
  accept cookie authentication.
- OpenAPI describes the image endpoint with `APIKeyCookie` named
  `monitoring_dashboard_session` and retains `HTTPBearer` for normal protected
  API operations.
- Generated map HTML contains no bearer token, `Authorization` header,
  `mapImageAccessToken`, or token-bearing iframe argument.
- Authenticated photo requests use same-origin `/api/v1/map/images` with
  `credentials: "same-origin"`; raw filesystem paths remain server-side.

Required post-restart checks:
- Confirm the scheduled task ran after boot with result `0`.
- Confirm exactly one listener each on 8000, 8001, 80, 443, and 2019, allowing
  the documented Tailscale-interface 443 listeners.
- Confirm FastAPI live/ready and Streamlit health endpoints.
- Confirm scheduler lock ownership, heartbeat age, latest job status, next
  run, and at least one successful post-restart scheduled job.
- Confirm tracked/runtime Caddyfile hash equality and run `caddy validate`.
- Confirm local Caddy hostname routing with explicit loopback resolution:
  HTTP 308, HTTPS dashboard 200, and protected bearer API 401 JSON.
- Confirm the image endpoint returns missing-cookie HTTP 401 both without
  credentials and with a bearer header alone.
- Import `services.api.main` and inspect OpenAPI without printing credentials:
  image security must be `APIKeyCookie`; normal protected routes must remain
  `HTTPBearer`.
- Run the targeted 66-test P1.7 suite and Python compilation.
- Search generated/source map HTML contracts to confirm no main bearer token
  or browser API override returned.
- Confirm `git status --short --untracked-files=all` still contains exactly
  the expected uncommitted P1.6/P1.7 documentation and code changes plus this
  handoff; no startup-generated tracked changes may appear.
- A real authenticated map photo may be checked manually by the user without
  exposing the cookie or password. Do not automate by reading browser state.
- Append a dated post-restart verification entry with results and deviations.

Known risks or accepted gaps:
- Uvicorn production startup still uses `--reload`; removal remains P2.13.
- A real authenticated device photo was not opened automatically before the
  restart because no dashboard credential or browser cookie was read.
- The full pytest suite was not rerun for P1.7; the focused 66-test set passed.
- Leaflet JavaScript and CSS are still loaded from `unpkg.com`; P1.8 is the
  next planned security item.
- P1.6 MFA/SSO remains deferred, so compromise of an administrator password
  can still be sufficient for account access.

### 2026-06-12 13:05 CEST - Post-restart verification

Scope:
- Verified the cold production runtime and P1.7 map iframe credential changes
  after the workstation restart described in the 12:51 CEST handoff.

Verified:
- Windows boot completed at 12:55:48 CEST. Scheduled task
  `API_dashboard_caddy` ran at 12:55:58 CEST with result `0`, remained
  `Ready`, used its boot trigger, and pointed to the tracked launcher.
- FastAPI had one listener on `127.0.0.1:8000`, Streamlit had one listener on
  `127.0.0.1:8001`, and one Caddy runtime owned TCP 80/443 and
  `127.0.0.1:2019`. Separate Tailscale-interface TCP 443 listeners were
  present as expected.
- FastAPI live/ready and Streamlit health endpoints returned HTTP 200.
- Scheduler metrics reported `scheduler_running=true`; the
  `scheduler_process` file lock was held and the heartbeat was within the
  configured 300-second TTL.
- The first post-restart `quarter_hour_job` completed successfully at
  13:05:10 CEST, with 0 failures and 96 successes in 24 hours; its next run
  was scheduled for 13:16:05 CEST.
- Tracked and runtime Caddyfile SHA-256 values both remained
  `F41D3B31EA03308CB4345B1D11F0488B11D1FE527CBF135B0E1E166E5E7BC9BE`.
  The runtime Caddy configuration validated successfully.
- Local hostname routing through Caddy returned HTTP 308 from HTTP to HTTPS,
  HTTP 200 for the HTTPS Streamlit page, and FastAPI HTTP 401 JSON for an
  unauthenticated protected bearer API route.
- `GET /api/v1/map/images` returned HTTP 401 without the dashboard session
  cookie and also returned HTTP 401 when sent only a synthetic bearer header.
- FastAPI imported successfully. OpenAPI described the image endpoint with
  `APIKeyCookie` named `monitoring_dashboard_session` and kept `HTTPBearer`
  for the normal protected map catalog route.
- Generated map HTML used same-origin `/api/v1/map/images` with
  `credentials: "same-origin"` and contained no `Authorization` header,
  bearer text, token variable, or browser API override.
- The focused P1.7 test suite passed all 66 tests. Python compilation passed
  for every changed application module, and `git diff --check` reported no
  whitespace errors.
- `git status --short --untracked-files=all` contained exactly the expected
  uncommitted P1.6/P1.7 documentation, application, and test changes.

Not verified:
- No real dashboard password, bearer token, browser cookie, production
  password hash, or authenticated device photo was read or used.
- External access from a separate network was not tested.
- The full pytest suite was not rerun; verification used the focused 66-test
  P1.7 suite from the handoff.

Deviations:
- None.

Follow-up:
- Continue with P1.8 by pinning and hosting the reviewed Leaflet JavaScript
  and CSS under application control and adding an external-script regression
  test.

### 2026-06-12 13:21 CEST - Local Leaflet assets

Scope:
- Completed dashboard security checklist item P1.8.

Changed:
- Vendored Leaflet `1.9.4` JavaScript, CSS, five referenced PNG assets, BSD
  license, and source/hash metadata under
  `moduly/apps/dashboard/assets/leaflet/1.9.4`.
- Replaced runtime `unpkg.com` Leaflet loading with cached local asset reads
  and inline iframe CSS/JavaScript.
- Embedded Leaflet CSS images and default marker images as data URIs.
- Added DEC-030 and updated the operating context and security checklist.
- Added regression tests for the official Leaflet SRI hashes, external
  executable script origins, inline map assets, and unbundled CSS references.

Verified:
- Vendored `leaflet.css` matched official SHA-256 SRI
  `p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=`.
- Vendored `leaflet.js` matched official SHA-256 SRI
  `20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=`.
- Generated map HTML contained Leaflet `1.9.4`, no external script source,
  no `unpkg.com` reference, no unbundled `url(images/...)` reference, and no
  stale source-map directive.
- Active dashboard Python and HTML sources contained no external HTTP(S)
  executable script tag.
- The combined P1.7/P1.8 map, authentication, authorization, and security
  suite passed all 73 tests.
- Python compilation, `git diff --check`, FastAPI live/ready, and Streamlit
  health checks passed.

Not verified:
- No real authenticated map interaction was automated because no dashboard
  credential or browser cookie was read or requested.
- The full pytest suite was not rerun; verification focused on the affected
  map, authentication, authorization, and security surfaces.

Decisions/notes:
- External OSM/CUZK map tiles and weather data remain network resources, but
  authenticated dashboard pages no longer execute third-party JavaScript.
- A workstation restart is not required for P1.8; Streamlit loads the changed
  renderer and repository assets on the next page rerun.

Follow-up:
- Continue with P1.9 browser session hardening.

### 2026-06-12 13:29 CEST - Pre-restart handoff

Reason for restart:
- Save the completed P1.7 and P1.8 security work and renew the complete
  production runtime through the supported Windows Task Scheduler boot path.
- Verify cookie-only map image authentication and locally vendored Leaflet
  assets from a cold start before continuing with P1.9 browser session
  hardening.

Current task/conversation state:
- P1.6 MFA/SSO remains deferred by explicit user decision.
- P1.7 is complete: map iframe JavaScript no longer receives the main bearer
  token, and only the map image endpoint accepts the HttpOnly dashboard
  session cookie.
- P1.8 is complete: Leaflet `1.9.4` JavaScript, CSS, images, license, and
  metadata are pinned under application control with no runtime executable
  code loading from `unpkg.com`.
- Pending before restart: commit all expected P1.6/P1.7/P1.8 files. Do not
  restart if staging, commit, or final clean-tree verification fails.
- Pending after restart: execute all checks below, append the actual result,
  then continue with P1.9 from `DASHBOARD_SECURITY_CHECKLIST.md`.
- First action after restart: read `AGENTS.md`, `DECISIONS.md`, and
  `SESSION_NOTES.md`, then run `git status --short --untracked-files=all`.

Working tree and deployment:
- Current HEAD before saving is `ff7513d` (`security check P1.5 hotovo`) on
  `master`.
- Expected files to commit before restart:

```text
.gitattributes
.env.example
AGENTS.md
DASHBOARD_SECURITY_CHECKLIST.md
DECISIONS.md
SESSION_NOTES.md
moduly/apps/dashboard/api_client.py
moduly/apps/dashboard/assets/leaflet/1.9.4/LICENSE
moduly/apps/dashboard/assets/leaflet/1.9.4/THIRD_PARTY.md
moduly/apps/dashboard/assets/leaflet/1.9.4/images/layers-2x.png
moduly/apps/dashboard/assets/leaflet/1.9.4/images/layers.png
moduly/apps/dashboard/assets/leaflet/1.9.4/images/marker-icon-2x.png
moduly/apps/dashboard/assets/leaflet/1.9.4/images/marker-icon.png
moduly/apps/dashboard/assets/leaflet/1.9.4/images/marker-shadow.png
moduly/apps/dashboard/assets/leaflet/1.9.4/leaflet.css
moduly/apps/dashboard/assets/leaflet/1.9.4/leaflet.js
moduly/apps/dashboard/map_shared.py
moduly/apps/dashboard/pages/36_mapove_podklady.py
services/api/core/dependencies.py
services/api/routes/map.py
tests/test_dashboard_map_page_layout.py
tests/test_dashboard_map_shared.py
tests/test_dashboard_security_config.py
tests/test_map_routes.py
```

- The expected working tree after commit and before restart is clean.
- Uvicorn reload and Streamlit page reruns have already loaded the Python
  changes in the current runtime; the restart will verify the committed cold
  startup.
- No Caddy configuration change is part of P1.7 or P1.8.
- Tracked and deployed Caddyfile SHA-256 values both equal
  `F41D3B31EA03308CB4345B1D11F0488B11D1FE527CBF135B0E1E166E5E7BC9BE`.
- The runtime Caddy configuration validated successfully before restart.
- The combined P1.7/P1.8 suite passed all 73 tests. Python compilation and
  `git diff --check` passed.

Sensitive/runtime artifacts:
- Do not print, change, delete, or commit the ignored local `.env` containing
  `API_TOKEN_SECRET`.
- Do not inspect, print, change, delete, or commit SmartFuelPass cookies or
  other browser session artifacts.
- Do not print raw authentication audit records from
  `C:\ProgramData\monitorovaci_platforma\logs\auth_audit.jsonl`.
- Do not read or print the `monitoring_dashboard_session` cookie, any bearer
  token, password, or stored password hash during verification.
- The retired ProgramData Caddy gate credential files remain sensitive and
  must not be printed, changed, or deleted.

Windows scheduled startup expectation:
- Scheduled task name: `API_dashboard_caddy`.
- Executable:
  `C:\Users\tra\PycharmProjects\monitorovaci_platforma\start_api_dashboard.bat`.
- Trigger: Windows boot (`MSFT_TaskBootTrigger`).
- Principal: user `tra`, highest run level.
- Before restart the task was `Ready`; its last run at
  2026-06-12 12:55:58 CEST completed with result `0`.

Expected processes and listeners after restart:
- One FastAPI/Uvicorn runtime owns the single listener
  `127.0.0.1:8000`. Reload mode may create a parent/child process tree, but
  there must be only one listener.
- One Streamlit runtime owns the single listener `127.0.0.1:8001`.
- One scheduler runtime runs `main.py`, holds the `scheduler_process` lock,
  and updates `core/scheduler/logs/scheduler_metrics.json`.
- One Caddy runtime from `C:\Program Files\Caddy\caddy.exe` owns TCP 80 and
  443 plus `127.0.0.1:2019`.
- Tailscale may separately own interface-specific TCP 443 listeners; those
  are expected and are not duplicate public Caddy listeners.

Expected application state:
- FastAPI `/health/live` and `/health/ready`: HTTP 200.
- Streamlit `/_stcore/health`: HTTP 200.
- Scheduler reports `scheduler_running=true`, holds the process lock, and has
  a heartbeat no older than the configured 300-second TTL.
- Immediately before restart, `quarter_hour_job` last ran successfully at
  `2026-06-12T13:16:08.313423`, had 0 failures and 96 successes in 24 hours,
  and its next run was `2026-06-12T13:35:05+02:00`.
- Tracked and runtime Caddyfile hashes remain equal to the SHA-256 above and
  the runtime configuration validates.
- Local hostname routing through Caddy returns HTTP 308 from HTTP to HTTPS,
  HTTP 200 for the HTTPS Streamlit page, and FastAPI HTTP 401 JSON for an
  unauthenticated protected bearer API route.
- `GET /api/v1/map/images` without the dashboard session cookie returns HTTP
  401, including when a bearer header is sent without the cookie.
- OpenAPI keeps `APIKeyCookie` only for the image endpoint and `HTTPBearer`
  for normal protected routes.
- Generated map HTML contains no main token, bearer header, external
  executable script source, `unpkg.com` reference, unbundled Leaflet image
  path, or stale source-map directive.
- Vendored `leaflet.js` and `leaflet.css` continue to match the official
  SHA-256 SRI values recorded in the tests and `THIRD_PARTY.md`.

Required post-restart checks:
- Confirm the scheduled task ran after boot with result `0`.
- Confirm exactly one listener each on 8000, 8001, 80, 443, and 2019, allowing
  the documented Tailscale-interface 443 listeners.
- Confirm FastAPI live/ready and Streamlit health endpoints.
- Confirm scheduler lock ownership, heartbeat age, latest job status, next
  run, and at least one successful post-restart scheduled job.
- Confirm tracked/runtime Caddyfile hash equality and run `caddy validate`.
- Confirm local Caddy hostname routing with explicit loopback resolution:
  HTTP 308, HTTPS dashboard 200, protected bearer API 401, and map image
  endpoint 401 without the dashboard cookie.
- Import `services.api.main` and inspect OpenAPI without printing credentials:
  image security must be `APIKeyCookie`; normal protected routes must remain
  `HTTPBearer`.
- Run the 73-test combined P1.7/P1.8 suite and Python compilation.
- Generate map HTML and confirm the token, same-origin image, local Leaflet,
  asset hash, and external-script regression contracts.
- Confirm `git status --short --untracked-files=all` is clean and HEAD is the
  commit created immediately before this restart.
- A real authenticated map may be checked manually by the user without
  exposing the cookie or password. Do not automate by reading browser state.
- Append a dated post-restart verification entry with results and deviations.

Known risks or accepted gaps:
- Uvicorn production startup still uses `--reload`; removal remains P2.13.
- No real authenticated map or device photo will be automated.
- The full pytest suite was not rerun; the focused combined suite passed all
  73 tests.
- P1.6 MFA/SSO remains deferred, so compromise of an administrator password
  can still be sufficient for account access.
- P1.9 browser session hardening has not started.
