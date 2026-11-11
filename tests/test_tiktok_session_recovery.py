from types import SimpleNamespace

import httpx
import pytest

from src.link.requester import Requester
from src.module.tiktok_api import TikTokAPIBridge
from src.tools.tiktok_session import TikTokVerificationRequired
from src.application.main_server import APIServer
from src.interface.template import API, APITikTok

CHALLENGE = '<html><p class="_wafchallengeid"></p></html>'


def parameter(client):
    return SimpleNamespace(
        client_tiktok=client, proxy_tiktok='http://proxy:7890',
        logger=SimpleNamespace(info=lambda *a: None, warning=lambda *a: None),
        headers_tiktok={'Cookie': 'old=1', 'User-Agent': 'old-agent'},
        headers_download_tiktok={}, headers_params_tiktok={},
        browser_info_tiktok={}, api_params_tiktok={}, max_retry=5,
        timeout=30, request_delay=0,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize('blocked_again', [False, True])
async def test_http_challenge_refreshes_once_then_retries_http(monkeypatch, blocked_again):
    requests = []
    refreshes = []

    def handler(request):
        requests.append(request)
        body = CHALLENGE if len(requests) == 1 or blocked_again else 'profile HTML'
        return httpx.Response(200, text=body)

    async def refresh(self, url):
        refreshes.append((url, self.proxy))
        return {'cookies': {'msToken': 'fresh'}, 'user_agent': 'browser-agent'}

    monkeypatch.setattr(TikTokAPIBridge, 'refresh_http_session', refresh)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        p = parameter(client)
        requester = Requester(p, client, p.headers_tiktok)
        if blocked_again:
            with pytest.raises(TikTokVerificationRequired):
                await requester.request_url('https://www.tiktok.com/@demo', content='text')
        else:
            assert await requester.request_url('https://www.tiktok.com/@demo', content='text') == 'profile HTML'
        assert len(requests) == 2  # max_retry=5 must not multiply challenge attempts
        assert refreshes == [('https://www.tiktok.com/@demo', 'http://proxy:7890')]
        assert requests[1].headers['Cookie'] == 'msToken=fresh'
        assert requests[1].headers['User-Agent'] == 'browser-agent'
        assert p.headers_download_tiktok['Cookie'] == 'msToken=fresh'
        assert p.api_params_tiktok['msToken'] == 'fresh'


@pytest.mark.asyncio
async def test_normal_response_does_not_open_browser(monkeypatch):
    async def unexpected(*args):
        pytest.fail('must not refresh a normal response')
    monkeypatch.setattr(TikTokAPIBridge, 'refresh_http_session', unexpected)
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, text='normal'))) as c:
        p = parameter(c)
        assert (await Requester(p, c, p.headers_tiktok).request_url_get('https://www.tiktok.com/@demo')).text == 'normal'


@pytest.mark.asyncio
async def test_api_retry_resigns_with_new_session(monkeypatch):
    from src.tools.tiktok_session import TikTokHTTPChallenge
    seen = []
    async def request(self, **kwargs):
        seen.append(kwargs)
        if len(seen) == 1:
            raise TikTokHTTPChallenge()
        assert kwargs['params']['msToken'] == 'fresh'
        assert kwargs['params']['cursor'] == 123
        assert self.headers['Cookie'] == 'msToken=fresh'
        return {'itemList': [{'id': '1'}]}
    async def refresh(self, url):
        assert url == 'https://www.tiktok.com/@demo'
        assert self.proxy == 'http://proxy:7890'
        return {'cookies': {'msToken': 'fresh'}, 'user_agent': 'browser-agent'}
    monkeypatch.setattr(API, 'request_data', request)
    monkeypatch.setattr(TikTokAPIBridge, 'refresh_http_session', refresh)
    api = object.__new__(APITikTok)
    p = parameter(None)
    api.runtime_parameter = p
    api.headers = dict(p.headers_tiktok, Referer='https://www.tiktok.com/@demo')
    api.params = {}
    api.proxy = p.proxy_tiktok
    api._client_proxy = p.proxy_tiktok
    result = await api.request_data('https://www.tiktok.com/api/post/item_list/', params={'cursor': 123})
    assert result['itemList']
    assert len(seen) == 2


def test_repeated_challenge_is_not_invalid_account_url():
    outcome = APIServer._account_exception_outcome(TikTokVerificationRequired('verification required'))
    assert outcome['outcome_code'] == 'verification_required'
    assert outcome['cross_identity'] is False
    assert outcome['retryable'] is False


@pytest.mark.asyncio
async def test_browser_refresh_exports_session_not_profile_data(monkeypatch):
    p = parameter(None)
    p.cookie_dict_tiktok = {}
    p.cookie_str_tiktok = ''
    p.tiktok_api_persistent_profile = False
    bridge = TikTokAPIBridge(p)
    visited = []
    class Page:
        async def goto(self, url, **kwargs):
            visited.append(url)
        async def content(self):
            return '<html>Profile</html>'
        async def evaluate(self, expression):
            return 'browser-agent'
    session = SimpleNamespace(page=Page(), params={'device_id': 'browser-device'})
    class BrowserAPI:
        sessions = [session]
        async def get_session_cookies(self, selected):
            assert selected is session
            return {'msToken': 'fresh'}
    async def run(url, callback):
        return await callback(BrowserAPI())
    monkeypatch.setattr(bridge, '_run_with_api', run)
    exported = await bridge.refresh_http_session('https://www.tiktok.com/@demo')
    assert visited == ['https://www.tiktok.com/@demo']
    assert exported == {'cookies': {'msToken': 'fresh'}, 'user_agent': 'browser-agent', 'params': {'device_id': 'browser-device'}}
    with pytest.raises(ValueError):
        await bridge.refresh_http_session('https://example.com/')


def test_json_content_is_not_misclassified_as_challenge():
    from src.tools.tiktok_session import is_tiktok_challenge
    assert not is_tiktok_challenge('{"description":"_wafchallengeid"}')
