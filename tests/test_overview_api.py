from threading import Lock
from time import monotonic
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.application.main_server import APIServer
from src.collector import (
    AESGCMSecretCodec,
    CollectorCredentials,
    CollectorIdentity,
    CollectorPlatform,
    CollectorRuntimeState,
    CollectorStore,
    IdentityStatus,
)


def _overview_test_client(tmp_path, monkeypatch):
    monkeypatch.setenv("FETCHSHELF_API_TOKEN", "overview-test-token")
    download_root = tmp_path / "downloads"
    download_root.mkdir()
    settings_path = tmp_path / "settings.json"
    settings_path.write_text("{}", encoding="utf-8")

    store = CollectorStore(
        tmp_path / "collector.sqlite3",
        codec=AESGCMSecretCodec(b"k" * 32),
    )
    identity = CollectorIdentity(
        identity_id="douyin-main",
        name="Douyin main",
        platform=CollectorPlatform.DOUYIN,
    )
    store.upsert_identity(identity)
    store.write_credentials(
        identity.identity_id,
        CollectorCredentials(
            cookie="sessionid=overview-secret",
            proxy="socks5://user:pass@proxy.test:1080",
        ),
    )
    store.save_runtime(
        CollectorRuntimeState(
            identity_id=identity.identity_id,
            status=IdentityStatus.HEALTHY,
            active_leases=1,
        ),
    )

    server = APIServer.__new__(APIServer)
    server.server = FastAPI()
    server.parameter = SimpleNamespace(
        root=download_root,
        settings=SimpleNamespace(path=settings_path, encode="utf-8"),
    )
    server.collector_store = store
    server.collector_vault_error = ""
    server.ui_schedules = {}
    server.ui_tasks = {
        "T000012": {
            "task_id": "T000012",
            "endpoint": "/workflow/douyin/account_batch",
            "payload": {"cookie": "sessionid=task-secret"},
            "status": "running",
            "created_at": "2026-08-28 12:24:31",
            "started_at": "2026-08-28 15:28:51",
            "finished_at": None,
            "updated_at": "2026-08-28 15:56:42",
            "message": "正在执行账号批次",
            "progress": {
                "current": 266,
                "total": 2291,
                "success": 265,
                "failed": 1,
                "percent": 12,
            },
            "account_summary": {"total": 2291, "success": 265, "failed": 1},
        },
        "T000011": {
            "task_id": "T000011",
            "endpoint": "/workflow/douyin/account_batch",
            "payload": {},
            "status": "success",
            "created_at": "2026-08-27 00:53:00",
            "started_at": "2026-08-27 00:53:00",
            "finished_at": "2026-08-27 10:51:07",
            "updated_at": "2026-08-27 10:51:07",
            "progress": {"current": 1839, "total": 1839, "percent": 100},
        },
    }
    server._overview_media_lock = Lock()
    server._overview_media_cache = {
        "folders": 2296,
        "files": 472818,
        "images": 237292,
        "videos": 234484,
        "other_files": 1042,
        "size": 879397093597,
        "size_human": "819.00 GB",
        "latest_updated_at": "2026-08-28T15:54:55+08:00",
        "refreshed_at": "2026-08-28T15:55:30+08:00",
    }
    server._overview_media_cache_updated_monotonic = monotonic()
    server._overview_media_scan_started_at = ""
    server._overview_media_scan_error = ""
    server._overview_media_scan_thread = None
    server.setup_routes()
    return server, TestClient(server.server)


def test_overview_api_aggregates_safe_runtime_state(tmp_path, monkeypatch):
    server, client = _overview_test_client(tmp_path, monkeypatch)
    headers = {"token": "overview-test-token"}

    response = client.get("/ui/api/overview", headers=headers)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["media"]["status"] == "ready"
    assert payload["media"]["videos"] == 234484
    assert payload["crawl"]["current"]["task_id"] == "T000012"
    assert payload["crawl"]["latest_success"]["finished_at"] == "2026-08-27 10:51:07"
    expected_collectors = {
        "total": 1,
        "enabled": 1,
        "routable": 1,
        "attention": 0,
        "cookie_configured": 1,
        "proxy_configured": 1,
        "cookie_and_proxy": 1,
        "active_leases": 1,
        "platforms": {"douyin": 1, "tiktok": 0},
    }
    assert {
        key: payload["collectors"][key]
        for key in expected_collectors
    } == expected_collectors
    assert payload["collectors"]["risk_failures"] == 0
    assert payload["collectors"]["cooldown"] == 0
    assert payload["collectors"]["identities"][0]["success_rate"] is None
    assert "payload" not in payload["crawl"]["current"]
    assert "overview-secret" not in response.text
    assert "task-secret" not in response.text
    assert "user:pass" not in response.text
    assert client.get("/ui/api/overview").status_code == 403
    server.collector_store.close()


def test_scope_stats_include_other_files_and_latest_update(tmp_path):
    root = tmp_path / "downloads"
    root.mkdir()
    (root / "poster.jpg").write_bytes(b"image")
    (root / "clip.mp4").write_bytes(b"video")
    (root / "notes.txt").write_bytes(b"notes")

    server = APIServer.__new__(APIServer)
    stats = server._collect_scope_stats(root, scope="download", scope_root=root)

    assert stats["files"] == 3
    assert stats["images"] == 1
    assert stats["videos"] == 1
    assert stats["other_files"] == 1
    assert stats["size"] == 15
    assert stats["latest_updated_at"]


def test_overview_eta_uses_only_progress_after_restart():
    snapshot = APIServer._overview_task_snapshot(
        {
            "task_id": "T000020",
            "status": "running",
            "created_at": "2026-08-28 12:24:31",
            "started_at": "2026-08-28 19:52:28",
            "finished_at": "2026-08-28 20:52:28",
            "progress": {"current": 864, "total": 2291},
            "recovered_after_restart": True,
            "eta_baseline_current": 744,
            "eta_baseline_at": "2026-08-28 19:52:28",
        }
    )

    assert snapshot["throughput_per_minute"] == 2
    assert snapshot["eta_seconds"] == 42810
    assert snapshot["eta_at"] == ""


def test_overview_eta_waits_for_recovered_task_baseline():
    snapshot = APIServer._overview_task_snapshot(
        {
            "task_id": "T000020",
            "status": "running",
            "created_at": "2026-08-28 12:24:31",
            "started_at": "2026-08-28 19:52:28",
            "finished_at": None,
            "progress": {"current": 744, "total": 2291},
            "recovered_after_restart": True,
        }
    )

    assert snapshot["throughput_per_minute"] == 0
    assert snapshot["eta_seconds"] is None
    assert snapshot["eta_at"] == ""
