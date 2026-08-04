from __future__ import annotations

import argparse
from datetime import date
import hashlib
import json
from pathlib import Path, PurePosixPath
import zipfile


BUNDLE_FILE_SOURCES = (
    (".env.example", "monitoring_agent/.env.example"),
    (".gitignore", "monitoring_agent/project.gitignore"),
    ("run_monitoring_agent.py", "run_monitoring_agent.py"),
    "monitoring_agent/__init__.py",
    "monitoring_agent/__main__.py",
    "monitoring_agent/client.py",
    "monitoring_agent/observer.py",
    "monitoring_agent/README.md",
    "monitoring_agent/settings.py",
    "monitoring_agent/store.py",
    "monitoring_agent/synthetic_server.py",
)
BUNDLE_FILES = tuple(
    item[0] if isinstance(item, tuple) else item for item in BUNDLE_FILE_SOURCES
)


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _zip_info(path: str, *, created_date: date) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(
        filename=str(PurePosixPath(path)),
        date_time=(created_date.year, created_date.month, created_date.day, 0, 0, 0),
    )
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    return info


def build_bundle(
    *,
    repository_root: Path,
    output_path: Path,
    bundle_version: str,
    created_date: date,
) -> dict[str, object]:
    root = repository_root.resolve()
    if not bundle_version.endswith("-test"):
        raise ValueError("test bundle version must end with '-test'")
    file_payloads: list[tuple[str, bytes]] = []
    manifest_files: list[dict[str, object]] = []
    for item in BUNDLE_FILE_SOURCES:
        if isinstance(item, tuple):
            archive_path, source_path = item
        else:
            archive_path = source_path = item
        source = (root / source_path).resolve()
        if not source.is_relative_to(root):
            raise ValueError("bundle source escaped repository root")
        content = source.read_bytes()
        file_payloads.append((archive_path, content))
        manifest_files.append(
            {
                "path": archive_path,
                "sha256": _sha256(content),
                "size": len(content),
            }
        )

    manifest = {
        "authentication": "local-dotenv-bearer-to-digest-verified-facade",
        "bundle_name": "monitoring-agent",
        "bundle_version": bundle_version,
        "created_date": created_date.isoformat(),
        "files": manifest_files,
        "mode": "test",
        "python": ">=3.14",
    }
    manifest_content = (
        json.dumps(manifest, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    manifest_digest_content = (
        f"{_sha256(manifest_content)}  manifest.json\n"
    ).encode("ascii")

    output = output_path.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w") as archive:
        for relative_path, content in file_payloads:
            archive.writestr(
                _zip_info(relative_path, created_date=created_date),
                content,
            )
        archive.writestr(
            _zip_info("manifest.json", created_date=created_date),
            manifest_content,
        )
        archive.writestr(
            _zip_info("manifest.sha256", created_date=created_date),
            manifest_digest_content,
        )

    return {
        "bundle_version": bundle_version,
        "file_count": len(BUNDLE_FILES),
        "output_path": str(output),
        "sha256": _sha256(output.read_bytes()),
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build the explicit-allowlist monitoring-agent test bundle."
    )
    parser.add_argument("--version", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--created-date", type=date.fromisoformat, required=True)
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    repository_root = Path(__file__).resolve().parents[1]
    result = build_bundle(
        repository_root=repository_root,
        output_path=args.output,
        bundle_version=args.version,
        created_date=args.created_date,
    )
    print(json.dumps(result, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
