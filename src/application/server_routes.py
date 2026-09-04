from asyncio import (
    FIRST_COMPLETED,
    Event,
    create_task,
    gather,
    open_connection,
    sleep,
    to_thread,
    wait,
)
from datetime import datetime
from json import JSONDecodeError, dumps, loads
from mimetypes import guess_type
from shutil import copy2
from textwrap import dedent
from urllib.parse import urlsplit

from fastapi import (
    Body,
    Depends,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from pydantic import ValidationError

from ..collector import (
    AssignmentSource,
    CollectorAssignment,
    CollectorAuthMode,
    CollectorCredentials,
    CollectorPolicy,
    IdentityInUseError,
    IdentityPlatformError,
    IdentityStatus,
    LoginBrowserBusyError,
    LoginBrowserError,
    LoginBrowserNotFoundError,
    RouteTarget,
    RouteUnavailable,
    RoutingStrategy,
    SecretCodecUnavailable,
    plan_routes,
)
from ..custom import PROJECT_ROOT, is_valid_token
from ..models import (
    Account,
    AccountTiktok,
    Comment,
    DataResponse,
    Detail,
    DetailTikTok,
    GeneralSearch,
    Live,
    LiveSearch,
    LiveTikTok,
    Mix,
    MixTikTok,
    Reply,
    Settings,
    ShortUrl,
    UrlResponse,
    UserSearch,
    VideoSearch,
)
from ..translation import _
from ..webui.files import (
    IMAGE_SUFFIXES,
    ScopeType,
    relative_path,
    resolve_within_root,
    serialize_entry,
)
from ..webui.profile_avatar import generate_face_avatar
from ..webui_security import (
    redact_webui_json_text,
    redact_webui_value,
    restore_redacted_values,
)

__all__ = [
    "ServerRoutesMixin",
    "WEBUI_SESSION_COOKIE",
    "WEBUI_SESSION_MAX_AGE",
    "token_dependency",
]

WEBUI_SESSION_COOKIE = "fetchshelf_webui_session"
WEBUI_SESSION_MAX_AGE = 60 * 60 * 24 * 30


def token_dependency(
    request: Request,
    token: str | None = Header(None),
):
    client_host = request.client.host if request.client else ""
    supplied_token = token or request.cookies.get(WEBUI_SESSION_COOKIE)
    if not is_valid_token(supplied_token, client_host):
        raise HTTPException(
            status_code=403,
            detail=_("验证失败！"),
        )
    return supplied_token or ""


class ServerRoutesMixin:
    def setup_routes(self):
        @self.server.exception_handler(RequestValidationError)
        async def safe_request_validation_error(
            request: Request,
            error: RequestValidationError,
        ):
            # FastAPI's default 422 includes the rejected input verbatim. A
            # malformed credential body could therefore echo Cookie or proxy
            # passwords before the endpoint handler runs.
            return JSONResponse(
                status_code=422,
                content={"detail": self._safe_validation_errors(error)},
            )

        @self.server.get(
            "/ui",
            include_in_schema=False,
        )
        async def webui():
            index_file = self.WEBUI_STATIC_DIR.joinpath("index.html")
            if not index_file.is_file():
                raise HTTPException(
                    status_code=404,
                    detail="Web UI resources not found.",
                )
            return FileResponse(
                index_file,
                headers={"Cache-Control": "no-cache"},
            )

        @self.server.get(
            "/ui/api/files",
            summary="Web UI 文件浏览",
            description="返回目录列表，供 Web UI 文件浏览卡片使用",
            tags=[_("项目")],
        )
        async def webui_files(
            scope: ScopeType = Query("download"),
            path: str = Query(""),
            page: int = Query(1, ge=1),
            page_size: int = Query(24, ge=12, le=96),
            search: str = Query(""),
            token: str = Depends(token_dependency),
        ):
            if scope not in {"project", "download"}:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid scope.",
                )
            root = self._scope_root(scope)
            try:
                current = resolve_within_root(root, path)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail="Path out of scope.",
                )
            self._ensure_public_file_scope_path(scope, root, current)
            if not current.exists():
                raise HTTPException(
                    status_code=404,
                    detail="Path does not exist.",
                )
            if not current.is_dir():
                raise HTTPException(
                    status_code=400,
                    detail="Path is not a directory.",
                )
            entries = sorted(
                (
                    serialize_entry(root, item)
                    for item in current.iterdir()
                    if not self._is_protected_file_scope_path(scope, root, item)
                ),
                key=lambda item: (not item["is_dir"], item["name"].lower()),
            )
            search_value = search.strip().casefold()
            if search_value:
                entries = [
                    item
                    for item in entries
                    if search_value in str(item.get("name", "")).casefold()
                    or search_value in str(item.get("path", "")).casefold()
                ]
            total = len(entries)
            pages = max(1, (total + page_size - 1) // page_size)
            page = min(page, pages)
            offset = (page - 1) * page_size
            page_entries = entries[offset:offset + page_size]
            root_path = root.expanduser().resolve()
            current_path = current.expanduser().resolve()
            return {
                "scope": scope,
                "root": str(root_path),
                "path": relative_path(root_path, current_path),
                "is_root": current_path == root_path,
                "parent": (
                    ""
                    if current_path == root_path
                    else relative_path(root_path, current_path.parent)
                ),
                "entries": page_entries,
                "count": len(page_entries),
                "total": total,
                "page": page,
                "page_size": page_size,
                "pages": pages,
                "search": search.strip(),
            }

        @self.server.get(
            "/ui/api/file",
            summary="Web UI 文件访问",
            description="返回 scope 下的文件内容，禁止越界路径",
            tags=[_("项目")],
        )
        async def webui_file(
            scope: ScopeType = Query("download"),
            path: str = Query(""),
            token: str = Depends(token_dependency),
        ):
            if scope not in {"project", "download"}:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid scope.",
                )
            if not path:
                raise HTTPException(
                    status_code=400,
                    detail="Path is required.",
                )
            root = self._scope_root(scope)
            try:
                target = resolve_within_root(root, path)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail="Path out of scope.",
                )
            self._ensure_public_file_scope_path(scope, root, target)
            if not target.exists():
                raise HTTPException(
                    status_code=404,
                    detail="File does not exist.",
                )
            if not target.is_file():
                raise HTTPException(
                    status_code=400,
                    detail="Target is not a file.",
                )
            media_type = guess_type(target.name)[0] or "application/octet-stream"
            return FileResponse(target, media_type=media_type)

        @self.server.get(
            "/ui/api/overview",
            summary="Web UI 运行概览",
            description="聚合媒体库、账号批次和采集身份状态",
            tags=[_("项目")],
        )
        async def webui_overview(
            refresh_media: bool = Query(False),
            token: str = Depends(token_dependency),
        ):
            media = self._overview_media_snapshot(
                force_refresh=refresh_media,
            )
            await self._flush_storage_alert(media)
            return {
                "generated_at": datetime.now()
                .astimezone()
                .isoformat(timespec="seconds"),
                "media": media,
                "crawl": self._overview_crawl_summary(),
                "collectors": self._overview_collector_summary(),
                "maintenance": {
                    "latest_snapshot": self._latest_configuration_snapshot(),
                    "snapshot_retention": self.CONFIGURATION_SNAPSHOT_RETENTION,
                },
            }

        @self.server.post(
            "/ui/api/maintenance/snapshot",
            summary="Web UI 配置与数据库快照",
            description="一致性备份 settings 与采集/任务 SQLite 数据库",
            tags=[_("配置")],
        )
        async def webui_maintenance_snapshot(
            token: str = Depends(token_dependency),
        ):
            snapshot = await to_thread(
                self._create_configuration_snapshot,
                "manual",
            )
            return {
                "message": _("配置与数据库快照已创建！"),
                "snapshot": snapshot,
            }

        @self.server.post(
            "/ui/api/maintenance/integrity-scan",
            summary="Web UI 媒体完整性扫描",
            description="后台重新扫描媒体数量、零字节文件、临时文件与读取错误",
            tags=[_("项目")],
        )
        async def webui_maintenance_integrity_scan(
            token: str = Depends(token_dependency),
        ):
            media = self._overview_media_snapshot(force_refresh=True)
            return {
                "message": _("媒体完整性扫描已在后台启动！"),
                "media": media,
            }

        @self.server.get(
            "/ui/api/files/stats",
            summary="Web UI 文件统计",
            description="统计目录下文件/图片/视频/文件夹数量和占用空间",
            tags=[_("项目")],
        )
        async def webui_files_stats(
            scope: ScopeType = Query("download"),
            path: str = Query(""),
            token: str = Depends(token_dependency),
        ):
            if scope not in {"project", "download"}:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid scope.",
                )
            root = self._scope_root(scope)
            try:
                current = resolve_within_root(root, path)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail="Path out of scope.",
                )
            self._ensure_public_file_scope_path(scope, root, current)
            if not current.exists() or not current.is_dir():
                raise HTTPException(
                    status_code=404,
                    detail="Path does not exist or is not a directory.",
                )
            root_path = root.expanduser().resolve()
            current_path = current.expanduser().resolve()
            return {
                "scope": scope,
                "root": str(root_path),
                "path": relative_path(root_path, current_path),
                **await to_thread(
                    self._collect_scope_stats,
                    current_path,
                    scope,
                    root_path,
                ),
            }

        @self.server.get(
            "/ui/api/settings/raw",
            summary="Web UI 原始 settings.json",
            description="返回 settings.json 原始文本，供 Web UI 编辑器使用",
            tags=[_("配置")],
        )
        async def webui_settings_raw(
            response: Response,
            include_secrets: bool = Query(False),
            token: str = Depends(token_dependency),
        ):
            response.headers["Cache-Control"] = "no-store"
            response.headers["X-Content-Type-Options"] = "nosniff"
            settings_path = self.parameter.settings.path
            if not settings_path.exists():
                self.parameter.settings.read()
            text = settings_path.read_text(
                encoding=self.parameter.settings.encode,
            )
            updated_at = datetime.fromtimestamp(settings_path.stat().st_mtime).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            return {
                "path": str(settings_path),
                "text": text if include_secrets else redact_webui_json_text(text),
                "updated_at": updated_at,
                "secrets_included": include_secrets,
            }

        @self.server.put(
            "/ui/api/settings/raw",
            summary="Web UI 保存原始 settings.json",
            description="写入并应用 settings.json 原始文本",
            tags=[_("配置")],
        )
        async def webui_settings_raw_update(
            body: dict = Body(...),
            token: str = Depends(token_dependency),
        ):
            text = body.get("text")
            if not isinstance(text, str):
                raise HTTPException(
                    status_code=400,
                    detail="text must be a JSON string.",
                )
            try:
                patch_data = loads(text)
            except JSONDecodeError as error:
                raise HTTPException(
                    status_code=400,
                    detail=f"JSON parse error: {error}",
                )
            if not isinstance(patch_data, dict):
                raise HTTPException(
                    status_code=400,
                    detail="JSON root must be an object.",
                )
            merged = self.parameter.settings.read()
            patch_data = restore_redacted_values(patch_data, merged)
            merged.update(patch_data)
            self.parameter.settings.update(merged)
            try:
                await self.parameter.set_settings_data(merged.copy())
                self._sync_runtime_http_clients()
            except Exception as error:
                raise HTTPException(
                    status_code=400,
                    detail=f"Apply settings failed: {error}",
                )
            return {
                "message": _("保存配置成功！"),
                "settings": self._public_settings(self.parameter.get_settings_data()),
            }

        @self.server.post(
            "/ui/api/settings/backup",
            summary="Web UI 备份 settings.json",
            description="创建带时间戳的 settings.json 备份",
            tags=[_("配置")],
        )
        async def webui_settings_backup(
            body: dict = Body(default={}),
            token: str = Depends(token_dependency),
        ):
            reason = self._normalize_string(body.get("reason")) or "manual"
            backup_path = self._backup_settings_file(reason=reason)
            return {
                "message": _("配置备份成功！"),
                "path": backup_path,
            }

        @self.server.get(
            "/ui/api/collector-identities",
            summary="Web UI 采集身份列表",
            tags=[_("配置")],
        )
        async def webui_collector_identities(
            platform: str = Query(""),
            token: str = Depends(token_dependency),
        ):
            normalized_platform = (
                self._collector_platform(platform) if platform else None
            )
            items = self.collector_store.list_public(normalized_platform)
            return {
                "items": [
                    self._collector_identity_public_data(item) for item in items
                ],
                "total": len(items),
                "vault": {
                    "locked": bool(self.collector_vault_error),
                    "message": (
                        "身份凭据库尚未解锁，请配置身份加密密钥。"
                        if self.collector_vault_error
                        else "身份凭据库已解锁。"
                    ),
                },
            }

        @self.server.post(
            "/ui/api/collector-identities",
            summary="Web UI 创建采集身份",
            tags=[_("配置")],
        )
        async def webui_collector_identity_create(
            body: dict = Body(...),
            token: str = Depends(token_dependency),
        ):
            try:
                identity = self._collector_identity_from_body(body)
                self.collector_store.save_identity(identity)
                await self.collector_leases.configure(
                    identity.identity_id,
                    identity.max_concurrency,
                )
                public = next(
                    item
                    for item in self.collector_store.list_public(identity.platform)
                    if item.identity_id == identity.identity_id
                )
                return {"identity": self._collector_identity_public_data(public)}
            except Exception as error:
                if isinstance(error, HTTPException):
                    raise
                if isinstance(error, LoginBrowserError):
                    raise self._collector_login_browser_http_error(error)
                raise self._collector_http_error(error)

        @self.server.patch(
            "/ui/api/collector-identities/{identity_id}",
            summary="Web UI 更新采集身份",
            tags=[_("配置")],
        )
        async def webui_collector_identity_update(
            identity_id: str,
            body: dict = Body(...),
            token: str = Depends(token_dependency),
        ):
            try:
                if self._collector_identity_login_locked(identity_id):
                    raise LoginBrowserBusyError(
                        "stop the identity login browser before editing this identity"
                    )
                current = self.collector_store.get_identity(identity_id)
                identity = self._collector_identity_from_body(body, current=current)
                await self.collector_leases.configure(
                    identity.identity_id,
                    identity.max_concurrency,
                )
                self.collector_store.save_identity(identity)
                public = next(
                    item
                    for item in self.collector_store.list_public(identity.platform)
                    if item.identity_id == identity.identity_id
                )
                return {"identity": self._collector_identity_public_data(public)}
            except Exception as error:
                if isinstance(error, HTTPException):
                    raise
                if isinstance(error, LoginBrowserError):
                    raise self._collector_login_browser_http_error(error)
                raise self._collector_http_error(error)

        @self.server.delete(
            "/ui/api/collector-identities/{identity_id}",
            summary="Web UI 删除采集身份",
            tags=[_("配置")],
        )
        async def webui_collector_identity_delete(
            identity_id: str,
            token: str = Depends(token_dependency),
        ):
            identity = None
            try:
                if self._collector_identity_login_locked(identity_id):
                    raise LoginBrowserBusyError(
                        "stop the identity login browser before deleting this identity"
                    )
                identity = self.collector_store.get_identity(identity_id)
                schedule_references = [
                    schedule.get("schedule_id", "")
                    for schedule in self.ui_schedules.values()
                    if self._normalize_string(schedule.get("identity_id"))
                    == identity_id
                ]
                task_references = [
                    task.get("task_id", "")
                    for task in self.ui_tasks.values()
                    if task.get("status") in {"pending", "running", "canceling"}
                    and self._normalize_string(
                        (task.get("payload") or {}).get("identity_id")
                    )
                    == identity_id
                ]
                if schedule_references or task_references:
                    raise IdentityInUseError(
                        "collector identity is referenced by an active task or schedule"
                    )
                await self.collector_leases.remove(identity_id)
                try:
                    self.collector_store.delete_identity(identity_id)
                except Exception:
                    # A referenced identity cannot be deleted. Restore the
                    # runtime gate so a rejected delete never breaks routing.
                    await self.collector_leases.configure(
                        identity.identity_id,
                        identity.max_concurrency,
                    )
                    raise
                return {"message": _("采集身份已删除！"), "identity_id": identity_id}
            except Exception as error:
                if isinstance(error, LoginBrowserError):
                    raise self._collector_login_browser_http_error(error)
                raise self._collector_http_error(error)

        @self.server.put(
            "/ui/api/collector-identities/{identity_id}/credentials",
            summary="Web UI 替换采集身份凭据",
            description="凭据只写不回显；省略字段保持原值，null 清除单个字段",
            tags=[_("配置")],
        )
        async def webui_collector_identity_credentials(
            identity_id: str,
            body: dict = Body(...),
            token: str = Depends(token_dependency),
        ):
            try:
                if self._collector_identity_login_locked(identity_id):
                    raise LoginBrowserBusyError(
                        "stop the identity login browser before replacing credentials"
                    )
                identity = self.collector_store.get_identity(identity_id)
                credentials = self._collector_credentials_from_body(identity_id, body)
                self.collector_store.save_identity(
                    identity,
                    credentials=credentials,
                )
                public = next(
                    item
                    for item in self.collector_store.list_public(identity.platform)
                    if item.identity_id == identity_id
                )
                return {
                    "message": _("采集身份凭据已安全保存！"),
                    "identity": self._collector_identity_public_data(public),
                }
            except Exception as error:
                if isinstance(error, HTTPException):
                    raise
                if isinstance(error, LoginBrowserError):
                    raise self._collector_login_browser_http_error(error)
                raise self._collector_http_error(error)

        @self.server.delete(
            "/ui/api/collector-identities/{identity_id}/credentials",
            summary="Web UI 清除采集身份凭据",
            tags=[_("配置")],
        )
        async def webui_collector_identity_credentials_clear(
            identity_id: str,
            token: str = Depends(token_dependency),
        ):
            try:
                if self._collector_identity_login_locked(identity_id):
                    raise LoginBrowserBusyError(
                        "stop the identity login browser before clearing credentials"
                    )
                identity = self.collector_store.get_identity(identity_id)
                self.collector_store.save_identity(
                    identity,
                    credentials=CollectorCredentials(),
                )
                return {"message": _("采集身份凭据已清除！")}
            except Exception as error:
                if isinstance(error, LoginBrowserError):
                    raise self._collector_login_browser_http_error(error)
                raise self._collector_http_error(error)

        @self.server.post(
            "/ui/api/collector-identities/{identity_id}/login-browser",
            summary="Web UI 启动采集身份登录浏览器",
            tags=[_("配置")],
        )
        async def webui_collector_login_browser_start(
            identity_id: str,
            response: Response,
            token: str = Depends(token_dependency),
        ):
            response.headers["Cache-Control"] = "no-store"
            try:
                if self.collector_vault_error:
                    raise SecretCodecUnavailable(self.collector_vault_error)
                identity = self.collector_store.get_identity(identity_id)
                if identity.auth_mode == CollectorAuthMode.ANONYMOUS:
                    raise LoginBrowserError(
                        "anonymous identities do not need an interactive login browser"
                    )
                await self.collector_leases.configure(
                    identity.identity_id,
                    identity.max_concurrency,
                )
                lease = await self.collector_leases.snapshot(identity.identity_id)
                manager = self._get_collector_login_browser()
                existing = manager.session_for(identity_id)
                if not existing and (lease.active or lease.waiting):
                    raise LoginBrowserBusyError(
                        "collector identity is active or waiting for a crawl"
                    )
                credentials = self.collector_store.load_credentials(identity_id)
                session = await manager.start(identity, credentials)
                ticket = await manager.issue_viewer_ticket(
                    identity_id,
                    session.session_id,
                )
                return {
                    "session": session.public_data(),
                    "viewer_ticket": ticket,
                    "viewer_protocol_prefix": manager.VIEWER_PROTOCOL_PREFIX,
                }
            except Exception as error:
                if isinstance(error, HTTPException):
                    raise
                raise self._collector_login_browser_http_error(error)

        @self.server.get(
            "/ui/api/collector-identities/{identity_id}/login-browser",
            summary="Web UI 获取采集身份登录浏览器状态",
            tags=[_("配置")],
        )
        async def webui_collector_login_browser_status(
            identity_id: str,
            response: Response,
            token: str = Depends(token_dependency),
        ):
            response.headers["Cache-Control"] = "no-store"
            self.collector_store.get_identity(identity_id)
            session = self._get_collector_login_browser().session_for(identity_id)
            return {"session": session, "active": bool(session)}

        @self.server.post(
            "/ui/api/collector-identities/{identity_id}/login-browser/"
            "{session_id}/viewer-ticket",
            summary="Web UI 刷新登录浏览器查看凭证",
            tags=[_("配置")],
        )
        async def webui_collector_login_browser_ticket(
            identity_id: str,
            session_id: str,
            response: Response,
            token: str = Depends(token_dependency),
        ):
            response.headers["Cache-Control"] = "no-store"
            try:
                manager = self._get_collector_login_browser()
                ticket = await manager.issue_viewer_ticket(identity_id, session_id)
                return {
                    "viewer_ticket": ticket,
                    "viewer_protocol_prefix": manager.VIEWER_PROTOCOL_PREFIX,
                }
            except Exception as error:
                raise self._collector_login_browser_http_error(error)

        @self.server.post(
            "/ui/api/collector-identities/{identity_id}/login-browser/"
            "{session_id}/capture",
            summary="Web UI 保存登录浏览器凭据",
            tags=[_("配置")],
        )
        async def webui_collector_login_browser_capture(
            identity_id: str,
            session_id: str,
            response: Response,
            token: str = Depends(token_dependency),
        ):
            response.headers["Cache-Control"] = "no-store"
            manager = self._get_collector_login_browser()
            try:
                identity = self.collector_store.get_identity(identity_id)
                captured = await manager.capture(identity_id, session_id)
                current = self.collector_store.load_credentials(identity_id)
                credentials = current.model_copy(
                    update={
                        "cookie": captured.cookie,
                        "user_agent": captured.user_agent or current.user_agent,
                    },
                    deep=True,
                )
                self.collector_store.save_identity(
                    identity,
                    credentials=credentials,
                )
                runtime_state = self.collector_store.get_runtime(identity_id)
                runtime_state.status = IdentityStatus.WARNING
                runtime_state.last_validated_at = self._collector_timestamp()
                runtime_state.last_error_code = "login_state_pending_target_check"
                self.collector_store.save_runtime(runtime_state)
                public = next(
                    item
                    for item in self.collector_store.list_public(identity.platform)
                    if item.identity_id == identity_id
                )
                await manager.stop(identity_id, session_id)
                return {
                    "message": "登录 Cookie 已自动提取并安全保存。",
                    "cookie_count": captured.cookie_count,
                    "login_cookie_count": captured.login_cookie_count,
                    "identity": self._collector_identity_public_data(public),
                }
            except Exception as error:
                if isinstance(error, HTTPException):
                    raise
                raise self._collector_login_browser_http_error(error)

        @self.server.delete(
            "/ui/api/collector-identities/{identity_id}/login-browser/"
            "{session_id}",
            summary="Web UI 停止采集身份登录浏览器",
            tags=[_("配置")],
        )
        async def webui_collector_login_browser_stop(
            identity_id: str,
            session_id: str,
            token: str = Depends(token_dependency),
        ):
            stopped = await self._get_collector_login_browser().stop(
                identity_id,
                session_id,
            )
            if not stopped:
                raise HTTPException(
                    status_code=404,
                    detail="collector login browser session not found",
                )
            return {"message": "身份登录浏览器已停止。"}

        @self.server.websocket(
            "/ui/ws/collector-identities/{identity_id}/login-browser/"
            "{session_id}"
        )
        async def webui_collector_login_browser_ws(
            websocket: WebSocket,
            identity_id: str,
            session_id: str,
        ):
            token = (
                websocket.headers.get("token")
                or websocket.cookies.get(WEBUI_SESSION_COOKIE)
            )
            client_host = websocket.client.host if websocket.client else ""
            if not is_valid_token(token, client_host):
                await websocket.close(code=4403, reason=_("验证失败！"))
                return
            origin = websocket.headers.get("origin", "")
            host = websocket.headers.get("host", "")
            if origin:
                try:
                    origin_host = urlsplit(origin).netloc.lower()
                except ValueError:
                    origin_host = ""
                if not origin_host or origin_host != host.lower():
                    await websocket.close(code=4403, reason="Origin not allowed")
                    return
            protocols = list(websocket.scope.get("subprotocols", []))
            manager = self._get_collector_login_browser()
            ticket = next(
                (
                    item.removeprefix(manager.VIEWER_PROTOCOL_PREFIX)
                    for item in protocols
                    if item.startswith(manager.VIEWER_PROTOCOL_PREFIX)
                ),
                "",
            )
            if not ticket:
                await websocket.close(code=4403, reason="Viewer ticket required")
                return
            try:
                vnc_port = await manager.begin_viewer(
                    identity_id,
                    session_id,
                    ticket,
                )
            except LoginBrowserNotFoundError:
                await websocket.close(code=4404, reason="Viewer session not found")
                return
            except LoginBrowserBusyError:
                await websocket.close(code=4409, reason="Viewer already connected")
                return

            await websocket.accept(
                subprotocol="binary" if "binary" in protocols else None
            )
            writer = None
            tasks = set()
            pending = set()
            try:
                reader, writer = await open_connection("127.0.0.1", vnc_port)

                async def client_to_vnc():
                    while True:
                        message = await websocket.receive()
                        if message.get("type") == "websocket.disconnect":
                            return
                        data = message.get("bytes")
                        if data:
                            writer.write(data)
                            await writer.drain()

                async def vnc_to_client():
                    while data := await reader.read(64 * 1024):
                        await websocket.send_bytes(data)

                client_task = create_task(client_to_vnc())
                server_task = create_task(vnc_to_client())
                tasks = {client_task, server_task}
                _, pending = await wait(
                    tasks,
                    return_when=FIRST_COMPLETED,
                )
            except (OSError, WebSocketDisconnect):
                pass
            finally:
                for task in pending:
                    task.cancel()
                if tasks:
                    await gather(*tasks, return_exceptions=True)
                if writer is not None:
                    writer.close()
                    try:
                        await writer.wait_closed()
                    except OSError:
                        pass
                await manager.end_viewer(identity_id, session_id)
                try:
                    await websocket.close()
                except RuntimeError:
                    pass

        async def run_collector_probe(identity_id: str, require_proxy: bool):
            try:
                return await self._probe_collector_identity(
                    identity_id,
                    require_proxy=require_proxy,
                )
            except HTTPException:
                raise
            except Exception:
                try:
                    state = self.collector_store.get_runtime(identity_id)
                    state.status = IdentityStatus.WARNING
                    state.last_validated_at = self._collector_timestamp()
                    state.last_failure_at = state.last_validated_at
                    state.last_error_code = (
                        "proxy_connectivity_failed"
                        if require_proxy
                        else "identity_connectivity_failed"
                    )
                    state.consecutive_failures += 1
                    state.total_failures += 1
                    self.collector_store.save_runtime(state)
                except Exception:
                    pass
                raise HTTPException(
                    status_code=502,
                    detail=(
                        "Proxy connectivity check failed."
                        if require_proxy
                        else "Identity connectivity check failed."
                    ),
                )

        @self.server.post(
            "/ui/api/collector-identities/{identity_id}/validate",
            summary="Web UI 验证采集身份",
            tags=[_("配置")],
        )
        async def webui_collector_identity_validate(
            identity_id: str,
            token: str = Depends(token_dependency),
        ):
            return await run_collector_probe(identity_id, False)

        @self.server.post(
            "/ui/api/collector-identities/{identity_id}/proxy-test",
            summary="Web UI 测试身份代理",
            tags=[_("配置")],
        )
        async def webui_collector_identity_proxy_test(
            identity_id: str,
            token: str = Depends(token_dependency),
        ):
            return await run_collector_probe(identity_id, True)

        @self.server.get(
            "/ui/api/collector-policies/{platform}",
            summary="Web UI 获取采集路由策略",
            tags=[_("配置")],
        )
        async def webui_collector_policy_get(
            platform: str,
            token: str = Depends(token_dependency),
        ):
            policy = self.collector_store.get_policy(
                self._collector_platform(platform)
            )
            return {"policy": self._collector_public_data(policy)}

        @self.server.put(
            "/ui/api/collector-policies/{platform}",
            summary="Web UI 保存采集路由策略",
            tags=[_("配置")],
        )
        async def webui_collector_policy_update(
            platform: str,
            body: dict = Body(...),
            token: str = Depends(token_dependency),
        ):
            normalized_platform = self._collector_platform(platform)
            data = dict(body)
            data["platform"] = normalized_platform.value
            if data.get("default_identity_id") is None:
                data["default_identity_id"] = ""
            try:
                policy = CollectorPolicy.model_validate(data)
                for identity_id in (
                    policy.default_identity_id,
                    *policy.fallback_identity_ids,
                ):
                    if not identity_id:
                        continue
                    identity = self.collector_store.get_identity(identity_id)
                    if identity.platform != normalized_platform:
                        raise IdentityPlatformError(
                            "policy references an identity from another platform"
                        )
                await self.collector_leases.configure(
                    f"platform:{normalized_platform.value}",
                    policy.global_max_parallel,
                )
                self.collector_store.upsert_policy(policy)
                return {"policy": self._collector_public_data(policy)}
            except Exception as error:
                raise self._collector_http_error(error)

        @self.server.get(
            "/ui/api/collector-assignments",
            summary="Web UI 获取目标身份绑定",
            tags=[_("配置")],
        )
        async def webui_collector_assignments_get(
            platform: str = Query(""),
            target_type: str = Query(""),
            search: str = Query("", max_length=500),
            page: int | None = Query(None, ge=1),
            page_size: int | None = Query(None, ge=1, le=200),
            token: str = Depends(token_dependency),
        ):
            normalized_platform = (
                self._collector_platform(platform) if platform else None
            )
            normalized_target_type = target_type or None
            normalized_search = self._normalize_string(search)
            paginated = page is not None or page_size is not None or bool(
                normalized_search
            )
            if paginated:
                resolved_page_size = page_size or 50
                items, total, resolved_page, pages = (
                    self.collector_store.list_assignments_page(
                        normalized_platform,
                        target_type=normalized_target_type,
                        search=normalized_search,
                        page=page or 1,
                        page_size=resolved_page_size,
                    )
                )
            else:
                items = self.collector_store.list_assignments(
                    normalized_platform,
                    target_type=normalized_target_type,
                )
                total = len(items)
                resolved_page = 1
                resolved_page_size = max(1, total)
                pages = 1
            return {
                "assignments": [
                    self._collector_public_data(item) for item in items
                ],
                "total": total,
                "page": resolved_page,
                "page_size": resolved_page_size,
                "pages": pages,
                "search": normalized_search,
            }

        @self.server.put(
            "/ui/api/collector-assignments",
            summary="Web UI 保存目标身份绑定",
            tags=[_("配置")],
        )
        async def webui_collector_assignments_update(
            body: dict = Body(...),
            token: str = Depends(token_dependency),
        ):
            raw_items = body.get("assignments", [])
            if not isinstance(raw_items, list):
                raise HTTPException(status_code=400, detail="assignments must be a list.")
            saved = []
            removed = 0
            try:
                for raw in raw_items:
                    if not isinstance(raw, dict):
                        raise ValueError("assignment must be an object")
                    platform_value = self._collector_platform(raw.get("platform"))
                    target_type_value = self._normalize_string(
                        raw.get("target_type")
                    ) or "account"
                    target_key_value = self._normalize_string(raw.get("target_key"))
                    if target_type_value == "account":
                        target_key_value = (
                            self._normalize_account_url(target_key_value)
                            or target_key_value
                        )
                    identity_id_value = self._normalize_string(raw.get("identity_id"))
                    if not target_key_value:
                        raise ValueError("target_key is required")
                    if not identity_id_value:
                        removed += int(
                            self.collector_store.delete_assignment(
                                platform_value,
                                target_type_value,
                                target_key_value,
                            )
                        )
                        continue
                    assignment = CollectorAssignment(
                        platform=platform_value,
                        target_type=target_type_value,
                        target_key=target_key_value,
                        identity_id=identity_id_value,
                        source=AssignmentSource.EXPLICIT,
                    )
                    saved.extend(self.collector_store.upsert_assignments([assignment]))
                return {
                    "message": _("目标身份绑定已保存！"),
                    "assignments": [
                        self._collector_public_data(item) for item in saved
                    ],
                    "removed": removed,
                }
            except Exception as error:
                if isinstance(error, HTTPException):
                    raise
                raise self._collector_http_error(error)

        @self.server.post(
            "/ui/api/collector-policies/preview",
            summary="Web UI 预览采集路由",
            tags=[_("配置")],
        )
        async def webui_collector_policy_preview(
            body: dict = Body(...),
            token: str = Depends(token_dependency),
        ):
            platform_value = self._collector_platform(body.get("platform"))
            target_type_value = self._normalize_string(
                body.get("target_type")
            ) or "account"
            policy = self.collector_store.get_policy(platform_value)
            try:
                strategy = RoutingStrategy(
                    self._normalize_string(body.get("strategy"))
                    or policy.strategy.value
                )
                raw_targets = body.get("targets", [])
                if not isinstance(raw_targets, list) or not raw_targets:
                    raise ValueError("targets must be a non-empty list")
                normalized_raw_targets = []
                for raw in raw_targets:
                    target_key = self._normalize_string(
                        raw.get("target_key") if isinstance(raw, dict) else raw
                    )
                    if target_type_value == "account":
                        target_key = self._normalize_account_url(target_key) or target_key
                    if not target_key:
                        raise ValueError("target_key is required")
                    explicit = self._normalize_string(
                        raw.get("explicit_identity_id")
                        if isinstance(raw, dict)
                        else ""
                    )
                    normalized_raw_targets.append((target_key, explicit))

                # Account preview reuses the exact production planner without
                # persisting newly calculated sticky assignments. This keeps
                # cooldown, defaults, fixed-binding fallback, and strategy
                # behavior identical to actual execution.
                if target_type_value == "account" and not any(
                    explicit for _, explicit in normalized_raw_targets
                ):
                    planned = self._plan_collector_account_routes(
                        platform_value,
                        [{"url": target_key} for target_key, _ in normalized_raw_targets],
                        persist_assignments=False,
                        strategy_override=strategy,
                    )
                    if len(planned) != len(normalized_raw_targets):
                        raise RouteUnavailable("no eligible collector identity")
                    return {
                        "assignments": [
                            {
                                "target_key": item["target_key"],
                                "identity_id": item["identity_id"],
                                "strategy": strategy.value,
                                "explicit": item["reason"]
                                in {"fixed_binding", "default_identity"},
                                "reason": item["reason"],
                            }
                            for item in planned
                        ],
                        "counts": {
                            "requested": len(planned),
                            "assigned": len(planned),
                        },
                    }
                targets = []
                reasons = {}
                for target_key, explicit in normalized_raw_targets:
                    reason = "explicit"
                    if not explicit:
                        assignment = self.collector_store.get_assignment(
                            platform_value,
                            target_type_value,
                            target_key,
                        )
                        if assignment:
                            explicit = assignment.identity_id
                            reason = "stored_binding"
                        else:
                            reason = strategy.value
                    targets.append(
                        RouteTarget(
                            target_key=target_key,
                            explicit_identity_id=explicit,
                        )
                    )
                    reasons[target_key] = reason
                public = {
                    item.identity_id: item
                    for item in self.collector_store.list_public(platform_value)
                    if item.route_configured
                    and not self._collector_identity_login_locked(item.identity_id)
                }
                candidates = [
                    item
                    for item in self.collector_store.route_candidates(platform_value)
                    if item.identity_id in public
                ]
                decisions = plan_routes(
                    platform=platform_value,
                    targets=targets,
                    candidates=candidates,
                    strategy=strategy,
                )
                return {
                    "assignments": [
                        {
                            **self._collector_public_data(item),
                            "reason": reasons.get(item.target_key, strategy.value),
                        }
                        for item in decisions
                    ],
                    "counts": {
                        "requested": len(targets),
                        "assigned": len(decisions),
                    },
                }
            except RouteUnavailable as error:
                raise HTTPException(status_code=409, detail=str(error))
            except Exception as error:
                raise self._collector_http_error(error)

        @self.server.get(
            "/ui/api/accounts",
            summary="Web UI 账号配置",
            description="返回当前账号与回收站账号配置",
            tags=[_("配置")],
        )
        async def webui_accounts_get(
            token: str = Depends(token_dependency),
        ):
            return {
                "accounts_urls": self._account_rows(False),
                "accounts_urls_tiktok": self._account_rows(True),
                "deleted_accounts": self._account_rows(False, deleted=True),
                "deleted_accounts_tiktok": self._account_rows(True, deleted=True),
            }

        @self.server.put(
            "/ui/api/accounts",
            summary="Web UI 保存账号配置",
            description="保存账号与回收站配置，可选自动备份",
            tags=[_("配置")],
        )
        async def webui_accounts_update(
            body: dict = Body(...),
            token: str = Depends(token_dependency),
        ):
            try:
                self._validate_ui_account_update_payload(body)
            except ValueError as error:
                raise HTTPException(
                    status_code=400,
                    detail=f"Payload validation failed: {error}",
                )
            backup_path = ""
            if body.get("backup", True):
                backup_path = self._backup_settings_file(reason="accounts_update")
            data = self._sync_account_payload_to_runtime(body)
            return {
                "message": _("账号配置保存成功！"),
                "backup_path": backup_path,
                **data,
            }

        @self.server.post(
            "/ui/api/accounts/archive",
            summary="Web UI 将账号移入删除区",
            description="从后续采集目标中移除单个账号，并保留可撤销的删除区记录",
            tags=[_("配置")],
        )
        async def webui_account_archive(
            body: dict = Body(...),
            token: str = Depends(token_dependency),
        ):
            try:
                return self._archive_account_configuration(
                    platform=body.get("platform", ""),
                    url=body.get("url", ""),
                    reason=body.get("reason", ""),
                )
            except ValueError as error:
                raise HTTPException(
                    status_code=400,
                    detail=f"Payload validation failed: {error}",
                )

        @self.server.post(
            "/ui/api/accounts/archive-batch",
            summary="Web UI 批量将账号移入删除区",
            description="一次备份后从后续采集目标中移除多个账号，并保留可撤销记录",
            tags=[_("配置")],
        )
        async def webui_accounts_archive_batch(
            body: dict = Body(...),
            token: str = Depends(token_dependency),
        ):
            try:
                return self._archive_account_configurations(
                    platform=body.get("platform", ""),
                    urls=body.get("urls"),
                    reason=body.get("reason", ""),
                )
            except ValueError as error:
                raise HTTPException(
                    status_code=400,
                    detail=f"Payload validation failed: {error}",
                )

        @self.server.post(
            "/ui/api/accounts/verify",
            summary="Web UI 批量检测账号存在性",
            description="检测账号主页是否可访问，并可自动移入 deleted_accounts",
            tags=[_("配置")],
        )
        async def webui_accounts_verify(
            body: dict = Body(...),
            token: str = Depends(token_dependency),
        ):
            try:
                result = await self._verify_accounts(body)
            except ValueError as error:
                raise HTTPException(
                    status_code=400,
                    detail=f"Payload validation failed: {error}",
                )
            return result

        @self.server.get(
            "/ui/api/accounts/board",
            summary="Web UI 账号媒体看板",
            description="分页返回账号卡片及随机媒体预览（图片优先）",
            tags=[_("配置")],
        )
        async def webui_accounts_board(
            platform: str = Query("douyin"),
            page: int = Query(1, ge=1),
            page_size: int = Query(24, ge=6, le=80),
            search: str = Query("", max_length=240),
            status: str = Query("all"),
            sort: str = Query("configured"),
            token: str = Depends(token_dependency),
        ):
            return self._build_account_board_page(
                platform=platform,
                page=page,
                page_size=page_size,
                search=search,
                status=status,
                sort_by=sort,
            )

        @self.server.get(
            "/ui/api/accounts/board/gallery",
            summary="Web UI 账户媒体 Gallery",
            description="分页返回单个账户目录中的图片和视频，不依赖文件浏览器状态",
            tags=[_("配置")],
        )
        async def webui_accounts_board_gallery(
            platform: str = Query("douyin"),
            url: str = Query(..., min_length=1, max_length=2048),
            page: int = Query(1, ge=1),
            page_size: int = Query(24, ge=12, le=72),
            kind: str = Query("all"),
            token: str = Depends(token_dependency),
        ):
            try:
                return self._build_account_board_gallery(
                    platform=platform,
                    url=url,
                    page=page,
                    page_size=page_size,
                    media_kind=kind,
                )
            except LookupError:
                raise HTTPException(status_code=404, detail=_("账号不存在或已停用。"))

        @self.server.post(
            "/ui/api/accounts/board/random",
            summary="Web UI 刷新账号卡片媒体",
            description="为指定账号重新随机一张图片或一个视频",
            tags=[_("配置")],
        )
        async def webui_accounts_board_random(
            body: dict = Body(...),
            token: str = Depends(token_dependency),
        ):
            platform = self._normalize_board_platform(body.get("platform", "douyin"))
            url = self._normalize_string(body.get("url"))
            current_path = self._normalize_string(body.get("current_path"))
            prefer_kind = self._normalize_media_prefer_kind(body.get("prefer_kind"))
            if not url:
                raise HTTPException(
                    status_code=400,
                    detail="url is required.",
                )
            row = self._find_active_account_row(platform, url)
            if not row:
                raise HTTPException(
                    status_code=404,
                    detail="Account row not found.",
                )
            root = self._scope_root("download").expanduser().resolve()
            folder = self._match_account_board_dir(
                mark=row.get("mark", ""),
                url=url,
                candidates=self._account_board_dirs(root),
            )
            if not folder:
                raise HTTPException(
                    status_code=404,
                    detail="Account media folder not found.",
                )
            media = self._pick_account_board_media(
                root=root,
                folder=folder,
                cache={},
                exclude_path=current_path,
                use_pinned=False,
                prefer_kind=prefer_kind,
            )
            return {
                "platform": platform,
                "url": url,
                "folder_path": relative_path(root, folder),
                "media_path": media.get("path", ""),
                "media_kind": media.get("kind", ""),
                "pinned": False,
                "prefer_kind": prefer_kind,
            }

        @self.server.post(
            "/ui/api/accounts/board/pin",
            summary="Web UI 固定账号卡片媒体",
            description="将当前媒体固定为该账号的 Profile",
            tags=[_("配置")],
        )
        async def webui_accounts_board_pin(
            body: dict = Body(...),
            token: str = Depends(token_dependency),
        ):
            platform = self._normalize_board_platform(body.get("platform", "douyin"))
            url = self._normalize_string(body.get("url"))
            path = self._normalize_string(body.get("path"))
            if not url:
                raise HTTPException(
                    status_code=400,
                    detail="url is required.",
                )
            if not path:
                raise HTTPException(
                    status_code=400,
                    detail="path is required.",
                )
            root = self._scope_root("download").expanduser().resolve()
            media_path = self._coerce_media_relpath(root, path)
            if not media_path:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid media path.",
                )
            pins = self._load_account_board_pins()
            pins[self._account_pin_key(platform, url)] = media_path
            try:
                self._save_account_board_pins(pins)
            except OSError as error:
                raise HTTPException(
                    status_code=500,
                    detail=f"Save pin failed: {error}",
                )
            return {
                "message": _("固定账号卡片成功！"),
                "platform": platform,
                "url": url,
                "path": media_path,
            }

        @self.server.post(
            "/ui/api/accounts/board/pin-all",
            summary="Web UI 批量固定看板页媒体",
            description="将当前页卡片媒体批量固定为账号 Profile",
            tags=[_("配置")],
        )
        async def webui_accounts_board_pin_all(
            body: dict = Body(...),
            token: str = Depends(token_dependency),
        ):
            platform = self._normalize_board_platform(body.get("platform", "douyin"))
            raw_items = body.get("items", [])
            if not isinstance(raw_items, list):
                raise HTTPException(
                    status_code=400,
                    detail="items must be a list.",
                )
            root = self._scope_root("download").expanduser().resolve()
            pins = self._load_account_board_pins()
            updated = 0
            for item in raw_items:
                if not isinstance(item, dict):
                    continue
                url = self._normalize_string(item.get("url"))
                path = self._normalize_string(item.get("path"))
                if not url or not path:
                    continue
                media_path = self._coerce_media_relpath(root, path)
                if not media_path:
                    continue
                pins[self._account_pin_key(platform, url)] = media_path
                updated += 1
            if updated:
                try:
                    self._save_account_board_pins(pins)
                except OSError as error:
                    raise HTTPException(
                        status_code=500,
                        detail=f"Save pin failed: {error}",
                    )
            return {
                "message": _("批量固定账号卡片成功！"),
                "platform": platform,
                "updated": updated,
                "requested": len(raw_items),
            }

        @self.server.post(
            "/ui/api/accounts/board/avatar/batch",
            summary="Web UI 创建账户头像批处理任务",
            description="图片优先、无图片时视频抽帧，并使用持久任务队列处理头像",
            tags=[_("配置")],
        )
        async def webui_accounts_board_avatar_batch(
            body: dict = Body(...),
            token: str = Depends(token_dependency),
        ):
            try:
                self._validate_ui_avatar_batch_payload(body)
            except ValueError as error:
                raise HTTPException(
                    status_code=400,
                    detail=f"Payload validation failed: {error}",
                )
            task = self._enqueue_ui_task(
                "/workflow/accounts/avatar_batch",
                {
                    "platform": self._normalize_board_platform(
                        body.get("platform")
                    ),
                    "urls": [
                        self._normalize_string(item)
                        for item in body.get("urls", [])
                        if self._normalize_string(item)
                    ],
                    "skip_existing": self._normalize_bool(
                        body.get("skip_existing"),
                        default=True,
                    ),
                    "max_candidates": max(
                        1,
                        min(int(body.get("max_candidates") or 12), 30),
                    ),
                },
            )
            return {
                "message": _("账户头像任务已加入队列。"),
                "task": self._public_ui_task(task),
            }

        @self.server.post(
            "/ui/api/accounts/board/avatar/generate",
            summary="Web UI 自动生成人脸头像",
            description="使用 Mediapipe 从账号媒体中识别并生成人脸头像",
            tags=[_("配置")],
        )
        async def webui_accounts_board_avatar_generate(
            body: dict = Body(...),
            token: str = Depends(token_dependency),
        ):
            platform = self._normalize_board_platform(body.get("platform", "douyin"))
            url = self._normalize_string(body.get("url"))
            scope: ScopeType = body.get("scope", "download")
            path = self._normalize_string(body.get("path"))
            if scope not in {"project", "download"}:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid scope.",
                )
            if not url:
                raise HTTPException(
                    status_code=400,
                    detail="url is required.",
                )
            if not path:
                raise HTTPException(
                    status_code=400,
                    detail="path is required.",
                )
            row = self._find_active_account_row(platform, url)
            mark = row.get("mark", "") if isinstance(row, dict) else ""
            source_rel = self._coerce_scope_media_relpath(
                scope,
                path,
                allow_video=True,
            )
            if not source_rel:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid media path.",
                )
            source_root = self._scope_root(scope).expanduser().resolve()
            source_path = resolve_within_root(source_root, source_rel)
            output_path = self._account_avatar_output_path(
                platform=platform,
                url=url,
                mark=mark,
                extension=".jpg",
            )
            try:
                details = generate_face_avatar(
                    source_path,
                    output_path,
                )
            except RuntimeError as error:
                raise HTTPException(
                    status_code=400,
                    detail=str(error),
                )
            except OSError as error:
                raise HTTPException(
                    status_code=500,
                    detail=f"Generate avatar failed: {error}",
                )
            try:
                avatar_rel = self._set_account_avatar_path(
                    platform,
                    url,
                    relative_path(PROJECT_ROOT, output_path),
                )
            except OSError as error:
                raise HTTPException(
                    status_code=500,
                    detail=f"Save avatar map failed: {error}",
                )
            self.logger.info(
                _("已生成人脸头像: {url} -> {path}").format(
                    url=url,
                    path=avatar_rel or output_path.name,
                )
            )
            return {
                "message": _("头像生成成功！"),
                "platform": platform,
                "url": url,
                "source_scope": scope,
                "source_path": source_rel,
                "avatar_scope": "project",
                "avatar_path": avatar_rel,
                "details": details,
            }

        @self.server.post(
            "/ui/api/accounts/board/avatar/pin",
            summary="Web UI 手动设置账号头像",
            description="将指定图片文件设置为账号头像（会复制到头像目录）",
            tags=[_("配置")],
        )
        async def webui_accounts_board_avatar_pin(
            body: dict = Body(...),
            token: str = Depends(token_dependency),
        ):
            platform = self._normalize_board_platform(body.get("platform", "douyin"))
            url = self._normalize_string(body.get("url"))
            scope: ScopeType = body.get("scope", "download")
            path = self._normalize_string(body.get("path"))
            if scope not in {"project", "download"}:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid scope.",
                )
            if not url:
                raise HTTPException(
                    status_code=400,
                    detail="url is required.",
                )
            if not path:
                raise HTTPException(
                    status_code=400,
                    detail="path is required.",
                )
            row = self._find_active_account_row(platform, url)
            mark = row.get("mark", "") if isinstance(row, dict) else ""
            source_rel = self._coerce_scope_media_relpath(
                scope,
                path,
                allow_video=False,
            )
            if not source_rel:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid image path.",
                )
            source_root = self._scope_root(scope).expanduser().resolve()
            source_path = resolve_within_root(source_root, source_rel)
            extension = source_path.suffix.lower() if source_path.suffix else ".jpg"
            output_path = self._account_avatar_output_path(
                platform=platform,
                url=url,
                mark=mark,
                extension=extension if extension in IMAGE_SUFFIXES else ".jpg",
            )
            try:
                if source_path.resolve() != output_path.resolve():
                    copy2(source_path, output_path)
            except OSError as error:
                raise HTTPException(
                    status_code=500,
                    detail=f"Copy avatar failed: {error}",
                )
            try:
                avatar_rel = self._set_account_avatar_path(
                    platform,
                    url,
                    relative_path(PROJECT_ROOT, output_path),
                )
            except OSError as error:
                raise HTTPException(
                    status_code=500,
                    detail=f"Save avatar map failed: {error}",
                )
            self.logger.info(
                _("已手动设置账号头像: {url} -> {path}").format(
                    url=url,
                    path=avatar_rel or output_path.name,
                )
            )
            return {
                "message": _("头像设置成功！"),
                "platform": platform,
                "url": url,
                "avatar_scope": "project",
                "avatar_path": avatar_rel,
            }

        @self.server.get(
            "/ui/api/logs",
            summary="Web UI 日志轮询",
            description="按日志 ID 增量返回日志记录",
            tags=[_("项目")],
        )
        async def webui_logs(
            after_id: int = Query(0, ge=0),
            limit: int = Query(200, ge=1, le=1000),
            token: str = Depends(token_dependency),
        ):
            items = redact_webui_value(
                self._fetch_logs(
                    after_id=after_id,
                    limit=self._normalize_limit(limit),
                )
            )
            latest_id = after_id
            if items:
                latest_id = max(int(item.get("id", 0)) for item in items)
            return {
                "items": items,
                "after_id": after_id,
                "latest_id": latest_id,
            }

        @self.server.post(
            "/ui/api/tasks",
            summary="Web UI 创建任务",
            description="将任务加入执行队列",
            tags=[_("项目")],
        )
        async def webui_create_task(
            body: dict = Body(...),
            token: str = Depends(token_dependency),
        ):
            endpoint = body.get("endpoint", "")
            payload = body.get("payload", {})
            if not isinstance(endpoint, str) or not endpoint.startswith("/"):
                raise HTTPException(
                    status_code=400,
                    detail="Invalid endpoint.",
                )
            if endpoint not in self._supported_ui_task_endpoints():
                raise HTTPException(
                    status_code=400,
                    detail="Unsupported endpoint.",
                )
            if not isinstance(payload, dict):
                raise HTTPException(
                    status_code=400,
                    detail="Invalid payload.",
                )
            try:
                self._validate_ui_task_payload(endpoint, payload)
            except ValidationError as error:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "message": "Payload validation failed.",
                        "errors": self._safe_validation_errors(error),
                    },
                )
            except (ValueError, TypeError):
                raise HTTPException(
                    status_code=400,
                    detail="Payload validation failed.",
                )
            task = self._enqueue_ui_task(
                endpoint=endpoint,
                payload=loads(dumps(payload, ensure_ascii=False)),
            )
            return {
                "task": self._public_ui_task(task),
            }

        @self.server.get(
            "/ui/api/tasks",
            summary="Web UI 任务列表",
            description="返回任务队列及最近任务状态",
            tags=[_("项目")],
        )
        async def webui_list_tasks(
            limit: int = Query(100, ge=1, le=500),
            status: str = Query(""),
            token: str = Depends(token_dependency),
        ):
            tasks = sorted(
                (self._public_ui_task(item) for item in self.ui_tasks.values()),
                key=self._ui_task_sort_key,
                reverse=True,
            )
            if status:
                tasks = [item for item in tasks if item.get("status") == status]
            tasks = tasks[: self._normalize_limit(limit)]
            return {
                "items": tasks,
                "count": len(tasks),
                "pending": sum(1 for i in self.ui_tasks.values() if i["status"] == "pending"),
                "running": sum(
                    1
                    for i in self.ui_tasks.values()
                    if i["status"] in {"running", "pausing", "canceling"}
                ),
                "paused": sum(
                    1
                    for i in self.ui_tasks.values()
                    if i["status"] == "paused"
                ),
            }

        @self.server.get(
            "/ui/api/tasks/{task_id}",
            summary="Web UI 任务详情",
            description="返回单个任务完整状态",
            tags=[_("项目")],
        )
        async def webui_get_task(
            task_id: str,
            token: str = Depends(token_dependency),
        ):
            task = self.ui_tasks.get(task_id)
            if not task:
                raise HTTPException(status_code=404, detail="Task not found.")
            return {
                "task": self._public_ui_task(task),
            }

        @self.server.post(
            "/ui/api/tasks/{task_id}/pause",
            summary="Web UI 暂停任务",
            description="在当前账号处理完成后暂停可暂停的批量任务",
            tags=[_("项目")],
        )
        async def webui_pause_task(
            task_id: str,
            token: str = Depends(token_dependency),
        ):
            task = self.ui_tasks.get(task_id)
            if not task:
                raise HTTPException(status_code=404, detail="Task not found.")
            pause_supported = bool(
                task.get(
                    "pause_supported",
                    self._ui_task_pause_supported(task.get("endpoint", "")),
                )
            )
            if not pause_supported:
                raise HTTPException(
                    status_code=409,
                    detail="Task does not support pause.",
                )
            if task.get("status") in {"pausing", "paused"}:
                return {"task": self._public_ui_task(task)}
            if task.get("status") != "running":
                raise HTTPException(
                    status_code=409,
                    detail="Only a running task can be paused.",
                )
            pause_event = task.get("_pause_event")
            runner = task.get("_runner")
            if not isinstance(pause_event, Event) or not runner or runner.done():
                raise HTTPException(
                    status_code=409,
                    detail="Task is not available for pause.",
                )
            task["_pause_requested"] = True
            pause_event.clear()
            task["status"] = "pausing"
            task["message"] = _("正在等待当前账号处理完成后暂停…")
            task["updated_at"] = self._now_text()
            self._set_ui_task_progress_label(task, _("正在安全暂停…"))
            self._mark_ui_task_paused_if_quiescent(task)
            self._persist_ui_task(task)
            return {"task": self._public_ui_task(task)}

        @self.server.post(
            "/ui/api/tasks/{task_id}/resume",
            summary="Web UI 继续任务",
            description="从已完成的账号进度继续执行暂停的批量任务",
            tags=[_("项目")],
        )
        async def webui_resume_task(
            task_id: str,
            token: str = Depends(token_dependency),
        ):
            task = self.ui_tasks.get(task_id)
            if not task:
                raise HTTPException(status_code=404, detail="Task not found.")
            if task.get("status") == "running":
                return {"task": self._public_ui_task(task)}
            if task.get("status") not in {"pausing", "paused"}:
                raise HTTPException(
                    status_code=409,
                    detail="Only a paused task can be resumed.",
                )
            pause_event = task.get("_pause_event")
            runner = task.get("_runner")
            if (not runner or runner.done()) and task.get("status") == "paused":
                task["_pause_requested"] = False
                task["_identity_failure_notified"] = ""
                task["status"] = "pending"
                task["worker"] = None
                task["finished_at"] = None
                task["message"] = _("已重新加入队列，将从持久化进度继续")
                task["updated_at"] = self._now_text()
                self._set_ui_task_progress_label(task, _("等待恢复执行"))
                self._persist_ui_task(task)
                self.ui_task_queue.put_nowait(task_id)
                return {"task": self._public_ui_task(task)}
            if not isinstance(pause_event, Event) or not runner or runner.done():
                raise HTTPException(
                    status_code=409,
                    detail="Task is not available for resume.",
                )
            task["_pause_requested"] = False
            task["status"] = "running"
            task["message"] = _("任务已继续执行")
            task["updated_at"] = self._now_text()
            task["_identity_failure_notified"] = ""
            self._set_ui_task_progress_label(task, _("继续执行账号批次"))
            pause_event.set()
            self._persist_ui_task(task)
            return {"task": self._public_ui_task(task)}

        @self.server.post(
            "/ui/api/tasks/{task_id}/cancel",
            summary="Web UI 取消任务",
            description="取消等待中或运行中的任务",
            tags=[_("项目")],
        )
        async def webui_cancel_task(
            task_id: str,
            token: str = Depends(token_dependency),
        ):
            task = self.ui_tasks.get(task_id)
            if not task:
                raise HTTPException(status_code=404, detail="Task not found.")
            if task["status"] in {"success", "failed", "canceled"}:
                return {"task": self._public_ui_task(task)}
            if task["status"] == "pending":
                task["status"] = "canceled"
                task["message"] = _("任务已取消")
                task["finished_at"] = self._now_text()
                task["updated_at"] = self._now_text()
                self._persist_ui_task(task)
                return {"task": self._public_ui_task(task)}
            runner = task.get("_runner")
            if runner and not runner.done():
                task["status"] = "canceling"
                task["message"] = _("正在取消任务…")
                task["updated_at"] = self._now_text()
                self._persist_ui_task(task)
                runner.cancel()
            else:
                task["status"] = "canceled"
                task["message"] = _("任务已取消")
                task["finished_at"] = self._now_text()
                task["updated_at"] = self._now_text()
                self._persist_ui_task(task)
            return {"task": self._public_ui_task(task)}

        @self.server.post(
            "/ui/api/tasks/{task_id}/retry",
            summary="Web UI 重试任务",
            description="基于历史任务创建重试任务",
            tags=[_("项目")],
        )
        async def webui_retry_task(
            task_id: str,
            token: str = Depends(token_dependency),
        ):
            task = self.ui_tasks.get(task_id)
            if not task:
                raise HTTPException(status_code=404, detail="Task not found.")
            new_task = self._enqueue_ui_task(
                endpoint=task["endpoint"],
                payload=loads(dumps(task["payload"], ensure_ascii=False)),
                retry_of=task_id,
                retry_mode="full",
            )
            self._inherit_schedule_task_meta(new_task, task)
            return {"task": self._public_ui_task(new_task)}

        @self.server.post(
            "/ui/api/tasks/{task_id}/retry-failed",
            summary="Web UI 仅重试失败账号",
            description="根据账号级持久化检查点创建仅包含失败账号的新任务",
            tags=[_("项目")],
        )
        async def webui_retry_failed_task(
            task_id: str,
            category: str = Query(""),
            token: str = Depends(token_dependency),
        ):
            task = self.ui_tasks.get(task_id)
            if not task:
                raise HTTPException(status_code=404, detail="Task not found.")
            if not self._ui_task_pause_supported(task.get("endpoint", "")):
                raise HTTPException(
                    status_code=409,
                    detail="Task does not contain account checkpoints.",
                )
            journal = getattr(self, "task_journal", None)
            normalized_category = self._normalize_string(category).lower()
            if (
                normalized_category
                and normalized_category not in self.ACCOUNT_FAILURE_CATEGORIES
            ):
                raise HTTPException(status_code=400, detail="Invalid failure category.")
            failed_accounts = (
                journal.list_accounts(task_id, status="failed", limit=5000)
                if journal is not None
                else []
            )
            if normalized_category:
                failed_accounts = [
                    item
                    for item in failed_accounts
                    if self._task_account_with_category(item).get(
                        "failure_category"
                    ) == normalized_category
                ]
            failed_items = [item.get("item", {}) for item in failed_accounts]
            if not failed_items:
                raise HTTPException(
                    status_code=409,
                    detail="Task has no failed account checkpoints.",
                )
            base_payload = loads(
                dumps(task.get("payload", {}), ensure_ascii=False)
            )
            if task.get("endpoint") == "/workflow/accounts/avatar_batch":
                retry_payload = {
                    **base_payload,
                    "urls": [
                        self._normalize_string(item.get("url"))
                        for item in failed_items
                        if self._normalize_string(item.get("url"))
                    ],
                }
            else:
                retry_payload = {
                    **base_payload,
                    "use_settings": False,
                    "items": failed_items,
                }
            new_task = self._enqueue_ui_task(
                endpoint=task["endpoint"],
                payload=retry_payload,
                retry_of=task_id,
                retry_mode=(
                    f"failed_category:{normalized_category}"
                    if normalized_category
                    else "failed_only"
                ),
            )
            self._inherit_schedule_task_meta(new_task, task)
            return {"task": self._public_ui_task(new_task)}

        @self.server.get(
            "/ui/api/tasks/{task_id}/accounts",
            summary="Web UI 任务账号检查点",
            description="返回父任务下的账号级持久化执行状态",
            tags=[_("项目")],
        )
        async def webui_task_accounts(
            task_id: str,
            status: str = Query(""),
            category: str = Query(""),
            page: int = Query(1, ge=1),
            page_size: int = Query(50, ge=1, le=200),
            limit: int | None = Query(None, ge=1, le=5000),
            offset: int | None = Query(None, ge=0),
            token: str = Depends(token_dependency),
        ):
            if task_id not in self.ui_tasks:
                raise HTTPException(status_code=404, detail="Task not found.")
            if status and status not in {
                "pending",
                "running",
                "success",
                "failed",
                "skipped",
            }:
                raise HTTPException(status_code=400, detail="Invalid account status.")
            normalized_category = self._normalize_string(category).lower()
            if (
                normalized_category
                and normalized_category not in self.ACCOUNT_FAILURE_CATEGORIES
            ):
                raise HTTPException(status_code=400, detail="Invalid failure category.")
            journal = getattr(self, "task_journal", None)
            if journal is None:
                return {"items": [], "summary": {}}
            all_items = journal.list_accounts(
                task_id,
                status=status,
                limit=5000,
            )
            categorized = [self._task_account_with_category(item) for item in all_items]
            task_endpoint = self._normalize_string(
                self.ui_tasks[task_id].get("endpoint")
            ).lower()
            task_platform = "tiktok" if "/tiktok/" in task_endpoint else "douyin"
            configured_urls = {
                self._normalize_account_url(item.get("url", ""))
                for item in self._account_rows(task_platform == "tiktok")
                if self._normalize_account_url(item.get("url", ""))
            }
            for account in categorized:
                item = account.get("item")
                account_url = (
                    self._normalize_account_url(item.get("url", ""))
                    if isinstance(item, dict)
                    else ""
                )
                account["platform"] = task_platform
                account["configured"] = bool(
                    account_url and account_url in configured_urls
                )
            all_failed = journal.list_accounts(task_id, status="failed", limit=5000)
            category_counts = {
                key: 0
                for key in sorted(self.ACCOUNT_FAILURE_CATEGORIES)
            }
            for account in all_failed:
                category = self._task_account_with_category(account).get(
                    "failure_category", "other"
                )
                category_counts[category] = category_counts.get(category, 0) + 1
            if normalized_category:
                categorized = [
                    item
                    for item in categorized
                    if item.get("failure_category") == normalized_category
                ]
            if limit is not None:
                page_size = limit
                page = (max(0, int(offset or 0)) // page_size) + 1
            filtered_total = len(categorized)
            pages = max(1, (filtered_total + page_size - 1) // page_size)
            page = min(page, pages)
            start = (page - 1) * page_size
            return {
                "items": redact_webui_value(
                    categorized[start : start + page_size]
                ),
                "summary": journal.account_summary(task_id),
                "category_counts": category_counts,
                "filtered_total": filtered_total,
                "page": page,
                "page_size": page_size,
                "pages": pages,
                "status": status,
                "category": normalized_category,
            }

        @self.server.get(
            "/ui/api/tasks/{task_id}/accounts/export",
            summary="Web UI 导出失败账号 URL",
            description="按失败分类导出账号主页 URL",
            tags=[_("项目")],
        )
        async def webui_task_accounts_export(
            task_id: str,
            category: str = Query(""),
            token: str = Depends(token_dependency),
        ):
            if task_id not in self.ui_tasks:
                raise HTTPException(status_code=404, detail="Task not found.")
            normalized_category = self._normalize_string(category).lower()
            if (
                normalized_category
                and normalized_category not in self.ACCOUNT_FAILURE_CATEGORIES
            ):
                raise HTTPException(status_code=400, detail="Invalid failure category.")
            accounts = self.task_journal.list_accounts(
                task_id,
                status="failed",
                limit=5000,
            )
            urls = []
            for account in accounts:
                if normalized_category and self._task_account_with_category(
                    account
                ).get("failure_category") != normalized_category:
                    continue
                item = account.get("item") if isinstance(account.get("item"), dict) else {}
                url = self._normalize_string(item.get("url"))
                if url:
                    urls.append(url)
            return {
                "task_id": task_id,
                "category": normalized_category,
                "count": len(urls),
                "urls": urls,
            }

        @self.server.get(
            "/ui/api/schedules",
            summary="Web UI 定时任务列表",
            description="返回账号批量下载定时任务配置",
            tags=[_("项目")],
        )
        async def webui_list_schedules(
            token: str = Depends(token_dependency),
        ):
            items = [
                self._schedule_public(item)
                for item in sorted(
                    self._schedule_items_by_type(self.ACCOUNT_BATCH_SCHEDULE),
                    key=lambda item: item.get("schedule_id", ""),
                    reverse=True,
                )
            ]
            return {
                "items": items,
                "count": len(items),
            }

        @self.server.post(
            "/ui/api/schedules",
            summary="Web UI 创建定时任务",
            description="创建每日账号批量下载定时任务",
            tags=[_("项目")],
        )
        async def webui_create_schedule(
            body: dict = Body(...),
            token: str = Depends(token_dependency),
        ):
            try:
                self._validate_ui_schedule_payload(body)
                self._validate_schedule_identity_reference(body)
            except ValueError as error:
                raise HTTPException(
                    status_code=400,
                    detail=f"Payload validation failed: {error}",
                )
            body = dict(body)
            body["schedule_type"] = self.ACCOUNT_BATCH_SCHEDULE
            schedule = self._normalize_schedule_payload(body)
            schedule["schedule_id"] = self._new_schedule_id()
            self.ui_schedules[schedule["schedule_id"]] = schedule
            if schedule["enabled"]:
                self._start_single_schedule_runner(schedule["schedule_id"])
            self._persist_ui_schedules()
            return {
                "schedule": self._schedule_public(schedule),
            }

        @self.server.post(
            "/ui/api/schedules/{schedule_id}/toggle",
            summary="Web UI 切换定时任务状态",
            description="启用或停用定时任务",
            tags=[_("项目")],
        )
        async def webui_toggle_schedule(
            schedule_id: str,
            body: dict = Body(default={}),
            token: str = Depends(token_dependency),
        ):
            schedule = self._find_schedule_by_type(
                schedule_id,
                self.ACCOUNT_BATCH_SCHEDULE,
            )
            if not schedule:
                raise HTTPException(status_code=404, detail="Schedule not found.")
            enabled = body.get("enabled")
            if enabled is None:
                enabled = not schedule.get("enabled", False)
            if not isinstance(enabled, bool):
                raise HTTPException(
                    status_code=400,
                    detail="enabled must be bool.",
                )
            schedule["enabled"] = enabled
            schedule["updated_at"] = self._now_text()
            if enabled:
                schedule["next_run_at"] = self._next_run_text(
                    schedule["hour"],
                    schedule["minute"],
                )
                self._start_single_schedule_runner(schedule_id)
            else:
                schedule["next_run_at"] = ""
                await self._stop_single_schedule_runner(schedule_id)
            self._persist_ui_schedules()
            return {
                "schedule": self._schedule_public(schedule),
            }

        @self.server.post(
            "/ui/api/schedules/{schedule_id}/run",
            summary="Web UI 立即执行定时任务",
            description="将定时任务立即加入队列执行",
            tags=[_("项目")],
        )
        async def webui_run_schedule_now(
            schedule_id: str,
            token: str = Depends(token_dependency),
        ):
            schedule = self._find_schedule_by_type(
                schedule_id,
                self.ACCOUNT_BATCH_SCHEDULE,
            )
            if not schedule:
                raise HTTPException(status_code=404, detail="Schedule not found.")
            overlap_action, active_task = await self._resolve_schedule_overlap(
                schedule,
                wait_for_slot=False,
            )
            if overlap_action == "enqueue":
                task = self._create_schedule_task(schedule)
            else:
                task = active_task
            schedule["last_run_at"] = self._now_text()
            schedule["updated_at"] = self._now_text()
            schedule["next_run_at"] = self._next_run_text(
                schedule["hour"],
                schedule["minute"],
            )
            self._persist_ui_schedules()
            return {
                "schedule": self._schedule_public(schedule),
                "task": self._public_ui_task(task) if task else None,
                "overlap_action": overlap_action,
            }

        @self.server.delete(
            "/ui/api/schedules/{schedule_id}",
            summary="Web UI 删除定时任务",
            description="删除定时任务配置",
            tags=[_("项目")],
        )
        async def webui_delete_schedule(
            schedule_id: str,
            token: str = Depends(token_dependency),
        ):
            schedule = self._find_schedule_by_type(
                schedule_id,
                self.ACCOUNT_BATCH_SCHEDULE,
            )
            if not schedule:
                raise HTTPException(status_code=404, detail="Schedule not found.")
            self.ui_schedules.pop(schedule_id, None)
            await self._stop_single_schedule_runner(schedule_id)
            self._persist_ui_schedules()
            return {
                "message": _("删除定时任务成功！"),
                "schedule_id": schedule_id,
            }

        @self.server.get(
            "/ui/api/collect-monitors",
            summary="Web UI 收藏夹监控列表",
            description="返回收藏夹监控配置与状态",
            tags=[_("项目")],
        )
        async def webui_list_collect_monitors(
            token: str = Depends(token_dependency),
        ):
            items = [
                self._schedule_public(item)
                for item in sorted(
                    self._schedule_items_by_type(self.COLLECT_MONITOR_SCHEDULE),
                    key=lambda item: item.get("schedule_id", ""),
                    reverse=True,
                )
            ]
            return {
                "items": items,
                "count": len(items),
            }

        @self.server.post(
            "/ui/api/collect-monitors",
            summary="Web UI 创建收藏夹监控",
            description="创建基于 collect_id 的定时监控任务",
            tags=[_("项目")],
        )
        async def webui_create_collect_monitor(
            body: dict = Body(...),
            token: str = Depends(token_dependency),
        ):
            try:
                self._validate_collect_monitor_payload(body)
                self._validate_schedule_identity_reference(
                    {**body, "platform": "douyin"}
                )
            except ValueError as error:
                raise HTTPException(
                    status_code=400,
                    detail=f"Payload validation failed: {error}",
                )
            payload = dict(body)
            payload["schedule_type"] = self.COLLECT_MONITOR_SCHEDULE
            schedule = self._normalize_schedule_payload(payload)
            schedule["schedule_id"] = self._new_schedule_id()
            self.ui_schedules[schedule["schedule_id"]] = schedule
            if schedule["enabled"]:
                self._start_single_schedule_runner(schedule["schedule_id"])
            self._persist_ui_schedules()
            return {
                "monitor": self._schedule_public(schedule),
            }

        @self.server.post(
            "/ui/api/collect-monitors/{schedule_id}/toggle",
            summary="Web UI 切换收藏夹监控状态",
            description="启用或停用收藏夹监控任务",
            tags=[_("项目")],
        )
        async def webui_toggle_collect_monitor(
            schedule_id: str,
            body: dict = Body(default={}),
            token: str = Depends(token_dependency),
        ):
            schedule = self._find_schedule_by_type(
                schedule_id,
                self.COLLECT_MONITOR_SCHEDULE,
            )
            if not schedule:
                raise HTTPException(status_code=404, detail="Monitor not found.")
            enabled = body.get("enabled")
            if enabled is None:
                enabled = not schedule.get("enabled", False)
            if not isinstance(enabled, bool):
                raise HTTPException(status_code=400, detail="enabled must be bool.")
            schedule["enabled"] = enabled
            schedule["updated_at"] = self._now_text()
            if enabled:
                schedule["next_run_at"] = self._next_interval_run_text(
                    self._normalize_collect_interval(
                        schedule.get("interval_minutes"),
                        default=30,
                    )
                )
                self._start_single_schedule_runner(schedule_id)
            else:
                schedule["next_run_at"] = ""
                await self._stop_single_schedule_runner(schedule_id)
            self._persist_ui_schedules()
            return {
                "monitor": self._schedule_public(schedule),
            }

        @self.server.post(
            "/ui/api/collect-monitors/{schedule_id}/run",
            summary="Web UI 立即执行收藏夹监控",
            description="立刻执行一次收藏夹监控并返回结果",
            tags=[_("项目")],
        )
        async def webui_run_collect_monitor_now(
            schedule_id: str,
            token: str = Depends(token_dependency),
        ):
            schedule = self._find_schedule_by_type(
                schedule_id,
                self.COLLECT_MONITOR_SCHEDULE,
            )
            if not schedule:
                raise HTTPException(status_code=404, detail="Monitor not found.")
            try:
                result = await self._run_collect_monitor_once(schedule)
            except Exception as error:  # noqa: BLE001
                result = self._collect_monitor_failure_result(schedule, error)
            schedule["last_result"] = result
            schedule["last_run_at"] = self._now_text()
            schedule["updated_at"] = self._now_text()
            if schedule.get("enabled", False):
                schedule["next_run_at"] = self._next_interval_run_text(
                    self._normalize_collect_interval(
                        schedule.get("interval_minutes"),
                        default=30,
                    )
                )
            else:
                schedule["next_run_at"] = ""
            await self._notify_collect_monitor(
                schedule=schedule,
                success=bool(result.get("ok", False)),
                summary=result,
                error_text=self._normalize_string(result.get("error")),
            )
            self._persist_ui_schedules()
            return {
                "monitor": self._schedule_public(schedule),
                "result": redact_webui_value(result),
            }

        @self.server.delete(
            "/ui/api/collect-monitors/{schedule_id}",
            summary="Web UI 删除收藏夹监控",
            description="删除收藏夹监控配置",
            tags=[_("项目")],
        )
        async def webui_delete_collect_monitor(
            schedule_id: str,
            token: str = Depends(token_dependency),
        ):
            schedule = self._find_schedule_by_type(
                schedule_id,
                self.COLLECT_MONITOR_SCHEDULE,
            )
            if not schedule:
                raise HTTPException(status_code=404, detail="Monitor not found.")
            self.ui_schedules.pop(schedule_id, None)
            await self._stop_single_schedule_runner(schedule_id)
            self._persist_ui_schedules()
            return {
                "message": _("删除收藏夹监控成功！"),
                "schedule_id": schedule_id,
            }

        @self.server.websocket("/ui/ws/logs")
        async def webui_logs_ws(websocket: WebSocket):
            token = (
                websocket.headers.get("token")
                or websocket.cookies.get(WEBUI_SESSION_COOKIE)
            )
            client_host = websocket.client.host if websocket.client else ""
            if not is_valid_token(token, client_host):
                await websocket.close(
                    code=4403,
                    reason=_("验证失败！"),
                )
                return
            await websocket.accept()
            raw_after = websocket.query_params.get("after_id", "0")
            try:
                cursor = max(int(raw_after), 0)
            except ValueError:
                cursor = 0
            try:
                while True:
                    items = redact_webui_value(
                        self._fetch_logs(
                            after_id=cursor,
                            limit=500,
                        )
                    )
                    if items:
                        cursor = max(
                            cursor,
                            max(int(item.get("id", 0)) for item in items),
                        )
                        await websocket.send_json(
                            {
                                "type": "logs",
                                "items": items,
                                "latest_id": cursor,
                            }
                        )
                    await sleep(1)
            except WebSocketDisconnect:
                return

        @self.server.get(
            "/",
            summary=_("访问 Web UI 首页"),
            description=_("重定向至 Web UI 交互界面"),
            tags=[_("项目")],
        )
        async def index():
            return RedirectResponse(url="/ui")

        @self.server.get(
            "/token",
            summary=_("测试令牌有效性"),
            description=_(
                dedent("""
                项目默认无需令牌；公开部署时，建议设置令牌以防止恶意请求！
                
                令牌设置位置：`src/custom/function.py` - `is_valid_token()`
                """)
            ),
            tags=[_("项目")],
            response_model=DataResponse,
        )
        async def handle_test(
            request: Request,
            response: Response,
            token: str = Depends(token_dependency),
        ):
            response.set_cookie(
                key=WEBUI_SESSION_COOKIE,
                value=token,
                max_age=WEBUI_SESSION_MAX_AGE,
                httponly=True,
                secure=request.url.scheme == "https",
                samesite="strict",
                path="/ui",
            )
            return DataResponse(
                message=_("验证成功！"),
                data=None,
                params=None,
            )

        @self.server.delete(
            "/ui/api/session",
            summary="清除 Web UI 浏览器会话",
            description="清除当前浏览器保存的 HttpOnly WebUI 会话 Cookie",
            tags=[_("项目")],
        )
        async def clear_webui_session():
            response = JSONResponse(
                content={"message": _("Web UI 会话已清除！")},
            )
            response.delete_cookie(
                key=WEBUI_SESSION_COOKIE,
                path="/ui",
                httponly=True,
                samesite="strict",
            )
            return response

        @self.server.post(
            "/settings",
            summary=_("更新项目全局配置"),
            description=_(
                dedent("""
                更新项目配置文件 settings.json
                
                仅需传入需要更新的配置参数
                
                返回更新后的全部配置参数
                """)
            ),
            tags=[_("配置")],
            response_model=Settings,
        )
        async def handle_settings(
            extract: Settings, token: str = Depends(token_dependency)
        ):
            current = self.parameter.get_settings_data()
            incoming = extract.model_dump()
            for key in ("cookie", "cookie_tiktok", "proxy", "proxy_tiktok"):
                if key not in extract.model_fields_set:
                    incoming[key] = current.get(key)
            incoming = restore_redacted_values(incoming, current)
            await self.parameter.set_settings_data(incoming)
            self._sync_runtime_http_clients()
            return Settings(
                **self._public_settings(self.parameter.get_settings_data())
            )

        @self.server.get(
            "/settings",
            summary=_("获取项目全局配置"),
            description=_("返回项目全部配置参数"),
            tags=[_("配置")],
            response_model=Settings,
        )
        async def get_settings(token: str = Depends(token_dependency)):
            return Settings(
                **self._public_settings(self.parameter.get_settings_data())
            )

        @self.server.post(
            "/douyin/share",
            summary=_("获取分享链接重定向的完整链接"),
            description=_(
                dedent("""
                **参数**:
                
                - **text**: 包含分享链接的字符串；必需参数
                - **proxy**: 代理；可选参数
                """)
            ),
            tags=[_("抖音")],
            response_model=UrlResponse,
        )
        async def handle_share(
            extract: ShortUrl, token: str = Depends(token_dependency)
        ):
            if url := await self.handle_redirect(extract.text, extract.proxy):
                return UrlResponse(
                    message=_("请求链接成功！"),
                    url=url,
                    params=redact_webui_value(extract.model_dump()),
                )
            return UrlResponse(
                message=_("请求链接失败！"),
                url=None,
                params=redact_webui_value(extract.model_dump()),
            )

        @self.server.post(
            "/douyin/detail",
            summary=_("获取单个作品数据"),
            description=_(
                dedent("""
                **参数**:
                
                - **cookie**: 抖音 Cookie；可选参数
                - **proxy**: 代理；可选参数
                - **source**: 是否返回原始响应数据；可选参数，默认值：False
                - **detail_id**: 抖音作品 ID；必需参数
                """)
            ),
            tags=[_("抖音")],
            response_model=DataResponse,
        )
        async def handle_detail(
            extract: Detail, token: str = Depends(token_dependency)
        ):
            return await self.handle_detail(extract, False)

        @self.server.post(
            "/douyin/account",
            summary=_("获取账号作品数据"),
            description=_(
                dedent("""
                **参数**:
                
                - **cookie**: 抖音 Cookie；可选参数
                - **proxy**: 代理；可选参数
                - **source**: 是否返回原始响应数据；可选参数，默认值：False
                - **sec_user_id**: 抖音账号 sec_uid；必需参数
                - **tab**: 账号页面类型；可选参数，默认值：`post`
                - **earliest**: 作品最早发布日期；可选参数
                - **latest**: 作品最晚发布日期；可选参数
                - **pages**: 最大请求次数，仅对请求账号喜欢页数据有效；可选参数
                - **cursor**: 可选参数
                - **count**: 可选参数
                """)
            ),
            tags=[_("抖音")],
            response_model=DataResponse,
        )
        async def handle_account(
            extract: Account, token: str = Depends(token_dependency)
        ):
            return await self.handle_account(extract, False)

        @self.server.post(
            "/douyin/mix",
            summary=_("获取合集作品数据"),
            description=_(
                dedent("""
                **参数**:
                
                - **cookie**: 抖音 Cookie；可选参数
                - **proxy**: 代理；可选参数
                - **source**: 是否返回原始响应数据；可选参数，默认值：False
                - **mix_id**: 抖音合集 ID
                - **detail_id**: 属于合集的抖音作品 ID
                - **cursor**: 可选参数
                - **count**: 可选参数
                
                **`mix_id` 和 `detail_id` 二选一，只需传入其中之一即可**
                """)
            ),
            tags=[_("抖音")],
            response_model=DataResponse,
        )
        async def handle_mix(extract: Mix, token: str = Depends(token_dependency)):
            return await self._handle_mix_request(extract, False)

        @self.server.post(
            "/douyin/live",
            summary=_("获取直播数据"),
            description=_(
                dedent("""
                **参数**:
                
                - **cookie**: 抖音 Cookie；可选参数
                - **proxy**: 代理；可选参数
                - **source**: 是否返回原始响应数据；可选参数，默认值：False
                - **web_rid**: 抖音直播 web_rid
                """)
            ),
            tags=[_("抖音")],
            response_model=DataResponse,
        )
        async def handle_live(extract: Live, token: str = Depends(token_dependency)):
            # if self.check_live_params(
            #     extract.web_rid,
            #     extract.room_id,
            #     extract.sec_user_id,
            # ):
            #     if data := await self.handle_live(
            #         extract,
            #     ):
            #         return self.success_response(extract, data[0])
            #     return self.failed_response(extract)
            # return DataResponse(
            #     message=_("参数错误！"),
            #     data=None,
            #     params=extract.model_dump(),
            # )
            return await self._handle_live_request(extract, False)

        @self.server.post(
            "/douyin/comment",
            summary=_("获取作品评论数据"),
            description=_(
                dedent("""
                **参数**:
                
                - **cookie**: 抖音 Cookie；可选参数
                - **proxy**: 代理；可选参数
                - **source**: 是否返回原始响应数据；可选参数，默认值：False
                - **detail_id**: 抖音作品 ID；必需参数
                - **pages**: 最大请求次数；可选参数
                - **cursor**: 可选参数
                - **count**: 可选参数
                - **count_reply**: 可选参数
                - **reply**: 可选参数，默认值：False
                """)
            ),
            tags=[_("抖音")],
            response_model=DataResponse,
        )
        async def handle_comment(
            extract: Comment, token: str = Depends(token_dependency)
        ):
            return await self._handle_comment_request(extract)

        @self.server.post(
            "/douyin/reply",
            summary=_("获取评论回复数据"),
            description=_(
                dedent("""
                **参数**:
                
                - **cookie**: 抖音 Cookie；可选参数
                - **proxy**: 代理；可选参数
                - **source**: 是否返回原始响应数据；可选参数，默认值：False
                - **detail_id**: 抖音作品 ID；必需参数
                - **comment_id**: 评论 ID；必需参数
                - **pages**: 最大请求次数；可选参数
                - **cursor**: 可选参数
                - **count**: 可选参数
                """)
            ),
            tags=[_("抖音")],
            response_model=DataResponse,
        )
        async def handle_reply(extract: Reply, token: str = Depends(token_dependency)):
            return await self._handle_reply_request(extract)

        @self.server.post(
            "/douyin/search/general",
            summary=_("获取综合搜索数据"),
            description=_(
                dedent("""
                **参数**:
                
                - **cookie**: 抖音 Cookie；可选参数
                - **proxy**: 代理；可选参数
                - **source**: 是否返回原始响应数据；可选参数，默认值：False
                - **keyword**: 关键词；必需参数
                - **offset**: 起始页码；可选参数
                - **count**: 数据数量；可选参数
                - **pages**: 总页数；可选参数
                - **sort_type**: 排序依据；可选参数
                - **publish_time**: 发布时间；可选参数
                - **duration**: 视频时长；可选参数
                - **search_range**: 搜索范围；可选参数
                - **content_type**: 内容形式；可选参数
                
                **部分参数传入规则请查阅文档**: [参数含义](https://github.com/JoeanAmier/TikTokDownloader/wiki/Documentation#%E9%87%87%E9%9B%86%E6%90%9C%E7%B4%A2%E7%BB%93%E6%9E%9C%E6%95%B0%E6%8D%AE%E6%8A%96%E9%9F%B3)
                """)
            ),
            tags=[_("抖音")],
            response_model=DataResponse,
        )
        async def handle_search_general(
            extract: GeneralSearch, token: str = Depends(token_dependency)
        ):
            return await self.handle_search(extract)

        @self.server.post(
            "/douyin/search/video",
            summary=_("获取视频搜索数据"),
            description=_(
                dedent("""
                **参数**:
                
                - **cookie**: 抖音 Cookie；可选参数
                - **proxy**: 代理；可选参数
                - **source**: 是否返回原始响应数据；可选参数，默认值：False
                - **keyword**: 关键词；必需参数
                - **offset**: 起始页码；可选参数
                - **count**: 数据数量；可选参数
                - **pages**: 总页数；可选参数
                - **sort_type**: 排序依据；可选参数
                - **publish_time**: 发布时间；可选参数
                - **duration**: 视频时长；可选参数
                - **search_range**: 搜索范围；可选参数
                
                **部分参数传入规则请查阅文档**: [参数含义](https://github.com/JoeanAmier/TikTokDownloader/wiki/Documentation#%E9%87%87%E9%9B%86%E6%90%9C%E7%B4%A2%E7%BB%93%E6%9E%9C%E6%95%B0%E6%8D%AE%E6%8A%96%E9%9F%B3)
                """)
            ),
            tags=[_("抖音")],
            response_model=DataResponse,
        )
        async def handle_search_video(
            extract: VideoSearch, token: str = Depends(token_dependency)
        ):
            return await self.handle_search(extract)

        @self.server.post(
            "/douyin/search/user",
            summary=_("获取用户搜索数据"),
            description=_(
                dedent("""
                **参数**:
                
                - **cookie**: 抖音 Cookie；可选参数
                - **proxy**: 代理；可选参数
                - **source**: 是否返回原始响应数据；可选参数，默认值：False
                - **keyword**: 关键词；必需参数
                - **offset**: 起始页码；可选参数
                - **count**: 数据数量；可选参数
                - **pages**: 总页数；可选参数
                - **douyin_user_fans**: 粉丝数量；可选参数
                - **douyin_user_type**: 用户类型；可选参数
                
                **部分参数传入规则请查阅文档**: [参数含义](https://github.com/JoeanAmier/TikTokDownloader/wiki/Documentation#%E9%87%87%E9%9B%86%E6%90%9C%E7%B4%A2%E7%BB%93%E6%9E%9C%E6%95%B0%E6%8D%AE%E6%8A%96%E9%9F%B3)
                """)
            ),
            tags=[_("抖音")],
            response_model=DataResponse,
        )
        async def handle_search_user(
            extract: UserSearch, token: str = Depends(token_dependency)
        ):
            return await self.handle_search(extract)

        @self.server.post(
            "/douyin/search/live",
            summary=_("获取直播搜索数据"),
            description=_(
                dedent("""
                **参数**:
                
                - **cookie**: 抖音 Cookie；可选参数
                - **proxy**: 代理；可选参数
                - **source**: 是否返回原始响应数据；可选参数，默认值：False
                - **keyword**: 关键词；必需参数
                - **offset**: 起始页码；可选参数
                - **count**: 数据数量；可选参数
                - **pages**: 总页数；可选参数
                """)
            ),
            tags=[_("抖音")],
            response_model=DataResponse,
        )
        async def handle_search_live(
            extract: LiveSearch, token: str = Depends(token_dependency)
        ):
            return await self.handle_search(extract)

        @self.server.post(
            "/tiktok/share",
            summary=_("获取分享链接重定向的完整链接"),
            description=_(
                dedent("""
            **参数**:

            - **text**: 包含分享链接的字符串；必需参数
            - **proxy**: 代理；可选参数
            """)
            ),
            tags=["TikTok"],
            response_model=UrlResponse,
        )
        async def handle_share_tiktok(
            extract: ShortUrl, token: str = Depends(token_dependency)
        ):
            if url := await self.handle_redirect_tiktok(extract.text, extract.proxy):
                return UrlResponse(
                    message=_("请求链接成功！"),
                    url=url,
                    params=redact_webui_value(extract.model_dump()),
                )
            return UrlResponse(
                message=_("请求链接失败！"),
                url=None,
                params=redact_webui_value(extract.model_dump()),
            )

        @self.server.post(
            "/tiktok/detail",
            summary=_("获取单个作品数据"),
            description=_(
                dedent("""
                **参数**:

                - **cookie**: TikTok Cookie；可选参数
                - **proxy**: 代理；可选参数
                - **source**: 是否返回原始响应数据；可选参数，默认值：False
                - **detail_id**: TikTok 作品 ID；可选参数
                - **detail_url**: TikTok 作品完整链接；可选参数

                **推荐优先传入 `detail_url`，`detail_id` 和 `detail_url` 二选一即可**
                """)
            ),
            tags=["TikTok"],
            response_model=DataResponse,
        )
        async def handle_detail_tiktok(
            extract: DetailTikTok, token: str = Depends(token_dependency)
        ):
            return await self.handle_detail(extract, True)

        @self.server.post(
            "/tiktok/account",
            summary=_("获取账号作品数据"),
            description=_(
                dedent("""
                **参数**:

                - **cookie**: TikTok Cookie；可选参数
                - **proxy**: 代理；可选参数
                - **source**: 是否返回原始响应数据；可选参数，默认值：False
                - **sec_user_id**: TikTok 账号 secUid；必需参数
                - **tab**: 账号页面类型；可选参数，默认值：`post`
                - **earliest**: 作品最早发布日期；可选参数
                - **latest**: 作品最晚发布日期；可选参数
                - **pages**: 最大请求次数，仅对请求账号喜欢页数据有效；可选参数
                - **cursor**: 可选参数
                - **count**: 可选参数
                """)
            ),
            tags=["TikTok"],
            response_model=DataResponse,
        )
        async def handle_account_tiktok(
            extract: AccountTiktok, token: str = Depends(token_dependency)
        ):
            return await self.handle_account(extract, True)

        @self.server.post(
            "/tiktok/mix",
            summary=_("获取合辑作品数据"),
            description=_(
                dedent("""
                **参数**:

                - **cookie**: TikTok Cookie；可选参数
                - **proxy**: 代理；可选参数
                - **source**: 是否返回原始响应数据；可选参数，默认值：False
                - **mix_id**: TikTok 合集 ID；必需参数
                - **cursor**: 可选参数
                - **count**: 可选参数
                """)
            ),
            tags=["TikTok"],
            response_model=DataResponse,
        )
        async def handle_mix_tiktok(
            extract: MixTikTok, token: str = Depends(token_dependency)
        ):
            return await self._handle_mix_request(extract, True)

        @self.server.post(
            "/tiktok/live",
            summary=_("获取直播数据"),
            description=_(
                dedent("""
                **参数**:

                - **cookie**: TikTok Cookie；可选参数
                - **proxy**: 代理；可选参数
                - **source**: 是否返回原始响应数据；可选参数，默认值：False
                - **room_id**: TikTok 直播 room_id；必需参数
                """)
            ),
            tags=["TikTok"],
            response_model=DataResponse,
        )
        async def handle_live_tiktok(
            extract: LiveTikTok, token: str = Depends(token_dependency)
        ):
            return await self._handle_live_request(extract, True)
