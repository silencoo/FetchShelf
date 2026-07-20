from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from .models import (
    CollectorCredentials,
    CollectorIdentity,
    CollectorPlatform,
    CollectorPolicy,
    LegacyMigrationResult,
)


def _cookie_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, Mapping):
        return "; ".join(
            f"{key}={item}"
            for key, item in value.items()
            if str(key).strip() and item not in (None, "")
        )
    return ""


def _proxy_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, Mapping):
        for key in ("https://", "http://", "all://"):
            if proxy := value.get(key):
                return str(proxy).strip()
    return ""


def _browser_info(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    return {
        str(key): str(item)
        for key, item in value.items()
        if item is not None
    }


def _coerce_bool(value: Any, *, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return default
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on", "enabled", "开启", "启用"}:
            return True
        if normalized in {"0", "false", "no", "off", "disabled", "关闭", "禁用"}:
            return False
    return default


def migrate_legacy_settings(settings: Mapping[str, Any]) -> LegacyMigrationResult:
    """Build a collector pool from legacy singleton fields without mutating input.

    The caller decides when to persist the returned objects. Once a collector
    schema marker or an explicit identity list exists, migration becomes a no-op;
    this prevents a user who intentionally removed all identities from having
    legacy identities recreated on every restart.
    """

    data = deepcopy(dict(settings))
    if data.get("collector_schema_version") or data.get("collector_identities"):
        return LegacyMigrationResult(migrated=False)

    try:
        request_delay = max(0.0, float(data.get("request_delay", 6.0)))
    except (TypeError, ValueError):
        request_delay = 6.0

    identities: list[CollectorIdentity] = []
    credentials: dict[str, CollectorCredentials] = {}
    policies: list[CollectorPolicy] = []

    specs = (
        (
            CollectorPlatform.DOUYIN,
            "legacy-douyin",
            "旧配置 · 抖音",
            "cookie",
            "proxy",
            "browser_info",
            "douyin_platform",
        ),
        (
            CollectorPlatform.TIKTOK,
            "legacy-tiktok",
            "旧配置 · TikTok",
            "cookie_tiktok",
            "proxy_tiktok",
            "browser_info_tiktok",
            "tiktok_platform",
        ),
    )

    for platform, identity_id, name, cookie_key, proxy_key, browser_key, enable_key in specs:
        info = _browser_info(data.get(browser_key))
        identity = CollectorIdentity(
            identity_id=identity_id,
            name=name,
            platform=platform,
            enabled=_coerce_bool(data.get(enable_key), default=True),
            request_delay=request_delay,
            max_concurrency=1,
        )
        credential = CollectorCredentials(
            cookie=_cookie_text(data.get(cookie_key)),
            proxy=_proxy_text(data.get(proxy_key)),
            user_agent=info.get("User-Agent", ""),
            device_id=info.get("device_id", "") if platform == CollectorPlatform.TIKTOK else "",
            browser_info=info,
        )
        identities.append(identity)
        credentials[identity_id] = credential
        policies.append(
            CollectorPolicy(
                platform=platform,
                default_identity_id=identity_id,
            )
        )

    return LegacyMigrationResult(
        migrated=True,
        identities=identities,
        credentials=credentials,
        policies=policies,
    )
