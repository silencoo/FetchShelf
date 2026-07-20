from collections import Counter
from datetime import datetime, timedelta, timezone

import pytest

from src.collector import (
    CollectorPlatform,
    IdentityStatus,
    RouteCandidate,
    RouteTarget,
    RouteUnavailable,
    RoutingStrategy,
    candidate_available,
    plan_routes,
    route_target,
)


def candidate(
    identity_id: str,
    *,
    weight: float = 1,
    active: int = 0,
    limit: int = 1,
    status: IdentityStatus = IdentityStatus.HEALTHY,
    cooldown_until: str = "",
) -> RouteCandidate:
    return RouteCandidate(
        identity_id=identity_id,
        platform=CollectorPlatform.TIKTOK,
        weight=weight,
        active_leases=active,
        max_concurrency=limit,
        status=status,
        cooldown_until=cooldown_until,
    )


def test_sticky_balanced_is_deterministic_independent_of_candidate_order():
    candidates = [candidate("tt-one"), candidate("tt-two"), candidate("tt-three")]
    targets = [RouteTarget(target_key=f"@account-{index}") for index in range(100)]

    first = plan_routes(
        platform=CollectorPlatform.TIKTOK,
        targets=targets,
        candidates=candidates,
    )
    second = plan_routes(
        platform=CollectorPlatform.TIKTOK,
        targets=targets,
        candidates=reversed(candidates),
    )

    assert first == second


def test_sticky_balanced_only_remaps_targets_owned_by_removed_identity():
    targets = [RouteTarget(target_key=f"target-{index}") for index in range(500)]
    all_candidates = [candidate("tt-one"), candidate("tt-two"), candidate("tt-three")]
    before = {
        item.target_key: item.identity_id
        for item in plan_routes(
            platform=CollectorPlatform.TIKTOK,
            targets=targets,
            candidates=all_candidates,
        )
    }
    after = {
        item.target_key: item.identity_id
        for item in plan_routes(
            platform=CollectorPlatform.TIKTOK,
            targets=targets,
            candidates=all_candidates[:2],
        )
    }

    assert all(
        after[key] == identity_id
        for key, identity_id in before.items()
        if identity_id != "tt-three"
    )


def test_sticky_balanced_honors_weight_over_large_sample():
    candidates = [candidate("tt-one", weight=1), candidate("tt-heavy", weight=3)]
    decisions = plan_routes(
        platform=CollectorPlatform.TIKTOK,
        targets=[RouteTarget(target_key=f"target-{index}") for index in range(4000)],
        candidates=candidates,
    )
    counts = Counter(item.identity_id for item in decisions)
    heavy_ratio = counts["tt-heavy"] / len(decisions)

    assert 0.70 < heavy_ratio < 0.80


def test_least_loaded_batch_planning_balances_virtual_work():
    decisions = plan_routes(
        platform=CollectorPlatform.TIKTOK,
        targets=[RouteTarget(target_key=f"target-{index}") for index in range(12)],
        candidates=[candidate("tt-one", limit=2), candidate("tt-two", limit=2)],
        strategy=RoutingStrategy.LEAST_LOADED,
    )
    counts = Counter(item.identity_id for item in decisions)

    assert counts == {"tt-one": 6, "tt-two": 6}


def test_explicit_binding_wins_and_unavailable_binding_never_silently_rotates():
    candidates = [candidate("tt-one"), candidate("tt-two")]
    decision = route_target(
        platform=CollectorPlatform.TIKTOK,
        target=RouteTarget(
            target_key="@bound",
            explicit_identity_id="tt-two",
        ),
        candidates=candidates,
    )

    assert decision.identity_id == "tt-two"
    assert decision.explicit is True

    with pytest.raises(RouteUnavailable) as captured:
        route_target(
            platform=CollectorPlatform.TIKTOK,
            target=RouteTarget(
                target_key="@bound",
                explicit_identity_id="tt-two",
            ),
            candidates=[candidate("tt-one")],
        )
    assert captured.value.identity_id == "tt-two"


def test_cooldown_blocks_until_deadline_but_expired_cooldown_is_eligible():
    now = datetime.now(timezone.utc)
    future = (now + timedelta(minutes=10)).isoformat()
    past = (now - timedelta(minutes=10)).isoformat()

    assert not candidate_available(
        candidate("tt-one", status=IdentityStatus.COOLDOWN, cooldown_until=future),
        platform=CollectorPlatform.TIKTOK,
        now=now,
    )
    assert candidate_available(
        candidate("tt-one", status=IdentityStatus.COOLDOWN, cooldown_until=past),
        platform=CollectorPlatform.TIKTOK,
        now=now,
    )


def test_saturated_identity_remains_routable_for_lease_queueing():
    assert candidate_available(
        candidate("tt-one", active=1, limit=1),
        platform=CollectorPlatform.TIKTOK,
    )
