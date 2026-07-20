from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


IDENTITY_ID_PATTERN = r"^[a-z0-9][a-z0-9_-]{2,63}$"
TARGET_TYPE_PATTERN = r"^[a-z][a-z0-9_-]{0,31}$"


class CollectorPlatform(StrEnum):
    DOUYIN = "douyin"
    TIKTOK = "tiktok"


class RoutingStrategy(StrEnum):
    STICKY_BALANCED = "sticky_balanced"
    LEAST_LOADED = "least_loaded"


class BindingFailureMode(StrEnum):
    PAUSE = "pause"
    FALLBACK = "fallback"


class IdentityStatus(StrEnum):
    UNTESTED = "untested"
    HEALTHY = "healthy"
    WARNING = "warning"
    COOLDOWN = "cooldown"
    INVALID = "invalid"
    DISABLED = "disabled"


class AssignmentSource(StrEnum):
    EXPLICIT = "explicit"
    POLICY = "policy"
    LEGACY = "legacy"


class CollectorIdentity(BaseModel):
    """Stable, non-secret identity metadata.

    ``identity_id`` is used by sticky routing and should be treated as immutable
    after creation. Credentials deliberately live in a separate model/table.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    identity_id: str = Field(pattern=IDENTITY_ID_PATTERN)
    name: str = Field(min_length=1, max_length=80)
    platform: CollectorPlatform
    enabled: bool = True
    weight: float = Field(default=1.0, gt=0, le=100)
    request_delay: float = Field(default=6.0, ge=0, le=3600)
    max_concurrency: int = Field(default=1, ge=1, le=16)


class CollectorCredentials(BaseModel):
    """Write-only fingerprint/session material for one collector identity."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    cookie: str = Field(default="", repr=False)
    proxy: str = Field(default="", repr=False)
    user_agent: str = Field(default="", repr=False)
    device_id: str = Field(default="", repr=False)
    browser_info: dict[str, str] = Field(default_factory=dict, repr=False)

    @field_validator("browser_info", mode="before")
    @classmethod
    def normalize_browser_info(cls, value: Any) -> dict[str, str]:
        if not isinstance(value, dict):
            return {}
        return {
            str(key): str(item)
            for key, item in value.items()
            if item is not None
        }

    @property
    def configured(self) -> bool:
        return any(
            (
                self.cookie,
                self.proxy,
                self.user_agent,
                self.device_id,
                self.browser_info,
            )
        )


class CollectorRuntimeState(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    identity_id: str = Field(pattern=IDENTITY_ID_PATTERN)
    status: IdentityStatus = IdentityStatus.UNTESTED
    active_leases: int = Field(default=0, ge=0)
    consecutive_failures: int = Field(default=0, ge=0)
    total_successes: int = Field(default=0, ge=0)
    total_failures: int = Field(default=0, ge=0)
    cooldown_until: str = ""
    last_validated_at: str = ""
    last_success_at: str = ""
    last_failure_at: str = ""
    last_error_code: str = Field(default="", pattern=r"^[a-z0-9_.-]{0,120}$")


class CollectorIdentityPublic(BaseModel):
    """Safe response model; it intentionally has no credential value fields."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    identity_id: str = Field(pattern=IDENTITY_ID_PATTERN)
    name: str
    platform: CollectorPlatform
    enabled: bool
    weight: float
    request_delay: float
    max_concurrency: int
    credential_configured: bool = False
    cookie_configured: bool = False
    proxy_configured: bool = False
    user_agent_configured: bool = False
    device_id_configured: bool = False
    status: IdentityStatus = IdentityStatus.UNTESTED
    active_leases: int = 0
    cooldown_until: str = ""
    last_validated_at: str = ""
    last_error_code: str = ""
    created_at: str = ""
    updated_at: str = ""


class CollectorPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    platform: CollectorPlatform
    strategy: RoutingStrategy = RoutingStrategy.STICKY_BALANCED
    default_identity_id: str = ""
    fallback_identity_ids: list[str] = Field(default_factory=list, max_length=64)
    global_max_parallel: int = Field(default=2, ge=1, le=64)
    binding_failure: BindingFailureMode = BindingFailureMode.PAUSE
    failure_threshold: int = Field(default=3, ge=1, le=100)
    cooldown_seconds: int = Field(default=1800, ge=0, le=604800)

    @field_validator("default_identity_id")
    @classmethod
    def validate_default_identity_id(cls, value: str) -> str:
        if value:
            return cls._validate_identity_id(value)
        return ""

    @field_validator("fallback_identity_ids")
    @classmethod
    def validate_fallback_identity_ids(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for value in values:
            item = cls._validate_identity_id(value)
            if item not in seen:
                normalized.append(item)
                seen.add(item)
        return normalized

    @staticmethod
    def _validate_identity_id(value: str) -> str:
        from re import fullmatch

        if not fullmatch(IDENTITY_ID_PATTERN, value):
            raise ValueError("invalid collector identity id")
        return value


class CollectorAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    platform: CollectorPlatform
    target_type: str = Field(default="account", pattern=TARGET_TYPE_PATTERN)
    target_key: str = Field(min_length=1, max_length=2048)
    identity_id: str = Field(pattern=IDENTITY_ID_PATTERN)
    source: AssignmentSource = AssignmentSource.EXPLICIT
    updated_at: str = ""


class RouteCandidate(BaseModel):
    """Pure routing input, independent from persistence and request clients."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    identity_id: str = Field(pattern=IDENTITY_ID_PATTERN)
    platform: CollectorPlatform
    enabled: bool = True
    weight: float = Field(default=1.0, gt=0, le=100)
    active_leases: int = Field(default=0, ge=0)
    max_concurrency: int = Field(default=1, ge=1, le=16)
    status: IdentityStatus = IdentityStatus.UNTESTED
    cooldown_until: str = ""


class RouteTarget(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    target_key: str = Field(min_length=1, max_length=2048)
    explicit_identity_id: str = ""

    @field_validator("explicit_identity_id")
    @classmethod
    def validate_explicit_identity_id(cls, value: str) -> str:
        if not value:
            return ""
        from re import fullmatch

        if not fullmatch(IDENTITY_ID_PATTERN, value):
            raise ValueError("invalid collector identity id")
        return value


class RouteDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    target_key: str
    identity_id: str
    strategy: RoutingStrategy
    explicit: bool = False


class LegacyMigrationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    migrated: bool
    identities: list[CollectorIdentity] = Field(default_factory=list)
    credentials: dict[str, CollectorCredentials] = Field(default_factory=dict)
    policies: list[CollectorPolicy] = Field(default_factory=list)
