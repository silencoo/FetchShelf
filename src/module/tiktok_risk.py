import json
from dataclasses import dataclass, field
from time import time
from typing import Any

CAPTCHA_MARKERS = (
    "captcha",
    "verify",
    "verification",
    "challenge",
    "slider",
    "robot",
    "security check",
    "unusual traffic",
    "complete the security check",
    "请完成验证",
    "安全验证",
    "拖动滑块",
    "验证你是真人",
    "验证以继续",
)

RATE_LIMIT_MARKERS = (
    "too many requests",
    "rate limit",
    "slow down",
    "temporarily unavailable",
    "request too frequently",
    "请求过于频繁",
    "访问过于频繁",
    "操作过于频繁",
)

SESSION_MARKERS = (
    "session expired",
    "login expired",
    "log in",
    "login required",
    "not logged in",
    "please login",
    "请先登录",
    "登录已过期",
    "登录后继续",
)

BLOCK_MARKERS = (
    "access denied",
    "forbidden",
    "denied",
    "blocked",
    "suspended",
    "restricted",
    "受限",
    "封禁",
    "限制访问",
)

HTML_MARKERS = (
    "<!doctype html",
    "<html",
    "<body",
    "<head",
    "</html>",
)


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _clip_text(value: Any, limit: int = 800) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return f"{text[:limit]}\n... [truncated, total {len(text)} chars]"


def _looks_like_html(text: str) -> bool:
    text = (text or "").strip().lower()
    return any(marker in text for marker in HTML_MARKERS)


def detect_risk_markers(*parts: Any) -> list[str]:
    text = " ".join(str(part or "") for part in parts).lower()
    found: list[str] = []
    for marker_group in (
        CAPTCHA_MARKERS,
        RATE_LIMIT_MARKERS,
        SESSION_MARKERS,
        BLOCK_MARKERS,
    ):
        for marker in marker_group:
            if marker in text and marker not in found:
                found.append(marker)
    return found


def _category_from_markers(markers: list[str]) -> str:
    if any(marker in CAPTCHA_MARKERS for marker in markers):
        return "captcha_required"
    if any(marker in SESSION_MARKERS for marker in markers):
        return "session_invalid"
    if any(marker in RATE_LIMIT_MARKERS for marker in markers):
        return "rate_limited_or_blocked"
    if any(marker in BLOCK_MARKERS for marker in markers):
        return "rate_limited_or_blocked"
    return "unknown_risk"


def _reason_from_category(category: str) -> str:
    return {
        "captcha_required": "检测到 TikTok 验证码或挑战页特征",
        "session_invalid": "检测到登录失效或会话不可用特征",
        "rate_limited_or_blocked": "检测到访问频率限制或封禁特征",
        "empty_response_risk": "TikTok 返回空响应，通常表示当前请求被静默拦截或命中风控",
        "invalid_json_response": "TikTok 返回了非 JSON 响应，可能是风控页、验证码页或异常中间页",
        "api_status_error": "TikTok API 返回了异常状态码",
        "account_items_unavailable": "账号资料显示存在作品，但作品列表为空，疑似账号维度受限",
        "user_info_missing": "账号详情接口未返回 userInfo",
        "session_unstable": "浏览器会话或网络状态不稳定",
        "access_forbidden": "TikTok 返回 403 Forbidden",
        "unknown_risk": "检测到未知风险信号",
    }.get(category, "检测到 TikTok 风控或异常信号")


@dataclass
class TikTokRiskSignal:
    category: str
    reason: str
    severity: str = "medium"
    scope: str = "session"
    source: str = "tiktok_api"
    retryable: bool = False
    should_pause: bool = True
    cooldown_seconds: int = 0
    detected_at: float = field(default_factory=time)
    cooldown_until: float = 0.0
    username: str = ""
    sec_user_id: str = ""
    url: str = ""
    endpoint: str = ""
    status_code: int | None = None
    exception_type: str = ""
    markers: list[str] = field(default_factory=list)
    raw_excerpt: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def activate_cooldown(self) -> "TikTokRiskSignal":
        if self.cooldown_seconds > 0:
            self.cooldown_until = self.detected_at + self.cooldown_seconds
        return self

    def is_active(self, now: float | None = None) -> bool:
        if not self.should_pause or self.cooldown_until <= 0:
            return False
        return (now or time()) < self.cooldown_until

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "reason": self.reason,
            "severity": self.severity,
            "scope": self.scope,
            "source": self.source,
            "retryable": self.retryable,
            "should_pause": self.should_pause,
            "cooldown_seconds": self.cooldown_seconds,
            "detected_at": self.detected_at,
            "cooldown_until": self.cooldown_until,
            "username": self.username,
            "sec_user_id": self.sec_user_id,
            "url": self.url,
            "endpoint": self.endpoint,
            "status_code": self.status_code,
            "exception_type": self.exception_type,
            "markers": self.markers,
            "raw_excerpt": self.raw_excerpt,
            "extra": self.extra,
        }


def build_risk_signal(
    category: str,
    *,
    reason: str | None = None,
    severity: str = "medium",
    scope: str = "session",
    source: str = "tiktok_api",
    retryable: bool = False,
    should_pause: bool = True,
    cooldown_seconds: int = 0,
    username: str = "",
    sec_user_id: str = "",
    url: str = "",
    endpoint: str = "",
    status_code: int | None = None,
    exception_type: str = "",
    markers: list[str] | None = None,
    raw_excerpt: str = "",
    extra: dict[str, Any] | None = None,
) -> TikTokRiskSignal:
    signal = TikTokRiskSignal(
        category=category,
        reason=reason or _reason_from_category(category),
        severity=severity,
        scope=scope,
        source=source,
        retryable=retryable,
        should_pause=should_pause,
        cooldown_seconds=max(_to_int(cooldown_seconds), 0),
        username=(username or "").strip().lstrip("@"),
        sec_user_id=(sec_user_id or "").strip(),
        url=(url or "").strip(),
        endpoint=endpoint,
        status_code=status_code,
        exception_type=exception_type,
        markers=list(markers or []),
        raw_excerpt=_clip_text(raw_excerpt),
        extra=extra or {},
    )
    if signal.should_pause:
        signal.activate_cooldown()
    return signal


def classify_exception(
    error: Exception,
    *,
    source: str,
    cooldown_seconds: int,
    username: str = "",
    sec_user_id: str = "",
    url: str = "",
    endpoint: str = "",
) -> TikTokRiskSignal | None:
    error_type = type(error).__name__
    message = str(getattr(error, "message", "") or error)
    raw_response = getattr(error, "raw_response", "") or ""
    status_code = getattr(error, "error_code", None)
    if status_code is None:
        status_code = getattr(getattr(error, "response", None), "status_code", None)
    raw_excerpt = _clip_text(raw_response or message)
    markers = detect_risk_markers(message, raw_response, url)
    marker_category = _category_from_markers(markers) if markers else ""
    scope = "account" if source == "download" else "session"

    if error_type == "CaptchaException" or marker_category == "captcha_required":
        return build_risk_signal(
            "captcha_required",
            severity="critical",
            scope="session",
            source=source,
            retryable=False,
            should_pause=True,
            cooldown_seconds=cooldown_seconds,
            username=username,
            sec_user_id=sec_user_id,
            url=url,
            endpoint=endpoint,
            status_code=status_code,
            exception_type=error_type,
            markers=markers,
            raw_excerpt=raw_excerpt,
        )

    if error_type == "EmptyResponseException":
        return build_risk_signal(
            "empty_response_risk",
            severity="high",
            scope="session",
            source=source,
            retryable=True,
            should_pause=True,
            cooldown_seconds=cooldown_seconds,
            username=username,
            sec_user_id=sec_user_id,
            url=url,
            endpoint=endpoint,
            status_code=status_code,
            exception_type=error_type,
            markers=markers,
            raw_excerpt=raw_excerpt,
        )

    if error_type == "InvalidJSONException":
        return build_risk_signal(
            marker_category or "invalid_json_response",
            severity="high",
            scope="session",
            source=source,
            retryable=True,
            should_pause=True,
            cooldown_seconds=cooldown_seconds,
            username=username,
            sec_user_id=sec_user_id,
            url=url,
            endpoint=endpoint,
            status_code=status_code,
            exception_type=error_type,
            markers=markers,
            raw_excerpt=raw_excerpt,
        )

    if marker_category in {"session_invalid", "rate_limited_or_blocked"}:
        return build_risk_signal(
            marker_category,
            severity="high",
            scope="session",
            source=source,
            retryable=True,
            should_pause=True,
            cooldown_seconds=cooldown_seconds,
            username=username,
            sec_user_id=sec_user_id,
            url=url,
            endpoint=endpoint,
            status_code=status_code,
            exception_type=error_type,
            markers=markers,
            raw_excerpt=raw_excerpt,
        )

    lowered = message.lower()
    if status_code == 403:
        return build_risk_signal(
            "access_forbidden",
            severity="medium",
            scope=scope,
            source=source,
            retryable=True,
            should_pause=(source != "download"),
            cooldown_seconds=cooldown_seconds if source != "download" else 0,
            username=username,
            sec_user_id=sec_user_id,
            url=url,
            endpoint=endpoint,
            status_code=status_code,
            exception_type=error_type,
            markers=markers,
            raw_excerpt=raw_excerpt,
        )

    if any(
        token in lowered
        for token in (
            "net::err_connection_closed",
            "connection closed",
            "context has been closed",
            "browser has been closed",
            "target page, context or browser has been closed",
            "timed out",
            "timeout",
            "session validation failed",
        )
    ):
        return build_risk_signal(
            "session_unstable",
            severity="medium",
            scope="session",
            source=source,
            retryable=True,
            should_pause=False,
            cooldown_seconds=0,
            username=username,
            sec_user_id=sec_user_id,
            url=url,
            endpoint=endpoint,
            status_code=status_code,
            exception_type=error_type,
            markers=markers,
            raw_excerpt=raw_excerpt,
        )

    if _looks_like_html(raw_excerpt):
        return build_risk_signal(
            "invalid_json_response",
            severity="high",
            scope="session",
            source=source,
            retryable=True,
            should_pause=True,
            cooldown_seconds=cooldown_seconds,
            username=username,
            sec_user_id=sec_user_id,
            url=url,
            endpoint=endpoint,
            status_code=status_code,
            exception_type=error_type,
            markers=markers,
            raw_excerpt=raw_excerpt,
        )

    if markers or raw_excerpt:
        return build_risk_signal(
            "unknown_risk",
            severity="medium",
            scope="session",
            source=source,
            retryable=True,
            should_pause=False,
            cooldown_seconds=0,
            username=username,
            sec_user_id=sec_user_id,
            url=url,
            endpoint=endpoint,
            status_code=status_code,
            exception_type=error_type,
            markers=markers,
            raw_excerpt=raw_excerpt,
        )

    return None


def extract_user_video_count(user_info: dict[str, Any] | None) -> int:
    if not isinstance(user_info, dict):
        return 0
    if nested := user_info.get("userInfo"):
        return extract_user_video_count(nested)
    stats = user_info.get("stats") or user_info.get("statsV2") or {}
    if not isinstance(stats, dict):
        return 0
    for key in ("videoCount", "video_count"):
        if value := stats.get(key):
            return _to_int(value)
    return 0


def classify_api_payload(
    payload: dict[str, Any] | None,
    *,
    endpoint: str,
    source: str,
    cooldown_seconds: int,
    username: str = "",
    sec_user_id: str = "",
    url: str = "",
    cached_user_info: dict[str, Any] | None = None,
) -> TikTokRiskSignal | None:
    if payload is None:
        return build_risk_signal(
            "invalid_json_response",
            reason="TikTok API 未返回有效数据",
            severity="high",
            scope="session",
            source=source,
            retryable=True,
            should_pause=True,
            cooldown_seconds=cooldown_seconds,
            username=username,
            sec_user_id=sec_user_id,
            url=url,
            endpoint=endpoint,
        )

    status_code = payload.get("status_code")
    if status_code is None:
        status_code = payload.get("statusCode")
    status_msg = str(payload.get("status_msg") or payload.get("statusMsg") or "").strip()
    markers = detect_risk_markers(status_msg)
    if markers:
        category = _category_from_markers(markers)
        return build_risk_signal(
            category,
            severity="high",
            scope="session",
            source=source,
            retryable=True,
            should_pause=True,
            cooldown_seconds=cooldown_seconds,
            username=username,
            sec_user_id=sec_user_id,
            url=url,
            endpoint=endpoint,
            status_code=status_code,
            markers=markers,
            raw_excerpt=json.dumps(
                {
                    "status_code": status_code,
                    "status_msg": status_msg,
                },
                ensure_ascii=False,
            ),
        )

    if status_code not in (None, 0):
        return build_risk_signal(
            "api_status_error",
            reason=(
                f"TikTok API 状态异常: status_code={status_code}, "
                f"status_msg={status_msg or '<empty>'}"
            ),
            severity="high",
            scope="session",
            source=source,
            retryable=True,
            should_pause=True,
            cooldown_seconds=cooldown_seconds,
            username=username,
            sec_user_id=sec_user_id,
            url=url,
            endpoint=endpoint,
            status_code=status_code,
            raw_excerpt=json.dumps(payload, ensure_ascii=False),
        )

    if endpoint == "user_detail" and not payload.get("userInfo"):
        return build_risk_signal(
            "user_info_missing",
            severity="medium",
            scope="account",
            source=source,
            retryable=True,
            should_pause=False,
            cooldown_seconds=0,
            username=username,
            sec_user_id=sec_user_id,
            url=url,
            endpoint=endpoint,
            status_code=status_code,
            raw_excerpt=json.dumps(payload, ensure_ascii=False),
        )

    if endpoint == "post_item_list":
        items = payload.get("itemList") or []
        if items:
            return None
        video_count = extract_user_video_count(cached_user_info)
        if video_count > 0:
            return build_risk_signal(
                "account_items_unavailable",
                reason=f"账号资料显示至少有 {video_count} 个作品，但接口返回空 itemList",
                severity="high",
                scope="account",
                source=source,
                retryable=True,
                should_pause=True,
                cooldown_seconds=cooldown_seconds,
                username=username,
                sec_user_id=sec_user_id,
                url=url,
                endpoint=endpoint,
                status_code=status_code,
                raw_excerpt=json.dumps(payload, ensure_ascii=False),
                extra={"video_count": video_count},
            )

    return None
