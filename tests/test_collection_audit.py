from pathlib import Path

import pytest

from src.tools import collection_audit
from src.tools.collection_audit import (
    CollectionAuthor,
    account_key_from_url,
    build_report,
    compare_collection_authors,
    extract_collection_authors,
    load_account_rows,
    select_monitor,
    write_report,
)


def test_extract_and_compare_collection_authors():
    items = [
        {
            "aweme_id": "w1",
            "author": {
                "sec_uid": "sec-active",
                "uid": "1",
                "unique_id": "active-user",
                "nickname": "Active",
            },
        },
        {
            "aweme_id": "w2",
            "author": {"sec_uid": "sec-active", "nickname": "Active"},
        },
        {
            "aweme_id": "w3",
            "author": {"sec_uid": "sec-deleted", "nickname": "Deleted"},
        },
        {
            "aweme_id": "w4",
            "author": {"sec_uid": "sec-missing", "nickname": "Missing"},
        },
        {"aweme_id": "ignored", "author": {}},
    ]
    authors = extract_collection_authors(items)
    compared = compare_collection_authors(
        authors,
        [{"url": "https://www.douyin.com/user/sec-active?showTab=post", "mark": "A"}],
        [{"url": "https://www.douyin.com/user/sec-deleted/", "mark": "D"}],
    )

    assert [item.sec_uid for item in compared] == [
        "sec-active",
        "sec-deleted",
        "sec-missing",
    ]
    assert [item.status for item in compared] == ["active", "deleted", "missing"]
    assert compared[0].aweme_count == 2
    assert compared[0].existing_mark == "A"


def test_account_key_and_monitor_selection():
    assert account_key_from_url("https://www.douyin.com/user/a%2Db/?foo=1") == "a-b"
    schedules = [
        {
            "schedule_type": "collect_monitor",
            "schedule_id": "S1",
            "collect_id": "11",
            "enabled": False,
        },
        {
            "schedule_type": "collect_monitor",
            "schedule_id": "S2",
            "collect_id": "22",
            "enabled": True,
        },
    ]
    assert select_monitor(schedules)["schedule_id"] == "S2"
    assert select_monitor(schedules, collect_id="11")["schedule_id"] == "S1"


def test_report_files_and_settings_loading(tmp_path: Path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        '{"accounts_urls":[{"url":"https://www.douyin.com/user/a"}],'
        '"deleted_accounts":[{"url":"https://www.douyin.com/user/b"}]}',
        encoding="utf-8",
    )
    active, deleted = load_account_rows(settings_path)
    assert len(active) == 1
    assert len(deleted) == 1

    authors = [
        CollectionAuthor(
            sec_uid="missing",
            account_url="https://www.douyin.com/user/missing",
            aweme_count=1,
        )
    ]
    report = build_report(
        collect_id="123",
        schedule_id="S1",
        requested_limit=500,
        transport="browser",
        items=[{"aweme_id": "1"}],
        authors=authors,
    )
    files = write_report(report, tmp_path / "reports")

    assert report["counts"]["missing"] == 1
    assert Path(files["json"]).is_file()
    assert Path(files["all_csv"]).is_file()
    assert Path(files["missing_csv"]).read_text(encoding="utf-8-sig").startswith(
        "status,sec_uid"
    )


@pytest.mark.asyncio
async def test_fetch_collection_items_can_exceed_monitor_limit(monkeypatch):
    class FakeCollector:
        def __init__(self, _parameter, **kwargs):
            self.input_cursor = kwargs["cursor"]
            self.count = kwargs["count"]
            self.cursor = self.input_cursor
            self.finished = False
            self.last_request_error = None

        async def run(self, single_page=False):
            assert single_page is True
            start = self.input_cursor
            self.cursor = start + self.count
            self.finished = self.cursor >= 160
            return [
                {"aweme_id": str(index), "author": {"sec_uid": f"s{index}"}}
                for index in range(start, self.cursor)
            ]

    monkeypatch.setattr(collection_audit, "CollectsDetail", FakeCollector)
    items, transport = await collection_audit.fetch_collection_items(
        parameter=object(),
        collect_id="123",
        cookie="session=value",
        proxy=None,
        limit=125,
        page_size=20,
    )

    assert transport == "direct"
    assert len(items) == 125
    assert items[-1]["aweme_id"] == "124"


@pytest.mark.asyncio
async def test_fetch_collection_items_uses_browser_fallback(monkeypatch):
    class FailingCollector:
        def __init__(self, _parameter, **_kwargs):
            self.cursor = 0
            self.finished = False
            self.last_request_error = RuntimeError("403")

        async def run(self, single_page=False):
            return []

    async def browser_fetch(**kwargs):
        assert kwargs["limit"] == 80
        return [{"aweme_id": str(index)} for index in range(80)]

    monkeypatch.setattr(collection_audit, "CollectsDetail", FailingCollector)
    monkeypatch.setattr(
        collection_audit,
        "fetch_douyin_collection_via_browser",
        browser_fetch,
    )
    items, transport = await collection_audit.fetch_collection_items(
        parameter=object(),
        collect_id="123",
        cookie="session=value",
        proxy=None,
        limit=80,
    )

    assert transport == "browser"
    assert len(items) == 80


@pytest.mark.asyncio
async def test_fetch_favorite_items_can_exceed_monitor_limit(monkeypatch):
    class FakeCollection:
        def __init__(self, _parameter, **kwargs):
            self.input_cursor = kwargs["cursor"]
            self.count = kwargs["count"]
            self.cursor = self.input_cursor
            self.finished = False
            self.last_request_error = None

        async def run(self, single_page=False):
            assert single_page is True
            start = self.input_cursor
            self.cursor = start + self.count
            self.finished = self.cursor >= 180
            return [
                {"aweme_id": str(index), "author": {"sec_uid": f"s{index}"}}
                for index in range(start, self.cursor)
            ]

    monkeypatch.setattr(collection_audit, "Collection", FakeCollection)
    items, transport = await collection_audit.fetch_favorite_items(
        parameter=object(),
        cookie="session=value",
        proxy=None,
        limit=150,
        page_size=20,
    )

    assert transport == "direct"
    assert len(items) == 150
    assert items[-1]["aweme_id"] == "149"
