from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from math import log
from typing import Iterable

from .models import (
    CollectorPlatform,
    IdentityStatus,
    RouteCandidate,
    RouteDecision,
    RouteTarget,
    RoutingStrategy,
)


class RouteUnavailable(RuntimeError):
    def __init__(self, message: str, *, target_key: str = "", identity_id: str = ""):
        super().__init__(message)
        self.target_key = target_key
        self.identity_id = identity_id


def _parse_datetime(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def candidate_available(
    candidate: RouteCandidate,
    *,
    platform: CollectorPlatform,
    now: datetime | None = None,
) -> bool:
    if candidate.platform != platform or not candidate.enabled:
        return False
    if candidate.status in {IdentityStatus.DISABLED, IdentityStatus.INVALID}:
        return False
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    cooldown_until = _parse_datetime(candidate.cooldown_until)
    if cooldown_until and cooldown_until > current.astimezone(timezone.utc):
        return False
    if candidate.status == IdentityStatus.COOLDOWN and cooldown_until is None:
        return False
    # Saturated identities remain routable: the lease manager queues work at
    # the configured concurrency boundary. Treating saturation as unhealthy
    # would make a second UI worker fail instead of waiting safely.
    return True


def eligible_candidates(
    candidates: Iterable[RouteCandidate],
    *,
    platform: CollectorPlatform,
    now: datetime | None = None,
) -> list[RouteCandidate]:
    return sorted(
        (
            candidate
            for candidate in candidates
            if candidate_available(candidate, platform=platform, now=now)
        ),
        key=lambda item: item.identity_id,
    )


def _hash_fraction(*parts: str) -> float:
    digest = sha256("\x00".join(parts).encode("utf-8")).digest()
    number = int.from_bytes(digest, "big") + 1
    return number / ((1 << (len(digest) * 8)) + 1)


class StickyBalancedRouter:
    """Deterministic weighted rendezvous hashing.

    A target remains on the same identity while the eligible identity set is
    unchanged. Removing one identity only remaps targets owned by that identity.
    """

    strategy = RoutingStrategy.STICKY_BALANCED

    @staticmethod
    def choose(
        platform: CollectorPlatform,
        target_key: str,
        candidates: Iterable[RouteCandidate],
    ) -> RouteCandidate:
        items = list(candidates)
        if not items:
            raise RouteUnavailable("no eligible collector identity", target_key=target_key)

        def score(candidate: RouteCandidate) -> tuple[float, str]:
            uniform = _hash_fraction(platform.value, target_key, candidate.identity_id)
            weighted = candidate.weight / -log(uniform)
            return weighted, candidate.identity_id

        return max(items, key=score)


class LeastLoadedRouter:
    strategy = RoutingStrategy.LEAST_LOADED

    @staticmethod
    def choose(
        platform: CollectorPlatform,
        target_key: str,
        candidates: Iterable[RouteCandidate],
        *,
        planned: dict[str, int] | None = None,
    ) -> RouteCandidate:
        items = list(candidates)
        if not items:
            raise RouteUnavailable("no eligible collector identity", target_key=target_key)
        planned = planned or {}

        def score(candidate: RouteCandidate) -> tuple[float, int, str]:
            virtual_active = candidate.active_leases + planned.get(candidate.identity_id, 0)
            capacity = candidate.max_concurrency * candidate.weight
            normalized_load = virtual_active / capacity
            tie_break = int.from_bytes(
                sha256(
                    f"{platform.value}\x00{target_key}\x00{candidate.identity_id}".encode(
                        "utf-8"
                    )
                ).digest()[:8],
                "big",
            )
            return normalized_load, tie_break, candidate.identity_id

        return min(items, key=score)


def route_target(
    *,
    platform: CollectorPlatform,
    target: RouteTarget,
    candidates: Iterable[RouteCandidate],
    strategy: RoutingStrategy = RoutingStrategy.STICKY_BALANCED,
    now: datetime | None = None,
) -> RouteDecision:
    all_candidates = list(candidates)
    eligible = eligible_candidates(all_candidates, platform=platform, now=now)
    if target.explicit_identity_id:
        selected = next(
            (
                candidate
                for candidate in eligible
                if candidate.identity_id == target.explicit_identity_id
            ),
            None,
        )
        if selected is None:
            raise RouteUnavailable(
                "bound collector identity is unavailable",
                target_key=target.target_key,
                identity_id=target.explicit_identity_id,
            )
        return RouteDecision(
            target_key=target.target_key,
            identity_id=selected.identity_id,
            strategy=strategy,
            explicit=True,
        )

    router = (
        LeastLoadedRouter
        if strategy == RoutingStrategy.LEAST_LOADED
        else StickyBalancedRouter
    )
    selected = router.choose(platform, target.target_key, eligible)
    return RouteDecision(
        target_key=target.target_key,
        identity_id=selected.identity_id,
        strategy=strategy,
    )


def plan_routes(
    *,
    platform: CollectorPlatform,
    targets: Iterable[RouteTarget],
    candidates: Iterable[RouteCandidate],
    strategy: RoutingStrategy = RoutingStrategy.STICKY_BALANCED,
    now: datetime | None = None,
) -> list[RouteDecision]:
    """Plan a batch without mutating candidates or global routing state."""

    all_candidates = list(candidates)
    eligible = eligible_candidates(all_candidates, platform=platform, now=now)
    planned: dict[str, int] = {}
    decisions: list[RouteDecision] = []

    for target in targets:
        if target.explicit_identity_id:
            decision = route_target(
                platform=platform,
                target=target,
                candidates=all_candidates,
                strategy=strategy,
                now=now,
            )
        elif strategy == RoutingStrategy.LEAST_LOADED:
            selected = LeastLoadedRouter.choose(
                platform,
                target.target_key,
                eligible,
                planned=planned,
            )
            decision = RouteDecision(
                target_key=target.target_key,
                identity_id=selected.identity_id,
                strategy=strategy,
            )
        else:
            selected = StickyBalancedRouter.choose(
                platform,
                target.target_key,
                eligible,
            )
            decision = RouteDecision(
                target_key=target.target_key,
                identity_id=selected.identity_id,
                strategy=strategy,
            )
        decisions.append(decision)
        planned[decision.identity_id] = planned.get(decision.identity_id, 0) + 1

    return decisions
