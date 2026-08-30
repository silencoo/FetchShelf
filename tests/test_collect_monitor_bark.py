from types import SimpleNamespace

import pytest

from src.application.main_server import APIServer


@pytest.mark.asyncio
async def test_notify_collect_monitor_skips_on_success_without_new_accounts():
    server = APIServer.__new__(APIServer)
    server.logger = SimpleNamespace(warning=lambda *args, **kwargs: None)
    calls = []

    async def fake_send(*args, **kwargs):
        calls.append((args, kwargs))
        return True, ""

    server._send_bark_notification = fake_send
    schedule = {
        "bark_url": "https://bark.example/push",
        "collect_id": "123",
        "proxy": "",
        "name": "Test",
    }
    summary = {
        "added_accounts": 0,
        "duplicate_accounts": 2,
        "fetched_aweme": 5,
    }

    await APIServer._notify_collect_monitor(server, schedule, True, summary)

    assert calls == []


@pytest.mark.asyncio
async def test_notify_collect_monitor_sends_on_failure_even_without_new_accounts():
    server = APIServer.__new__(APIServer)
    server.logger = SimpleNamespace(warning=lambda *args, **kwargs: None)
    calls = []

    async def fake_send(*args, **kwargs):
        calls.append((args, kwargs))
        return True, ""

    server._send_bark_notification = fake_send
    schedule = {
        "bark_url": "https://bark.example/push",
        "collect_id": "123",
        "proxy": "",
        "name": "Test",
    }
    summary = {
        "added_accounts": 0,
        "duplicate_accounts": 2,
        "fetched_aweme": 5,
    }

    await APIServer._notify_collect_monitor(server, schedule, False, summary, "boom")

    assert len(calls) == 1
    assert "错误=boom" in calls[0][1]["body"]
