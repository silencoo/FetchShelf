from types import SimpleNamespace

import pytest

from src.collector import (
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


async def _async_none():
    return None
