from __future__ import annotations

import csv
import json

from src.tools.collection_alignment import build_alignment, write_alignment


def test_build_alignment_reports_both_directions_and_bad_rows():
    audit = {
        "collect_id": "123",
        "counts": {"fetched_aweme": 4},
        "authors": [
            {
                "sec_uid": "shared",
                "account_url": "https://www.douyin.com/user/shared",
                "nickname": "Shared",
                "aweme_count": 2,
            },
            {
                "sec_uid": "dk-only",
                "account_url": "https://www.douyin.com/user/dk-only",
                "nickname": "DK only",
                "aweme_count": 2,
            },
            {"sec_uid": ""},
        ],
    }
    settings = {
        "accounts_urls": [
            {
                "url": "https://www.douyin.com/user/shared?from=test",
                "mark": "kept",
                "enable": True,
            },
            {
                "url": "https://www.douyin.com/user/config-only",
                "mark": "outside",
                "enable": True,
            },
            {"url": "invalid"},
        ],
        "deleted_accounts": [
            {"url": "https://www.douyin.com/user/dk-only"},
        ],
    }

    report = build_alignment(audit, settings)

    assert report["counts"] == {
        "dk_authors": 2,
        "configured_targets": 2,
        "in_both": 1,
        "dk_only": 1,
        "configured_only": 1,
        "dk_previously_deleted": 1,
        "dk_duplicate_rows": 0,
        "configured_duplicate_rows": 0,
        "dk_invalid_rows": 1,
        "configured_invalid_rows": 1,
    }
    assert [row["alignment_status"] for row in report["rows"]] == [
        "both",
        "dk_only",
        "configured_only",
    ]
    assert report["rows"][0]["configured_mark"] == "kept"


def test_write_alignment_creates_filtered_csv_files(tmp_path):
    report = {
        "collect_id": "123",
        "counts": {},
        "rows": [
            {"alignment_status": "both", "sec_uid": "a"},
            {"alignment_status": "dk_only", "sec_uid": "b"},
            {"alignment_status": "configured_only", "sec_uid": "c"},
        ],
    }

    files = write_alignment(report, tmp_path)

    summary = json.loads((tmp_path / files["summary"].split("/")[-1]).read_text())
    assert "rows" not in summary
    with open(files["dk_only"], encoding="utf-8-sig", newline="") as file:
        assert [row["sec_uid"] for row in csv.DictReader(file)] == ["b"]
