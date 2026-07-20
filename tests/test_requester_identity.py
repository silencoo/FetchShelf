from types import SimpleNamespace

import pytest

from src.link import requester as requester_module
from src.link.requester import Requester


class _Response:
    url = "https://example.test/final"
    status_code = 200
    headers = {}

    def raise_for_status(self):
        return None


class _Client:
    def __init__(self):
        self.urls = []
        self.closed = False

    async def get(self, url, **kwargs):
        self.urls.append((url, kwargs))
        return _Response()

    async def head(self, url, **kwargs):
        self.urls.append((url, kwargs))
        return _Response()

    async def aclose(self):
        self.closed = True


@pytest.mark.asyncio
async def test_proxy_override_uses_async_identity_client(monkeypatch):
    base_client = _Client()
    proxy_client = _Client()
    params = SimpleNamespace(
        client=base_client,
        client_tiktok=object(),
        headers={},
        logger=SimpleNamespace(info=lambda *args, **kwargs: None),
        max_retry=1,
        timeout=10,
        request_delay=6,
        proxy="http://base-proxy:8080",
        proxy_tiktok=None,
    )
    monkeypatch.setattr(
        requester_module,
        "create_client",
        lambda **kwargs: proxy_client,
    )
    requester = Requester(params, base_client, {"User-Agent": "identity"})

    response = await requester.request_url_get_proxy(
        "https://example.test/start",
        "http://identity-proxy:8080",
    )

    assert response.status_code == 200
    assert base_client.urls == []
    assert proxy_client.urls[0][0] == "https://example.test/start"
    assert proxy_client.closed is True
