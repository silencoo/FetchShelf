from TikTokApi import TikTokApi
from TikTokApi.api.video import Video
from TikTokApi.exceptions import InvalidResponseException
import base64
import os
import pytest
from types import SimpleNamespace

ms_token = os.environ.get("ms_token", None)
headless = os.environ.get("headless", "True").lower() == "true"


@pytest.mark.asyncio
async def test_video_id_from_url():
    api = TikTokApi()
    async with api:
        await api.create_sessions(
            ms_tokens=[ms_token],
            num_sessions=1,
            sleep_after=3,
            browser=os.getenv("TIKTOK_BROWSER", "chromium"),
            headless=headless,
        )

        expected_id = "7074717081563942186"
        video = api.video(
            url="https://www.tiktok.com/@davidteathercodes/video/7074717081563942186"
        )

        assert video.id == expected_id

        # mobile_url = "https://www.tiktok.com/t/ZT8LCfcUC/"
        # video = api.video(url=mobile_url)

        # assert video.id == expected_id


@pytest.mark.asyncio
async def test_video_info():
    api = TikTokApi()
    async with api:
        await api.create_sessions(
            ms_tokens=[ms_token],
            num_sessions=1,
            sleep_after=3,
            browser=os.getenv("TIKTOK_BROWSER", "chromium"),
            headless=headless,
        )
        video_id = "7074717081563942186"
        video = api.video(
            url="https://www.tiktok.com/@davidteathercodes/video/7074717081563942186"
        )

        data = await video.info()

        assert data["id"] == video_id
        video.author.username = "davidteathercodes"


@pytest.mark.asyncio
async def test_video_bytes():
    pytest.skip("Not implemented yet")
    api = TikTokApi()
    async with api:
        await api.create_sessions(
            ms_tokens=[ms_token],
            num_sessions=1,
            sleep_after=3,
            browser=os.getenv("TIKTOK_BROWSER", "chromium"),
            headless=headless,
        )
        video_id = "7107272719166901550"
        video = api.video(id=video_id)

        data = await video.bytes()
        assert len(data) > 10000


@pytest.mark.asyncio
async def test_related_videos():
    api = TikTokApi()
    async with api:
        await api.create_sessions(
            ms_tokens=[ms_token],
            num_sessions=1,
            sleep_after=3,
            browser=os.getenv("TIKTOK_BROWSER", "chromium"),
            headless=headless,
        )
        video_id = "7107272719166901550"
        video = api.video(id=video_id)
        count = 0
        async for related_video in video.related_videos(count=10):
            print(related_video)
            count += 1

        assert count >= 10


@pytest.mark.asyncio
async def test_video_bytes_prefers_download_addr_and_falls_back(monkeypatch):
    async def fake_get_session_cookies(session):
        return {"msToken": "cookie-ms-token"}

    session = SimpleNamespace(headers={"user-agent": "DummyAgent/1.0"})
    browser_calls = []

    async def fake_fetch_binary(url, headers=None, session_index=None):
        browser_calls.append(
            {
                "url": url,
                "headers": dict(headers or {}),
                "session_index": session_index,
            }
        )
        if url == "https://cdn.example/download.mp4":
            return {
                "ok": False,
                "status": 403,
                "url": url,
                "contentType": "text/html",
                "size": 32,
                "textPreview": "forbidden",
                "bodyBase64": base64.b64encode(b"<html>blocked</html>").decode(
                    "ascii"
                ),
            }
        if url == "https://cdn.example/play.mp4":
            return {
                "ok": True,
                "status": 200,
                "url": url,
                "contentType": "video/mp4",
                "size": 11,
                "textPreview": "",
                "bodyBase64": base64.b64encode(b"video-bytes").decode("ascii"),
            }
        return {
            "ok": False,
            "status": 404,
            "url": url,
            "contentType": "text/plain",
            "size": 0,
            "textPreview": "",
            "bodyBase64": "",
        }

    async def fail_capture_media_response(*args, **kwargs):
        raise AssertionError("capture_media_response should not be used here")

    fake_parent = SimpleNamespace(
        _get_session=lambda **kwargs: (0, session),
        get_session_cookies=fake_get_session_cookies,
        fetch_binary=fake_fetch_binary,
        capture_media_response=fail_capture_media_response,
        user=lambda **kwargs: kwargs,
        sound=lambda **kwargs: kwargs,
        hashtag=lambda **kwargs: kwargs,
    )
    monkeypatch.setattr(Video, "parent", fake_parent, raising=False)

    video = Video(
        data={
            "id": "video-1",
            "createTime": 0,
            "stats": {},
            "author": {"uniqueId": "author"},
            "challenges": [],
            "video": {
                "downloadAddr": "https://cdn.example/download.mp4",
                "playAddr": "https://cdn.example/play.mp4",
                "PlayAddrStruct": {
                    "UrlList": [
                        "https://cdn.example/struct-1.mp4",
                    ]
                },
                "bitrateInfo": [
                    {
                        "PlayAddr": {
                            "UrlList": [
                                "https://cdn.example/bitrate-1.mp4",
                            ]
                        }
                    }
                ],
            },
        }
    )

    data = await video.bytes()

    assert data == b"video-bytes"
    assert [request["url"] for request in browser_calls] == [
        "https://cdn.example/download.mp4",
        "https://cdn.example/play.mp4",
    ]
    assert all(
        request["headers"]["referer"] == "https://www.tiktok.com/"
        for request in browser_calls
    )
    assert session.headers == {"user-agent": "DummyAgent/1.0"}


@pytest.mark.asyncio
async def test_video_bytes_stream_stops_retrying_after_partial_chunk(monkeypatch):
    async def fake_get_session_cookies(session):
        return {}

    session = SimpleNamespace(headers={"user-agent": "DummyAgent/1.0"})
    stream_calls = []

    async def fake_fetch_binary(url, headers=None, session_index=None):
        stream_calls.append(
            {
                "url": url,
                "range": dict(headers or {}).get("range"),
                "session_index": session_index,
            }
        )
        if len(stream_calls) == 1:
            return {
                "ok": True,
                "status": 206,
                "url": url,
                "contentType": "video/mp4",
                "contentRange": "bytes 0-3/8",
                "size": 4,
                "textPreview": "",
                "bodyBase64": base64.b64encode(b"part").decode("ascii"),
            }
        raise RuntimeError("stream reset")

    async def fail_capture_media_response(*args, **kwargs):
        raise AssertionError("capture_media_response should not run after stream start")

    fake_parent = SimpleNamespace(
        _get_session=lambda **kwargs: (0, session),
        get_session_cookies=fake_get_session_cookies,
        fetch_binary=fake_fetch_binary,
        capture_media_response=fail_capture_media_response,
        user=lambda **kwargs: kwargs,
        sound=lambda **kwargs: kwargs,
        hashtag=lambda **kwargs: kwargs,
    )
    monkeypatch.setattr(Video, "parent", fake_parent, raising=False)

    video = Video(
        data={
            "id": "video-2",
            "createTime": 0,
            "stats": {},
            "author": {"uniqueId": "author"},
            "challenges": [],
            "video": {
                "downloadAddr": "https://cdn.example/download.mp4",
                "playAddr": "https://cdn.example/play.mp4",
            },
        }
    )

    stream = await video.bytes(stream=True, browser_chunk_size=4, stream_chunk_size=4)
    received = []

    with pytest.raises(InvalidResponseException):
        async for chunk in stream:
            received.append(chunk)

    assert received == [b"part"]
    assert stream_calls == [
        {
            "url": "https://cdn.example/download.mp4",
            "range": "bytes=0-3",
            "session_index": 0,
        },
        {
            "url": "https://cdn.example/download.mp4",
            "range": "bytes=4-7",
            "session_index": 0,
        },
    ]


@pytest.mark.asyncio
async def test_video_bytes_stream_falls_back_to_capture_response(monkeypatch):
    async def fake_get_session_cookies(session):
        return {}

    session = SimpleNamespace(headers={"user-agent": "DummyAgent/1.0"})
    fetch_calls = []
    capture_calls = []

    async def fake_fetch_binary(url, headers=None, session_index=None):
        fetch_calls.append(
            {
                "url": url,
                "range": dict(headers or {}).get("range"),
                "session_index": session_index,
            }
        )
        return {
            "ok": False,
            "status": 403,
            "url": url,
            "contentType": "text/html",
            "size": 18,
            "textPreview": "blocked",
            "bodyBase64": base64.b64encode(b"<html>blocked</html>").decode("ascii"),
        }

    async def fake_capture_media_response(url, headers=None, session_index=None):
        capture_calls.append(
            {
                "url": url,
                "headers": dict(headers or {}),
                "session_index": session_index,
            }
        )
        return {
            "ok": True,
            "status": 200,
            "url": url,
            "contentType": "video/mp4",
            "size": 10,
            "textPreview": "",
            "bodyBase64": base64.b64encode(b"abcdefghij").decode("ascii"),
        }

    fake_parent = SimpleNamespace(
        _get_session=lambda **kwargs: (0, session),
        get_session_cookies=fake_get_session_cookies,
        fetch_binary=fake_fetch_binary,
        capture_media_response=fake_capture_media_response,
        user=lambda **kwargs: kwargs,
        sound=lambda **kwargs: kwargs,
        hashtag=lambda **kwargs: kwargs,
    )
    monkeypatch.setattr(Video, "parent", fake_parent, raising=False)

    video = Video(
        data={
            "id": "video-3",
            "createTime": 0,
            "stats": {},
            "author": {"uniqueId": "author"},
            "challenges": [],
            "video": {
                "downloadAddr": "https://cdn.example/download.mp4",
            },
        }
    )

    stream = await video.bytes(stream=True, browser_chunk_size=4, stream_chunk_size=4)
    received = []
    async for chunk in stream:
        received.append(chunk)

    assert received == [b"abcd", b"efgh", b"ij"]
    assert fetch_calls == [
        {
            "url": "https://cdn.example/download.mp4",
            "range": "bytes=0-3",
            "session_index": 0,
        }
    ]
    assert capture_calls == [
        {
            "url": "https://cdn.example/download.mp4",
            "headers": {
                "user-agent": "DummyAgent/1.0",
                "range": "bytes=0-",
                "accept-encoding": "identity;q=1, *;q=0",
                "referer": "https://www.tiktok.com/",
            },
            "session_index": 0,
        }
    ]
