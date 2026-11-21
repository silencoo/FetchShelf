from __future__ import annotations

from datetime import datetime, timedelta, timezone
from time import monotonic
import pytest

from src.collector import (
    CollectorCredentials,
    CollectorIdentity,
    CollectorLoginBrowserManager,
    LoginBrowserDependencyError,
    LoginBrowserNotAuthenticatedError,
    LoginBrowserNotFoundError,
)
from src.collector.login_browser import LoginBrowserSession


class _Page:
    async def evaluate(self, expression):
        assert expression == "navigator.userAgent"
        return "FetchShelf Login Browser"


class _Context:
    def __init__(self, cookies):
        self._cookies = cookies
        self.pages = [_Page()]
        self.closed = False

    async def cookies(self, urls):
        assert urls
        return self._cookies

    async def close(self):
        self.closed = True


class _Playwright:
    def __init__(self):
        self.stopped = False

    async def stop(self):
        self.stopped = True


def _session(tmp_path, cookies):
    manager = CollectorLoginBrowserManager(tmp_path)
    now = datetime.now(timezone.utc)
    context = _Context(cookies)
    playwright = _Playwright()
    manager._session = LoginBrowserSession(
        session_id="lb_test",
        identity_id="tik-login",
        platform="tiktok",
        started_at=now,
        expires_at=now + timedelta(minutes=20),
        expires_monotonic=monotonic() + 1200,
        display=98,
        vnc_port=5901,
        width=1440,
        height=900,
        playwright=playwright,
        context=context,
        xvfb_process=None,
        vnc_process=None,
    )
    return manager, context, playwright


@pytest.mark.asyncio
async def test_login_browser_capture_filters_domains_and_requires_login_cookie(tmp_path):
    manager, _, _ = _session(
        tmp_path,
        [
            {"name": "msToken", "value": "anonymous", "domain": ".tiktok.com"},
            {"name": "sessionid", "value": "secret", "domain": ".tiktok.com"},
            {"name": "foreign", "value": "ignored", "domain": ".example.com"},
        ],
    )

    captured = await manager.capture("tik-login", "lb_test")

    assert captured.cookie_count == 2
    assert captured.login_cookie_count == 1
    assert captured.cookie == "msToken=anonymous; sessionid=secret"
    assert captured.user_agent == "FetchShelf Login Browser"


@pytest.mark.asyncio
async def test_login_browser_capture_rejects_anonymous_cookie_jar(tmp_path):
    manager, _, _ = _session(
        tmp_path,
        [{"name": "msToken", "value": "anonymous", "domain": ".tiktok.com"}],
    )

    with pytest.raises(LoginBrowserNotAuthenticatedError):
        await manager.capture("tik-login", "lb_test")


@pytest.mark.asyncio
async def test_viewer_ticket_is_short_lived_single_use_and_exclusive(tmp_path):
    manager, _, _ = _session(tmp_path, [])
    ticket = await manager.issue_viewer_ticket("tik-login", "lb_test")

    assert await manager.begin_viewer("tik-login", "lb_test", ticket) == 5901
    await manager.end_viewer("tik-login", "lb_test")
    with pytest.raises(LoginBrowserNotFoundError):
        await manager.begin_viewer("tik-login", "lb_test", ticket)


@pytest.mark.asyncio
async def test_login_browser_stop_releases_profile_resources(tmp_path):
    manager, context, playwright = _session(tmp_path, [])

    assert manager.is_identity_locked("tik-login") is True
    assert await manager.stop("tik-login", "lb_test") is True
    assert manager.is_identity_locked("tik-login") is False
    assert context.closed is True
    assert playwright.stopped is True


@pytest.mark.asyncio
async def test_login_browser_reports_missing_display_dependencies(tmp_path, monkeypatch):
    monkeypatch.setattr("src.collector.login_browser.which", lambda name: None)
    manager = CollectorLoginBrowserManager(tmp_path)
    identity = CollectorIdentity(
        identity_id="tik-login",
        name="TikTok Login",
        platform="tiktok",
    )

    with pytest.raises(LoginBrowserDependencyError):
        await manager.start(identity, CollectorCredentials())


def test_login_browser_parses_authenticated_proxy_without_leaking_credentials(tmp_path):
    proxy = CollectorLoginBrowserManager._playwright_proxy(
        "socks5://name:password@proxy.example:1080"
    )

    assert proxy == {
        "server": "socks5://proxy.example:1080",
        "username": "name",
        "password": "password",
    }


@pytest.mark.asyncio
async def test_paste_text_uses_focused_page_and_preserves_unicode(tmp_path):
    from types import SimpleNamespace
    manager, context, _ = _session(tmp_path, [])
    inserted = []
    class Page:
        def __init__(self, focused):
            self.focused = focused
            self.keyboard = SimpleNamespace(insert_text=self.insert)
        def is_closed(self):
            return False
        async def evaluate(self, expression):
            assert expression == 'document.hasFocus()'
            return self.focused
        async def insert(self, text):
            assert self.focused
            inserted.append(text)
    context.pages = [Page(True), Page(False)]
    await manager.paste_text('tik-login', 'lb_test', '中文 👋\npass & <text>')
    assert inserted == ['中文 👋\npass & <text>']
    with pytest.raises(LoginBrowserNotFoundError):
        await manager.paste_text('other-identity', 'lb_test', 'secret')
    with pytest.raises(LoginBrowserNotFoundError):
        await manager.paste_text('tik-login', 'expired-session', 'secret')
    assert len(inserted) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('text', ['', None, 'x' * 65537])
async def test_paste_text_rejects_invalid_payload(tmp_path, text):
    from src.collector.login_browser import LoginBrowserError
    manager, _, _ = _session(tmp_path, [])
    with pytest.raises(LoginBrowserError):
        await manager.paste_text('tik-login', 'lb_test', text)


@pytest.mark.asyncio
@pytest.mark.parametrize("fail", [False, True])
async def test_start_uses_only_cloak_and_preserves_profile_proxy(tmp_path, monkeypatch, fail):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    import src.collector.login_browser as module

    monkeypatch.setattr(module, "which", lambda name: "/bin/" + name)
    monkeypatch.setattr(module.asyncio, "create_subprocess_exec", AsyncMock(return_value=None))
    manager = CollectorLoginBrowserManager(tmp_path)
    monkeypatch.setattr(manager, "_ensure_process_started", AsyncMock())
    monkeypatch.setattr(manager, "_wait_for_vnc", AsyncMock())
    page = SimpleNamespace(goto=AsyncMock())
    context = SimpleNamespace(pages=[page], on=lambda *a: None, close=AsyncMock())
    launch = AsyncMock(return_value=context, side_effect=RuntimeError("cloak failed") if fail else None)
    monkeypatch.setattr(module, "launch_persistent_context_async", launch)
    identity = CollectorIdentity(identity_id="tik-login", name="TikTok", platform="tiktok")
    credentials = CollectorCredentials(proxy="http://proxy:7890")
    if fail:
        with pytest.raises(RuntimeError, match="cloak failed"):
            await manager.start(identity, credentials)
        assert manager._session is None
    else:
        session = await manager.start(identity, credentials)
        await manager.stop(identity.identity_id, session.session_id)
        context.close.assert_awaited_once()
    launch.assert_awaited_once()
    args, kwargs = launch.call_args
    assert args == (str(tmp_path / "browser_profiles" / "tik-login"),)
    assert kwargs["proxy"] == {"server": "http://proxy:7890"}
    assert kwargs["headless"] is False
    assert kwargs["no_viewport"] is True
    assert f"--window-size={manager.width},{manager.height}" in kwargs["args"]
    assert "--window-position=0,0" in kwargs["args"]
    assert "channel" not in kwargs
