import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.application import main_server as main_server_module
from src.application.main_server import APIServer
from src.collector import (
    AESGCMSecretCodec,
    AssignmentSource,
    BindingFailureMode,
    CollectorAssignment,
    CollectorCredentials,
    CollectorIdentity,
    CollectorPlatform,
    CollectorPolicy,
    CollectorStore,
    IdentityLeaseManager,
    IdentityStatus,
    RouteUnavailable,
    RoutingStrategy,
)


class _Runtime:
    def __init__(self, identity):
        self.parameter = SimpleNamespace(collector_identity_id=identity.identity_id)

    async def close(self):
        return None


@pytest.mark.asyncio
async def test_account_batch_parallelizes_between_identities_not_within_one(
    tmp_path: Path,
    monkeypatch,
):
    server = APIServer.__new__(APIServer)
    server.collector_store = CollectorStore(
        tmp_path / "collector.sqlite3",
        codec=AESGCMSecretCodec(b"p" * 32),
    )
    server.collector_leases = IdentityLeaseManager()
    server.database = object()
    server.console = SimpleNamespace()
    server.logger = SimpleNamespace(info=lambda *args, **kwargs: None)
    server.parameter = SimpleNamespace(
        accounts_urls=[],
        accounts_urls_tiktok=[],
        earliest_update_days=3,
        auto_backfill_mark=True,
        settings=SimpleNamespace(path=tmp_path / "settings.json"),
    )
    server._persist_account_runtime_updates = lambda **kwargs: None

    identities = []
    for identity_id in ("dy-one", "dy-two"):
        identity = CollectorIdentity(
            identity_id=identity_id,
            name=identity_id,
            platform="douyin",
            max_concurrency=1,
        )
        server.collector_store.save_identity(
            identity,
            credentials=CollectorCredentials(cookie=f"sessionid={identity_id}"),
        )
        identities.append(identity)
        await server.collector_leases.configure(identity_id, 1)
    await server.collector_leases.configure("platform:douyin", 2)

    items = [
        {"mark": key, "url": f"https://www.douyin.com/user/{key}", "enable": True}
        for key in ("a", "b", "c", "d")
    ]
    assignments = []
    for index, item in enumerate(items):
        assignments.append(
            CollectorAssignment(
                platform="douyin",
                target_type="account",
                target_key=item["url"],
                identity_id=identities[index % 2].identity_id,
                source=AssignmentSource.EXPLICIT,
            )
        )
    server.collector_store.upsert_assignments(assignments)

    active = {identity.identity_id: 0 for identity in identities}
    max_per_identity = dict(active)
    total_active = 0
    max_total_active = 0

    class _Worker:
        def __init__(self, parameter, database, server_mode=True):
            self.identity_id = parameter.collector_identity_id

        async def check_sec_user_id(self, url, tiktok=False):
            return url.rsplit("/", 1)[-1]

        async def deal_account_detail(self, *args, **kwargs):
            nonlocal total_active, max_total_active
            active[self.identity_id] += 1
            total_active += 1
            max_per_identity[self.identity_id] = max(
                max_per_identity[self.identity_id],
                active[self.identity_id],
            )
            max_total_active = max(max_total_active, total_active)
            await asyncio.sleep(0.02)
            active[self.identity_id] -= 1
            total_active -= 1
            return {"mark": kwargs.get("mark", "")}

    monkeypatch.setattr(main_server_module, "TikTok", _Worker)
    monkeypatch.setattr(
        main_server_module,
        "build_collector_runtime",
        lambda base, identity, credentials, settings_dir: _Runtime(identity),
    )

    result = await server._run_ui_account_batch(
        {"use_settings": False, "items": items},
        tiktok=False,
    )

    assert result.data["success"] == 4
    assert result.data["failed"] == 0
    assert max_per_identity == {"dy-one": 1, "dy-two": 1}
    assert max_total_active == 2
    assert {route["identity_id"] for route in result.data["routes"]} == {
        "dy-one",
        "dy-two",
    }
    server.collector_store.close()


def _routing_server(tmp_path: Path) -> APIServer:
    server = APIServer.__new__(APIServer)
    server.collector_store = CollectorStore(
        tmp_path / "routing.sqlite3",
        codec=AESGCMSecretCodec(b"r" * 32),
    )
    for identity_id in ("dy-one", "dy-two"):
        server.collector_store.save_identity(
            CollectorIdentity(
                identity_id=identity_id,
                name=identity_id,
                platform=CollectorPlatform.DOUYIN,
            ),
            credentials=CollectorCredentials(cookie=f"sessionid={identity_id}"),
        )
    return server


def test_policy_sticky_assignment_rebalances_but_fixed_binding_obeys_failure_mode(
    tmp_path: Path,
):
    server = _routing_server(tmp_path)
    target = "https://www.douyin.com/user/target"
    server.collector_store.upsert_assignments(
        [
            CollectorAssignment(
                platform=CollectorPlatform.DOUYIN,
                target_type="account",
                target_key=target,
                identity_id="dy-one",
                source=AssignmentSource.POLICY,
            )
        ]
    )
    state = server.collector_store.get_runtime("dy-one")
    state.status = IdentityStatus.COOLDOWN
    state.cooldown_until = (
        datetime.now().astimezone() + timedelta(minutes=10)
    ).isoformat(timespec="seconds")
    server.collector_store.save_runtime(state)

    route = server._plan_collector_account_routes(
        CollectorPlatform.DOUYIN,
        [{"url": target}],
    )[0]
    assert route["identity_id"] == "dy-two"
    assert route["reason"] == "sticky_rebalanced"
    assert (
        server.collector_store.get_assignment(
            CollectorPlatform.DOUYIN,
            "account",
            target,
        ).identity_id
        == "dy-two"
    )

    server.collector_store.upsert_assignments(
        [
            CollectorAssignment(
                platform=CollectorPlatform.DOUYIN,
                target_type="account",
                target_key=target,
                identity_id="dy-one",
                source=AssignmentSource.EXPLICIT,
            )
        ]
    )
    with pytest.raises(RouteUnavailable):
        server._plan_collector_account_routes(
            CollectorPlatform.DOUYIN,
            [{"url": target}],
        )

    server.collector_store.upsert_policy(
        CollectorPolicy(
            platform=CollectorPlatform.DOUYIN,
            binding_failure=BindingFailureMode.FALLBACK,
        )
    )
    route = server._plan_collector_account_routes(
        CollectorPlatform.DOUYIN,
        [{"url": target}],
    )[0]
    assert route["identity_id"] == "dy-two"
    assert route["reason"] == "binding_fallback"
    assert (
        server.collector_store.get_assignment(
            CollectorPlatform.DOUYIN,
            "account",
            target,
        ).identity_id
        == "dy-one"
    )
    server.collector_store.close()


def test_runtime_enters_policy_cooldown_and_success_recovers(tmp_path: Path):
    server = _routing_server(tmp_path)
    server.collector_store.upsert_policy(
        CollectorPolicy(
            platform=CollectorPlatform.DOUYIN,
            failure_threshold=2,
            cooldown_seconds=60,
        )
    )

    server._update_collector_runtime_after_group(
        "dy-one",
        active_leases=0,
        failures=1,
    )
    assert server.collector_store.get_runtime("dy-one").status == IdentityStatus.WARNING

    server._update_collector_runtime_after_group(
        "dy-one",
        active_leases=0,
        failures=1,
    )
    state = server.collector_store.get_runtime("dy-one")
    assert state.status == IdentityStatus.COOLDOWN
    assert datetime.fromisoformat(state.cooldown_until) > datetime.now().astimezone()

    server._update_collector_runtime_after_group(
        "dy-one",
        active_leases=0,
        successes=1,
    )
    recovered = server.collector_store.get_runtime("dy-one")
    assert recovered.status == IdentityStatus.HEALTHY
    assert recovered.consecutive_failures == 0
    assert recovered.cooldown_until == ""
    server.collector_store.close()


def test_default_identity_and_fallback_priority_are_applied(tmp_path: Path):
    server = _routing_server(tmp_path)
    server.collector_store.upsert_policy(
        CollectorPolicy(
            platform=CollectorPlatform.DOUYIN,
            default_identity_id="dy-two",
            fallback_identity_ids=["dy-one"],
        )
    )
    target = {"url": "https://www.douyin.com/user/default-target"}

    route = server._plan_collector_account_routes(
        CollectorPlatform.DOUYIN,
        [target],
    )[0]
    assert route["identity_id"] == "dy-two"
    assert route["reason"] == "default_identity"

    state = server.collector_store.get_runtime("dy-two")
    state.status = IdentityStatus.COOLDOWN
    state.cooldown_until = (
        datetime.now().astimezone() + timedelta(minutes=5)
    ).isoformat(timespec="seconds")
    server.collector_store.save_runtime(state)
    fallback = server._plan_collector_account_routes(
        CollectorPlatform.DOUYIN,
        [target],
    )[0]
    assert fallback["identity_id"] == "dy-one"
    assert fallback["reason"] == "default_fallback"
    server.collector_store.close()


def test_proxy_only_identity_is_not_routable_without_cookie(tmp_path: Path):
    server = _routing_server(tmp_path)
    server.collector_store.save_identity(
        CollectorIdentity(
            identity_id="dy-proxy-only",
            name="Proxy only",
            platform=CollectorPlatform.DOUYIN,
        ),
        credentials=CollectorCredentials(proxy="socks5://proxy.test:1080"),
    )

    with pytest.raises(RouteUnavailable, match="no credentials"):
        server._plan_collector_account_routes(
            CollectorPlatform.DOUYIN,
            [{"url": "https://www.douyin.com/user/demo"}],
            forced_identity_id="dy-proxy-only",
        )
    server.collector_store.close()


def test_least_loaded_policy_does_not_turn_into_a_sticky_assignment(tmp_path: Path):
    server = _routing_server(tmp_path)
    server.collector_store.upsert_policy(
        CollectorPolicy(
            platform=CollectorPlatform.DOUYIN,
            strategy=RoutingStrategy.LEAST_LOADED,
        )
    )
    target = "https://www.douyin.com/user/dynamic-target"
    first = server.collector_store.get_runtime("dy-one")
    first.active_leases = 1
    server.collector_store.save_runtime(first)

    route = server._plan_collector_account_routes(
        CollectorPlatform.DOUYIN,
        [{"url": target}],
    )[0]
    assert route["identity_id"] == "dy-two"
    assert route["reason"] == RoutingStrategy.LEAST_LOADED.value
    assert (
        server.collector_store.get_assignment(
            CollectorPlatform.DOUYIN,
            "account",
            target,
        )
        is None
    )

    first.active_leases = 0
    server.collector_store.save_runtime(first)
    second = server.collector_store.get_runtime("dy-two")
    second.active_leases = 1
    server.collector_store.save_runtime(second)
    rerouted = server._plan_collector_account_routes(
        CollectorPlatform.DOUYIN,
        [{"url": target}],
    )[0]
    assert rerouted["identity_id"] == "dy-one"
    server.collector_store.close()
