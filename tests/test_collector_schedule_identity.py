from types import SimpleNamespace

import pytest

from src.application.main_server import APIServer
from src.collector import (
    CollectorPlatform,
    IdentityNotFoundError,
    RouteUnavailable,
)


def test_workflow_account_identity_id_type_validation():
    APIServer._validate_ui_workflow_account_payload(
        {
            "use_settings": True,
            "items": [],
            "identity_id": "tt-main",
        }
    )

    with pytest.raises(ValueError, match="identity_id"):
        APIServer._validate_ui_workflow_account_payload(
            {
                "use_settings": True,
                "items": [],
                "identity_id": 123,
            }
        )


def test_schedule_identity_id_round_trips_to_workflow_payload():
    server = APIServer.__new__(APIServer)
    schedule = APIServer._normalize_schedule_payload(
        server,
        {
            "name": "Nightly TikTok",
            "platform": "tiktok",
            "hour": 2,
            "minute": 30,
            "use_settings": True,
            "items": [],
            "identity_id": "  tt-main  ",
        },
    )

    endpoint, payload = APIServer._schedule_task_payload(server, schedule)

    assert schedule["identity_id"] == "tt-main"
    assert endpoint == "/workflow/tiktok/account_batch"
    assert payload["identity_id"] == "tt-main"
    APIServer._validate_ui_task_payload(endpoint, payload)


def test_schedule_identity_id_type_validation():
    with pytest.raises(ValueError, match="identity_id"):
        APIServer._validate_ui_schedule_payload(
            {
                "platform": "tiktok",
                "identity_id": 123,
            }
        )


def test_schedule_identity_reference_must_exist_and_match_platform():
    server = APIServer.__new__(APIServer)
    server.collector_store = SimpleNamespace(
        get_identity=lambda identity_id: SimpleNamespace(
            platform=CollectorPlatform.TIKTOK,
        )
    )

    server._validate_schedule_identity_reference(
        {
            "platform": "tiktok",
            "identity_id": "tt-main",
        }
    )

    with pytest.raises(ValueError, match="another platform"):
        server._validate_schedule_identity_reference(
            {
                "platform": "douyin",
                "identity_id": "tt-main",
            }
        )

    server.collector_store = SimpleNamespace(
        get_identity=lambda identity_id: (_ for _ in ()).throw(
            IdentityNotFoundError(identity_id)
        )
    )
    with pytest.raises(ValueError, match="existing identity"):
        server._validate_schedule_identity_reference(
            {
                "platform": "tiktok",
                "identity_id": "missing",
            }
        )


@pytest.mark.asyncio
async def test_account_workflow_forwards_forced_identity_to_route_planner():
    server = APIServer.__new__(APIServer)
    server.parameter = SimpleNamespace(
        accounts_urls=[],
        accounts_urls_tiktok=[],
        earliest_update_days=0,
    )
    captured = {}

    def plan_routes(platform, items, *, forced_identity_id=""):
        captured["platform"] = platform
        captured["items"] = items
        captured["forced_identity_id"] = forced_identity_id
        return []

    server._plan_collector_account_routes = plan_routes
    server.collector_store = SimpleNamespace(list_public=lambda platform: [])

    with pytest.raises(RouteUnavailable, match="no eligible collector identity"):
        await APIServer._run_ui_account_batch(
            server,
            {
                "use_settings": False,
                "items": [
                    {
                        "url": "https://www.tiktok.com/@demo",
                        "enable": True,
                    }
                ],
                "identity_id": "tt-main",
            },
            True,
        )

    assert captured["platform"] is CollectorPlatform.TIKTOK
    assert captured["forced_identity_id"] == "tt-main"
    assert captured["items"][0]["url"] == "https://www.tiktok.com/@demo"
