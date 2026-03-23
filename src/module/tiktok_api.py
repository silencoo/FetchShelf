import asyncio
import hashlib
import importlib
import inspect
import json
import os
import re
import sys
import time
from datetime import datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit, urlunsplit

from aiofiles import open as aio_open

from ..custom import PROJECT_ROOT
from ..tools import cookie_str_to_dict
from ..translation import _
from .tiktok_risk import (
    TikTokRiskSignal,
    classify_api_payload,
    classify_exception,
    detect_risk_markers,
)

if TYPE_CHECKING:
    from ..config import Parameter


USERNAME_PATTERN = re.compile(r"tiktok\.com/@([^/?]+)")
DETAIL_URL_PATTERN = re.compile(
    r"(?P<prefix>https?://(?:www\.)?tiktok\.com/@[^/?#]+/)(?P<kind>video|photo)/(?P<id>\d+)",
    re.IGNORECASE,
)
DEFAULT_PROFILE_DIR = Path("cache") / "tiktok_api_profile"
DEFAULT_CLOAKBROWSER_FINGERPRINT_SEED = "52195"
REPO_ROOT = PROJECT_ROOT.parent
DEFAULT_VIEWPORT = {
    "width": 1323,
    "height": 827,
}


@dataclass
class SharedTikTokApiEntry:
    api: Any | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class TikTokAPIBridge:
    _shared_apis: dict[tuple[int, str], SharedTikTokApiEntry] = {}
    _param_api_keys: dict[tuple[int, int], set[tuple[int, str]]] = {}
    _risk_cooldowns: dict[str, TikTokRiskSignal] = {}
    _user_info_cache: dict[str, dict[str, Any]] = {}
    CAPTCHA_STAGE_MARKERS = {
        "captcha",
        "verify",
        "verification",
        "challenge",
        "slider",
        "security check",
        "请完成验证",
        "安全验证",
        "拖动滑块",
    }
    SLIDER_HANDLE_SELECTORS = (
        '[id*="captcha"] [class*="drag"]',
        '[id*="captcha"] [class*="slider"]',
        '[class*="captcha"] [class*="drag"]',
        '[class*="captcha"] [class*="slider"]',
        '[class*="secsdk-captcha"] [class*="drag"]',
        '[class*="secsdk-captcha"] [class*="slider"]',
        '[class*="verify"] [class*="drag"]',
        '[class*="verify"] [class*="slider"]',
        '[class*="slide"] [role="button"]',
        '[class*="drag-icon"]',
        '[aria-label*="slider" i]',
        '[aria-label*="drag" i]',
    )
    SLIDER_TRACK_SELECTORS = (
        '[id*="captcha"] [class*="track"]',
        '[class*="captcha"] [class*="track"]',
        '[class*="verify"] [class*="track"]',
        '[class*="slider"] [class*="track"]',
        '[class*="slide"] [class*="track"]',
    )

    def __init__(
        self,
        params: "Parameter",
        cookie: str | dict | None = None,
        proxy: str | dict | None = None,
    ) -> None:
        self.params = params
        self.log = params.logger
        self.cookie = cookie
        self.proxy = proxy
        self.browser = self._get_str_setting("tiktok_api_browser", "chromium")
        self.browser_engine = self._resolve_browser_engine(
            self._get_str_setting("tiktok_api_browser_engine", "cloakbrowser")
        )
        self.headless = self._get_bool_setting("tiktok_api_headless", False)
        self.humanize = self._get_bool_setting("tiktok_api_humanize", True)
        self.human_preset = self._get_str_setting(
            "tiktok_api_human_preset",
            "default",
        )
        self.sleep_after = self._get_int_setting("tiktok_api_sleep_after", 3)
        self.timeout = self._get_int_setting("tiktok_api_timeout_ms", 30000)
        self.page_size = self._get_int_setting("tiktok_api_page_size", 30)
        self.max_pages = self._get_int_setting("max_pages", 0)
        self.reuse_session = self._get_bool_setting("tiktok_api_reuse_session", True)
        self.persistent_profile = self._get_bool_setting(
            "tiktok_api_persistent_profile", True
        )
        self.skip_on_risk = self._get_bool_setting("tiktok_api_skip_on_risk", True)
        self.risk_cooldown_seconds = max(
            self._get_int_setting("tiktok_api_risk_cooldown_seconds", 1800),
            0,
        )
        self.profile_dir = self._resolve_profile_dir()
        self.last_risk_signal: TikTokRiskSignal | None = None
        self.debug_trace_enabled = False
        self.debug_trace_limit = 400
        self.debug_trace_events: list[dict[str, Any]] = []
        self.debug_capture_enabled = self._get_bool_setting(
            "tiktok_api_debug_capture_enabled",
            False,
        )
        self.debug_capture_slider = self._get_bool_setting(
            "tiktok_api_debug_capture_slider",
            False,
        )
        self.debug_capture_dir = self._get_str_setting(
            "tiktok_api_debug_capture_dir",
            "browser_debug",
        )
        self.last_debug_capture: dict[str, Any] | None = None

    @staticmethod
    def _vendor_root() -> Path:
        return REPO_ROOT.joinpath("vendor", "TikTok-Api")

    @classmethod
    def _ensure_import_path(cls) -> None:
        vendor_root = cls._vendor_root()
        if vendor_root.exists():
            vendor_path = str(vendor_root)
            if vendor_path not in sys.path:
                sys.path.insert(0, vendor_path)

    @classmethod
    def _module_within_vendor(cls, module: Any) -> bool:
        vendor_root = cls._vendor_root()
        module_file = getattr(module, "__file__", "")
        if not (vendor_root.exists() and module_file):
            return False
        try:
            return Path(module_file).resolve().is_relative_to(vendor_root.resolve())
        except (OSError, RuntimeError, ValueError):
            return False

    @staticmethod
    def _purge_tiktok_api_modules() -> None:
        for name in list(sys.modules):
            if name == "TikTokApi" or name.startswith("TikTokApi."):
                sys.modules.pop(name, None)

    @staticmethod
    def _module_source(module: Any) -> str:
        module_file = getattr(module, "__file__", "")
        if not module_file:
            return "<unknown>"
        try:
            return str(Path(module_file).resolve())
        except (OSError, RuntimeError, ValueError):
            return str(module_file)

    @classmethod
    def _api_source(cls, api_class: Any) -> str:
        module_name = str(getattr(api_class, "__module__", "")).split(".", 1)[0]
        module = sys.modules.get(module_name)
        return cls._module_source(module) if module else "<unknown>"

    @classmethod
    def _import_tiktok_api_class(cls):
        cls._ensure_import_path()
        existing = sys.modules.get("TikTokApi")
        if existing and not cls._module_within_vendor(existing):
            cls._purge_tiktok_api_modules()
        importlib.invalidate_caches()
        module = importlib.import_module("TikTokApi")
        if cls._vendor_root().exists() and not cls._module_within_vendor(module):
            cls._purge_tiktok_api_modules()
            importlib.invalidate_caches()
            module = importlib.import_module("TikTokApi")
        return module.TikTokApi

    @staticmethod
    def _filter_create_sessions_kwargs(
        api_class: Any,
        session_kwargs: dict[str, Any],
    ) -> tuple[dict[str, Any], list[str]]:
        try:
            signature = inspect.signature(api_class.create_sessions)
        except (TypeError, ValueError):
            return session_kwargs, []
        if any(
            parameter.kind == inspect.Parameter.VAR_KEYWORD
            for parameter in signature.parameters.values()
        ):
            return session_kwargs, []
        allowed = {name for name in signature.parameters if name != "self"}
        filtered = {
            key: value for key, value in session_kwargs.items() if key in allowed
        }
        unsupported = sorted(set(session_kwargs) - set(filtered))
        return filtered, unsupported

    @classmethod
    def available(cls) -> bool:
        try:
            cls._import_tiktok_api_class()
        except (ImportError, ModuleNotFoundError):
            return False
        return True

    def _get_bool_setting(self, name: str, default: bool) -> bool:
        value = getattr(self.params, name, default)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            value = value.strip().lower()
            if value in {"1", "true", "yes", "on"}:
                return True
            if value in {"0", "false", "no", "off"}:
                return False
        return default

    def _get_int_setting(self, name: str, default: int) -> int:
        value = getattr(self.params, name, default)
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _get_str_setting(self, name: str, default: str) -> str:
        value = getattr(self.params, name, default)
        return str(value or default).strip()

    def _resolve_browser_engine(self, value: str) -> str:
        value = (value or "").strip().lower()
        if value in {"cloakbrowser", "playwright"}:
            return value
        if value == "auto":
            return "cloakbrowser" if self.browser == "chromium" else "playwright"
        return "cloakbrowser" if self.browser == "chromium" else "playwright"

    def _resolve_profile_dir(self) -> str | None:
        if not self.persistent_profile:
            return None
        raw_value = self._get_str_setting(
            "tiktok_api_profile_dir",
            str(DEFAULT_PROFILE_DIR),
        )
        path = Path(raw_value).expanduser()
        if not path.is_absolute():
            path = PROJECT_ROOT.joinpath(path)
        path.mkdir(parents=True, exist_ok=True)
        return str(path.resolve())

    def _account_label(
        self,
        unique_id: str = "",
        sec_user_id: str = "",
        url: str = "",
    ) -> str:
        return (
            (sec_user_id or "").strip()
            or self.extract_unique_id(url)
            or (unique_id or "").strip().lstrip("@")
        )

    def _session_risk_key(self) -> str:
        return f"session:{self._shared_signature()}"

    def _account_risk_key(
        self,
        unique_id: str = "",
        sec_user_id: str = "",
        url: str = "",
    ) -> str | None:
        if not (label := self._account_label(unique_id, sec_user_id, url)):
            return None
        return f"{self._session_risk_key()}:account:{label.lower()}"

    def _user_info_cache_keys(
        self,
        unique_id: str = "",
        sec_user_id: str = "",
        url: str = "",
    ) -> list[str]:
        keys: list[str] = []
        if account_key := self._account_risk_key(unique_id, sec_user_id, url):
            keys.append(f"{account_key}:userinfo")
        username = (unique_id or self.extract_unique_id(url)).strip().lstrip("@")
        if username:
            keys.append(
                f"{self._session_risk_key()}:username:{username.lower()}:userinfo"
            )
        if sec_user_id:
            keys.append(f"{self._session_risk_key()}:sec_uid:{sec_user_id}:userinfo")
        seen: set[str] = set()
        return [key for key in keys if not (key in seen or seen.add(key))]

    @classmethod
    def _prune_risk_cooldowns(cls) -> None:
        now = time.time()
        expired = [
            key
            for key, signal in cls._risk_cooldowns.items()
            if not signal.is_active(now)
        ]
        for key in expired:
            cls._risk_cooldowns.pop(key, None)

    def _active_risk_signal(
        self,
        unique_id: str = "",
        sec_user_id: str = "",
        url: str = "",
    ) -> TikTokRiskSignal | None:
        self._prune_risk_cooldowns()
        now = time.time()
        for key in (
            self._account_risk_key(unique_id, sec_user_id, url),
            self._session_risk_key(),
        ):
            if not key:
                continue
            if signal := self._risk_cooldowns.get(key):
                if signal.is_active(now):
                    return signal
                self._risk_cooldowns.pop(key, None)
        return None

    def _remember_user_info(
        self,
        info: dict[str, Any],
        unique_id: str = "",
        sec_user_id: str = "",
        url: str = "",
    ) -> None:
        payload = info.get("userInfo") if "userInfo" in info else info
        if not isinstance(payload, dict) or not payload:
            return
        user = payload.get("user") or {}
        username = str(user.get("uniqueId") or unique_id or "").strip().lstrip("@")
        sec_uid = str(user.get("secUid") or sec_user_id or "").strip()
        for key in self._user_info_cache_keys(username, sec_uid, url):
            self._user_info_cache[key] = payload

    def _cached_user_info(
        self,
        unique_id: str = "",
        sec_user_id: str = "",
        url: str = "",
    ) -> dict[str, Any] | None:
        for key in self._user_info_cache_keys(unique_id, sec_user_id, url):
            if cached := self._user_info_cache.get(key):
                return cached
        return None

    def _clear_account_risk(
        self,
        unique_id: str = "",
        sec_user_id: str = "",
        url: str = "",
    ) -> None:
        if account_key := self._account_risk_key(unique_id, sec_user_id, url):
            self._risk_cooldowns.pop(account_key, None)
        if self.last_risk_signal and self.last_risk_signal.scope == "account":
            self.last_risk_signal = None

    def _risk_storage_keys(
        self,
        signal: TikTokRiskSignal,
        unique_id: str = "",
        sec_user_id: str = "",
        url: str = "",
    ) -> list[str]:
        if signal.scope == "account":
            if account_key := self._account_risk_key(unique_id, sec_user_id, url):
                return [account_key]
            return [self._session_risk_key()]
        return [self._session_risk_key()]

    def _log_risk_signal(self, signal: TikTokRiskSignal) -> None:
        self.log.warning(
            _("TikTok 风控信号: {risk}").format(
                risk=json.dumps(signal.to_dict(), ensure_ascii=False, sort_keys=True)
            )
        )

    def _apply_risk_signal(
        self,
        signal: TikTokRiskSignal | None,
        unique_id: str = "",
        sec_user_id: str = "",
        url: str = "",
    ) -> None:
        if not signal:
            return
        if not signal.username:
            signal.username = (
                (unique_id or self.extract_unique_id(url)).strip().lstrip("@")
            )
        if not signal.sec_user_id:
            signal.sec_user_id = (sec_user_id or "").strip()
        if not signal.url:
            signal.url = (url or "").strip()
        self.last_risk_signal = signal
        self._log_risk_signal(signal)
        if not (self.skip_on_risk and signal.should_pause):
            return
        for key in self._risk_storage_keys(signal, unique_id, sec_user_id, url):
            self._risk_cooldowns[key] = signal

    def should_skip_legacy_fallback(self) -> bool:
        return bool(
            self.skip_on_risk
            and self.last_risk_signal
            and self.last_risk_signal.should_pause
        )

    @staticmethod
    def extract_unique_id(url: str) -> str:
        match = USERNAME_PATTERN.search((url or "").strip())
        return match.group(1) if match else ""

    def _cookie_dict(self) -> dict[str, str]:
        value = self.cookie
        if not value:
            value = self.params.cookie_dict_tiktok or self.params.cookie_str_tiktok
        if isinstance(value, dict):
            return {str(key): str(item) for key, item in value.items() if item}
        return cookie_str_to_dict(str(value))

    def _proxy_list(self) -> list[dict[str, Any]] | None:
        value = self.proxy if self.proxy is not None else self.params.proxy_tiktok
        if not value:
            return None
        if isinstance(value, dict):
            return [value]
        proxy = str(value).strip()
        return [{"server": proxy}] if proxy else None

    def _context_options(self) -> dict[str, Any]:
        info = getattr(self.params, "browser_info_tiktok", {}) or {}
        options: dict[str, Any] = {
            "viewport": DEFAULT_VIEWPORT.copy(),
        }
        if user_agent := info.get("User-Agent"):
            options["user_agent"] = user_agent
        if locale := info.get("browser_language") or info.get("language"):
            options["locale"] = locale
        if timezone := info.get("tz_name"):
            options["timezone_id"] = timezone
        return options

    def _session_params_overrides(self) -> dict[str, Any]:
        info = getattr(self.params, "browser_info_tiktok", {}) or {}
        is_cloakbrowser = self.browser_engine == "cloakbrowser"
        overrides = {
            "app_language": info.get("app_language"),
            "browser_language": info.get("browser_language") or info.get("language"),
            "browser_name": info.get("browser_name"),
            "browser_platform": None
            if is_cloakbrowser
            else info.get("browser_platform"),
            "browser_version": None
            if is_cloakbrowser
            else (info.get("browser_version") or info.get("User-Agent")),
            "language": info.get("language"),
            "os": None if is_cloakbrowser else info.get("os"),
            "priority_region": info.get("priority_region"),
            "region": info.get("region"),
            "tz_name": info.get("tz_name"),
            "webcast_language": info.get("webcast_language"),
            "device_id": info.get("device_id"),
            "screen_width": DEFAULT_VIEWPORT["width"],
            "screen_height": DEFAULT_VIEWPORT["height"],
            "history_len": "3",
        }
        return {
            key: value for key, value in overrides.items() if value not in (None, "")
        }

    @staticmethod
    def _has_display_server() -> bool:
        return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))

    def _resolved_headless(self) -> bool:
        if self.headless:
            return True
        if self.browser != "chromium":
            return self.headless
        if sys.platform.startswith("linux") and not self._has_display_server():
            self.log.warning(
                _("当前环境未检测到 DISPLAY/WAYLAND，TikTokApi 会话将自动改用无头模式")
            )
            return True
        return False

    @classmethod
    def _normalize_detail_url_for_tiktok_api(cls, detail_url: str) -> str:
        raw_url = str(detail_url or "").strip()
        if not raw_url:
            return ""
        if not (match := DETAIL_URL_PATTERN.search(raw_url)):
            return raw_url
        if match.group("kind").lower() == "video":
            return raw_url
        parsed = urlsplit(raw_url)
        prefix = match.group("prefix")
        video_id = match.group("id")
        normalized_path = f"{prefix}video/{video_id}".replace(
            f"{parsed.scheme}://{parsed.netloc}",
            "",
            1,
        )
        return urlunsplit(
            (
                parsed.scheme,
                parsed.netloc,
                normalized_path,
                parsed.query,
                parsed.fragment,
            )
        )

    def _session_kwargs(self, starting_url: str) -> dict[str, Any]:
        cookies = self._cookie_dict()
        resolved_headless = self._resolved_headless()
        override_browser_args = ["--disable-quic"]
        if self.browser_engine == "cloakbrowser":
            override_browser_args.append(
                f"--fingerprint={DEFAULT_CLOAKBROWSER_FINGERPRINT_SEED}"
            )
        kwargs: dict[str, Any] = {
            "num_sessions": 1,
            "headless": resolved_headless,
            "browser": self.browser,
            "browser_engine": self.browser_engine,
            "sleep_after": self.sleep_after,
            "starting_url": starting_url or "https://www.tiktok.com",
            "timeout": self.timeout,
            "humanize": self.humanize,
            "human_preset": self.human_preset,
            "context_options": self._context_options(),
            "session_params_overrides": self._session_params_overrides(),
            "override_browser_args": override_browser_args,
        }
        if self.debug_trace_enabled or self.debug_capture_enabled:
            kwargs["page_factory"] = self._debug_page_factory(starting_url)
        if self.profile_dir:
            kwargs["user_data_dir"] = self.profile_dir
        if cookies:
            kwargs["cookies"] = [cookies]
        elif ms_token := self.params.ms_token_tiktok:
            kwargs["ms_tokens"] = [ms_token]
        if proxies := self._proxy_list():
            kwargs["proxies"] = proxies
        return kwargs

    def enable_debug_trace(self, enabled: bool = True, limit: int = 400) -> None:
        self.debug_trace_enabled = enabled
        self.debug_trace_limit = max(int(limit), 50)
        if enabled:
            self.debug_trace_events = []

    def _append_debug_event(self, kind: str, **payload: Any) -> None:
        if not self.debug_trace_enabled:
            return
        event = {
            "ts": time.time(),
            "kind": kind,
            **payload,
        }
        self.debug_trace_events.append(event)
        overflow = len(self.debug_trace_events) - self.debug_trace_limit
        if overflow > 0:
            del self.debug_trace_events[:overflow]

    def _clip_debug_text(self, value: Any, limit: int = 600) -> str:
        text = str(value or "")
        if len(text) <= limit:
            return text
        return f"{text[:limit]}... [truncated, total {len(text)} chars]"

    def _debug_page_factory(self, starting_url: str):
        async def factory(context):
            page = await context.new_page()

            if self.debug_trace_enabled:
                page.on(
                    "console",
                    lambda message: self._append_debug_event(
                        "console",
                        level=message.type,
                        text=self._clip_debug_text(message.text),
                    ),
                )
                page.on(
                    "pageerror",
                    lambda error: self._append_debug_event(
                        "pageerror",
                        text=self._clip_debug_text(error),
                    ),
                )
                page.on(
                    "request",
                    lambda request: self._append_debug_event(
                        "request",
                        method=request.method,
                        resource_type=request.resource_type,
                        url=request.url,
                    ),
                )
                page.on(
                    "response",
                    lambda response: self._append_debug_event(
                        "response",
                        status=response.status,
                        ok=response.ok,
                        url=response.url,
                    ),
                )
                page.on(
                    "requestfailed",
                    lambda request: self._append_debug_event(
                        "requestfailed",
                        method=request.method,
                        resource_type=request.resource_type,
                        url=request.url,
                        failure=(
                            request.failure.get("errorText", "")
                            if isinstance(request.failure, dict)
                            else str(request.failure or "")
                        ),
                    ),
                )
                page.on(
                    "framenavigated",
                    lambda frame: self._append_debug_event(
                        "framenavigated",
                        url=frame.url,
                        is_main_frame=(frame == page.main_frame),
                    ),
                )

            self._append_debug_event("page_factory", action="new_page")
            await page.goto(starting_url or "https://www.tiktok.com")
            self._append_debug_event("goto", url=page.url)

            try:
                await page.evaluate(
                    """
                    (payload) => {
                        console.log(`[detail-debug] ${payload}`)
                    }
                    """,
                    f"page opened: {page.url}",
                )
            except Exception as error:
                self._append_debug_event("console_inject_error", text=str(error))
            if self.debug_capture_enabled:
                await self._capture_challenge_from_page(
                    page,
                    reason="session_bootstrap",
                    starting_url=starting_url,
                )
            return page

        return factory

    def _session_candidates(
        self, starting_url: str
    ) -> list[tuple[str, dict[str, Any]]]:
        base = self._session_kwargs(starting_url)
        candidates: list[tuple[str, dict[str, Any]]] = []
        seen: set[tuple[Any, ...]] = set()

        def add(label: str, **overrides: Any) -> None:
            candidate = {**base, **overrides}
            key = (
                candidate.get("browser"),
                candidate.get("browser_engine"),
                candidate.get("headless"),
                candidate.get("humanize"),
                candidate.get("human_preset"),
                candidate.get("user_data_dir"),
            )
            if key in seen:
                return
            seen.add(key)
            candidates.append((label, candidate))

        add("configured")
        if not base.get("headless"):
            add("headless-fallback", headless=True)
        if base.get("browser_engine") == "cloakbrowser":
            add("playwright-fallback", browser_engine="playwright")
            if not base.get("headless"):
                add(
                    "playwright-headless-fallback",
                    browser_engine="playwright",
                    headless=True,
                )
        return candidates

    @staticmethod
    def _video_share_url(item: dict[str, Any]) -> str:
        if share_url := str(item.get("share_url") or "").strip():
            return share_url
        unique_id = str(item.get("unique_id") or "").strip().lstrip("@")
        video_id = str(item.get("id") or "").strip()
        if not all((unique_id, video_id)):
            return ""
        return f"https://www.tiktok.com/@{unique_id}/video/{video_id}"

    def _shared_signature(self) -> str:
        payload = {
            "browser": self.browser,
            "browser_engine": self.browser_engine,
            "headless": self.headless,
            "humanize": self.humanize,
            "human_preset": self.human_preset,
            "profile_dir": self.profile_dir,
            "cookies": self._cookie_dict(),
            "proxies": self._proxy_list() or [],
            "session_params": self._session_params_overrides(),
        }
        raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _shared_key(self) -> tuple[int, str]:
        loop = asyncio.get_running_loop()
        return id(loop), self._shared_signature()

    def _param_registry_key(self) -> tuple[int, int]:
        loop = asyncio.get_running_loop()
        return id(loop), id(self.params)

    @classmethod
    def _entry_for_key(cls, key: tuple[int, str]) -> SharedTikTokApiEntry:
        if key not in cls._shared_apis:
            cls._shared_apis[key] = SharedTikTokApiEntry()
        return cls._shared_apis[key]

    @classmethod
    def _register_param_key(
        cls,
        param_key: tuple[int, int],
        shared_key: tuple[int, str],
    ) -> None:
        cls._param_api_keys.setdefault(param_key, set()).add(shared_key)

    @classmethod
    def _unregister_param_key(
        cls,
        param_key: tuple[int, int],
        shared_key: tuple[int, str],
    ) -> None:
        if shared_keys := cls._param_api_keys.get(param_key):
            shared_keys.discard(shared_key)
            if not shared_keys:
                cls._param_api_keys.pop(param_key, None)

    @staticmethod
    def _looks_like_session_error(error: Exception) -> bool:
        text = str(error).lower()
        return any(
            token in text
            for token in (
                "target page, context or browser has been closed",
                "session validation failed",
                "no sessions created",
                "session failed during fetch",
                "playwright error",
                "browser has been closed",
                "context has been closed",
            )
        )

    async def _close_api(self, api: Any | None) -> None:
        if not api:
            return
        try:
            await api.close_sessions()
        except Exception:
            try:
                await api.stop_browser()
            except Exception:
                pass

    async def _create_api(self, starting_url: str):
        TikTokApi = self._import_tiktok_api_class()
        api_source = self._api_source(TikTokApi)

        errors: list[Exception] = []
        for label, session_kwargs in self._session_candidates(starting_url):
            api = TikTokApi()
            try:
                filtered_kwargs, unsupported = self._filter_create_sessions_kwargs(
                    TikTokApi,
                    session_kwargs,
                )
                if unsupported:
                    self.log.warning(
                        _("当前导入的 TikTokApi 来源: {source}").format(
                            source=api_source
                        )
                    )
                    self.log.warning(
                        _(
                            "当前 TikTokApi 版本不支持以下 create_sessions 参数，已自动忽略: {keys}"
                        ).format(keys=", ".join(unsupported))
                    )
                await api.create_sessions(**filtered_kwargs)
                return api
            except Exception as error:
                errors.append(error)
                await self._close_api(api)
                self.log.warning(
                    _("TikTokApi 会话策略 {label} 失败: {error}").format(
                        label=label,
                        error=error,
                    )
                )
        if errors:
            raise errors[-1]
        raise RuntimeError(_("TikTokApi 会话创建失败"))

    async def _api_healthy(self, api: Any | None) -> bool:
        if not api:
            return False
        try:
            health = await api.health_check()
        except Exception:
            return False
        return health.get("healthy_sessions", 0) > 0

    async def _get_or_create_shared_api(self, starting_url: str):
        shared_key = self._shared_key()
        param_key = self._param_registry_key()
        entry = self._entry_for_key(shared_key)
        async with entry.lock:
            if await self._api_healthy(entry.api):
                self._register_param_key(param_key, shared_key)
                return entry.api
            if entry.api:
                await self._close_api(entry.api)
                entry.api = None
            entry.api = await self._create_api(starting_url)
            self._register_param_key(param_key, shared_key)
            return entry.api

    async def _reset_shared_api(self) -> None:
        shared_key = self._shared_key()
        entry = self._shared_apis.get(shared_key)
        if not entry:
            return
        async with entry.lock:
            await self._close_api(entry.api)
            entry.api = None

    async def _run_with_shared_api(self, starting_url: str, callback):
        last_error: Exception | None = None
        for attempt in range(2):
            api = await self._get_or_create_shared_api(starting_url)
            try:
                return await callback(api)
            except Exception as error:
                last_error = error
                await self._capture_runtime_debug_artifacts(
                    api,
                    reason="shared_api_exception",
                    starting_url=starting_url,
                    error=error,
                )
                if attempt == 0 and self._looks_like_session_error(error):
                    await self._reset_shared_api()
                    continue
                raise
        if last_error:
            raise last_error
        raise RuntimeError(_("TikTokApi 共享会话执行失败"))

    async def _run_with_fresh_api(self, starting_url: str, callback):
        api = await self._create_api(starting_url)
        try:
            return await callback(api)
        except Exception as error:
            await self._capture_runtime_debug_artifacts(
                api,
                reason="fresh_api_exception",
                starting_url=starting_url,
                error=error,
            )
            raise
        finally:
            await self._close_api(api)

    async def _run_with_api(self, starting_url: str, callback):
        if self.reuse_session:
            return await self._run_with_shared_api(starting_url, callback)
        return await self._run_with_fresh_api(starting_url, callback)

    async def capture_debug_artifacts(
        self,
        output_dir: Path,
        prefix: str = "tiktok_detail",
    ) -> dict[str, Any]:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        artifact_dir = output_dir / "browser_debug"
        artifact_dir.mkdir(parents=True, exist_ok=True)

        result: dict[str, Any] = {
            "artifact_dir": str(artifact_dir),
            "shared_key": self._shared_signature(),
            "browser": self.browser,
            "browser_engine": self.browser_engine,
            "headless": self._resolved_headless(),
            "reuse_session": self.reuse_session,
            "session_count": 0,
            "trace_count": len(self.debug_trace_events),
            "trace_path": str(artifact_dir / f"{prefix}_trace.json"),
            "captures": [],
        }

        if self.debug_trace_enabled:
            Path(result["trace_path"]).write_text(
                json.dumps(self.debug_trace_events, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        entry = self._shared_apis.get(self._shared_key())
        if not entry or not entry.api:
            result["error"] = "no_active_api_session"
            return result

        async with entry.lock:
            api = entry.api
            sessions = list(getattr(api, "sessions", []) or [])
            result["session_count"] = len(sessions)
            if not sessions:
                result["error"] = "no_browser_sessions"
                return result

            for index, session in enumerate(sessions, start=1):
                capture: dict[str, Any] = {
                    "index": index,
                    "is_valid": bool(getattr(session, "is_valid", False)),
                }
                page = getattr(session, "page", None)
                if not page:
                    capture["error"] = "missing_page"
                    result["captures"].append(capture)
                    continue

                try:
                    capture["url"] = page.url
                except Exception as error:
                    capture["url_error"] = str(error)

                screenshot_path = artifact_dir / f"{prefix}_session_{index}.png"
                html_path = artifact_dir / f"{prefix}_session_{index}.html"

                try:
                    await page.screenshot(path=str(screenshot_path), full_page=True)
                    capture["screenshot_path"] = str(screenshot_path)
                except Exception as error:
                    capture["screenshot_error"] = str(error)

                try:
                    html = await page.content()
                    html_path.write_text(html, encoding="utf-8")
                    capture["html_path"] = str(html_path)
                except Exception as error:
                    capture["html_error"] = str(error)

                result["captures"].append(capture)

        return result

    @staticmethod
    def _artifact_slug(value: str, fallback: str = "capture") -> str:
        slug = re.sub(r"[^0-9A-Za-z._-]+", "_", str(value or "").strip())
        slug = slug.strip("._-")
        return slug[:80] or fallback

    def _debug_artifact_root(self) -> Path:
        settings_obj = getattr(self.params, "settings", None)
        path = getattr(settings_obj, "path", None)
        if path:
            try:
                return Path(path).resolve().parent.joinpath(self.debug_capture_dir)
            except (OSError, RuntimeError, ValueError):
                pass
        return PROJECT_ROOT.joinpath("settings", self.debug_capture_dir)

    def _artifact_event_dir(
        self,
        reason: str,
        starting_url: str = "",
    ) -> Path:
        target = self.extract_unique_id(starting_url) or urlsplit(starting_url).path or ""
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        name = "_".join(
            filter(
                None,
                (
                    stamp,
                    self._artifact_slug(reason, "risk"),
                    self._artifact_slug(target, ""),
                ),
            )
        )
        directory = self._debug_artifact_root().joinpath(name)
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    @staticmethod
    def _page_has_captcha(markers: list[str]) -> bool:
        return any(marker in TikTokAPIBridge.CAPTCHA_STAGE_MARKERS for marker in markers)

    async def _page_debug_context(self, page) -> dict[str, Any]:
        context: dict[str, Any] = {
            "url": "",
            "title": "",
            "content": "",
            "markers": [],
        }
        try:
            context["url"] = page.url or ""
        except Exception:
            pass
        try:
            context["title"] = await page.title()
        except Exception:
            pass
        try:
            context["content"] = await page.content()
        except Exception:
            pass
        context["markers"] = detect_risk_markers(
            context["url"],
            context["title"],
            context["content"],
        )
        return context

    async def _element_box_from_selectors(
        self,
        page,
        selectors: tuple[str, ...],
    ) -> dict[str, Any] | None:
        for selector in selectors:
            try:
                locator = page.locator(selector).first
                count = await locator.count()
                if count < 1:
                    continue
                box = await locator.bounding_box()
                if not box:
                    continue
                width = float(box.get("width") or 0)
                height = float(box.get("height") or 0)
                if width < 12 or height < 12:
                    continue
                return {
                    "selector": selector,
                    "x": float(box["x"]),
                    "y": float(box["y"]),
                    "width": width,
                    "height": height,
                }
            except Exception:
                continue
        return None

    async def _slider_boxes(self, page) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        handle = await self._element_box_from_selectors(page, self.SLIDER_HANDLE_SELECTORS)
        track = await self._element_box_from_selectors(page, self.SLIDER_TRACK_SELECTORS)
        return handle, track

    async def _capture_slider_probe(
        self,
        page,
        artifact_dir: Path,
        base_name: str,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "enabled": self.debug_capture_slider,
        }
        if not self.debug_capture_slider:
            return result
        handle, track = await self._slider_boxes(page)
        if not handle:
            result["error"] = "slider_handle_not_found"
            return result
        start_x = handle["x"] + handle["width"] / 2
        start_y = handle["y"] + handle["height"] / 2
        track_width = float(track["width"]) if track else 0
        max_distance = max(track_width - handle["width"] - 8, 0) if track else 0
        distance = max_distance * 0.35 if max_distance > 0 else 140
        distance = max(40, min(distance, 220))
        drag_path = artifact_dir.joinpath(f"{base_name}_slider_dragging.png")
        released_path = artifact_dir.joinpath(f"{base_name}_slider_released.png")
        result["handle"] = handle
        if track:
            result["track"] = track
        try:
            await page.mouse.move(start_x, start_y)
            await asyncio.sleep(0.2)
            await page.mouse.down()
            await asyncio.sleep(0.1)
            await page.mouse.move(start_x + distance, start_y, steps=18)
            await asyncio.sleep(0.2)
            await page.screenshot(path=str(drag_path), full_page=True)
            result["dragging_path"] = str(drag_path)
        except Exception as error:
            result["error"] = str(error)
        finally:
            try:
                await page.mouse.up()
                await asyncio.sleep(0.1)
                await page.screenshot(path=str(released_path), full_page=True)
                result["released_path"] = str(released_path)
            except Exception as error:
                result["release_error"] = str(error)
        return result

    async def _capture_challenge_from_page(
        self,
        page,
        *,
        reason: str,
        starting_url: str = "",
        error: Exception | None = None,
        session_index: int = 1,
        force: bool = False,
    ) -> dict[str, Any] | None:
        if not self.debug_capture_enabled:
            return None
        context = await self._page_debug_context(page)
        challenge_detected = self._page_has_captcha(context["markers"])
        if not (force or challenge_detected):
            return None
        artifact_dir = self._artifact_event_dir(reason, starting_url or context["url"])
        base_name = f"session_{session_index}"
        result: dict[str, Any] = {
            "reason": reason,
            "artifact_dir": str(artifact_dir),
            "session_index": session_index,
            "starting_url": starting_url,
            "page_url": context["url"],
            "page_title": context["title"],
            "markers": context["markers"],
            "challenge_detected": challenge_detected,
            "error": str(error) if error else "",
        }
        initial_path = artifact_dir.joinpath(f"{base_name}_captcha_initial.png")
        html_path = artifact_dir.joinpath(f"{base_name}_captcha_initial.html")
        metadata_path = artifact_dir.joinpath(f"{base_name}_metadata.json")
        try:
            await page.screenshot(path=str(initial_path), full_page=True)
            result["initial_path"] = str(initial_path)
        except Exception as capture_error:
            result["initial_error"] = str(capture_error)
        try:
            html_path.write_text(context["content"], encoding="utf-8")
            result["html_path"] = str(html_path)
        except Exception as html_error:
            result["html_error"] = str(html_error)
        if challenge_detected:
            slider = await self._capture_slider_probe(page, artifact_dir, base_name)
            if slider:
                result["slider_probe"] = slider
        try:
            metadata_path.write_text(
                json.dumps(result, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            result["metadata_path"] = str(metadata_path)
        except Exception:
            pass
        self.last_debug_capture = result
        self.log.warning(
            _("TikTok 调试截图已保存: {path}").format(
                path=result.get("artifact_dir")
            )
        )
        return result

    async def _capture_runtime_debug_artifacts(
        self,
        api: Any | None,
        *,
        reason: str,
        starting_url: str = "",
        error: Exception | None = None,
    ) -> dict[str, Any] | None:
        if not (self.debug_capture_enabled and api):
            return None
        sessions = list(getattr(api, "sessions", []) or [])
        captures: list[dict[str, Any]] = []
        for index, session in enumerate(sessions, start=1):
            page = getattr(session, "page", None)
            if not page:
                continue
            if capture := await self._capture_challenge_from_page(
                page,
                reason=reason,
                starting_url=starting_url,
                error=error,
                session_index=index,
                force=True,
            ):
                captures.append(capture)
        if not captures:
            return None
        result = {
            "reason": reason,
            "starting_url": starting_url,
            "captures": captures,
        }
        self.last_debug_capture = result
        return result

    async def close(self) -> None:
        param_key = self._param_registry_key()
        shared_keys = list(self._param_api_keys.get(param_key, set()))
        for shared_key in shared_keys:
            entry = self._shared_apis.get(shared_key)
            if not entry:
                self._unregister_param_key(param_key, shared_key)
                continue
            async with entry.lock:
                await self._close_api(entry.api)
                entry.api = None
            self._shared_apis.pop(shared_key, None)
            self._unregister_param_key(param_key, shared_key)

    @classmethod
    async def close_for_params(cls, params: "Parameter") -> None:
        if not cls.available():
            return
        await cls(params).close()

    async def get_user_info(
        self,
        unique_id: str = "",
        sec_user_id: str = "",
        url: str = "",
    ) -> dict:
        username = (unique_id or self.extract_unique_id(url)).strip().lstrip("@")
        if not (username or sec_user_id):
            return {}
        target_url = url or (
            f"https://www.tiktok.com/@{username}"
            if username
            else "https://www.tiktok.com"
        )
        self.last_risk_signal = None
        if active_signal := self._active_risk_signal(username, sec_user_id, url):
            self.last_risk_signal = active_signal
            self.log.warning(
                _("TikTok 风控冷却中，跳过账号信息请求: {target}").format(
                    target=username or sec_user_id or url
                )
            )
            return {}

        async def _callback(api):
            user = api.user(username=username or None, sec_uid=sec_user_id or None)
            return await user.info()

        original_reuse_session = self.reuse_session
        self.reuse_session = False
        try:
            response = await self._run_with_api(
                target_url,
                _callback,
            )
        except Exception as error:
            self._apply_risk_signal(
                classify_exception(
                    error,
                    source="get_user_info",
                    cooldown_seconds=self.risk_cooldown_seconds,
                    username=username,
                    sec_user_id=sec_user_id,
                    url=target_url,
                    endpoint="user_detail",
                ),
                username,
                sec_user_id,
                url,
            )
            self.log.warning(
                _("TikTokApi 获取账号信息失败: {error}").format(error=error)
            )
            return {}
        finally:
            self.reuse_session = original_reuse_session
        self._apply_risk_signal(
            classify_api_payload(
                response,
                endpoint="user_detail",
                source="get_user_info",
                cooldown_seconds=self.risk_cooldown_seconds,
                username=username,
                sec_user_id=sec_user_id,
                url=target_url,
            ),
            username,
            sec_user_id,
            url,
        )
        if self.should_skip_legacy_fallback():
            return {}
        info = response.get("userInfo") or {}
        if info:
            self._remember_user_info(info, username, sec_user_id, url)
            self._clear_account_risk(username, sec_user_id, url)
            self.last_risk_signal = None
        return info

    async def get_account_items(
        self,
        sec_user_id: str,
        tab: str = "post",
        pages: int | None = None,
        cursor: int = 0,
        url: str = "",
    ) -> tuple[list[dict], str, str]:
        if not sec_user_id:
            return [], "", ""
        self.last_risk_signal = None
        if active_signal := self._active_risk_signal(sec_user_id=sec_user_id, url=url):
            self.last_risk_signal = active_signal
            self.log.warning(
                _("TikTok 风控冷却中，跳过账号作品请求: {target}").format(
                    target=sec_user_id or url
                )
            )
            return [], "", ""

        tab = (tab or "post").strip().lower()
        endpoint = {
            "post": "https://www.tiktok.com/api/post/item_list/",
            "favorite": "https://www.tiktok.com/api/favorite/item_list",
        }.get(tab)
        if not endpoint:
            self.log.warning(_("TikTokApi 暂不支持该账号标签: {tab}").format(tab=tab))
            return [], "", ""

        page_limit = self._get_int_setting("max_pages", 0)
        if isinstance(pages, int) and pages > 0:
            page_limit = pages

        async def _callback(api):
            items: list[dict] = []
            next_cursor = cursor
            page_count = 0
            first_response: dict[str, Any] | None = None
            while True:
                if page_limit > 0 and page_count >= page_limit:
                    break
                page_count += 1
                response = await api.make_request(
                    url=endpoint,
                    params={
                        "secUid": sec_user_id,
                        "count": self.page_size,
                        "cursor": next_cursor,
                    },
                )
                if first_response is None and isinstance(response, dict):
                    first_response = response
                if not isinstance(response, dict):
                    break
                page_items = response.get("itemList") or []
                items.extend(page_items)
                if not response.get("hasMore", False):
                    break
                candidate_cursor = response.get("cursor")
                if candidate_cursor in (None, "", next_cursor):
                    break
                next_cursor = candidate_cursor
            return items, first_response

        original_reuse_session = self.reuse_session
        self.reuse_session = False
        try:
            items, first_response = await self._run_with_api(
                url or "https://www.tiktok.com",
                _callback,
            )
        except Exception as error:
            self._apply_risk_signal(
                classify_exception(
                    error,
                    source="get_account_items",
                    cooldown_seconds=self.risk_cooldown_seconds,
                    sec_user_id=sec_user_id,
                    url=url or "https://www.tiktok.com",
                    endpoint=f"{tab}_item_list",
                ),
                sec_user_id=sec_user_id,
                url=url,
            )
            self.log.warning(
                _("TikTokApi 获取账号作品失败: {error}").format(error=error)
            )
            return [], "", ""
        finally:
            self.reuse_session = original_reuse_session
        if first_response:
            self._apply_risk_signal(
                classify_api_payload(
                    first_response,
                    endpoint=f"{tab}_item_list",
                    source="get_account_items",
                    cooldown_seconds=self.risk_cooldown_seconds,
                    sec_user_id=sec_user_id,
                    url=url or "https://www.tiktok.com",
                    cached_user_info=self._cached_user_info(
                        sec_user_id=sec_user_id,
                        url=url,
                    ),
                ),
                sec_user_id=sec_user_id,
                url=url,
            )
            if self.should_skip_legacy_fallback():
                return [], "", ""
        if items:
            self._clear_account_risk(sec_user_id=sec_user_id, url=url)
            self.last_risk_signal = None
        return items, "", ""

    async def get_video_detail(
        self,
        detail_url: str = "",
        detail_id: str = "",
    ) -> dict[str, Any]:
        detail_url = self._normalize_detail_url_for_tiktok_api(detail_url)
        detail_id = str(detail_id or "").strip()
        if not detail_url:
            return {}
        self.last_risk_signal = None
        if active_signal := self._active_risk_signal(url=detail_url):
            self.last_risk_signal = active_signal
            self.log.warning(
                _("TikTok 风控冷却中，跳过作品详情请求: {target}").format(
                    target=detail_url or detail_id
                )
            )
            return {}

        async def _callback(api):
            video = api.video(url=detail_url)
            return await video.info()

        try:
            data = await self._run_with_api(detail_url, _callback)
        except Exception as error:
            self._apply_risk_signal(
                classify_exception(
                    error,
                    source="get_video_detail",
                    cooldown_seconds=self.risk_cooldown_seconds,
                    url=detail_url,
                    endpoint="video_detail",
                ),
                url=detail_url,
            )
            self.log.warning(
                _("TikTokApi 获取作品详情失败: {error}").format(error=error)
            )
            return {}
        if isinstance(data, dict) and data.get("id"):
            self.last_risk_signal = None
            return data
        self.log.warning(
            _("TikTokApi 获取作品详情结果为空: {url}").format(url=detail_url)
        )
        return {}

    async def download_video(
        self,
        item: dict[str, Any],
        temp: Path,
        show: str,
        progress,
    ) -> bool:
        """Download TikTok video through TikTokApi using no-watermark media only."""
        share_url = self._video_share_url(item)
        if not share_url:
            self.log.warning(_("TikTokApi 视频下载缺少 share_url 或 unique_id"))
            return False
        self.last_risk_signal = None
        if active_signal := self._active_risk_signal(
            unique_id=str(item.get("unique_id") or ""),
            url=share_url,
        ):
            self.last_risk_signal = active_signal
            self.log.warning(
                _("TikTok 风控冷却中，跳过 TikTokApi 视频回退下载: {url}").format(
                    url=share_url
                )
            )
            return False

        async def _callback(api):
            video = api.video(url=share_url)
            await video.info()
            stream = await video.bytes(stream=True)
            task_id = progress.add_task(show, total=None, completed=0)
            try:
                async with aio_open(temp, "wb") as file:
                    async for chunk in stream:
                        await file.write(chunk)
                        progress.update(task_id, advance=len(chunk))
                progress.remove_task(task_id)
                return True
            except Exception:
                progress.remove_task(task_id)
                raise

        try:
            temp.parent.mkdir(parents=True, exist_ok=True)
            return await self._run_with_api(share_url, _callback)
        except Exception as error:
            self._apply_risk_signal(
                classify_exception(
                    error,
                    source="download",
                    cooldown_seconds=self.risk_cooldown_seconds,
                    username=str(item.get("unique_id") or ""),
                    url=share_url,
                    endpoint="video_download",
                ),
                unique_id=str(item.get("unique_id") or ""),
                url=share_url,
            )
            self.log.warning(
                _("TikTokApi 会话下载视频失败: {error}").format(error=error)
            )
            return False
