from __future__ import annotations

import argparse
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import subprocess
import sys


DEFAULT_MAX_BYTES = 10 * 1024 * 1024
DEFAULT_BACKUP_COUNT = 10


def _default_log_directory() -> Path:
    program_data = os.environ.get("PROGRAMDATA")
    if program_data:
        return Path(program_data) / "monitorovaci_platforma" / "logs"
    return Path(__file__).resolve().parents[1] / "runtime_logs"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a child process and retain its combined output in rotating logs."
    )
    parser.add_argument("--log-name", required=True)
    parser.add_argument("--log-dir", type=Path, default=_default_log_directory())
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    parser.add_argument("--backup-count", type=int, default=DEFAULT_BACKUP_COUNT)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    return parser


def _normalized_command(command: list[str]) -> list[str]:
    resolved = list(command)
    if resolved and resolved[0] == "--":
        resolved = resolved[1:]
    if not resolved:
        raise ValueError("A child command is required after '--'.")
    return resolved


def _build_logger(
    *,
    log_path: Path,
    max_bytes: int,
    backup_count: int,
) -> logging.Logger:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(f"monitoring.runtime.{log_path.stem}.{os.getpid()}")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    handler = RotatingFileHandler(
        log_path,
        maxBytes=max(1, int(max_bytes)),
        backupCount=max(1, int(backup_count)),
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s | %(message)s"))
    logger.addHandler(handler)
    return logger


def _close_logger(logger: logging.Logger) -> None:
    for handler in list(logger.handlers):
        handler.flush()
        handler.close()
        logger.removeHandler(handler)


def run_logged_process(
    command: list[str],
    *,
    log_path: Path,
    max_bytes: int = DEFAULT_MAX_BYTES,
    backup_count: int = DEFAULT_BACKUP_COUNT,
) -> int:
    resolved_command = _normalized_command(command)
    logger = _build_logger(
        log_path=log_path,
        max_bytes=max_bytes,
        backup_count=backup_count,
    )
    logger.info("process_start executable=%s", Path(resolved_command[0]).name)

    try:
        process = subprocess.Popen(
            resolved_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
    except OSError:
        logger.exception("process_launch_failed")
        _close_logger(logger)
        raise

    assert process.stdout is not None
    try:
        try:
            for line in process.stdout:
                logger.info("%s", line.rstrip("\r\n"))
            return_code = process.wait()
        except KeyboardInterrupt:
            process.terminate()
            try:
                return_code = process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                return_code = process.wait()
    finally:
        process.stdout.close()

    logger.info("process_exit code=%s", return_code)
    _close_logger(logger)
    return int(return_code)


def main() -> int:
    args = _build_parser().parse_args()
    try:
        command = _normalized_command(args.command)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    return run_logged_process(
        command,
        log_path=args.log_dir / f"{args.log_name}.log",
        max_bytes=args.max_bytes,
        backup_count=args.backup_count,
    )


if __name__ == "__main__":
    raise SystemExit(main())
