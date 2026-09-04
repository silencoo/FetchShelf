from asyncio import (
    Event,
    Queue,
    CancelledError,
    create_task,
    gather,
    sleep,
    to_thread,
)
from datetime import datetime, timedelta
from hashlib import md5
from json import JSONDecodeError, dumps, loads
from pathlib import Path
from random import choice
from re import compile, sub
from shutil import copy2, disk_usage
from sqlite3 import connect as sqlite_connect
from tempfile import TemporaryDirectory
from threading import Lock, Thread
from time import monotonic
from typing import TYPE_CHECKING, Any, Callable
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import (
    FastAPI,
    HTTPException,
)
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from uvicorn import Config, Server

from ..custom import (
    __VERSION__,
    PROJECT_ROOT,
    SERVER_HOST,
    SERVER_PORT,
    VERSION_BETA,
)
from ..collector import (
    AESGCMSecretCodec,
    AssignmentSource,
    BindingFailureMode,
    CollectorAuthMode,
    CollectorAssignment,
    CollectorCredentials,
    DouyinBrowserCollectionError,
    CollectorIdentity,
    CollectorLoginBrowserManager,
    CollectorPlatform,
    CollectorStore,
    IdentityInUseError,
    IdentityLeaseManager,
    IdentityNotFoundError,
    IdentityPlatformError,
    IdentityStatus,
    LeaseConfigurationError,
    LoginBrowserBusyError,
    LoginBrowserDependencyError,
    LoginBrowserError,
    LoginBrowserNotAuthenticatedError,
    LoginBrowserNotFoundError,
    RouteTarget,
    RouteUnavailable,
    RoutingStrategy,
    SecretCodecError,
    SecretCodecUnavailable,
    UnavailableSecretCodec,
    build_collector_runtime,
    candidate_available,
    fetch_douyin_collection_via_browser,
    migrate_legacy_settings,
    plan_routes,
)
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
    UserSearch,
    VideoSearch,
)
from ..tools import create_client, cookie_dict_to_str
from ..interface import CollectsDetail
from ..translation import _
from ..webui_security import (
    WEBUI_SENSITIVE_FIELDS,
    is_protected_project_path,
    redact_webui_value,
)
from ..webui.files import (
    IMAGE_SUFFIXES,
    ScopeType,
    VIDEO_SUFFIXES,
    relative_path,
    resolve_within_root,
    serialize_entry,
)
from ..webui.account_backfill import attach_settings_index_by_url
from ..webui.profile_avatar import generate_face_avatar
from ..webui.task_journal import ACTIVE_TASK_STATUSES, TaskJournal
from .main_terminal import TikTok
from .server_routes import (
    ServerRoutesMixin,
    WEBUI_SESSION_COOKIE,
    WEBUI_SESSION_MAX_AGE,
    token_dependency,
)

try:
    from ..webui.log_store import LOG_STORE
except Exception:
    class _FallbackLogStore:
        @staticmethod
        def latest(limit: int = 200):
            return []

        @staticmethod
        def list_after(after_id: int = 0, limit: int = 200):
            return []

    LOG_STORE = _FallbackLogStore()

if TYPE_CHECKING:
    from ..config import Parameter
    from ..manager import Database

__all__ = ["APIServer"]


WORK_FILENAME_DATE_PATTERN = compile(
    r"(?<!\d)(20\d{2})[-_.](\d{2})[-_.](\d{2})"
    r"(?:[ T_.-](\d{2})[.:-](\d{2})[.:-](\d{2}))?"
)


class APIServer(TikTok, ServerRoutesMixin):
    WEBUI_STATIC_DIR = Path(__file__).resolve().parent.parent.joinpath(
        "webui",
        "static",
    )
    DELETED_ACCOUNT_HINTS = (
        "已注销",
        "注销账号",
        "账号已注销",
        "account not found",
        "user not found",
        "account has been deleted",
    )
    ACCOUNT_BATCH_SCHEDULE = "account_batch"
    COLLECT_MONITOR_SCHEDULE = "collect_monitor"
    SCHEDULE_OVERLAP_POLICIES = frozenset({"wait", "skip", "allow"})
    IDENTITY_FAILURE_ACTIONS = frozenset({"continue", "pause"})
    COLLECT_MONITOR_PAGE_COUNT = 20
    COLLECT_MONITOR_MAX_PAGES = 30
    # A scheduled Douyin account crawl may contain thousands of accounts.  Do
    # not retain the only identity/platform lease for the entire run: releasing
    # it between bounded chunks lets a queued collection monitor run without
    # increasing cookie concurrency.  TikTok batches keep one runtime because
    # anonymous runtime preparation launches a browser session and Douyin is
    # currently the only platform with a collection-monitor schedule.
    DOUYIN_ACCOUNT_LEASE_CHUNK_SIZE = 10
    OVERVIEW_MEDIA_CACHE_TTL_SECONDS = 300
    STORAGE_ALERT_THRESHOLDS = (75, 85, 95)
    CONFIGURATION_SNAPSHOT_RETENTION = 14
    UI_TASK_SENSITIVE_FIELDS = WEBUI_SENSITIVE_FIELDS
    ACCOUNT_FAILURE_CATEGORIES = frozenset(
        {
            "identity",
            "visibility",
            "account_unavailable",
            "network",
            "download",
            "parse",
            "other",
        }
    )

    def __init__(
        self,
        parameter: "Parameter",
        database: "Database",
        server_mode: bool = True,
    ):
        super().__init__(
            parameter,
            database,
            server_mode,
        )
        self.server = None
        self.ui_task_queue: Queue[str] = Queue()
        self.ui_task_workers = []
        self.ui_tasks: dict[str, dict] = {}
        self.ui_task_counter = 0
        self.ui_tasks_restored = False
        self.ui_task_shutdown = False
        self.ui_schedules: dict[str, dict] = {}
        self.ui_schedule_tasks: dict[str, Any] = {}
        self.ui_schedule_counter = 0
        self.collector_vault_error = ""
        try:
            collector_codec = AESGCMSecretCodec.from_environment()
        except (SecretCodecError, SecretCodecUnavailable) as error:
            collector_codec = UnavailableSecretCodec()
            self.collector_vault_error = str(error)
        self.collector_store = CollectorStore.in_settings_dir(
            self.parameter.settings.path.parent,
            codec=collector_codec,
        )
        self.collector_login_browser = CollectorLoginBrowserManager(
            self.parameter.settings.path.parent,
        )
        self.task_journal = TaskJournal.in_settings_dir(
            self.parameter.settings.path.parent,
        )
        self.collector_leases = IdentityLeaseManager()
        self._overview_media_lock = Lock()
        self._overview_media_cache: dict[str, Any] = {}
        self._overview_media_cache_updated_monotonic = 0.0
        self._overview_media_scan_attempt_monotonic = 0.0
        self._overview_media_scan_started_at = ""
        self._overview_media_scan_error = ""
        self._overview_media_scan_thread: Thread | None = None
        self._maintenance_lock = Lock()
        self._storage_alert_pending_level = 0
        self._storage_alert_last_level = 0
        self._initialize_legacy_collectors()

    @staticmethod
    def _now_text() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _new_task_id(self) -> str:
        self.ui_task_counter += 1
        return f"T{self.ui_task_counter:06d}"

    def _refresh_task_counter(self) -> None:
        max_id = 0
        for key in self.ui_tasks:
            try:
                max_id = max(max_id, int(str(key).lstrip("T")))
            except ValueError:
                continue
        self.ui_task_counter = max_id

    def _new_schedule_id(self) -> str:
        self.ui_schedule_counter += 1
        return f"S{self.ui_schedule_counter:06d}"

    @staticmethod
    def _collector_timestamp() -> str:
        return datetime.now().astimezone().isoformat(timespec="seconds")

    @staticmethod
    def _collector_platform(value: Any) -> CollectorPlatform:
        try:
            return CollectorPlatform(str(value or "").strip().lower())
        except ValueError as error:
            raise HTTPException(
                status_code=400,
                detail="platform must be douyin or tiktok.",
            ) from error

    def _initialize_legacy_collectors(self) -> None:
        migration = migrate_legacy_settings(self.parameter.get_settings_data())
        if not migration.migrated:
            return
        existing = {
            item.identity_id: item
            for item in self.collector_store.list_public()
        }
        if not existing:
            # Persist non-secret metadata even when the vault is locked. Legacy
            # settings remain the execution fallback until a key is supplied.
            for identity in migration.identities:
                self.collector_store.upsert_identity(identity)
            for policy in migration.policies:
                self.collector_store.upsert_policy(policy)
            existing = {
                item.identity_id: item
                for item in self.collector_store.list_public()
            }
        if self.collector_vault_error:
            return
        for identity_id, credentials in migration.credentials.items():
            public = existing.get(identity_id)
            if public and credentials.configured and not public.credential_configured:
                self.collector_store.write_credentials(identity_id, credentials)

    async def _configure_collector_leases(self) -> None:
        for identity in self.collector_store.list_identities():
            await self.collector_leases.configure(
                identity.identity_id,
                identity.max_concurrency,
            )
        for platform in CollectorPlatform:
            policy = self.collector_store.get_policy(platform)
            await self.collector_leases.configure(
                f"platform:{platform.value}",
                policy.global_max_parallel,
            )

    @staticmethod
    def _collector_public_data(value) -> dict:
        return value.model_dump(mode="json")

    def _get_collector_login_browser(self) -> CollectorLoginBrowserManager:
        manager = getattr(self, "collector_login_browser", None)
        if manager is None:
            settings_path = getattr(
                getattr(self, "parameter", None),
                "settings",
                None,
            )
            settings_path = getattr(
                settings_path,
                "path",
                PROJECT_ROOT.joinpath("settings.json"),
            )
            manager = CollectorLoginBrowserManager(Path(settings_path).parent)
            self.collector_login_browser = manager
        return manager

    def _collector_identity_public_data(self, value) -> dict:
        data = self._collector_public_data(value)
        manager = getattr(self, "collector_login_browser", None)
        data["login_browser_active"] = bool(
            manager and manager.is_identity_locked(value.identity_id)
        )
        return data

    def _collector_identity_login_locked(self, identity_id: str) -> bool:
        manager = getattr(self, "collector_login_browser", None)
        return bool(manager and manager.is_identity_locked(identity_id))

    @staticmethod
    def _collector_login_browser_http_error(error: Exception) -> HTTPException:
        if isinstance(error, LoginBrowserDependencyError):
            return HTTPException(status_code=503, detail=str(error))
        if isinstance(error, LoginBrowserNotFoundError):
            return HTTPException(status_code=404, detail=str(error))
        if isinstance(
            error,
            (LoginBrowserBusyError, LoginBrowserNotAuthenticatedError),
        ):
            return HTTPException(status_code=409, detail=str(error))
        if isinstance(error, LoginBrowserError):
            return HTTPException(status_code=400, detail=str(error))
        return APIServer._collector_http_error(error)

    @staticmethod
    def _safe_validation_errors(error: ValidationError | RequestValidationError) -> list[dict]:
        return [
            {
                "type": item.get("type", "validation_error"),
                "loc": item.get("loc", ()),
                "msg": item.get("msg", "Invalid value."),
            }
            for item in error.errors()
        ]

    @staticmethod
    def _collector_http_error(error: Exception) -> HTTPException:
        if isinstance(error, IdentityNotFoundError):
            return HTTPException(status_code=404, detail=str(error))
        if isinstance(error, IdentityInUseError):
            return HTTPException(status_code=409, detail=str(error))
        if isinstance(error, (IdentityPlatformError, LeaseConfigurationError)):
            return HTTPException(status_code=409, detail=str(error))
        if isinstance(error, (SecretCodecError, SecretCodecUnavailable)):
            return HTTPException(
                status_code=423,
                detail=(
                    "Collector credential vault is locked. Configure "
                    "FETCHSHELF_IDENTITY_KEY_FILE or FETCHSHELF_IDENTITY_KEY."
                ),
            )
        if isinstance(error, ValidationError):
            # Pydantic's default error payload contains ``input`` values, which
            # may be a Cookie, authenticated proxy URL, or browser fingerprint.
            # Keep the useful field path while never echoing submitted secrets.
            details = APIServer._safe_validation_errors(error)
            return HTTPException(status_code=422, detail=details)
        return HTTPException(
            status_code=400,
            detail="Collector request failed.",
        )

    def _collector_identity_from_body(
        self,
        body: dict,
        *,
        current: CollectorIdentity | None = None,
    ) -> CollectorIdentity:
        data = current.model_dump(mode="json") if current else {}
        for key in (
            "identity_id",
            "name",
            "platform",
            "auth_mode",
            "enabled",
            "weight",
            "request_delay",
            "max_concurrency",
        ):
            if key in body:
                data[key] = body[key]
        if current:
            data["identity_id"] = current.identity_id
            data["platform"] = current.platform.value
        else:
            data["identity_id"] = self._normalize_string(
                data.get("identity_id")
            ) or f"ci_{uuid4().hex[:16]}"
        return CollectorIdentity.model_validate(data)

    def _collector_credentials_from_body(
        self,
        identity_id: str,
        body: dict,
    ) -> CollectorCredentials:
        public = next(
            (
                item
                for item in self.collector_store.list_public()
                if item.identity_id == identity_id
            ),
            None,
        )
        current = (
            self.collector_store.load_credentials(identity_id)
            if public and public.credential_configured
            else CollectorCredentials()
        )
        data = current.model_dump(mode="json")
        for key in ("cookie", "proxy", "user_agent", "device_id", "browser_info"):
            if key not in body:
                continue
            value = body[key]
            data[key] = {} if key == "browser_info" and value is None else value or ""
        return CollectorCredentials.model_validate(data)

    async def _probe_collector_identity(
        self,
        identity_id: str,
        *,
        require_proxy: bool = False,
    ) -> dict:
        identity = self.collector_store.get_identity(identity_id)
        credentials = self.collector_store.load_credentials(identity_id)
        if require_proxy and not credentials.proxy:
            raise HTTPException(status_code=400, detail="Proxy is not configured.")
        if (
            not require_proxy
            and not credentials.cookie
            and identity.auth_mode != CollectorAuthMode.ANONYMOUS
        ):
            raise HTTPException(status_code=400, detail="Cookie is not configured.")
        if (
            not require_proxy
            and identity.platform == CollectorPlatform.TIKTOK
            and identity.auth_mode == CollectorAuthMode.ANONYMOUS
        ):
            settings_path = getattr(
                getattr(self.parameter, "settings", None),
                "path",
                PROJECT_ROOT.joinpath("settings.json"),
            )
            runtime = build_collector_runtime(
                self.parameter,
                identity,
                credentials,
                settings_dir=Path(settings_path).parent,
            )
            try:
                await runtime.prepare()
                cookie_count = len(runtime.parameter.cookie_dict_tiktok)
            finally:
                await runtime.close()
            state = self.collector_store.get_runtime(identity_id)
            state.status = IdentityStatus.WARNING
            state.last_validated_at = self._collector_timestamp()
            state.last_error_code = "anonymous_session_pending_target_check"
            self.collector_store.save_runtime(state)
            return {
                "ok": True,
                "identity_id": identity_id,
                "platform": identity.platform.value,
                "auth_mode": identity.auth_mode.value,
                "status_code": 200,
                "validation_level": "anonymous_session",
                "cookie_count": cookie_count,
                "message": "匿名 Cloak 会话已建立；可用性将在首次目标采集时确认。",
            }
        headers = {}
        if credentials.user_agent:
            headers["User-Agent"] = credentials.user_agent
        if credentials.cookie:
            headers["Cookie"] = credentials.cookie
        client = create_client(
            user_agent=(
                credentials.user_agent
                or (
                    self.parameter.headers_tiktok.get("User-Agent", "")
                    if identity.platform == CollectorPlatform.TIKTOK
                    else self.parameter.headers.get("User-Agent", "")
                )
            ),
            timeout=min(max(int(self.parameter.timeout), 5), 20),
            proxy=credentials.proxy or None,
        )
        url = (
            "https://www.tiktok.com/"
            if identity.platform == CollectorPlatform.TIKTOK
            else "https://www.douyin.com/"
        )
        try:
            response = await client.get(url, headers=headers or None)
            response.raise_for_status()
        finally:
            await client.aclose()
        state = self.collector_store.get_runtime(identity_id)
        now = self._collector_timestamp()
        # A homepage request verifies the network/proxy/session material can be
        # loaded, but it cannot prove the account is logged in. Actual target
        # success promotes the identity to healthy.
        state.status = IdentityStatus.WARNING
        state.last_validated_at = now
        state.last_error_code = "login_state_pending_target_check"
        self.collector_store.save_runtime(state)
        return {
            "ok": True,
            "identity_id": identity_id,
            "platform": identity.platform.value,
            "auth_mode": identity.auth_mode.value,
            "status_code": response.status_code,
            "validation_level": "connectivity",
            "message": (
                "代理连通性测试成功。"
                if require_proxy
                else "网络与凭据加载成功；登录态将在首次目标采集时确认。"
            ),
        }

    def _build_ui_task(
        self,
        endpoint: str,
        payload: dict,
        retry_of: str | None = None,
        retry_mode: str = "",
    ) -> dict:
        task = {
            "task_id": self._new_task_id(),
            "endpoint": endpoint,
            "payload": payload,
            "status": "pending",
            "created_at": self._now_text(),
            "started_at": None,
            "finished_at": None,
            "updated_at": self._now_text(),
            "eta_baseline_current": 0,
            "eta_baseline_at": None,
            "retry_of": retry_of,
            "retry_mode": retry_mode,
            "worker": None,
            "error": "",
            "message": "",
            "result": None,
            "pause_supported": self._ui_task_pause_supported(endpoint),
            "progress": {
                "current": 0,
                "total": 0,
                "success": 0,
                "failed": 0,
                "skipped": 0,
                "percent": 0,
                "label": _("等待执行"),
            },
            "_runner": None,
            "_pause_event": None,
            "_pause_requested": False,
            "_active_units": 0,
            "_identity_failure_notified": "",
        }
        self.ui_tasks[task["task_id"]] = task
        self._persist_ui_task(task)
        return task

    @staticmethod
    def _hydrate_ui_task(task: dict) -> dict:
        task = dict(task)
        if task.get("status") == "success" and isinstance(task.get("result"), dict):
            task["status"] = APIServer._ui_task_result_status(task["result"])
        task.setdefault("pause_supported", APIServer._ui_task_pause_supported(
            str(task.get("endpoint") or "")
        ))
        task.setdefault("progress", {})
        task.setdefault("retry_of", None)
        task.setdefault("retry_mode", "")
        task.setdefault("result", None)
        task.setdefault("error", "")
        task.setdefault("message", "")
        task.setdefault("worker", None)
        task.setdefault("started_at", None)
        task.setdefault("finished_at", None)
        task.setdefault("eta_baseline_current", None)
        task.setdefault("eta_baseline_at", None)
        task["_runner"] = None
        task["_pause_event"] = None
        task["_pause_requested"] = False
        task["_active_units"] = 0
        task["_identity_failure_notified"] = ""
        return task

    def _persist_ui_task(self, task: dict) -> None:
        journal = getattr(self, "task_journal", None)
        if journal is None:
            return
        task_id = self._normalize_string(task.get("task_id"))
        if task_id:
            try:
                task["account_summary"] = journal.account_summary(task_id)
            except Exception:
                task.setdefault("account_summary", {})
        journal.save_task(task)

    async def _restore_ui_tasks(self) -> None:
        if getattr(self, "ui_tasks_restored", False):
            return
        journal = getattr(self, "task_journal", None)
        if journal is None:
            self.ui_tasks_restored = True
            return
        journal.recover_interrupted()
        for stored in reversed(journal.load_tasks()):
            task_id = self._normalize_string(stored.get("task_id"))
            if not task_id:
                continue
            hydrated = self._hydrate_ui_task(stored)
            self.ui_tasks[task_id] = hydrated
            journal.save_task(hydrated)
        self._refresh_task_counter()
        for task in self.ui_tasks.values():
            if task.get("status") == "pending":
                self.ui_task_queue.put_nowait(task["task_id"])
        self.ui_tasks_restored = True

    @classmethod
    def _redact_ui_task_value(cls, value, key: str = ""):
        return redact_webui_value(value, key)

    @classmethod
    def _public_ui_task(cls, task: dict) -> dict:
        return cls._redact_ui_task_value(
            {
                key: value
                for key, value in task.items()
                if not key.startswith("_")
                and key not in {"eta_baseline_current", "eta_baseline_at"}
            }
        )

    @classmethod
    def _public_settings(cls, settings: dict) -> dict:
        return cls._redact_ui_task_value(settings)

    @staticmethod
    def _ui_task_sort_key(item: dict) -> int:
        task_id = str(item.get("task_id", "")).lstrip("T")
        try:
            return int(task_id)
        except ValueError:
            return 0

    @staticmethod
    def _ui_task_pause_supported(endpoint: str) -> bool:
        return endpoint in {
            "/workflow/douyin/account_batch",
            "/workflow/tiktok/account_batch",
            "/workflow/accounts/avatar_batch",
        }

    def _set_ui_task_progress_label(self, task: dict, label: str) -> None:
        progress = task.get("progress")
        if isinstance(progress, dict):
            progress["label"] = label

    def _mark_ui_task_paused_if_quiescent(self, task: dict) -> bool:
        if (
            task.get("_pause_requested")
            and int(task.get("_active_units") or 0) == 0
            and task.get("status") == "pausing"
        ):
            task["status"] = "paused"
            task["message"] = _("任务已暂停，可从当前进度继续")
            task["updated_at"] = self._now_text()
            self._set_ui_task_progress_label(task, _("已暂停"))
            self._persist_ui_task(task)
            return True
        return task.get("status") == "paused"

    def _enqueue_ui_task(
        self,
        endpoint: str,
        payload: dict,
        retry_of: str | None = None,
        retry_mode: str = "",
    ) -> dict:
        task = self._build_ui_task(
            endpoint,
            payload,
            retry_of=retry_of,
            retry_mode=retry_mode,
        )
        self.ui_task_queue.put_nowait(task["task_id"])
        return task

    async def _start_ui_task_workers(self, workers: int = 2) -> None:
        await self._restore_ui_tasks()
        if self.ui_task_workers:
            return
        self.ui_task_shutdown = False
        for i in range(max(1, workers)):
            self.ui_task_workers.append(create_task(self._ui_task_worker(i + 1)))

    async def _stop_ui_task_workers(self) -> None:
        if not self.ui_task_workers:
            return
        self.ui_task_shutdown = True
        for worker in self.ui_task_workers:
            worker.cancel()
        await gather(*self.ui_task_workers, return_exceptions=True)
        self.ui_task_workers.clear()

    async def _start_ui_schedules(self) -> None:
        if self.ui_schedules:
            return
        raw = self.parameter.ui_schedules if isinstance(self.parameter.ui_schedules, list) else []
        for item in raw:
            normalized = self._normalize_schedule_payload(item)
            schedule_id = self._normalize_string(item.get("schedule_id"))
            if schedule_id:
                normalized["schedule_id"] = schedule_id
            else:
                normalized["schedule_id"] = self._new_schedule_id()
            self.ui_schedules[normalized["schedule_id"]] = normalized
            if normalized["enabled"]:
                self._start_single_schedule_runner(normalized["schedule_id"])
        self._refresh_schedule_counter()
        try:
            await to_thread(self._maybe_create_daily_configuration_snapshot)
        except Exception as error:
            self.logger.warning(
                _("每日配置快照失败：{error}").format(error=error)
            )

    async def _stop_ui_schedules(self) -> None:
        for task in self.ui_schedule_tasks.values():
            task.cancel()
        if self.ui_schedule_tasks:
            await gather(*self.ui_schedule_tasks.values(), return_exceptions=True)
        self.ui_schedule_tasks.clear()

    def _refresh_schedule_counter(self) -> None:
        max_id = 0
        for key in self.ui_schedules:
            try:
                max_id = max(max_id, int(str(key).lstrip("S")))
            except ValueError:
                continue
        self.ui_schedule_counter = max_id

    async def _ui_task_worker(self, worker_id: int) -> None:
        while True:
            try:
                task_id = await self.ui_task_queue.get()
            except CancelledError:
                break
            try:
                await self._execute_ui_task(task_id, worker_id)
            finally:
                self.ui_task_queue.task_done()

    @staticmethod
    def _serialize_response(response):
        if hasattr(response, "model_dump"):
            return response.model_dump()
        if isinstance(response, (dict, list, str, int, float, bool)) or response is None:
            return response
        return str(response)

    @staticmethod
    def _is_failed_response(result) -> bool:
        if not isinstance(result, dict):
            return False
        message = str(result.get("message", ""))
        return "失败" in message or "参数错误" in message

    @classmethod
    def _ui_task_result_status(cls, result) -> str:
        data = result.get("data") if isinstance(result, dict) else None
        if isinstance(data, dict) and any(key in data for key in ("success", "failed")):
            try:
                succeeded = max(0, int(data.get("success") or 0))
                failed = max(0, int(data.get("failed") or 0))
            except (TypeError, ValueError):
                pass
            else:
                if failed and succeeded:
                    return "partial_success"
                if failed and not succeeded:
                    return "failed"
                return "success"
        return "failed" if cls._is_failed_response(result) else "success"

    def _sync_runtime_http_clients(self) -> None:
        if hasattr(self.links, "requester"):
            self.links.requester.client = self.parameter.client
        if hasattr(self.links_tiktok, "requester"):
            self.links_tiktok.requester.client = self.parameter.client_tiktok
        self.downloader.client = self.parameter.client
        self.downloader.client_tiktok = self.parameter.client_tiktok
        self.downloader.proxy = self.parameter.proxy
        self.downloader.proxy_tiktok = self.parameter.proxy_tiktok
        self.downloader.timeout = self.parameter.timeout

    async def _execute_ui_task(self, task_id: str, worker_id: int) -> None:
        task = self.ui_tasks.get(task_id)
        if not task or task.get("status") != "pending":
            return
        task["status"] = "running"
        task["worker"] = worker_id
        task["started_at"] = self._now_text()
        progress = task.get("progress") if isinstance(task.get("progress"), dict) else {}
        try:
            resumed_current = max(0, int(progress.get("current") or 0))
        except (TypeError, ValueError):
            resumed_current = 0
        task["eta_baseline_current"] = (
            resumed_current if task.get("recovered_after_restart") else 0
        )
        task["eta_baseline_at"] = task["started_at"]
        task["updated_at"] = self._now_text()
        self._persist_ui_task(task)
        execution_payload = dict(task["payload"])
        pause_supported = bool(task.get("pause_supported"))
        pause_event = Event()
        pause_event.set()
        task["_pause_event"] = pause_event
        task["_pause_requested"] = False
        task["_active_units"] = 0

        def update_progress(progress: dict) -> None:
            task["progress"] = {
                **task.get("progress", {}),
                **progress,
            }
            task["updated_at"] = self._now_text()
            if task.get("recovered_after_restart"):
                task["message"] = _("服务重启后已恢复并继续执行")
            self._persist_ui_task(task)

        async def pause_checkpoint() -> None:
            if not pause_supported:
                return
            while task.get("_pause_requested"):
                self._mark_ui_task_paused_if_quiescent(task)
                await pause_event.wait()

        def unit_started() -> None:
            if pause_supported:
                task["_active_units"] = int(task.get("_active_units") or 0) + 1

        def unit_finished() -> None:
            if not pause_supported:
                return
            task["_active_units"] = max(
                0,
                int(task.get("_active_units") or 0) - 1,
            )
            self._mark_ui_task_paused_if_quiescent(task)

        async def identity_failure(
            identity_id: str,
            error_code: str,
            message: str,
        ) -> bool:
            policy = self._normalize_string(
                task.get("payload", {}).get("identity_failure_action")
            ).lower()
            task["identity_failure"] = {
                "identity_id": self._normalize_string(identity_id),
                "error_code": self._normalize_string(error_code)
                or "identity_unavailable",
                "message": self._normalize_string(message)
                or _("采集身份不可用"),
                "at": self._now_text(),
            }
            task["updated_at"] = self._now_text()
            if self._normalize_bool(
                task.get("payload", {}).get("notify_on_identity_failure"),
                default=True,
            ):
                signature = "|".join(
                    (
                        task["identity_failure"]["identity_id"],
                        task["identity_failure"]["error_code"],
                    )
                )
                if task.get("_identity_failure_notified") != signature:
                    task["_identity_failure_notified"] = signature
                    create_task(self._notify_ui_identity_failure(task))
            if policy != "pause" or not pause_supported:
                self._persist_ui_task(task)
                return False
            task["_pause_requested"] = True
            pause_event.clear()
            task["status"] = "pausing"
            task["message"] = _("采集身份异常，任务将在安全边界暂停")
            self._set_ui_task_progress_label(task, _("等待修复采集身份"))
            self._mark_ui_task_paused_if_quiescent(task)
            self._persist_ui_task(task)
            return True

        execution_payload["_ui_progress_callback"] = update_progress
        execution_payload["_ui_pause_control"] = {
            "checkpoint": pause_checkpoint,
            "unit_started": unit_started,
            "unit_finished": unit_finished,
            "identity_failure": identity_failure,
            "task_id": task_id,
        }
        runner = create_task(
            self._execute_ui_endpoint(
                task["endpoint"],
                execution_payload,
            )
        )
        task["_runner"] = runner
        try:
            response = await runner
            result = self._serialize_response(response)
            task["result"] = result
            task["message"] = (
                result.get("message", "")
                if isinstance(result, dict)
                else ""
            )
            task["status"] = self._ui_task_result_status(result)
        except CancelledError:
            journal = getattr(self, "task_journal", None)
            if journal is not None:
                journal.reset_running_accounts(task_id)
            if getattr(self, "ui_task_shutdown", False) and pause_supported:
                keep_paused = task.get("status") in {"pausing", "paused"}
                task["status"] = "paused" if keep_paused else "pending"
                task["worker"] = None
                task["error"] = ""
                task["message"] = (
                    _("服务停止，任务保持暂停")
                    if keep_paused
                    else _("服务停止，任务将在下次启动时继续")
                )
            else:
                task["status"] = "canceled"
                task["error"] = "task_canceled"
                task["message"] = _("任务已取消")
        except ValidationError:
            task["status"] = "failed"
            task["error"] = "validation_error"
            task["message"] = _("参数校验失败！")
        except Exception as error:
            message = str(error)
            if "client has been closed" in message.lower():
                try:
                    old_client = self.parameter.client
                    old_client_tiktok = self.parameter.client_tiktok
                    self.parameter.client = create_client(
                        timeout=self.parameter.timeout,
                        proxy=self.parameter.proxy,
                    )
                    self.parameter.client_tiktok = create_client(
                        timeout=self.parameter.timeout,
                        proxy=self.parameter.proxy_tiktok,
                    )
                    self._sync_runtime_http_clients()
                    await old_client.aclose()
                    await old_client_tiktok.aclose()
                    retry_response = await self._execute_ui_endpoint(
                        task["endpoint"],
                        execution_payload,
                    )
                    retry_result = self._serialize_response(retry_response)
                    task["result"] = retry_result
                    task["message"] = (
                        retry_result.get("message", "")
                        if isinstance(retry_result, dict)
                        else ""
                    )
                    task["status"] = self._ui_task_result_status(retry_result)
                    return
                except Exception:
                    pass
            task["status"] = "failed"
            task["error"] = "task_execution_failed"
            task["message"] = _("任务执行失败！")
        finally:
            progress = task.get("progress")
            if isinstance(progress, dict):
                if task.get("status") == "success":
                    progress["label"] = _("执行完成")
                elif task.get("status") == "partial_success":
                    progress["label"] = _("部分完成")
                elif task.get("status") == "failed":
                    progress["label"] = _("执行失败")
                elif task.get("status") == "canceled":
                    progress["label"] = _("已取消")
            if task.get("status") in {
                "success",
                "partial_success",
                "failed",
                "canceled",
            }:
                task["finished_at"] = self._now_text()
            else:
                task["finished_at"] = None
            task["updated_at"] = self._now_text()
            task["_runner"] = None
            task["_pause_event"] = None
            task["_pause_requested"] = False
            task["_active_units"] = 0
            self._persist_ui_task(task)
            schedule_url = self._normalize_string(task.get("schedule_uptime_kuma_url"))
            if schedule_url and task.get("status") in {
                "success",
                "partial_success",
                "failed",
                "canceled",
            }:
                status, message = self._build_uptime_kuma_status(
                    task,
                    self._normalize_string(task.get("schedule_name")),
                    self._normalize_string(task.get("schedule_platform")),
                )
                push_url = self._build_uptime_kuma_url(schedule_url, status, message)
                if push_url:
                    create_task(
                        self._send_uptime_kuma_push(
                            push_url,
                            proxy=self._normalize_string(task.get("payload", {}).get("proxy")),
                        )
                    )
            if task.get("status") in {
                "success",
                "partial_success",
                "failed",
                "canceled",
            }:
                await self._notify_ui_task_completion(task)

    async def _execute_ui_endpoint(self, endpoint: str, payload: dict):
        payload = dict(payload)
        progress_callback = payload.pop("_ui_progress_callback", None)
        pause_control = payload.pop("_ui_pause_control", None)
        if endpoint == "/douyin/detail":
            return await self.handle_detail(Detail(**payload), False)
        if endpoint == "/douyin/account":
            return await self.handle_account(Account(**payload), False)
        if endpoint == "/douyin/mix":
            return await self._handle_mix_request(Mix(**payload), False)
        if endpoint == "/douyin/live":
            return await self._handle_live_request(Live(**payload), False)
        if endpoint == "/douyin/comment":
            return await self._handle_comment_request(Comment(**payload))
        if endpoint == "/douyin/reply":
            return await self._handle_reply_request(Reply(**payload))
        if endpoint == "/douyin/search/general":
            return await self.handle_search(GeneralSearch(**payload))
        if endpoint == "/douyin/search/video":
            return await self.handle_search(VideoSearch(**payload))
        if endpoint == "/douyin/search/user":
            return await self.handle_search(UserSearch(**payload))
        if endpoint == "/douyin/search/live":
            return await self.handle_search(LiveSearch(**payload))
        if endpoint == "/tiktok/detail":
            return await self.handle_detail(DetailTikTok(**payload), True)
        if endpoint == "/tiktok/account":
            return await self.handle_account(AccountTiktok(**payload), True)
        if endpoint == "/tiktok/mix":
            return await self._handle_mix_request(MixTikTok(**payload), True)
        if endpoint == "/tiktok/live":
            return await self._handle_live_request(LiveTikTok(**payload), True)
        if endpoint == "/workflow/douyin/account_batch":
            return await self._run_ui_account_batch(
                payload,
                False,
                progress_callback=progress_callback,
                pause_control=pause_control,
            )
        if endpoint == "/workflow/tiktok/account_batch":
            return await self._run_ui_account_batch(
                payload,
                True,
                progress_callback=progress_callback,
                pause_control=pause_control,
            )
        if endpoint == "/workflow/douyin/detail_links":
            return await self._run_ui_detail_links(payload, False)
        if endpoint == "/workflow/tiktok/detail_links":
            return await self._run_ui_detail_links(payload, True)
        if endpoint == "/workflow/accounts/avatar_batch":
            return await self._run_ui_avatar_batch(
                payload,
                progress_callback=progress_callback,
                pause_control=pause_control,
            )
        raise HTTPException(
            status_code=400,
            detail="Unsupported endpoint.",
        )

    def _scope_root(self, scope: ScopeType) -> Path:
        return {
            "project": PROJECT_ROOT,
            "download": self.parameter.root,
        }.get(scope, self.parameter.root)

    @staticmethod
    def _is_protected_file_scope_path(
        scope: ScopeType,
        root: Path,
        target: Path,
    ) -> bool:
        return scope == "project" and is_protected_project_path(root, target)

    def _is_runtime_debug_capture_path(self, target: Path) -> bool:
        parameter = getattr(self, "parameter", None)
        configured = self._normalize_string(
            getattr(parameter, "tiktok_api_debug_capture_dir", "")
        )
        settings = getattr(parameter, "settings", None)
        settings_path = getattr(settings, "path", None)
        if not configured or not settings_path:
            return False
        try:
            debug_root = Path(configured).expanduser()
            if not debug_root.is_absolute():
                debug_root = Path(settings_path).expanduser().resolve().parent / debug_root
            debug_root = debug_root.resolve()
            target.expanduser().resolve().relative_to(debug_root)
            return True
        except (OSError, RuntimeError, ValueError):
            return False

    def _ensure_public_file_scope_path(
        self,
        scope: ScopeType,
        root: Path,
        target: Path,
    ) -> None:
        if self._is_protected_file_scope_path(
            scope,
            root,
            target,
        ) or self._is_runtime_debug_capture_path(target):
            # Do not reveal whether a protected settings/profile path exists.
            raise HTTPException(
                status_code=404,
                detail="File does not exist.",
            )

    @staticmethod
    def _human_size(value: int) -> str:
        size = max(0, int(value or 0))
        if size < 1024:
            return f"{size} B"
        units = ("KB", "MB", "GB", "TB")
        number = size / 1024
        unit = units[0]
        for next_unit in units[1:]:
            if number < 1024:
                break
            number /= 1024
            unit = next_unit
        return f"{number:.2f} {unit}"

    def _collect_scope_stats(
        self,
        current: Path,
        scope: ScopeType = "download",
        scope_root: Path | None = None,
    ) -> dict[str, Any]:
        folders = 0
        files = 0
        images = 0
        videos = 0
        total_size = 0
        latest_modified_at = 0.0
        zero_byte_files = 0
        temporary_files = 0
        scan_errors = 0
        root = scope_root or current
        for path in current.rglob("*"):
            try:
                if self._is_protected_file_scope_path(scope, root, path):
                    continue
                if path.is_dir():
                    folders += 1
                    continue
                if not path.is_file():
                    continue
                files += 1
                suffix = path.suffix.lower()
                if suffix in IMAGE_SUFFIXES:
                    images += 1
                elif suffix in VIDEO_SUFFIXES:
                    videos += 1
                file_stat = path.stat()
                total_size += file_stat.st_size
                if file_stat.st_size == 0:
                    zero_byte_files += 1
                if suffix in {".part", ".tmp", ".download", ".crdownload"}:
                    temporary_files += 1
                latest_modified_at = max(latest_modified_at, file_stat.st_mtime)
            except OSError:
                scan_errors += 1
                continue
        try:
            disk = disk_usage(current)
            used_percent = round((disk.used / disk.total) * 100, 1) if disk.total else 0
        except OSError:
            disk = None
            used_percent = 0
        return {
            "folders": folders,
            "files": files,
            "images": images,
            "videos": videos,
            "other_files": max(0, files - images - videos),
            "size": total_size,
            "size_human": self._human_size(total_size),
            "integrity": {
                "zero_byte_files": zero_byte_files,
                "temporary_files": temporary_files,
                "scan_errors": scan_errors,
                "checked_files": files,
            },
            "storage": (
                {
                    "total": disk.total,
                    "used": disk.used,
                    "free": disk.free,
                    "used_percent": used_percent,
                    "alert_level": self._storage_alert_level_for_percent(
                        used_percent
                    ),
                    "thresholds": list(self.STORAGE_ALERT_THRESHOLDS),
                }
                if disk is not None
                else {}
            ),
            "latest_updated_at": (
                datetime.fromtimestamp(latest_modified_at)
                .astimezone()
                .isoformat(timespec="seconds")
                if latest_modified_at
                else ""
            ),
        }

    def _ensure_overview_media_state(self) -> None:
        """Initialize overview cache fields for lightweight test instances."""

        if not hasattr(self, "_overview_media_lock"):
            self._overview_media_lock = Lock()
        if not hasattr(self, "_overview_media_cache"):
            self._overview_media_cache = {}
        if not hasattr(self, "_overview_media_cache_updated_monotonic"):
            self._overview_media_cache_updated_monotonic = 0.0
        if not hasattr(self, "_overview_media_scan_attempt_monotonic"):
            self._overview_media_scan_attempt_monotonic = 0.0
        if not hasattr(self, "_overview_media_scan_started_at"):
            self._overview_media_scan_started_at = ""
        if not hasattr(self, "_overview_media_scan_error"):
            self._overview_media_scan_error = ""
        if not hasattr(self, "_overview_media_scan_thread"):
            self._overview_media_scan_thread = None
        self._ensure_maintenance_state()

    @classmethod
    def _storage_alert_level_for_percent(cls, used_percent: float) -> int:
        return max(
            (threshold for threshold in cls.STORAGE_ALERT_THRESHOLDS if used_percent >= threshold),
            default=0,
        )

    def _refresh_overview_media_cache(self, root: Path) -> None:
        try:
            stats = self._collect_scope_stats(
                root,
                scope="download",
                scope_root=root,
            )
            refreshed_at = datetime.now().astimezone().isoformat(timespec="seconds")
        except Exception as error:
            logger = getattr(self, "logger", None)
            if logger:
                logger.error(f"Overview media scan failed: {error}")
            with self._overview_media_lock:
                self._overview_media_scan_error = "媒体目录统计失败"
            return
        with self._overview_media_lock:
            self._overview_media_cache = {
                **stats,
                "refreshed_at": refreshed_at,
            }
            self._overview_media_cache_updated_monotonic = monotonic()
            self._overview_media_scan_error = ""
        storage = stats.get("storage") if isinstance(stats.get("storage"), dict) else {}
        level = int(storage.get("alert_level") or 0)
        if level > self._storage_alert_last_level:
            self._storage_alert_pending_level = level
        elif level == 0 and self._storage_alert_last_level:
            self._storage_alert_last_level = 0
            self._save_storage_alert_state(0)

    def _overview_media_snapshot(self, *, force_refresh: bool = False) -> dict:
        self._ensure_overview_media_state()
        root = self._scope_root("download").expanduser().resolve()
        with self._overview_media_lock:
            cache_age = (
                monotonic() - self._overview_media_cache_updated_monotonic
                if self._overview_media_cache
                else None
            )
            running = bool(
                self._overview_media_scan_thread
                and self._overview_media_scan_thread.is_alive()
            )
            stale = cache_age is None or (
                cache_age >= self.OVERVIEW_MEDIA_CACHE_TTL_SECONDS
            )
            retry_ready = not self._overview_media_scan_error or (
                monotonic() - self._overview_media_scan_attempt_monotonic >= 60
            )
            if not running and (force_refresh or (stale and retry_ready)):
                self._overview_media_scan_attempt_monotonic = monotonic()
                self._overview_media_scan_started_at = (
                    datetime.now().astimezone().isoformat(timespec="seconds")
                )
                self._overview_media_scan_error = ""
                thread = Thread(
                    target=self._refresh_overview_media_cache,
                    args=(root,),
                    name="fetchshelf-overview-media-scan",
                    daemon=True,
                )
                self._overview_media_scan_thread = thread
                thread.start()
                running = True
            cache = dict(self._overview_media_cache)
            error = self._overview_media_scan_error
            scan_started_at = self._overview_media_scan_started_at

        if running:
            status = "refreshing" if cache else "scanning"
        elif error:
            status = "error"
        elif cache:
            status = "ready"
        else:
            status = "empty"
        return {
            **cache,
            "status": status,
            "stale": stale,
            "scan_started_at": scan_started_at,
            "error": error,
        }

    @classmethod
    def _overview_task_snapshot(cls, task: dict | None) -> dict | None:
        if not task:
            return None
        keys = (
            "task_id",
            "endpoint",
            "status",
            "created_at",
            "started_at",
            "finished_at",
            "updated_at",
            "message",
            "progress",
            "account_summary",
            "schedule_id",
            "schedule_name",
            "recovered_after_restart",
        )
        snapshot = {key: task.get(key) for key in keys}
        progress = task.get("progress") if isinstance(task.get("progress"), dict) else {}
        try:
            current = max(0, int(progress.get("current") or 0))
            total = max(0, int(progress.get("total") or 0))
            baseline_value = task.get("eta_baseline_current")
            if task.get("recovered_after_restart") and baseline_value is None:
                raise ValueError("Recovered task has no ETA baseline")
            baseline_current = max(0, int(baseline_value or 0))
            processed = max(0, current - baseline_current)
            started_text = str(
                task.get("eta_baseline_at")
                or task.get("started_at")
                or task.get("created_at")
                or ""
            )
            ended_text = str(task.get("finished_at") or "")
            started = datetime.fromisoformat(started_text.replace("Z", "+00:00"))
            ended = (
                datetime.fromisoformat(ended_text.replace("Z", "+00:00"))
                if ended_text
                else datetime.now(started.tzinfo)
            )
            elapsed_seconds = max(1.0, (ended - started).total_seconds())
            throughput = processed / (elapsed_seconds / 60)
            remaining = max(0, total - current)
            eta_seconds = round((remaining / throughput) * 60) if throughput else None
            snapshot["throughput_per_minute"] = round(throughput, 2)
            snapshot["eta_seconds"] = eta_seconds
            snapshot["eta_at"] = (
                (datetime.now().astimezone() + timedelta(seconds=eta_seconds))
                .isoformat(timespec="seconds")
                if eta_seconds is not None and not task.get("finished_at")
                else ""
            )
        except (TypeError, ValueError):
            snapshot["throughput_per_minute"] = 0
            snapshot["eta_seconds"] = None
            snapshot["eta_at"] = ""
        return cls._redact_ui_task_value(snapshot)

    def _overview_crawl_summary(self) -> dict:
        endpoints = {
            "/workflow/douyin/account_batch",
            "/workflow/tiktok/account_batch",
        }
        tasks = sorted(
            (
                item
                for item in getattr(self, "ui_tasks", {}).values()
                if item.get("endpoint") in endpoints
            ),
            key=self._ui_task_sort_key,
            reverse=True,
        )
        current = next(
            (item for item in tasks if item.get("status") in ACTIVE_TASK_STATUSES),
            None,
        )
        latest_ended = next(
            (item for item in tasks if item.get("status") not in ACTIVE_TASK_STATUSES),
            None,
        )
        latest_success = next(
            (item for item in tasks if item.get("status") == "success"),
            None,
        )
        latest_completed = next(
            (
                item
                for item in tasks
                if item.get("status") in {"success", "partial_success"}
            ),
            None,
        )
        return {
            "current": self._overview_task_snapshot(current),
            "latest": self._overview_task_snapshot(tasks[0] if tasks else None),
            "latest_ended": self._overview_task_snapshot(latest_ended),
            "latest_success": self._overview_task_snapshot(latest_success),
            "latest_completed": self._overview_task_snapshot(latest_completed),
            "active_count": sum(
                item.get("status") in ACTIVE_TASK_STATUSES for item in tasks
            ),
        }

    def _overview_collector_summary(self) -> dict:
        store = getattr(self, "collector_store", None)
        identities = store.list_public() if store else []
        route_configured_ids = {
            item.identity_id for item in identities if item.route_configured
        }
        routable_ids = set()
        if store:
            for platform in CollectorPlatform:
                routable_ids.update(
                    item.identity_id
                    for item in store.route_candidates(platform)
                    if item.identity_id in route_configured_ids
                    and not self._collector_identity_login_locked(item.identity_id)
                    and candidate_available(item, platform=platform)
                )
        identity_rows = []
        for item in identities:
            attempts = max(0, int(item.total_successes + item.total_failures))
            identity_rows.append(
                {
                    "identity_id": item.identity_id,
                    "name": item.name,
                    "platform": item.platform.value,
                    "auth_mode": item.auth_mode.value,
                    "status": item.status.value,
                    "active_leases": item.active_leases,
                    "successes": item.total_successes,
                    "failures": item.total_failures,
                    "risk_failures": item.risk_failures,
                    "success_rate": (
                        round((item.total_successes / attempts) * 100, 1)
                        if attempts
                        else None
                    ),
                    "cooldown_until": item.cooldown_until,
                    "last_error_code": item.last_error_code,
                }
            )
        return {
            "total": len(identities),
            "enabled": sum(bool(item.enabled) for item in identities),
            "routable": len(routable_ids),
            "attention": sum(
                bool(item.enabled) and item.identity_id not in routable_ids
                for item in identities
            ),
            "cookie_configured": sum(
                bool(item.cookie_configured) for item in identities
            ),
            "anonymous": sum(
                item.auth_mode == CollectorAuthMode.ANONYMOUS for item in identities
            ),
            "proxy_configured": sum(
                bool(item.proxy_configured) for item in identities
            ),
            "cookie_and_proxy": sum(
                bool(item.cookie_configured and item.proxy_configured)
                for item in identities
            ),
            "route_and_proxy": sum(
                bool(item.route_configured and item.proxy_configured)
                for item in identities
            ),
            "active_leases": sum(
                max(0, int(item.active_leases or 0)) for item in identities
            ),
            "risk_failures": sum(
                max(0, int(item.risk_failures or 0)) for item in identities
            ),
            "cooldown": sum(
                item.status == IdentityStatus.COOLDOWN for item in identities
            ),
            "identities": identity_rows,
            "platforms": {
                platform.value: sum(item.platform == platform for item in identities)
                for platform in CollectorPlatform
            },
        }

    @staticmethod
    def _supported_ui_task_endpoints() -> set[str]:
        return {
            "/douyin/detail",
            "/douyin/account",
            "/douyin/mix",
            "/douyin/live",
            "/douyin/comment",
            "/douyin/reply",
            "/douyin/search/general",
            "/douyin/search/video",
            "/douyin/search/user",
            "/douyin/search/live",
            "/tiktok/detail",
            "/tiktok/account",
            "/tiktok/mix",
            "/tiktok/live",
            "/workflow/douyin/account_batch",
            "/workflow/tiktok/account_batch",
            "/workflow/douyin/detail_links",
            "/workflow/tiktok/detail_links",
            "/workflow/accounts/avatar_batch",
        }

    @staticmethod
    def _validate_ui_task_payload(endpoint: str, payload: dict) -> None:
        validators = {
            "/douyin/detail": Detail,
            "/douyin/account": Account,
            "/douyin/mix": Mix,
            "/douyin/live": Live,
            "/douyin/comment": Comment,
            "/douyin/reply": Reply,
            "/douyin/search/general": GeneralSearch,
            "/douyin/search/video": VideoSearch,
            "/douyin/search/user": UserSearch,
            "/douyin/search/live": LiveSearch,
            "/tiktok/detail": DetailTikTok,
            "/tiktok/account": AccountTiktok,
            "/tiktok/mix": MixTikTok,
            "/tiktok/live": LiveTikTok,
        }
        model = validators.get(endpoint)
        if model:
            model(**payload)
            return
        if endpoint in {
            "/workflow/douyin/account_batch",
            "/workflow/tiktok/account_batch",
        }:
            APIServer._validate_ui_workflow_account_payload(payload)
            return
        if endpoint in {
            "/workflow/douyin/detail_links",
            "/workflow/tiktok/detail_links",
        }:
            APIServer._validate_ui_workflow_detail_payload(payload)
            return
        if endpoint == "/workflow/accounts/avatar_batch":
            APIServer._validate_ui_avatar_batch_payload(payload)

    @staticmethod
    def _normalize_string(value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip()

    @staticmethod
    def _normalize_bool(value: Any, default: bool = False) -> bool:
        if isinstance(value, bool):
            return value
        if value in {None, ""}:
            return default
        if isinstance(value, (int, float)):
            return value != 0
        if isinstance(value, str):
            text = value.strip().lower()
            if text in {"1", "true", "yes", "on", "enable", "enabled", "启用", "开启"}:
                return True
            if text in {
                "0",
                "false",
                "no",
                "off",
                "disable",
                "disabled",
                "禁用",
                "关闭",
            }:
                return False
        return default

    @staticmethod
    def _build_uptime_kuma_url(
        base_url: str,
        status: str,
        message: str,
    ) -> str:
        if not base_url:
            return ""
        parsed = urlsplit(base_url)
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        query["status"] = status
        if message:
            query["msg"] = message
        new_query = urlencode(query, doseq=True)
        return urlunsplit(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                new_query,
                parsed.fragment,
            )
        )

    @staticmethod
    def _build_uptime_kuma_status(
        task: dict,
        name: str,
        platform: str,
    ) -> tuple[str, str]:
        task_status = str(task.get("status", "") or "")
        result = task.get("result") if isinstance(task.get("result"), dict) else {}
        data = result.get("data") if isinstance(result.get("data"), dict) else {}

        def _get_int(key: str) -> int | None:
            value = data.get(key)
            return value if isinstance(value, int) else None

        queued = _get_int("queued")
        success = _get_int("success")
        failed = _get_int("failed")
        skipped = _get_int("skipped")
        failed_streak_max = _get_int("failed_streak_max")

        ratio_down = (
            isinstance(failed, int)
            and isinstance(success, int)
            and failed > success
        )
        streak_down = isinstance(failed_streak_max, int) and failed_streak_max >= 5
        status = "down" if (ratio_down or streak_down) else "up"

        base = f"{name or 'Schedule'} · {platform or '-'}"
        summary_parts = []
        result_message = result.get("message") if isinstance(result, dict) else ""
        if isinstance(result_message, str) and result_message:
            summary_parts.append(result_message)
        elif task_status:
            summary_parts.append(task_status)
        if queued is not None:
            summary_parts.append(f"queued={queued}")
        if success is not None:
            summary_parts.append(f"success={success}")
        if failed is not None:
            summary_parts.append(f"failed={failed}")
        if skipped is not None:
            summary_parts.append(f"skipped={skipped}")
        if failed_streak_max is not None:
            summary_parts.append(f"failed_streak_max={failed_streak_max}")
        message = f"{base} | {' | '.join(summary_parts)}" if summary_parts else base
        return status, message

    def _attach_schedule_task_meta(self, task: dict, schedule: dict) -> None:
        if not isinstance(task, dict) or not isinstance(schedule, dict):
            return
        task["schedule_id"] = self._normalize_string(schedule.get("schedule_id"))
        task["schedule_name"] = self._normalize_string(schedule.get("name"))
        task["schedule_platform"] = self._normalize_string(schedule.get("platform"))
        task["schedule_uptime_kuma_url"] = self._normalize_string(
            schedule.get("uptime_kuma_url")
        )
        task["schedule_bark_url"] = self._normalize_string(
            schedule.get("bark_url")
        )
        self._persist_ui_task(task)

    def _inherit_schedule_task_meta(self, task: dict, source: dict) -> None:
        for key in (
            "schedule_id",
            "schedule_name",
            "schedule_platform",
            "schedule_uptime_kuma_url",
            "schedule_bark_url",
        ):
            if source.get(key):
                task[key] = source[key]
        schedule_id = self._normalize_string(task.get("schedule_id"))
        schedule = getattr(self, "ui_schedules", {}).get(schedule_id)
        if schedule is not None:
            schedule["last_task_id"] = task.get("task_id", "")
            schedule["updated_at"] = self._now_text()
            self._persist_ui_schedules()
        self._persist_ui_task(task)

    async def _send_uptime_kuma_push(self, url: str, proxy: str | None = None) -> None:
        target = self._normalize_string(url)
        if not target:
            return
        proxy_value = self._normalize_string(proxy) or self.parameter.proxy
        timeout = max(5, min(int(getattr(self.parameter, "timeout", 10) or 10), 30))
        try:
            async with create_client(timeout=timeout, proxy=proxy_value) as client:
                await client.get(target)
        except Exception as error:  # noqa: BLE001
            self.logger.warning(
                _("Uptime Kuma push failed: {error}").format(error=error)
            )

    async def _notify_ui_identity_failure(self, task: dict) -> None:
        failure = (
            task.get("identity_failure")
            if isinstance(task.get("identity_failure"), dict)
            else {}
        )
        identity_id = self._normalize_string(failure.get("identity_id")) or "自动路由"
        error_code = (
            self._normalize_string(failure.get("error_code"))
            or "identity_unavailable"
        )
        schedule_name = (
            self._normalize_string(task.get("schedule_name"))
            or self._normalize_string(task.get("task_id"))
            or "账号批量任务"
        )
        message = f"{schedule_name} · identity={identity_id} · error={error_code}"
        proxy = self._normalize_string(task.get("payload", {}).get("proxy"))
        uptime_url = self._normalize_string(task.get("schedule_uptime_kuma_url"))
        if uptime_url:
            push_url = self._build_uptime_kuma_url(
                uptime_url,
                "down",
                message,
            )
            if push_url:
                await self._send_uptime_kuma_push(push_url, proxy=proxy)
        bark_url = self._normalize_string(task.get("schedule_bark_url"))
        if bark_url:
            ok, error = await self._send_bark_notification(
                bark_url,
                f"采集身份异常: {schedule_name}",
                message,
                proxy=proxy,
            )
            if not ok and error:
                self.logger.warning(
                    _("Bark 通知发送失败：{error}").format(error=error),
                )

    @classmethod
    def _build_ui_task_completion_notification(
        cls,
        task: dict,
    ) -> tuple[str, str]:
        task_status = cls._normalize_string(task.get("status")).lower()
        result = task.get("result") if isinstance(task.get("result"), dict) else {}
        data = result.get("data") if isinstance(result.get("data"), dict) else {}

        def _count(key: str) -> int | None:
            value = data.get(key)
            if isinstance(value, bool):
                return None
            try:
                return int(value) if value is not None else None
            except (TypeError, ValueError):
                return None

        queued = _count("queued")
        success = _count("success")
        failed = _count("failed")
        skipped = _count("skipped")
        if task_status == "canceled":
            outcome = "已取消"
        elif task_status == "failed" or (
            isinstance(failed, int)
            and failed > 0
            and (success is None or success <= 0)
        ):
            outcome = "失败"
        elif isinstance(failed, int) and failed > 0:
            outcome = "部分失败"
        else:
            outcome = "完成"

        schedule_name = (
            cls._normalize_string(task.get("schedule_name"))
            or cls._normalize_string(task.get("task_id"))
            or "账号批量任务"
        )
        platform = cls._normalize_string(task.get("schedule_platform"))
        platform_label = {"douyin": "抖音", "tiktok": "TikTok"}.get(
            platform.lower(),
            platform or "-",
        )
        task_id = cls._normalize_string(task.get("task_id")) or "-"
        parts = [platform_label, f"任务 {task_id}"]
        if queued is not None:
            parts.append(f"共 {queued}")
        if success is not None:
            parts.append(f"成功 {success}")
        if failed is not None:
            parts.append(f"失败 {failed}")
        if skipped is not None and skipped > 0:
            parts.append(f"跳过 {skipped}")

        failures = data.get("failures") if isinstance(data.get("failures"), list) else []
        if failures and isinstance(failures[0], dict):
            reason = cls._normalize_string(failures[0].get("reason"))
            if reason:
                parts.append(reason[:120])
        elif task_status in {"failed", "canceled"}:
            message = cls._normalize_string(task.get("message"))
            if message:
                parts.append(message[:120])
        return f"下载{outcome}: {schedule_name}", " · ".join(parts)

    async def _notify_ui_task_completion(self, task: dict) -> None:
        bark_url = self._normalize_string(task.get("schedule_bark_url"))
        if not bark_url:
            return
        title, body = self._build_ui_task_completion_notification(task)
        sent, error = await self._send_bark_notification(
            bark_url=bark_url,
            title=title,
            body=body,
            proxy=self._normalize_string(task.get("payload", {}).get("proxy")),
        )
        task["schedule_notification"] = {
            "channel": "bark",
            "status": "sent" if sent else "failed",
            "at": self._now_text(),
        }
        self._persist_ui_task(task)
        if not sent and error:
            self.logger.warning(
                _("Bark 任务结果通知发送失败：{error}").format(error=error),
            )

    @staticmethod
    def _account_request_failure_reason(error: Exception | None) -> str:
        response = getattr(error, "response", None)
        status_code = getattr(response, "status_code", None)
        if status_code is None:
            status_code = getattr(error, "status_code", None)
        try:
            status_code = int(status_code) if status_code is not None else None
        except (TypeError, ValueError):
            status_code = None
        if status_code == 403:
            return _("HTTP 403 Forbidden（Cookie 或采集身份可能已失效）")
        if status_code is not None:
            return _("采集请求失败（HTTP {status}）").format(status=status_code)
        return _("账号作品下载失败")

    @classmethod
    def _account_exception_outcome(cls, error: Exception | None) -> dict:
        reason = cls._account_request_failure_reason(error)
        category = cls._account_failure_category(reason)
        error_type = type(error).__name__.lower() if error is not None else ""
        if "timeout" in error_type:
            code = "request_timeout"
            category = "network"
            reason = _("账号采集请求超时")
        elif category == "identity":
            code = "identity_forbidden"
        elif category == "network":
            code = "network_error"
        else:
            code = "runtime_error"
            reason = _("账号处理过程中发生未分类异常")
        return {
            "ok": False,
            "context": {},
            "outcome_code": code,
            "reason": reason,
            "failure_category": category,
            "terminal_status": "failed",
            "retryable": True,
            "cross_identity": category in {"identity", "network"},
            "affects_identity_health": category in {"identity", "network"},
        }

    @classmethod
    def _normalize_account_worker_outcome(cls, value: Any) -> dict:
        if isinstance(value, dict) and value.get("outcome_code"):
            result = dict(value)
            result["context"] = (
                result.get("context")
                if isinstance(result.get("context"), dict)
                else {}
            )
            result["ok"] = bool(result.get("ok"))
            result["terminal_status"] = str(
                result.get("terminal_status")
                or ("success" if result["ok"] else "failed")
            )
            result["failure_category"] = str(
                result.get("failure_category")
                or cls._account_failure_category(
                    result.get("reason"),
                    result.get("outcome_code"),
                )
            )
            return result
        if value:
            context = value if isinstance(value, dict) else {}
            return {
                "ok": True,
                "context": context,
                "outcome_code": "success",
                "reason": "",
                "failure_category": "",
                "terminal_status": "success",
                "retryable": False,
                "cross_identity": False,
                "affects_identity_health": False,
            }
        # Compatibility for third-party/older workers that still return None.
        # The native worker now returns a structured reason instead.
        return {
            "ok": False,
            "context": {},
            "outcome_code": "legacy_empty_result",
            "reason": _("账号处理未返回结果，旧版采集器未提供具体原因"),
            "failure_category": "other",
            "terminal_status": "failed",
            "retryable": True,
            "cross_identity": True,
            "affects_identity_health": True,
        }

    @staticmethod
    def _account_failure_category(reason: Any, outcome_code: Any = "") -> str:
        code = str(outcome_code or "").strip().lower()
        if code in {
            "identity_forbidden",
            "rate_limited",
            "risk_control",
        }:
            return "identity"
        if code in {
            "private_followed_empty",
            "private_not_visible",
            "works_not_visible",
        }:
            return "visibility"
        if code in {
            "account_deleted",
            "profile_unavailable",
            "account_unavailable",
        }:
            return "account_unavailable"
        if code in {
            "request_timeout",
            "network_error",
            "upstream_unavailable",
        }:
            return "network"
        if code == "download_failed":
            return "download"
        if code in {"invalid_account_url", "parse_failed"}:
            return "parse"
        text = str(reason or "").strip().lower()
        if any(
            hint in text
            for hint in (
                "403",
                "forbidden",
                "cookie",
                "身份",
                "登录",
                "验证",
                "captcha",
                "risk",
            )
        ):
            return "identity"
        if any(
            hint in text
            for hint in (
                "已注销",
                "不存在",
                "私密",
                "account not found",
                "user not found",
                "deleted",
            )
        ):
            return "account_unavailable"
        if any(
            hint in text
            for hint in (
                "timeout",
                "timed out",
                "proxy",
                "network",
                "connect",
                "http 5",
                "网络",
                "连接",
                "超时",
            )
        ):
            return "network"
        if any(hint in text for hint in ("下载", "保存", "write", "ffmpeg")):
            return "download"
        if any(hint in text for hint in ("解析", "提取", "parse", "decode")):
            return "parse"
        return "other"

    @classmethod
    def _task_account_with_category(cls, account: dict) -> dict:
        result = dict(account)
        outcome = account.get("result")
        outcome = outcome if isinstance(outcome, dict) else {}
        for key in (
            "outcome_code",
            "retryable",
            "attempted_identities",
            "recovered_by_identity",
            "failure_category",
            "context",
        ):
            if key in outcome:
                result[key] = outcome[key]
        category = str(result.get("failure_category") or "").strip().lower()
        if category not in cls.ACCOUNT_FAILURE_CATEGORIES:
            category = cls._account_failure_category(
                account.get("reason"),
                result.get("outcome_code"),
            )
        result["outcome_category"] = category
        result["failure_category"] = (
            category if account.get("status") == "failed" else ""
        )
        return result

    @staticmethod
    def _normalize_optional_int(value: Any) -> int | None:
        if value in {
            None,
            "",
        }:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _normalize_schedule_type(cls, value: Any) -> str:
        text = cls._normalize_string(value).lower()
        if text == cls.COLLECT_MONITOR_SCHEDULE:
            return cls.COLLECT_MONITOR_SCHEDULE
        return cls.ACCOUNT_BATCH_SCHEDULE

    @staticmethod
    def _normalize_collect_tab(value: Any) -> str:
        tab = APIServer._normalize_string(value).lower()
        if tab in {"post", "favorite", "collection"}:
            return tab
        return "post"

    @staticmethod
    def _normalize_collect_limit(value: Any, default: int = 10) -> int:
        try:
            number = int(value)
        except (TypeError, ValueError):
            number = default
        return max(1, min(number, 60))

    @staticmethod
    def _normalize_collect_interval(value: Any, default: int = 30) -> int:
        try:
            number = int(value)
        except (TypeError, ValueError):
            number = default
        return max(1, min(number, 24 * 60))

    @staticmethod
    def _normalize_account_url(url: str) -> str:
        value = APIServer._normalize_string(url)
        if not value:
            return ""
        try:
            parsed = urlsplit(value)
            path = parsed.path.rstrip("/")
            if parsed.scheme and parsed.netloc:
                base = f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{path}"
                return base
        except ValueError:
            pass
        return value.split("?", 1)[0].split("#", 1)[0].rstrip("/")

    @staticmethod
    def _normalize_match_token(value: str) -> str:
        text = APIServer._normalize_string(value).lower()
        if not text:
            return ""
        return sub(r"[^0-9a-z\u4e00-\u9fff]+", "", text)

    @staticmethod
    def _normalize_account_items(items: list[dict]) -> list[dict]:
        results = []
        for item in items:
            if not isinstance(item, dict):
                continue
            results.append(
                {
                    "mark": APIServer._normalize_string(item.get("mark")),
                    "url": APIServer._normalize_string(item.get("url")),
                    "tab": APIServer._normalize_string(item.get("tab")) or "post",
                    "earliest": APIServer._normalize_string(item.get("earliest")),
                    "latest": APIServer._normalize_string(item.get("latest")),
                    "enable": APIServer._normalize_bool(
                        item.get("enable"),
                        default=True,
                    ),
                    "auto_update_earliest": APIServer._normalize_bool(
                        item.get("auto_update_earliest"),
                        default=False,
                    ),
                    "pages": APIServer._normalize_optional_int(item.get("pages")),
                }
            )
        return results

    @staticmethod
    def _validate_ui_workflow_account_payload(payload: dict) -> None:
        use_settings = payload.get("use_settings", True)
        if not isinstance(use_settings, bool):
            raise ValueError("use_settings must be a boolean value.")
        items = payload.get("items", [])
        if not isinstance(items, list):
            raise ValueError("items must be a list.")
        for item in items:
            if not isinstance(item, dict):
                raise ValueError("items must be a list of objects.")
        for key in (
            "cookie",
            "proxy",
            "identity_id",
        ):
            value = payload.get(key)
            if value is not None and not isinstance(value, str):
                raise ValueError(f"{key} must be string or null.")
        action = APIServer._normalize_string(payload.get("identity_failure_action"))
        if action and action not in APIServer.IDENTITY_FAILURE_ACTIONS:
            raise ValueError("identity_failure_action must be continue or pause.")
        notify = payload.get("notify_on_identity_failure")
        if notify is not None and not isinstance(notify, bool):
            raise ValueError("notify_on_identity_failure must be bool.")
        threshold = payload.get("identity_failure_threshold")
        if threshold not in {None, ""}:
            try:
                threshold_value = int(threshold)
            except (TypeError, ValueError):
                raise ValueError("identity_failure_threshold must be integer.")
            if not 1 <= threshold_value <= 20:
                raise ValueError("identity_failure_threshold must be between 1 and 20.")

    @staticmethod
    def _validate_ui_avatar_batch_payload(payload: dict) -> None:
        platform = APIServer._normalize_string(payload.get("platform")).lower()
        if platform not in {"douyin", "tiktok"}:
            raise ValueError("platform must be douyin or tiktok.")
        urls = payload.get("urls", [])
        if not isinstance(urls, list) or any(
            not isinstance(item, str) for item in urls
        ):
            raise ValueError("urls must be a string list.")
        for key in ("skip_existing",):
            value = payload.get(key)
            if value is not None and not isinstance(value, bool):
                raise ValueError(f"{key} must be boolean.")
        raw_candidates = payload.get("max_candidates", 12)
        try:
            candidates = int(raw_candidates)
        except (TypeError, ValueError):
            raise ValueError("max_candidates must be integer.") from None
        if not 1 <= candidates <= 30:
            raise ValueError("max_candidates must be between 1 and 30.")

    @staticmethod
    def _normalize_link_inputs(raw_links: str | list[str]) -> list[str]:
        if isinstance(raw_links, str):
            lines = raw_links.splitlines()
        else:
            lines = [item for item in raw_links if isinstance(item, str)]
        return [line.strip() for line in lines if isinstance(line, str) and line.strip()]

    @staticmethod
    def _validate_ui_workflow_detail_payload(payload: dict) -> None:
        raw_links = payload.get("links")
        if not isinstance(raw_links, (str, list)):
            raise ValueError("links must be a string or a string list.")
        if isinstance(raw_links, list) and any(
            not isinstance(item, str) for item in raw_links
        ):
            raise ValueError("links list only accepts string items.")
        if not APIServer._normalize_link_inputs(raw_links):
            raise ValueError("links cannot be empty.")
        for key in (
            "cookie",
            "proxy",
            "identity_id",
        ):
            value = payload.get(key)
            if value is not None and not isinstance(value, str):
                raise ValueError(f"{key} must be string or null.")

    @staticmethod
    def _normalize_deleted_account_items(items: list[dict]) -> list[dict]:
        results = []
        if not isinstance(items, list):
            return results
        for item in items:
            if not isinstance(item, dict):
                continue
            url = APIServer._normalize_string(item.get("url"))
            if not url:
                continue
            results.append(
                {
                    "mark": APIServer._normalize_string(item.get("mark")),
                    "url": url,
                    "tab": APIServer._normalize_string(item.get("tab")) or "post",
                    "earliest": APIServer._normalize_string(item.get("earliest")),
                    "latest": APIServer._normalize_string(item.get("latest")),
                    "enable": APIServer._normalize_bool(
                        item.get("enable"),
                        default=False,
                    ),
                    "auto_update_earliest": APIServer._normalize_bool(
                        item.get("auto_update_earliest"),
                        default=False,
                    ),
                    "deleted_at": APIServer._normalize_string(item.get("deleted_at")),
                    "reason": APIServer._normalize_string(item.get("reason")),
                }
            )
        return results

    @staticmethod
    def _merge_deleted_accounts(current: list[dict], incoming: list[dict]) -> list[dict]:
        merged = []
        seen = set()
        for item in [*current, *incoming]:
            key = APIServer._normalize_string(item.get("url"))
            if not key or key in seen:
                continue
            seen.add(key)
            merged.append(item)
        return merged

    def _account_rows(self, tiktok: bool, deleted: bool = False) -> list[dict]:
        if deleted:
            return (
                self.parameter.deleted_accounts_tiktok
                if tiktok
                else self.parameter.deleted_accounts
            )
        rows = (
            self.parameter.accounts_urls_tiktok
            if tiktok
            else self.parameter.accounts_urls
        )
        return [vars(item) for item in rows]

    def _set_account_rows(
        self,
        tiktok: bool,
        rows: list[dict],
        deleted: bool = False,
    ) -> None:
        if deleted:
            if tiktok:
                self.parameter.deleted_accounts_tiktok = self.parameter.check_deleted_accounts(
                    rows
                )
            else:
                self.parameter.deleted_accounts = self.parameter.check_deleted_accounts(rows)
            return
        checked = self.parameter.check_urls_params(rows)
        if tiktok:
            self.parameter.accounts_urls_tiktok = checked
        else:
            self.parameter.accounts_urls = checked

    def _sync_account_payload_to_runtime(self, payload: dict) -> dict:
        active_douyin = self._normalize_account_items(payload.get("accounts_urls", []))
        active_tiktok = self._normalize_account_items(
            payload.get("accounts_urls_tiktok", []),
        )
        deleted_douyin = self._normalize_deleted_account_items(
            payload.get("deleted_accounts", []),
        )
        deleted_tiktok = self._normalize_deleted_account_items(
            payload.get("deleted_accounts_tiktok", []),
        )
        self._set_account_rows(False, active_douyin)
        self._set_account_rows(True, active_tiktok)
        self._set_account_rows(False, deleted_douyin, deleted=True)
        self._set_account_rows(True, deleted_tiktok, deleted=True)
        self.parameter.settings.update(self.parameter.get_settings_data())
        return {
            "accounts_urls": self._account_rows(False),
            "accounts_urls_tiktok": self._account_rows(True),
            "deleted_accounts": self._account_rows(False, deleted=True),
            "deleted_accounts_tiktok": self._account_rows(True, deleted=True),
        }

    def _archive_account_configuration(
        self,
        *,
        platform: str,
        url: str,
        reason: str = "",
    ) -> dict:
        result = self._archive_account_configurations(
            platform=platform,
            urls=[url],
            reason=reason,
        )
        archived_accounts = result.pop("archived_accounts", [])
        normalized_url = result.get("urls", [self._normalize_account_url(url)])[0]
        return {
            **result,
            "message": (
                _("账号已移入删除区。")
                if result["archived_count"]
                else _("账号已不在采集名单中。")
            ),
            "archived": bool(result["archived_count"]),
            "assignment_removed": bool(result["assignment_removed"]),
            "url": normalized_url,
            "archived_account": archived_accounts[0] if archived_accounts else None,
        }

    def _archive_account_configurations(
        self,
        *,
        platform: str,
        urls: list,
        reason: str = "",
    ) -> dict:
        normalized_platform = self._normalize_string(platform).lower()
        if normalized_platform not in {"douyin", "tiktok"}:
            raise ValueError("platform must be douyin or tiktok.")
        if not isinstance(urls, list) or not urls:
            raise ValueError("urls must be a non-empty list.")
        if len(urls) > 500:
            raise ValueError("urls cannot contain more than 500 items.")
        normalized_urls = []
        seen_urls = set()
        for raw_url in urls:
            if not isinstance(raw_url, str):
                raise ValueError("each url must be a string.")
            normalized_url = self._normalize_account_url(raw_url)
            if not normalized_url:
                raise ValueError("each url is required.")
            if normalized_url not in seen_urls:
                normalized_urls.append(normalized_url)
                seen_urls.add(normalized_url)

        tiktok = normalized_platform == "tiktok"
        active_rows = [dict(item) for item in self._account_rows(tiktok)]
        removed_rows = [
            item
            for item in active_rows
            if self._normalize_account_url(item.get("url", "")) in seen_urls
        ]
        if not removed_rows:
            return {
                "message": _("所选账号已不在采集名单中。"),
                "archived_count": 0,
                "removed_count": 0,
                "assignment_removed": 0,
                "backup_path": "",
                "platform": normalized_platform,
                "urls": normalized_urls,
                "archived_accounts": [],
                "accounts_urls": self._account_rows(False),
                "accounts_urls_tiktok": self._account_rows(True),
                "deleted_accounts": self._account_rows(False, deleted=True),
                "deleted_accounts_tiktok": self._account_rows(True, deleted=True),
            }

        backup_path = self._backup_settings_file(
            reason=f"task_account_archive_batch_{normalized_platform}",
        )
        remaining_rows = [
            item
            for item in active_rows
            if self._normalize_account_url(item.get("url", "")) not in seen_urls
        ]
        archive_reason = (
            self._normalize_string(reason)[:300]
            or _("从任务失败记录手动移出采集名单")
        )
        removed_by_url = {}
        for row in removed_rows:
            normalized_url = self._normalize_account_url(row.get("url", ""))
            removed_by_url.setdefault(normalized_url, row)
        deleted_at = self._now_text()
        archived_rows = [
            {
                **removed_by_url[normalized_url],
                "url": self._normalize_string(
                    removed_by_url[normalized_url].get("url")
                )
                or normalized_url,
                "enable": False,
                "deleted_at": deleted_at,
                "reason": archive_reason,
            }
            for normalized_url in normalized_urls
            if normalized_url in removed_by_url
        ]
        archived_url_set = set(removed_by_url)
        deleted_rows = [
            dict(item)
            for item in self._account_rows(tiktok, deleted=True)
            if self._normalize_account_url(item.get("url", ""))
            not in archived_url_set
        ]
        self._set_account_rows(tiktok, remaining_rows)
        self._set_account_rows(tiktok, [*archived_rows, *deleted_rows], deleted=True)
        self.parameter.settings.update(self.parameter.get_settings_data())

        assignment_removed = 0
        for normalized_url in removed_by_url:
            try:
                assignment_removed += int(
                    bool(
                        self.collector_store.delete_assignment(
                            self._collector_platform(normalized_platform),
                            "account",
                            normalized_url,
                        )
                    )
                )
            except Exception as error:
                self.logger.warning(
                    _("清理已归档账号的身份绑定失败: {error}").format(error=error)
                )
        self.logger.info(
            _(
                "已从采集名单批量移出 {accounts} 个账号"
                "（{platform}，匹配 {rows} 条配置）"
            ).format(
                accounts=len(archived_rows),
                platform=normalized_platform,
                rows=len(removed_rows),
            )
        )
        return {
            "message": _("所选账号已移入删除区。"),
            "archived_count": len(archived_rows),
            "removed_count": len(removed_rows),
            "assignment_removed": assignment_removed,
            "backup_path": backup_path,
            "platform": normalized_platform,
            "urls": normalized_urls,
            "archived_accounts": archived_rows,
            "accounts_urls": self._account_rows(False),
            "accounts_urls_tiktok": self._account_rows(True),
            "deleted_accounts": self._account_rows(False, deleted=True),
            "deleted_accounts_tiktok": self._account_rows(True, deleted=True),
        }

    @staticmethod
    def _normalize_board_platform(platform: str) -> str:
        return "tiktok" if APIServer._normalize_string(platform).lower() == "tiktok" else "douyin"

    @staticmethod
    def _normalize_board_page(page: int) -> int:
        try:
            return max(int(page), 1)
        except (TypeError, ValueError):
            return 1

    @staticmethod
    def _normalize_board_page_size(page_size: int, default: int = 24) -> int:
        try:
            size = int(page_size)
        except (TypeError, ValueError):
            return default
        return max(6, min(size, 80))

    def _account_board_pin_file(self) -> Path:
        return self.parameter.settings.path.parent.joinpath("account_profile_pins.json")

    def _load_account_board_pins(self) -> dict[str, str]:
        pin_file = self._account_board_pin_file()
        if not pin_file.exists():
            return {}
        try:
            payload = loads(pin_file.read_text(encoding=self.parameter.settings.encode))
        except (JSONDecodeError, OSError, TypeError, ValueError):
            return {}
        if not isinstance(payload, dict):
            return {}
        source = payload.get("pins", payload)
        if not isinstance(source, dict):
            return {}
        pins = {}
        for key, value in source.items():
            k = self._normalize_string(key)
            v = self._normalize_string(value).replace("\\", "/").lstrip("/")
            if k and v:
                pins[k] = v
        return pins

    def _save_account_board_pins(self, pins: dict[str, str]) -> None:
        pin_file = self._account_board_pin_file()
        if not pin_file.parent.exists():
            pin_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "updated_at": self._now_text(),
            "pins": pins,
        }
        pin_file.write_text(
            dumps(payload, ensure_ascii=False, indent=2),
            encoding=self.parameter.settings.encode,
        )

    def _account_board_avatar_file(self) -> Path:
        return self.parameter.settings.path.parent.joinpath("account_profile_avatars.json")

    def _load_account_board_avatars(self) -> dict[str, str]:
        avatar_file = self._account_board_avatar_file()
        if not avatar_file.exists():
            return {}
        try:
            payload = loads(avatar_file.read_text(encoding=self.parameter.settings.encode))
        except (JSONDecodeError, OSError, TypeError, ValueError):
            return {}
        if not isinstance(payload, dict):
            return {}
        source = payload.get("avatars", payload)
        if not isinstance(source, dict):
            return {}
        avatars = {}
        for key, value in source.items():
            account_key = self._normalize_string(key)
            if not account_key:
                continue
            if isinstance(value, dict):
                raw_path = self._normalize_string(value.get("path"))
            else:
                raw_path = self._normalize_string(value)
            avatar_path = self._coerce_project_image_relpath(raw_path)
            if avatar_path:
                avatars[account_key] = avatar_path
        return avatars

    def _save_account_board_avatars(self, avatars: dict[str, str]) -> None:
        avatar_file = self._account_board_avatar_file()
        if not avatar_file.parent.exists():
            avatar_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "updated_at": self._now_text(),
            "folder": self.parameter.profile_avatar_folder,
            "avatars": avatars,
        }
        avatar_file.write_text(
            dumps(payload, ensure_ascii=False, indent=2),
            encoding=self.parameter.settings.encode,
        )

    @staticmethod
    def _account_pin_key(platform: str, url: str) -> str:
        normalized_platform = APIServer._normalize_board_platform(platform)
        return f"{normalized_platform}::{APIServer._normalize_string(url)}"

    def _profile_avatar_root(self) -> Path:
        folder_name = self.parameter.CLEANER.filter_name(
            self._normalize_string(
                getattr(self.parameter, "profile_avatar_folder", "profile_avatars")
            ),
            "profile_avatars",
        )
        root = self.parameter.settings.path.parent.joinpath(folder_name)
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _coerce_project_image_relpath(self, path: str) -> str:
        value = self._normalize_string(path).replace("\\", "/").lstrip("/")
        if not value:
            return ""
        try:
            target = resolve_within_root(PROJECT_ROOT, value)
        except ValueError:
            return ""
        if not target.exists() or not target.is_file():
            return ""
        if target.suffix.lower() not in IMAGE_SUFFIXES:
            return ""
        return relative_path(PROJECT_ROOT, target)

    def _coerce_scope_media_relpath(
        self,
        scope: ScopeType,
        path: str,
        allow_video: bool = True,
    ) -> str:
        value = self._normalize_string(path).replace("\\", "/").lstrip("/")
        if not value:
            return ""
        root = self._scope_root(scope).expanduser().resolve()
        try:
            target = resolve_within_root(root, value)
        except ValueError:
            return ""
        if not target.exists() or not target.is_file():
            return ""
        suffix = target.suffix.lower()
        allowed = IMAGE_SUFFIXES | VIDEO_SUFFIXES if allow_video else IMAGE_SUFFIXES
        if suffix not in allowed:
            return ""
        return relative_path(root, target)

    def _account_avatar_output_path(
        self,
        platform: str,
        url: str,
        mark: str = "",
        extension: str = ".jpg",
    ) -> Path:
        token = ""
        if mark:
            token = self.parameter.CLEANER.filter_name(mark, "")
        if not token:
            tokens = self._extract_account_tokens(url)
            if tokens:
                token = self.parameter.CLEANER.filter_name(tokens[0], "")
        if not token:
            token = "account"
        digest = md5(f"{platform}:{url}".encode("utf-8")).hexdigest()[:12]
        filename = f"{token}_{digest}{extension}"
        root = self._profile_avatar_root().joinpath(platform)
        root.mkdir(parents=True, exist_ok=True)
        return root.joinpath(filename)

    def _set_account_avatar_path(self, platform: str, url: str, path: str) -> str:
        avatar_rel = self._coerce_project_image_relpath(path)
        if not avatar_rel:
            return ""
        avatars = self._load_account_board_avatars()
        avatars[self._account_pin_key(platform, url)] = avatar_rel
        self._save_account_board_avatars(avatars)
        return avatar_rel

    @staticmethod
    def _extract_account_tokens(url: str) -> list[str]:
        value = APIServer._normalize_string(url).lower()
        if not value:
            return []
        tokens = set()
        try:
            parsed = urlsplit(value)
            for segment in [item for item in parsed.path.split("/") if item]:
                token = segment.strip().split("?", 1)[0].split("#", 1)[0]
                if token.startswith("@"):
                    token = token[1:]
                token = token.strip()
                if len(token) >= 4 and token not in {"user", "post", "video", "favorite", "collection"}:
                    tokens.add(token)
        except ValueError:
            pass
        if "@" in value:
            token = (
                value.split("@", 1)[1]
                .split("/", 1)[0]
                .split("?", 1)[0]
                .split("#", 1)[0]
                .strip()
            )
            if len(token) >= 3:
                tokens.add(token)
        return sorted(tokens, key=len, reverse=True)

    def _account_board_dirs(self, root: Path) -> list[Path]:
        if not root.exists() or not root.is_dir():
            return []
        try:
            return [
                item
                for item in root.iterdir()
                if item.is_dir() and item.name.startswith("UID")
            ]
        except OSError:
            return []

    @staticmethod
    def _account_board_folder_updated_at(folder: Path | None) -> str:
        if not folder:
            return ""
        try:
            return (
                datetime.fromtimestamp(folder.stat().st_mtime)
                .astimezone()
                .isoformat(timespec="seconds")
            )
        except (OSError, OverflowError, ValueError):
            return ""

    def _account_match_tokens(self, value: str) -> list[str]:
        raw = self._normalize_string(value).lower()
        if not raw:
            return []
        tokens = {raw}
        cleaned = self.parameter.CLEANER.filter_name(raw, "").lower()
        if cleaned:
            tokens.add(cleaned)
        normalized = self._normalize_match_token(raw)
        if normalized:
            tokens.add(normalized)
        return sorted(tokens, key=len, reverse=True)

    def _account_board_dir_match_index(
        self,
        candidates: list[Path],
    ) -> list[tuple[Path, str, str, str]]:
        index = []
        for folder in candidates:
            name = folder.name.lower()
            index.append(
                (
                    folder,
                    name,
                    self.parameter.CLEANER.filter_name(name, "").lower(),
                    self._normalize_match_token(name),
                )
            )
        return index

    def _account_board_dir_mark_index(
        self,
        candidates: list[Path],
    ) -> dict[str, list[Path]]:
        index: dict[str, list[Path]] = {}
        for folder in candidates:
            name = folder.name
            if "_" not in name:
                continue
            account_name = name.split("_", 1)[1]
            variants = {account_name}
            if "_" in account_name:
                variants.add(account_name.rsplit("_", 1)[0])
            for variant in variants:
                for token in self._account_match_tokens(variant):
                    folders = index.setdefault(token, [])
                    if folder not in folders:
                        folders.append(folder)
        return index

    def _account_board_mark_candidates(
        self,
        mark: str,
        mark_index: dict[str, list[Path]],
    ) -> list[Path]:
        candidates = []
        seen = set()
        for token in self._account_match_tokens(mark):
            for folder in mark_index.get(token, []):
                if folder in seen:
                    continue
                seen.add(folder)
                candidates.append(folder)
        return candidates

    def _match_account_board_dir(
        self,
        mark: str,
        url: str,
        candidates: list[Path],
        candidate_index: list[tuple[Path, str, str, str]] | None = None,
    ) -> Path | None:
        if not candidates:
            return None
        mark_tokens = self._account_match_tokens(mark)
        url_tokens: list[str] = []
        for token in self._extract_account_tokens(url):
            url_tokens.extend(self._account_match_tokens(token))
        best_dir = None
        best_score = 0
        indexed_candidates = (
            candidate_index
            if candidate_index is not None
            else self._account_board_dir_match_index(candidates)
        )
        for folder, name, cleaned_name, normalized_name in indexed_candidates:
            score = 0
            for mark_token in mark_tokens:
                if not mark_token:
                    continue
                normalized_mark_token = self._normalize_match_token(mark_token)
                if (
                    f"_{mark_token}_" in name
                    or f"_{mark_token}_" in cleaned_name
                    or mark_token in name
                    or mark_token in cleaned_name
                    or (
                        normalized_mark_token
                        and normalized_mark_token in normalized_name
                    )
                ):
                    score += 120
                    break
            for token in url_tokens:
                if not token:
                    continue
                normalized_url_token = self._normalize_match_token(token)
                if (
                    token in name
                    or token in cleaned_name
                    or (
                        normalized_url_token
                        and normalized_url_token in normalized_name
                    )
                ):
                    score += 26
            if score > best_score:
                best_dir = folder
                best_score = score
        return best_dir if best_score > 0 else None

    def _coerce_media_relpath(self, root: Path, path: str) -> str:
        value = self._normalize_string(path).replace("\\", "/").lstrip("/")
        if not value:
            return ""
        try:
            target = resolve_within_root(root, value)
        except ValueError:
            return ""
        if not target.exists() or not target.is_file():
            return ""
        suffix = target.suffix.lower()
        if suffix not in IMAGE_SUFFIXES and suffix not in VIDEO_SUFFIXES:
            return ""
        return relative_path(root, target)

    def _collect_media_relpaths(
        self,
        root: Path,
        folder: Path | None,
        cache: dict[str, tuple[list[str], list[str]]],
    ) -> tuple[list[str], list[str]]:
        if not folder:
            return [], []
        key = str(folder.resolve())
        if key in cache:
            return cache[key]
        images = []
        videos = []
        if folder.exists() and folder.is_dir():
            try:
                for path in folder.rglob("*"):
                    if not path.is_file():
                        continue
                    suffix = path.suffix.lower()
                    if suffix in IMAGE_SUFFIXES:
                        images.append(relative_path(root, path))
                    elif suffix in VIDEO_SUFFIXES:
                        videos.append(relative_path(root, path))
                    if len(images) + len(videos) >= 1200:
                        break
            except OSError:
                images = []
                videos = []
        images.sort(reverse=True)
        videos.sort(reverse=True)
        cache[key] = (images, videos)
        return images, videos

    @staticmethod
    def _latest_work_from_media_paths(paths: list[str]) -> dict[str, str]:
        latest_at = ""
        latest_path = ""
        for relative in paths:
            match = WORK_FILENAME_DATE_PATTERN.search(Path(relative).name)
            if not match:
                continue
            parts = [int(value or 0) for value in match.groups()]
            year, month, day, hour, minute, second = parts
            try:
                published_at = datetime(
                    year,
                    month,
                    day,
                    hour,
                    minute,
                    second,
                ).astimezone().isoformat(timespec="seconds")
            except ValueError:
                continue
            if published_at > latest_at:
                latest_at = published_at
                latest_path = relative
        return {
            "at": latest_at,
            "path": latest_path,
        }

    @staticmethod
    def _media_kind_from_relpath(path: str) -> str:
        suffix = Path(path).suffix.lower()
        if suffix in IMAGE_SUFFIXES:
            return "image"
        if suffix in VIDEO_SUFFIXES:
            return "video"
        return "file"

    @staticmethod
    def _normalize_media_prefer_kind(value: Any) -> str:
        kind = APIServer._normalize_string(value).lower()
        if kind in {"image", "video"}:
            return kind
        return "auto"

    def _pick_account_board_media(
        self,
        root: Path,
        folder: Path | None,
        cache: dict[str, tuple[list[str], list[str]]],
        pinned_path: str = "",
        exclude_path: str = "",
        use_pinned: bool = True,
        prefer_kind: str = "auto",
    ) -> dict[str, Any]:
        exclude_rel = self._coerce_media_relpath(root, exclude_path)
        if use_pinned:
            pinned_rel = self._coerce_media_relpath(root, pinned_path)
            if pinned_rel and pinned_rel != exclude_rel:
                return {
                    "path": pinned_rel,
                    "kind": self._media_kind_from_relpath(pinned_rel),
                    "pinned": True,
                }

        images, videos = self._collect_media_relpaths(root, folder, cache)
        media_order = [images, videos]
        preferred = self._normalize_media_prefer_kind(prefer_kind)
        if preferred == "video":
            media_order = [videos, images]
        elif preferred == "image":
            media_order = [images, videos]

        selected = ""
        for pool in media_order:
            candidates = pool
            if exclude_rel and len(candidates) > 1:
                candidates = [item for item in candidates if item != exclude_rel]
            if candidates:
                selected = choice(candidates)
                break
        if not selected:
            return {
                "path": "",
                "kind": "",
                "pinned": False,
            }
        return {
            "path": selected,
            "kind": self._media_kind_from_relpath(selected),
            "pinned": False,
        }

    def _build_account_board_gallery(
        self,
        platform: str,
        url: str,
        page: int,
        page_size: int,
        media_kind: str = "all",
    ) -> dict[str, Any]:
        normalized_platform = self._normalize_board_platform(platform)
        account_url = self._normalize_string(url)
        row = self._find_active_account_row(normalized_platform, account_url)
        if not row:
            raise LookupError("account_not_found")

        root = self._scope_root("download").expanduser().resolve()
        candidates = self._account_board_dirs(root)
        mark_index = self._account_board_dir_mark_index(candidates)
        mark_candidates = self._account_board_mark_candidates(
            row.get("mark", ""),
            mark_index,
        )
        if len(mark_candidates) == 1:
            folder = mark_candidates[0]
        else:
            match_candidates = mark_candidates or candidates
            folder = self._match_account_board_dir(
                mark=row.get("mark", ""),
                url=account_url,
                candidates=match_candidates,
                candidate_index=self._account_board_dir_match_index(match_candidates),
            )

        normalized_kind = self._normalize_string(media_kind).lower()
        if normalized_kind not in {"all", "image", "video"}:
            normalized_kind = "all"
        try:
            normalized_size = int(page_size)
        except (TypeError, ValueError):
            normalized_size = 24
        normalized_size = max(12, min(normalized_size, 72))

        gallery_limit = 10_000
        image_total = 0
        video_total = 0
        truncated = False
        all_entries = []
        if folder and folder.exists() and folder.is_dir():
            try:
                for target in folder.rglob("*"):
                    if not target.is_file():
                        continue
                    suffix = target.suffix.lower()
                    if suffix not in IMAGE_SUFFIXES and suffix not in VIDEO_SUFFIXES:
                        continue
                    try:
                        media_path = relative_path(root, target)
                        resolved = resolve_within_root(root, media_path)
                        if self._is_protected_file_scope_path(
                            "download",
                            root,
                            resolved,
                        ):
                            continue
                        all_entries.append(serialize_entry(root, resolved))
                    except (OSError, ValueError):
                        continue
                    if suffix in IMAGE_SUFFIXES:
                        image_total += 1
                    else:
                        video_total += 1
                    if len(all_entries) >= gallery_limit:
                        truncated = True
                        break
            except OSError:
                all_entries = []
                image_total = 0
                video_total = 0
        all_entries.sort(
            key=lambda item: (
                self._normalize_string(item.get("modified_at")),
                self._normalize_string(item.get("name")).casefold(),
            ),
            reverse=True,
        )
        entries = [
            item
            for item in all_entries
            if normalized_kind == "all" or item.get("kind") == normalized_kind
        ]

        total = len(entries)
        pages = max(1, (total + normalized_size - 1) // normalized_size)
        current = min(self._normalize_board_page(page), pages)
        offset = (current - 1) * normalized_size
        return {
            "platform": normalized_platform,
            "url": account_url,
            "mark": self._normalize_string(row.get("mark")),
            "folder_found": bool(folder),
            "folder_path": relative_path(root, folder) if folder else "",
            "folder_updated_at": self._account_board_folder_updated_at(folder),
            "kind": normalized_kind,
            "page": current,
            "page_size": normalized_size,
            "pages": pages,
            "total": total,
            "image_total": image_total,
            "video_total": video_total,
            "truncated": truncated,
            "index_limit": gallery_limit,
            "items": entries[offset:offset + normalized_size],
        }

    def _active_account_rows(self, platform: str) -> list[dict]:
        tiktok = self._normalize_board_platform(platform) == "tiktok"
        rows = self._normalize_account_items(self._account_rows(tiktok))
        return [item for item in rows if item.get("url")]

    def _find_active_account_row(self, platform: str, url: str) -> dict | None:
        target = self._normalize_string(url)
        if not target:
            return None
        for item in self._active_account_rows(platform):
            if self._normalize_string(item.get("url")) == target:
                return item
        return None

    def _build_account_board_page(
        self,
        platform: str,
        page: int,
        page_size: int,
        search: str = "",
        status: str = "all",
        sort_by: str = "configured",
    ) -> dict:
        normalized_platform = self._normalize_board_platform(platform)
        rows = self._active_account_rows(normalized_platform)
        unfiltered_total = len(rows)
        normalized_search = self._normalize_string(search).lower()
        normalized_status = self._normalize_string(status).lower()
        if normalized_status not in {
            "all",
            "success",
            "failed",
            "never",
            "no_avatar",
        }:
            normalized_status = "all"
        normalized_sort = self._normalize_string(sort_by).lower()
        if normalized_sort not in {
            "configured",
            "folder_updated_desc",
            "latest_desc",
            "latest_asc",
            "checked_desc",
        }:
            normalized_sort = "configured"

        journal = getattr(self, "task_journal", None)
        activity_items = (
            journal.list_account_activity(normalized_platform)
            if journal is not None
            else []
        )
        activity_by_url = {
            self._normalize_string(item.get("url")): item
            for item in activity_items
            if self._normalize_string(item.get("url"))
        }
        avatars = self._load_account_board_avatars()
        root = self._scope_root("download").expanduser().resolve()
        candidates = self._account_board_dirs(root)
        candidate_index = self._account_board_dir_match_index(candidates)
        candidate_mark_index = self._account_board_dir_mark_index(candidates)
        folder_by_account: dict[tuple[str, str], Path | None] = {}

        def account_folder(row: dict) -> Path | None:
            key = (
                self._normalize_string(row.get("url")),
                self._normalize_string(row.get("mark")),
            )
            if key not in folder_by_account:
                mark_candidates = (
                    self._account_board_mark_candidates(
                        row.get("mark", ""),
                        candidate_mark_index,
                    )
                    if candidates
                    else []
                )
                if len(mark_candidates) == 1:
                    folder_by_account[key] = mark_candidates[0]
                else:
                    match_candidates = mark_candidates or candidates
                    match_index = (
                        self._account_board_dir_match_index(match_candidates)
                        if mark_candidates
                        else candidate_index
                    )
                    folder_by_account[key] = self._match_account_board_dir(
                        mark=row.get("mark", ""),
                        url=row.get("url", ""),
                        candidates=match_candidates,
                        candidate_index=match_index,
                    )
            return folder_by_account[key]

        if normalized_search:
            rows = [
                row
                for row in rows
                if normalized_search
                in " ".join(
                    (
                        self._normalize_string(row.get("mark")),
                        self._normalize_string(row.get("url")),
                        self._normalize_string(row.get("tab")),
                    )
                ).lower()
            ]
        if normalized_status != "all":
            filtered_rows = []
            for row in rows:
                url = self._normalize_string(row.get("url"))
                activity = activity_by_url.get(url, {})
                if normalized_status == "no_avatar":
                    pin_key = self._account_pin_key(normalized_platform, url)
                    if not self._coerce_project_image_relpath(
                        avatars.get(pin_key, "")
                    ):
                        filtered_rows.append(row)
                    continue
                activity_status = self._normalize_string(
                    activity.get("last_status")
                ) or "never"
                if activity_status == normalized_status:
                    filtered_rows.append(row)
            rows = filtered_rows

        def activity_date(row: dict, key: str) -> str:
            return self._normalize_string(
                activity_by_url.get(
                    self._normalize_string(row.get("url")),
                    {},
                ).get(key)
            )

        if normalized_sort == "latest_desc":
            rows.sort(
                key=lambda row: max(
                    activity_date(row, "latest_seen_work_at"),
                    activity_date(row, "latest_saved_work_at"),
                ),
                reverse=True,
            )
        elif normalized_sort == "latest_asc":
            rows.sort(
                key=lambda row: (
                    not bool(
                        max(
                            activity_date(row, "latest_seen_work_at"),
                            activity_date(row, "latest_saved_work_at"),
                        )
                    ),
                    max(
                        activity_date(row, "latest_seen_work_at"),
                        activity_date(row, "latest_saved_work_at"),
                    ),
                )
            )
        elif normalized_sort == "checked_desc":
            rows.sort(
                key=lambda row: activity_date(row, "last_checked_at"),
                reverse=True,
            )
        elif normalized_sort == "folder_updated_desc":
            rows.sort(
                key=lambda row: self._account_board_folder_updated_at(
                    account_folder(row)
                ),
                reverse=True,
            )

        total = len(rows)
        size = self._normalize_board_page_size(page_size)
        pages = max(1, (total + size - 1) // size)
        current = min(self._normalize_board_page(page), pages)
        start = (current - 1) * size
        end = start + size
        page_rows = rows[start:end]

        pins = self._load_account_board_pins()
        media_cache: dict[str, tuple[list[str], list[str]]] = {}
        items = []
        for offset, row in enumerate(page_rows, start=start + 1):
            folder = account_folder(row)
            folder_updated_at = self._account_board_folder_updated_at(folder)
            pin_key = self._account_pin_key(normalized_platform, row.get("url", ""))
            media = self._pick_account_board_media(
                root=root,
                folder=folder,
                cache=media_cache,
                pinned_path=pins.get(pin_key, ""),
                use_pinned=True,
            )
            avatar_path = self._coerce_project_image_relpath(avatars.get(pin_key, ""))
            activity = activity_by_url.get(
                self._normalize_string(row.get("url")),
                {},
            )
            latest_seen_at = self._normalize_string(
                activity.get("latest_seen_work_at")
            )
            latest_saved_at = self._normalize_string(
                activity.get("latest_saved_work_at")
            )
            latest_work_at = max(latest_seen_at, latest_saved_at)
            latest_work_id = (
                self._normalize_string(activity.get("latest_seen_work_id"))
                if latest_seen_at >= latest_saved_at
                else self._normalize_string(activity.get("latest_saved_work_id"))
            )
            latest_work_source = "crawl" if latest_work_at else ""
            if not latest_work_at:
                images, videos = self._collect_media_relpaths(
                    root,
                    folder,
                    media_cache,
                )
                historical = self._latest_work_from_media_paths(
                    [*images, *videos]
                )
                latest_work_at = historical["at"]
                latest_work_source = "filename" if latest_work_at else ""
            items.append(
                {
                    "index": offset,
                    "platform": normalized_platform,
                    "url": row.get("url", ""),
                    "mark": row.get("mark", ""),
                    "tab": row.get("tab", "post"),
                    "enable": bool(row.get("enable", True)),
                    "folder_path": relative_path(root, folder) if folder else "",
                    "folder_name": folder.name if folder else "",
                    "folder_updated_at": folder_updated_at,
                    "media_path": media.get("path", ""),
                    "media_kind": media.get("kind", ""),
                    "pinned": bool(media.get("pinned", False)),
                    "avatar_path": avatar_path,
                    "avatar_scope": "project" if avatar_path else "",
                    "latest_work_at": latest_work_at,
                    "latest_work_id": latest_work_id,
                    "latest_work_source": latest_work_source,
                    "latest_seen_work_at": latest_seen_at,
                    "latest_saved_work_at": latest_saved_at,
                    "last_checked_at": self._normalize_string(
                        activity.get("last_checked_at")
                    ),
                    "last_status": self._normalize_string(
                        activity.get("last_status")
                    )
                    or "never",
                    "last_error": self._normalize_string(
                        activity.get("last_error")
                    ),
                    "last_item_count": int(
                        activity.get("last_item_count") or 0
                    ),
                }
            )

        return {
            "platform": normalized_platform,
            "page": current,
            "page_size": size,
            "pages": pages,
            "total": total,
            "unfiltered_total": unfiltered_total,
            "search": normalized_search,
            "status": normalized_status,
            "sort": normalized_sort,
            "items": items,
        }

    def _settings_backup_dir(self) -> Path:
        backup_dir = self.parameter.settings.path.parent.joinpath("backups")
        backup_dir.mkdir(exist_ok=True)
        return backup_dir

    def _ensure_maintenance_state(self) -> None:
        if not hasattr(self, "_maintenance_lock"):
            self._maintenance_lock = Lock()
        if not hasattr(self, "_storage_alert_pending_level"):
            self._storage_alert_pending_level = 0
        if hasattr(self, "_storage_alert_state_loaded"):
            return
        self._storage_alert_state_loaded = True
        self._storage_alert_last_level = 0
        try:
            payload = loads(
                self.parameter.settings.path.parent.joinpath(
                    ".storage_alert_state.json"
                ).read_text(encoding="utf-8")
            )
            self._storage_alert_last_level = max(
                0,
                int(payload.get("level") or 0),
            )
        except (OSError, TypeError, ValueError, JSONDecodeError):
            pass

    def _save_storage_alert_state(self, level: int) -> None:
        path = self.parameter.settings.path.parent.joinpath(
            ".storage_alert_state.json"
        )
        temporary = path.with_suffix(".tmp")
        temporary.write_text(
            dumps(
                {
                    "level": max(0, int(level or 0)),
                    "updated_at": self._now_text(),
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        temporary.replace(path)

    def _configured_bark_targets(self) -> list[str]:
        return sorted(
            {
                target
                for item in getattr(self, "ui_schedules", {}).values()
                if (target := self._normalize_string(item.get("bark_url")))
            }
        )

    async def _flush_storage_alert(self, media: dict) -> None:
        self._ensure_maintenance_state()
        level = int(getattr(self, "_storage_alert_pending_level", 0) or 0)
        if not level:
            return
        targets = self._configured_bark_targets()
        if not targets:
            return
        storage = media.get("storage") if isinstance(media, dict) else {}
        percent = float(storage.get("used_percent") or 0)
        free = int(storage.get("free") or 0)
        sent = False
        for bark_url in targets:
            ok, error = await self._send_bark_notification(
                bark_url,
                f"FetchShelf 存储告警：已使用 {percent:.1f}%",
                f"已触发 {level}% 阈值 · 剩余 {self._human_size(free)}",
            )
            sent = sent or ok
            if error:
                self.logger.warning(
                    _("Bark 存储告警发送失败：{error}").format(error=error)
                )
        if sent:
            self._storage_alert_last_level = level
            self._storage_alert_pending_level = 0
            self._save_storage_alert_state(level)

    @staticmethod
    def _backup_sqlite_database(source: Path, destination: Path) -> None:
        source_connection = sqlite_connect(source)
        destination_connection = sqlite_connect(destination)
        try:
            source_connection.backup(destination_connection)
        finally:
            destination_connection.close()
            source_connection.close()

    def _configuration_snapshot_files(self) -> list[tuple[Path, str]]:
        return [
            (self.parameter.settings.path, "settings.json"),
            (self.collector_store.path, "collector_pool.sqlite3"),
            (self.task_journal.path, "ui_task_runtime.sqlite3"),
        ]

    def _create_configuration_snapshot(self, reason: str = "manual") -> dict:
        self._ensure_maintenance_state()
        with self._maintenance_lock:
            backup_dir = self._settings_backup_dir()
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_reason = sub(
                r"[^a-zA-Z0-9_-]+",
                "-",
                self._normalize_string(reason) or "manual",
            ).strip("-")[:32] or "manual"
            destination = backup_dir.joinpath(
                f"fetchshelf_snapshot_{timestamp}_{safe_reason}.zip"
            )
            with TemporaryDirectory(dir=backup_dir) as temporary_dir:
                temporary_root = Path(temporary_dir)
                prepared: list[tuple[Path, str]] = []
                for source, archive_name in self._configuration_snapshot_files():
                    if not source.exists():
                        continue
                    staged = temporary_root.joinpath(archive_name)
                    if source.suffix.lower() in {".sqlite", ".sqlite3", ".db"}:
                        self._backup_sqlite_database(source, staged)
                    else:
                        copy2(source, staged)
                    prepared.append((staged, archive_name))
                with ZipFile(destination, "w", compression=ZIP_DEFLATED) as archive:
                    for source, archive_name in prepared:
                        archive.write(source, arcname=archive_name)
            snapshots = sorted(
                backup_dir.glob("fetchshelf_snapshot_*.zip"),
                key=lambda item: item.stat().st_mtime,
                reverse=True,
            )
            for expired in snapshots[self.CONFIGURATION_SNAPSHOT_RETENTION :]:
                expired.unlink(missing_ok=True)
            return {
                "name": destination.name,
                "created_at": datetime.fromtimestamp(destination.stat().st_mtime)
                .astimezone()
                .isoformat(timespec="seconds"),
                "size": destination.stat().st_size,
                "reason": safe_reason,
            }

    def _latest_configuration_snapshot(self) -> dict | None:
        snapshots = sorted(
            self._settings_backup_dir().glob("fetchshelf_snapshot_*.zip"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        if not snapshots:
            return None
        latest = snapshots[0]
        return {
            "name": latest.name,
            "created_at": datetime.fromtimestamp(latest.stat().st_mtime)
            .astimezone()
            .isoformat(timespec="seconds"),
            "size": latest.stat().st_size,
        }

    def _maybe_create_daily_configuration_snapshot(self) -> dict:
        today = datetime.now().strftime("%Y%m%d")
        latest = self._latest_configuration_snapshot()
        if latest and f"snapshot_{today}_" in latest["name"]:
            return latest
        return self._create_configuration_snapshot(reason="daily")

    def _backup_settings_file(self, reason: str = "manual") -> str:
        source = self.parameter.settings.path
        if not source.exists():
            self.parameter.settings.read()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        name = f"settings_{timestamp}_{self._normalize_string(reason) or 'backup'}.json"
        backup_path = self._settings_backup_dir().joinpath(name)
        backup_path.write_text(
            source.read_text(encoding=self.parameter.settings.encode),
            encoding=self.parameter.settings.encode,
        )
        return str(backup_path)

    @staticmethod
    def _validate_ui_account_update_payload(payload: dict) -> None:
        for key in (
            "accounts_urls",
            "accounts_urls_tiktok",
            "deleted_accounts",
            "deleted_accounts_tiktok",
        ):
            value = payload.get(key, [])
            if not isinstance(value, list):
                raise ValueError(f"{key} must be a list.")
            if any(not isinstance(item, dict) for item in value):
                raise ValueError(f"{key} only accepts object items.")

    @staticmethod
    def _validate_ui_account_verify_payload(payload: dict) -> None:
        platform = payload.get("platform", "douyin")
        if platform not in {"douyin", "tiktok"}:
            raise ValueError("platform must be douyin or tiktok.")
        use_settings = payload.get("use_settings", True)
        if not isinstance(use_settings, bool):
            raise ValueError("use_settings must be bool.")
        items = payload.get("items", [])
        if not isinstance(items, list):
            raise ValueError("items must be a list.")
        if any(not isinstance(item, dict) for item in items):
            raise ValueError("items only accepts object items.")
        move_deleted = payload.get("move_deleted", True)
        if not isinstance(move_deleted, bool):
            raise ValueError("move_deleted must be bool.")
        for key in ("cookie", "proxy", "identity_id"):
            value = payload.get(key)
            if value is not None and not isinstance(value, str):
                raise ValueError(f"{key} must be string or null.")

    def _extract_verified_user_info(self, info: dict, tiktok: bool) -> dict:
        if not isinstance(info, dict):
            return {}
        if tiktok:
            user = info.get("user")
            if isinstance(user, dict):
                return {
                    "nickname": self._normalize_string(user.get("nickname")),
                    "sec_uid": self._normalize_string(user.get("secUid")),
                    "uid": self._normalize_string(user.get("id")),
                }
            return {
                "nickname": self._normalize_string(info.get("nickname")),
                "sec_uid": self._normalize_string(info.get("secUid")),
                "uid": self._normalize_string(info.get("id")),
            }
        return {
            "nickname": self._normalize_string(info.get("nickname")),
            "sec_uid": self._normalize_string(info.get("sec_uid")),
            "uid": self._normalize_string(info.get("uid")),
        }

    def _is_deleted_nickname(self, nickname: str) -> bool:
        value = self._normalize_string(nickname).lower()
        if not value:
            return False
        return any(hint in value for hint in self.DELETED_ACCOUNT_HINTS)

    def _verify_user_info_state(
        self,
        info: dict,
        sec_user_id: str,
        tiktok: bool,
    ) -> tuple[bool, str]:
        user = self._extract_verified_user_info(info, tiktok)
        if not user:
            return False, _("账号主页信息为空")
        if not user.get("sec_uid"):
            return False, _("账号信息缺少 sec_uid")
        if not user.get("uid"):
            return False, _("账号信息缺少 uid")
        if not user.get("nickname"):
            return False, _("账号昵称为空")
        target_sec_uid = self._normalize_string(sec_user_id)
        if target_sec_uid and user["sec_uid"] != target_sec_uid:
            return False, _("账号 sec_uid 校验不一致")
        if self._is_deleted_nickname(user["nickname"]):
            return False, _("账号已注销或不可访问")
        return True, ""

    @staticmethod
    def _validate_ui_schedule_payload(payload: dict) -> None:
        platform = payload.get("platform", "douyin")
        if platform not in {"douyin", "tiktok"}:
            raise ValueError("platform must be douyin or tiktok.")
        for key in ("hour", "minute"):
            if key in payload and payload[key] not in {None, ""}:
                try:
                    int(payload[key])
                except (TypeError, ValueError):
                    raise ValueError(f"{key} must be integer.")
        use_settings = payload.get("use_settings", True)
        if not isinstance(use_settings, bool):
            raise ValueError("use_settings must be bool.")
        items = payload.get("items", [])
        if not isinstance(items, list):
            raise ValueError("items must be list.")
        if any(not isinstance(item, dict) for item in items):
            raise ValueError("items only accepts object items.")
        uptime_kuma_url = payload.get("uptime_kuma_url")
        if uptime_kuma_url is not None and not isinstance(uptime_kuma_url, str):
            raise ValueError("uptime_kuma_url must be string or null.")
        bark_url = payload.get("bark_url")
        if bark_url is not None and not isinstance(bark_url, str):
            raise ValueError("bark_url must be string or null.")
        overlap_policy = APIServer._normalize_string(
            payload.get("overlap_policy")
        )
        if (
            overlap_policy
            and overlap_policy not in APIServer.SCHEDULE_OVERLAP_POLICIES
        ):
            raise ValueError("overlap_policy must be wait, skip, or allow.")
        identity_failure_action = APIServer._normalize_string(
            payload.get("identity_failure_action")
        )
        if (
            identity_failure_action
            and identity_failure_action not in APIServer.IDENTITY_FAILURE_ACTIONS
        ):
            raise ValueError("identity_failure_action must be continue or pause.")
        notify_on_identity_failure = payload.get("notify_on_identity_failure")
        if (
            notify_on_identity_failure is not None
            and not isinstance(notify_on_identity_failure, bool)
        ):
            raise ValueError("notify_on_identity_failure must be bool.")
        threshold = payload.get("identity_failure_threshold")
        if threshold not in {None, ""}:
            try:
                threshold_value = int(threshold)
            except (TypeError, ValueError):
                raise ValueError("identity_failure_threshold must be integer.")
            if not 1 <= threshold_value <= 20:
                raise ValueError("identity_failure_threshold must be between 1 and 20.")
        identity_id = payload.get("identity_id")
        if identity_id is not None and not isinstance(identity_id, str):
            raise ValueError("identity_id must be string or null.")

    def _validate_schedule_identity_reference(self, payload: dict) -> None:
        identity_id = self._normalize_string(payload.get("identity_id"))
        if not identity_id:
            return
        try:
            identity = self.collector_store.get_identity(identity_id)
        except IdentityNotFoundError:
            raise ValueError("identity_id does not reference an existing identity.") from None
        platform = self._normalize_string(payload.get("platform")) or "douyin"
        if identity.platform.value != platform:
            raise ValueError("identity_id belongs to another platform.")

    @staticmethod
    def _validate_collect_monitor_payload(payload: dict) -> None:
        collect_id = APIServer._normalize_string(payload.get("collect_id"))
        if not collect_id:
            raise ValueError("collect_id is required.")
        if not collect_id.isdigit():
            raise ValueError("collect_id must be numeric.")
        for key in ("interval_minutes", "limit"):
            if key in payload and payload[key] not in {None, ""}:
                try:
                    int(payload[key])
                except (TypeError, ValueError):
                    raise ValueError(f"{key} must be integer.")
        tab = APIServer._normalize_string(payload.get("default_tab"))
        if tab and tab not in {"post", "favorite", "collection"}:
            raise ValueError("default_tab must be post/favorite/collection.")
        for key in (
            "enabled",
            "account_enable",
            "immediate_crawl",
            "default_auto_update_earliest",
        ):
            if key in payload and not isinstance(payload.get(key), bool):
                raise ValueError(f"{key} must be bool.")
        for key in ("cookie", "proxy", "bark_url", "identity_id"):
            value = payload.get(key)
            if value is not None and not isinstance(value, str):
                raise ValueError(f"{key} must be string or null.")

    @staticmethod
    def _schedule_serializable(schedule: dict) -> dict:
        return {
            key: value
            for key, value in schedule.items()
            if key not in {"_runner"}
        }

    @classmethod
    def _schedule_public(cls, schedule: dict) -> dict:
        return redact_webui_value(cls._schedule_serializable(schedule))

    def _normalize_collect_monitor_payload(self, payload: dict) -> dict:
        now = self._now_text()
        collect_id = self._normalize_string(payload.get("collect_id"))
        interval_minutes = self._normalize_collect_interval(
            payload.get("interval_minutes"),
            default=30,
        )
        limit = self._normalize_collect_limit(payload.get("limit"), default=10)
        enabled = self._normalize_bool(payload.get("enabled"), default=True)
        normalized = {
            "schedule_type": self.COLLECT_MONITOR_SCHEDULE,
            "schedule_id": self._normalize_string(payload.get("schedule_id")),
            "name": self._normalize_string(payload.get("name"))
            or f"收藏夹监控-{collect_id or '未设置'}",
            "platform": "douyin",
            "collect_id": collect_id,
            "interval_minutes": interval_minutes,
            "limit": limit,
            "enabled": enabled,
            "account_enable": self._normalize_bool(
                payload.get("account_enable"),
                default=True,
            ),
            "immediate_crawl": self._normalize_bool(
                payload.get("immediate_crawl"),
                default=False,
            ),
            "default_tab": self._normalize_collect_tab(payload.get("default_tab")),
            "default_earliest": self._normalize_string(payload.get("default_earliest")),
            "default_latest": self._normalize_string(payload.get("default_latest")),
            "default_auto_update_earliest": self._normalize_bool(
                payload.get("default_auto_update_earliest"),
                default=False,
            ),
            "identity_id": self._normalize_string(payload.get("identity_id")),
            "cookie": self._normalize_string(payload.get("cookie")),
            "proxy": self._normalize_string(payload.get("proxy")),
            "bark_url": self._normalize_string(payload.get("bark_url")),
            "created_at": self._normalize_string(payload.get("created_at")) or now,
            "updated_at": now,
            "last_run_at": self._normalize_string(payload.get("last_run_at")),
            "next_run_at": self._normalize_string(payload.get("next_run_at")),
            "last_result": (
                payload.get("last_result")
                if isinstance(payload.get("last_result"), dict)
                else {}
            ),
        }
        if normalized["enabled"]:
            normalized["next_run_at"] = normalized["next_run_at"] or self._next_interval_run_text(
                normalized["interval_minutes"]
            )
        else:
            normalized["next_run_at"] = ""
        return normalized

    def _normalize_schedule_payload(self, payload: dict) -> dict:
        schedule_type = self._normalize_schedule_type(payload.get("schedule_type"))
        if schedule_type == self.COLLECT_MONITOR_SCHEDULE:
            return self._normalize_collect_monitor_payload(payload)

        platform = self._normalize_string(payload.get("platform")) or "douyin"
        if platform not in {"douyin", "tiktok"}:
            platform = "douyin"
        hour = self._normalize_optional_int(payload.get("hour"))
        minute = self._normalize_optional_int(payload.get("minute"))
        if hour is None or not 0 <= hour <= 23:
            hour = 2
        if minute is None or not 0 <= minute <= 59:
            minute = 0
        use_settings = self._normalize_bool(payload.get("use_settings"), default=True)
        items = (
            self._normalize_account_items(payload.get("items", []))
            if not use_settings
            else []
        )
        overlap_policy = self._normalize_string(
            payload.get("overlap_policy")
        ).lower()
        if overlap_policy not in self.SCHEDULE_OVERLAP_POLICIES:
            overlap_policy = "wait"
        identity_failure_action = self._normalize_string(
            payload.get("identity_failure_action")
        ).lower()
        if identity_failure_action not in self.IDENTITY_FAILURE_ACTIONS:
            identity_failure_action = "continue"
        identity_failure_threshold = self._normalize_optional_int(
            payload.get("identity_failure_threshold")
        )
        if identity_failure_threshold is None:
            identity_failure_threshold = 3
        identity_failure_threshold = max(1, min(identity_failure_threshold, 20))
        now = self._now_text()
        normalized = {
            "schedule_type": self.ACCOUNT_BATCH_SCHEDULE,
            "schedule_id": self._normalize_string(payload.get("schedule_id")),
            "name": self._normalize_string(payload.get("name"))
            or f"每日下载-{platform}",
            "platform": platform,
            "hour": hour,
            "minute": minute,
            "enabled": self._normalize_bool(payload.get("enabled"), default=True),
            "use_settings": use_settings,
            "items": items,
            "identity_id": self._normalize_string(payload.get("identity_id")),
            "cookie": self._normalize_string(payload.get("cookie")),
            "proxy": self._normalize_string(payload.get("proxy")),
            "uptime_kuma_url": self._normalize_string(payload.get("uptime_kuma_url")),
            "bark_url": self._normalize_string(payload.get("bark_url")),
            "overlap_policy": overlap_policy,
            "identity_failure_action": identity_failure_action,
            "identity_failure_threshold": identity_failure_threshold,
            "notify_on_identity_failure": self._normalize_bool(
                payload.get("notify_on_identity_failure"),
                default=True,
            ),
            "created_at": self._normalize_string(payload.get("created_at")) or now,
            "updated_at": now,
            "last_run_at": self._normalize_string(payload.get("last_run_at")),
            "next_run_at": self._normalize_string(payload.get("next_run_at")),
            "last_task_id": self._normalize_string(payload.get("last_task_id")),
            "overlap_state": self._normalize_string(payload.get("overlap_state")),
            "waiting_for_task_id": self._normalize_string(
                payload.get("waiting_for_task_id")
            ),
            "last_result": (
                payload.get("last_result")
                if isinstance(payload.get("last_result"), dict)
                else {}
            ),
        }
        if normalized["enabled"]:
            normalized["next_run_at"] = normalized["next_run_at"] or self._next_run_text(
                normalized["hour"],
                normalized["minute"],
            )
        else:
            normalized["next_run_at"] = ""
        return normalized

    @staticmethod
    def _next_run_datetime(hour: int, minute: int) -> datetime:
        now = datetime.now()
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        return target

    def _next_run_text(self, hour: int, minute: int) -> str:
        return self._next_run_datetime(hour, minute).strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def _next_interval_run_datetime(minutes: int) -> datetime:
        return datetime.now() + timedelta(minutes=max(1, int(minutes or 1)))

    def _next_interval_run_text(self, minutes: int) -> str:
        return self._next_interval_run_datetime(minutes).strftime("%Y-%m-%d %H:%M:%S")

    def _schedule_task_payload(self, schedule: dict) -> tuple[str, dict]:
        endpoint = (
            "/workflow/tiktok/account_batch"
            if schedule["platform"] == "tiktok"
            else "/workflow/douyin/account_batch"
        )
        payload = {
            "use_settings": schedule["use_settings"],
            "items": schedule.get("items", []) if not schedule["use_settings"] else [],
            "identity_id": self._normalize_string(schedule.get("identity_id")),
            "cookie": schedule.get("cookie", ""),
            "proxy": schedule.get("proxy", ""),
            "identity_failure_action": schedule.get(
                "identity_failure_action",
                "continue",
            ),
            "identity_failure_threshold": max(
                1,
                min(
                    self._normalize_optional_int(
                        schedule.get("identity_failure_threshold")
                    )
                    or 3,
                    20,
                ),
            ),
            "notify_on_identity_failure": self._normalize_bool(
                schedule.get("notify_on_identity_failure"),
                default=True,
            ),
        }
        return endpoint, payload

    @staticmethod
    def _extract_collect_monitor_sec_uids(aweme_items: list[dict]) -> list[str]:
        sec_uids = []
        seen = set()
        for item in aweme_items:
            if not isinstance(item, dict):
                continue
            author = item.get("author") or {}
            if not isinstance(author, dict):
                continue
            sec_uid = APIServer._normalize_string(author.get("sec_uid"))
            if not sec_uid or sec_uid in seen:
                continue
            seen.add(sec_uid)
            sec_uids.append(sec_uid)
        return sec_uids

    @classmethod
    def _collect_monitor_page_count(cls, limit: int) -> int:
        return max(1, min(int(limit), cls.COLLECT_MONITOR_PAGE_COUNT))

    async def _collect_monitor_fetch_aweme_items(
        self,
        collect_id: str,
        cookie: str,
        proxy: str | None,
        limit: int,
        *,
        parameter=None,
        user_agent: str = "",
    ) -> list[dict]:
        runtime_parameter = parameter or self.parameter
        target = self._normalize_collect_limit(limit, default=10)
        cursor = 0
        page_count = self._collect_monitor_page_count(target)
        max_pages = max(
            1,
            min(
                self.COLLECT_MONITOR_MAX_PAGES,
                (target * 3 + page_count - 1) // page_count,
            ),
        )
        aweme_items: list[dict] = []
        seen_aweme_ids = set()
        direct_request_failed = False

        for page_index in range(max_pages):
            collector = CollectsDetail(
                runtime_parameter,
                cookie=cookie,
                proxy=proxy,
                collects_id=collect_id,
                pages=1,
                cursor=cursor,
                count=page_count,
            )
            page_items = await collector.run(single_page=True)
            if collector.last_request_error is not None:
                direct_request_failed = True
                break
            if not isinstance(page_items, list):
                page_items = []

            for item in page_items:
                if not isinstance(item, dict):
                    continue
                aweme_id = self._normalize_string(item.get("aweme_id"))
                if aweme_id:
                    if aweme_id in seen_aweme_ids:
                        continue
                    seen_aweme_ids.add(aweme_id)
                aweme_items.append(item)
                if len(aweme_items) >= target:
                    break

            next_cursor = collector.cursor
            if (
                len(aweme_items) >= target
                or collector.finished
                or next_cursor == cursor
                or page_index + 1 >= max_pages
            ):
                break
            cursor = next_cursor

        if direct_request_failed:
            self.logger.warning(
                _(
                    "抖音收藏夹直连接口不可用，正在切换到浏览器签名请求"
                )
            )
            try:
                return await fetch_douyin_collection_via_browser(
                    collect_id=collect_id,
                    cookie=cookie,
                    proxy=proxy,
                    limit=target,
                    user_agent=user_agent,
                )
            except DouyinBrowserCollectionError:
                raise
            except Exception as error:
                raise DouyinBrowserCollectionError(
                    "抖音收藏夹浏览器请求执行失败，请稍后重试。",
                    error_code="douyin_browser_runtime_failed",
                ) from error

        return aweme_items[:target]

    def _resolve_runtime_douyin_cookie(self, override: str = "") -> str:
        if override := self._normalize_string(override):
            return override
        if self.parameter.cookie_str:
            return self.parameter.cookie_str
        if isinstance(self.parameter.cookie_dict, dict) and self.parameter.cookie_dict:
            return cookie_dict_to_str(self.parameter.cookie_dict)
        return ""

    async def _send_bark_notification(
        self,
        bark_url: str,
        title: str,
        body: str,
        proxy: str | None = None,
    ) -> tuple[bool, str]:
        url = self._normalize_string(bark_url)
        if not url:
            return False, ""
        proxy_value = self._normalize_string(proxy) or self.parameter.proxy
        timeout = max(5, min(int(getattr(self.parameter, "timeout", 10) or 10), 30))
        try:
            async with create_client(timeout=timeout, proxy=proxy_value) as client:
                if "{title}" in url or "{body}" in url:
                    target = url.format(
                        title=quote(title, safe=""),
                        body=quote(body, safe=""),
                    )
                    response = await client.get(target)
                elif url.rstrip("/").endswith("/push"):
                    response = await client.post(
                        url,
                        json={
                            "title": title,
                            "body": body,
                        },
                    )
                else:
                    target = f"{url.rstrip('/')}/{quote(title, safe='')}/{quote(body, safe='')}"
                    response = await client.get(target)
                response.raise_for_status()
                return True, ""
        except Exception as error:  # noqa: BLE001
            return False, str(error)

    async def _notify_collect_monitor(
        self,
        schedule: dict,
        success: bool,
        summary: dict,
        error_text: str = "",
    ) -> None:
        bark_url = self._normalize_string(schedule.get("bark_url"))
        if not bark_url:
            return
        if success:
            try:
                added_accounts = int(summary.get("added_accounts", 0) or 0)
            except (TypeError, ValueError):
                added_accounts = 0
            if added_accounts <= 0:
                return
        title = (
            f"收藏夹监控成功: {schedule.get('name') or schedule.get('collect_id')}"
            if success
            else f"收藏夹监控异常: {schedule.get('name') or schedule.get('collect_id')}"
        )
        if success:
            body = (
                f"collect_id={schedule.get('collect_id')} "
                f"新增{summary.get('added_accounts', 0)} 去重{summary.get('duplicate_accounts', 0)} "
                f"作品{summary.get('fetched_aweme', 0)}"
            )
        else:
            body = (
                f"collect_id={schedule.get('collect_id')} "
                f"错误={error_text or summary.get('error', 'unknown')}"
            )
        sent, error = await self._send_bark_notification(
            bark_url=bark_url,
            title=title,
            body=body,
            proxy=self._normalize_string(schedule.get("proxy")),
        )
        if not sent and error:
            self.logger.warning(
                _("Bark 通知发送失败：{error}").format(error=error),
            )

    async def _run_collect_monitor_once(self, schedule: dict) -> dict:
        collect_id = self._normalize_string(schedule.get("collect_id"))
        if not collect_id:
            return {
                "ok": False,
                "error": "collect_id is empty",
            }
        if not collect_id.isdigit():
            return {
                "ok": False,
                "error": "collect_id must be numeric",
            }
        count = self._normalize_collect_limit(schedule.get("limit"), default=10)

        async def operation(worker, credentials, selected_identity_id):
            cookie = self._resolve_runtime_douyin_cookie(credentials.cookie)
            if not cookie:
                return (
                    {
                        "ok": False,
                        "error": _("未配置抖音 Cookie，无法访问收藏夹接口"),
                        "_new_rows": [],
                    },
                    0,
                    1,
                )
            aweme_items = await self._collect_monitor_fetch_aweme_items(
                collect_id=collect_id,
                cookie=cookie,
                proxy=credentials.proxy or None,
                limit=count,
                parameter=worker.parameter,
                user_agent=credentials.user_agent,
            )
            sec_uids = self._extract_collect_monitor_sec_uids(aweme_items)

            existing_rows = self._normalize_account_items(self._account_rows(False))
            seen_urls = {
                self._normalize_account_url(item.get("url", ""))
                for item in existing_rows
                if self._normalize_account_url(item.get("url", ""))
            }
            new_rows = []
            duplicate_accounts = 0
            for sec_uid in sec_uids:
                account_url = f"https://www.douyin.com/user/{sec_uid}"
                key = self._normalize_account_url(account_url)
                if not key or key in seen_urls:
                    duplicate_accounts += 1
                    continue
                seen_urls.add(key)
                new_rows.append(
                    {
                        "mark": "",
                        "url": account_url,
                        "tab": self._normalize_collect_tab(
                            schedule.get("default_tab")
                        ),
                        "earliest": self._normalize_string(
                            schedule.get("default_earliest")
                        ),
                        "latest": self._normalize_string(
                            schedule.get("default_latest")
                        ),
                        "enable": self._normalize_bool(
                            schedule.get("account_enable"),
                            default=True,
                        ),
                        "auto_update_earliest": self._normalize_bool(
                            schedule.get("default_auto_update_earliest"),
                            default=False,
                        ),
                    }
                )

            if new_rows:
                # Keep monitor-added accounts at top, matching manual insertion.
                self._set_account_rows(False, [*new_rows, *existing_rows])
                self.parameter.settings.update(self.parameter.get_settings_data())

            return (
                {
                    "ok": True,
                    "collect_id": collect_id,
                    "fetched_aweme": len(aweme_items),
                    "sec_uid_count": len(sec_uids),
                    "added_accounts": len(new_rows),
                    "duplicate_accounts": duplicate_accounts,
                    "_new_rows": new_rows,
                },
                1,
                0,
            )

        summary, selected_identity_id, selected_by = (
            await self._execute_collector_operation(
                platform=CollectorPlatform.DOUYIN,
                target_type="collect",
                target_key=collect_id,
                identity_id=self._normalize_string(schedule.get("identity_id")),
                cookie=self._normalize_string(schedule.get("cookie")),
                proxy=self._normalize_string(schedule.get("proxy")),
                operation=operation,
                failure_error_code="collect_monitor_failed",
            )
        )
        new_rows = summary.pop("_new_rows", [])
        immediate_result: dict[str, Any] = {}
        immediate_crawl = self._normalize_bool(
            schedule.get("immediate_crawl"),
            default=False,
        )
        if summary.get("ok") and new_rows and immediate_crawl:
            scheduled_identity_id = self._normalize_string(
                schedule.get("identity_id")
            )
            batch = await self._run_ui_account_batch(
                payload={
                    "use_settings": False,
                    "items": new_rows,
                    "identity_id": scheduled_identity_id,
                    "cookie": (
                        ""
                        if scheduled_identity_id
                        else self._normalize_string(schedule.get("cookie"))
                    ),
                    "proxy": (
                        ""
                        if scheduled_identity_id
                        else self._normalize_string(schedule.get("proxy"))
                    ),
                },
                tiktok=False,
            )
            immediate_result = {
                "message": batch.message,
                "data": batch.data,
            }
        summary.update(
            {
                "immediate_crawl": immediate_crawl,
                "immediate_result": immediate_result,
                "selected_identity_id": selected_identity_id,
                "selected_by": selected_by,
            }
        )
        if summary.get("ok"):
            self.logger.info(
                _(
                    "收藏夹监控完成: collect_id={collect} 作品={works} sec_uid={sec} 新增账号={added} 去重={dup}"
                ).format(
                    collect=collect_id,
                    works=summary.get("fetched_aweme", 0),
                    sec=summary.get("sec_uid_count", 0),
                    added=summary.get("added_accounts", 0),
                    dup=summary.get("duplicate_accounts", 0),
                )
            )
        else:
            self.logger.warning(
                _("收藏夹监控失败: collect_id={collect} 错误={error}").format(
                    collect=collect_id,
                    error=summary.get("error", "unknown"),
                )
            )
        return summary

    @staticmethod
    def _find_douyin_browser_error(
        error: BaseException,
    ) -> DouyinBrowserCollectionError | None:
        current: BaseException | None = error
        seen: set[int] = set()
        while current is not None and id(current) not in seen:
            seen.add(id(current))
            if isinstance(current, DouyinBrowserCollectionError):
                return current
            current = current.__cause__ or current.__context__
        return None

    def _collect_monitor_failure_result(
        self,
        schedule: dict,
        error: Exception,
    ) -> dict:
        browser_error = self._find_douyin_browser_error(error)
        exception_chain = []
        current: BaseException | None = error
        seen: set[int] = set()
        while current is not None and id(current) not in seen:
            seen.add(id(current))
            exception_chain.append(
                f"{type(current).__name__}: {redact_webui_value(str(current))}"
            )
            current = current.__cause__ or current.__context__
        logger = getattr(self, "logger", None)
        if callable(getattr(logger, "error", None)):
            logger.error(
                _("收藏夹监控执行异常: collect_id={collect} {error}").format(
                    collect=self._normalize_string(schedule.get("collect_id")),
                    error=" <- ".join(exception_chain),
                )
            )

        if browser_error is None:
            return {
                "ok": False,
                "error_code": "monitor_execution_failed",
                "error": _("收藏夹监控执行失败"),
            }

        error_code = self._normalize_string(browser_error.error_code)
        result = {
            "ok": False,
            "error_code": error_code or "douyin_browser_collection_failed",
            "error": self._normalize_string(browser_error),
            "selected_identity_id": self._normalize_string(
                browser_error.identity_id
            ),
        }
        if error_code == "douyin_auth_required":
            result.update(
                {
                    "requires_login": True,
                    "action": "reauthenticate_identity",
                }
            )
        return result

    def _start_single_schedule_runner(self, schedule_id: str) -> None:
        if schedule_id in self.ui_schedule_tasks:
            return
        if schedule_id not in self.ui_schedules:
            return
        self.ui_schedule_tasks[schedule_id] = create_task(
            self._ui_schedule_runner(schedule_id),
        )

    def _active_schedule_task(self, schedule_id: str) -> dict | None:
        candidates = [
            task
            for task in getattr(self, "ui_tasks", {}).values()
            if self._normalize_string(task.get("schedule_id")) == schedule_id
            and task.get("status") in ACTIVE_TASK_STATUSES
        ]
        if not candidates:
            return None
        return max(candidates, key=self._ui_task_sort_key)

    def _create_schedule_task(self, schedule: dict) -> dict:
        endpoint, payload = self._schedule_task_payload(schedule)
        task = self._enqueue_ui_task(
            endpoint=endpoint,
            payload=loads(dumps(payload, ensure_ascii=False)),
        )
        self._attach_schedule_task_meta(task, schedule)
        schedule["last_task_id"] = task["task_id"]
        schedule["overlap_state"] = ""
        return task

    async def _resolve_schedule_overlap(
        self,
        schedule: dict,
        *,
        wait_for_slot: bool,
    ) -> tuple[str, dict | None]:
        policy = self._normalize_string(
            schedule.get("overlap_policy")
        ).lower()
        if policy not in self.SCHEDULE_OVERLAP_POLICIES:
            policy = "wait"
        active = self._active_schedule_task(
            self._normalize_string(schedule.get("schedule_id"))
        )
        if not active or policy == "allow":
            return "enqueue", None
        if policy == "skip":
            schedule["overlap_state"] = "skipped"
            schedule["last_result"] = {
                "ok": True,
                "skipped": True,
                "reason": "active_task_exists",
                "active_task_id": active.get("task_id", ""),
            }
            return "skip", active
        if not wait_for_slot:
            schedule["overlap_state"] = "waiting"
            return "wait", active
        schedule["overlap_state"] = "waiting"
        schedule["waiting_for_task_id"] = active.get("task_id", "")
        self._persist_ui_schedules()
        while True:
            current = self.ui_schedules.get(
                self._normalize_string(schedule.get("schedule_id"))
            )
            if not current or not current.get("enabled", False):
                return "disabled", active
            active = self._active_schedule_task(
                self._normalize_string(schedule.get("schedule_id"))
            )
            if not active:
                schedule["overlap_state"] = ""
                schedule["waiting_for_task_id"] = ""
                return "enqueue", None
            try:
                await sleep(5)
            except CancelledError:
                raise

    async def _stop_single_schedule_runner(self, schedule_id: str) -> None:
        task = self.ui_schedule_tasks.pop(schedule_id, None)
        if task:
            task.cancel()
            await gather(task, return_exceptions=True)

    async def _ui_schedule_runner(self, schedule_id: str) -> None:
        while True:
            schedule = self.ui_schedules.get(schedule_id)
            if not schedule or not schedule.get("enabled", False):
                break
            schedule_type = self._normalize_schedule_type(schedule.get("schedule_type"))
            if schedule_type == self.COLLECT_MONITOR_SCHEDULE:
                interval = self._normalize_collect_interval(
                    schedule.get("interval_minutes"),
                    default=30,
                )
                next_run = self._next_interval_run_datetime(interval)
            else:
                next_run = self._next_run_datetime(schedule["hour"], schedule["minute"])
            schedule["next_run_at"] = next_run.strftime("%Y-%m-%d %H:%M:%S")
            delay = max(1.0, (next_run - datetime.now()).total_seconds())
            try:
                await sleep(delay)
            except CancelledError:
                break
            schedule = self.ui_schedules.get(schedule_id)
            if not schedule or not schedule.get("enabled", False):
                continue
            schedule_type = self._normalize_schedule_type(schedule.get("schedule_type"))
            if schedule_type == self.COLLECT_MONITOR_SCHEDULE:
                try:
                    result = await self._run_collect_monitor_once(schedule)
                except Exception as error:  # noqa: BLE001
                    result = self._collect_monitor_failure_result(schedule, error)
                schedule["last_result"] = result
                if result.get("ok", False):
                    await self._notify_collect_monitor(
                        schedule=schedule,
                        success=True,
                        summary=result,
                    )
                else:
                    await self._notify_collect_monitor(
                        schedule=schedule,
                        success=False,
                        summary=result,
                        error_text=self._normalize_string(result.get("error")),
                    )
            else:
                overlap_action, active_task = await self._resolve_schedule_overlap(
                    schedule,
                    wait_for_slot=True,
                )
                if overlap_action == "enqueue":
                    self._create_schedule_task(schedule)
                elif overlap_action == "skip":
                    self.logger.info(
                        _(
                            "定时任务因上次任务仍在运行而跳过: {schedule} active={task}"
                        ).format(
                            schedule=schedule_id,
                            task=(active_task or {}).get("task_id", ""),
                        )
                    )
                elif overlap_action == "disabled":
                    continue
            schedule["last_run_at"] = self._now_text()
            schedule["updated_at"] = self._now_text()
            if schedule_type == self.COLLECT_MONITOR_SCHEDULE:
                schedule["next_run_at"] = self._next_interval_run_text(
                    self._normalize_collect_interval(
                        schedule.get("interval_minutes"),
                        default=30,
                    )
                )
            else:
                schedule["next_run_at"] = self._next_run_text(
                    schedule["hour"],
                    schedule["minute"],
                )
            self.parameter.ui_schedules = [
                self._schedule_serializable(item)
                for item in self.ui_schedules.values()
            ]
            self.parameter.settings.update(self.parameter.get_settings_data())
        self.ui_schedule_tasks.pop(schedule_id, None)

    def _persist_ui_schedules(self) -> None:
        self.parameter.ui_schedules = [
            self._schedule_serializable(item)
            for item in sorted(
                self.ui_schedules.values(),
                key=lambda item: item.get("schedule_id", ""),
            )
        ]
        self.parameter.settings.update(self.parameter.get_settings_data())

    def _schedule_items_by_type(self, schedule_type: str) -> list[dict]:
        target = self._normalize_schedule_type(schedule_type)
        return [
            item
            for item in self.ui_schedules.values()
            if self._normalize_schedule_type(item.get("schedule_type")) == target
        ]

    def _find_schedule_by_type(
        self,
        schedule_id: str,
        schedule_type: str,
    ) -> dict | None:
        schedule = self.ui_schedules.get(schedule_id)
        if not schedule:
            return None
        if (
            self._normalize_schedule_type(schedule.get("schedule_type"))
            != self._normalize_schedule_type(schedule_type)
        ):
            return None
        return schedule

    def _plan_collector_routes(
        self,
        platform: CollectorPlatform,
        items: list[dict],
        *,
        target_type: str,
        target_key_getter=None,
        forced_identity_id: str = "",
        persist_assignments: bool = True,
        strategy_override: RoutingStrategy | None = None,
    ) -> list[dict]:
        forced_identity_id = self._normalize_string(forced_identity_id)
        if forced_identity_id:
            identity = self.collector_store.get_identity(forced_identity_id)
            if identity.platform != platform:
                raise IdentityPlatformError(
                    "selected collector identity belongs to another platform"
                )
        public = {
            item.identity_id: item
            for item in self.collector_store.list_public(platform)
            if item.route_configured
            and not self._collector_identity_login_locked(item.identity_id)
        }
        candidates = [
            item
            for item in self.collector_store.route_candidates(platform)
            if item.identity_id in public
        ]
        if forced_identity_id and forced_identity_id not in public:
            raise RouteUnavailable(
                "selected collector identity is unavailable or has no credentials/session",
                identity_id=forced_identity_id,
            )
        if not candidates:
            return []

        policy = self.collector_store.get_policy(platform)
        strategy = strategy_override or policy.strategy
        eligible_ids = {
            candidate.identity_id
            for candidate in candidates
            if candidate_available(candidate, platform=platform)
        }

        def fallback_identity(excluded: str = "") -> str:
            preferred = [
                *policy.fallback_identity_ids,
                policy.default_identity_id,
            ]
            return next(
                (
                    identity_id
                    for identity_id in preferred
                    if identity_id
                    and identity_id != excluded
                    and identity_id in eligible_ids
                ),
                "",
            )

        targets = []
        reasons = []
        sticky_flags = []
        for item in items:
            raw_target_key = (
                target_key_getter(item)
                if target_key_getter is not None
                else item.get("target_key", "")
            )
            target_key = self._normalize_string(raw_target_key)
            if target_type == "account":
                target_key = self._normalize_account_url(target_key) or target_key
            if not target_key:
                raise RouteUnavailable("collector target key is empty")
            explicit_identity_id = forced_identity_id
            reason = "task_override" if forced_identity_id else strategy.value
            persist_sticky = False
            if not explicit_identity_id:
                assignment = self.collector_store.get_assignment(
                    platform,
                    target_type,
                    target_key,
                )
                if assignment:
                    assigned_available = assignment.identity_id in eligible_ids
                    if assignment.source == AssignmentSource.EXPLICIT:
                        explicit_identity_id = assignment.identity_id
                        reason = "fixed_binding"
                        if (
                            not assigned_available
                            and policy.binding_failure
                            == BindingFailureMode.FALLBACK
                        ):
                            explicit_identity_id = fallback_identity(
                                assignment.identity_id
                            )
                            reason = "binding_fallback"
                    elif strategy == RoutingStrategy.LEAST_LOADED:
                        # Policy-generated sticky history must not freeze a
                        # least-loaded policy after its first execution.
                        explicit_identity_id = ""
                        reason = strategy.value
                    elif assigned_available:
                        explicit_identity_id = assignment.identity_id
                        reason = "existing_sticky"
                    else:
                        # A policy-created sticky assignment is not a hard
                        # binding. Rebalance it when its identity is cooling,
                        # disabled, deleted from the candidate set, or invalid.
                        explicit_identity_id = fallback_identity(
                            assignment.identity_id
                        )
                        reason = "sticky_rebalanced"
                        persist_sticky = target_type == "account"
                elif policy.default_identity_id:
                    if policy.default_identity_id in eligible_ids:
                        explicit_identity_id = policy.default_identity_id
                        reason = "default_identity"
                    else:
                        explicit_identity_id = fallback_identity(
                            policy.default_identity_id
                        )
                        reason = "default_fallback"
                else:
                    # Rendezvous hashing is already deterministic. Persist only
                    # account affinity, which has an exposed binding lifecycle;
                    # one-off details/searches must not create hidden DB growth.
                    persist_sticky = (
                        target_type == "account"
                        and strategy == RoutingStrategy.STICKY_BALANCED
                    )
            targets.append(
                RouteTarget(
                    target_key=target_key,
                    explicit_identity_id=explicit_identity_id,
                )
            )
            reasons.append(reason)
            sticky_flags.append(persist_sticky)

        decisions = plan_routes(
            platform=platform,
            targets=targets,
            candidates=candidates,
            strategy=strategy,
        )
        sticky_updates = []
        planned = []
        for item, decision, reason, persist_sticky in zip(
            items,
            decisions,
            reasons,
            sticky_flags,
        ):
            planned.append(
                {
                    "item": item,
                    "identity_id": decision.identity_id,
                    "target_key": decision.target_key,
                    "reason": reason,
                }
            )
            if persist_sticky and not forced_identity_id:
                sticky_updates.append(
                    CollectorAssignment(
                        platform=platform,
                        target_type=target_type,
                        target_key=decision.target_key,
                        identity_id=decision.identity_id,
                        source=AssignmentSource.POLICY,
                    )
                )
        if sticky_updates and persist_assignments:
            self.collector_store.upsert_assignments(sticky_updates)
        return planned

    def _plan_collector_account_routes(
        self,
        platform: CollectorPlatform,
        items: list[dict],
        *,
        forced_identity_id: str = "",
        persist_assignments: bool = True,
        strategy_override: RoutingStrategy | None = None,
    ) -> list[dict]:
        """Backward-compatible account facade over the generic planner."""

        return self._plan_collector_routes(
            platform,
            items,
            target_type="account",
            target_key_getter=lambda item: item.get("url", ""),
            forced_identity_id=forced_identity_id,
            persist_assignments=persist_assignments,
            strategy_override=strategy_override,
        )

    def _update_collector_runtime_after_group(
        self,
        identity_id: str,
        *,
        active_leases: int,
        successes: int = 0,
        failures: int = 0,
        risk_failures: int = 0,
        error_code: str = "",
    ) -> None:
        state = self.collector_store.get_runtime(identity_id)
        now = self._collector_timestamp()
        state.active_leases = max(0, active_leases)
        systemic_failure = (
            bool(failures)
            and error_code == "identity_runtime_close_failed"
        )
        if successes:
            state.total_successes += successes
            state.last_success_at = now
            if not systemic_failure:
                state.status = IdentityStatus.HEALTHY
                state.consecutive_failures = 0
                state.cooldown_until = ""
                state.last_error_code = ""
        if failures:
            state.total_failures += failures
            state.risk_failures += max(
                max(0, int(risk_failures or 0)),
                failures if self._is_collector_risk_error_code(error_code) else 0,
            )
            state.last_failure_at = now
            state.last_error_code = error_code or "collector_request_failed"
            # A partial success proves the identity can still reach the target
            # platform, so target-specific misses must not trip risk cooldown.
            if not successes or error_code == "identity_runtime_close_failed":
                state.status = IdentityStatus.WARNING
                state.consecutive_failures += failures
                identity = self.collector_store.get_identity(identity_id)
                policy = self.collector_store.get_policy(identity.platform)
                if (
                    state.consecutive_failures >= policy.failure_threshold
                    and policy.cooldown_seconds > 0
                ):
                    state.status = IdentityStatus.COOLDOWN
                    state.cooldown_until = (
                        datetime.now().astimezone()
                        + timedelta(seconds=policy.cooldown_seconds)
                    ).isoformat(timespec="seconds")
        self.collector_store.save_runtime(state)

    @staticmethod
    def _is_collector_risk_error_code(error_code: str) -> bool:
        normalized = str(error_code or "").strip().lower()
        return "403" in normalized or "forbidden" in normalized or "risk" in normalized

    @staticmethod
    def _collector_failure_error_code(error: Exception, fallback: str) -> str:
        if error_code := str(getattr(error, "error_code", "") or "").strip():
            return error_code
        response = getattr(error, "response", None)
        status_code = getattr(response, "status_code", None)
        if status_code is None:
            status_code = getattr(error, "status_code", None)
        message = str(error or "").lower()
        if status_code == 403 or "403" in message or "forbidden" in message:
            return "http_403_forbidden"
        return fallback

    async def _execute_collector_identity_operation(
        self,
        platform: CollectorPlatform,
        identity_id: str,
        operation,
        *,
        failure_error_code: str = "collector_request_failed",
    ):
        """Run one callback inside the selected identity's isolated runtime.

        ``operation`` receives ``(worker, credentials, identity_id)`` and must
        return ``(result, successes, failures)``.  This is the single lease,
        runtime lifecycle and health-accounting boundary shared by every
        collector-backed endpoint.
        """

        identity = self.collector_store.get_identity(identity_id)
        if identity.platform != platform:
            raise IdentityPlatformError(
                "selected collector identity belongs to another platform"
            )
        if self._collector_identity_login_locked(identity_id):
            raise RouteUnavailable(
                "selected collector identity is busy in the login browser",
                identity_id=identity_id,
            )
        credentials = self.collector_store.load_credentials(identity_id)
        if (
            not credentials.cookie
            and identity.auth_mode != CollectorAuthMode.ANONYMOUS
        ):
            raise RouteUnavailable(
                "selected collector identity has no cookie",
                identity_id=identity_id,
            )
        policy = self.collector_store.get_policy(platform)
        await self.collector_leases.configure(
            identity.identity_id,
            identity.max_concurrency,
        )
        await self.collector_leases.configure(
            f"platform:{platform.value}",
            policy.global_max_parallel,
        )

        successes = 0
        failures = 0
        risk_failures = 0
        error_code = ""
        result = None
        acquired_identity = False
        try:
            # Acquire the narrow identity gate first. A queued second request
            # for identity A must not occupy a platform slot and block an idle
            # identity B (head-of-line blocking).
            async with self.collector_leases.lease(identity_id):
                async with self.collector_leases.lease(f"platform:{platform.value}"):
                    acquired_identity = True
                    snapshot = await self.collector_leases.snapshot(identity_id)
                    self._update_collector_runtime_after_group(
                        identity_id,
                        active_leases=snapshot.active,
                    )
                    runtime = None
                    try:
                        settings_path = getattr(
                            getattr(self.parameter, "settings", None),
                            "path",
                            PROJECT_ROOT.joinpath("settings.json"),
                        )
                        runtime = build_collector_runtime(
                            self.parameter,
                            identity,
                            credentials,
                            settings_dir=Path(settings_path).parent,
                        )
                        if prepare_runtime := getattr(runtime, "prepare", None):
                            await prepare_runtime()
                        worker = TikTok(
                            runtime.parameter,
                            self.database,
                            server_mode=True,
                        )
                        result, successes, failures = await operation(
                            worker,
                            getattr(runtime, "credentials", credentials),
                            identity_id,
                        )
                        successes = max(0, int(successes or 0))
                        failures = max(0, int(failures or 0))
                        if isinstance(result, list):
                            risk_failures = sum(
                                self._account_failure_category(
                                    item.get("reason"),
                                    item.get("outcome_code"),
                                )
                                == "identity"
                                and (
                                    "403" in str(item.get("reason") or "")
                                    or "forbidden" in str(item.get("reason") or "").lower()
                                )
                                for item in result
                                if isinstance(item, dict)
                            )
                        if failures:
                            error_code = failure_error_code
                    except CancelledError:
                        error_code = "task_cancelled"
                        raise
                    except Exception as error:
                        failures = max(1, failures)
                        error_code = self._collector_failure_error_code(
                            error,
                            failure_error_code,
                        )
                        if isinstance(error, DouyinBrowserCollectionError):
                            error.identity_id = identity_id
                        raise
                    finally:
                        if runtime is not None:
                            try:
                                await runtime.close()
                            except Exception:
                                failures = max(1, failures)
                                error_code = "identity_runtime_close_failed"
        finally:
            if acquired_identity:
                snapshot = await self.collector_leases.snapshot(identity_id)
                self._update_collector_runtime_after_group(
                    identity_id,
                    active_leases=snapshot.active,
                    successes=successes,
                    failures=failures,
                    risk_failures=risk_failures,
                    error_code=error_code,
                )
        return result

    async def _execute_collector_operation(
        self,
        *,
        platform: CollectorPlatform,
        target_type: str,
        target_key: str,
        identity_id: str = "",
        cookie: str = "",
        proxy: str = "",
        operation,
        failure_error_code: str = "collector_request_failed",
    ) -> tuple[Any, str, str]:
        """Resolve legacy overrides or a policy route, then execute once.

        Precedence is explicit identity, explicit cookie/proxy legacy override,
        automatic identity-pool routing, then the original global Parameter.
        Identity credentials are passed separately and are never written into
        the request model returned by API responses.
        """

        forced_identity_id = self._normalize_string(identity_id)
        override_credentials = CollectorCredentials(
            cookie=self._normalize_string(cookie),
            proxy=self._normalize_string(proxy),
        )
        legacy_override = bool(
            override_credentials.cookie or override_credentials.proxy
        ) and not forced_identity_id

        if legacy_override:
            result, _, _ = await operation(self, override_credentials, "")
            return result, "", "legacy_override"

        try:
            routes = self._plan_collector_routes(
                platform,
                [{"target_key": self._normalize_string(target_key)}],
                target_type=target_type,
                forced_identity_id=forced_identity_id,
            )
            pool_has_cookie = any(
                item.route_configured
                for item in self.collector_store.list_public(platform)
            )
            if routes:
                route = routes[0]
                result = await self._execute_collector_identity_operation(
                    platform,
                    route["identity_id"],
                    operation,
                    failure_error_code=failure_error_code,
                )
                return result, route["identity_id"], route["reason"]
            if forced_identity_id or pool_has_cookie:
                raise RouteUnavailable(
                    "no eligible collector identity",
                    target_key=self._normalize_string(target_key),
                    identity_id=forced_identity_id,
                )
        except IdentityNotFoundError as error:
            raise HTTPException(status_code=404, detail=str(error)) from None
        except IdentityPlatformError as error:
            raise HTTPException(status_code=409, detail=str(error)) from None
        except RouteUnavailable as error:
            raise HTTPException(status_code=409, detail=str(error)) from None

        result, _, _ = await operation(self, CollectorCredentials(), "")
        return result, "", "global_fallback"

    async def _run_ui_account_batch(
        self,
        payload: dict,
        tiktok: bool,
        progress_callback: Callable[[dict], None] | None = None,
        pause_control: dict[str, Callable] | None = None,
    ) -> DataResponse:
        use_settings = payload.get("use_settings", True)
        cookie = self._normalize_string(payload.get("cookie")) or None
        proxy = self._normalize_string(payload.get("proxy")) or None
        forced_identity_id = self._normalize_string(payload.get("identity_id"))
        platform_value = (
            CollectorPlatform.TIKTOK if tiktok else CollectorPlatform.DOUYIN
        )
        platform = "tiktok" if tiktok else "douyin"

        settings_rows = (
            self.parameter.accounts_urls_tiktok
            if tiktok
            else self.parameter.accounts_urls
        )
        rows = [vars(item) for item in settings_rows] if use_settings else payload.get("items", [])
        items = self._normalize_account_items(rows)
        if use_settings:
            for index, item in enumerate(items):
                item["_settings_index"] = index
        else:
            attach_settings_index_by_url(
                items,
                settings_rows,
                normalizer=self._normalize_string,
            )
        queued_items = [item for item in items if item["url"] and item["enable"]]
        skipped_items = max(0, len(items) - len(queued_items))
        pause_checkpoint = (
            pause_control.get("checkpoint")
            if isinstance(pause_control, dict)
            else None
        )
        unit_started = (
            pause_control.get("unit_started")
            if isinstance(pause_control, dict)
            else None
        )
        identity_failure = (
            pause_control.get("identity_failure")
            if isinstance(pause_control, dict)
            else None
        )
        task_id = (
            self._normalize_string(pause_control.get("task_id"))
            if isinstance(pause_control, dict)
            else ""
        )
        journal = getattr(self, "task_journal", None) if task_id else None
        journal_accounts = (
            journal.prepare_accounts(task_id, queued_items)
            if journal is not None
            else []
        )
        if journal_accounts:
            queued_items = []
            for account in journal_accounts:
                stored_item = dict(account["item"])
                normalized_items = self._normalize_account_items([stored_item])
                item = normalized_items[0] if normalized_items else stored_item
                item["_task_position"] = account["position"]
                if account["status"] not in {"success", "failed", "skipped"}:
                    queued_items.append(item)
            attach_settings_index_by_url(
                queued_items,
                settings_rows,
                normalizer=self._normalize_string,
            )
            progress_success = sum(
                1 for account in journal_accounts if account["status"] == "success"
            )
            progress_failed = sum(
                1 for account in journal_accounts if account["status"] == "failed"
            )
            journal_skipped = sum(
                1 for account in journal_accounts if account["status"] == "skipped"
            )
            progress_skipped = skipped_items + journal_skipped
            progress_current = progress_success + progress_failed + journal_skipped
            total_queued_items = len(journal_accounts)
            failures = [
                {
                    "index": account["position"],
                    "url": account["item"].get("url", ""),
                    "identity_id": account["identity_id"],
                    "reason": account["reason"] or _("账号作品下载失败"),
                    "outcome_code": account.get("result", {}).get(
                        "outcome_code", ""
                    ),
                }
                for account in journal_accounts
                if account["status"] == "failed"
            ]
        else:
            for position, item in enumerate(queued_items, start=1):
                item["_task_position"] = position
            progress_current = 0
            progress_success = 0
            progress_failed = 0
            progress_skipped = skipped_items
            total_queued_items = len(queued_items)
            failures = []
        unit_finished = (
            pause_control.get("unit_finished")
            if isinstance(pause_control, dict)
            else None
        )

        async def wait_for_resume() -> None:
            if callable(pause_checkpoint):
                await pause_checkpoint()

        def mark_unit_started(item: dict, identity_id: str = "") -> None:
            if journal is not None:
                journal.mark_account_running(
                    task_id,
                    int(item.get("_task_position") or 0),
                    identity_id=identity_id,
                )
            if callable(unit_started):
                unit_started()

        def mark_unit_finished() -> None:
            if callable(unit_finished):
                unit_finished()

        def report_progress(label: str) -> None:
            if not progress_callback:
                return
            total = total_queued_items
            progress_callback(
                {
                    "current": progress_current,
                    "total": total,
                    "success": progress_success,
                    "failed": progress_failed,
                    "skipped": progress_skipped,
                    "percent": (
                        round(progress_current * 100 / total)
                        if total
                        else 0
                    ),
                    "label": label,
                }
            )

        def complete_progress_item(
            status: str,
            item: dict,
            *,
            identity_id: str = "",
            reason: str = "",
            result: dict | None = None,
            advance: bool = True,
            previous_status: str = "",
        ) -> None:
            nonlocal progress_current, progress_success, progress_failed, progress_skipped
            normalized_status = (
                status if status in {"success", "failed", "skipped"} else "failed"
            )
            if journal is not None:
                journal.mark_account_finished(
                    task_id,
                    int(item.get("_task_position") or 0),
                    status=normalized_status,
                    identity_id=identity_id,
                    reason=reason,
                    result=result,
                )
            def update_count(target: str, delta: int) -> None:
                nonlocal progress_success, progress_failed, progress_skipped
                if target == "success":
                    progress_success += delta
                elif target == "failed":
                    progress_failed += delta
                elif target == "skipped":
                    progress_skipped += delta

            if advance:
                progress_current += 1
                update_count(normalized_status, 1)
            elif previous_status and previous_status != normalized_status:
                update_count(previous_status, -1)
                update_count(normalized_status, 1)
            report_progress(_("正在执行账号批次"))

        def save_account_activity(
            item: dict,
            *,
            sec_uid: str,
            execution: dict,
        ) -> None:
            activity_journal = getattr(self, "task_journal", None)
            if activity_journal is None:
                return
            context = (
                execution.get("context", {})
                if isinstance(execution.get("context"), dict)
                else {}
            )
            try:
                activity_journal.save_account_activity(
                    platform=platform,
                    url=self._normalize_string(item.get("url")),
                    sec_uid=self._normalize_string(sec_uid),
                    mark=self._normalize_string(
                        context.get("mark") or item.get("mark")
                    ),
                    latest_seen_work_at=self._normalize_string(
                        context.get("latest_seen_work_at")
                    ),
                    latest_seen_work_id=self._normalize_string(
                        context.get("latest_seen_work_id")
                    ),
                    latest_saved_work_at=self._normalize_string(
                        context.get("latest_saved_work_at")
                    ),
                    latest_saved_work_id=self._normalize_string(
                        context.get("latest_saved_work_id")
                    ),
                    status=(
                        "success"
                        if execution.get("terminal_status") in {"success", "skipped"}
                        else "failed"
                    ),
                    error=(
                        ""
                        if execution.get("terminal_status") in {"success", "skipped"}
                        else self._normalize_string(execution.get("reason"))
                    ),
                    item_count=max(0, int(context.get("item_count") or 0)),
                )
            except (OSError, TypeError, ValueError) as error:
                self.logger.warning(
                    _("保存账号看板状态失败: {error}").format(error=error)
                )

        if total_queued_items == 0:
            report_progress(_("没有可执行账号"))
            return DataResponse(
                message=_("未找到可执行的账号任务！"),
                data={
                    "platform": platform,
                    "source": "settings" if use_settings else "editor",
                    "total": len(items),
                    "queued": 0,
                    "success": 0,
                    "failed": 0,
                    "skipped": len(items),
                    "failures": [],
                },
                params=payload,
            )

        success = progress_success
        failed = progress_failed
        auto_filled_mark = 0
        auto_updated_earliest = 0
        earliest_days = self._normalize_earliest_update_days(
            getattr(self.parameter, "earliest_update_days", 0)
        )
        legacy_override = bool(cookie or proxy) and not forced_identity_id
        identity_failure_threshold = max(
            1,
            min(
                self._normalize_optional_int(
                    payload.get("identity_failure_threshold")
                )
                or 3,
                20,
            ),
        )
        identity_failure_policy_enabled = (
            self._normalize_string(payload.get("identity_failure_action")).lower()
            == "pause"
            or self._normalize_bool(
                payload.get("notify_on_identity_failure"),
                default=True,
            )
        )
        routes = []
        if queued_items and not legacy_override:
            while True:
                try:
                    try:
                        routes = self._plan_collector_account_routes(
                            platform_value,
                            queued_items,
                            forced_identity_id=forced_identity_id,
                            persist_assignments=False,
                        )
                    except TypeError as error:
                        if "persist_assignments" not in str(error):
                            raise
                        # Preserve compatibility with integrations overriding
                        # the account planner before the success-only affinity
                        # option was introduced.
                        routes = self._plan_collector_account_routes(
                            platform_value,
                            queued_items,
                            forced_identity_id=forced_identity_id,
                        )
                    pool_has_credentials = any(
                        item.route_configured
                        for item in self.collector_store.list_public(platform_value)
                    )
                    if not routes and (forced_identity_id or pool_has_credentials):
                        raise RouteUnavailable(
                            "no eligible collector identity",
                            identity_id=forced_identity_id,
                        )
                    break
                except RouteUnavailable as error:
                    paused = (
                        await identity_failure(
                            error.identity_id or forced_identity_id,
                            "identity_unavailable",
                            str(error),
                        )
                        if callable(identity_failure)
                        else False
                    )
                    if not paused:
                        raise
                    await wait_for_resume()

        async def run_entries(
            worker: "TikTok",
            entries: list[tuple[int, dict, str, str]],
            *,
            identity_id: str = "",
            identity_cookie: str | None = None,
            identity_proxy: str | None = None,
            track_progress: bool = True,
            identity_failure_state: dict[str, int] | None = None,
            pause_after_last: bool = False,
        ) -> list[dict]:
            results = []
            identity_failure_streak = (
                max(0, int(identity_failure_state.get("streak", 0)))
                if identity_failure_state is not None
                else 0
            )
            for entry_offset, (
                index,
                item,
                route_reason,
                target_key,
            ) in enumerate(entries):
                await wait_for_resume()
                mark_unit_started(item, identity_id)
                execution = None
                identity_request_failed = False
                sec_user_id = ""
                try:
                    sec_user_id = await worker.check_sec_user_id(
                        item["url"],
                        tiktok,
                    )
                    if not sec_user_id:
                        execution = {
                            "index": index,
                            "item": item,
                            "ok": False,
                            "identity_id": identity_id,
                            "route_reason": route_reason,
                            "target_key": target_key,
                            "context": {},
                            "outcome_code": "invalid_account_url",
                            "reason": _("账号链接无法提取 sec_user_id"),
                            "failure_category": "parse",
                            "terminal_status": "failed",
                            "retryable": False,
                            "cross_identity": False,
                            "affects_identity_health": False,
                        }
                    else:
                        raw_outcome = await worker.deal_account_detail(
                            index,
                            sec_user_id=sec_user_id,
                            mark=item["mark"],
                            url=item["url"],
                            tab=item["tab"],
                            earliest=item["earliest"],
                            latest=item["latest"],
                            pages=item["pages"],
                            api=False,
                            source=False,
                            cookie=identity_cookie,
                            proxy=identity_proxy,
                            tiktok=tiktok,
                            return_context=True,
                            return_outcome=True,
                        )
                        outcome = self._normalize_account_worker_outcome(raw_outcome)
                        identity_request_failed = bool(
                            outcome.get("affects_identity_health")
                        )
                        execution = {
                            "index": index,
                            "item": item,
                            "identity_id": identity_id,
                            "route_reason": route_reason,
                            "target_key": target_key,
                            **outcome,
                        }
                except CancelledError:
                    raise
                except Exception as error:
                    outcome = self._account_exception_outcome(error)
                    identity_request_failed = bool(
                        outcome.get("affects_identity_health")
                    )
                    execution = {
                        "index": index,
                        "item": item,
                        "identity_id": identity_id,
                        "route_reason": route_reason,
                        "target_key": target_key,
                        **outcome,
                    }
                finally:
                    mark_unit_finished()
                results.append(execution)
                execution["sec_uid"] = sec_user_id
                execution["_progress_status"] = self._normalize_string(
                    execution.get("terminal_status")
                ) or ("success" if execution.get("ok") else "failed")
                if track_progress:
                    complete_progress_item(
                        execution["_progress_status"],
                        item,
                        identity_id=identity_id,
                        reason=self._normalize_string(execution.get("reason")),
                        result={
                            "outcome_code": self._normalize_string(
                                execution.get("outcome_code")
                            ),
                            "failure_category": self._normalize_string(
                                execution.get("failure_category")
                            ),
                            "retryable": bool(execution.get("retryable")),
                        },
                    )
                if (
                    identity_id
                    and identity_failure_policy_enabled
                    and identity_request_failed
                ):
                    identity_failure_streak += 1
                    if (
                        identity_failure_streak >= identity_failure_threshold
                        and (
                            entry_offset + 1 < len(entries)
                            or pause_after_last
                        )
                        and callable(identity_failure)
                    ):
                        paused = await identity_failure(
                            identity_id,
                            "identity_failure_threshold",
                            _(
                                "已配置身份连续 {count} 个账号采集失败"
                            ).format(count=identity_failure_streak),
                        )
                        identity_failure_streak = 0
                        if paused:
                            await wait_for_resume()
                elif not identity_request_failed:
                    identity_failure_streak = 0
                if identity_failure_state is not None:
                    identity_failure_state["streak"] = identity_failure_streak
            return results

        async def run_identity_group(
            identity_id: str,
            entries: list[tuple],
            *,
            track_progress: bool = True,
        ) -> list[dict]:
            chunk_size = (
                self.DOUYIN_ACCOUNT_LEASE_CHUNK_SIZE
                if platform_value == CollectorPlatform.DOUYIN
                else max(1, len(entries))
            )
            chunk_size = max(1, int(chunk_size))
            group_results: list[dict] = []
            identity_failure_state = {"streak": 0}

            for chunk_start in range(0, len(entries), chunk_size):
                chunk = entries[chunk_start : chunk_start + chunk_size]
                has_more_entries = chunk_start + len(chunk) < len(entries)

                async def operation(worker, credentials, selected_identity_id):
                    chunk_results = await run_entries(
                        worker,
                        chunk,
                        identity_id=selected_identity_id,
                        identity_cookie=credentials.cookie or None,
                        identity_proxy=credentials.proxy or None,
                        track_progress=track_progress,
                        identity_failure_state=identity_failure_state,
                        pause_after_last=has_more_entries,
                    )
                    chunk_success = sum(
                        1
                        for result in chunk_results
                        if not result.get("affects_identity_health")
                    )
                    chunk_failures = sum(
                        1
                        for result in chunk_results
                        if result.get("affects_identity_health")
                    )
                    return chunk_results, chunk_success, chunk_failures

                while True:
                    try:
                        chunk_results = (
                            await self._execute_collector_identity_operation(
                                platform_value,
                                identity_id,
                                operation,
                                failure_error_code="account_collection_failed",
                            )
                        )
                        group_results.extend(chunk_results)
                        break
                    except CancelledError:
                        raise
                    except Exception as error:
                        paused = (
                            await identity_failure(
                                identity_id,
                                "identity_runtime_unavailable",
                                str(error),
                            )
                            if callable(identity_failure)
                            else False
                        )
                        if paused:
                            await wait_for_resume()
                            continue
                        remaining_entries = entries[chunk_start:]
                        failed_results = [
                            {
                                "index": index,
                                "item": item,
                                "ok": False,
                                "identity_id": identity_id,
                                "route_reason": reason,
                                "target_key": target_key,
                                "context": {},
                                "outcome_code": "identity_runtime_unavailable",
                                "reason": _("身份运行环境执行失败"),
                                "failure_category": "identity",
                                "terminal_status": "failed",
                                "retryable": True,
                                "cross_identity": True,
                                "affects_identity_health": True,
                                "sec_uid": "",
                            }
                            for index, item, reason, target_key in remaining_entries
                        ]
                        if track_progress:
                            for execution in failed_results:
                                execution["_progress_status"] = "failed"
                                complete_progress_item(
                                    "failed",
                                    execution["item"],
                                    identity_id=identity_id,
                                    reason=execution["reason"],
                                    result={
                                        "outcome_code": execution["outcome_code"],
                                        "failure_category": execution[
                                            "failure_category"
                                        ],
                                        "retryable": True,
                                    },
                                )
                        group_results.extend(failed_results)
                        return group_results

                if has_more_entries:
                    # Give tasks already queued on this identity/platform (for
                    # example the 30-minute collection monitor) a chance to
                    # acquire the lease before this batch requests it again.
                    await sleep(0)

            return group_results

        def alternate_identity_ids(execution: dict) -> list[str]:
            if forced_identity_id or legacy_override or not routes:
                return []
            target_key = self._normalize_string(execution.get("target_key"))
            assignment = self.collector_store.get_assignment(
                platform_value,
                "account",
                target_key,
            )
            if assignment and assignment.source == AssignmentSource.EXPLICIT:
                return []
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
                and candidate_available(item, platform=platform_value)
            ]
            policy = self.collector_store.get_policy(platform_value)
            preferred = [
                *policy.fallback_identity_ids,
                policy.default_identity_id,
            ]
            ordered = []
            for identity_id in [
                *preferred,
                *(
                    item.identity_id
                    for item in sorted(
                        candidates,
                        key=lambda item: (item.active_leases, item.identity_id),
                    )
                ),
            ]:
                if (
                    identity_id
                    and identity_id != execution.get("identity_id")
                    and identity_id in public
                    and identity_id not in ordered
                ):
                    ordered.append(identity_id)
            return ordered

        def persist_successful_identity(execution: dict) -> bool:
            identity_id = self._normalize_string(execution.get("identity_id"))
            target_key = self._normalize_string(execution.get("target_key"))
            if not identity_id or not target_key or forced_identity_id:
                return False
            policy = self.collector_store.get_policy(platform_value)
            if policy.strategy != RoutingStrategy.STICKY_BALANCED:
                return False
            assignment = self.collector_store.get_assignment(
                platform_value,
                "account",
                target_key,
            )
            if assignment and assignment.source == AssignmentSource.EXPLICIT:
                return False
            self.collector_store.upsert_assignments(
                [
                    CollectorAssignment(
                        platform=platform_value,
                        target_type="account",
                        target_key=target_key,
                        identity_id=identity_id,
                        source=AssignmentSource.POLICY,
                    )
                ]
            )
            return True

        def outcome_priority(execution: dict) -> int:
            if execution.get("ok"):
                return 100
            if execution.get("terminal_status") == "skipped":
                return 90
            category = execution.get("failure_category")
            return {
                "visibility": 70,
                "account_unavailable": 60,
                "identity": 50,
                "network": 40,
                "parse": 30,
                "download": 30,
                "other": 10,
            }.get(category, 0)

        report_progress(_("准备账号批次"))
        if routes:
            grouped: dict[str, list[tuple]] = {}
            for route in routes:
                index = int(route["item"].get("_task_position") or 0)
                grouped.setdefault(route["identity_id"], []).append(
                    (
                        index,
                        route["item"],
                        route["reason"],
                        route["target_key"],
                    )
                )
            nested_results = await gather(
                *(
                    run_identity_group(identity_id, entries)
                    for identity_id, entries in grouped.items()
                )
            )
            item_results = sorted(
                (item for group in nested_results for item in group),
                key=lambda item: item["index"],
            )
        else:
            item_results = await run_entries(
                self,
                [
                    (
                        index,
                        item,
                        "legacy_settings",
                        self._normalize_account_url(item["url"]) or item["url"],
                    )
                    for index, item in (
                        (
                            int(item.get("_task_position") or 0),
                            item,
                        )
                        for item in queued_items
                    )
                ],
                identity_cookie=cookie,
                identity_proxy=proxy,
            )

        resolved_results = []
        for initial_execution in item_results:
            initial_identity_id = self._normalize_string(
                initial_execution.get("identity_id")
            )
            attempts = [
                {
                    "identity_id": initial_identity_id,
                    "outcome_code": self._normalize_string(
                        initial_execution.get("outcome_code")
                    ),
                    "reason": self._normalize_string(
                        initial_execution.get("reason")
                    ),
                }
            ]
            selected = initial_execution
            if (
                not initial_execution.get("ok")
                and initial_execution.get("cross_identity")
            ):
                candidates = alternate_identity_ids(initial_execution)
                if candidates:
                    report_progress(_("正在跨身份核验账号可见性"))
                for candidate_id in candidates:
                    retry_results = await run_identity_group(
                        candidate_id,
                        [
                            (
                                initial_execution["index"],
                                initial_execution["item"],
                                "visibility_probe",
                                initial_execution["target_key"],
                            )
                        ],
                        track_progress=False,
                    )
                    retry_execution = retry_results[0]
                    attempts.append(
                        {
                            "identity_id": candidate_id,
                            "outcome_code": self._normalize_string(
                                retry_execution.get("outcome_code")
                            ),
                            "reason": self._normalize_string(
                                retry_execution.get("reason")
                            ),
                        }
                    )
                    if outcome_priority(retry_execution) > outcome_priority(selected):
                        selected = retry_execution
                    if retry_execution.get("ok") or (
                        retry_execution.get("terminal_status") == "skipped"
                        and not retry_execution.get("retryable")
                    ):
                        selected = retry_execution
                        break
            selected["attempted_identities"] = attempts
            selected["initial_identity_id"] = initial_identity_id
            selected["_progress_status"] = initial_execution.get(
                "_progress_status",
                "success" if initial_execution.get("ok") else "failed",
            )
            selected["recovered_by_identity"] = (
                self._normalize_string(selected.get("identity_id"))
                if selected.get("ok")
                and self._normalize_string(selected.get("identity_id"))
                != initial_identity_id
                else ""
            )
            if selected.get("ok"):
                persist_successful_identity(selected)
            resolved_results.append(selected)
        item_results = sorted(resolved_results, key=lambda item: item["index"])

        for execution in item_results:
            result_metadata = {
                "outcome_code": self._normalize_string(
                    execution.get("outcome_code")
                ),
                "failure_category": self._normalize_string(
                    execution.get("failure_category")
                ),
                "retryable": bool(execution.get("retryable")),
                "attempted_identities": execution.get("attempted_identities", []),
                "recovered_by_identity": self._normalize_string(
                    execution.get("recovered_by_identity")
                ),
                "context": {
                    key: execution.get("context", {}).get(key)
                    for key in ("item_count", "download")
                    if key in execution.get("context", {})
                },
            }
            save_account_activity(
                execution["item"],
                sec_uid=self._normalize_string(execution.get("sec_uid")),
                execution=execution,
            )
            complete_progress_item(
                self._normalize_string(execution.get("terminal_status"))
                or ("success" if execution.get("ok") else "failed"),
                execution["item"],
                identity_id=self._normalize_string(execution.get("identity_id")),
                reason=self._normalize_string(execution.get("reason")),
                result=result_metadata,
                advance=False,
                previous_status=self._normalize_string(
                    execution.get("_progress_status")
                ),
            )

        failed_streak = 0
        failed_streak_max = 0
        route_results = []
        for execution in item_results:
            item = execution["item"]
            route_results.append(
                {
                    "url": item["url"],
                    "identity_id": execution.get("identity_id", ""),
                    "selected_by": execution.get("route_reason", ""),
                    "attempted_identities": execution.get(
                        "attempted_identities", []
                    ),
                    "recovered_by_identity": execution.get(
                        "recovered_by_identity", ""
                    ),
                }
            )
            if execution.get("terminal_status") == "skipped":
                failed_streak = 0
                continue
            if not execution.get("ok"):
                failed += 1
                failed_streak += 1
                failed_streak_max = max(failed_streak_max, failed_streak)
                failures.append(
                    {
                        "index": execution["index"],
                        "url": item["url"],
                        "identity_id": execution.get("identity_id", ""),
                        "reason": execution.get("reason") or _("账号作品下载失败"),
                        "outcome_code": execution.get("outcome_code", ""),
                        "failure_category": execution.get(
                            "failure_category", "other"
                        ),
                        "retryable": bool(execution.get("retryable")),
                        "attempted_identities": execution.get(
                            "attempted_identities", []
                        ),
                    }
                )
                continue
            success += 1
            failed_streak = 0
            context = execution.get("context", {})
            row_index = item.get("_settings_index")
            if isinstance(row_index, int) and 0 <= row_index < len(settings_rows):
                if (
                    getattr(self.parameter, "auto_backfill_mark", True)
                    and self._apply_missing_mark(
                        settings_rows[row_index],
                        context.get("mark", ""),
                    )
                ):
                    auto_filled_mark += 1
                if use_settings:
                    earliest_updated, earliest_target = self._apply_auto_update_earliest(
                        settings_rows[row_index],
                        earliest_days,
                    )
                    if earliest_updated:
                        auto_updated_earliest += 1
                        self.logger.info(
                            _("已更新账号 earliest: {target} -> {date}").format(
                                target=getattr(settings_rows[row_index], "mark", "")
                                or item["url"],
                                date=earliest_target,
                            )
                        )
        skipped = progress_skipped
        if failed == 0 and success == 0 and skipped > 0:
            message = _("账号批量任务完成，没有需要下载的可见作品。")
        elif success == 0:
            message = _("账号批量下载任务失败！")
        elif failed > 0:
            message = _("账号批量下载任务完成，部分账号未成功。")
        else:
            message = _("账号批量下载任务完成！")
        self._persist_account_runtime_updates(
            mark_updated=auto_filled_mark,
            earliest_updated=auto_updated_earliest,
            tiktok=tiktok,
        )
        report_progress(_("账号批次执行完成"))
        return DataResponse(
            message=message,
            data={
                "platform": platform,
                "source": "settings" if use_settings else "editor",
                "total": total_queued_items + skipped_items,
                "queued": total_queued_items,
                "success": success,
                "failed": failed,
                "skipped": skipped,
                "failed_streak_max": failed_streak_max,
                "mark_backfilled": auto_filled_mark,
                "earliest_updated": auto_updated_earliest,
                "failures": failures,
                "routes": route_results,
            },
            params=payload,
        )

    async def _run_ui_avatar_batch(
        self,
        payload: dict,
        progress_callback: Callable[[dict], None] | None = None,
        pause_control: dict[str, Callable] | None = None,
    ) -> DataResponse:
        self._validate_ui_avatar_batch_payload(payload)
        platform = self._normalize_board_platform(payload.get("platform"))
        requested_urls = {
            self._normalize_string(item)
            for item in payload.get("urls", [])
            if self._normalize_string(item)
        }
        skip_existing = self._normalize_bool(
            payload.get("skip_existing"),
            default=True,
        )
        max_candidates = max(
            1,
            min(int(payload.get("max_candidates") or 12), 30),
        )
        rows = [
            {
                "url": self._normalize_string(row.get("url")),
                "mark": self._normalize_string(row.get("mark")),
            }
            for row in self._active_account_rows(platform)
            if self._normalize_string(row.get("url"))
            and (
                not requested_urls
                or self._normalize_string(row.get("url")) in requested_urls
            )
        ]

        pause_checkpoint = (
            pause_control.get("checkpoint")
            if isinstance(pause_control, dict)
            else None
        )
        unit_started = (
            pause_control.get("unit_started")
            if isinstance(pause_control, dict)
            else None
        )
        unit_finished = (
            pause_control.get("unit_finished")
            if isinstance(pause_control, dict)
            else None
        )
        task_id = (
            self._normalize_string(pause_control.get("task_id"))
            if isinstance(pause_control, dict)
            else ""
        )
        journal = getattr(self, "task_journal", None) if task_id else None
        journal_accounts = (
            journal.prepare_accounts(task_id, rows)
            if journal is not None
            else []
        )
        if journal_accounts:
            pending_rows = []
            for account in journal_accounts:
                item = dict(account["item"])
                item["_task_position"] = account["position"]
                if account["status"] not in {"success", "failed", "skipped"}:
                    pending_rows.append(item)
            rows = pending_rows
            success = sum(
                1 for account in journal_accounts if account["status"] == "success"
            )
            failed = sum(
                1 for account in journal_accounts if account["status"] == "failed"
            )
            skipped = sum(
                1 for account in journal_accounts if account["status"] == "skipped"
            )
            total = len(journal_accounts)
        else:
            for position, item in enumerate(rows, start=1):
                item["_task_position"] = position
            success = 0
            failed = 0
            skipped = 0
            total = len(rows)
        current = success + failed + skipped
        failures = []

        def report_progress(label: str) -> None:
            if not progress_callback:
                return
            progress_callback(
                {
                    "current": current,
                    "total": total,
                    "success": success,
                    "failed": failed,
                    "skipped": skipped,
                    "percent": round(current * 100 / total) if total else 0,
                    "label": label,
                }
            )

        async def wait_for_resume() -> None:
            if callable(pause_checkpoint):
                await pause_checkpoint()

        def start_item(item: dict) -> None:
            if journal is not None:
                journal.mark_account_running(
                    task_id,
                    int(item.get("_task_position") or 0),
                )
            if callable(unit_started):
                unit_started()

        def finish_item(
            item: dict,
            *,
            status: str,
            reason: str = "",
        ) -> None:
            nonlocal current, success, failed, skipped
            if journal is not None:
                journal.mark_account_finished(
                    task_id,
                    int(item.get("_task_position") or 0),
                    status=status,
                    reason=reason,
                )
            current += 1
            if status == "success":
                success += 1
            elif status == "skipped":
                skipped += 1
            else:
                failed += 1
            if callable(unit_finished):
                unit_finished()
            report_progress(_("正在处理账户头像"))

        report_progress(_("正在准备账户头像"))
        if total == 0:
            return DataResponse(
                message=_("没有可处理的账户头像。"),
                data={
                    "platform": platform,
                    "total": 0,
                    "success": 0,
                    "failed": 0,
                    "skipped": 0,
                    "failures": [],
                },
                params=payload,
            )

        root = self._scope_root("download").expanduser().resolve()
        account_dirs = self._account_board_dirs(root)
        media_cache: dict[str, tuple[list[str], list[str]]] = {}
        avatars = self._load_account_board_avatars()
        for item in rows:
            await wait_for_resume()
            start_item(item)
            url = self._normalize_string(item.get("url"))
            mark = self._normalize_string(item.get("mark"))
            pin_key = self._account_pin_key(platform, url)
            if skip_existing and self._coerce_project_image_relpath(
                avatars.get(pin_key, "")
            ):
                finish_item(
                    item,
                    status="skipped",
                    reason=_("已有固定头像"),
                )
                continue
            folder = self._match_account_board_dir(
                mark=mark,
                url=url,
                candidates=account_dirs,
            )
            if not folder:
                reason = _("未匹配到账户媒体目录")
                failures.append({"url": url, "reason": reason})
                finish_item(item, status="failed", reason=reason)
                continue
            images, videos = self._collect_media_relpaths(
                root,
                folder,
                media_cache,
            )
            # If an account contains images, inspect images exclusively. Video
            # extraction is a fallback only for accounts without any images.
            media_kind = "image" if images else "video"
            media_paths = (images if images else videos)[:max_candidates]
            if not media_paths:
                reason = _("账户目录中没有可处理的图片或视频")
                failures.append({"url": url, "reason": reason})
                finish_item(item, status="failed", reason=reason)
                continue

            output_path = self._account_avatar_output_path(
                platform=platform,
                url=url,
                mark=mark,
                extension=".jpg",
            )
            generated = None
            last_error = ""
            for media_path in media_paths:
                try:
                    generated = generate_face_avatar(
                        resolve_within_root(root, media_path),
                        output_path,
                    )
                    generated["source_path"] = media_path
                    break
                except (OSError, RuntimeError, ValueError) as error:
                    last_error = str(error)
            if not generated:
                reason = (
                    _("图片中未找到可用人脸")
                    if media_kind == "image"
                    else _("视频抽帧中未找到可用人脸")
                )
                if last_error:
                    reason = f"{reason}: {last_error}"
                failures.append({"url": url, "reason": reason})
                finish_item(item, status="failed", reason=reason)
                continue
            try:
                avatar_rel = self._set_account_avatar_path(
                    platform,
                    url,
                    relative_path(PROJECT_ROOT, output_path),
                )
            except OSError as error:
                reason = _("保存头像映射失败: {error}").format(error=error)
                failures.append({"url": url, "reason": reason})
                finish_item(item, status="failed", reason=reason)
                continue
            avatars[pin_key] = avatar_rel
            finish_item(item, status="success")

        if success == 0 and failed > 0:
            message = _("账户头像批量处理失败！")
        elif failed > 0:
            message = _(
                "账户头像处理完成，部分账户未完成：成功 {success}，跳过 {skipped}，未完成 {failed}。"
            ).format(
                success=success,
                skipped=skipped,
                failed=failed,
            )
        else:
            message = _(
                "账户头像处理完成：成功 {success}，跳过 {skipped}。"
            ).format(
                success=success,
                skipped=skipped,
            )
        return DataResponse(
            message=message,
            data={
                "platform": platform,
                "total": total,
                "success": success,
                "failed": failed,
                "skipped": skipped,
                "failures": failures[:200],
                "media_policy": "image_first_video_only_when_no_images",
            },
            params=payload,
        )

    async def _run_ui_detail_links(
        self,
        payload: dict,
        tiktok: bool,
    ) -> DataResponse:
        platform = "tiktok" if tiktok else "douyin"
        platform_value = (
            CollectorPlatform.TIKTOK if tiktok else CollectorPlatform.DOUYIN
        )
        links = self._normalize_link_inputs(payload.get("links", []))
        if not links:
            return DataResponse(
                message=_("未找到有效链接！"),
                data={
                    "platform": platform,
                    "input_links": 0,
                    "parsed_ids": 0,
                    "downloaded": 0,
                    "invalid_links": [],
                    "preview": "",
                },
                params=redact_webui_value(payload),
            )

        forced_identity_id = self._normalize_string(payload.get("identity_id"))
        direct_credentials = CollectorCredentials(
            cookie=self._normalize_string(payload.get("cookie")),
            proxy=self._normalize_string(payload.get("proxy")),
        )
        legacy_override = bool(
            direct_credentials.cookie or direct_credentials.proxy
        ) and not forced_identity_id
        route_items = [
            {
                "index": index,
                "link": link,
                "target_key": (
                    link
                    if len(link) <= 2048
                    else f"link:{md5(link.encode()).hexdigest()}"
                ),
            }
            for index, link in enumerate(links)
        ]
        if legacy_override:
            routes = [
                {
                    "item": item,
                    "identity_id": "",
                    "target_key": item["target_key"],
                    "reason": "legacy_override",
                }
                for item in route_items
            ]
        else:
            try:
                routes = self._plan_collector_routes(
                    platform_value,
                    route_items,
                    target_type="detail",
                    target_key_getter=lambda item: item["target_key"],
                    forced_identity_id=forced_identity_id,
                )
                pool_has_cookie = any(
                    item.route_configured
                    for item in self.collector_store.list_public(platform_value)
                )
                if not routes and (forced_identity_id or pool_has_cookie):
                    raise RouteUnavailable("no eligible collector identity")
            except IdentityNotFoundError as error:
                raise HTTPException(status_code=404, detail=str(error)) from None
            except IdentityPlatformError as error:
                raise HTTPException(status_code=409, detail=str(error)) from None
            except RouteUnavailable as error:
                raise HTTPException(status_code=409, detail=str(error)) from None
            if not routes:
                routes = [
                    {
                        "item": item,
                        "identity_id": "",
                        "target_key": item["target_key"],
                        "reason": "global_fallback",
                    }
                    for item in route_items
                ]

        grouped: dict[str, list[dict]] = {}
        for route in routes:
            grouped.setdefault(route["identity_id"], []).append(route)

        async def run_group(
            worker,
            credentials,
            selected_identity_id,
            entries,
        ):
            proxy = credentials.proxy or None
            parser = worker.links_tiktok if tiktok else worker.links
            invalid_links = []
            parsed_ids = []
            parsed_urls = []
            route_results = []
            seen = set()
            for route in entries:
                text = route["item"]["link"]
                item_ids = []
                item_urls = []
                if tiktok:
                    items = await worker._parse_tiktok_detail_targets(text, proxy)
                    if items:
                        item_ids, item_urls = worker._split_tiktok_detail_targets(items)
                    else:
                        invalid_links.append(text)
                else:
                    item_ids = await parser.run(text, proxy=proxy) or []
                    if not item_ids:
                        invalid_links.append(text)
                for item_index, detail_id in enumerate(item_ids):
                    detail_url = (
                        item_urls[item_index]
                        if item_index < len(item_urls)
                        else ""
                    )
                    key = (detail_id, detail_url) if tiktok else detail_id
                    if key in seen:
                        continue
                    seen.add(key)
                    parsed_ids.append(detail_id)
                    if tiktok:
                        parsed_urls.append(detail_url)
                route_results.append(
                    {
                        "index": route["item"]["index"],
                        "link": text,
                        "identity_id": selected_identity_id,
                        "selected_by": route["reason"],
                        "parsed_ids": len(item_ids),
                    }
                )

            data = None
            if parsed_ids:
                root, params, logger = worker.record.run(worker.parameter)
                async with logger(root, console=worker.console, **params) as record:
                    data = await worker._handle_detail(
                        parsed_ids,
                        tiktok,
                        record,
                        api=True,
                        source=False,
                        cookie=credentials.cookie or None,
                        proxy=proxy,
                        detail_urls=parsed_urls if tiktok else None,
                    )
                if data:
                    await worker.downloader.run(data, "detail", tiktok=tiktok)
            return (
                {
                    "parsed_ids": len(parsed_ids),
                    "downloaded": len(data or []),
                    "invalid_links": invalid_links,
                    "preview": (
                        worker._get_preview_image(data[0]) if data else ""
                    ),
                    "routes": route_results,
                },
                int(bool(data)),
                int(bool(parsed_ids) and not bool(data)),
            )

        async def execute_group(identity_id: str, entries: list[dict]):
            async def operation(worker, credentials, selected_identity_id):
                return await run_group(
                    worker,
                    credentials,
                    selected_identity_id,
                    entries,
                )

            if identity_id:
                return await self._execute_collector_identity_operation(
                    platform_value,
                    identity_id,
                    operation,
                    failure_error_code="detail_links_collection_failed",
                )
            return (
                await operation(self, direct_credentials, "")
            )[0]

        group_entries = list(grouped.items())
        group_outputs = await gather(
            *(execute_group(identity_id, entries) for identity_id, entries in group_entries),
            return_exceptions=True,
        )
        summaries = []
        for (identity_id, entries), output in zip(group_entries, group_outputs):
            if isinstance(output, CancelledError):
                raise output
            if isinstance(output, BaseException):
                summaries.append(
                    {
                        "parsed_ids": 0,
                        "downloaded": 0,
                        "invalid_links": [entry["item"]["link"] for entry in entries],
                        "preview": "",
                        "routes": [
                            {
                                "index": entry["item"]["index"],
                                "link": entry["item"]["link"],
                                "identity_id": identity_id,
                                "selected_by": entry["reason"],
                                "parsed_ids": 0,
                                "error": "identity_execution_failed",
                            }
                            for entry in entries
                        ],
                    }
                )
            else:
                summaries.append(output)

        downloaded = sum(item["downloaded"] for item in summaries)
        parsed_count = sum(item["parsed_ids"] for item in summaries)
        invalid_links = [
            link for item in summaries for link in item["invalid_links"]
        ]
        route_results = sorted(
            (route for item in summaries for route in item["routes"]),
            key=lambda item: item["index"],
        )
        preview = next(
            (item["preview"] for item in summaries if item["preview"]),
            "",
        )
        selected_ids = {
            route["identity_id"] for route in route_results if route["identity_id"]
        }
        selected_reasons = {route["selected_by"] for route in route_results}
        selected_identity_id = (
            next(iter(selected_ids)) if len(selected_ids) == 1 else ""
        )
        selected_by = (
            next(iter(selected_reasons))
            if len(selected_reasons) == 1
            else "mixed"
        )
        if downloaded == 0:
            message = _("作品下载失败！") if parsed_count else _("链接解析失败！")
        elif invalid_links:
            message = _("链接下载任务完成，部分链接未成功解析。")
        else:
            message = _("链接下载任务完成！")
        response = DataResponse(
            message=message,
            data={
                "platform": platform,
                "input_links": len(links),
                "parsed_ids": parsed_count,
                "downloaded": downloaded,
                "invalid_links": invalid_links,
                "preview": preview,
                "selected_identity_id": selected_identity_id,
                "selected_by": selected_by,
                "routes": route_results,
            },
            params=redact_webui_value(payload),
        )
        return self._attach_collector_route(
            response,
            selected_identity_id,
            selected_by,
        )

    async def _verify_accounts(
        self,
        payload: dict,
    ) -> dict:
        self._validate_ui_account_verify_payload(payload)
        platform = payload.get("platform", "douyin")
        tiktok = platform == "tiktok"
        platform_name = "TikTok" if tiktok else "抖音"
        use_settings = payload.get("use_settings", True)
        move_deleted = payload.get("move_deleted", True)
        cookie = self._normalize_string(payload.get("cookie")) or None
        proxy = self._normalize_string(payload.get("proxy")) or None
        forced_identity_id = self._normalize_string(payload.get("identity_id"))
        platform_value = (
            CollectorPlatform.TIKTOK if tiktok else CollectorPlatform.DOUYIN
        )
        source_rows = (
            self._account_rows(tiktok)
            if use_settings
            else self._normalize_account_items(payload.get("items", []))
        )
        rows = self._normalize_account_items(source_rows)
        total_targets = sum(1 for item in rows if item.get("url"))
        self.logger.info(
            _(
                "开始检测账号有效性（{platform}）：配置 {rows} 行，待检测 {targets} 条"
            ).format(
                platform=platform_name,
                rows=len(rows),
                targets=total_targets,
            )
        )

        checked = []
        missing_rows = []
        valid_rows = []
        processed = 0
        for index, item in enumerate(rows, start=1):
            url = item.get("url")
            if not url:
                continue
            processed += 1
            target_name = item.get("mark") or url
            self.logger.info(
                _("账号检测 {current}/{total}: {target}").format(
                    current=processed,
                    total=total_targets,
                    target=target_name,
                )
            )
            async def operation(worker, credentials, selected_identity_id):
                sec_user_id = await worker.check_sec_user_id(url, tiktok)
                if not sec_user_id:
                    return {"sec_user_id": "", "info": {}}, 0, 0
                info = await worker.get_user_info_data(
                    tiktok=tiktok,
                    cookie=credentials.cookie or None,
                    proxy=credentials.proxy or None,
                    sec_user_id=sec_user_id,
                )
                return (
                    {"sec_user_id": sec_user_id, "info": info},
                    int(bool(info)),
                    int(not bool(info)),
                )

            execution, selected_identity_id, selected_by = (
                await self._execute_collector_operation(
                    platform=platform_value,
                    target_type="account",
                    target_key=url,
                    identity_id=forced_identity_id,
                    cookie=cookie or "",
                    proxy=proxy or "",
                    operation=operation,
                    failure_error_code="account_verification_failed",
                )
            )
            sec_user_id = execution["sec_user_id"]
            if not sec_user_id:
                reason = _("链接无法提取账号 ID")
                result = {
                    "index": index,
                    "url": url,
                    "exists": False,
                    "selected_identity_id": selected_identity_id,
                    "selected_by": selected_by,
                    "reason": reason,
                }
                checked.append(result)
                self.logger.warning(
                    _("账号失效: {target}（{reason}）").format(
                        target=target_name,
                        reason=reason,
                    )
                )
                missing_rows.append(item | {"reason": result["reason"]})
                continue
            info = execution["info"]
            exists, reason = self._verify_user_info_state(
                info,
                sec_user_id,
                tiktok,
            )
            if not exists:
                result = {
                    "index": index,
                    "url": url,
                    "exists": False,
                    "selected_identity_id": selected_identity_id,
                    "selected_by": selected_by,
                    "reason": reason or _("账号主页不可访问或不存在"),
                }
                checked.append(result)
                self.logger.warning(
                    _("账号失效: {target}（{reason}）").format(
                        target=target_name,
                        reason=result["reason"],
                    )
                )
                missing_rows.append(item | {"reason": result["reason"]})
                continue
            checked.append(
                {
                    "index": index,
                    "url": url,
                    "exists": True,
                    "selected_identity_id": selected_identity_id,
                    "selected_by": selected_by,
                    "reason": "",
                }
            )
            self.logger.info(
                _("账号有效: {target}").format(target=target_name)
            )
            valid_rows.append(item)

        backup_path = ""
        if move_deleted and use_settings and missing_rows:
            backup_path = self._backup_settings_file(
                reason=f"verify_{platform}",
            )
            deleted_current = self._account_rows(tiktok, deleted=True)
            deleted_incoming = [
                item
                | {
                    "deleted_at": self._now_text(),
                    "reason": item.get("reason", ""),
                    "enable": False,
                }
                for item in missing_rows
            ]
            merged_deleted = self._merge_deleted_accounts(
                deleted_current,
                deleted_incoming,
            )
            self._set_account_rows(tiktok, valid_rows)
            self._set_account_rows(tiktok, merged_deleted, deleted=True)
            self.parameter.settings.update(self.parameter.get_settings_data())
            self.logger.info(
                _("已将 {count} 条失效账号移入回收站，备份文件: {path}").format(
                    count=len(missing_rows),
                    path=backup_path,
                )
            )
        elif missing_rows:
            self.logger.info(
                _("检测到 {count} 条失效账号（未自动转移）").format(
                    count=len(missing_rows),
                )
            )

        checked_count = len(checked)
        exists_count = sum(1 for item in checked if item["exists"])
        missing_count = checked_count - exists_count
        moved_count = (
            len(missing_rows)
            if (move_deleted and use_settings)
            else 0
        )
        self.logger.info(
            _(
                "账号检测完成（{platform}）：检测 {checked} 条，有效 {exists}，失效 {missing}，转移 {moved}"
            ).format(
                platform=platform_name,
                checked=checked_count,
                exists=exists_count,
                missing=missing_count,
                moved=moved_count,
            )
        )

        return {
            "platform": platform,
            "checked": checked_count,
            "exists": exists_count,
            "missing": missing_count,
            "items": checked,
            "moved_to_deleted": moved_count,
            "backup_path": backup_path,
            "accounts": self._account_rows(tiktok),
            "deleted_accounts": self._account_rows(tiktok, deleted=True),
        }

    @staticmethod
    def _coerce_log_list(records: list | tuple | None) -> list[dict]:
        if not isinstance(records, (list, tuple)):
            return []
        return [item for item in records if isinstance(item, dict)]

    @classmethod
    def _fetch_logs(cls, after_id: int = 0, limit: int = 200) -> list[dict]:
        logs = []
        if hasattr(LOG_STORE, "list_after"):
            try:
                logs = LOG_STORE.list_after(after_id=after_id, limit=limit)
            except TypeError:
                logs = LOG_STORE.list_after(after_id, limit)
        elif hasattr(LOG_STORE, "latest"):
            try:
                logs = LOG_STORE.latest(limit=limit)
            except TypeError:
                logs = LOG_STORE.latest(limit)
            logs = [
                item
                for item in cls._coerce_log_list(logs)
                if int(item.get("id", 0)) > after_id
            ]
        return cls._coerce_log_list(logs)

    @staticmethod
    def _normalize_limit(limit: int) -> int:
        return max(1, min(limit, 1000))

    async def handle_redirect(self, text: str, proxy: str = None) -> str:
        return await self.links.run(
            text,
            "",
            proxy,
        )

    async def handle_redirect_tiktok(self, text: str, proxy: str = None) -> str:
        return await self.links_tiktok.run(
            text,
            "",
            proxy,
        )

    async def run_server(
        self,
        host=SERVER_HOST,
        port=SERVER_PORT,
        log_level="info",
    ):
        self.server = FastAPI(
            debug=VERSION_BETA,
            title="FetchShelf",
            version=__VERSION__,
        )
        self.server.mount(
            "/ui/static",
            StaticFiles(directory=self.WEBUI_STATIC_DIR, check_dir=False),
            name="webui-static",
        )
        self.setup_routes()
        config = Config(
            self.server,
            host=host,
            port=port,
            log_level=log_level,
        )
        server = Server(config)
        await self._configure_collector_leases()
        await self._start_ui_task_workers()
        await self._start_ui_schedules()
        try:
            await server.serve()
        finally:
            await self._get_collector_login_browser().cleanup()
            await self._stop_ui_schedules()
            await self._stop_ui_task_workers()
            self.task_journal.close()
            self.collector_store.close()


    @staticmethod
    def _attach_collector_route(response, identity_id: str, reason: str):
        if isinstance(response, DataResponse):
            params = dict(response.params or {})
            params["selected_identity_id"] = identity_id
            params["selected_by"] = reason
            response.params = params
        return response

    async def handle_search(self, extract):
        platform = CollectorPlatform.DOUYIN

        async def operation(worker, credentials, selected_identity_id):
            runtime_extract = extract.model_copy(
                update={
                    "cookie": credentials.cookie,
                    "proxy": credentials.proxy,
                }
            )
            data = await worker.deal_search_data(
                runtime_extract,
                runtime_extract.source,
            )
            response_extract = extract.model_copy(
                update={"identity_id": selected_identity_id or extract.identity_id}
            )
            if isinstance(data, list):
                response = self.success_response(
                    response_extract,
                    *(data, None) if any(data) else (None, _("搜索结果为空！")),
                )
                return response, int(bool(data and any(data))), int(not (data and any(data)))
            return self.failed_response(response_extract), 0, 1

        response, identity_id, reason = await self._execute_collector_operation(
            platform=platform,
            target_type="search",
            target_key=f"{getattr(extract, 'channel', 0)}:{extract.keyword}",
            identity_id=extract.identity_id,
            cookie=extract.cookie,
            proxy=extract.proxy,
            operation=operation,
            failure_error_code="search_collection_failed",
        )
        return self._attach_collector_route(response, identity_id, reason)

    async def handle_detail(
        self,
        extract: Detail | DetailTikTok,
        tiktok=False,
    ):
        if tiktok and not (
            getattr(extract, "detail_id", "") or getattr(extract, "detail_url", "")
        ):
            return self.failed_response(
                extract,
                _("detail_id 和 detail_url 不能同时为空！"),
            )
        platform = (
            CollectorPlatform.TIKTOK if tiktok else CollectorPlatform.DOUYIN
        )
        target_key = (
            getattr(extract, "detail_url", "")
            or getattr(extract, "detail_id", "")
        )

        async def operation(worker, credentials, selected_identity_id):
            root, params, logger = worker.record.run(worker.parameter)
            response_extract = extract.model_copy(
                update={"identity_id": selected_identity_id or extract.identity_id}
            )
            detail_ids = [extract.detail_id]
            detail_urls = None
            if tiktok and getattr(extract, "detail_url", ""):
                items = await worker._parse_tiktok_detail_targets(
                    extract.detail_url,
                    credentials.proxy or None,
                )
                parsed_ids, parsed_urls = worker._split_tiktok_detail_targets(items)
                if parsed_ids:
                    detail_ids = parsed_ids[:1]
                    detail_urls = parsed_urls[:1]
                else:
                    detail_urls = [extract.detail_url]
            async with logger(root, console=worker.console, **params) as record:
                data = await worker._handle_detail(
                    detail_ids,
                    tiktok,
                    record,
                    True,
                    extract.source,
                    credentials.cookie or None,
                    credentials.proxy or None,
                    detail_urls=detail_urls,
                )
            if data:
                return self.success_response(response_extract, data[0]), 1, 0
            return self.failed_response(response_extract), 0, 1

        response, identity_id, reason = await self._execute_collector_operation(
            platform=platform,
            target_type="detail",
            target_key=target_key,
            identity_id=extract.identity_id,
            cookie=extract.cookie,
            proxy=extract.proxy,
            operation=operation,
            failure_error_code="detail_collection_failed",
        )
        return self._attach_collector_route(response, identity_id, reason)

    async def handle_account(
        self,
        extract: Account | AccountTiktok,
        tiktok=False,
    ):
        platform = (
            CollectorPlatform.TIKTOK if tiktok else CollectorPlatform.DOUYIN
        )

        async def operation(worker, credentials, selected_identity_id):
            data = await worker.deal_account_detail(
                0,
                extract.sec_user_id,
                tab=extract.tab,
                earliest=extract.earliest,
                latest=extract.latest,
                pages=extract.pages,
                api=True,
                source=extract.source,
                cookie=credentials.cookie or None,
                proxy=credentials.proxy or None,
                tiktok=tiktok,
                cursor=extract.cursor,
                count=extract.count,
            )
            response_extract = extract.model_copy(
                update={"identity_id": selected_identity_id or extract.identity_id}
            )
            if data:
                return self.success_response(response_extract, data), 1, 0
            return self.failed_response(response_extract), 0, 1

        response, identity_id, reason = await self._execute_collector_operation(
            platform=platform,
            target_type="account",
            target_key=extract.sec_user_id,
            identity_id=extract.identity_id,
            cookie=extract.cookie,
            proxy=extract.proxy,
            operation=operation,
            failure_error_code="account_collection_failed",
        )
        return self._attach_collector_route(response, identity_id, reason)

    async def _handle_mix_request(self, extract: Mix | MixTikTok, tiktok=False):
        if tiktok:
            is_mix, target_id = True, extract.mix_id
        else:
            is_mix, target_id = self.generate_mix_params(
                extract.mix_id,
                extract.detail_id,
            )
            if not isinstance(is_mix, bool):
                return DataResponse(
                    message=_("参数错误！"),
                    data=None,
                    params=redact_webui_value(extract.model_dump()),
                )
        platform = (
            CollectorPlatform.TIKTOK if tiktok else CollectorPlatform.DOUYIN
        )

        async def operation(worker, credentials, selected_identity_id):
            data = await worker.deal_mix_detail(
                is_mix,
                target_id,
                api=True,
                source=extract.source,
                cookie=credentials.cookie or None,
                proxy=credentials.proxy or None,
                cursor=extract.cursor,
                count=extract.count,
            )
            response_extract = extract.model_copy(
                update={"identity_id": selected_identity_id or extract.identity_id}
            )
            if data:
                return self.success_response(response_extract, data), 1, 0
            return self.failed_response(response_extract), 0, 1

        response, identity_id, reason = await self._execute_collector_operation(
            platform=platform,
            target_type="mix",
            target_key=f"{'mix' if is_mix else 'detail'}:{target_id}",
            identity_id=extract.identity_id,
            cookie=extract.cookie,
            proxy=extract.proxy,
            operation=operation,
            failure_error_code="mix_collection_failed",
        )
        return self._attach_collector_route(response, identity_id, reason)

    async def _handle_live_request(self, extract: Live | LiveTikTok, tiktok=False):
        platform = (
            CollectorPlatform.TIKTOK if tiktok else CollectorPlatform.DOUYIN
        )
        target_key = extract.room_id if tiktok else extract.web_rid

        async def operation(worker, credentials, selected_identity_id):
            if tiktok:
                raw = await worker.get_live_data_tiktok(
                    extract.room_id,
                    credentials.cookie or None,
                    credentials.proxy or None,
                )
            else:
                raw = await worker.get_live_data(
                    extract.web_rid,
                    cookie=credentials.cookie or None,
                    proxy=credentials.proxy or None,
                )
            data = (
                [raw]
                if extract.source
                else await worker.extractor.run(
                    [raw],
                    None,
                    "live",
                    tiktok=tiktok,
                )
            )
            response_extract = extract.model_copy(
                update={"identity_id": selected_identity_id or extract.identity_id}
            )
            if data:
                return self.success_response(response_extract, data[0]), 1, 0
            return self.failed_response(response_extract), 0, 1

        response, identity_id, reason = await self._execute_collector_operation(
            platform=platform,
            target_type="live",
            target_key=target_key or "unknown-live",
            identity_id=extract.identity_id,
            cookie=extract.cookie,
            proxy=extract.proxy,
            operation=operation,
            failure_error_code="live_collection_failed",
        )
        return self._attach_collector_route(response, identity_id, reason)

    async def _handle_comment_request(self, extract: Comment):
        async def operation(worker, credentials, selected_identity_id):
            data = await worker.comment_handle_single(
                extract.detail_id,
                cookie=credentials.cookie or None,
                proxy=credentials.proxy or None,
                source=extract.source,
                pages=extract.pages,
                cursor=extract.cursor,
                count=extract.count,
                count_reply=extract.count_reply,
                reply=extract.reply,
            )
            response_extract = extract.model_copy(
                update={"identity_id": selected_identity_id or extract.identity_id}
            )
            if data:
                return self.success_response(response_extract, data), 1, 0
            return self.failed_response(response_extract), 0, 1

        response, identity_id, reason = await self._execute_collector_operation(
            platform=CollectorPlatform.DOUYIN,
            target_type="comment",
            target_key=extract.detail_id,
            identity_id=extract.identity_id,
            cookie=extract.cookie,
            proxy=extract.proxy,
            operation=operation,
            failure_error_code="comment_collection_failed",
        )
        return self._attach_collector_route(response, identity_id, reason)

    async def _handle_reply_request(self, extract: Reply):
        async def operation(worker, credentials, selected_identity_id):
            data = await worker.reply_handle(
                extract.detail_id,
                extract.comment_id,
                cookie=credentials.cookie or None,
                proxy=credentials.proxy or None,
                pages=extract.pages,
                cursor=extract.cursor,
                count=extract.count,
                source=extract.source,
            )
            response_extract = extract.model_copy(
                update={"identity_id": selected_identity_id or extract.identity_id}
            )
            if data:
                return self.success_response(response_extract, data), 1, 0
            return self.failed_response(response_extract), 0, 1

        response, identity_id, reason = await self._execute_collector_operation(
            platform=CollectorPlatform.DOUYIN,
            target_type="reply",
            target_key=f"{extract.detail_id}:{extract.comment_id}",
            identity_id=extract.identity_id,
            cookie=extract.cookie,
            proxy=extract.proxy,
            operation=operation,
            failure_error_code="reply_collection_failed",
        )
        return self._attach_collector_route(response, identity_id, reason)

    @staticmethod
    def success_response(
        extract,
        data: dict | list[dict],
        message: str = None,
    ):
        return DataResponse(
            message=message or _("获取数据成功！"),
            data=data,
            params=redact_webui_value(extract.model_dump()),
        )

    @staticmethod
    def failed_response(
        extract,
        message: str = None,
    ):
        return DataResponse(
            message=message or _("获取数据失败！"),
            data=None,
            params=redact_webui_value(extract.model_dump()),
        )

    @staticmethod
    def generate_mix_params(mix_id: str = None, detail_id: str = None):
        if mix_id:
            return True, mix_id
        return (False, detail_id) if detail_id else (None, None)

    @staticmethod
    def check_live_params(
        web_rid: str = None,
        room_id: str = None,
        sec_user_id: str = None,
    ) -> bool:
        return bool(web_rid or room_id and sec_user_id)

    async def handle_live(self, extract: Live | LiveTikTok, tiktok=False):
        """Legacy low-level helper retained for internal compatibility."""

        if tiktok:
            data = await self.get_live_data_tiktok(
                extract.room_id,
                extract.cookie,
                extract.proxy,
            )
        else:
            data = await self.get_live_data(
                extract.web_rid,
                # extract.room_id,
                # extract.sec_user_id,
                cookie=extract.cookie,
                proxy=extract.proxy,
            )
        if extract.source:
            return [data]
        return await self.extractor.run(
            [data],
            None,
            "live",
            tiktok=tiktok,
        )
