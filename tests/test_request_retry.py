"""HTTP failures pass through request capture before the retry policy sees them."""
import importlib
from types import SimpleNamespace

import httpx
import pytest
from curl_cffi.requests.exceptions import HTTPError as CurlHTTPError

from src.tools.capture import capture_error_request
from src.tools.retry import Retry


@pytest.mark.asyncio
@pytest.mark.parametrize("transport", ["httpx", "curl"])
@pytest.mark.parametrize("status, attempts", [(404, 1), (500, 6)])
@pytest.mark.parametrize("finished", [False, True])
async def test_http_retry_policy(monkeypatch, transport, status, attempts, finished):
    waits = []

    async def wait():
        waits.append(True)

    monkeypatch.setattr(importlib.import_module("src.tools.retry"), "wait", wait)
    response = httpx.Response(status, request=httpx.Request("GET", "https://example.test/comments"))
    error = (httpx.HTTPStatusError("failed", request=response.request, response=response)
             if transport == "httpx" else CurlHTTPError("failed", response=response))

    class Fetcher:
        max_retry = 5
        finished = False
        calls = 0
        log = SimpleNamespace(error=lambda *a: None, warning=lambda *a: None)

        @Retry.retry
        @capture_error_request
        async def request(self):
            self.calls += 1
            raise error

    fetcher = Fetcher()
    assert await fetcher.request(finished=finished) is None
    assert fetcher.calls == attempts
    assert len(waits) == attempts - 1
    assert fetcher.last_request_error is error
    assert fetcher.finished is finished


@pytest.mark.asyncio
async def test_successful_empty_comment_page_does_not_retry():
    class Fetcher:
        max_retry = 5
        calls = 0

        @Retry.retry
        @capture_error_request
        async def request(self):
            self.calls += 1
            return {"comments": [], "has_more": 0}

    fetcher = Fetcher()
    assert await fetcher.request() == {"comments": [], "has_more": 0}
    assert fetcher.calls == 1
