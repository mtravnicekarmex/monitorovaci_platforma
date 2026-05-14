from __future__ import annotations

import re


LOG_RECORD_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3} \| ")
ERROR_LOG_RECORD_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3} \| ERROR \| ")


def extract_error_log_blocks(content: str, *, max_blocks: int = 8) -> tuple[str, ...]:
    if not content or max_blocks <= 0:
        return ()

    blocks: list[str] = []
    current_block: list[str] | None = None
    for line in content.splitlines():
        starts_record = LOG_RECORD_RE.match(line) is not None
        starts_error = ERROR_LOG_RECORD_RE.match(line) is not None

        if starts_error:
            if current_block:
                blocks.append("\n".join(current_block))
            current_block = [line]
            continue

        if starts_record:
            if current_block:
                blocks.append("\n".join(current_block))
                current_block = None
            continue

        if current_block is not None:
            current_block.append(line)

    if current_block:
        blocks.append("\n".join(current_block))

    return tuple(blocks[-max_blocks:])
