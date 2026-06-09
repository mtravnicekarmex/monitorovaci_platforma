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
