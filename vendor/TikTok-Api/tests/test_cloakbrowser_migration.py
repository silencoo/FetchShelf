import sys
import types

import pytest

import TikTokApi.tiktok as tiktok_module
from TikTokApi import TikTokApi


class DummyMouse:
    async def move(self, *args, **kwargs):
        return None


class DummyPage:
    def __init__(self):
        self.url = "about:blank"
        self.mouse = DummyMouse()
        self._request_handler = None

    async def evaluate(self, script):
        values = {
            "navigator.userAgent": "DummyAgent/1.0",
            "navigator.language": "en-US",
            "navigator.platform": "MacIntel",
            "Intl.DateTimeFormat().resolvedOptions().timeZone": "Asia/Shanghai",
        }
        for marker, value in values.items():
            if marker in script:
                return value
        return None

    async def route(self, pattern, handler):
        self._route = (pattern, handler)

    async def goto(self, url):
        self.url = url
        if self._request_handler is not None:
            request = types.SimpleNamespace(headers={"user-agent": "DummyAgent/1.0"})
            self._request_handler(request)
        return None

    def once(self, event, handler):
        if event == "request":
            self._request_handler = handler

    def set_default_navigation_timeout(self, timeout):
        self._timeout = timeout

    async def wait_for_load_state(self, state):
        return None

    async def close(self):
        self.closed = True

    async def content(self):
        return "<html></html>"


class DummyContext:
    def __init__(self):
        self.cookies_store = [{"name": "msToken", "value": "cookie-ms-token"}]

    async def add_cookies(self, cookies):
        self.cookies_store = cookies

    async def new_page(self):
        self.page = DummyPage()
        return self.page

    async def cookies(self):
        return self.cookies_store

    async def close(self):
        self.closed = True


class DummyBrowser:
    def __init__(self):
        self.contexts = []
        self.close_called = False

    async def new_context(self, **kwargs):
        self.new_context_kwargs = kwargs
        context = DummyContext()
        self.contexts.append(context)
        return context

    async def close(self):
        self.close_called = True


class DummyPlaywright:
    def __init__(self):
        self.chromium = types.SimpleNamespace(launch=self._launch)
        self.firefox = types.SimpleNamespace(launch=self._launch)
        self.webkit = types.SimpleNamespace(launch=self._launch)
        self.launch_kwargs = None
        self.stop_called = False

    async def _launch(self, **kwargs):
        self.launch_kwargs = kwargs
        return DummyBrowser()

    async def stop(self):
        self.stop_called = True


class DummyPlaywrightManager:
    def __init__(self, playwright):
        self.playwright = playwright

    async def start(self):
        return self.playwright


@pytest.mark.asyncio
async def test_create_sessions_uses_cloakbrowser_for_default_chromium(monkeypatch):
    calls = {}

    async def fake_cloak_launch_async(**kwargs):
        calls["kwargs"] = kwargs
        return DummyBrowser()

    monkeypatch.setitem(
        sys.modules,
        "cloakbrowser",
        types.SimpleNamespace(launch_async=fake_cloak_launch_async),
    )

    api = TikTokApi()
    try:
        await api.create_sessions(
            num_sessions=1,
            sleep_after=0,
            ms_tokens=["provided-ms-token"],
        )

        assert api.browser_engine == "cloakbrowser"
        assert calls["kwargs"]["headless"] is False
        assert calls["kwargs"]["args"] == ["--headless=new"]
        assert len(api.sessions) == 1
    finally:
        await api.close_sessions()


@pytest.mark.asyncio
async def test_create_sessions_falls_back_to_playwright_when_executable_path_used(
    monkeypatch,
):
    dummy_playwright = DummyPlaywright()

    async def noop_stealth(page):
        return None

    monkeypatch.setattr(
        tiktok_module,
        "async_playwright",
        lambda: DummyPlaywrightManager(dummy_playwright),
    )
    monkeypatch.setattr(tiktok_module, "stealth_async", noop_stealth)

    api = TikTokApi()
    try:
        await api.create_sessions(
            num_sessions=1,
            sleep_after=0,
            ms_tokens=["provided-ms-token"],
            executable_path="/tmp/custom-browser",
        )

        assert api.browser_engine == "playwright"
        assert dummy_playwright.launch_kwargs["executable_path"] == "/tmp/custom-browser"
        assert len(api.sessions) == 1
    finally:
        await api.close_sessions()
