from scripts.split_session_notes import (
    build_monthly_archives,
    entry_fingerprint,
    parse_archive_entries,
    parse_source,
)


def test_split_preserves_every_dated_entry_exactly_once():
    source = (
        "# SESSION_NOTES.md\r\n"
        "\r\n"
        "Current baseline.\r\n"
        "\r\n"
        "## Session Log\r\n"
        "\r\n"
        "### 2026-07-02 - Later\r\n"
        "\r\n"
        "- second\r\n"
        "\r\n"
        "### 2026-06-30 - Earlier month\r\n"
        "\r\n"
        "- first\r\n"
        "\r\n"
        "### 2026-07-01 - Earlier July entry\r\n"
        "\r\n"
        "- middle\r\n"
    )

    preamble, entries = parse_source(source)
    archives = build_monthly_archives(entries)
    reparsed = parse_archive_entries(archives)

    assert preamble == "# SESSION_NOTES.md\r\n\r\nCurrent baseline.\r\n\r\n"
    assert set(archives) == {"2026-06", "2026-07"}
    assert archives["2026-07"].index("2026-07-01") < archives["2026-07"].index(
        "2026-07-02"
    )
    assert len(reparsed) == len(entries) == 3
    assert entry_fingerprint(reparsed) == entry_fingerprint(entries)
