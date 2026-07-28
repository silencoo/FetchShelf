"""Security helpers shared by the Web UI and API surfaces.

The helpers in this module deliberately have no FastAPI dependencies so they
can also be used by configuration and background-task serializers.
"""

from __future__ import annotations

from copy import deepcopy
from hmac import compare_digest
from ipaddress import ip_address
from json import JSONDecodeError, dumps, loads
from os import environ
from pathlib import Path
from re import IGNORECASE, compile as compile_pattern
from typing import Any
from urllib.parse import unquote_plus

REDACTED_VALUE = "[REDACTED]"
WEBUI_TOKEN_ENV_NAMES = ("DOUK_API_TOKEN", "DOUK_WEBUI_TOKEN")

WEBUI_SENSITIVE_FIELDS = frozenset(
    {
        "api_key",
        "api_token",
        "authorization",
        "bark_url",
        "client_secret",
        "cookie",
        "cookies",
        "device_id",
        "mstoken",
        "ms_token",
        "odin_tt",
        "password",
        "passport_csrf_token",
        "proxy",
        "proxy_tiktok",
        "refresh_token",
        "secret",
        "sessionid",
        "sessionid_ss",
        "sid_tt",
        "token",
        "ttwid",
        "uid_tt",
        "uptime_kuma_url",
        "user_agent",
        "webid",
        "web_id",
        "uifid",
        "ui_fid",
        # Request signatures and browser-verification fingerprints are short
        # lived, but exposing them still makes replay and identity correlation
        # easier. Treat their common spellings as write-only material.
        "_signature",
        "a_bogus",
        "signature",
        "verify_fp",
        "verifyfp",
        "x_bogus",
        "x_gnarly",
        "x_tt_params",
    }
)

_PROTECTED_PROJECT_COMPONENTS = frozenset(
    {
        ".env",
        ".keys",
        ".secrets",
        "backup",
        "backups",
        "browser_debug",
        "browser_debug_capture",
        "browser_profile",
        "browser_profiles",
        "cache",
        "collector",
        "collector_data",
        "collectors",
        "encipher.py",
        "identities.json",
        "identity_runtime.sqlite3",
        "ui_task_runtime.sqlite3",
        "keys",
        "profiles",
        "secrets",
        "settings.json",
        "tiktok_debug",
        "tiktok_debug_capture",
        "tiktok_api_profile",
        "tiktok_api_profiles",
        "webui_token",
    }
)

_URL_CREDENTIALS_PATTERN = compile_pattern(
    r"([a-z][a-z0-9+.-]*://)([^/@\s]+)@",
    IGNORECASE,
)
_BARE_PROXY_CREDENTIALS_PATTERN = compile_pattern(
    r"(?<![\w/@])[a-z0-9._~%+-]+:[^@\s/(),]+@"
    r"((?:\[[0-9a-f:.]+\]|[a-z0-9.-]+)(?::\d{1,5})?)",
    IGNORECASE,
)
_TEXT_URL_PATTERN = compile_pattern(
    r"\b[a-z][a-z0-9+.-]*://[^\s<>\"']+",
    IGNORECASE,
)
_QUERY_SEPARATOR_PATTERN = compile_pattern(r"([&;])")
_QUOTED_HEADER_SECRET_PATTERN = compile_pattern(
    r"(?<![?&;])\b(cookie|authorization|user[-_ ]agent)\b"
    r"([\"']?\s*[:=]\s*)([\"'])(.*?)\3",
    IGNORECASE,
)
_HEADER_SECRET_PATTERN = compile_pattern(
    r"(?<![?&;])\b(cookie|authorization|user[-_ ]agent)\b"
    r"([\"']?\s*[:=])(?!(?:\s*)[\"'])(\s*)[^\r\n]+",
    IGNORECASE,
)
_LABELED_SECRET_PATTERN = compile_pattern(
    r"\b(proxy|token|password|secret|bark_url|uptime_kuma_url|device[-_]id|"
    r"web[-_]?id|ui[-_]?fid|ms[-_]?token|a[-_]bogus|x[-_]bogus|x[-_]gnarly|"
    r"_signature|signature|verify[-_]?fp|ttwid)"
    r"\b([\"']?\s*[:=]\s*[\"']?)([^\s,;&\"'}#]+)",
    IGNORECASE,
)
_COMMON_COOKIE_PATTERN = compile_pattern(
    r"\b(sessionid(?:_ss)?|sid_tt|uid_tt|passport_csrf_token|odin_tt|msToken)="
    r"[^;&\s,#]+",
    IGNORECASE,
)
_BARK_URL_PATTERN = compile_pattern(
    r"(https?://api\.day\.app/)[^\s?#/]+",
    IGNORECASE,
)
_UPTIME_PUSH_PATTERN = compile_pattern(
    r"(https?://[^\s?#]+/api/push/)[^\s?#/]+",
    IGNORECASE,
)


def configured_webui_token() -> str:
    """Return the configured API token without inventing an insecure default."""
    for name in WEBUI_TOKEN_ENV_NAMES:
        if value := environ.get(name, "").strip():
            return value
    return ""


def is_loopback_client(host: str | None) -> bool:
    """Return whether an ASGI peer address is an actual loopback address."""
    value = str(host or "").strip().lower()
    if value == "localhost":
        return True
    if not value:
        return False
    # IPv6 peer strings can include a zone identifier.
    value = value.split("%", 1)[0]
    try:
        return ip_address(value).is_loopback
    except ValueError:
        return False


def validate_webui_token(token: str | None, client_host: str | None = None) -> bool:
    """Validate a configured token, or allow tokenless loopback development.

    When ``DOUK_API_TOKEN`` (or the compatibility alias
    ``DOUK_WEBUI_TOKEN``) is configured, every client must provide an exact
    token match. Without a configured token, only a loopback ASGI peer is
    accepted; Docker bridge, LAN and Internet peers fail closed.
    """
    expected = configured_webui_token()
    if not expected:
        return is_loopback_client(client_host)
    supplied = str(token or "")
    return compare_digest(supplied.encode("utf-8"), expected.encode("utf-8"))


def _normalized_key(key: str) -> str:
    return str(key).strip().lower().replace("-", "_").replace(" ", "_")


def is_sensitive_webui_key(key: str) -> bool:
    normalized = _normalized_key(key)
    return (
        normalized in WEBUI_SENSITIVE_FIELDS
        or normalized.startswith(("cookie_", "proxy_"))
        or normalized.endswith(
            (
                "_bark_url",
                "_cookie",
                "_password",
                "_proxy",
                "_secret",
                "_token",
                "_uptime_kuma_url",
            )
        )
    )


def _split_url_suffix(value: str) -> tuple[str, str]:
    """Separate sentence punctuation from a URL without rewriting the URL."""
    url = value
    suffix = ""
    while url and url[-1] in ".,;:!?":
        suffix = url[-1] + suffix
        url = url[:-1]
    pairs = {")": "(", "]": "[", "}": "{"}
    while url and url[-1] in pairs:
        closing = url[-1]
        if url.count(closing) <= url.count(pairs[closing]):
            break
        suffix = closing + suffix
        url = url[:-1]
    return url, suffix


def _redact_url_query(match) -> str:
    """Redact sensitive URL query values while preserving all other text."""
    original = match.group(0)
    url, suffix = _split_url_suffix(original)
    prefix, separator, remainder = url.partition("?")
    if not separator:
        return original
    query, fragment_separator, fragment = remainder.partition("#")
    parts = _QUERY_SEPARATOR_PATTERN.split(query)
    changed = False
    for index in range(0, len(parts), 2):
        component = parts[index]
        raw_key, value_separator, raw_value = component.partition("=")
        if not value_separator or not raw_value:
            continue
        try:
            key = unquote_plus(raw_key)
        except (UnicodeDecodeError, ValueError):
            key = raw_key
        if not is_sensitive_webui_key(key):
            continue
        parts[index] = f"{raw_key}={REDACTED_VALUE}"
        changed = True
    if not changed:
        return original
    redacted = f"{prefix}?{''.join(parts)}"
    if fragment_separator:
        redacted = f"{redacted}#{fragment}"
    return redacted + suffix


def _redact_quoted_header(match) -> str:
    quote = match.group(3)
    return f"{match.group(1)}{match.group(2)}{quote}{REDACTED_VALUE}{quote}"


def redact_webui_text(value: str) -> str:
    """Best-effort sanitization for credentials embedded in error/log text."""
    # Only URLs containing sensitive query keys are reconstructed. Ordinary
    # URLs and the surrounding log message remain byte-for-byte unchanged.
    text = _TEXT_URL_PATTERN.sub(_redact_url_query, value)
    text = _URL_CREDENTIALS_PATTERN.sub(r"\1[REDACTED]@", text)
    text = _BARE_PROXY_CREDENTIALS_PATTERN.sub(r"[REDACTED]@\1", text)
    text = _QUOTED_HEADER_SECRET_PATTERN.sub(_redact_quoted_header, text)
    text = _HEADER_SECRET_PATTERN.sub(r"\1\2\3[REDACTED]", text)
    text = _LABELED_SECRET_PATTERN.sub(r"\1\2[REDACTED]", text)
    text = _COMMON_COOKIE_PATTERN.sub(r"\1=[REDACTED]", text)
    text = _BARK_URL_PATTERN.sub(r"\1[REDACTED]", text)
    return _UPTIME_PUSH_PATTERN.sub(r"\1[REDACTED]", text)


def redact_webui_value(value: Any, key: str = "") -> Any:
    """Recursively redact credentials before a value crosses the API boundary."""
    if is_sensitive_webui_key(key):
        return REDACTED_VALUE if value is not None and value != "" else value
    if isinstance(value, dict):
        return {
            item_key: redact_webui_value(item_value, item_key)
            for item_key, item_value in value.items()
        }
    if isinstance(value, list):
        return [redact_webui_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_webui_value(item) for item in value)
    if isinstance(value, str):
        return redact_webui_text(value)
    return value


def redact_webui_json_text(text: str) -> str:
    """Return a JSON document with the same structure and redacted secrets."""
    try:
        value = loads(text)
    except (JSONDecodeError, TypeError):
        # Never fall back to returning an unparsed settings document because it
        # may still contain credentials.
        return "{}"
    return dumps(redact_webui_value(value), indent=4, ensure_ascii=False)


def restore_redacted_values(value: Any, current: Any) -> Any:
    """Treat the public redaction sentinel as write-only "keep existing".

    Empty strings remain empty and can therefore be used by a dedicated clear
    action. Only the exact sentinel has preservation semantics.
    """
    if value == REDACTED_VALUE:
        return deepcopy(current)
    if isinstance(value, dict):
        source = current if isinstance(current, dict) else {}
        return {
            key: restore_redacted_values(item, source.get(key))
            for key, item in value.items()
        }
    if isinstance(value, list):
        source = current if isinstance(current, list) else []
        return [
            restore_redacted_values(item, source[index] if index < len(source) else None)
            for index, item in enumerate(value)
        ]
    return deepcopy(value)


def _looks_like_protected_project_component(component: str) -> bool:
    name = component.strip().lower()
    if name in _PROTECTED_PROJECT_COMPONENTS:
        return True
    if "debug" in name and any(
        marker in name for marker in ("browser", "capture", "tiktok")
    ):
        return True
    if name.startswith(("collector_", "collector-", "identity-secret")):
        return True
    if name.startswith("ui_task_runtime.sqlite3"):
        return True
    if any(marker in name for marker in ("cookie", "secret", "token")):
        return True
    if name in {"key", "master_key"} or name.endswith(
        (".key", "-key", "_key", ".pem", ".p12", ".pfx")
    ):
        return True
    return False


def is_protected_project_path(root: Path, target: Path) -> bool:
    """Protect configuration, credentials, profiles and collector state.

    The current ``project`` file scope points at ``/app/settings`` in Docker,
    so path containment alone is not a sufficient authorization boundary.
    """
    root_path = root.expanduser().resolve()
    target_path = target.expanduser().resolve()
    try:
        relative = target_path.relative_to(root_path)
    except ValueError:
        return True
    return any(_looks_like_protected_project_component(part) for part in relative.parts)
