import pytest

from src.collector.douyin_browser import (
    DouyinBrowserCollectionError,
    _douyin_login_prompt_visible,
    _open_context,
    _playwright_proxy,
    _should_update_collection_pagination,
    cookie_header_to_playwright,
)


class _FakeLocator:
    def __init__(self, visible: bool):
        self.visible = visible

    async def count(self):
        return 1

    def nth(self, index):
        return self

    async def is_visible(self):
        return self.visible


class _FakePage:
    def __init__(self, visible_labels=()):
        self.visible_labels = set(visible_labels)

    def get_by_text(self, label, exact=False):
        return _FakeLocator(label in self.visible_labels)


class _FakeBrowser:
    def __init__(self):
        self.options = None

    async def new_context(self, **options):
        self.options = options
        return object()


def test_cookie_header_to_playwright_accepts_exported_header():
    cookies = cookie_header_to_playwright(
        "Cookie: sessionid=abc%20123; empty=; malformed"
    )

    assert cookies == [
        {
            "name": "sessionid",
            "value": "abc%20123",
            "domain": ".douyin.com",
            "path": "/",
            "secure": True,
        },
        {
            "name": "empty",
            "value": "",
            "domain": ".douyin.com",
            "path": "/",
            "secure": True,
        },
    ]


def test_playwright_proxy_separates_credentials():
    assert _playwright_proxy("http://name:p%40ss@127.0.0.1:7890") == {
        "server": "http://127.0.0.1:7890",
        "username": "name",
        "password": "p@ss",
    }


def test_late_collection_preview_does_not_replace_full_page_pagination():
    assert _should_update_collection_pagination(0, 1) is True
    assert _should_update_collection_pagination(0, 20) is True
    assert _should_update_collection_pagination(19, 20) is True
    assert _should_update_collection_pagination(19, 1) is False


@pytest.mark.asyncio
async def test_douyin_login_prompt_detection_uses_visible_interactive_labels():
    assert await _douyin_login_prompt_visible(_FakePage({"验证码登录"})) is True
    assert await _douyin_login_prompt_visible(_FakePage({"扫码登录"})) is True
    assert await _douyin_login_prompt_visible(_FakePage()) is False


@pytest.mark.asyncio
async def test_open_context_preserves_identity_user_agent():
    browser = _FakeBrowser()

    await _open_context(browser, user_agent="identity-agent")

    assert browser.options["user_agent"] == "identity-agent"
    assert browser.options["locale"] == "zh-CN"


def test_browser_collection_error_exposes_stable_code():
    error = DouyinBrowserCollectionError(
        "login required",
        error_code="douyin_auth_required",
    )

    assert error.error_code == "douyin_auth_required"
    assert error.identity_id == ""
