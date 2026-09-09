import json

from app.borg_runner import CommandResult, parse_info, parse_list, parse_prune

INFO_JSON = json.dumps({
    "repository": {"id": "abc123", "last_modified": "2026-01-02T03:04:05.000000", "location": "ssh://backup/repo"},
    "encryption": {"mode": "repokey-blake2"},
    "cache": {
        "path": "/root/.cache/borg/abc123",
        "stats": {
            "total_chunks": 4200,
            "total_csize": 5_000_000_000,
            "total_size": 20_000_000_000,
            "total_unique_chunks": 900,
            "unique_csize": 1_200_000_000,
            "unique_size": 3_000_000_000,
        },
    },
})

LIST_JSON = json.dumps({
    "archives": [
        {"name": "host1-2026-01-01T02:00:00", "id": "id1", "time": "2026-01-01T02:00:00.000000"},
        {"name": "host1-2026-01-02T02:00:00", "id": "id2", "time": "2026-01-02T02:00:00.000000"},
        {"name": "host1-2025-12-31T02:00:00", "id": "id0", "time": "2025-12-31T02:00:00.000000"},
    ],
})

PRUNE_DRY_RUN_OUTPUT = """
Keeping archive (rule: daily #1):  host1-2026-01-02T02:00:00
Would prune:                       host1-2025-12-01T02:00:00
Would prune:                       host1-2025-11-01T02:00:00
"""


def test_parse_info_success_extracts_stats():
    info = parse_info(CommandResult(0, INFO_JSON, ""))
    assert info.ok is True
    assert info.original_size == 20_000_000_000
    assert info.compressed_size == 5_000_000_000
    assert info.deduplicated_size == 1_200_000_000


def test_parse_info_nonzero_exit_reports_error():
    info = parse_info(CommandResult(2, "", "Repository does not exist"))
    assert info.ok is False
    assert "does not exist" in info.error


def test_parse_info_malformed_json_does_not_raise():
    info = parse_info(CommandResult(0, "not json", ""))
    assert info.ok is False
    assert info.error


def test_parse_list_picks_latest_archive_by_time_not_list_order():
    archive_list = parse_list(CommandResult(0, LIST_JSON, ""))
    assert archive_list.ok is True
    assert len(archive_list.archives) == 3
    assert archive_list.latest.name == "host1-2026-01-02T02:00:00"


def test_parse_list_failure():
    archive_list = parse_list(CommandResult(1, "", "connection closed"))
    assert archive_list.ok is False
    assert archive_list.latest is None


def test_parse_prune_counts_would_prune_lines_in_dry_run():
    result = parse_prune(CommandResult(0, PRUNE_DRY_RUN_OUTPUT, ""))
    assert result.ok is True
    assert result.archives_deleted == 2


def test_parse_prune_failure_reports_error():
    result = parse_prune(CommandResult(2, "", "passphrase supplied in BORG_PASSPHRASE is incorrect"))
    assert result.ok is False
    assert result.archives_deleted == 0
    assert "incorrect" in result.error
