from types import SimpleNamespace

import pytest

from src.collector import (
    CollectorAuthMode,
    CollectorCredentials,
    CollectorIdentity,
    build_collector_runtime,
)


class _Client:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.closed = False

    async def aclose(self):
        self.closed = True


def _parameter():
    return SimpleNamespace(
        headers={"User-Agent": "global"},
        headers_tiktok={"User-Agent": "global-tiktok"},
        headers_download={"User-Agent": "global"},
        headers_download_tiktok={"User-Agent": "global-tiktok"},
        headers_params={"User-Agent": "global"},
        headers_params_tiktok={"User-Agent": "global-tiktok"},
        headers_qrcode={"User-Agent": "global"},
        browser_info={},
        browser_info_tiktok={},
        timeout=10,
        proxy=None,
        proxy_tiktok=None,
        client=object(),
        client_tiktok=object(),
        cookie_dict={},
        cookie_str="",
        cookie_state=False,
        cookie_dict_tiktok={},
        cookie_str_tiktok="",
        cookie_tiktok_state=False,
        ms_token_tiktok="",
        _external_signers=set(),
        ab=object(),
        xb=object(),
        xg=object(),
    )


@pytest.mark.asyncio
async def test_tiktok_runtime_isolates_proxy_headers_and_profile(tmp_path, monkeypatch):
    base = _parameter()
    identity = CollectorIdentity(
        identity_id="tt-main",
        name="TikTok main",
        platform="tiktok",
        request_delay=8,
    )
    credentials = CollectorCredentials(
        cookie="sessionid=secret; msToken=token",
        proxy="socks5://proxy.test:1080",
        user_agent="identity-agent",
        device_id="device-1",
    )
    monkeypatch.setattr(
        "src.collector.runtime.TikTokAPIBridge.close_for_params",
        lambda parameter: _async_none(),
    )

    runtime = build_collector_runtime(
        base,
        identity,
        credentials,
        settings_dir=tmp_path,
        client_factory=_Client,
    )

    assert runtime.parameter is not base
    assert runtime.parameter.client_tiktok is runtime.owned_client
    assert runtime.parameter.proxy_tiktok == "socks5://proxy.test:1080"
    assert runtime.parameter.headers_tiktok["Cookie"] == credentials.cookie
    assert runtime.parameter.headers_tiktok["User-Agent"] == "identity-agent"
    assert runtime.parameter.api_params_tiktok["device_id"] == "device-1"
    assert runtime.parameter.api_params_tiktok["msToken"] == "token"
    assert runtime.parameter.request_delay == 8
    assert "tt-main" in runtime.parameter.tiktok_api_profile_dir
    assert "Cookie" not in base.headers_tiktok
    assert base.proxy_tiktok is None

    await runtime.close()
    assert runtime.owned_client.closed is True


@pytest.mark.asyncio
async def test_anonymous_tiktok_runtime_bootstraps_ephemeral_cloak_session(
    tmp_path,
    monkeypatch,
):
    base = _parameter()
    identity = CollectorIdentity(
        identity_id="tt-anonymous",
        name="TikTok anonymous",
        platform="tiktok",
        auth_mode=CollectorAuthMode.ANONYMOUS,
    )
    credentials = CollectorCredentials(
        cookie="sessionid=must-be-ignored",
        proxy="socks5://proxy.test:1080",
    )

    class _Bridge:
        def __init__(self, parameter, proxy=None):
            assert proxy == credentials.proxy

        async def bootstrap_anonymous_session(self):
            return {
                "cookies": {"msToken": "anonymous-token", "ttwid": "visitor"},
                "user_agent": "anonymous-agent",
                "params": {"device_id": "anonymous-device"},
            }

        @classmethod
        async def close_for_params(cls, parameter):
            return None

    monkeypatch.setattr("src.collector.runtime.TikTokAPIBridge", _Bridge)
    runtime = build_collector_runtime(
        base,
        identity,
        credentials,
        settings_dir=tmp_path,
        client_factory=_Client,
    )

    assert runtime.credentials.cookie == ""
    await runtime.prepare()

    assert runtime.parameter.ms_token_tiktok == "anonymous-token"
    assert runtime.parameter.api_params_tiktok["device_id"] == "anonymous-device"
    assert runtime.parameter.headers_tiktok["Cookie"].startswith("msToken=")
    assert runtime.parameter.headers_tiktok["User-Agent"] == "anonymous-agent"
    assert runtime.parameter.proxy_tiktok == credentials.proxy
    await runtime.close()


@pytest.mark.asyncio
async def test_douyin_runtime_preserves_refreshed_token_when_identity_has_none(tmp_path):
    base = _parameter()
    identity = CollectorIdentity(
        identity_id="dy-main",
        name="Douyin main",
        platform="douyin",
    )
    credentials = CollectorCredentials(cookie="sessionid=secret")

    runtime = build_collector_runtime(
        base,
        identity,
        credentials,
        settings_dir=tmp_path,
        client_factory=_Client,
    )

    assert "msToken" not in runtime.parameter.api_params
    await runtime.close()


@pytest.mark.asyncio
async def test_douyin_runtime_accepts_query_token_from_browser_info(tmp_path):
    base = _parameter()
    identity = CollectorIdentity(
        identity_id="dy-main",
        name="Douyin main",
        platform="douyin",
    )
    credentials = CollectorCredentials(
        cookie="sessionid=secret",
        browser_info={"msToken": "query-token"},
    )

    runtime = build_collector_runtime(
        base,
        identity,
        credentials,
        settings_dir=tmp_path,
        client_factory=_Client,
    )

    assert runtime.parameter.api_params["msToken"] == "query-token"
    await runtime.close()


async def _async_none():
    return None
