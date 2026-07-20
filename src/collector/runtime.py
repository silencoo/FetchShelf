from __future__ import annotations

from copy import copy, deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from ..encrypt import ABogus, XBogus, XGnarly
from ..module import TikTokAPIBridge
from ..tools import cookie_str_to_dict, create_client
from .models import CollectorCredentials, CollectorIdentity, CollectorPlatform

if TYPE_CHECKING:
    from httpx import AsyncClient

    from ..config import Parameter


_HEADER_FIELDS = (
    "headers",
    "headers_tiktok",
    "headers_download",
    "headers_download_tiktok",
    "headers_params",
    "headers_params_tiktok",
    "headers_qrcode",
)

_DOUYIN_PARAM_FIELDS = (
    "pc_libra_divert",
    "browser_language",
    "browser_platform",
    "browser_name",
    "browser_version",
    "engine_name",
    "engine_version",
    "os_name",
    "os_version",
)

_TIKTOK_PARAM_FIELDS = (
    "app_language",
    "browser_language",
    "browser_name",
    "browser_platform",
    "browser_version",
    "language",
    "os",
    "priority_region",
    "region",
    "tz_name",
    "webcast_language",
    "device_id",
)


def _clone_signer(value: Any) -> Any:
    try:
        return deepcopy(value)
    except Exception:
        try:
            return type(value)()
        except Exception:
            # External signers are user-supplied. Keeping their instance is a
            # compatibility fallback; built-in stateful signers are replaced
            # explicitly below.
            return value


@dataclass(slots=True)
class CollectorRuntimeContext:
    """One isolated Parameter view and its owned HTTP client."""

    identity: CollectorIdentity
    credentials: CollectorCredentials
    parameter: "Parameter"
    owned_client: "AsyncClient"

    async def close(self) -> None:
        if self.identity.platform == CollectorPlatform.TIKTOK:
            await TikTokAPIBridge.close_for_params(self.parameter)
        await self.owned_client.aclose()

    async def __aenter__(self) -> "CollectorRuntimeContext":
        return self

    async def __aexit__(self, exc_type, exc_value, traceback) -> None:
        await self.close()


def build_collector_runtime(
    base: "Parameter",
    identity: CollectorIdentity,
    credentials: CollectorCredentials,
    *,
    settings_dir: str | Path,
    client_factory: Callable[..., "AsyncClient"] = create_client,
) -> CollectorRuntimeContext:
    """Create an identity-scoped view without mutating the global Parameter.

    The non-selected platform deliberately keeps the base clients because the
    worker never dispatches work to it. Only the selected platform client is
    owned and closed by the returned context.
    """

    parameter = copy(base)
    for name in _HEADER_FIELDS:
        setattr(parameter, name, dict(getattr(base, name, {}) or {}))
    parameter.browser_info = dict(getattr(base, "browser_info", {}) or {})
    parameter.browser_info_tiktok = dict(
        getattr(base, "browser_info_tiktok", {}) or {}
    )
    parameter.api_params = {}
    parameter.api_params_tiktok = {}
    parameter.collector_identity_id = identity.identity_id
    parameter.request_delay = identity.request_delay

    info = dict(credentials.browser_info)
    if credentials.user_agent:
        info["User-Agent"] = credentials.user_agent
    if credentials.device_id:
        info["device_id"] = credentials.device_id
    cookie = credentials.cookie
    cookie_dict = cookie_str_to_dict(cookie)
    user_agent = info.get("User-Agent") or (
        parameter.headers_tiktok.get("User-Agent", "")
        if identity.platform == CollectorPlatform.TIKTOK
        else parameter.headers.get("User-Agent", "")
    )
    owned_client = client_factory(
        user_agent=user_agent,
        timeout=parameter.timeout,
        proxy=credentials.proxy or None,
    )

    if identity.platform == CollectorPlatform.DOUYIN:
        parameter.browser_info.update(info)
        parameter.cookie_dict = cookie_dict
        parameter.cookie_str = cookie
        parameter.cookie_state = bool(cookie)
        parameter.proxy = credentials.proxy or None
        parameter.client = owned_client
        parameter.api_params = {
            key: info[key]
            for key in _DOUYIN_PARAM_FIELDS
            if info.get(key) not in (None, "")
        }
        parameter.api_params["uifid"] = cookie_dict.get("UIFID", "")
        parameter.api_params["msToken"] = cookie_dict.get("msToken", "")
        for name in (
            "headers",
            "headers_download",
            "headers_params",
            "headers_qrcode",
        ):
            headers = getattr(parameter, name)
            if user_agent:
                headers["User-Agent"] = user_agent
        if cookie:
            parameter.headers["Cookie"] = cookie
            parameter.headers_download["Cookie"] = cookie
        if "ABogus" in getattr(base, "_external_signers", set()):
            parameter.ab = _clone_signer(base.ab)
        else:
            parameter.ab = ABogus(user_agent, info.get("browser_platform") or None)
    else:
        parameter.browser_info_tiktok.update(info)
        parameter.cookie_dict_tiktok = cookie_dict
        parameter.cookie_str_tiktok = cookie
        parameter.cookie_tiktok_state = bool(cookie)
        parameter.proxy_tiktok = credentials.proxy or None
        parameter.client_tiktok = owned_client
        parameter.ms_token_tiktok = cookie_dict.get("msToken", "")
        parameter.api_params_tiktok = {
            key: info[key]
            for key in _TIKTOK_PARAM_FIELDS
            if info.get(key) not in (None, "")
        }
        parameter.api_params_tiktok["msToken"] = parameter.ms_token_tiktok
        profile_dir = Path(settings_dir).joinpath(
            "browser_profiles",
            identity.identity_id,
        )
        profile_dir.mkdir(parents=True, exist_ok=True)
        profile_dir.chmod(0o700)
        parameter.tiktok_api_profile_dir = str(profile_dir.resolve())
        for name in (
            "headers_tiktok",
            "headers_download_tiktok",
            "headers_params_tiktok",
        ):
            headers = getattr(parameter, name)
            if user_agent:
                headers["User-Agent"] = user_agent
        if cookie:
            parameter.headers_tiktok["Cookie"] = cookie
            parameter.headers_download_tiktok["Cookie"] = cookie
        parameter.xb = (
            _clone_signer(base.xb)
            if "XBogus" in getattr(base, "_external_signers", set())
            else XBogus()
        )
        parameter.xg = (
            _clone_signer(base.xg)
            if "XGnarly" in getattr(base, "_external_signers", set())
            else XGnarly()
        )

    return CollectorRuntimeContext(
        identity=identity,
        credentials=credentials,
        parameter=parameter,
        owned_client=owned_client,
    )
