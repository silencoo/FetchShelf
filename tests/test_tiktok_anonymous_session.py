from types import SimpleNamespace

import pytest

from src.module import TikTokAPIBridge


@pytest.mark.asyncio
async def test_bridge_exports_anonymous_session_state_without_persisting_it(
    monkeypatch,
):
    params = SimpleNamespace(
        logger=SimpleNamespace(warning=lambda *args, **kwargs: None),
        cookie_dict_tiktok={},
        cookie_str_tiktok="",
        proxy_tiktok=None,
        browser_info_tiktok={},
        tiktok_api_persistent_profile=False,
        tiktok_api_reuse_session=True,
    )
    bridge = TikTokAPIBridge(params)

    class Page:
        async def evaluate(self, expression):
            assert expression == "() => navigator.userAgent"
            return "anonymous-agent"

    session = SimpleNamespace(
        page=Page(),
        params={"device_id": "anonymous-device"},
    )

    class API:
        sessions = [session]

        async def get_session_cookies(self, selected):
            assert selected is session
            return {"msToken": "ephemeral", "ttwid": "visitor"}

    async def run_with_api(starting_url, callback):
        assert starting_url == "https://www.tiktok.com/@demo"
        return await callback(API())

    monkeypatch.setattr(bridge, "_run_with_api", run_with_api)
    result = await bridge.bootstrap_anonymous_session(
        "https://www.tiktok.com/@demo"
    )

    assert result == {
        "cookies": {"msToken": "ephemeral", "ttwid": "visitor"},
        "user_agent": "anonymous-agent",
        "params": {"device_id": "anonymous-device"},
    }
    assert params.cookie_dict_tiktok == {}
    assert params.cookie_str_tiktok == ""


@pytest.mark.asyncio
async def test_bridge_rejects_anonymous_session_without_ms_token(monkeypatch):
    params = SimpleNamespace(
        logger=SimpleNamespace(warning=lambda *args, **kwargs: None),
        cookie_dict_tiktok={},
        cookie_str_tiktok="",
        proxy_tiktok=None,
        browser_info_tiktok={},
        tiktok_api_persistent_profile=False,
        tiktok_api_reuse_session=True,
    )
    bridge = TikTokAPIBridge(params)
    session = SimpleNamespace(page=None, params={})

    class API:
        sessions = [session]

        async def get_session_cookies(self, selected):
            return {"ttwid": "visitor"}

    async def run_with_api(starting_url, callback):
        return await callback(API())

    monkeypatch.setattr(bridge, "_run_with_api", run_with_api)
    with pytest.raises(RuntimeError, match="msToken"):
        await bridge.bootstrap_anonymous_session()
