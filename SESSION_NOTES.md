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
