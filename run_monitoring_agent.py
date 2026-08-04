from __future__ import annotations

from pathlib import Path

from monitoring_agent.__main__ import main


if __name__ == "__main__":
    raise SystemExit(
        main(default_env_file=Path(__file__).resolve().with_name(".env"))
    )
