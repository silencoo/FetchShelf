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


def test_schedule_identity_failure_policy_is_opt_in():
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
    assert defaults["notify_on_identity_failure"] is False
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
