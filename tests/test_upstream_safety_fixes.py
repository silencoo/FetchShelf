from types import SimpleNamespace

import pytest

from src.application import main_terminal
from src.application.main_terminal import TikTok
from src.storage.xlsx import XLSXLogger


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
async def test_tiktok_bridge_account_api_forwards_cursor_and_count(monkeypatch):
    captured = {}

    class FakeBridge:
        @staticmethod
        def available():
            return True

        def __init__(self, *args, **kwargs):
            pass

        async def get_account_items(self, **kwargs):
            captured.update(kwargs)
            return [], "", ""

        def should_skip_legacy_fallback(self):
            return True

    monkeypatch.setattr(main_terminal, "TikTokAPIBridge", FakeBridge)
    runner = SimpleNamespace(
        parameter=SimpleNamespace(tiktok_api_enabled=True),
        logger=SimpleNamespace(warning=lambda *args, **kwargs: None),
    )

    await TikTok._get_account_data_tiktok(
        runner,
        sec_user_id="sec-user",
        cursor=24,
        count=9,
    )

    assert captured["cursor"] == 24
    assert captured["count"] == 9
