from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from src.tools.collection_audit import account_key_from_url


class CollectionAlignmentError(RuntimeError):
    """Raised when an alignment report cannot be produced safely."""


ALIGNMENT_FIELDS = (
    "alignment_status",
    "sec_uid",
    "account_url",
    "nickname",
    "unique_id",
    "uid",
    "dk_aweme_count",
    "sample_aweme_id",
    "configured_mark",
    "configured_enable",
    "configured_pages",
    "configured_tab",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _load_json(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as error:
        raise CollectionAlignmentError(f"无法读取 JSON：{path}") from error
    if not isinstance(payload, dict):
        raise CollectionAlignmentError(f"JSON 顶层必须是对象：{path}")
    return payload


def build_alignment(audit: dict, settings: dict) -> dict:
    authors = audit.get("authors")
    configured = settings.get("accounts_urls")
    deleted = settings.get("deleted_accounts")
    authors = authors if isinstance(authors, list) else []
    configured = configured if isinstance(configured, list) else []
    deleted = deleted if isinstance(deleted, list) else []

    author_keys = [_text(row.get("sec_uid")) for row in authors if isinstance(row, dict)]
    configured_keys = [
        account_key_from_url(row.get("url"))
        for row in configured
        if isinstance(row, dict)
    ]
    deleted_keys = {
        account_key_from_url(row.get("url"))
        for row in deleted
        if isinstance(row, dict)
    }
    deleted_keys.discard("")

    author_counts = Counter(key for key in author_keys if key)
    configured_counts = Counter(key for key in configured_keys if key)
    author_by_key = {
        _text(row.get("sec_uid")): row
        for row in authors
        if isinstance(row, dict) and _text(row.get("sec_uid"))
    }
    configured_by_key = {
        account_key_from_url(row.get("url")): row
        for row in configured
        if isinstance(row, dict) and account_key_from_url(row.get("url"))
    }

    rows: list[dict] = []
    ordered_keys = list(author_by_key)
    ordered_keys.extend(key for key in configured_by_key if key not in author_by_key)
    for key in ordered_keys:
        author = author_by_key.get(key, {})
        target = configured_by_key.get(key, {})
        if author and target:
            status = "both"
        elif author:
            status = "dk_only"
        else:
            status = "configured_only"
        rows.append(
            {
                "alignment_status": status,
                "sec_uid": key,
                "account_url": _text(author.get("account_url"))
                or _text(target.get("url"))
                or f"https://www.douyin.com/user/{key}",
                "nickname": _text(author.get("nickname")),
                "unique_id": _text(author.get("unique_id")),
                "uid": _text(author.get("uid")),
                "dk_aweme_count": author.get("aweme_count", "") if author else "",
                "sample_aweme_id": _text(author.get("sample_aweme_id")),
                "configured_mark": _text(target.get("mark")),
                "configured_enable": target.get("enable", "") if target else "",
                "configured_pages": target.get("pages", "") if target else "",
                "configured_tab": _text(target.get("tab")),
            }
        )

    counts = {
        "dk_authors": len(author_by_key),
        "configured_targets": len(configured_by_key),
        "in_both": sum(row["alignment_status"] == "both" for row in rows),
        "dk_only": sum(row["alignment_status"] == "dk_only" for row in rows),
        "configured_only": sum(
            row["alignment_status"] == "configured_only" for row in rows
        ),
        "dk_previously_deleted": sum(key in deleted_keys for key in author_by_key),
        "dk_duplicate_rows": sum(value - 1 for value in author_counts.values()),
        "configured_duplicate_rows": sum(
            value - 1 for value in configured_counts.values()
        ),
        "dk_invalid_rows": sum(not key for key in author_keys),
        "configured_invalid_rows": sum(not key for key in configured_keys),
    }
    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "collect_id": _text(audit.get("collect_id")),
        "source_audit_generated_at": _text(audit.get("generated_at")),
        "source_fetched_aweme": (audit.get("counts") or {}).get("fetched_aweme", 0),
        "counts": counts,
        "rows": rows,
    }


def _write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=ALIGNMENT_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_alignment(report: dict, output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    stem = f"collection-{_text(report.get('collect_id')) or 'unknown'}-alignment-{stamp}"
    rows = report.get("rows") if isinstance(report.get("rows"), list) else []
    paths = {
        "summary": output_dir / f"{stem}-summary.json",
        "all": output_dir / f"{stem}-all.csv",
        "in_both": output_dir / f"{stem}-in-both.csv",
        "dk_only": output_dir / f"{stem}-dk-only.csv",
        "configured_only": output_dir / f"{stem}-configured-only.csv",
    }
    paths["summary"].write_text(
        json.dumps({key: value for key, value in report.items() if key != "rows"}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _write_csv(paths["all"], rows)
    _write_csv(
        paths["in_both"],
        [row for row in rows if row.get("alignment_status") == "both"],
    )
    _write_csv(
        paths["dk_only"],
        [row for row in rows if row.get("alignment_status") == "dk_only"],
    )
    _write_csv(
        paths["configured_only"],
        [row for row in rows if row.get("alignment_status") == "configured_only"],
    )
    return {key: str(path) for key, path in paths.items()}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="将收藏夹全量审计结果与 FetchShelf 当前账号配置做双向对齐。",
    )
    parser.add_argument("--audit-json", required=True, type=Path)
    parser.add_argument("--settings-json", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = build_alignment(
            _load_json(args.audit_json),
            _load_json(args.settings_json),
        )
        files = write_alignment(report, args.output_dir)
    except CollectionAlignmentError as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        return 1
    print(
        json.dumps(
            {"ok": True, "counts": report["counts"], "files": files},
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
