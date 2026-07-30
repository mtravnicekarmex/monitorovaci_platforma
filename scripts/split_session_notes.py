"""Split the legacy SESSION_NOTES log into lossless monthly archives.

The script treats every dated level-three heading and its following content as
one immutable entry block. It verifies the block count and SHA-256 multiset
before writing anything. Archive files may add a small header, but entry blocks
are emitted byte-for-byte from the decoded source text.
"""

from __future__ import annotations

import argparse
import hashlib
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = PROJECT_ROOT / "agents" / "history" / "SESSION_NOTES.md"
DEFAULT_ARCHIVE_DIR = PROJECT_ROOT / "agents" / "history" / "archive"

SESSION_LOG_HEADING = "## Session Log"
ENTRY_RE = re.compile(r"^### (?P<date>\d{4}-\d{2}-\d{2})(?:\s|$)")


@dataclass(frozen=True)
class Entry:
    date: str
    source_order: int
    text: str

    @property
    def month(self) -> str:
        return self.date[:7]

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()


def parse_source(source_text: str) -> tuple[str, list[Entry]]:
    lines = source_text.splitlines(keepends=True)
    try:
        session_log_index = next(
            index
            for index, line in enumerate(lines)
            if line.rstrip("\r\n") == SESSION_LOG_HEADING
        )
    except StopIteration as exc:
        raise ValueError(f"Missing {SESSION_LOG_HEADING!r}") from exc

    preamble = "".join(lines[:session_log_index])
    log_lines = lines[session_log_index + 1 :]
    starts: list[tuple[int, str]] = []
    for index, line in enumerate(log_lines):
        match = ENTRY_RE.match(line)
        if match:
            starts.append((index, match.group("date")))

    if not starts:
        raise ValueError("No dated session entries found")

    leading = "".join(log_lines[: starts[0][0]])
    if leading.strip():
        raise ValueError("Unexpected non-empty content before first session entry")

    entries: list[Entry] = []
    for source_order, (start, date) in enumerate(starts):
        end = starts[source_order + 1][0] if source_order + 1 < len(starts) else len(log_lines)
        entries.append(
            Entry(
                date=date,
                source_order=source_order,
                text="".join(log_lines[start:end]),
            )
        )
    return preamble, entries


def build_monthly_archives(entries: list[Entry]) -> dict[str, str]:
    grouped: dict[str, list[Entry]] = defaultdict(list)
    for entry in entries:
        grouped[entry.month].append(entry)

    archives: dict[str, str] = {}
    for month, month_entries in sorted(grouped.items()):
        ordered = sorted(month_entries, key=lambda entry: (entry.date, entry.source_order))
        header = (
            f"# Session archive: {month}\n\n"
            "This file contains immutable session-log entries extracted from "
            "`../SESSION_NOTES.md`.\n"
            "Entries are ordered by date; entries sharing a date retain their "
            "original relative order.\n\n"
        )
        archives[month] = header + "".join(entry.text for entry in ordered)
    return archives


def parse_archive_entries(archive_texts: dict[str, str]) -> list[Entry]:
    parsed: list[Entry] = []
    source_order = 0
    for month, text in sorted(archive_texts.items()):
        lines = text.splitlines(keepends=True)
        starts: list[tuple[int, str]] = []
        for index, line in enumerate(lines):
            match = ENTRY_RE.match(line)
            if match:
                starts.append((index, match.group("date")))
        for position, (start, date) in enumerate(starts):
            if date[:7] != month:
                raise AssertionError(
                    f"Archive {month} contains entry dated {date}"
                )
            end = starts[position + 1][0] if position + 1 < len(starts) else len(lines)
            parsed.append(
                Entry(
                    date=date,
                    source_order=source_order,
                    text="".join(lines[start:end]),
                )
            )
            source_order += 1
    return parsed


def entry_fingerprint(entries: list[Entry]) -> Counter[str]:
    return Counter(entry.digest for entry in entries)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--archive-dir", type=Path, default=DEFAULT_ARCHIVE_DIR)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write archives. Without this flag the command is a dry run.",
    )
    args = parser.parse_args()

    source_text = args.source.read_bytes().decode("utf-8-sig")
    preamble, entries = parse_source(source_text)
    archives = build_monthly_archives(entries)
    reparsed = parse_archive_entries(archives)

    if len(entries) != len(reparsed):
        raise AssertionError(
            f"Entry count mismatch: source={len(entries)} archive={len(reparsed)}"
        )
    if entry_fingerprint(entries) != entry_fingerprint(reparsed):
        raise AssertionError("Archive entry fingerprints do not match source")

    month_counts = Counter(entry.month for entry in entries)
    print(f"source_entries={len(entries)}")
    print(f"preamble_sha256={hashlib.sha256(preamble.encode('utf-8')).hexdigest()}")
    for month in sorted(month_counts):
        print(f"{month}_entries={month_counts[month]}")
    print("entry_fingerprints=verified")

    if not args.apply:
        print("mode=dry-run")
        return 0

    args.archive_dir.mkdir(parents=True, exist_ok=True)
    for month, archive_text in archives.items():
        (args.archive_dir / f"{month}.md").write_bytes(archive_text.encode("utf-8"))

    legacy_header = (
        "# Legacy SESSION_NOTES preamble\n\n"
        "This is the pre-session-log baseline and template section preserved "
        "during the 2026-07-30 archive split.\n\n"
    )
    (args.archive_dir / "LEGACY_PREAMBLE.md").write_bytes(
        (legacy_header + preamble).encode("utf-8")
    )
    print(f"mode=apply archive_dir={args.archive_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
