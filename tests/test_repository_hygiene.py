from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ALLOWED_ROOT_FILES = {
    ".env",
    ".env.example",
    ".gitattributes",
    ".gitignore",
    "AGENTS.md",
    "Caddyfile",
    "main.py",
    "requirements-api.txt",
    "requirements-production.in",
    "requirements-production.lock.txt",
    "requirements-security.in",
    "requirements-security.lock.txt",
    "start_api_dashboard.bat",
}


def test_repository_root_contains_only_approved_files():
    root_files = {path.name for path in PROJECT_ROOT.iterdir() if path.is_file()}

    assert root_files <= ALLOWED_ROOT_FILES, (
        "Move unexpected root files into the narrowest appropriate subdirectory: "
        f"{sorted(root_files - ALLOWED_ROOT_FILES)}"
    )
