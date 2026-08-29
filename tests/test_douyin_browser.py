from src.collector.douyin_browser import (
    _playwright_proxy,
    _should_update_collection_pagination,
    cookie_header_to_playwright,
)


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
