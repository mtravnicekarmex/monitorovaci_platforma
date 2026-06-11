from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CADDYFILE_PATH = PROJECT_ROOT / "Caddyfile"
START_SCRIPT_PATH = PROJECT_ROOT / "start_api_dashboard.bat"


def test_public_dashboard_routes_api_and_streamlit_separately():
    source = CADDYFILE_PATH.read_text(encoding="utf-8")

    assert "monitoring.armexholding.cz {" in source
    assert source.index("handle /api/*") < source.index("handle {")
    assert "reverse_proxy 127.0.0.1:8000" in source
    assert "reverse_proxy 127.0.0.1:8001" in source
    assert "tls internal" not in source
    assert ":8080" not in source


def test_start_script_uses_program_files_caddy_after_backend_health_checks():
    source = START_SCRIPT_PATH.read_text(encoding="utf-8")

    assert 'set "CADDY_DIR=C:\\Program Files\\Caddy"' in source
    assert 'set "CADDY_EXE=%CADDY_DIR%\\caddy.exe"' in source
    assert 'set "CADDY_CONFIG=%CADDY_DIR%\\Caddyfile"' in source
    assert 'if /I "%~1"=="caddy" goto run_caddy' in source
    assert "http://127.0.0.1:8000/health/live" in source
    assert "http://127.0.0.1:8001/_stcore/health" in source
    assert source.index("http://127.0.0.1:8001/_stcore/health") < source.index(
        'start "Monitoring Caddy"'
    )
    assert (
        '"%CADDY_EXE%" validate --config "%CADDY_CONFIG%" --adapter caddyfile'
        in source
    )
    assert (
        '"%CADDY_EXE%" reload --config "%CADDY_CONFIG%" --adapter caddyfile '
        "--address 127.0.0.1:2019"
        in source
    )
    assert (
        '"%CADDY_EXE%" run --config "%CADDY_CONFIG%" --adapter caddyfile'
        in source
    )
