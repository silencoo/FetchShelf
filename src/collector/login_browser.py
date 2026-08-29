from __future__ import annotations

import asyncio
import hashlib
import hmac
import os
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from secrets import token_urlsafe
from shutil import which
from time import monotonic
from typing import Any
from urllib.parse import unquote, urlsplit
from uuid import uuid4

from playwright.async_api import async_playwright

from .models import CollectorCredentials, CollectorIdentity, CollectorPlatform


class LoginBrowserError(RuntimeError):
    """Base error for the interactive collector identity browser."""


class LoginBrowserDependencyError(LoginBrowserError):
    pass


class LoginBrowserBusyError(LoginBrowserError):
    pass


class LoginBrowserNotFoundError(LoginBrowserError):
    pass


class LoginBrowserNotAuthenticatedError(LoginBrowserError):
    pass


@dataclass(frozen=True)
class CapturedLoginCredentials:
    cookie: str = field(repr=False)
    user_agent: str = field(default="", repr=False)
    cookie_count: int = 0
    login_cookie_count: int = 0


@dataclass
class LoginBrowserSession:
    session_id: str
    identity_id: str
    platform: CollectorPlatform
    started_at: datetime
    expires_at: datetime
    expires_monotonic: float
    display: int
    vnc_port: int
    width: int
    height: int
    playwright: Any
    context: Any
    xvfb_process: asyncio.subprocess.Process | None
    vnc_process: asyncio.subprocess.Process | None
    startup_warning: str = ""
    viewer_connected: bool = False
    viewer_tickets: list[tuple[bytes, float]] = field(default_factory=list)
    expiry_task: asyncio.Task | None = None

    def public_data(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "identity_id": self.identity_id,
            "platform": self.platform.value,
            "status": "running",
            "started_at": self.started_at.isoformat(timespec="seconds"),
            "expires_at": self.expires_at.isoformat(timespec="seconds"),
            "viewer_connected": self.viewer_connected,
            "width": self.width,
            "height": self.height,
            "startup_warning": self.startup_warning,
        }


class CollectorLoginBrowserManager:
    """One interactive browser bound to one collector identity at a time.

    Xvfb and x11vnc stay on container-local interfaces. The Web UI reaches the
    raw RFB server only through the authenticated FastAPI WebSocket proxy.
    """

    DISPLAY = 98
    VNC_PORT = 5901
    WIDTH = 1440
    HEIGHT = 900
    SESSION_TTL_SECONDS = 20 * 60
    VIEWER_TICKET_TTL_SECONDS = 60
    VIEWER_PROTOCOL_PREFIX = "fetchshelf-login."
    PLATFORM_URLS = {
        CollectorPlatform.DOUYIN: "https://www.douyin.com/",
        CollectorPlatform.TIKTOK: "https://www.tiktok.com/login",
    }
    PLATFORM_DOMAINS = {
        CollectorPlatform.DOUYIN: "douyin.com",
        CollectorPlatform.TIKTOK: "tiktok.com",
    }
    LOGIN_COOKIE_NAMES = {
        "sessionid",
        "sessionid_ss",
        "sid_tt",
        "sid_guard",
        "uid_tt",
        "uid_tt_ss",
        "login_status",
    }

    def __init__(
        self,
        settings_dir: str | Path,
        *,
        session_ttl_seconds: int = SESSION_TTL_SECONDS,
        display: int = DISPLAY,
        vnc_port: int = VNC_PORT,
        width: int = WIDTH,
        height: int = HEIGHT,
    ) -> None:
        self.settings_dir = Path(settings_dir)
        self.session_ttl_seconds = max(60, int(session_ttl_seconds))
        self.display = int(display)
        self.vnc_port = int(vnc_port)
        self.width = max(800, int(width))
        self.height = max(600, int(height))
        self._session: LoginBrowserSession | None = None
        self._lock = asyncio.Lock()

    @property
    def supported(self) -> bool:
        return bool(which("Xvfb") and which("x11vnc"))

    def is_identity_locked(self, identity_id: str) -> bool:
        session = self._session
        return bool(session and session.identity_id == identity_id)

    def session_for(self, identity_id: str) -> dict[str, Any] | None:
        session = self._session
        if not session or session.identity_id != identity_id:
            return None
        if session.expires_monotonic <= monotonic():
            return None
        return session.public_data()

    async def start(
        self,
        identity: CollectorIdentity,
        credentials: CollectorCredentials,
    ) -> LoginBrowserSession:
        async with self._lock:
            current = self._session
            if current and current.expires_monotonic <= monotonic():
                self._session = None
                await self._cleanup_session(current)
                current = None
            if current:
                if current.identity_id == identity.identity_id:
                    return current
                raise LoginBrowserBusyError(
                    "another collector identity login browser is already running"
                )
            xvfb_path = which("Xvfb")
            x11vnc_path = which("x11vnc")
            if not xvfb_path or not x11vnc_path:
                raise LoginBrowserDependencyError(
                    "interactive login browser requires Xvfb and x11vnc"
                )

            profile_dir = self.settings_dir.joinpath(
                "browser_profiles",
                identity.identity_id,
            )
            profile_dir.mkdir(parents=True, exist_ok=True)
            try:
                profile_dir.chmod(0o700)
            except OSError:
                pass
            for name in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
                try:
                    profile_dir.joinpath(name).unlink(missing_ok=True)
                except OSError:
                    pass

            session_id = f"lb_{uuid4().hex}"
            xvfb_process: asyncio.subprocess.Process | None = None
            vnc_process: asyncio.subprocess.Process | None = None
            playwright = None
            context = None
            try:
                xvfb_process = await asyncio.create_subprocess_exec(
                    xvfb_path,
                    f":{self.display}",
                    "-screen",
                    "0",
                    f"{self.width}x{self.height}x24",
                    "-nolisten",
                    "tcp",
                    "-ac",
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                await self._ensure_process_started(xvfb_process, "Xvfb")

                display_env = {**os.environ, "DISPLAY": f":{self.display}"}
                vnc_process = await asyncio.create_subprocess_exec(
                    x11vnc_path,
                    "-display",
                    f":{self.display}",
                    "-rfbport",
                    str(self.vnc_port),
                    "-localhost",
                    "-forever",
                    "-shared",
                    "-nopw",
                    "-noxdamage",
                    "-quiet",
                    env=display_env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                await self._wait_for_vnc(vnc_process)

                playwright = await async_playwright().start()
                launch_options: dict[str, Any] = {
                    "headless": False,
                    "channel": "chromium",
                    "viewport": None,
                    "locale": "zh-CN",
                    "env": display_env,
                    "args": [
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-quic",
                        f"--window-size={self.width},{self.height}",
                        "--start-maximized",
                    ],
                }
                if proxy := self._playwright_proxy(credentials.proxy):
                    launch_options["proxy"] = proxy
                if credentials.user_agent:
                    launch_options["user_agent"] = credentials.user_agent
                context = await playwright.chromium.launch_persistent_context(
                    str(profile_dir),
                    **launch_options,
                )
                if credentials.cookie:
                    await context.add_cookies(
                        self._cookie_header_to_playwright(
                            credentials.cookie,
                            identity.platform,
                        )
                    )
                pages = list(context.pages)
                page = pages[0] if pages else await context.new_page()
                startup_warning = ""
                try:
                    await page.goto(
                        self.PLATFORM_URLS[identity.platform],
                        wait_until="domcontentloaded",
                        timeout=30_000,
                    )
                except Exception:
                    startup_warning = "登录页暂时未加载，请在浏览器中刷新后重试。"

                now = datetime.now(timezone.utc)
                session = LoginBrowserSession(
                    session_id=session_id,
                    identity_id=identity.identity_id,
                    platform=identity.platform,
                    started_at=now,
                    expires_at=now + timedelta(seconds=self.session_ttl_seconds),
                    expires_monotonic=monotonic() + self.session_ttl_seconds,
                    display=self.display,
                    vnc_port=self.vnc_port,
                    width=self.width,
                    height=self.height,
                    playwright=playwright,
                    context=context,
                    xvfb_process=xvfb_process,
                    vnc_process=vnc_process,
                    startup_warning=startup_warning,
                )
                self._session = session
                context.on(
                    "close",
                    lambda *_: self._schedule_closed_session_stop(session_id),
                )
                session.expiry_task = asyncio.create_task(
                    self._expire_session(session_id),
                    name=f"collector-login-expiry:{identity.identity_id}",
                )
                return session
            except BaseException:
                await self._cleanup_resources(
                    context=context,
                    playwright=playwright,
                    vnc_process=vnc_process,
                    xvfb_process=xvfb_process,
                )
                raise

    async def capture(
        self,
        identity_id: str,
        session_id: str,
    ) -> CapturedLoginCredentials:
        async with self._lock:
            session = self._require_session(identity_id, session_id)
            return await self._capture_session(session)

    async def _capture_session(
        self,
        session: LoginBrowserSession,
    ) -> CapturedLoginCredentials:
        context = session.context
        platform = session.platform
        cookies = await context.cookies([self.PLATFORM_URLS[platform]])
        domain = self.PLATFORM_DOMAINS[platform]
        selected: dict[str, str] = {}
        login_cookie_count = 0
        for cookie in cookies:
            cookie_domain = str(cookie.get("domain") or "").lstrip(".").lower()
            if cookie_domain != domain and not cookie_domain.endswith(f".{domain}"):
                continue
            name = str(cookie.get("name") or "").strip()
            value = str(cookie.get("value") or "")
            if not name or not value:
                continue
            selected[name] = value
            if name.lower() in self.LOGIN_COOKIE_NAMES:
                login_cookie_count += 1
        if not login_cookie_count:
            raise LoginBrowserNotAuthenticatedError(
                "login cookies were not detected; finish signing in before saving"
            )

        user_agent = ""
        for page in reversed(list(context.pages)):
            try:
                user_agent = str(await page.evaluate("navigator.userAgent") or "")
            except Exception:
                continue
            if user_agent:
                break
        cookie_header = "; ".join(
            f"{name}={value}" for name, value in selected.items()
        )
        return CapturedLoginCredentials(
            cookie=cookie_header,
            user_agent=user_agent,
            cookie_count=len(selected),
            login_cookie_count=login_cookie_count,
        )

    async def issue_viewer_ticket(
        self,
        identity_id: str,
        session_id: str,
    ) -> str:
        async with self._lock:
            session = self._require_session(identity_id, session_id)
            now = monotonic()
            session.viewer_tickets = [
                item for item in session.viewer_tickets if item[1] > now
            ]
            raw = token_urlsafe(32)
            digest = hashlib.sha256(raw.encode("utf-8")).digest()
            session.viewer_tickets.append(
                (digest, now + self.VIEWER_TICKET_TTL_SECONDS)
            )
            return raw

    async def begin_viewer(
        self,
        identity_id: str,
        session_id: str,
        ticket: str,
    ) -> int:
        digest = hashlib.sha256(ticket.encode("utf-8")).digest()
        async with self._lock:
            session = self._require_session(identity_id, session_id)
            now = monotonic()
            matched = False
            remaining: list[tuple[bytes, float]] = []
            for stored, expires_at in session.viewer_tickets:
                if (
                    not matched
                    and expires_at > now
                    and hmac.compare_digest(stored, digest)
                ):
                    matched = True
                    continue
                if expires_at > now:
                    remaining.append((stored, expires_at))
            session.viewer_tickets = remaining
            if not matched:
                raise LoginBrowserNotFoundError("viewer ticket is invalid or expired")
            if session.viewer_connected:
                raise LoginBrowserBusyError("login browser already has an active viewer")
            session.viewer_connected = True
            return session.vnc_port

    async def end_viewer(self, identity_id: str, session_id: str) -> None:
        async with self._lock:
            session = self._session
            if (
                session
                and session.identity_id == identity_id
                and session.session_id == session_id
            ):
                session.viewer_connected = False

    async def stop(self, identity_id: str = "", session_id: str = "") -> bool:
        async with self._lock:
            session = self._session
            if not session:
                return False
            if identity_id and session.identity_id != identity_id:
                return False
            if session_id and session.session_id != session_id:
                return False
            self._session = None
        await self._cleanup_session(session)
        return True

    async def cleanup(self) -> None:
        await self.stop()

    def _require_session(
        self,
        identity_id: str,
        session_id: str,
    ) -> LoginBrowserSession:
        session = self._session
        if (
            not session
            or session.identity_id != identity_id
            or session.session_id != session_id
            or session.expires_monotonic <= monotonic()
        ):
            raise LoginBrowserNotFoundError("collector login browser session not found")
        return session

    async def _expire_session(self, session_id: str) -> None:
        try:
            await asyncio.sleep(self.session_ttl_seconds)
            await self.stop(session_id=session_id)
        except asyncio.CancelledError:
            return

    async def _stop_closed_session(self, session_id: str) -> None:
        await self.stop(session_id=session_id)

    def _schedule_closed_session_stop(self, session_id: str) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(
            self._stop_closed_session(session_id),
            name=f"collector-login-close:{session_id}",
        )

    async def _cleanup_session(self, session: LoginBrowserSession) -> None:
        current_task = asyncio.current_task()
        if session.expiry_task and session.expiry_task is not current_task:
            session.expiry_task.cancel()
        await self._cleanup_resources(
            context=session.context,
            playwright=session.playwright,
            vnc_process=session.vnc_process,
            xvfb_process=session.xvfb_process,
        )

    @classmethod
    async def _cleanup_resources(
        cls,
        *,
        context: Any,
        playwright: Any,
        vnc_process: asyncio.subprocess.Process | None,
        xvfb_process: asyncio.subprocess.Process | None,
    ) -> None:
        if context is not None:
            try:
                await context.close()
            except Exception:
                pass
        if playwright is not None:
            try:
                await playwright.stop()
            except Exception:
                pass
        await cls._terminate_process(vnc_process)
        await cls._terminate_process(xvfb_process)

    @staticmethod
    async def _terminate_process(
        process: asyncio.subprocess.Process | None,
    ) -> None:
        if process is None or process.returncode is not None:
            return
        try:
            process.terminate()
        except ProcessLookupError:
            return
        try:
            await asyncio.wait_for(process.wait(), timeout=3)
        except asyncio.TimeoutError:
            try:
                process.kill()
            except ProcessLookupError:
                return
            await process.wait()

    @staticmethod
    async def _ensure_process_started(
        process: asyncio.subprocess.Process,
        label: str,
    ) -> None:
        await asyncio.sleep(0.25)
        if process.returncode is not None:
            raise LoginBrowserDependencyError(f"{label} failed to start")

    async def _wait_for_vnc(self, process: asyncio.subprocess.Process) -> None:
        deadline = monotonic() + 8
        while monotonic() < deadline:
            if process.returncode is not None:
                raise LoginBrowserDependencyError("x11vnc failed to start")
            try:
                _reader, writer = await asyncio.open_connection(
                    "127.0.0.1",
                    self.vnc_port,
                )
            except OSError:
                await asyncio.sleep(0.2)
                continue
            writer.close()
            await writer.wait_closed()
            return
        raise LoginBrowserDependencyError("x11vnc did not become ready")

    @classmethod
    def _cookie_header_to_playwright(
        cls,
        cookie_header: str,
        platform: CollectorPlatform,
    ) -> list[dict[str, Any]]:
        value = str(cookie_header or "").strip()
        if value.lower().startswith("cookie:"):
            value = value.split(":", 1)[1].strip()
        domain = f".{cls.PLATFORM_DOMAINS[platform]}"
        cookies = []
        for part in value.split(";"):
            if "=" not in part:
                continue
            name, item = part.strip().split("=", 1)
            if not name:
                continue
            cookies.append(
                {
                    "name": name,
                    "value": item,
                    "domain": domain,
                    "path": "/",
                    "secure": True,
                }
            )
        return cookies

    @staticmethod
    def _playwright_proxy(value: str) -> dict[str, str] | None:
        raw = str(value or "").strip()
        if not raw:
            return None
        parsed = urlsplit(raw)
        if not parsed.scheme or not parsed.hostname:
            return {"server": raw}
        host = parsed.hostname
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        server = f"{parsed.scheme}://{host}"
        if parsed.port:
            server = f"{server}:{parsed.port}"
        proxy = {"server": server}
        if parsed.username:
            proxy["username"] = unquote(parsed.username)
        if parsed.password:
            proxy["password"] = unquote(parsed.password)
        return proxy
