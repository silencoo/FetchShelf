from json import loads
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

from src.application.main_server import APIServer, token_dependency
from src.custom.function import is_valid_token
from src.record.base import BaseLogger
from src.webui.log_store import LogStore
from src.webui_security import (
    REDACTED_VALUE,
    is_protected_project_path,
    redact_webui_json_text,
    redact_webui_text,
    redact_webui_value,
    restore_redacted_values,
)


@pytest.fixture(autouse=True)
def clear_webui_tokens(monkeypatch):
    monkeypatch.delenv("DOUK_API_TOKEN", raising=False)
    monkeypatch.delenv("DOUK_WEBUI_TOKEN", raising=False)


def test_tokenless_access_is_loopback_only():
    assert is_valid_token(None, "127.0.0.1") is True
    assert is_valid_token("", "::1") is True
    assert is_valid_token(None, "192.168.1.20") is False
    assert is_valid_token(None, "172.18.0.1") is False
    assert is_valid_token(None, None) is False


def test_configured_token_is_required_for_every_client(monkeypatch):
    monkeypatch.setenv("DOUK_API_TOKEN", "correct-horse")

    assert is_valid_token("correct-horse", "203.0.113.10") is True
    assert is_valid_token("wrong", "127.0.0.1") is False
    assert is_valid_token(None, "127.0.0.1") is False


def test_fastapi_dependency_rejects_remote_default_and_accepts_env_token(monkeypatch):
    app = FastAPI()

    @app.get("/private")
    async def private_route(_: None = Depends(token_dependency)):
        return {"ok": True}

    client = TestClient(app)
    assert client.get("/private").status_code == 403

    monkeypatch.setenv("DOUK_API_TOKEN", "nas-secret")
    assert client.get("/private", headers={"token": "wrong"}).status_code == 403
    response = client.get("/private", headers={"token": "nas-secret"})
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_recursive_redaction_covers_settings_schedules_tasks_and_text():
    source = {
        "cookie": "sessionid=top-secret",
        "proxy_tiktok": "socks5://user:pass@proxy.test:1080",
        "ui_schedules": [
            {
                "cookie": "schedule-cookie",
                "bark_url": "https://api.day.app/private-key",
                "uptime_kuma_url": "https://kuma.test/api/push/private-key",
            }
        ],
        "error": "proxy failed: socks5://user:pass@proxy.test:1080; sessionid=abc",
        "header_error": "Authorization: Bearer top-secret",
        "safe": "kept",
    }

    public = redact_webui_value(source)

    assert public["cookie"] == REDACTED_VALUE
    assert public["proxy_tiktok"] == REDACTED_VALUE
    assert public["ui_schedules"][0]["cookie"] == REDACTED_VALUE
    assert public["ui_schedules"][0]["bark_url"] == REDACTED_VALUE
    assert public["ui_schedules"][0]["uptime_kuma_url"] == REDACTED_VALUE
    assert "user:pass" not in public["error"]
    assert "sessionid=abc" not in public["error"]
    assert "top-secret" not in public["header_error"]
    assert public["safe"] == "kept"
    assert source["cookie"] == "sessionid=top-secret"


def test_recursive_redaction_covers_identity_fingerprint_and_signatures():
    source = {
        "browser_info_tiktok": {
            "User-Agent": "identity-agent",
            "device_id": "device-secret",
            "webid": "web-secret",
            "uifid": "uifid-secret",
            "msToken": "ms-secret",
        },
        "signatures": {
            "a_bogus": "a-secret",
            "X-Bogus": "x-secret",
            "X-Gnarly": "g-secret",
        },
    }

    public = redact_webui_value(source)

    assert set(public["browser_info_tiktok"].values()) == {REDACTED_VALUE}
    assert set(public["signatures"].values()) == {REDACTED_VALUE}


def test_text_redaction_preserves_normal_query_fields_and_surrounding_log():
    text = (
        "HTTP 403 for https://www.tiktok.com/api/post/item_list/"
        "?count=20&device%5Fid=device-secret&msToken=ms-secret"
        "&X-Bogus=x-secret&X-Gnarly=g-secret&a_bogus=a-secret#response "
        "retry=2"
    )

    redacted = redact_webui_text(text)

    assert redacted.startswith("HTTP 403 for https://www.tiktok.com/")
    assert "count=20" in redacted
    assert "#response retry=2" in redacted
    assert redacted.count(REDACTED_VALUE) == 5
    for secret in (
        "device-secret",
        "ms-secret",
        "x-secret",
        "g-secret",
        "a-secret",
    ):
        assert secret not in redacted


def test_text_redaction_does_not_rewrite_ordinary_url_or_log_message():
    text = "GET https://example.test/path?q=hello%20world&count=20 -> 200 (43 ms)"
    assert redact_webui_text(text) == text


def test_text_redaction_preserves_semicolon_query_separators():
    text = "GET https://example.test/path?count=20;User-Agent=agent&cursor=2"
    assert redact_webui_text(text) == (
        f"GET https://example.test/path?count=20;User-Agent={REDACTED_VALUE}&cursor=2"
    )


def test_text_redaction_covers_header_labels_and_unschemed_proxy_credentials():
    header = "User-Agent: Mozilla/5.0 identity-agent\nnext-line=kept"
    structured = "{'User-Agent': 'identity-agent', 'status': 'failed'}"
    labeled = "device_id=device-secret webid=web-secret"
    proxy_error = "ProxyError(user:pass@proxy.example.test:1080), retrying"

    assert redact_webui_text(header) == (
        f"User-Agent: {REDACTED_VALUE}\nnext-line=kept"
    )
    assert redact_webui_text(structured) == (
        "{'User-Agent': '[REDACTED]', 'status': 'failed'}"
    )
    assert "device-secret" not in redact_webui_text(labeled)
    assert "web-secret" not in redact_webui_text(labeled)
    assert redact_webui_text(proxy_error) == (
        "ProxyError([REDACTED]@proxy.example.test:1080), retrying"
    )


def test_log_ingress_stores_only_sanitized_text():
    store = LogStore(maxlen=2)
    store.add(
        "ERROR",
        "request failed: https://example.test/api?device_id=device-secret&count=20",
    )

    record = store.latest(1)[0]
    assert record["message"].endswith(
        f"?device_id={REDACTED_VALUE}&count=20"
    )
    assert "device-secret" not in record["message"]


def test_base_logger_sanitizes_console_and_web_ingress():
    class FakeConsole:
        def __init__(self):
            self.messages = []

        def print(self, text, **kwargs):
            self.messages.append(text)

    logger = BaseLogger.__new__(BaseLogger)
    logger.console = FakeConsole()
    web_messages = []
    logger.push_web_log = lambda level, text: web_messages.append((level, text))

    logger.error("device_id=device-secret status=failed")

    assert "device-secret" not in logger.console.messages[0]
    assert "device-secret" not in web_messages[0][1]


def test_redacted_raw_settings_can_be_saved_without_overwriting_secrets():
    current = {
        "cookie": "sessionid=real",
        "proxy": "http://user:pass@proxy.test:8080",
        "ui_schedules": [{"schedule_id": "S1", "cookie": "scheduled-secret"}],
    }
    public_text = redact_webui_json_text(
        """{
            "cookie": "sessionid=real",
            "proxy": "http://user:pass@proxy.test:8080",
            "ui_schedules": [{"schedule_id": "S1", "cookie": "scheduled-secret"}]
        }"""
    )
    public = loads(public_text)

    assert public["cookie"] == REDACTED_VALUE
    restored = restore_redacted_values(public, current)
    assert restored == current

    public["cookie"] = "sessionid=replaced"
    public["proxy"] = ""
    restored = restore_redacted_values(public, current)
    assert restored["cookie"] == "sessionid=replaced"
    assert restored["proxy"] == ""
    assert restored["ui_schedules"][0]["cookie"] == "scheduled-secret"


@pytest.mark.parametrize(
    "relative",
    (
        "settings.json",
        "backups/settings_20260714.json",
        "browser_debug/20260714/session_1.html",
        "collector_pool.sqlite3",
        "collector_pool.sqlite3-wal",
        "cache/tiktok_api_profiles/identity-a/Default/Cookies",
        "secrets/identity-secrets.enc",
        "keys/master.key",
        "encipher.py",
        "custom_tiktok_debug_capture/session_1_metadata.json",
    ),
)
def test_project_file_scope_blocks_sensitive_state(tmp_path: Path, relative: str):
    root = tmp_path / "settings"
    root.mkdir()
    assert is_protected_project_path(root, root / relative) is True


def test_project_file_scope_keeps_public_avatar_media_available(tmp_path: Path):
    root = tmp_path / "settings"
    root.mkdir()
    assert is_protected_project_path(
        root,
        root / "profile_avatars" / "avatar.png",
    ) is False


def test_main_server_file_guard_hides_protected_paths(tmp_path: Path):
    root = tmp_path / "settings"
    root.mkdir()
    server = APIServer.__new__(APIServer)
    server.parameter = SimpleNamespace(
        settings=SimpleNamespace(path=root / "settings.json"),
        tiktok_api_debug_capture_dir="opaque_artifacts_42",
    )

    with pytest.raises(HTTPException) as captured:
        server._ensure_public_file_scope_path(
            "project",
            root,
            root / "collector_pool.sqlite3",
        )

    assert captured.value.status_code == 404
    server._ensure_public_file_scope_path(
        "project",
        root,
        root / "profile_avatars" / "avatar.png",
    )

    with pytest.raises(HTTPException) as dynamic_capture:
        server._ensure_public_file_scope_path(
            "project",
            root,
            root / "opaque_artifacts_42" / "session.html",
        )
    assert dynamic_capture.value.status_code == 404


def test_schedule_public_redacts_without_corrupting_persistence_payload():
    schedule = {
        "schedule_id": "S1",
        "cookie": "schedule-secret",
        "proxy": "http://user:pass@proxy.test:8080",
        "bark_url": "https://api.day.app/private-key",
        "_runner": object(),
    }

    stored = APIServer._schedule_serializable(schedule)
    public = APIServer._schedule_public(schedule)

    assert stored["cookie"] == "schedule-secret"
    assert stored["proxy"] == "http://user:pass@proxy.test:8080"
    assert "_runner" not in stored
    assert public["cookie"] == REDACTED_VALUE
    assert public["proxy"] == REDACTED_VALUE
    assert public["bark_url"] == REDACTED_VALUE
    assert schedule["cookie"] == "schedule-secret"


@pytest.mark.asyncio
async def test_ui_task_failure_keeps_internal_exception_out_of_public_state():
    server = APIServer.__new__(APIServer)
    server.ui_tasks = {
        "T000001": {
            "task_id": "T000001",
            "endpoint": "/workflow/douyin/account_batch",
            "payload": {},
            "status": "pending",
            "created_at": "",
            "started_at": None,
            "finished_at": None,
            "updated_at": "",
            "error": "",
            "message": "",
            "_runner": None,
        }
    }

    async def fail_endpoint(endpoint, payload):
        raise RuntimeError(
            "request failed with sessionid=task-secret "
            "via socks5://user:password@proxy.test:1080"
        )

    server._execute_ui_endpoint = fail_endpoint
    await server._execute_ui_task("T000001", worker_id=1)

    task = server.ui_tasks["T000001"]
    assert task["status"] == "failed"
    assert task["error"] == "task_execution_failed"
    assert "task-secret" not in str(task)
    assert "user:password" not in str(task)
