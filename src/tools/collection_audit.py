from __future__ import annotations

import argparse
import asyncio
import csv
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from src.collector import (
    CollectorPlatform,
    fetch_douyin_collection_via_browser,
    fetch_douyin_favorites_via_browser,
)
from src.interface import Collection, CollectsDetail


class CollectionAuditError(RuntimeError):
    """Raised when an audit cannot safely produce a comparison."""


@dataclass(slots=True)
class CollectionAuthor:
    sec_uid: str
    uid: str = ""
    unique_id: str = ""
    nickname: str = ""
    account_url: str = ""
    aweme_count: int = 0
    sample_aweme_id: str = ""
    status: str = "missing"
    existing_mark: str = ""


def _text(value: Any) -> str:
    return str(value or "").strip()


def account_key_from_url(value: Any) -> str:
    """Return the stable identifier from a Douyin ``/user/<id>`` URL."""

    url = _text(value)
    if not url:
        return ""
    try:
        path = urlsplit(url).path
    except ValueError:
        path = url.split("?", 1)[0].split("#", 1)[0]
    parts = [unquote(part).strip() for part in path.split("/") if part.strip()]
    for index, part in enumerate(parts[:-1]):
        if part.lower() == "user":
            return parts[index + 1]
    return ""


def extract_collection_authors(items: list[dict]) -> list[CollectionAuthor]:
    """Collapse collection works into unique authors while preserving order."""

    authors: dict[str, CollectionAuthor] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        author = item.get("author")
        if not isinstance(author, dict):
            continue
        sec_uid = _text(author.get("sec_uid"))
        if not sec_uid:
            continue
        record = authors.get(sec_uid)
        if record is None:
            record = CollectionAuthor(
                sec_uid=sec_uid,
                uid=_text(author.get("uid")),
                unique_id=_text(author.get("unique_id")),
                nickname=_text(author.get("nickname")),
                account_url=f"https://www.douyin.com/user/{sec_uid}",
                sample_aweme_id=_text(item.get("aweme_id")),
            )
            authors[sec_uid] = record
        record.aweme_count += 1
    return list(authors.values())


def _account_index(rows: list[dict]) -> dict[str, dict]:
    index: dict[str, dict] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = account_key_from_url(row.get("url"))
        if key and key not in index:
            index[key] = row
    return index


def compare_collection_authors(
    authors: list[CollectionAuthor],
    active_rows: list[dict],
    deleted_rows: list[dict],
) -> list[CollectionAuthor]:
    """Classify authors as active, deleted, or missing from FetchShelf."""

    active = _account_index(active_rows)
    deleted = _account_index(deleted_rows)
    for author in authors:
        row = active.get(author.sec_uid)
        if row is not None:
            author.status = "active"
            author.existing_mark = _text(row.get("mark"))
            continue
        row = deleted.get(author.sec_uid)
        if row is not None:
            author.status = "deleted"
            author.existing_mark = _text(row.get("mark"))
            continue
        author.status = "missing"
        author.existing_mark = ""
    return authors


async def fetch_collection_items(
    *,
    parameter,
    collect_id: str,
    cookie: str,
    proxy: str | None,
    limit: int,
    page_size: int = 20,
    browser_only: bool = False,
) -> tuple[list[dict], str]:
    """Fetch well beyond the monitor's 60-work safety cap for one-off audits."""

    target = max(1, min(int(limit), 2000))
    count = max(1, min(int(page_size), 20))
    max_pages = max(1, min(300, ((target + count - 1) // count) * 3))
    cursor = 0
    items: list[dict] = []
    seen_aweme_ids: set[str] = set()
    direct_failed = False

    if browser_only:
        browser_items = await fetch_douyin_collection_via_browser(
            collect_id=collect_id,
            cookie=cookie,
            proxy=proxy,
            limit=target,
        )
        return browser_items[:target], "browser"

    for page_index in range(max_pages):
        collector = CollectsDetail(
            parameter,
            cookie=cookie,
            proxy=proxy,
            collects_id=collect_id,
            pages=1,
            cursor=cursor,
            count=count,
        )
        try:
            page_items = await collector.run(single_page=True)
        except Exception:  # noqa: BLE001 - browser fallback handles direct failures
            direct_failed = True
            break
        if collector.last_request_error is not None:
            direct_failed = True
            break
        if not isinstance(page_items, list):
            page_items = []

        for item in page_items:
            if not isinstance(item, dict):
                continue
            aweme_id = _text(item.get("aweme_id"))
            if aweme_id and aweme_id in seen_aweme_ids:
                continue
            if aweme_id:
                seen_aweme_ids.add(aweme_id)
            items.append(item)
            if len(items) >= target:
                break

        next_cursor = collector.cursor
        if (
            len(items) >= target
            or collector.finished
            or next_cursor == cursor
            or page_index + 1 >= max_pages
        ):
            break
        cursor = next_cursor

    if direct_failed:
        browser_items = await fetch_douyin_collection_via_browser(
            collect_id=collect_id,
            cookie=cookie,
            proxy=proxy,
            limit=target,
        )
        return browser_items[:target], "browser"
    return items[:target], "direct"


async def fetch_favorite_items(
    *,
    parameter,
    cookie: str,
    proxy: str | None,
    limit: int,
    page_size: int = 20,
    browser_only: bool = False,
) -> tuple[list[dict], str]:
    """Fetch the signed-in account's general favorite-work feed."""

    target = max(1, min(int(limit), 2000))
    count = max(1, min(int(page_size), 20))
    max_pages = max(1, min(300, ((target + count - 1) // count) * 3))
    cursor = 0
    items: list[dict] = []
    seen_aweme_ids: set[str] = set()
    direct_failed = False

    if browser_only:
        browser_items = await fetch_douyin_favorites_via_browser(
            cookie=cookie,
            proxy=proxy,
            limit=target,
        )
        return browser_items[:target], "browser"

    for page_index in range(max_pages):
        collector = Collection(
            parameter,
            cookie=cookie,
            proxy=proxy,
            pages=1,
            cursor=cursor,
            count=count,
        )
        try:
            page_items = await collector.run(single_page=True)
        except Exception:  # noqa: BLE001 - browser fallback handles direct failures
            direct_failed = True
            break
        if collector.last_request_error is not None:
            direct_failed = True
            break
        if not isinstance(page_items, list):
            page_items = []

        for item in page_items:
            if not isinstance(item, dict):
                continue
            aweme_id = _text(item.get("aweme_id"))
            if aweme_id and aweme_id in seen_aweme_ids:
                continue
            if aweme_id:
                seen_aweme_ids.add(aweme_id)
            items.append(item)
            if len(items) >= target:
                break

        next_cursor = collector.cursor
        if (
            len(items) >= target
            or collector.finished
            or next_cursor == cursor
            or page_index + 1 >= max_pages
        ):
            break
        cursor = next_cursor

    if direct_failed:
        browser_items = await fetch_douyin_favorites_via_browser(
            cookie=cookie,
            proxy=proxy,
            limit=target,
        )
        return browser_items[:target], "browser"
    return items[:target], "direct"


def select_monitor(
    schedules: list[dict],
    *,
    collect_id: str = "",
    schedule_id: str = "",
) -> dict:
    monitors = [
        item
        for item in schedules
        if isinstance(item, dict)
        and _text(item.get("schedule_type")) == "collect_monitor"
    ]
    if schedule_id:
        monitors = [
            item for item in monitors if _text(item.get("schedule_id")) == schedule_id
        ]
    if collect_id:
        monitors = [
            item for item in monitors if _text(item.get("collect_id")) == collect_id
        ]
    if not monitors:
        raise CollectionAuditError("没有找到匹配的收藏夹监控配置。")
    if len(monitors) == 1:
        return monitors[0]
    enabled = [item for item in monitors if item.get("enabled") is True]
    if len(enabled) == 1:
        return enabled[0]
    choices = ", ".join(
        f"{_text(item.get('schedule_id'))}:{_text(item.get('collect_id'))}"
        for item in monitors
    )
    raise CollectionAuditError(
        f"匹配到多个收藏夹监控，请指定 --schedule-id 或 --collect-id：{choices}"
    )


def load_account_rows(settings_path: Path) -> tuple[list[dict], list[dict]]:
    try:
        payload = json.loads(settings_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as error:
        raise CollectionAuditError("无法读取 FetchShelf settings.json。") from error
    active = payload.get("accounts_urls")
    deleted = payload.get("deleted_accounts")
    return (
        active if isinstance(active, list) else [],
        deleted if isinstance(deleted, list) else [],
    )


def build_report(
    *,
    collect_id: str,
    schedule_id: str,
    requested_limit: int,
    transport: str,
    items: list[dict],
    authors: list[CollectionAuthor],
    source: str = "folder",
) -> dict:
    serialized = [asdict(author) for author in authors]
    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "collect_id": collect_id,
        "source": source,
        "schedule_id": schedule_id,
        "requested_limit": requested_limit,
        "transport": transport,
        "counts": {
            "fetched_aweme": len(items),
            "unique_authors": len(authors),
            "active": sum(author.status == "active" for author in authors),
            "deleted": sum(author.status == "deleted" for author in authors),
            "missing": sum(author.status == "missing" for author in authors),
        },
        "authors": serialized,
        "missing_authors": [
            item for item in serialized if item.get("status") == "missing"
        ],
        "deleted_authors": [
            item for item in serialized if item.get("status") == "deleted"
        ],
    }


def write_report(report: dict, output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    collect_id = _text(report.get("collect_id")) or "unknown"
    stem = f"collection-{collect_id}-audit-{stamp}"
    json_path = output_dir / f"{stem}.json"
    all_csv_path = output_dir / f"{stem}-all.csv"
    missing_csv_path = output_dir / f"{stem}-missing.csv"

    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    fields = [
        "status",
        "sec_uid",
        "nickname",
        "unique_id",
        "uid",
        "account_url",
        "aweme_count",
        "sample_aweme_id",
        "existing_mark",
    ]

    def write_csv(path: Path, rows: list[dict]) -> None:
        with path.open("w", encoding="utf-8-sig", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)

    authors = report.get("authors")
    missing = report.get("missing_authors")
    write_csv(all_csv_path, authors if isinstance(authors, list) else [])
    write_csv(missing_csv_path, missing if isinstance(missing, list) else [])
    return {
        "json": str(json_path),
        "all_csv": str(all_csv_path),
        "missing_csv": str(missing_csv_path),
    }


def default_output_dir() -> Path:
    mounted_data = Path("/mnt/data")
    if mounted_data.is_dir():
        return mounted_data / "fetchshelf-audits"
    return Path("settings") / "audits"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="审计抖音收藏夹作者是否已存在于 FetchShelf 账号池。",
    )
    parser.add_argument("--collect-id", default="", help="抖音收藏夹 ID")
    parser.add_argument("--schedule-id", default="", help="收藏夹监控任务 ID")
    parser.add_argument(
        "--source",
        choices=("folder", "favorites"),
        default="folder",
        help="审计自定义收藏夹或账号全部收藏作品（默认 folder）",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=500,
        help="最多拉取的收藏作品数，范围 1-2000（默认 500）",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=20,
        help="直连接口单页数量，范围 1-20（默认 20）",
    )
    parser.add_argument(
        "--browser-only",
        action="store_true",
        help="跳过已知会返回 403 的直连接口，直接使用浏览器采集",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=default_output_dir(),
        help="审计报告输出目录",
    )
    args = parser.parse_args(argv)
    if not 1 <= args.limit <= 2000:
        parser.error("--limit 必须在 1 到 2000 之间")
    if not 1 <= args.page_size <= 20:
        parser.error("--page-size 必须在 1 到 20 之间")
    return args


async def run_audit(args: argparse.Namespace) -> dict:
    # Importing the application lazily keeps the pure comparison helpers cheap
    # to import in tests and other tooling.
    from src.application import FetchShelf
    from src.application.main_server import APIServer

    async with FetchShelf() as downloader:
        downloader.check_config()
        await downloader.check_settings(False)
        server = APIServer(downloader.parameter, downloader.database)
        await server._configure_collector_leases()
        schedule = select_monitor(
            downloader.parameter.ui_schedules,
            collect_id=args.collect_id,
            schedule_id=args.schedule_id,
        )
        collect_id = _text(schedule.get("collect_id"))
        if args.source == "folder" and not collect_id.isdigit():
            raise CollectionAuditError("收藏夹监控中的 collect_id 无效。")

        async def operation(worker, credentials, _selected_identity_id):
            cookie = server._resolve_runtime_douyin_cookie(credentials.cookie)
            if not cookie:
                raise CollectionAuditError("没有可用的抖音 Cookie。")
            proxy = (
                credentials.proxy
                or _text(getattr(worker.parameter, "proxy", ""))
                or None
            )
            if args.source == "favorites":
                items, transport = await fetch_favorite_items(
                    parameter=worker.parameter,
                    cookie=cookie,
                    proxy=proxy,
                    limit=args.limit,
                    page_size=args.page_size,
                    browser_only=args.browser_only,
                )
            else:
                items, transport = await fetch_collection_items(
                    parameter=worker.parameter,
                    collect_id=collect_id,
                    cookie=cookie,
                    proxy=proxy,
                    limit=args.limit,
                    page_size=args.page_size,
                    browser_only=args.browser_only,
                )
            return {"items": items, "transport": transport}, 1, 0

        fetched, selected_identity_id, selected_by = (
            await server._execute_collector_operation(
                platform=CollectorPlatform.DOUYIN,
                target_type=(
                    "favorites_audit" if args.source == "favorites" else "collect_audit"
                ),
                target_key=(
                    "self-favorites" if args.source == "favorites" else collect_id
                ),
                identity_id=_text(schedule.get("identity_id")),
                cookie=_text(schedule.get("cookie")),
                proxy=_text(schedule.get("proxy")),
                operation=operation,
                failure_error_code="collection_audit_failed",
            )
        )
        items = fetched.get("items") if isinstance(fetched, dict) else []
        if not isinstance(items, list):
            items = []
        transport = _text(fetched.get("transport")) or "unknown"
        active_rows, deleted_rows = load_account_rows(downloader.settings.path)
        authors = compare_collection_authors(
            extract_collection_authors(items),
            active_rows,
            deleted_rows,
        )
        report = build_report(
            collect_id=("favorites" if args.source == "favorites" else collect_id),
            schedule_id=_text(schedule.get("schedule_id")),
            requested_limit=args.limit,
            transport=transport,
            items=items,
            authors=authors,
            source=args.source,
        )
        report["routing"] = {
            "selected_identity_id": selected_identity_id,
            "selected_by": selected_by,
        }
        report["files"] = write_report(report, args.output_dir)
        return report


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = asyncio.run(run_audit(args))
    except (CollectionAuditError, KeyboardInterrupt) as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        return 1
    except Exception as error:  # noqa: BLE001 - keep credentials out of CLI failures
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": f"收藏夹审计失败：{type(error).__name__}",
                },
                ensure_ascii=False,
            )
        )
        return 1

    print(
        json.dumps(
            {
                "ok": True,
                "collect_id": report["collect_id"],
                "source": report["source"],
                "transport": report["transport"],
                "counts": report["counts"],
                "files": report["files"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
