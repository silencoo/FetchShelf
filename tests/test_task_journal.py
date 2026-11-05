from asyncio import Queue
from os import utime
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.application import main_server as main_server_module
from src.application.main_server import APIServer
from src.application.main_terminal import TikTok
from src.collector import CollectorStore
from src.tools.cleaner import Cleaner
from src.webui.task_journal import TaskJournal


def _task(task_id: str = "T000001", status: str = "running") -> dict:
    return {
        "task_id": task_id,
        "endpoint": "/workflow/douyin/account_batch",
        "payload": {"use_settings": False, "items": []},
        "status": status,
        "created_at": "2026-07-28 01:00:00",
        "started_at": "2026-07-28 01:01:00",
        "finished_at": None,
        "updated_at": "2026-07-28 01:02:00",
        "retry_of": None,
        "worker": 1,
        "error": "",
        "message": "",
        "result": None,
        "pause_supported": True,
        "progress": {
            "current": 1,
            "total": 3,
            "success": 1,
            "failed": 0,
            "skipped": 0,
            "percent": 33,
            "label": "正在执行账号批次",
        },
    }


def test_task_journal_recovers_only_unfinished_account(tmp_path: Path):
    path = tmp_path / "ui_task_runtime.sqlite3"
    journal = TaskJournal(path)
    task = _task()
    journal.save_task(task)
    accounts = journal.prepare_accounts(
        task["task_id"],
        [
            {"mark": "done", "url": "https://example.test/done", "enable": True},
            {"mark": "active", "url": "https://example.test/active", "enable": True},
            {"mark": "later", "url": "https://example.test/later", "enable": True},
        ],
    )
    assert len(accounts) == 3
    journal.mark_account_running(task["task_id"], 1, identity_id="identity-a")
    journal.mark_account_finished(
        task["task_id"],
        1,
        status="success",
        identity_id="identity-a",
    )
    journal.mark_account_running(task["task_id"], 2, identity_id="identity-a")
    journal.close()

    reopened = TaskJournal(path)
    reopened.recover_interrupted()
    restored_task = reopened.load_tasks()[0]
    restored_accounts = reopened.list_accounts(task["task_id"])

    assert restored_task["status"] == "pending"
    assert restored_task["recovered_after_restart"] is True
    assert [item["status"] for item in restored_accounts] == [
        "success",
        "pending",
        "pending",
    ]
    assert reopened.account_summary(task["task_id"]) == {
        "total": 3,
        "pending": 2,
        "running": 0,
        "success": 1,
        "failed": 0,
        "skipped": 0,
    }
    reopened.close()


def test_task_journal_persists_structured_account_outcome(tmp_path: Path):
    journal = TaskJournal(tmp_path / "structured.sqlite3")
    task = _task("T000002")
    journal.save_task(task)
    journal.prepare_accounts(
        task["task_id"],
        [{"mark": "private", "url": "https://example.test/private"}],
    )
    journal.mark_account_running(task["task_id"], 1, identity_id="dy-one")
    journal.mark_account_finished(
        task["task_id"],
        1,
        status="failed",
        identity_id="dy-two",
        reason="私密账号对当前身份不可见",
        result={
            "outcome_code": "private_not_visible",
            "failure_category": "visibility",
            "retryable": True,
            "attempted_identities": [
                {"identity_id": "dy-one", "outcome_code": "private_not_visible"},
                {"identity_id": "dy-two", "outcome_code": "private_not_visible"},
            ],
        },
    )

    account = journal.list_accounts(task["task_id"])[0]
    assert account["identity_id"] == "dy-two"
    assert account["result"]["outcome_code"] == "private_not_visible"
    assert account["result"]["failure_category"] == "visibility"
    assert len(account["result"]["attempted_identities"]) == 2
    journal.close()


@pytest.mark.asyncio
async def test_restore_enqueues_pending_but_preserves_paused_task(tmp_path: Path):
    journal = TaskJournal(tmp_path / "ui_task_runtime.sqlite3")
    journal.save_task(_task("T000003", "running"))
    journal.save_task(_task("T000004", "paused"))

    server = APIServer.__new__(APIServer)
    server.task_journal = journal
    server.ui_tasks = {}
    server.ui_task_queue = Queue()
    server.ui_task_counter = 0
    server.ui_tasks_restored = False

    await server._restore_ui_tasks()

    assert server.ui_tasks["T000003"]["status"] == "pending"
    assert server.ui_tasks["T000004"]["status"] == "paused"
    assert server.ui_task_counter == 4
    assert server.ui_task_queue.get_nowait() == "T000003"
    assert server.ui_task_queue.empty()
    journal.close()


@pytest.mark.asyncio
async def test_overlap_policy_defaults_to_wait_and_skips_duplicate(tmp_path: Path):
    server = APIServer.__new__(APIServer)
    server.ui_tasks = {
        "T000001": {
            **_task("T000001", "running"),
            "schedule_id": "S000001",
        }
    }
    persisted = []
    server._persist_ui_schedules = lambda: persisted.append(True)
    server.ui_schedules = {}

    normalized = server._normalize_schedule_payload(
        {
            "schedule_id": "S000001",
            "platform": "douyin",
            "use_settings": True,
        }
    )
    normalized["schedule_id"] = "S000001"

    assert normalized["overlap_policy"] == "wait"
    action, active = await server._resolve_schedule_overlap(
        normalized,
        wait_for_slot=False,
    )
    assert action == "wait"
    assert active["task_id"] == "T000001"

    normalized["overlap_policy"] = "skip"
    action, active = await server._resolve_schedule_overlap(
        normalized,
        wait_for_slot=False,
    )
    assert action == "skip"
    assert normalized["last_result"]["reason"] == "active_task_exists"
    assert active["task_id"] == "T000001"


def test_schedule_identity_failure_notification_defaults_on():
    server = APIServer.__new__(APIServer)
    defaults = server._normalize_schedule_payload(
        {
            "platform": "douyin",
            "use_settings": True,
        }
    )
    enabled = server._normalize_schedule_payload(
        {
            "platform": "douyin",
            "use_settings": True,
            "identity_failure_action": "pause",
            "notify_on_identity_failure": True,
            "bark_url": "https://api.day.app/example",
        }
    )

    assert defaults["identity_failure_action"] == "continue"
    assert defaults["identity_failure_threshold"] == 3
    assert defaults["notify_on_identity_failure"] is True
    assert enabled["identity_failure_action"] == "pause"
    assert enabled["notify_on_identity_failure"] is True
    assert enabled["bark_url"] == "https://api.day.app/example"


def test_retry_failed_endpoint_creates_linked_failed_only_task(
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.setenv("FETCHSHELF_API_TOKEN", "journal-test-token")
    journal = TaskJournal(tmp_path / "ui_task_runtime.sqlite3")
    original = _task(status="failed")
    original["payload"] = {
        "use_settings": False,
        "items": [
            {"mark": "ok", "url": "https://example.test/ok", "enable": True},
            {"mark": "bad", "url": "https://example.test/bad", "enable": True},
        ],
    }
    journal.save_task(original)
    journal.prepare_accounts(original["task_id"], original["payload"]["items"])
    journal.mark_account_running(original["task_id"], 1)
    journal.mark_account_finished(original["task_id"], 1, status="success")
    journal.mark_account_running(original["task_id"], 2)
    journal.mark_account_finished(
        original["task_id"],
        2,
        status="failed",
        reason="network",
    )

    server = APIServer.__new__(APIServer)
    server.server = FastAPI()
    server.task_journal = journal
    server.ui_tasks = {original["task_id"]: server._hydrate_ui_task(original)}
    server.ui_task_queue = Queue()
    server.ui_task_counter = 1
    server.setup_routes()

    response = TestClient(server.server).post(
        "/ui/api/tasks/T000001/retry-failed",
        headers={"token": "journal-test-token"},
    )

    assert response.status_code == 200
    retry = server.ui_tasks["T000002"]
    assert retry["retry_of"] == "T000001"
    assert retry["retry_mode"] == "failed_only"
    assert retry["payload"]["use_settings"] is False
    assert [item["mark"] for item in retry["payload"]["items"]] == ["bad"]
    assert server.ui_task_queue.get_nowait() == "T000002"
    journal.close()


def test_failed_task_account_can_be_archived_from_future_collection(
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.setenv("FETCHSHELF_API_TOKEN", "journal-test-token")
    account_url = "https://www.douyin.com/user/inactive-account?from=task"
    normalized_url = "https://www.douyin.com/user/inactive-account"
    journal = TaskJournal(tmp_path / "ui_task_runtime.sqlite3")
    task = _task(status="failed")
    task["payload"] = {
        "use_settings": False,
        "items": [{"mark": "inactive", "url": account_url, "enable": True}],
    }
    journal.save_task(task)
    journal.prepare_accounts(task["task_id"], task["payload"]["items"])
    journal.mark_account_running(task["task_id"], 1)
    journal.mark_account_finished(
        task["task_id"],
        1,
        status="failed",
        reason="账号已注销或不可访问",
        result={
            "outcome_code": "account_deleted",
            "failure_category": "account_unavailable",
        },
    )

    settings_updates = []
    assignment_deletes = []

    class FakeParameter:
        def __init__(self):
            self.accounts_urls = [
                SimpleNamespace(
                    mark="inactive",
                    url=account_url,
                    tab="post",
                    earliest="",
                    latest="",
                    enable=True,
                    auto_update_earliest=False,
                    pages=None,
                )
            ]
            self.accounts_urls_tiktok = []
            self.deleted_accounts = []
            self.deleted_accounts_tiktok = []
            self.settings = SimpleNamespace(
                update=lambda data: settings_updates.append(data)
            )

        @staticmethod
        def check_urls_params(rows):
            return [SimpleNamespace(**item) for item in rows]

        @staticmethod
        def check_deleted_accounts(rows):
            return [dict(item) for item in rows]

        def get_settings_data(self):
            return {
                "accounts_urls": [vars(item) for item in self.accounts_urls],
                "accounts_urls_tiktok": [
                    vars(item) for item in self.accounts_urls_tiktok
                ],
                "deleted_accounts": self.deleted_accounts,
                "deleted_accounts_tiktok": self.deleted_accounts_tiktok,
            }

    server = APIServer.__new__(APIServer)
    server.server = FastAPI()
    server.parameter = FakeParameter()
    server.task_journal = journal
    server.ui_tasks = {task["task_id"]: server._hydrate_ui_task(task)}
    server.ui_task_queue = Queue()
    server.ui_task_counter = 1
    server._backup_settings_file = lambda reason="manual": f"{reason}.json"
    server.collector_store = SimpleNamespace(
        delete_assignment=lambda platform, target_type, target_key: assignment_deletes.append(
            (platform.value, target_type, target_key)
        )
        or True
    )
    server.logger = SimpleNamespace(
        info=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
    )
    server.setup_routes()
    client = TestClient(server.server)

    before = client.get(
        f"/ui/api/tasks/{task['task_id']}/accounts?status=failed",
        headers={"token": "journal-test-token"},
    )
    assert before.status_code == 200
    assert before.json()["items"][0]["configured"] is True
    assert before.json()["items"][0]["platform"] == "douyin"

    archived = client.post(
        "/ui/api/accounts/archive",
        headers={"token": "journal-test-token"},
        json={
            "platform": "douyin",
            "url": normalized_url,
            "reason": "人工确认账号已注销",
        },
    )
    assert archived.status_code == 200
    payload = archived.json()
    assert payload["archived"] is True
    assert payload["removed_count"] == 1
    assert payload["accounts_urls"] == []
    assert payload["deleted_accounts"][0]["url"] == account_url
    assert payload["deleted_accounts"][0]["reason"] == "人工确认账号已注销"
    assert payload["deleted_accounts"][0]["enable"] is False
    assert settings_updates
    assert assignment_deletes == [("douyin", "account", normalized_url)]

    after = client.get(
        f"/ui/api/tasks/{task['task_id']}/accounts?status=failed",
        headers={"token": "journal-test-token"},
    )
    assert after.status_code == 200
    assert after.json()["items"][0]["configured"] is False
    journal.close()


def test_failed_task_accounts_can_be_archived_in_one_batch(
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.setenv("FETCHSHELF_API_TOKEN", "journal-test-token")
    first_url = "https://www.douyin.com/user/first?from=task"
    second_url = "https://www.douyin.com/user/second"
    backup_calls = []
    settings_updates = []
    assignment_deletes = []

    class FakeParameter:
        def __init__(self):
            self.accounts_urls = [
                SimpleNamespace(mark="first", url=first_url, enable=True),
                SimpleNamespace(mark="first duplicate", url=first_url, enable=True),
                SimpleNamespace(mark="second", url=second_url, enable=True),
                SimpleNamespace(
                    mark="keep",
                    url="https://www.douyin.com/user/keep",
                    enable=True,
                ),
            ]
            self.accounts_urls_tiktok = []
            self.deleted_accounts = [
                {
                    "mark": "old first",
                    "url": "https://www.douyin.com/user/first",
                    "enable": False,
                },
                {
                    "mark": "older",
                    "url": "https://www.douyin.com/user/older",
                    "enable": False,
                },
            ]
            self.deleted_accounts_tiktok = []
            self.settings = SimpleNamespace(
                update=lambda data: settings_updates.append(data)
            )

        @staticmethod
        def check_urls_params(rows):
            return [SimpleNamespace(**item) for item in rows]

        @staticmethod
        def check_deleted_accounts(rows):
            return [dict(item) for item in rows]

        def get_settings_data(self):
            return {
                "accounts_urls": [vars(item) for item in self.accounts_urls],
                "accounts_urls_tiktok": [],
                "deleted_accounts": self.deleted_accounts,
                "deleted_accounts_tiktok": [],
            }

    journal = TaskJournal(tmp_path / "ui_task_runtime.sqlite3")
    server = APIServer.__new__(APIServer)
    server.server = FastAPI()
    server.parameter = FakeParameter()
    server.task_journal = journal
    server.ui_tasks = {}
    server.ui_task_queue = Queue()
    server.ui_task_counter = 0
    server._backup_settings_file = (
        lambda reason="manual": backup_calls.append(reason) or f"{reason}.json"
    )
    server.collector_store = SimpleNamespace(
        delete_assignment=lambda platform, target_type, target_key: assignment_deletes.append(
            (platform.value, target_type, target_key)
        )
        or True
    )
    server.logger = SimpleNamespace(
        info=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
    )
    server.setup_routes()
    client = TestClient(server.server)

    response = client.post(
        "/ui/api/accounts/archive-batch",
        headers={"token": "journal-test-token"},
        json={
            "platform": "douyin",
            "urls": [first_url, second_url, second_url],
            "reason": "批量确认账号不可用",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["archived_count"] == 2
    assert payload["removed_count"] == 3
    assert payload["assignment_removed"] == 2
    assert len(backup_calls) == 1
    assert len(settings_updates) == 1
    assert [item["mark"] for item in payload["accounts_urls"]] == ["keep"]
    assert [item["mark"] for item in payload["deleted_accounts"]] == [
        "first",
        "second",
        "older",
    ]
    assert all(
        item["reason"] == "批量确认账号不可用"
        for item in payload["deleted_accounts"][:2]
    )
    assert assignment_deletes == [
        ("douyin", "account", "https://www.douyin.com/user/first"),
        ("douyin", "account", second_url),
    ]

    invalid = client.post(
        "/ui/api/accounts/archive-batch",
        headers={"token": "journal-test-token"},
        json={"platform": "douyin", "urls": []},
    )
    assert invalid.status_code == 400
    journal.close()


@pytest.mark.asyncio
async def test_account_batch_uses_persisted_snapshot_and_skips_success(
    tmp_path: Path,
):
    journal = TaskJournal(tmp_path / "ui_task_runtime.sqlite3")
    task = _task()
    task["status"] = "running"
    task["payload"] = {
        "use_settings": False,
        "cookie": "sessionid=legacy",
        "items": [
            {"mark": "done", "url": "https://example.test/done", "enable": True},
            {"mark": "next", "url": "https://example.test/next", "enable": True},
        ],
    }
    journal.save_task(task)
    journal.prepare_accounts(task["task_id"], task["payload"]["items"])
    journal.mark_account_running(task["task_id"], 1)
    journal.mark_account_finished(task["task_id"], 1, status="success")

    processed = []
    progress = []
    server = APIServer.__new__(APIServer)
    server.task_journal = journal
    server.parameter = SimpleNamespace(
        accounts_urls=[],
        accounts_urls_tiktok=[],
        earliest_update_days=3,
        auto_backfill_mark=True,
    )
    server.logger = SimpleNamespace(info=lambda *args, **kwargs: None)
    server._persist_account_runtime_updates = lambda **kwargs: None

    async def check_sec_user_id(url, tiktok=False):
        return url.rsplit("/", 1)[-1]

    async def deal_account_detail(*args, **kwargs):
        processed.append(kwargs["mark"])
        return {"mark": kwargs["mark"]}

    async def checkpoint():
        return None

    server.check_sec_user_id = check_sec_user_id
    server.deal_account_detail = deal_account_detail

    result = await server._run_ui_account_batch(
        task["payload"],
        tiktok=False,
        progress_callback=lambda value: progress.append(value.copy()),
        pause_control={
            "task_id": task["task_id"],
            "checkpoint": checkpoint,
        },
    )

    assert processed == ["next"]
    assert result.data["success"] == 2
    assert result.data["failed"] == 0
    assert progress[0]["current"] == 1
    assert progress[-1]["current"] == 2
    assert journal.account_summary(task["task_id"])["success"] == 2
    journal.close()


@pytest.mark.asyncio
async def test_cookie_less_global_batch_does_not_trigger_identity_failure(
    tmp_path: Path,
):
    server = APIServer.__new__(APIServer)
    server.collector_store = CollectorStore(tmp_path / "collector.sqlite3")
    server.parameter = SimpleNamespace(
        accounts_urls=[],
        accounts_urls_tiktok=[],
        earliest_update_days=3,
        auto_backfill_mark=True,
    )
    server.logger = SimpleNamespace(info=lambda *args, **kwargs: None)
    server._persist_account_runtime_updates = lambda **kwargs: None
    identity_failures = []

    async def check_sec_user_id(url, tiktok=False):
        return "sec-user"

    async def deal_account_detail(*args, **kwargs):
        assert kwargs["cookie"] is None
        return {"mark": kwargs["mark"]}

    async def identity_failure(identity_id, error_code, message):
        identity_failures.append((identity_id, error_code, message))
        return False

    server.check_sec_user_id = check_sec_user_id
    server.deal_account_detail = deal_account_detail
    result = await server._run_ui_account_batch(
        {
            "use_settings": False,
            "items": [
                {
                    "mark": "public-account",
                    "url": "https://www.douyin.com/user/public-account",
                    "enable": True,
                }
            ],
        },
        tiktok=False,
        pause_control={"identity_failure": identity_failure},
    )

    assert result.data["success"] == 1
    assert identity_failures == []
    server.collector_store.close()


def test_account_activity_preserves_latest_work_and_updates_last_result(
    tmp_path: Path,
):
    journal = TaskJournal(tmp_path / "ui_task_runtime.sqlite3")
    url = "https://www.douyin.com/user/activity-account"

    first = journal.save_account_activity(
        platform="douyin",
        url=url,
        sec_uid="sec-a",
        mark="activity",
        latest_seen_work_at="2026-07-20T10:00:00+08:00",
        latest_seen_work_id="newest",
        latest_saved_work_at="2026-07-20T10:00:00+08:00",
        latest_saved_work_id="newest",
        status="success",
        item_count=8,
    )
    second = journal.save_account_activity(
        platform="douyin",
        url=url,
        latest_seen_work_at="2026-07-18T10:00:00+08:00",
        latest_seen_work_id="older",
        status="failed",
        error="temporary network error",
        item_count=0,
    )

    assert first["latest_seen_work_id"] == "newest"
    assert second["latest_seen_work_id"] == "newest"
    assert second["latest_saved_work_id"] == "newest"
    assert second["last_status"] == "failed"
    assert second["last_error"] == "temporary network error"
    assert second["last_success_at"]
    assert second["last_failure_at"]
    assert journal.list_account_activity("douyin") == [second]
    journal.close()


def test_latest_account_work_supports_douyin_tiktok_and_extracted_rows():
    douyin = TikTok._latest_account_work(
        [
            {"create_time": 100, "aweme_id": "older"},
            {"create_time": 200, "aweme_id": "douyin-new"},
        ],
        tiktok=False,
    )
    tiktok = TikTok._latest_account_work(
        [
            {"createTime": "250", "id": "tiktok-new"},
            {"createTime": "bad", "id": "ignored"},
        ],
        tiktok=True,
    )
    extracted = TikTok._latest_account_work(
        [
            {"create_timestamp": 300, "id": "saved-new"},
            {"create_timestamp": 150, "id": "saved-old"},
        ],
        tiktok=False,
        extracted=True,
    )

    assert douyin["id"] == "douyin-new"
    assert tiktok["id"] == "tiktok-new"
    assert extracted["id"] == "saved-new"
    assert douyin["at"]
    assert tiktok["at"]
    assert extracted["at"]


def test_account_board_search_and_latest_sort_use_activity_index(
    tmp_path: Path,
):
    journal = TaskJournal(tmp_path / "ui_task_runtime.sqlite3")
    alpha_url = "https://www.douyin.com/user/alpha"
    beta_url = "https://www.douyin.com/user/beta"
    journal.save_account_activity(
        platform="douyin",
        url=alpha_url,
        mark="Alpha",
        latest_seen_work_at="2026-07-20T10:00:00+08:00",
        latest_seen_work_id="alpha-work",
        status="success",
        item_count=2,
    )
    journal.save_account_activity(
        platform="douyin",
        url=beta_url,
        mark="Beta Creator",
        latest_seen_work_at="2026-07-28T10:00:00+08:00",
        latest_seen_work_id="beta-work",
        status="failed",
        error="rate limited",
    )

    server = APIServer.__new__(APIServer)
    server.task_journal = journal
    server._active_account_rows = lambda platform: [
        {"url": alpha_url, "mark": "Alpha", "tab": "post", "enable": True},
        {"url": beta_url, "mark": "Beta Creator", "tab": "post", "enable": True},
        {
            "url": "https://www.douyin.com/user/gamma",
            "mark": "Gamma",
            "tab": "favorite",
            "enable": True,
        },
    ]
    server._load_account_board_avatars = lambda: {}
    server._scope_root = lambda scope: tmp_path
    server._account_board_dirs = lambda root: []
    server._load_account_board_pins = lambda: {}
    server._match_account_board_dir = lambda **kwargs: None
    server._pick_account_board_media = lambda **kwargs: {
        "path": "",
        "kind": "",
        "pinned": False,
    }

    searched = server._build_account_board_page(
        "douyin",
        1,
        24,
        search="beta",
    )
    sorted_page = server._build_account_board_page(
        "douyin",
        1,
        24,
        sort_by="latest_desc",
    )

    assert searched["unfiltered_total"] == 3
    assert searched["total"] == 1
    assert searched["items"][0]["url"] == beta_url
    assert searched["items"][0]["last_status"] == "failed"
    assert [item["url"] for item in sorted_page["items"][:2]] == [
        beta_url,
        alpha_url,
    ]
    assert sorted_page["items"][0]["latest_work_id"] == "beta-work"
    journal.close()


def test_account_board_can_sort_by_matched_folder_update_time(
    tmp_path: Path,
):
    older_dir = tmp_path / "UID100_Alpha_发布作品"
    newer_dir = tmp_path / "UID200_Beta_发布作品"
    older_dir.mkdir()
    newer_dir.mkdir()
    utime(older_dir, (1_700_000_000, 1_700_000_000))
    utime(newer_dir, (1_800_000_000, 1_800_000_000))

    server = APIServer.__new__(APIServer)
    server.task_journal = None
    server._active_account_rows = lambda platform: [
        {
            "url": "https://www.douyin.com/user/alpha",
            "mark": "Alpha",
            "tab": "post",
            "enable": True,
        },
        {
            "url": "https://www.douyin.com/user/beta",
            "mark": "Beta",
            "tab": "post",
            "enable": True,
        },
        {
            "url": "https://www.douyin.com/user/missing",
            "mark": "Missing",
            "tab": "post",
            "enable": True,
        },
    ]
    server._load_account_board_avatars = lambda: {}
    server._scope_root = lambda scope: tmp_path
    server._account_board_dirs = lambda root: [older_dir, newer_dir]
    server.parameter = SimpleNamespace(
        CLEANER=SimpleNamespace(filter_name=lambda value, _: value),
    )
    server._load_account_board_pins = lambda: {}
    server._match_account_board_dir = lambda mark, **kwargs: {
        "Alpha": older_dir,
        "Beta": newer_dir,
    }.get(mark)
    server._pick_account_board_media = lambda **kwargs: {
        "path": "",
        "kind": "",
        "pinned": False,
    }

    page = server._build_account_board_page(
        "douyin",
        1,
        24,
        sort_by="folder_updated_desc",
    )

    assert page["sort"] == "folder_updated_desc"
    assert [item["mark"] for item in page["items"]] == [
        "Beta",
        "Alpha",
        "Missing",
    ]
    assert page["items"][0]["folder_updated_at"] > page["items"][1]["folder_updated_at"]
    assert page["items"][2]["folder_updated_at"] == ""


def test_account_board_gallery_is_recursive_filterable_and_account_scoped(
    tmp_path: Path,
):
    account_url = "https://www.douyin.com/user/gallery-account"
    account_dir = tmp_path / "UID123_GalleryAccount_发布作品"
    nested_dir = account_dir / "图集"
    nested_dir.mkdir(parents=True)
    image_path = nested_dir / "2026-08-27_image.jpg"
    video_path = account_dir / "2026-08-28_video.mp4"
    ignored_path = account_dir / "notes.txt"
    image_path.write_bytes(b"image")
    video_path.write_bytes(b"video")
    ignored_path.write_text("ignored", encoding="utf-8")
    utime(image_path, (1_800_000_000, 1_800_000_000))
    utime(video_path, (1_900_000_000, 1_900_000_000))

    server = APIServer.__new__(APIServer)
    server._find_active_account_row = lambda platform, url: (
        {"url": account_url, "mark": "GalleryAccount"}
        if url == account_url
        else None
    )
    server._scope_root = lambda scope: tmp_path
    server._account_board_dirs = lambda root: [account_dir]
    server._account_board_dir_mark_index = lambda candidates: {}
    server._account_board_mark_candidates = lambda mark, index: [account_dir]

    gallery = server._build_account_board_gallery(
        "douyin",
        account_url,
        1,
        24,
    )
    images = server._build_account_board_gallery(
        "douyin",
        account_url,
        1,
        24,
        media_kind="image",
    )

    assert gallery["folder_found"] is True
    assert gallery["folder_path"] == account_dir.name
    assert gallery["total"] == 2
    assert gallery["image_total"] == 1
    assert gallery["video_total"] == 1
    assert gallery["truncated"] is False
    assert gallery["index_limit"] == 10_000
    assert [item["kind"] for item in gallery["items"]] == ["video", "image"]
    assert images["total"] == 1
    assert images["items"][0]["path"].endswith("图集/2026-08-27_image.jpg")

    with pytest.raises(LookupError, match="account_not_found"):
        server._build_account_board_gallery(
            "douyin",
            "https://www.douyin.com/user/not-configured",
            1,
            24,
        )


@pytest.mark.asyncio
async def test_avatar_batch_does_not_fall_back_to_video_when_images_exist(
    tmp_path: Path,
    monkeypatch,
):
    account_dir = tmp_path / "UID123_Test"
    account_dir.mkdir()
    image_path = account_dir / "post.jpg"
    video_path = account_dir / "post.mp4"
    image_path.write_bytes(b"image")
    video_path.write_bytes(b"video")
    generated_from = []

    def fail_generation(source: Path, output: Path):
        generated_from.append(source)
        raise RuntimeError("no face")

    monkeypatch.setattr(
        main_server_module,
        "generate_face_avatar",
        fail_generation,
    )
    server = APIServer.__new__(APIServer)
    server._active_account_rows = lambda platform: [
        {
            "url": "https://www.douyin.com/user/test",
            "mark": "Test",
        }
    ]
    server._scope_root = lambda scope: tmp_path
    server._account_board_dirs = lambda root: [account_dir]
    server._load_account_board_avatars = lambda: {}
    server._match_account_board_dir = lambda **kwargs: account_dir
    server._collect_media_relpaths = lambda *args: (
        ["UID123_Test/post.jpg"],
        ["UID123_Test/post.mp4"],
    )
    server._account_avatar_output_path = lambda **kwargs: tmp_path / "avatar.jpg"

    result = await server._run_ui_avatar_batch(
        {
            "platform": "douyin",
            "skip_existing": False,
            "max_candidates": 12,
        }
    )

    assert generated_from == [image_path]
    assert result.data["failed"] == 1
    assert result.data["media_policy"] == "image_first_video_only_when_no_images"


@pytest.mark.asyncio
async def test_avatar_batch_uses_video_only_when_account_has_no_images(
    tmp_path: Path,
    monkeypatch,
):
    account_dir = tmp_path / "UID456_VideoOnly"
    account_dir.mkdir()
    video_path = account_dir / "post.mp4"
    video_path.write_bytes(b"video")
    generated_from = []

    def generate(source: Path, output: Path):
        generated_from.append(source)
        return {"faces_detected": 1, "source_kind": "video"}

    monkeypatch.setattr(main_server_module, "generate_face_avatar", generate)
    server = APIServer.__new__(APIServer)
    server._active_account_rows = lambda platform: [
        {
            "url": "https://www.douyin.com/user/video-only",
            "mark": "VideoOnly",
        }
    ]
    server._scope_root = lambda scope: tmp_path
    server._account_board_dirs = lambda root: [account_dir]
    server._load_account_board_avatars = lambda: {}
    server._match_account_board_dir = lambda **kwargs: account_dir
    server._collect_media_relpaths = lambda *args: (
        [],
        ["UID456_VideoOnly/post.mp4"],
    )
    server._account_avatar_output_path = lambda **kwargs: tmp_path / "avatar.jpg"
    server._set_account_avatar_path = lambda *args: "avatars/video-only.jpg"
    monkeypatch.setattr(
        main_server_module,
        "relative_path",
        lambda root, target: "avatars/video-only.jpg",
    )

    result = await server._run_ui_avatar_batch(
        {
            "platform": "douyin",
            "skip_existing": False,
            "max_candidates": 12,
        }
    )

    assert generated_from == [video_path]
    assert result.data["success"] == 1
    assert result.data["failed"] == 0


def test_board_outcomes_survive_upgrade_and_attention_skips_media(tmp_path):
    path = tmp_path / "journal.sqlite3"
    with TaskJournal(path) as journal:
        journal.save_account_activity(platform="douyin", url="legacy", status="success")
        journal.connection.execute("ALTER TABLE ui_account_activity DROP COLUMN last_outcome_code")
        journal.connection.commit()
    with TaskJournal(path) as journal:
        for url, status, code in [
            ("active", "success", "success"),
            ("quiet", "success", "no_matching_items"),
            ("empty", "skipped", "no_works"),
            ("blocked", "failed", "private_not_visible"),
        ]:
            journal.save_account_activity(platform="douyin", url=url, status=status, outcome_code=code)
        activity = {a["url"]: APIServer._board_outcome(a) for a in journal.list_account_activity("douyin")}
        assert activity == {
            "legacy": "legacy_success", "active": "success", "quiet": "no_updates",
            "empty": "skipped", "blocked": "failed",
        }
        server = APIServer.__new__(APIServer)
        server.task_journal = journal
        server._active_account_rows = lambda platform: [{"url": url} for url in [*activity, "unchecked"]]
        server._scope_root = lambda scope: tmp_path
        server._load_account_board_avatars = server._load_account_board_pins = lambda: {}
        server._board_folder_index = lambda root: pytest.fail("Attention should not scan media")
        page = server._build_account_board_page("douyin", 1, 24, status="attention")
        assert {row["url"]: row["outcome"] for row in page["items"]} == {
            "empty": "skipped", "blocked": "failed", "unchecked": "never",
        }


def test_board_reuses_folder_index_and_queries_activity_for_visible_page(tmp_path, monkeypatch):
    server = APIServer.__new__(APIServer)
    server.parameter = SimpleNamespace(CLEANER=Cleaner())
    server._active_account_rows = lambda platform: [{"url": str(i)} for i in range(2750)]
    server._scope_root = lambda scope: tmp_path
    server._load_account_board_pins = server._load_account_board_avatars = lambda: {}
    scans = []
    original_scan = server._account_board_dirs
    def scan(root):
        scans.append(root)
        return original_scan(root)
    server._account_board_dirs = scan
    with TaskJournal(tmp_path / "db") as journal:
        server.task_journal = journal
        requests = []
        original = journal.list_account_activity
        def activity(platform, urls=None):
            requests.append(urls)
            return original(platform, urls)
        monkeypatch.setattr(journal, "list_account_activity", activity)
        for page in (1, 2):
            server._build_account_board_page("douyin", page, 24)
        assert requests == [[str(i) for i in range(24)], [str(i) for i in range(24, 48)]]
        assert len(scans) == 1
        (tmp_path / "UID-new").mkdir()
        assert (tmp_path / "UID-new") in server._board_folder_index(tmp_path)[0]
        assert len(scans) == 2


def test_recovery_honors_pause_cancel_and_old_pending_tasks(tmp_path):
    with TaskJournal(tmp_path / "journal.db") as journal:
        for i, status in enumerate(["pausing", "canceling", "running", "success"], 1):
            journal.save_task(_task(f"T{i:06d}", status))
        journal.recover_interrupted()
        all_tasks = {task["task_id"]: task for task in journal.load_tasks()}
        assert all_tasks["T000001"]["status"] == "paused"
        assert all_tasks["T000002"]["status"] == "canceled"
        assert all_tasks["T000002"]["finished_at"]
        assert all_tasks["T000003"]["status"] == "pending"
        assert {t["task_id"] for t in journal.load_tasks(limit=1)} == {
            "T000001", "T000003", "T000004",
        }


def test_large_task_checkpoint_pages_export_and_retry(tmp_path, monkeypatch):
    monkeypatch.setenv("FETCHSHELF_API_TOKEN", "journal-test-token")
    with TaskJournal(tmp_path / "journal.db") as journal:
        server = APIServer.__new__(APIServer)
        server.server = FastAPI()
        server.task_journal = journal
        task = _task(status="partial_success")
        journal.save_task(task)
        journal.prepare_accounts(task["task_id"], ({"url": f"https://example.test/{i}"} for i in range(5003)))
        with journal.connection:
            journal.connection.execute("UPDATE ui_task_accounts SET status = 'failed', reason = 'network'")
        server.ui_tasks = {task["task_id"]: server._hydrate_ui_task(task)}
        server.ui_task_queue = Queue()
        server.ui_task_counter = 1
        server._account_rows = lambda tiktok: []
        server.setup_routes()
        client = TestClient(server.server, headers={"token": "journal-test-token"})
        base = "/ui/api/tasks/T000001"
        last = client.get(base + "/accounts?page=26&page_size=200").json()
        assert last["filtered_total"] == 5003
        assert [r["position"] for r in last["items"]] == [5001, 5002, 5003]
        offset = client.get(base + "/accounts?limit=2&offset=3").json()
        assert [r["position"] for r in offset["items"]] == [4, 5]
        assert not client.get(base + "/accounts?limit=2&offset=6000").json()["items"]
        assert client.get(base + "/accounts/export").json()["count"] == 5003
        assert client.post(base + "/retry-failed").is_success
        assert len(server.ui_tasks["T000002"]["payload"]["items"]) == 5003
        assert client.post(base + "/cancel").json()["task"]["status"] == "partial_success"


@pytest.mark.asyncio
async def test_shutdown_does_not_leave_running_worker_waiting_for_queue():
    from asyncio import Event, create_task, wait_for

    server = APIServer.__new__(APIServer)
    server.ui_task_shutdown = False
    server.ui_task_queue = Queue()
    server.ui_tasks = {"T000001": server._hydrate_ui_task(_task(status="pending"))}
    started = Event()
    async def execute(*args):
        started.set()
        await Event().wait()
    server._execute_ui_endpoint = execute
    server.ui_task_workers = [create_task(server._ui_task_worker(1))]
    server.ui_task_queue.put_nowait("T000001")
    await wait_for(started.wait(), 2)
    await wait_for(server._stop_ui_task_workers(), 2)
    assert server.ui_tasks["T000001"]["status"] == "pending"


def test_board_keeps_covers_and_only_replaces_the_requested_account(tmp_path, monkeypatch):
    monkeypatch.setenv("FETCHSHELF_API_TOKEN", "board-test-token")
    server = APIServer.__new__(APIServer)
    server.server = FastAPI()
    server.parameter = SimpleNamespace(
        CLEANER=Cleaner(), settings=SimpleNamespace(path=tmp_path / "settings.json", encode="utf-8"),
    )
    rows = [{"url": name.lower(), "mark": name} for name in ("Alpha", "Beta", "Empty")]
    server._active_account_rows = lambda platform: rows
    server._scope_root = lambda scope: tmp_path
    for name in ("Alpha", "Beta"):
        folder = tmp_path / f"UID1_{name}"
        folder.mkdir()
        for filename in ("a.jpg", "b.mp4"):
            (folder / filename).touch()
    server.setup_routes()
    client = TestClient(server.server, headers={"token": "board-test-token"})
    base = "/ui/api/accounts/board"
    def board():
        return {row["url"]: (row["media_path"], row["pinned"]) for row in client.get(base).json()["items"]}

    # The former release stored manual and automatic covers as plain paths.
    server._account_board_pin_file().write_text('{"pins":{"douyin::beta":"UID1_Beta/b.mp4"}}')
    initial = board()
    assert initial == {"alpha": ("UID1_Alpha/a.jpg", True), "beta": ("UID1_Beta/b.mp4", True), "empty": ("", False)}
    assert board() == initial
    def pick(url, mode):
        return client.post(base + "/random", json={
            "url": url, "current_path": board()[url][0], "face_cover": mode,
        }).json()

    from src.application import server_routes
    calls = []
    def match(*args):
        calls.append(args)
        return {"path": "UID1_Alpha/b.mp4", "second": 1}
    monkeypatch.setattr(server_routes, "choose_face_cover", match)
    assert pick("beta", "auto")["outcome"] == "superseded"
    change = pick("alpha", "auto")
    assert change["poster_second"] == 1
    assert pick("alpha", "auto")["outcome"] == "superseded"
    assert len(calls) == 1
    assert board() == {**initial, "alpha": (change["media_path"], True)}
    monkeypatch.setattr(server_routes, "choose_face_cover", lambda *args: None)
    assert pick("alpha", "replace")["outcome"] == "no_face"
    assert client.get(base).json()["items"][0]["poster_second"] == 1
    (tmp_path / change["media_path"]).unlink()
    assert board() == initial
    assert pick("alpha", "auto")["outcome"] == "no_face"
    assert not client.get(base).json()["items"][0]["cover_pending"]
