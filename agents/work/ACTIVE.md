# Active work

## DASH-MAP-001 - Dashboard map viewport, controls, and filtering

- Status: source implemented and locally verified; pending post-restart
  browser verification and commit.
- Scope completed on 2026-08-24:
  `Mapove podklady / Mapa` moved base-map, overlay, location, and
  visible-layer filter controls into Leaflet; added `Bez mapy`; groups
  filters per visible layer; lazy-initializes hidden overlays; supports
  compound conditional style rules through `all`/`any`; includes style/filter
  properties in GeoJSON; normalizes Leaflet filter values for boolean/string
  source data; and makes the map fill the browser viewport while preserving
  Streamlit sidebar open/collapse controls above the map.
- Follow-up completed on 2026-08-25:
  layers with configured `Sloupce zobrazene v mape` / `map_label_columns`
  now appear in a separate Leaflet control `Popisky`. The control lists only
  currently visible labeled layers and lets the user hide/show labels per
  layer without hiding the layer geometry, filters, styles, or popups. Labels
  remain visible by default after page load.
- Legend follow-up completed on 2026-08-25:
  conditional-style rules in `Mapove vrstvy` now have optional
  `Název pravidla` stored as rule `name`. `Mapove podklady / Mapa` has a
  separate Leaflet control `Legenda` that lists currently visible
  conditional-style layers, shows rule color swatches, and lets the user hide
  or show legend entries per visible layer without changing map data,
  filters, labels, popups, or layer visibility. Follow-up fixed legend color
  fidelity by rendering line swatches as lines in `style.color` and applying
  opacity only to polygon/point fill, not to the whole swatch. The top-right
  Leaflet control stack is now viewport-bounded and vertically scrollable, so
  lower controls remain reachable when multiple panels are open; the
  scrollable Leaflet corner also enables `pointer-events: auto` so the
  scrollbar is draggable/clickable. Manual map zoom now allows level 24 for
  detailed vector-layer inspection; base tiles can be upscaled to level 24
  while retaining native tile limits 19/20, and automatic `fitBounds` is
  capped at zoom 22. The `poradi` / `draw_order` field now controls stable
  overlay stacking through per-layer Leaflet panes; lower values render below
  higher values even after a layer is toggled off and back on. Map-layer
  aliases and display labels are now separate: `property_aliases` maps source
  columns to technical GeoJSON keys, while `property_labels` maps GeoJSON keys
  to human-facing filter/popup labels and unnamed legend-condition fallback
  labels through the new `Popisky vlastnosti JSON` admin field. The map page
  also explicitly merges `property_labels` from catalog metadata and feature
  payloads when building the Leaflet iframe payload, so configured popup
  labels are not erased by an empty/partial layer payload.
- Revize map follow-up completed on 2026-08-26:
  map-layer configuration now includes `map_context` with supported contexts
  `evidence`, `revize`, and `shared`. The existing evidence map and the new
  `Revize / Mapa` page use the same shared full-viewport Leaflet page shell
  while loading different layer contexts. `Sprava / Mapove vrstvy` exposes the
  context as a `Mapa` selector. The default `revize_terminy_zarizeni` layer is
  sourced from `revize.v_mapa_terminy_zarizeni`, styled by `stav_terminu`,
  and filterable by status, device type, term type, building, floor, and room.
  Map API access is also checked by map context, so direct API calls for
  `revize` layers require access to the `revize` section.
  `scripts/postgres_dashboard_map_contexts.sql` was applied on 2026-08-26.
- Revize map field follow-up completed on 2026-08-26:
  `revize.v_mapa_terminy_zarizeni` now appends `servisni_smlouva` and
  `revize_soubor` to the output. The `revize_terminy_zarizeni` layer metadata
  includes both fields in popup/map properties and labels. The DB update was
  applied through `scripts/postgres_revize_map_terms_view.sql` plus
  `scripts/postgres_revize_map_terms_revision_file_fields.sql`. Runtime
  checks loaded 230 revize-map features and confirmed both keys in the feature
  payload. `revize_soubor` is populated in current source data, while
  `revize_servisni_smlouva` is currently empty in all revision evidence
  source views.
- PDF document-link follow-up completed on 2026-08-27:
  map-layer configuration now includes `document_columns`, a JSON object
  mapping source columns to popup link labels. Configured document source
  values stay server-side; GeoJSON feature payloads expose only sanitized
  `document_links`. The map has a new authorized
  `GET /api/v1/map/documents` endpoint that resolves PDF files by
  `layer_id`, `identifier`, and `document_key` using the same HttpOnly
  session-cookie boundary as map photos. Leaflet popups render these entries
  as links opening a new browser tab. The `revize_terminy_zarizeni` layer
  uses `revize_soubor -> Zobrazit revizi` and
  `servisni_smlouva -> Zobrazit servisni smlouvu`; these columns are no
  longer ordinary popup/property values. DB verification loaded 230 revize
  features, found 91 document-linked features, confirmed zero raw document
  path properties in feature payloads, and resolved all 91 current
  `revize_soubor` values as PDF files. `servisni_smlouva` is still empty in
  current source data.
- Label-default follow-up completed on 2026-08-26:
  map-layer configuration now includes `map_labels_default_visible`, exposed
  in `Sprava / Mapove vrstvy` as `Popisek defaultne`. It controls only the
  initial visibility of configured map labels; the Leaflet `Popisky` control
  remains the runtime per-layer toggle. All checkbox controls in the map-layer
  state row now have help text. `scripts/postgres_map_layer_label_default_visibility.sql`
  was applied on 2026-08-26.
- Revize linked-filter follow-up completed on 2026-08-27:
  the shared Leaflet payload now includes `map_context`, and only in
  `map_context=revize` the `mistnosti` layer copies supported room-context
  filter selections into `revize_terminy_zarizeni`. Current effective linked
  filters are `budova` and `patro`; `mistnost_id` and `mistnost` are prepared
  but apply only if both layers expose those filter keys. The sync is one-way
  from `mistnosti` to revision terms, and it leaves independent term filters
  unchanged. The Leaflet `Filtry` control also preserves the open state of
  each layer section during panel re-rendering, so selecting `Budova` no
  longer closes the `Mistnosti` section before `Patro` can be selected.
- Pronajem map section follow-up completed on 2026-08-27:
  dashboard navigation now includes section `pronajem` / `Pronájem` between
  `Revize` and `Mapove podklady`, with one configurable page
  `pronajem_map` displayed as `Mapa - pronájem`. The page uses the shared
  full-viewport Leaflet renderer with `map_context=pronajem`. Map API,
  admin request validation, backend context validation, and `Sprava / Mapove
  vrstvy` now accept `pronajem`; non-admin access requires section
  permission `pronajem`. No pronajem-specific seed layer or database
  migration was added.
- Opticke vany rack-location follow-up completed on 2026-08-27:
  `scripts/postgres_opticke_vany_rack_location_columns.sql` was added and
  applied. `evidence."OPTICKÉ VANY"` now has `budova`, `patro`, and
  `místnost` cache columns populated from `evidence."RACKY"` through
  `OPTICKÉ VANY"."rack" -> RACKY"."označení"`. A before trigger fills the
  cache when an optical tray is inserted or its rack changes, and an after
  trigger on `RACKY` propagates later rack-location changes. Verification
  found 5 optical-tray rows, 5 matched racks, and 5 rows matching the current
  rack location values. Existing map-layer metadata for `opticke_vany` and
  `racky` already exposes these fields, so no map metadata update was needed.
- Switche rack-location follow-up completed on 2026-08-27:
  `scripts/postgres_switche_rack_location_columns.sql` was added and applied.
  `evidence."SWITCHE"` now has `budova`, `patro`, and `místnost` cache
  columns populated from `evidence."RACKY"` through
  `SWITCHE"."rack" -> RACKY"."označení"`. A before trigger fills the cache
  when a switch is inserted or its rack changes, and an after trigger on
  `RACKY` propagates later rack-location changes. Verification found 0 switch
  rows currently present and proved the insert trigger through a rollback-only
  test against an existing rack. No dashboard map layer for `SWITCHE` exists
  yet, so no map metadata update was needed.
- Evidence linked-filter follow-up completed on 2026-08-27:
  `Mapove podklady / Mapa` now uses `mistnosti` as a linked-filter source for
  all other `layer_kind=device` layers with matching supported filter keys,
  plus explicitly approved infrastructure context layers
  `vodovodni_potrubi`, `vodovodni_uzly`, and `VZT`. Current linked keys are
  `budova`, `patro`, `mistnost_id`, and room-name variants when supported.
  The sync also stores filter state for hidden target layers, so enabling a
  device or approved infrastructure layer later applies the active
  `mistnosti` building/floor/room filter immediately. Generic context layers
  such as `budovy` are not targets.
- Current pause point: the user is restarting the workstation. After restart,
  browser-test the map page with the sidebar expanded and collapsed. The
  latest CSS uses a transparent fixed zero-height Streamlit header and a
  fixed collapsed-sidebar open control. Follow-up after restart found that
  Streamlit 1.57 uses `stExpandSidebarButton` inside `stToolbar` for the
  collapsed-sidebar open arrow; the page must keep `stToolbar` transparent and
  overflow-visible rather than hiding it. The collapsed map layout now keeps
  only a `2.5rem` left gutter for this arrow and otherwise keeps left padding
  at zero. If the arrow still disappears, inspect whether the running frontend
  differs from local Streamlit 1.57 and adjust only that CSS
  selector/positioning. The expanded Leaflet layers panel now keeps its
  natural content width, and `Filtry` measures that panel and applies the
  result through `--map-filter-panel-width`; do not force the main layer panel
  wider to align the two controls.
- Verification before restart:
  `tests/test_dashboard_map_page_layout.py` returned `2 passed`; the focused
  map regression set returned `102 passed`; AST syntax passed; `git diff
  --check` had only LF/CRLF warnings. PyCharm lint reported only existing
  weak/type warnings outside the new CSS behavior. Follow-up label-toggle
  verification on 2026-08-25 returned `21 passed` for
  `tests/test_dashboard_map_shared.py`, `74 passed` for the focused map
  regression subset, `py_compile` passed for `map_shared.py`, and
  `git diff --check` returned only LF/CRLF normalization warnings. Initial
  legend-rule verification on 2026-08-25 returned `24 passed` for
  `tests/test_dashboard_map_shared.py` and
  `tests/test_dashboard_map_layers_admin.py`; after the legend color fix the
  same focused test pair returned `24 passed`. After the control-stack scroll
  and pointer-events fix, `tests/test_dashboard_map_shared.py` returned
  `23 passed`. After the zoom-limit fix,
  `tests/test_dashboard_map_shared.py` returned `24 passed` and the focused
  map regression subset returned `78 passed`. After the draw-order pane fix,
  `tests/test_dashboard_map_shared.py` returned `25 passed` and the focused
  map regression subset returned `79 passed`. After the property-label fix,
  targeted map-layer tests returned `46 passed`, the focused map regression
  subset returned `81 passed`, and `py_compile` passed for the touched
  dashboard/API map modules. After the property-label runtime merge fix,
  targeted map-page/renderer/admin tests returned `32 passed`, the focused
  map regression subset returned `82 passed`, and `py_compile` passed for
  `36_mapove_podklady.py` and `map_shared.py`. After the revize map context
  follow-up on 2026-08-26, targeted map/context/navigation tests returned
  `64 passed`, the focused map regression set returned `110 passed`,
  `py_compile` passed for touched dashboard/API map modules, DB verification
  loaded 230 revize map features and confirmed revize-context API access
  control, and `git diff --check` returned only LF/CRLF normalization
  warnings. After the revize map field follow-up on 2026-08-26, targeted map
  service/routes/shared/admin tests returned `63 passed`, `compileall` passed
  for `services/api/services/map_layers.py` and
  `tests/test_map_layers_service.py`, and DB verification confirmed the new
  appended view columns plus catalog/feature payload metadata. After the
  label-default follow-up on 2026-08-26, targeted map
  label/admin/service tests returned `63 passed`, the focused map regression
  set returned `111 passed`, `py_compile` passed for touched dashboard/API
  map modules, and DB verification confirmed the new column/catalog field.
  After the PDF document-link follow-up on 2026-08-27, targeted map
  service/routes/shared/admin/page tests returned `98 passed`, `compileall`
  passed for touched dashboard/API/test Python files, DB verification
  confirmed sanitized document-link feature payloads and 91 resolvable current
  revision PDFs, and `git diff --check` returned only LF/CRLF normalization
  warnings. After the Revize linked-filter follow-up on 2026-08-27,
  `tests/test_dashboard_map_shared.py` and
  `tests/test_dashboard_map_page_layout.py` returned `31 passed`, and
  `compileall` passed for the touched dashboard/test Python files. After the
  Pronajem map section follow-up on 2026-08-27, targeted
  navigation/map/admin/service/route tests returned `73 passed`, and
  `compileall` passed for touched dashboard/API/test Python files. After the
  Opticke vany rack-location follow-up on 2026-08-27, PostgreSQL metadata
  verification confirmed the new columns, both synchronization triggers, and
  all 5 current rows matching rack location values. After the evidence
  linked-filter follow-up on 2026-08-27,
  `tests/test_dashboard_map_shared.py` and
  `tests/test_dashboard_map_page_layout.py` returned `32 passed`, and
  `compileall` passed for the touched dashboard/test Python files.
- Changed files are listed in the 2026-08-24 10:29 +02:00 pre-restart
  handoff in `../history/SESSION_NOTES.md`.
- Updated: 2026-08-27

## DASH-REVIZE-001 - Dashboard Revize renewal history

- Status: source implemented, locally verified, and PostgreSQL schema applied;
  pending workstation restart and browser/API runtime test.
- Scope completed on 2026-08-24:
  `Prehled / Revize` renewal now uses a dedicated admin API endpoint
  `POST /api/v1/admin/revize/{revize_id}/renew`. The backend creates a new
  revision row, writes linked-device rows for it, and marks the source row as
  replaced through `revize.revize.nahrazena_revizi_id` in one transaction.
  The revision form `Budova` options now load from
  `"evidence"."BUDOVY".budova`; edit/renew forms still append the current
  record value if it is missing from the evidence table.
  The overview defaults to current records only; historical replaced records
  are available through an explicit sidebar record-scope filter and show
  status `Nahrazené`.
- Schema prerequisite:
  `scripts/postgres_revize_replacement_link.sql` was applied on 2026-08-24.
  Follow-up schema verification confirmed
  `revize.revize.nahrazena_revizi_id`, the foreign key, the self-link check,
  and the index exist.
- Verification:
  `tests/test_dashboard_revize_shared.py`,
  `tests/test_dashboard_admin_write_api_client.py`, and
  `tests/test_api_authorization_regression.py` returned `255 passed`;
  after switching `Budova` options to `evidence.BUDOVY`,
  `tests/test_dashboard_revize_shared.py` returned `25 passed`;
  `git diff --check` returned only LF/CRLF normalization warnings.
- Not done: dashboard runtime has not yet been restarted after the schema and
  source change; no production revize row was intentionally changed.
- Updated: 2026-08-24

## OPS-002 - Independent scheduler monitoring agent

- Status: roadmap items 1, 2, 3, 4, 5, and 6 completed on 2026-08-14; item 7
  completed on 2026-08-17 as a healthy no-event reviewed pilot plus
  file-only synthetic comparison mechanics proof. Item 8 completed on
  2026-08-17 with local DB-availability and scheduler-metrics agents running
  through the shared local Scheduled Task `MonitoringLocalAgents`. Item 9
  completed on 2026-08-17 when
  `../plans/monitoring/MONITORING_ORCHESTRATOR_DESIGN.md` was reviewed and
  accepted as the read-only supervision-correlation architecture baseline.
  The approved file-only/shadow-only orchestrator scope now includes
  `monitoring_agent/orchestrator.py`,
  `monitoring_agent/orchestrator_cli.py`, and
  `monitoring_agent/orchestrator_export_cli.py`. The full three-source
  file-only pilot completed on 2026-08-18, including a follow-up rerun where
  the supplied remote audit was wrapped with `captured_at`, removing the
  artificial `source_timestamp_missing` gap. No live polling, orchestrator
  Scheduled Task, remote polling-set change, production delivery,
  remediation, process control, provider execution, or alert replacement is
  approved by item 9. Separate from item 9, a controlled automatic
  test-recipient delivery gate was later approved and activated on 2026-08-21.
  Remote
  `0.8.1-test` uses the intentional clean `monitoring-agent-state-ops002`
  baseline; env-v1 bridge, target scheduler-detail timezone restart, env-v2
  nine-endpoint proof, and continuous `MonitoringAgentTest` Scheduled Task
  restoration all passed. The latest remote-proved item-7 checkout uses
  audit-v8 and is healthy with nine observations, zero latest transport
  failures, `shadow_incidents.present=true`, and no current runtime/delivery
  failure. Local source now contains
  incident-rule version 1, bounded incident/outbox state, observation
  retention, pure report/programming-agent prompt rendering, and a
  disabled-by-default test-only Outlook delivery adapter. One separately
  approved synthetic `send-due` message was sent from the supervision station
  with sanitized success evidence. Local source also contains a pure
  draft-only interpretation contract over confirmed incidents only and a pure
  `shadow_only` comparison contract for supplied sanitized monitoring-agent
  and legacy-alert events. The 2026-08-17 source update wires deterministic
  incident evaluation into the polling loop after each completed cycle,
  persists bounded `incident_state.json`, emits sanitized `shadow_incidents`,
  and advances `--audit-state` to audit contract 8. It adds no `.env` key and
  does not enable automatic delivery, real provider execution, remediation,
  process control, or any legacy-alert replacement. Standalone Git commit
  `207fc1d38d066cdc642dc86bc0cc0b2b6c817cfc` was pulled on the supervision
  station, but remote activation exposed an env-v2
  compatibility bug: `--check-config` passed, while real client startup failed
  because `MONITORING_AGENT_EXTERNAL_WEB_URL` was not loaded for env contract
  2. Fix commit `e23f5f893d76951995a8b6df833e60aadb96a858` was pulled and
  remotely verified: foreground `--once` created `incident_state.json`, and
  the restarted `MonitoringAgentTest` task runs with audit-v8
  `shadow_incidents.present=true`. No `.env` change was required. Follow-up
  commit `3c6502c74d478a7518d3bbc37f7799951bbbaba4` adds the file-based
  shadow-pilot comparison CLI and was pulled/verified on the supervision
  station; audit-v8 stayed healthy with `shadow_incidents.present=true`.
  Standalone commit `f6583d80a77695b3f4a094337251c6835b389b59` was pushed on
  2026-08-21 with item-9 file-only orchestrator/export modules and a 25-file
  Git manifest SHA-256
  `37e2967efa4edbf5cfcfdeaa5a9bb8e073ef417fd2499ed058cf7085a8daf61b`; it was
  pulled and wrapper-verified on the supervision station on 2026-08-21.
- Priority: normal
- Plan: `../plans/monitoring/SCHEDULER_MONITORING_AGENT_PLAN.md`
- Runtime design:
  `../plans/monitoring/SCHEDULER_MONITORING_AGENT_REMOTE_RUNTIME_DESIGN.md`
- Reporting handoff:
  `../plans/monitoring/MONITORING_AGENT_REPORTING_LAYER_HANDOFF.md`
- Implementation roadmap/checklist:
  `../plans/monitoring/MONITORING_AGENT_IMPLEMENTATION_ROADMAP.md`
- Orchestrator accepted design:
  `../plans/monitoring/MONITORING_ORCHESTRATOR_DESIGN.md`
- Historical 2026-08-17 handoff for item 7: the then-current remote-proved
  checkout was `3c6502c74d478a7518d3bbc37f7799951bbbaba4`;
  `MonitoringAgentTest` was `Running`, latest audit-v8 heartbeat was
  `healthy`, and `shadow_incidents.present=true` with `mode="shadow_only"` and
  `delivery_enabled=false`. The retained `unclean_restart_count=2`,
  `start_while_prior_run_open_count=2`, `abandoned_unclosed_run_count=1`, and
  `cycle_sequence_valid=false` are planned activation artifacts from stopping
  the old long-running process and using foreground `--once`, not current
  runtime/delivery failures. Item 7 is closed for test-stage shadow
  comparison evidence, but do not enable automatic delivery, production
  recipients, real interpretation provider execution, remediation, process
  control, or legacy-alert replacement without separate approval.
- Earlier 2026-08-21 checkout proof: `f6583d80a77695b3f4a094337251c6835b389b59`
  is pulled and wrapper/config-verified on the supervision station. A
  180-second follow-up runtime sample showed `MonitoringAgentTest`
  `State=Running`, audit-v8 latest heartbeat `healthy`, nine latest
  observations, zero latest transport failures, valid endpoint/retry
  contracts, no in-progress or incomplete observations, and no current
  concurrent-start, run-reentry, overlap, or process-run-transition evidence.
  Retained lifecycle artifacts are now `unclean_restart_count=3`,
  `start_while_prior_run_open_count=3`, and
  `abandoned_unclosed_run_count=2`. Shadow incidents are still
  `mode="shadow_only"` with `delivery_enabled=false`; the sample reported
  `active_state_count=1`, `resolved_state_count=2`, and
  `outbox_pending_count=11`, which are follow-up analysis inputs rather than
  delivery authorization.
- Follow-up 2026-08-21 analysis confirmed the active state is
  `endpoint:system_scheduler`, opened at
  `2026-08-20T00:17:37.512339+02:00`, with
  `last_reason="endpoint_payload_status:degraded"`. The user identified the
  operational source as the last two days' midnight `daily_job` failure in
  `SOFTLINK_save_to_database_all`. The outbox has only one pending `opened`
  item for `endpoint:system_scheduler`; the rest of the 11 pending intents are
  older `system_runtime` and `target_wide_outage` transitions. Commit
  `601a50587c73627835d4860b2212a82a92670f12` was pushed to the standalone
  repository on 2026-08-21 to collapse redundant unchanged `updated`
  transition records, document the steady-state `300/30` poll profile, and
  regenerate the 25-file Git manifest with SHA-256
  `07e08ccd56275a30e0169b863c60aee07241ba2f1c7126fb19989382c2c1a349`.
  The supervision station pulled and verified this commit on 2026-08-21:
  config remained valid with endpoint count 9 / env contract 2 / test mode,
  the restarted runtime reported latest heartbeat `healthy`, zero latest
  transport failures, and a new 310.977-second interval inside the
  332-second configured maximum. The transition-compaction check showed no
  new repeated unchanged `endpoint:system_scheduler` `updated` records after
  the restarted 300-second runtime began.
- 2026-08-21 follow-up on the operational source found the SOFTLINK failure
  in `SOFTLINK_data_z_dotazu.py`: Playwright timed out after 30 seconds
  waiting for visible `text=Odhlásit` after login submission on both
  2026-08-20 and 2026-08-21. The user confirmed changed SOFTLINK credentials.
  Local scheduler source now pauses `SOFTLINK_save_to_database_all` and
  `elektromery_softlink_monitoring_import` from scheduled/manual scheduler
  execution; `daily_job` currently runs only `meteo_sync`. The new
  independent-step runner for `daily_job` continues after a failed independent
  step and raises one aggregate error afterward. Return gate: port
  `SOFTLINK_data_z_dotazu.py` to the saved-session/API-validation pattern in
  `SOFTLINK_data_zarizeni.py`, verify login, then re-add the paused scheduler
  steps. Verification: `tests/test_scheduler.py` returned `58 passed`;
  py_compile passed for touched files; `git diff --check` had only line-ending
  normalization warnings.
- Pre-restart handoff for 2026-08-21 is recorded in
  `../history/SESSION_NOTES.md`. After the local workstation restart,
  the later remote-agent checkpoint supersedes it. Current remote
  supervision-station checkout is
  `b6f4e047d59d14d0e34ac61c1a4e270b386f6ae9`; verify
  `MonitoringAgentTest` only with safe concurrent commands (`--check-config`,
  `--audit-state`) while it is running. The remote agent remains
  `shadow_only`, but controlled automatic test delivery is enabled through
  `DELIVERY_AUTOMATION_ENABLED=true`. If `endpoint:system_scheduler` remains
  active, first correlate retained scheduler metrics from the old SOFTLINK
  `daily_job` failure before treating it as new remote-agent evidence.
- Current 2026-08-21 automatic test-delivery checkpoint:
  standalone commit `b6f4e047d59d14d0e34ac61c1a4e270b386f6ae9`
  (`Add automatic test delivery gate`) adds
  `monitoring_agent/runtime_delivery.py`, an explicit
  `DELIVERY_AUTOMATION_ENABLED` gate, and runtime wiring after completed
  observation cycles. It sends at most one due pending outbox item per cycle
  to `DELIVERY_TEST_RECIPIENT` only, using existing Outlook test credentials
  and sanitized deterministic report text. Local verification passed with 19
  delivery/shadow tests, 89 main monitoring-agent tests, compileall,
  standalone env-v2 `--check-config`, and fake-transport smoke. The
  supervision station pulled the commit, enabled the local gate, restarted
  `MonitoringAgentTest`, and audit-v8 reported task `Running`, latest
  heartbeat `healthy`, nine latest observations, zero latest transport
  failures, `delivery_enabled=true`, `outbox_pending_count=0`,
  `outbox_sent_count=1`, `outbox_dead_letter_count=14`, one active
  `endpoint:system_scheduler` state, and update time
  `2026-08-21T11:08:28.897356+00:00`. No immediate automatic email is
  expected while pending remains zero; a future recovery of the active
  scheduler incident may automatically send one recovery message to the
  configured test recipient. Production recipients, provider execution,
  remediation, process control, alert suppression, and legacy-alert
  replacement remain unauthorized.
- Item 8 first local-agent proof: `local_monitoring_agents/database_availability.py`
  reads the local scheduler database-availability SQLite store read-only,
  writes bounded sanitized agent-owned state under the ignored
  `.local-monitoring-agent-state/` directory with its own writer lock, and
  exposes only safe aggregates through
  `/api/v1/monitoring/health/local-agents/database-availability`. The
  one-shot runner is `scripts/run_database_availability_local_agent.py`.
  Local proof on 2026-08-17 returned sanitized `status="ok"`,
  `service_count=2`, `pending_event_count=0`,
  `unavailable_service_count=0`, and `stale_service_count=0`. Tests:
  `tests/test_database_availability_local_agent.py` and
  `tests/test_monitoring_facade.py` returned `19 passed`; compileall passed.
  No `.env` key, delivery, provider execution, scheduler/application mutation,
  process control, remediation, raw reason/service-label/path exposure, or
  alert replacement was added.
- Item 8 second local-agent proof:
  `local_monitoring_agents/scheduler_metrics.py` reads local
  `core/scheduler/logs/scheduler_metrics.json` read-only, interprets naive
  scheduler timestamps as Europe/Prague local time, normalizes raw job
  `last_status` values into bounded classes, writes sanitized agent-owned
  state, and exposes only safe aggregates through
  `/api/v1/monitoring/health/local-agents/scheduler-metrics`. The one-shot
  runner is `scripts/run_scheduler_metrics_local_agent.py`. Real local proof
  on 2026-08-17 returned `status="degraded"`, `scheduler_running=true`,
  `job_count=51`, `success_count_24h=2594`, `failure_count_24h=0`,
  `error_job_count=2`, and `degraded_job_count=0`; this is fail-visible
  evidence of historical last-error job states without 24h failures. The
  DB-availability task helper
  `scripts/register_database_availability_local_agent_task.ps1` was added as
  an explicit operator-run registrar only; the helper itself does not start,
  stop, or unregister tasks. Targeted local-agent/facade/shadow tests returned
  `40 passed`; compileall passed. No labels, descriptions, raw skipped
  reasons, logs, paths, `.env`, delivery, provider execution,
  scheduler/application mutation, process control, remediation, or alert
  replacement was added.
- Item 8 first local Scheduled Task proof: on 2026-08-17
  `MonitoringDatabaseAvailabilityLocalAgent` was registered locally with the
  project `.venv` Python, project-root working directory, current-user limited
  principal, `IgnoreNew`, `StartWhenAvailable`, five-minute repetition, and a
  two-minute execution limit. A manual run returned `LastTaskResult=0`; the
  first automatic trigger ran at `2026-08-17 13:23:21 +02:00` with
  `LastTaskResult=0`, `NumberOfMissedRuns=0`, and next run
  `2026-08-17 13:28:21 +02:00`. The facade aggregate after the scheduled run
  remained `status="ok"`, `service_count=2`, `pending_event_count=0`,
  `unavailable_service_count=0`, and `stale_service_count=0`. No remote
  polling set or `.env` change was made.
- Item 8 shared-runner direction: the preferred runtime is now a shared local
  runner, not one Scheduled Task per local agent.
  `scripts/run_local_monitoring_agents.py` runs approved local agents in
  deterministic order while each agent retains its own state and writer lock.
  `scripts/register_local_monitoring_agents_task.ps1` is the preferred
  registrar for that shared runner; it parsed successfully. Manual
  shared-runner proof against real local sources returned overall
  `status="degraded"` with DB availability `status="ok"` and scheduler
  metrics `status="degraded"`, `scheduler_running=true`, `job_count=51`,
  `success_count_24h=2594`, `failure_count_24h=0`, `error_job_count=2`, and
  `degraded_job_count=0`. Verification returned `43 passed`, shared registrar
  parse OK, and compileall passed.
- Item 8 shared Scheduled Task migration completed on 2026-08-17.
  `MonitoringDatabaseAvailabilityLocalAgent` was retired and verified absent.
  `MonitoringLocalAgents` is the active local monitoring task. It uses project
  `.venv` Python, project-root working directory, current-user limited
  principal, `IgnoreNew`, `StartWhenAvailable`, five-minute repetition, and a
  three-minute execution limit. Manual run proof completed at
  `2026-08-17 13:41:50 +02:00` with `LastTaskResult=0`; first automatic
  trigger proof completed at `2026-08-17 13:42:32 +02:00` with
  `LastTaskResult=0`, `NumberOfMissedRuns=0`, and next run
  `2026-08-17 13:47:32 +02:00`. Sanitized facade projections after the
  automatic trigger had no evidence gaps: DB availability `status="ok"`,
  `service_count=2`, `pending_event_count=0`, `unavailable_service_count=0`,
  `stale_service_count=0`; scheduler metrics `status="degraded"`,
  `scheduler_running=true`, `job_count=51`, `success_count_24h=2594`,
  `failure_count_24h=0`, `error_job_count=2`, and `degraded_job_count=0`.
  Roadmap item 8 is complete; the next monitoring roadmap step is item 9,
  orchestrator design from observed shared needs. No remote polling set or
  `.env` change was made.
- Item 9 design was prepared and accepted on 2026-08-17 in
  `../plans/monitoring/MONITORING_ORCHESTRATOR_DESIGN.md`. It uses three
  verified agent surfaces as evidence: remote external monitoring,
  DB-availability local agent, and scheduler-metrics local agent. The draft
  inventories the actually shared needs: stable agent identity, bounded
  status vocabulary, freshness/staleness, evidence gaps, safe aggregate
  projections, single-writer/lifecycle proof, incident/report references, and
  shadow comparison workflow. The proposed orchestrator is located on the
  supervision workstation and v1 is limited to read-only correlation over
  center-owned audit summaries, file-only sanitized snapshots, and later
  separately approved GET-only facade reads. Roadmap item 9 is complete. The
  next approved implementation scope is file-only/shadow-only orchestrator CLI
  over sanitized sample snapshots. No runtime orchestrator, live polling,
  scheduling, remote polling-set change, `.env` change, delivery, provider
  execution, process control, remediation, or alert replacement was added.
- Item 9 file-only CLI source was implemented locally on 2026-08-17.
  `monitoring_agent/orchestrator.py` defines the static registry,
  normalized snapshots, bounded correlation findings, freshness/status
  handling, sanitized payload digesting, duplicate-key fail-closed behavior,
  `.env` source rejection, and v1 correlation rules.
  `monitoring_agent/orchestrator_cli.py` provides
  `python -m monitoring_agent.orchestrator_cli run` over supplied sanitized
  files only. Supported payload kinds are `agent_snapshot_v1`,
  `local_agent_facade_v1`, and `remote_agent_audit_v8`. Source verification
  returned `8 passed` for `tests/test_monitoring_agent_orchestrator.py` and
  `49 passed` for the focused orchestrator/shadow/local-agent/facade set.
  This source was later extended by the 2026-08-18 remote-audit timestamp
  wrapper; no live polling, scheduling, remote `.env` or polling-set change,
  delivery, provider execution, process control, remediation, or alert
  replacement was added.
- Item 9 remote-audit timestamp wrapper was added locally on 2026-08-18.
  `monitoring_agent/orchestrator_export_cli.py` provides
  `python -m monitoring_agent.orchestrator_export_cli wrap-remote-audit` for
  file-only wrapping of supplied sanitized remote `--audit-state` JSON with
  `captured_at`. It accepts file or stdin input, rejects `.env` paths and
  non-`agent_state_audit` payloads, and writes only a copied wrapped JSON
  output. The orchestrator remote-audit parser now uses `captured_at` before
  falling back to `checked_at` or `generated_at`. No live polling, scheduling,
  remote `.env` or polling-set change, delivery, provider execution, process
  control, remediation, or alert replacement was added.
- Item 9 local-only file preflight ran on 2026-08-18. The shared local runner
  refreshed local sanitized state and returned DB availability `status="ok"`
  plus scheduler metrics `status="degraded"`, `failure_count_24h=0`,
  `error_job_count=2`, and `job_count=51`.
  `scripts/export_monitoring_orchestrator_local_inputs.py` exported local
  facade aggregate snapshots to
  `artifacts/monitoring/orchestrator/2026-08-18-file-only-pilot/`, and
  `python -m monitoring_agent.orchestrator_cli run` over the local-only
  registry wrote `orchestrator-local-preflight.json` and
  `orchestrator-local-preflight.md`. The result was `status="degraded"` with
  two fresh sources, no evidence gaps, and correlation
  `scheduler_historical_error_states_no_recent_failures`. This is not the
  full three-surface pilot; the current remote `--audit-state` JSON from the
  supervision station is still required.
- Item 9 full three-surface file-only pilot completed on 2026-08-18 after the
  supervision station supplied a sanitized audit-v8 `--audit-state` JSON. The
  orchestrator full registry consumed `external_health`,
  `database_availability`, and `scheduler_metrics` from files only and wrote
  `artifacts/monitoring/orchestrator/2026-08-18-file-only-pilot/orchestrator-full-pilot.json`
  plus `.md`. Result: three fresh sources, `external_health status="ok"` with
  evidence gaps `heartbeat_transition_history_not_persisted` and
  `source_timestamp_missing`, DB availability `status="ok"` with no evidence
  gaps, scheduler metrics `status="degraded"` with no evidence gaps,
  `failure_count_24h=0`, `error_job_count=2`, and `job_count=51`. Overall
  status was `degraded`; the only correlation was
  `scheduler_historical_error_states_no_recent_failures`. The remote audit
  latest heartbeat was healthy with nine latest observations and zero latest
  transport failures; shadow incidents remained `mode="shadow_only"` and
  `delivery_enabled=false`, with two pending outbox intents. No live polling,
  deployment, scheduling, remote `.env` or polling-set change, delivery,
  provider execution, process control, remediation, or alert replacement was
  added.
- Item 9 captured-audit rerun completed on 2026-08-18. The same supplied
  remote audit was wrapped with `captured_at` and the file-only pilot was
  rerun, writing
  `artifacts/monitoring/orchestrator/2026-08-18-file-only-pilot/orchestrator-full-pilot-captured.json`
  plus `.md`. Result: overall `status="degraded"` remained unchanged,
  `external_health status="ok"` retained only
  `heartbeat_transition_history_not_persisted`,
  `database_availability status="ok"` had no evidence gaps, and
  `scheduler_metrics status="degraded"` had no evidence gaps with correlation
  `scheduler_historical_error_states_no_recent_failures`. Verification
  returned `18 passed` for focused orchestrator/export/helper tests,
  `190 passed` for the broader monitoring-agent/local-agent set, Python
  compileall passed, and `git diff --check` passed.
- Item 9 standalone Git publication completed on 2026-08-21. The remote
  station failure `No module named monitoring_agent.orchestrator_export_cli`
  was caused by trying to run the wrapper before the new module existed in the
  standalone checkout. Commit
  `f6583d80a77695b3f4a094337251c6835b389b59` was pushed to
  `https://github.com/mtravnicekarmex/monitoring-agent-0.8.1.git` on
  `master`. It adds `monitoring_agent/orchestrator.py`,
  `monitoring_agent/orchestrator_cli.py`,
  `monitoring_agent/orchestrator_export_cli.py`, updates README, and
  regenerates the 25-file Git manifest with SHA-256
  `37e2967efa4edbf5cfcfdeaa5a9bb8e073ef417fd2499ed058cf7085a8daf61b`.
  Temporary standalone verification compiled the package, loaded wrapper
  help, wrapped a sample stdin audit with `captured_at`, and verified all
  manifest-declared hashes. The supervision station then verified the pull:
  `git rev-parse HEAD` returned
  `f6583d80a77695b3f4a094337251c6835b389b59`,
  `run_monitoring_agent.py --check-config` returned endpoint count 9, env
  contract 2, and mode `test`, and
  `monitoring_agent.orchestrator_export_cli wrap-remote-audit` wrote
  `remote-audit.json` with `event="agent_state_audit"`,
  `audit_contract_version=8`, and
  `captured_at="2026-08-21T05:21:19.603716Z"`.
- Item 9 f6583d80 runtime sample completed on 2026-08-21 after a 180-second
  wait. `MonitoringAgentTest` was `Running`; audit-v8 latest heartbeat was
  `healthy` with nine latest observations and zero latest transport failures.
  Endpoint sequence, retry contract, attempt bounds, timing budget, and
  single-writer history were valid. The current run was open as expected and
  had 9,999 observations. Historical lifecycle artifacts remained visible:
  `unclean_restart_count=3`, `start_while_prior_run_open_count=3`,
  `abandoned_unclosed_run_count=2`, and `cycle_sequence_valid=false`.
  Shadow incidents remained disabled for delivery and shadow-only, but now
  reported `active_state_count=1`, `resolved_state_count=2`, `state_count=3`,
  `outbox_pending_count=11`, and update time
  `2026-08-21T05:28:14.530041+00:00`.
- Current continuous runtime: `0.8.1-test` runs on the separate Windows 11
  supervision center through Scheduled Task `MonitoringAgentTest`. The task
  uses one `AtStartup` trigger, `SYSTEM`, the exact project-local Python 3.14
  virtual environment and working directory, `IgnoreNew`, `StartWhenAvailable`,
  and one-minute failure restarts. It contains no credential, URL, or `.env`
  value on its command line. The complete platform repository remains absent
  from the center.
- Retained 0.7 integrity and four-endpoint configuration history: the verified
  13-file ZIP SHA-256 is
  `0BA56B60FD8F5A229346D565FEA33F58F57F9239FE541F216C07E79E56D7BF20`;
  manifest SHA-256 is
  `39C06473793C92FB281D509C3468493E9562CF9CDB74F27DBEA4D249C4676ACB`.
  Archive and extracted-content verification passed with no real `.env`.
  Configuration migration retained the existing credential, state path, and
  all non-endpoint values while changing only the ordered endpoint set to
  `live`, `ready`, `system_scheduler`, and `system_runtime`.
- Facade/runtime proof: the monitored workstation was restarted through its
  supported boot-created FastAPI/Caddy boundary. The authenticated new System
  Runtime route returned HTTP 200 with the expected schema, runtime status
  `ok`, five expected listeners with none non-OK, and no temporary listener.
  One controlled 0.7 cycle produced four successes, and audit v6 validated
  retained observation-contract-2/set-1 history plus new
  observation-contract-3/set-2 history without rewriting it.
- Supervision restart proof: before reboot, 0.7 closed cleanly with eight
  starts and eight stops. After the 2026-08-06 reboot, the task started one
  logical `SYSTEM` writer. Windows exposes it as a two-process venv
  launcher/interpreter tree; this is not a second writer. The first lifecycle
  write arrived roughly 110 seconds after task launch, so postboot checks must
  require fresh state rather than task state alone.
- Last retained 0.7 aggregate before migration: audit v6 reached 1,389
  complete cycles: 1,313 healthy, 71 partial failure, and 5 unreachable.
  Transport totals were 4,430 success, 12 connection error, 50 timeout, and 68
  schema error. The latest four-observation heartbeat was degraded with two
  failures because the new target runtime schema was incompatible with the
  deployed 0.7 client. Lifecycle was nine starts, eight stops, one active run,
  zero unclean restarts, and zero abandoned runs. Historical concurrent-start
  and process-run-reentry counts remain one each from immutable pre-lock
  history and did not increment.
- Local 0.8.1 candidate: eight authenticated GET-only facade projections now
  cover liveness, readiness, system scheduler, detailed scheduler, runtime,
  database, proxy, and SmartFuelPass health. A ninth direct external-web probe
  runs without the facade bearer, follows no redirect, reads no body, and
  retains no URL or headers. Environment contract 2, observation contract 4 /
  endpoint set 3, and audit contract 7 retain exact compatibility with sets 1
  and 2. The original 0.8.0 ZIP SHA-256 was
  `29BEE64FEE267F1E74BE1AA89CA621E2930262E16C0C662580DA5D2B7EBF8EF0`;
  manifest SHA-256 is
  `282DFDDA162B4D4CB2C3CE656066D47E2B03504F1434277659E20CBCBB173ADF`.
  The original 0.8.0 bundle is superseded and must not be deployed. 0.8.1 adds
  a strict env-v1/contract-3/set-2 bridge before env-v2/contract-4/set-3 while
  preserving the existing credential, state, timing, and endpoint identity.
  Its focused matrix passed 192 tests. ZIP SHA-256 is
  `D17A88A10814D4CC645AD731B5C2B56B3B662E0662547ED9FCEA3443EF876884`;
  manifest SHA-256 is
  `18A3E477E724EEA61F3EFDCBE303BEBE4DC298A4D646D37FE643D6CD9C49CBB1`.
- Target activation proof: the supported 2026-08-06 restart recovered all
  expected services/listeners and scheduler state, activated all eight facade
  paths, and produced repeated complete HTTP-200 route sequences from the
  still-running remote 0.7 observer. The later client audit showed those HTTP
  responses did not constitute schema recovery. Runtime, database, and proxy
  safe payloads are `ok`. The SmartFuelPass application payload was later
  changed on 2026-08-10 to represent the manual Excel import path instead of
  the retired Cloudflare/browser import error.
- Superseded 0.7 remote audit finding: lifecycle remained valid with no
  unclean/abandoned run, but the latest 0.7 heartbeat was degraded and history
  added 68 schema errors because deployed 0.7 expected the former full System
  Runtime schema. Do not restore excluded server fields and do not deploy
  0.8.0.
- Remote bundle and repository status: the transferred 0.8.1 ZIP was later
  revalidated on the supervision center with the reviewed SHA-256. The
  standalone GitHub repository
  `https://github.com/mtravnicekarmex/monitoring-agent-0.8.1.git` was public
  at commit `02a90a4ae887867d20819e4b2b618d86f750c48d`; its original 0.8.1
  manifest SHA-256 matched
  `18A3E477E724EEA61F3EFDCBE303BEBE4DC298A4D646D37FE643D6CD9C49CBB1`.
  On 2026-08-14 the user switched the test iteration workflow from
  per-change ZIP bundles to direct Git pulls. Commit
  `5cfc5916d3e83cdcc1eecd34f3f2719d62ec351c` was pushed to `master` with the
  local item 2-5 candidate source. Commit
  `86ee42b058c74675976904c1e51a2f3677c5f138` was then pushed to `master` with
  item 6 draft/fallback interpretation source and regenerated manifest files.
  Commit `3e7b94e9045527a1254b10066a3a34493577f025` was then pushed to
  `master` with item 7 shadow-pilot comparison source and regenerated
  manifest files. Commit `207fc1d38d066cdc642dc86bc0cc0b2b6c817cfc` was then
  pushed to `master` with item 7 runtime shadow incident persistence, audit
  contract 8, and a 21-file Git manifest SHA-256
  `4011bb7de330b30371199123dca41aabaaddecd267293dadf990c91f57445287`. Commit
  `e23f5f893d76951995a8b6df833e60aadb96a858` was then pushed to `master` with
  the env-v2 external-web URL fix and a 21-file Git manifest SHA-256
  `b15c3d6288352c051a30e5693ea710b19b826d7c62bd6e803be0b79163e7d113`. The
  supervision station pulled and proved
  `e23f5f893d76951995a8b6df833e60aadb96a858`; `--check-config` stayed valid
  with endpoint count 9 / env contract 2 / test mode, foreground `--once`
  created `incident_state.json`, and audit-v8 after Scheduled Task restart
  retained a healthy nine-observation latest heartbeat, zero latest transport
  failures, `shadow_incidents.present=true`, and a running task. The original
  ZIP identity is historical release evidence only until a new bundle is
  explicitly built.
- Follow-up commit `3c6502c74d478a7518d3bbc37f7799951bbbaba4` was then pushed
  to `master` with `monitoring_agent/shadow_pilot_cli.py`,
  transition-record/event JSON parser helpers, README usage, and a 22-file
  Git manifest SHA-256
  `f10e0392b2e294956f522f62df270859fad7c153ba4dee6a7fbac2fbba760c11`. The
  supervision station pulled and verified it on 2026-08-17: `--check-config`
  stayed valid with env contract 2 / nine endpoints / test mode, audit-v8
  latest heartbeat was `healthy`, latest observations were nine with zero
  transport failures, current-run observation count was 315, and
  `shadow_incidents` remained present, `shadow_only`, delivery-disabled, and
  empty of active state/outbox items.
- Item 7 source preflight: `monitoring_agent/shadow_pilot.py` compares
  supplied sanitized monitoring-agent and legacy-alert detection/recovery
  events over one reviewed period. It reports matched detections,
  confirmation delay, recoveries, recovery delay, duplicate counts/rates,
  false positives, false negatives, agent/legacy-only recoveries, and blind
  spots with `mode="shadow_only"`. It does not read `.env`, inspect DBs, poll
  endpoints, call providers, send email, mutate state, control processes, or
  suppress/replace alerts. Focused shadow tests passed with 10 tests; the
  broader monitoring-agent matrix passed with 165 tests.
- Item 7 comparison CLI source: `python -m monitoring_agent.shadow_pilot_cli`
  exports comparable agent events from an explicit `incident_state.json` and
  compares them with supplied sanitized `legacy_alert` event JSON for a
  reviewed start-inclusive/end-exclusive period. It can write requested JSON
  and Markdown review outputs only; it does not read `.env`, inspect
  production DBs/mailboxes, poll endpoints, send email, claim outbox items,
  call providers, mutate state, control processes, remediate, or replace
  alerts. Focused shadow-pilot tests now pass with 13 tests; the
  `tests/test_monitoring_agent*.py` matrix passes with 159 tests.
- Local legacy DB-availability exporter:
  `scripts/export_database_availability_shadow_events.py` produces sanitized
  `legacy_alert` JSON from delivered rows in
  `core/scheduler/data/database_availability.sqlite3`. It maps delivered
  `unavailable`/`recovered` events to `alerted`/`resolved` for
  `endpoint:system_database`, omits raw `reason` text, does not read `.env`,
  does not send email, and does not mutate the SQLite store. Local inspection
  found six delivered historical DB-availability events, all outside the
  current shadow-runtime period; current scheduler logs did not show matching
  alert/error patterns. Exporter/CLI/shadow tests passed with `15 passed`.
- Remote no-event baseline comparison: on 2026-08-17 the supervision station
  ran `shadow_pilot_cli compare` for
  `2026-08-17T07:00:00+00:00 <= event < 2026-08-17T07:35:00+00:00` with
  agent events exported from `incident_state.json` and an explicitly empty
  sanitized `legacy_alert` event file. The generated report timestamp was
  `2026-08-17T07:52:10.639549+00:00`; all detection, recovery, duplicate,
  false-positive, false-negative, and blind-spot counts were zero. This is a
  healthy current-alert baseline proof.
- Remote synthetic comparison mechanics proof: on 2026-08-17 the supervision
  station ran a file-only synthetic comparison for
  `2026-08-17T08:00:00+00:00 <= event < 2026-08-17T09:00:00+00:00`. It
  proved matched detections 1, false positives 1, false negatives 1, matched
  recoveries 1, duplicate counts 0/0, blind spots 0/0/0, and both
  confirmation/recovery delay as agent later by 60 seconds. The report
  timestamp was `2026-08-17T08:07:12.386903+00:00` and retained the safety
  boundary that legacy alerts remain authoritative.
- Runtime shadow source update 2026-08-17:
  `monitoring_agent/runtime_shadow.py` applies deterministic incident
  lifecycle state after each completed polling cycle and persists bounded
  `incident_state.json` in the agent-owned state directory. The runtime
  summary is printed as `shadow_incidents` and audit contract 8 exposes only
  aggregate counts with `mode="shadow_only"` and `delivery_enabled=false`.
  The polling loop does not claim/send outbox items, call providers, mutate
  the target, control processes, remediate, or suppress/replace alerts. Local
  verification passed with `91 passed` for targeted runtime-shadow/agent
  tests and `169 passed` for the broader monitoring-agent matrix. The
  standalone Git commit is
  `207fc1d38d066cdc642dc86bc0cc0b2b6c817cfc`
  (`Wire shadow incident persistence`), manifest SHA-256
  `4011bb7de330b30371199123dca41aabaaddecd267293dadf990c91f57445287`. This
  activation attempt exposed the env-v2 external-web URL source bug described
  above. Follow-up standalone commit
  `e23f5f893d76951995a8b6df833e60aadb96a858`
  (`Load external web URL for env v2`), manifest SHA-256
  `b15c3d6288352c051a30e5693ea710b19b826d7c62bd6e803be0b79163e7d113`, was
  pulled and verified on the supervision station. Foreground `--once`
  completed one nine-observation success cycle and wrote shadow state at
  `2026-08-17T06:57:39.941598+00:00`. After `MonitoringAgentTest` restarted,
  audit-v8 showed the task `Running`, latest heartbeat `healthy`, zero latest
  transport failures, current-run observation count 27, and shadow state
  updated at `2026-08-17T07:00:53.832229+00:00`.
- Test-stage stop authorization: the user accepts a one-time planned
  observation discontinuity and hard termination if no Ctrl+C console is
  available. Preserve state and qualify any resulting abandoned/unclean 0.7
  run as migration evidence. Manual `.env` transfer is allowed without
  displaying its contents.
- Executed stop: the only two Python processes formed the expected Session-0
  launcher/interpreter tree. The elevated fail-closed stop required the old
  `.env`, exact ZIP hash, both process identities, and parent/child relation;
  afterward the exact targets and all Python processes were absent.
- Current remote 0.8.1 proof: the new clean state directory
  `monitoring-agent-state-ops002` is the intentional state baseline to carry
  across later agent versions. Env-v1 `--check-config`, `--once`, and
  `--audit-state` passed with four successes, one complete healthy cycle, and
  clean lifecycle. After the monitored workstation restart activated the
  timezone-aware `scheduler_detail` fix, env-v2 `--once` completed one
  nine-observation cycle with transport status `success`. Audit v7 reported
  endpoint set 3, valid endpoint and cycle order, latest heartbeat `healthy`,
  nine latest observations, zero latest transport failures, valid retry and
  attempt bounds, and clean lifecycle. The two retained env-v2 schema errors
  are historical pre-fix evidence and recovery is proved. After the 2026-08-10
  SmartFuelPass Excel-import change, the 2026-08-14 continuous proof showed
  `system_smartfuelpass` returning HTTP 200 / `success` on attempt 1.
- Continuous Scheduled Task restoration proof: on 2026-08-14 elevated
  registration in
  `C:\Users\tra\PycharmProjects\monitoring-agent-0.8.1-test` succeeded,
  `MonitoringAgentTest` remained `Running`, and `LastTaskResult=267009` /
  `0x41301` indicated a currently running task. After four retained
  startup/recovery degraded cycles, the latest endpoint summary showed all
  nine endpoint keys returned HTTP 200 / `success` on attempt 1. Audit v7
  showed first recovery at cycle 5, latest heartbeat `healthy`, nine latest
  observations, zero latest transport failures, valid retry/attempt bounds,
  valid endpoint/cycle order, clean open continuous lifecycle, and no new
  concurrent-start, run-reentry, unclean, abandoned, incomplete, or overlap
  evidence. Keep legacy alerts authoritative and automatic/production delivery
  disabled.
- Local item 2 proof: `monitoring_agent/incidents.py` implements incident-rule
  version 1 without persistence, outbox, external delivery, `.env` reads,
  network access, target mutation, or legacy-alert replacement. It
  distinguishes endpoint incidents, target-wide facade transport outage,
  observer/facade self-health problems, and supervision-center blind spots;
  defines confirmation and recovery thresholds, deterministic stale checks,
  recurrence cooldown, target-wide endpoint-noise suppression, and
  historical-evidence suppression. `monitoring_agent/README.md` records the
  rule table and lifecycle semantics; `DEC-128` records the
  no-persistence/no-delivery boundary. The next bundle identity must not reuse
  the already verified 0.8.1 hash/version.
- Local item 3 proof: `monitoring_agent/incident_store.py` implements bounded
  local `incident_state.json` persistence for normalized incident states,
  sanitized transition records, report references, and delivery-intent outbox
  items. Environment contract 3 adds explicit local bounds for observation
  records, incident states, transition records, outbox items, delivery
  attempts, retry backoff, and abandoned-claim timeout. The outbox has
  deterministic idempotency keys, pending/in-progress/sent/dead-letter state,
  due-claim state, retry backoff, and abandoned-claim recovery, but no sender
  adapter, recipients, credentials, message body, network access, or delivery
  authorization. `ObserverStore.retain_recent_observations()` keeps whole
  recent cycles and rewrites `observations.jsonl` atomically after each
  runtime cycle. `DEC-129` records the bounded-store contract.
- Local item 4 proof: `monitoring_agent/reporting.py` implements pure report
  and programming-agent prompt renderers over supplied normalized incident
  facts and optional incident-store snapshots. Reports separate verified
  facts, deterministic rule conclusions, historical qualifications/evidence
  gaps, and hypotheses, and always state that delivery is disabled. The prompt
  is explicitly draft-only, bounded, and does not authorize command execution,
  network contact, state mutation, process control, delivery, or legacy-alert
  replacement. Redaction covers likely secret assignments, bearer values, URL
  query/fragment content, Windows user paths, and synthetic private
  identifiers. `DEC-130` records the pure draft/report contract.
- Item 5 delivery proof: `monitoring_agent/delivery.py` implements a
  disabled-by-default test-only adapter over incident outbox items. Disabled
  mode does not claim outbox items or mutate state. Enabled mode is restricted
  to `mode="test"`, `DELIVERY_TEST_RECIPIENT`, an in-memory recipient
  allowlist derived from that same value, supplied report text by
  `report_reference`, and explicit transport object. Sanitized results exclude
  raw recipients, sender, credentials, message bodies, and transport exception
  text. The only operator SMTP backend is `send_email_outlook()` through
  `OutlookEmailTransport`; it mirrors the Office365 STARTTLS alarm-email
  pattern using `O_EMAIL` and `O_APP` for login/default sender, accepts
  `EMAIL`/`APP` only as compatibility fallback, and was verified only with
  fake SMTP. `monitoring_agent/delivery_cli.py` provides optional recipient
  hashing diagnostics, synthetic local outbox preparation, dry-run without
  claim, and confirmed `send-due`; real send requires
  `--confirm SEND_TEST_DELIVERY`, exact `report_reference`,
  `DELIVERY_TEST_RECIPIENT`, `O_EMAIL`, `O_APP`, and a sanitized report file.
  Delivery-test recipient variables use `DELIVERY_TEST_*`, not
  `MONITORING_AGENT_*`, to avoid the strict runtime schema; the polling
  runtime validates only `MONITORING_AGENT_*` keys, so these non-prefixed
  delivery keys may remain in the same local `.env`. On 2026-08-14 the
  supervision station verified Git commit
  `5cfc5916d3e83cdcc1eecd34f3f2719d62ec351c`, `hash-recipient` printed only
  the configured recipient hash, `prepare-synthetic` created one isolated
  `endpoint:system_database` outbox item/report, `dry-run` returned
  `due_count=1`, and the explicitly confirmed `send-due` returned
  `status="sent"`, `action="opened"`, `attempt_count=1`, and no error code.
  A follow-up dry-run for the same `idempotency_key` returned `due_count=0`,
  proving the synthetic item was no longer pending for re-send.
  `DEC-131` records the disabled/test-only delivery boundary; `DEC-133`
  records the controlled send proof and remaining limits.
- Local item 6 proof: `monitoring_agent/interpretation.py` implements
  interpretation contract version 1 over supplied
  `MonitoringReportSnapshot` objects. It invokes only an injected provider,
  only when `InterpretationPolicy(enabled=True, mode="draft")` is supplied,
  and only when the deterministic report snapshot contains at least one
  active confirmed incident. Candidate-only evidence, disabled policy, missing
  provider, provider exception, invalid output, or unsafe provider output all
  fall back to the deterministic report. The policy records provider/model
  names, timeout, cost ceiling, prompt/output bounds, and item-count bounds,
  but all permission-style flags for network, state mutation, process
  control, delivery, and alert suppression must remain false. The module adds
  no `.env` keys, no provider credentials, no network client, no polling-loop
  integration, and no state writes. Results include prompt hash/length and
  sanitized hypotheses/read-only checks/evidence gaps only. `DEC-134` records
  the draft/fallback interpretation boundary.
- Restrictions: no further external delivery without separate approval, no
  automatic delivery, no real interpretation provider execution without
  separate approval, no general process control, no manual jobs,
  application/database writes, or replacement of current alerts. The earlier
  exact 0.7 process-tree hard stop was a one-time authorized test-migration
  exception and is closed. Do not launch foreground continuous mode or `--once`
  while the task is running; `--check-config` and `--audit-state` remain safe
  concurrent commands.
- Open gates: credential rotation, independent observation of the supervision
  center, reporting review UI, real interpretation provider execution,
  production delivery channels, and any legacy alert replacement.
- Updated: 2026-08-21

## PLY-002 - Plynomery long high usage alert timing

- Status: source implemented and locally verified; pending whole-workstation
  restart and post-restart verification.
- Trigger contract: existing `LONG_HIGH_USAGE` remains the plynomery sustained
  high-usage event type. It opens after eight consecutive scores above the
  configured z-score threshold, but the stored event starts at the first
  qualifying score in that run.
- Alert contract: plynomery alert-rule duration is inclusive. A rule with
  `min_duration_minutes=30` matches an event whose stored duration is exactly
  30 minutes.
- Implemented source scope:
  `moduly/mereni/plynomery/plynomery_events.py`,
  `moduly/mereni/plynomery/database/outlier_review_apply.py`, and
  `moduly/mereni/plynomery/alerting/service.py`.
- Verification before restart: new and directly affected plynomery tests
  passed with `14 passed`; broader adjacent regression for plynomery,
  outlier-review, scheduler, dashboard alerting, and API authorization passed
  with `304 passed`; production Python compile passed; `git diff --check`
  passed with line-ending normalization warnings only.
- Not done: no production database row was intentionally changed, no
  historical event backfill was run, no alert email was sent, and no alert
  rule or recipient configuration was changed by this source update.
- Next after restart: verify the full runtime stack, wait for one post-boot
  plynomery quarter-hour pipeline cycle, confirm the loaded source exposes the
  corrected helper behavior, and leave historical backfill/email delivery out
  of scope unless separately approved.
- Updated: 2026-08-11
