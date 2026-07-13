from types import SimpleNamespace

import pytest

from src.application import main_terminal
from src.application.main_server import APIServer
from src.application.main_terminal import TikTok
from src.downloader.download import Downloader
from src.storage.xlsx import XLSXLogger


def test_public_ui_tasks_recursively_redact_credentials():
    task = {
        "task_id": "T000001",
        "endpoint": "/workflow/tiktok/detail_links",
        "payload": {
            "cookie": "sessionid=secret",
            "proxy": "http://user:password@example.test:8080",
            "links": ["https://www.tiktok.com/@demo/video/1"],
        },
        "result": {
            "params": {
                "cookie_tiktok": "tt-session=secret",
                "headers": {
                    "Authorization": "Bearer secret",
                    "User-Agent": "safe-agent",
                },
                "uptime_kuma_url": "https://kuma.test/api/push/secret",
            },
            "data": {"downloaded": 1},
        },
        "_runner": object(),
    }

    public_task = APIServer._public_ui_task(task)

    assert public_task["payload"]["cookie"] == "[REDACTED]"
    assert public_task["payload"]["proxy"] == "[REDACTED]"
    assert public_task["result"]["params"]["cookie_tiktok"] == "[REDACTED]"
    assert public_task["result"]["params"]["headers"]["Authorization"] == "[REDACTED]"
    assert public_task["result"]["params"]["uptime_kuma_url"] == "[REDACTED]"
    assert public_task["payload"]["links"] == task["payload"]["links"]
    assert public_task["result"]["params"]["headers"]["User-Agent"] == "safe-agent"
    assert public_task["result"]["data"] == {"downloaded": 1}
    assert "_runner" not in public_task
    assert task["payload"]["cookie"] == "sessionid=secret"


class _FakeWorkbook:
    def __init__(self):
        self.saved_paths = []
        self.closed = False

    def save(self, path):
        self.saved_paths.append(path)

    def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_xlsx_context_saves_only_after_success():
    logger = XLSXLogger.__new__(XLSXLogger)
    logger.path = "records.xlsx"
    logger.book = _FakeWorkbook()

    await logger.__aexit__(None, None, None)

    assert logger.book.saved_paths == ["records.xlsx"]
    assert logger.book.closed is True


@pytest.mark.asyncio
async def test_xlsx_context_does_not_overwrite_after_failure():
    logger = XLSXLogger.__new__(XLSXLogger)
    logger.path = "records.xlsx"
    logger.book = _FakeWorkbook()

    await logger.__aexit__(RuntimeError, RuntimeError("boom"), None)

    assert logger.book.saved_paths == []
    assert logger.book.closed is True


@pytest.mark.asyncio
async def test_account_api_forwards_cursor_and_count(monkeypatch):
    captured = {}

    class FakeAccount:
        def __init__(self, *args, **kwargs):
            captured.update(kwargs)

        async def run(self):
            return [], "", ""

    monkeypatch.setattr(main_terminal, "Account", FakeAccount)
    runner = SimpleNamespace(parameter=object())

    await TikTok._get_account_data(
        runner,
        sec_user_id="sec-user",
        cursor=42,
        count=7,
    )

    assert captured["cursor"] == 42
    assert captured["count"] == 7


@pytest.mark.asyncio
async def test_tiktok_primary_account_api_forwards_cursor_and_count(monkeypatch):
    captured = {}

    class FakeAccountTikTok:
        def __init__(self, *args, **kwargs):
            captured.update(kwargs)

        async def run(self):
            return [], "", ""

    monkeypatch.setattr(main_terminal, "AccountTikTok", FakeAccountTikTok)
    runner = TikTok.__new__(TikTok)
    runner.parameter = SimpleNamespace(
        tiktok_api_enabled=True,
        tiktok_bridge_fallback_enabled=False,
    )
    runner.logger = SimpleNamespace(warning=lambda *args, **kwargs: None)

    await TikTok._get_account_data_tiktok(
        runner,
        sec_user_id="sec-user",
        cursor=24,
        count=9,
    )

    assert captured["cursor"] == 24
    assert captured["count"] == 9


@pytest.mark.asyncio
async def test_tiktok_bridge_is_not_probed_when_fallback_is_disabled(monkeypatch):
    class FakeAccountTikTok:
        def __init__(self, *args, **kwargs):
            pass

        async def run(self):
            return [], "", ""

    class BridgeMustNotRun:
        @staticmethod
        def available():
            raise AssertionError("disabled bridge should not be probed")

    monkeypatch.setattr(main_terminal, "AccountTikTok", FakeAccountTikTok)
    monkeypatch.setattr(main_terminal, "TikTokAPIBridge", BridgeMustNotRun)
    runner = TikTok.__new__(TikTok)
    runner.parameter = SimpleNamespace(
        tiktok_api_enabled=True,
        tiktok_bridge_fallback_enabled=False,
    )
    runner.logger = SimpleNamespace(info=lambda *args, **kwargs: None)

    result = await TikTok._get_account_data_tiktok(runner, sec_user_id="sec-user")

    assert result == ([], "", "")


@pytest.mark.asyncio
async def test_tiktok_bridge_runs_only_after_primary_failure_when_enabled(monkeypatch):
    calls = []

    class FakeAccountTikTok:
        def __init__(self, *args, **kwargs):
            calls.append("primary")

        async def run(self):
            return [], "", ""

    class FakeBridge:
        @staticmethod
        def available():
            return True

        def __init__(self, *args, **kwargs):
            calls.append("bridge")

        async def get_account_items(self, **kwargs):
            return [{"id": "1"}], "", ""

        def should_skip_legacy_fallback(self):
            return False

    monkeypatch.setattr(main_terminal, "AccountTikTok", FakeAccountTikTok)
    monkeypatch.setattr(main_terminal, "TikTokAPIBridge", FakeBridge)
    runner = TikTok.__new__(TikTok)
    runner.parameter = SimpleNamespace(
        tiktok_api_enabled=True,
        tiktok_bridge_fallback_enabled=True,
    )
    runner.logger = SimpleNamespace(
        info=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
    )

    result = await TikTok._get_account_data_tiktok(runner, sec_user_id="sec-user")

    assert result[0] == [{"id": "1"}]
    assert calls == ["primary", "bridge"]


def test_tiktok_media_bridge_fallback_requires_both_flags():
    downloader = Downloader.__new__(Downloader)
    downloader.params = SimpleNamespace(
        tiktok_api_enabled=True,
        tiktok_bridge_fallback_enabled=False,
    )
    assert downloader._tiktok_bridge_fallback_enabled() is False

    downloader.params.tiktok_bridge_fallback_enabled = True
    assert downloader._tiktok_bridge_fallback_enabled() is True

    downloader.params.tiktok_api_enabled = False
    assert downloader._tiktok_bridge_fallback_enabled() is False
