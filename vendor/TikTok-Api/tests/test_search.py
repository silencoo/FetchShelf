from TikTokApi import TikTokApi
from TikTokApi.api.search import Search
import os
import pytest
from types import SimpleNamespace

ms_token = os.environ.get("ms_token", None)
headless = os.environ.get("headless", "True").lower() == "true"


@pytest.mark.asyncio
async def test_users_single_page():
    api = TikTokApi()
    async with api:
        await api.create_sessions(
            ms_tokens=[ms_token],
            num_sessions=1,
            sleep_after=3,
            browser=os.getenv("TIKTOK_BROWSER", "chromium"),
            headless=headless,
        )
        count = 0
        async for user in api.search.users("therock", count=10):
            count += 1

        assert count >= 10


# @pytest.mark.asyncio
@pytest.mark.skip(
    reason="Known issue, see #1088 (https://github.com/davidteather/TikTok-Api/issues/1088)"
)
async def test_users_multi_page():
    api = TikTokApi()
    async with api:
        await api.create_sessions(
            ms_tokens=[ms_token],
            num_sessions=1,
            sleep_after=3,
            browser=os.getenv("TIKTOK_BROWSER", "chromium"),
            headless=headless,
        )
        count = 0
        async for user in api.search.users("therock", count=50):
            count += 1

        assert count >= 50


@pytest.mark.asyncio
async def test_search_users_reuses_search_id_between_pages(monkeypatch):
    calls = []
    responses = [
        {
            "user_list": [
                {
                    "user_info": {
                        "sec_uid": "sec-1",
                        "user_id": "user-1",
                        "unique_id": "name-1",
                    }
                }
            ],
            "has_more": True,
            "cursor": 1,
            "rid": "rid-1",
        },
        {
            "user_list": [
                {
                    "user_info": {
                        "sec_uid": "sec-2",
                        "user_id": "user-2",
                        "unique_id": "name-2",
                    }
                }
            ],
            "has_more": False,
            "cursor": 2,
            "rid": "rid-2",
        },
    ]

    async def fake_make_request(url, params, headers=None, session_index=None):
        calls.append(params.copy())
        return responses.pop(0)

    fake_parent = SimpleNamespace(
        make_request=fake_make_request,
        user=lambda **kwargs: kwargs,
    )
    monkeypatch.setattr(Search, "parent", fake_parent, raising=False)

    found = []
    async for user in Search.users("therock", count=2):
        found.append(user)

    assert [user["username"] for user in found] == ["name-1", "name-2"]
    assert "search_id" not in calls[0]
    assert calls[1]["search_id"] == "rid-1"


@pytest.mark.asyncio
async def test_search_items_stops_at_requested_count(monkeypatch):
    calls = []
    responses = [
        {
            "item_list": [{"id": "video-1"}, {"id": "video-2"}],
            "has_more": True,
            "cursor": 1,
            "rid": "rid-1",
        },
        {
            "item_list": [{"id": "video-3"}, {"id": "video-4"}],
            "has_more": False,
            "cursor": 2,
            "rid": "rid-2",
        },
    ]

    async def fake_make_request(url, params, headers=None, session_index=None):
        calls.append(params.copy())
        return responses.pop(0)

    fake_parent = SimpleNamespace(
        make_request=fake_make_request,
        video=lambda data: data["id"],
    )
    monkeypatch.setattr(Search, "parent", fake_parent, raising=False)

    found = []
    async for video in Search.search_type("cat", "item", count=3):
        found.append(video)

    assert found == ["video-1", "video-2", "video-3"]
    assert calls[1]["search_id"] == "rid-1"
