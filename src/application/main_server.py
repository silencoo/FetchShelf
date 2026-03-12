from asyncio import Queue, CancelledError, create_task, gather, sleep
from datetime import datetime, timedelta
from hashlib import md5
from json import JSONDecodeError, dumps, loads
from mimetypes import guess_type
from pathlib import Path
from random import choice
from re import sub
from shutil import copy2
from textwrap import dedent
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

from fastapi import (
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Query,
    Body,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from uvicorn import Config, Server

from ..custom import (
    __VERSION__,
    PROJECT_ROOT,
    REPOSITORY,
    SERVER_HOST,
    SERVER_PORT,
    VERSION_BETA,
    is_valid_token,
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
    Settings,
    ShortUrl,
    UrlResponse,
    UserSearch,
    VideoSearch,
)
from ..tools import create_client, cookie_dict_to_str
from ..interface import CollectsDetail
from ..translation import _
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
from .main_terminal import TikTok

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


def token_dependency(token: str = Header(None)):
    if not is_valid_token(token):
        raise HTTPException(
            status_code=403,
            detail=_("验证失败！"),
        )


class APIServer(TikTok):
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
    COLLECT_MONITOR_PAGE_COUNT = 20
    COLLECT_MONITOR_MAX_PAGES = 30

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
        self.ui_schedules: dict[str, dict] = {}
        self.ui_schedule_tasks: dict[str, Any] = {}
        self.ui_schedule_counter = 0

    @staticmethod
    def _now_text() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _new_task_id(self) -> str:
        self.ui_task_counter += 1
        return f"T{self.ui_task_counter:06d}"

    def _new_schedule_id(self) -> str:
        self.ui_schedule_counter += 1
        return f"S{self.ui_schedule_counter:06d}"

    def _build_ui_task(
        self,
        endpoint: str,
        payload: dict,
        retry_of: str | None = None,
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
            "retry_of": retry_of,
            "worker": None,
            "error": "",
            "message": "",
            "result": None,
            "_runner": None,
        }
        self.ui_tasks[task["task_id"]] = task
        return task

    @staticmethod
    def _public_ui_task(task: dict) -> dict:
        return {
            key: value
            for key, value in task.items()
            if not key.startswith("_")
        }

    @staticmethod
    def _ui_task_sort_key(item: dict) -> int:
        task_id = str(item.get("task_id", "")).lstrip("T")
        try:
            return int(task_id)
        except ValueError:
            return 0

    def _enqueue_ui_task(
        self,
        endpoint: str,
        payload: dict,
        retry_of: str | None = None,
    ) -> dict:
        task = self._build_ui_task(endpoint, payload, retry_of=retry_of)
        self.ui_task_queue.put_nowait(task["task_id"])
        return task

    async def _start_ui_task_workers(self, workers: int = 2) -> None:
        if self.ui_task_workers:
            return
        for i in range(max(1, workers)):
            self.ui_task_workers.append(create_task(self._ui_task_worker(i + 1)))

    async def _stop_ui_task_workers(self) -> None:
        if not self.ui_task_workers:
            return
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
        task["updated_at"] = self._now_text()
        runner = create_task(
            self._execute_ui_endpoint(
                task["endpoint"],
                task["payload"],
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
            task["status"] = "failed" if self._is_failed_response(result) else "success"
        except CancelledError:
            task["status"] = "canceled"
            task["error"] = "Task canceled"
            task["message"] = _("任务已取消")
        except ValidationError as error:
            task["status"] = "failed"
            task["error"] = str(error)
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
                        task["payload"],
                    )
                    retry_result = self._serialize_response(retry_response)
                    task["result"] = retry_result
                    task["message"] = (
                        retry_result.get("message", "")
                        if isinstance(retry_result, dict)
                        else ""
                    )
                    task["status"] = (
                        "failed" if self._is_failed_response(retry_result) else "success"
                    )
                    return
                except Exception as retry_error:
                    message = str(retry_error)
            task["status"] = "failed"
            task["error"] = message
            task["message"] = _("任务执行失败！")
        finally:
            task["finished_at"] = self._now_text()
            task["updated_at"] = self._now_text()
            task["_runner"] = None
            schedule_url = self._normalize_string(task.get("schedule_uptime_kuma_url"))
            if schedule_url:
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

    async def _execute_ui_endpoint(self, endpoint: str, payload: dict):
        if endpoint == "/douyin/detail":
            return await self.handle_detail(Detail(**payload), False)
        if endpoint == "/douyin/account":
            return await self.handle_account(Account(**payload), False)
        if endpoint == "/douyin/mix":
            extract = Mix(**payload)
            is_mix, id_ = self.generate_mix_params(
                extract.mix_id,
                extract.detail_id,
            )
            if not isinstance(is_mix, bool):
                return DataResponse(
                    message=_("参数错误！"),
                    data=None,
                    params=extract.model_dump(),
                )
            if data := await self.deal_mix_detail(
                is_mix,
                id_,
                api=True,
                source=extract.source,
                cookie=extract.cookie,
                proxy=extract.proxy,
                cursor=extract.cursor,
                count=extract.count,
            ):
                return self.success_response(extract, data)
            return self.failed_response(extract)
        if endpoint == "/douyin/live":
            extract = Live(**payload)
            if data := await self.handle_live(extract, False):
                return self.success_response(extract, data[0])
            return self.failed_response(extract)
        if endpoint == "/douyin/comment":
            extract = Comment(**payload)
            if data := await self.comment_handle_single(
                extract.detail_id,
                cookie=extract.cookie,
                proxy=extract.proxy,
                source=extract.source,
                pages=extract.pages,
                cursor=extract.cursor,
                count=extract.count,
                count_reply=extract.count_reply,
                reply=extract.reply,
            ):
                return self.success_response(extract, data)
            return self.failed_response(extract)
        if endpoint == "/tiktok/detail":
            return await self.handle_detail(DetailTikTok(**payload), True)
        if endpoint == "/tiktok/account":
            return await self.handle_account(AccountTiktok(**payload), True)
        if endpoint == "/tiktok/mix":
            extract = MixTikTok(**payload)
            if data := await self.deal_mix_detail(
                True,
                extract.mix_id,
                api=True,
                source=extract.source,
                cookie=extract.cookie,
                proxy=extract.proxy,
                cursor=extract.cursor,
                count=extract.count,
            ):
                return self.success_response(extract, data)
            return self.failed_response(extract)
        if endpoint == "/tiktok/live":
            extract = LiveTikTok(**payload)
            if data := await self.handle_live(extract, True):
                return self.success_response(extract, data[0])
            return self.failed_response(extract)
        if endpoint == "/workflow/douyin/account_batch":
            return await self._run_ui_account_batch(payload, False)
        if endpoint == "/workflow/tiktok/account_batch":
            return await self._run_ui_account_batch(payload, True)
        if endpoint == "/workflow/douyin/detail_links":
            return await self._run_ui_detail_links(payload, False)
        if endpoint == "/workflow/tiktok/detail_links":
            return await self._run_ui_detail_links(payload, True)
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

    def _collect_scope_stats(self, current: Path) -> dict[str, Any]:
        folders = 0
        files = 0
        images = 0
        videos = 0
        total_size = 0
        for path in current.rglob("*"):
            try:
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
                total_size += path.stat().st_size
            except OSError:
                continue
        return {
            "folders": folders,
            "files": files,
            "images": images,
            "videos": videos,
            "size": total_size,
            "size_human": self._human_size(total_size),
        }

    @staticmethod
    def _supported_ui_task_endpoints() -> set[str]:
        return {
            "/douyin/detail",
            "/douyin/account",
            "/douyin/mix",
            "/douyin/live",
            "/douyin/comment",
            "/tiktok/detail",
            "/tiktok/account",
            "/tiktok/mix",
            "/tiktok/live",
            "/workflow/douyin/account_batch",
            "/workflow/tiktok/account_batch",
            "/workflow/douyin/detail_links",
            "/workflow/tiktok/detail_links",
        }

    @staticmethod
    def _validate_ui_task_payload(endpoint: str, payload: dict) -> None:
        validators = {
            "/douyin/detail": Detail,
            "/douyin/account": Account,
            "/douyin/mix": Mix,
            "/douyin/live": Live,
            "/douyin/comment": Comment,
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

    @staticmethod
    def _normalize_string(value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip()

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

        status = "up"
        if task_status == "failed":
            status = "down"
        if isinstance(failed, int) and failed > 0:
            status = "down"
        if isinstance(queued, int) and queued == 0:
            status = "down"

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
            enable = item.get("enable", True)
            if not isinstance(enable, bool):
                enable = bool(enable)
            auto_update_earliest = item.get("auto_update_earliest", False)
            if not isinstance(auto_update_earliest, bool):
                auto_update_earliest = bool(auto_update_earliest)
            results.append(
                {
                    "mark": APIServer._normalize_string(item.get("mark")),
                    "url": APIServer._normalize_string(item.get("url")),
                    "tab": APIServer._normalize_string(item.get("tab")) or "post",
                    "earliest": APIServer._normalize_string(item.get("earliest")),
                    "latest": APIServer._normalize_string(item.get("latest")),
                    "enable": enable,
                    "auto_update_earliest": auto_update_earliest,
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
        ):
            value = payload.get(key)
            if value is not None and not isinstance(value, str):
                raise ValueError(f"{key} must be string or null.")

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
                    "enable": bool(item.get("enable", False)),
                    "auto_update_earliest": bool(
                        item.get("auto_update_earliest", False)
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

    def _match_account_board_dir(
        self,
        mark: str,
        url: str,
        candidates: list[Path],
    ) -> Path | None:
        if not candidates:
            return None
        mark_tokens = self._account_match_tokens(mark)
        url_tokens: list[str] = []
        for token in self._extract_account_tokens(url):
            url_tokens.extend(self._account_match_tokens(token))
        best_dir = None
        best_score = 0
        for folder in candidates:
            name = folder.name.lower()
            cleaned_name = self.parameter.CLEANER.filter_name(name, "").lower()
            normalized_name = self._normalize_match_token(name)
            score = 0
            for mark_token in mark_tokens:
                if not mark_token:
                    continue
                if (
                    f"_{mark_token}_" in name
                    or f"_{mark_token}_" in cleaned_name
                    or mark_token in name
                    or mark_token in cleaned_name
                    or (
                        self._normalize_match_token(mark_token)
                        and self._normalize_match_token(mark_token) in normalized_name
                    )
                ):
                    score += 120
                    break
            for token in url_tokens:
                if not token:
                    continue
                if (
                    token in name
                    or token in cleaned_name
                    or (
                        self._normalize_match_token(token)
                        and self._normalize_match_token(token) in normalized_name
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
        cache[key] = (images, videos)
        return images, videos

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
    ) -> dict:
        normalized_platform = self._normalize_board_platform(platform)
        rows = self._active_account_rows(normalized_platform)
        total = len(rows)
        size = self._normalize_board_page_size(page_size)
        pages = max(1, (total + size - 1) // size)
        current = min(self._normalize_board_page(page), pages)
        start = (current - 1) * size
        end = start + size
        page_rows = rows[start:end]

        root = self._scope_root("download").expanduser().resolve()
        candidates = self._account_board_dirs(root)
        pins = self._load_account_board_pins()
        avatars = self._load_account_board_avatars()
        media_cache: dict[str, tuple[list[str], list[str]]] = {}
        items = []
        for offset, row in enumerate(page_rows, start=start + 1):
            folder = self._match_account_board_dir(
                mark=row.get("mark", ""),
                url=row.get("url", ""),
                candidates=candidates,
            )
            pin_key = self._account_pin_key(normalized_platform, row.get("url", ""))
            media = self._pick_account_board_media(
                root=root,
                folder=folder,
                cache=media_cache,
                pinned_path=pins.get(pin_key, ""),
                use_pinned=True,
            )
            avatar_path = self._coerce_project_image_relpath(avatars.get(pin_key, ""))
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
                    "media_path": media.get("path", ""),
                    "media_kind": media.get("kind", ""),
                    "pinned": bool(media.get("pinned", False)),
                    "avatar_path": avatar_path,
                    "avatar_scope": "project" if avatar_path else "",
                }
            )

        return {
            "platform": normalized_platform,
            "page": current,
            "page_size": size,
            "pages": pages,
            "total": total,
            "items": items,
        }

    def _settings_backup_dir(self) -> Path:
        backup_dir = self.parameter.settings.path.parent.joinpath("backups")
        backup_dir.mkdir(exist_ok=True)
        return backup_dir

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
        for key in ("cookie", "proxy"):
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
        for key in ("cookie", "proxy", "bark_url"):
            value = payload.get(key)
            if value is not None and not isinstance(value, str):
                raise ValueError(f"{key} must be string or null.")

    def _schedule_public(self, schedule: dict) -> dict:
        return {
            key: value
            for key, value in schedule.items()
            if key not in {"_runner"}
        }

    def _normalize_collect_monitor_payload(self, payload: dict) -> dict:
        now = self._now_text()
        collect_id = self._normalize_string(payload.get("collect_id"))
        interval_minutes = self._normalize_collect_interval(
            payload.get("interval_minutes"),
            default=30,
        )
        limit = self._normalize_collect_limit(payload.get("limit"), default=10)
        enabled = bool(payload.get("enabled", True))
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
            "account_enable": bool(payload.get("account_enable", True)),
            "immediate_crawl": bool(payload.get("immediate_crawl", False)),
            "default_tab": self._normalize_collect_tab(payload.get("default_tab")),
            "default_earliest": self._normalize_string(payload.get("default_earliest")),
            "default_latest": self._normalize_string(payload.get("default_latest")),
            "default_auto_update_earliest": bool(
                payload.get("default_auto_update_earliest", False)
            ),
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
        use_settings = bool(payload.get("use_settings", True))
        items = (
            self._normalize_account_items(payload.get("items", []))
            if not use_settings
            else []
        )
        now = self._now_text()
        normalized = {
            "schedule_type": self.ACCOUNT_BATCH_SCHEDULE,
            "schedule_id": self._normalize_string(payload.get("schedule_id")),
            "name": self._normalize_string(payload.get("name"))
            or f"每日下载-{platform}",
            "platform": platform,
            "hour": hour,
            "minute": minute,
            "enabled": bool(payload.get("enabled", True)),
            "use_settings": use_settings,
            "items": items,
            "cookie": self._normalize_string(payload.get("cookie")),
            "proxy": self._normalize_string(payload.get("proxy")),
            "uptime_kuma_url": self._normalize_string(payload.get("uptime_kuma_url")),
            "created_at": self._normalize_string(payload.get("created_at")) or now,
            "updated_at": now,
            "last_run_at": self._normalize_string(payload.get("last_run_at")),
            "next_run_at": self._normalize_string(payload.get("next_run_at")),
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
            "cookie": schedule.get("cookie", ""),
            "proxy": schedule.get("proxy", ""),
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
    ) -> list[dict]:
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

        for _ in range(max_pages):
            collector = CollectsDetail(
                self.parameter,
                cookie=cookie,
                proxy=proxy,
                collects_id=collect_id,
                pages=1,
                cursor=cursor,
                count=page_count,
            )
            page_items = await collector.run(single_page=True)
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
            ):
                break
            cursor = next_cursor

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
        cookie = self._resolve_runtime_douyin_cookie(schedule.get("cookie", ""))
        if not cookie:
            return {
                "ok": False,
                "error": _("未配置抖音 Cookie，无法访问收藏夹接口"),
            }
        proxy = self._normalize_string(schedule.get("proxy")) or None
        count = self._normalize_collect_limit(schedule.get("limit"), default=10)
        aweme_items = await self._collect_monitor_fetch_aweme_items(
            collect_id=collect_id,
            cookie=cookie,
            proxy=proxy,
            limit=count,
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
                    "tab": self._normalize_collect_tab(schedule.get("default_tab")),
                    "earliest": self._normalize_string(schedule.get("default_earliest")),
                    "latest": self._normalize_string(schedule.get("default_latest")),
                    "enable": bool(schedule.get("account_enable", True)),
                    "auto_update_earliest": bool(
                        schedule.get("default_auto_update_earliest", False)
                    ),
                }
            )

        if new_rows:
            # Keep monitor-added accounts at top, same as manual "新增一行" behavior.
            merged_rows = [*new_rows, *existing_rows]
            self._set_account_rows(False, merged_rows)
            self.parameter.settings.update(self.parameter.get_settings_data())

        immediate_result: dict[str, Any] = {}
        if new_rows and bool(schedule.get("immediate_crawl", False)):
            batch = await self._run_ui_account_batch(
                payload={
                    "use_settings": False,
                    "items": new_rows,
                    "cookie": self._normalize_string(schedule.get("cookie")),
                    "proxy": self._normalize_string(schedule.get("proxy")),
                },
                tiktok=False,
            )
            immediate_result = {
                "message": batch.message,
                "data": batch.data,
            }

        summary = {
            "ok": True,
            "collect_id": collect_id,
            "fetched_aweme": len(aweme_items),
            "sec_uid_count": len(sec_uids),
            "added_accounts": len(new_rows),
            "duplicate_accounts": duplicate_accounts,
            "immediate_crawl": bool(schedule.get("immediate_crawl", False)),
            "immediate_result": immediate_result,
        }
        self.logger.info(
            _(
                "收藏夹监控完成: collect_id={collect} 作品={works} sec_uid={sec} 新增账号={added} 去重={dup}"
            ).format(
                collect=collect_id,
                works=summary["fetched_aweme"],
                sec=summary["sec_uid_count"],
                added=summary["added_accounts"],
                dup=summary["duplicate_accounts"],
            )
        )
        return summary

    def _start_single_schedule_runner(self, schedule_id: str) -> None:
        if schedule_id in self.ui_schedule_tasks:
            return
        if schedule_id not in self.ui_schedules:
            return
        self.ui_schedule_tasks[schedule_id] = create_task(
            self._ui_schedule_runner(schedule_id),
        )

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
                    result = {
                        "ok": False,
                        "error": str(error),
                    }
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
                endpoint, payload = self._schedule_task_payload(schedule)
                task = self._enqueue_ui_task(
                    endpoint=endpoint,
                    payload=loads(dumps(payload, ensure_ascii=False)),
                )
                self._attach_schedule_task_meta(task, schedule)
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
                self._schedule_public(item) for item in self.ui_schedules.values()
            ]
            self.parameter.settings.update(self.parameter.get_settings_data())
        self.ui_schedule_tasks.pop(schedule_id, None)

    def _persist_ui_schedules(self) -> None:
        self.parameter.ui_schedules = [
            self._schedule_public(item)
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

    async def _run_ui_account_batch(
        self,
        payload: dict,
        tiktok: bool,
    ) -> DataResponse:
        use_settings = payload.get("use_settings", True)
        cookie = self._normalize_string(payload.get("cookie")) or None
        proxy = self._normalize_string(payload.get("proxy")) or None
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

        if not queued_items:
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

        success = 0
        failed = 0
        failures = []
        auto_filled_mark = 0
        auto_updated_earliest = 0
        earliest_days = self._normalize_earliest_update_days(
            getattr(self.parameter, "earliest_update_days", 0)
        )
        for index, item in enumerate(queued_items, start=1):
            if not (sec_user_id := await self.check_sec_user_id(item["url"], tiktok)):
                failed += 1
                failures.append(
                    {
                        "index": index,
                        "url": item["url"],
                        "reason": _("提取 sec_user_id 失败"),
                    }
                )
                continue
            result = await self.deal_account_detail(
                index,
                sec_user_id=sec_user_id,
                mark=item["mark"],
                tab=item["tab"],
                earliest=item["earliest"],
                latest=item["latest"],
                pages=item["pages"],
                api=False,
                source=False,
                cookie=cookie,
                proxy=proxy,
                tiktok=tiktok,
                return_context=True,
            )
            if result:
                success += 1
                row_index = item.get("_settings_index")
                if isinstance(row_index, int) and 0 <= row_index < len(settings_rows):
                    if (
                        getattr(self.parameter, "auto_backfill_mark", True)
                        and self._apply_missing_mark(
                            settings_rows[row_index],
                            result.get("mark", ""),
                        )
                    ):
                        auto_filled_mark += 1
                        self._persist_settings_on_mark_backfill(tiktok)
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
                continue
            failed += 1
            failures.append(
                {
                    "index": index,
                    "url": item["url"],
                    "reason": _("账号作品下载失败"),
                }
            )
        skipped = max(0, len(items) - len(queued_items))
        if success == 0:
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
        return DataResponse(
            message=message,
            data={
                "platform": platform,
                "source": "settings" if use_settings else "editor",
                "total": len(items),
                "queued": len(queued_items),
                "success": success,
                "failed": failed,
                "skipped": skipped,
                "mark_backfilled": auto_filled_mark,
                "earliest_updated": auto_updated_earliest,
                "failures": failures,
            },
            params=payload,
        )

    async def _run_ui_detail_links(
        self,
        payload: dict,
        tiktok: bool,
    ) -> DataResponse:
        platform = "tiktok" if tiktok else "douyin"
        cookie = self._normalize_string(payload.get("cookie")) or None
        proxy = self._normalize_string(payload.get("proxy")) or None
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
                params=payload,
            )

        parser = self.links_tiktok if tiktok else self.links
        invalid_links = []
        parsed_ids = []
        for text in links:
            if ids := await parser.run(text):
                parsed_ids.extend(ids)
            else:
                invalid_links.append(text)
        unique_ids = []
        seen = set()
        for item in parsed_ids:
            if item in seen:
                continue
            seen.add(item)
            unique_ids.append(item)
        if not unique_ids:
            return DataResponse(
                message=_("链接解析失败！"),
                data={
                    "platform": platform,
                    "input_links": len(links),
                    "parsed_ids": 0,
                    "downloaded": 0,
                    "invalid_links": invalid_links,
                    "preview": "",
                },
                params=payload,
            )

        root, params, logger = self.record.run(self.parameter)
        async with logger(root, console=self.console, **params) as record:
            data = await self._handle_detail(
                unique_ids,
                tiktok,
                record,
                api=True,
                source=False,
                cookie=cookie,
                proxy=proxy,
            )
        if not data:
            return DataResponse(
                message=_("作品下载失败！"),
                data={
                    "platform": platform,
                    "input_links": len(links),
                    "parsed_ids": len(unique_ids),
                    "downloaded": 0,
                    "invalid_links": invalid_links,
                    "preview": "",
                },
                params=payload,
            )
        await self.downloader.run(data, "detail", tiktok=tiktok)
        message = (
            _("链接下载任务完成，部分链接未成功解析。")
            if invalid_links
            else _("链接下载任务完成！")
        )
        return DataResponse(
            message=message,
            data={
                "platform": platform,
                "input_links": len(links),
                "parsed_ids": len(unique_ids),
                "downloaded": len(data),
                "invalid_links": invalid_links,
                "preview": self._get_preview_image(data[0]) if data else "",
            },
            params=payload,
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
            sec_user_id = await self.check_sec_user_id(url, tiktok)
            if not sec_user_id:
                reason = _("链接无法提取账号 ID")
                result = {
                    "index": index,
                    "url": url,
                    "exists": False,
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
            info = await self.get_user_info_data(
                tiktok=tiktok,
                cookie=cookie,
                proxy=proxy,
                sec_user_id=sec_user_id,
            )
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
            title="DouK-Downloader",
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
        await self._start_ui_task_workers()
        await self._start_ui_schedules()
        try:
            await server.serve()
        finally:
            await self._stop_ui_task_workers()
            await self._stop_ui_schedules()

    def setup_routes(self):
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
            return FileResponse(index_file)

        @self.server.get(
            "/ui/api/files",
            summary="Web UI 文件浏览",
            description="返回目录列表，供 Web UI 文件浏览卡片使用",
            tags=[_("项目")],
        )
        async def webui_files(
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
                (serialize_entry(root, item) for item in current.iterdir()),
                key=lambda item: (not item["is_dir"], item["name"].lower()),
            )
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
                "entries": entries,
                "count": len(entries),
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
                **self._collect_scope_stats(current_path),
            }

        @self.server.get(
            "/ui/api/settings/raw",
            summary="Web UI 原始 settings.json",
            description="返回 settings.json 原始文本，供 Web UI 编辑器使用",
            tags=[_("配置")],
        )
        async def webui_settings_raw(
            token: str = Depends(token_dependency),
        ):
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
                "text": text,
                "updated_at": updated_at,
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
                "settings": self.parameter.get_settings_data(),
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
            token: str = Depends(token_dependency),
        ):
            return self._build_account_board_page(
                platform=platform,
                page=page,
                page_size=page_size,
            )

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
            items = self._fetch_logs(
                after_id=after_id,
                limit=self._normalize_limit(limit),
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
            except (ValidationError, ValueError, TypeError) as error:
                raise HTTPException(
                    status_code=400,
                    detail=f"Payload validation failed: {error}",
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
                "running": sum(1 for i in self.ui_tasks.values() if i["status"] in {"running", "canceling"}),
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
                return {"task": self._public_ui_task(task)}
            runner = task.get("_runner")
            if runner and not runner.done():
                task["status"] = "canceling"
                task["message"] = _("正在取消任务…")
                task["updated_at"] = self._now_text()
                runner.cancel()
            else:
                task["status"] = "canceled"
                task["message"] = _("任务已取消")
                task["finished_at"] = self._now_text()
                task["updated_at"] = self._now_text()
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
            )
            return {"task": self._public_ui_task(new_task)}

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
            endpoint, payload = self._schedule_task_payload(schedule)
            task = self._enqueue_ui_task(
                endpoint=endpoint,
                payload=loads(dumps(payload, ensure_ascii=False)),
            )
            self._attach_schedule_task_meta(task, schedule)
            schedule["last_run_at"] = self._now_text()
            schedule["updated_at"] = self._now_text()
            schedule["next_run_at"] = self._next_run_text(
                schedule["hour"],
                schedule["minute"],
            )
            self._persist_ui_schedules()
            return {
                "schedule": self._schedule_public(schedule),
                "task": self._public_ui_task(task),
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
                result = {
                    "ok": False,
                    "error": str(error),
                }
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
                "result": result,
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
            token = websocket.headers.get("token") or websocket.query_params.get(
                "token"
            )
            if not is_valid_token(token):
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
                    items = self._fetch_logs(
                        after_id=cursor,
                        limit=500,
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
        async def handle_test(token: str = Depends(token_dependency)):
            return DataResponse(
                message=_("验证成功！"),
                data=None,
                params=None,
            )

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
            await self.parameter.set_settings_data(extract.model_dump())
            self._sync_runtime_http_clients()
            return Settings(**self.parameter.get_settings_data())

        @self.server.get(
            "/settings",
            summary=_("获取项目全局配置"),
            description=_("返回项目全部配置参数"),
            tags=[_("配置")],
            response_model=Settings,
        )
        async def get_settings(token: str = Depends(token_dependency)):
            return Settings(**self.parameter.get_settings_data())

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
                    params=extract.model_dump(),
                )
            return UrlResponse(
                message=_("请求链接失败！"),
                url=None,
                params=extract.model_dump(),
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
            is_mix, id_ = self.generate_mix_params(
                extract.mix_id,
                extract.detail_id,
            )
            if not isinstance(is_mix, bool):
                return DataResponse(
                    message=_("参数错误！"),
                    data=None,
                    params=extract.model_dump(),
                )
            if data := await self.deal_mix_detail(
                is_mix,
                id_,
                api=True,
                source=extract.source,
                cookie=extract.cookie,
                proxy=extract.proxy,
                cursor=extract.cursor,
                count=extract.count,
            ):
                return self.success_response(extract, data)
            return self.failed_response(extract)

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
            if data := await self.handle_live(
                extract,
            ):
                return self.success_response(extract, data[0])
            return self.failed_response(extract)

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
            if data := await self.comment_handle_single(
                extract.detail_id,
                cookie=extract.cookie,
                proxy=extract.proxy,
                source=extract.source,
                pages=extract.pages,
                cursor=extract.cursor,
                count=extract.count,
                count_reply=extract.count_reply,
                reply=extract.reply,
            ):
                return self.success_response(extract, data)
            return self.failed_response(extract)

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
            if data := await self.reply_handle(
                extract.detail_id,
                extract.comment_id,
                cookie=extract.cookie,
                proxy=extract.proxy,
                pages=extract.pages,
                cursor=extract.cursor,
                count=extract.count,
                source=extract.source,
            ):
                return self.success_response(extract, data)
            return self.failed_response(extract)

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
                    params=extract.model_dump(),
                )
            return UrlResponse(
                message=_("请求链接失败！"),
                url=None,
                params=extract.model_dump(),
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
                - **detail_id**: TikTok 作品 ID；必需参数
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
            if data := await self.deal_mix_detail(
                True,
                extract.mix_id,
                api=True,
                source=extract.source,
                cookie=extract.cookie,
                proxy=extract.proxy,
                cursor=extract.cursor,
                count=extract.count,
            ):
                return self.success_response(extract, data)
            return self.failed_response(extract)

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
            if data := await self.handle_live(
                extract,
                True,
            ):
                return self.success_response(extract, data[0])
            return self.failed_response(extract)

    async def handle_search(self, extract):
        if isinstance(
            data := await self.deal_search_data(
                extract,
                extract.source,
            ),
            list,
        ):
            return self.success_response(
                extract,
                *(data, None) if any(data) else (None, _("搜索结果为空！")),
            )
        return self.failed_response(extract)

    async def handle_detail(
        self,
        extract: Detail | DetailTikTok,
        tiktok=False,
    ):
        root, params, logger = self.record.run(self.parameter)
        async with logger(root, console=self.console, **params) as record:
            if data := await self._handle_detail(
                [extract.detail_id],
                tiktok,
                record,
                True,
                extract.source,
                extract.cookie,
                extract.proxy,
            ):
                return self.success_response(extract, data[0])
            return self.failed_response(extract)

    async def handle_account(
        self,
        extract: Account | AccountTiktok,
        tiktok=False,
    ):
        if data := await self.deal_account_detail(
            0,
            extract.sec_user_id,
            tab=extract.tab,
            earliest=extract.earliest,
            latest=extract.latest,
            pages=extract.pages,
            api=True,
            source=extract.source,
            cookie=extract.cookie,
            proxy=extract.proxy,
            tiktok=tiktok,
            cursor=extract.cursor,
            count=extract.count,
        ):
            return self.success_response(extract, data)
        return self.failed_response(extract)

    @staticmethod
    def success_response(
        extract,
        data: dict | list[dict],
        message: str = None,
    ):
        return DataResponse(
            message=message or _("获取数据成功！"),
            data=data,
            params=extract.model_dump(),
        )

    @staticmethod
    def failed_response(
        extract,
        message: str = None,
    ):
        return DataResponse(
            message=message or _("获取数据失败！"),
            data=None,
            params=extract.model_dump(),
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
