from asyncio import Queue, CancelledError, create_task, gather, sleep
from datetime import datetime
from json import JSONDecodeError, dumps, loads
from mimetypes import guess_type
from pathlib import Path
from textwrap import dedent
from typing import TYPE_CHECKING

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
from ..translation import _
from ..webui.files import ScopeType, relative_path, resolve_within_root, serialize_entry
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

    @staticmethod
    def _now_text() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _new_task_id(self) -> str:
        self.ui_task_counter += 1
        return f"T{self.ui_task_counter:06d}"

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
            task["status"] = "failed"
            task["error"] = str(error)
            task["message"] = _("任务执行失败！")
        finally:
            task["finished_at"] = self._now_text()
            task["updated_at"] = self._now_text()
            task["_runner"] = None

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
        try:
            await server.serve()
        finally:
            await self._stop_ui_task_workers()

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
            except Exception as error:
                raise HTTPException(
                    status_code=400,
                    detail=f"Apply settings failed: {error}",
                )
            return {
                "message": _("保存配置成功！"),
                "settings": self.parameter.get_settings_data(),
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
            except ValidationError as error:
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
            summary=_("访问项目 GitHub 仓库"),
            description=_("重定向至项目 GitHub 仓库主页"),
            tags=[_("项目")],
        )
        async def index():
            return RedirectResponse(url=REPOSITORY)

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
