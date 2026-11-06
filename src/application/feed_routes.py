"""Immersive feed API: posts, profiles and personal marks over the local library."""

from __future__ import annotations

from asyncio import Semaphore, sleep, to_thread
from collections import OrderedDict
from json import loads
import os
from pathlib import Path
from subprocess import SubprocessError
from time import monotonic
from typing import TYPE_CHECKING, Literal

from fastapi import Depends, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from ..collector import CollectorPlatform
from ..interface import Comment as CommentFetcher, Reply as ReplyFetcher
from ..webui.feed_index import (
    AccountSource,
    FeedIndex,
    FeedWorker,
    decode_cursor,
    encode_cursor,
    media_kind,
    parse_media_name,
    uid_from_folder,
)
from ..webui.feed_state import FeedState
from ..webui.files import IMAGE_SUFFIXES, VIDEO_SUFFIXES, resolve_within_root
from ..webui.video_preview import image_preview, video_preview

if TYPE_CHECKING:
    from .main_server import APIServer

__all__ = ["FeedService", "register_feed_routes"]

_POST_SOURCES = frozenset(
    {"foryou", "latest", "following", "account", "likes", "saves", "popular", "search", "tag", "music"}
)
_COMMENT_CACHE_SECONDS = 900.0
_COMMENT_CACHE_SIZE = 64
_TAG_CACHE_SECONDS = 1800.0
_THUMB_CACHE = "private, max-age=2592000"


class FeedMark(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["like", "save", "follow", "hide"]
    target: str = Field(min_length=1, max_length=2300)
    on: bool


def _http_url(value: object) -> str:
    text = str(value or "").strip()
    return text if text.startswith(("https://", "http://")) else ""


def _first_url(node: object) -> str:
    urls = node.get("url_list") if isinstance(node, dict) else None
    return _http_url(urls[0]) if isinstance(urls, list) and urls else ""


def _delay_seconds(value: object) -> float:
    try:
        return max(0.0, float(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def _integer(value: object) -> int:
    try:
        return max(0, int(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def comment_payload(raw: dict) -> dict:
    """Keep only what the sheet renders; remote objects carry session details."""
    user = raw.get("user") if isinstance(raw.get("user"), dict) else {}
    images = raw.get("image_list")
    image = images[0].get("origin_url") if isinstance(images, list) and images and isinstance(images[0], dict) else None
    sticker = raw.get("sticker") if isinstance(raw.get("sticker"), dict) else {}
    return {
        "id": str(raw.get("cid") or ""),
        "text": str(raw.get("text") or ""),
        "likes": _integer(raw.get("digg_count")),
        "created_ts": _integer(raw.get("create_time")),
        "ip": str(raw.get("ip_label") or ""),
        "replies": _integer(raw.get("reply_comment_total")),
        "author": str(user.get("nickname") or ""),
        "avatar": _first_url(user.get("avatar_thumb")),
        "image": _first_url(image),
        "sticker": _first_url(sticker.get("static_url")),
    }


class FeedService:
    def __init__(self, server: "APIServer"):
        self.server = server
        settings_dir = Path(server.parameter.settings.path).parent
        self.index = FeedIndex(settings_dir / "ui_feed_index.sqlite3")
        self.state = FeedState(settings_dir / "ui_feed_state.sqlite3")
        self.worker = FeedWorker(
            self.index,
            self.account_sources,
            self.media_root,
            self.detail_database,
            log=self._log,
        )
        self._covers_signature: tuple | None = None
        self._covers: tuple[dict, dict] = ({}, {})
        self._tags: tuple[float, list[dict]] = (0.0, [])
        self.comment_slot = Semaphore(1)
        self.comment_cache: OrderedDict[tuple, tuple[float, dict]] = OrderedDict()
        self.last_comment_fetch = 0.0

    def _log(self, message: str) -> None:
        logger = getattr(self.server, "logger", None)
        if logger:
            logger.warning(message)

    def close(self) -> None:
        self.worker.stop()

    def media_root(self) -> Path:
        return self.server._scope_root("download").expanduser().resolve()

    def detail_database(self) -> Path:
        return self.media_root().joinpath("Data", "DetailData.db")

    def account_sources(self) -> list[AccountSource]:
        """Reuse the board's account-to-folder matching so both views agree."""
        server = self.server
        root = self.media_root()
        folder_index = server._board_folder_index(root)
        owned: set[Path] = set()
        sources = []
        for platform in ("douyin", "tiktok"):
            for row in server._active_account_rows(platform):
                url = server._normalize_string(row.get("url"))
                folder = server._indexed_account_folder(row, folder_index)
                # A fuzzy match can point two rows at one folder; one row owns it.
                if folder in owned:
                    folder = None
                elif folder is not None:
                    owned.add(folder)
                sources.append(
                    AccountSource(
                        key=server._account_pin_key(platform, url),
                        platform=platform,
                        url=url,
                        mark=server._normalize_string(row.get("mark")),
                        folder=folder,
                    )
                )
        return sources

    # ----------------------------------------------------------- serialization

    def _cover_sources(self) -> tuple[dict, dict]:
        server = self.server
        signature = []
        for path in (server._account_board_pin_file(), server._account_board_avatar_file()):
            try:
                stat = path.stat()
                signature.append((stat.st_mtime_ns, stat.st_size))
            except OSError:
                signature.append(None)
        key = tuple(signature)
        if key != self._covers_signature:
            try:
                pins = server._load_account_board_pins()
            except (OSError, ValueError):
                pins = {}
            self._covers = (pins, server._load_account_board_avatars())
            self._covers_signature = key
        return self._covers

    def avatar_for(self, account_key: str, cover_path: str) -> dict | None:
        pins, avatars = self._cover_sources()
        if avatars.get(account_key):
            return {"scope": "project", "path": avatars[account_key], "second": 0}
        pin = pins.get(account_key)
        if pin and pin.get("path"):
            return {"scope": "download", "path": pin["path"], "second": pin.get("second", 0)}
        if cover_path:
            return {"scope": "download", "path": cover_path, "second": 0}
        return None

    def pinned_post_key(self, account: dict) -> str:
        pins, _ = self._cover_sources()
        pin = pins.get(account["account_key"])
        if not pin or not pin.get("path"):
            return ""
        parsed = parse_media_name(os.path.basename(pin["path"]), account.get("name", ""))
        if not parsed.time_key:
            return ""
        folder = os.path.basename(os.path.dirname(pin["path"]))
        uid = uid_from_folder(folder) if folder else account.get("uid", "")
        for code in ("v", "i", "l"):
            key = f"{uid}:{parsed.time_key}:{code}"
            if self.index.post(key):
                return key
        return ""

    @staticmethod
    def _share_url(row: dict, work_id: str) -> str:
        url = _http_url(row.get("share_url"))
        if url:
            return url
        if work_id and row.get("platform") == "douyin":
            path = "video" if row.get("kind") == "video" else "note"
            return f"https://www.douyin.com/{path}/{work_id}"
        return ""

    def posts_payload(self, rows: list[dict], *, pinned: str = "") -> list[dict]:
        keys = [row["post_key"] for row in rows]
        liked = self.state.marked("like", keys)
        saved = self.state.marked("save", keys)
        followed = self.state.marked("follow", sorted({row["account_key"] for row in rows}))
        enriching = self.worker.status.phase == "enriching"
        payload = []
        for row in rows:
            folder = row["folder"]
            media = [
                {"path": f"{folder}/{name}", "kind": media_kind(name)}
                for name in loads(row["files"])
            ]
            work_id = row.get("work_id") or row.get("work_hint") or ""
            music_title = row.get("music_title") or ""
            music_url = _http_url(row.get("music_url"))
            has_counts = row.get("likes") is not None
            payload.append(
                {
                    "key": row["post_key"],
                    "kind": row["kind"],
                    "published_ts": row["published_ts"],
                    "caption": row.get("full_caption") or row["caption"],
                    "tags": str(row.get("tags") or "").split(),
                    "duration": row.get("duration"),
                    "width": row.get("width"),
                    "height": row.get("height"),
                    "stats": (
                        {
                            "likes": row.get("likes"),
                            "comments": row.get("comments"),
                            "saves": row.get("saves"),
                            "shares": row.get("shares"),
                        }
                        if has_counts
                        else None
                    ),
                    "music": (
                        {
                            "title": music_title,
                            "author": row.get("music_author") or "",
                            "url": music_url,
                        }
                        if music_title or music_url
                        else None
                    ),
                    "work_id": work_id,
                    "share_url": self._share_url(row, work_id),
                    "media": media,
                    "cover": f"{folder}/{row['poster']}" if row["poster"] else media[0]["path"],
                    "liked": row["post_key"] in liked,
                    "saved": row["post_key"] in saved,
                    "pinned": bool(pinned) and row["post_key"] == pinned,
                    "meta_pending": enriching and not row.get("work_id"),
                    "author": {
                        "key": row["account_key"],
                        "platform": row["platform"],
                        "url": row["url"],
                        "name": row["name"],
                        "avatar": self.avatar_for(row["account_key"], row.get("cover_path") or ""),
                        "followed": row["account_key"] in followed,
                    },
                }
            )
        return payload

    def account_payload(self, account: dict, *, followed: set[str] | None = None) -> dict:
        key = account["account_key"]
        if followed is None:
            followed = self.state.marked("follow", [key])
        return {
            "key": key,
            "platform": account["platform"],
            "url": account["url"],
            "name": account["name"],
            "nickname": account["nickname"],
            "handle": account["handle"],
            "bio": account["bio"],
            "uid": account["uid"],
            "avatar": self.avatar_for(key, account["cover_path"]),
            "cover": account["cover_path"],
            "followed": key in followed,
            "stats": {
                "posts": account["post_count"],
                "videos": account["video_count"],
                "images": account["image_count"],
                "likes": account["total_likes"],
            },
            "latest_ts": account["latest_ts"],
        }

    # ---------------------------------------------------------------- queries

    def status(self) -> dict:
        status = self.worker.status
        counts = self.index.counts()
        return {
            "phase": status.phase,
            "done": status.done,
            "total": status.total,
            "accounts": counts["accounts"],
            "posts": counts["posts"],
            "metadata_available": status.metadata_available,
            "metadata_done": status.metadata_done,
            "metadata_total": status.metadata_total,
            "last_finished_at": status.last_finished_at,
            "error": status.error,
        }

    def list_posts(
        self,
        *,
        source: str,
        account: str,
        query: str,
        sort: str,
        kind: str,
        cursor: dict,
        limit: int,
    ) -> dict:
        index = self.index
        state = self.state
        hidden = state.targets("hide")
        pinned = ""
        rows: list[dict] = []
        following: dict | None = None
        if source == "foryou":
            rows, following = index.foryou_page(
                limit=limit,
                cursor=cursor,
                favorites=state.affinity_accounts(),
                hidden=hidden,
            )
        elif source == "latest":
            rows, following = index.latest_posts(limit=limit, cursor=cursor, hidden=hidden)
        elif source == "following":
            followed = state.targets("follow")
            if followed:
                rows, following = index.latest_posts(limit=limit, cursor=cursor, only=followed)
        elif source == "account":
            record = index.account(account)
            if record is None:
                raise HTTPException(status_code=404, detail="Account not found.")
            exclude = ""
            if sort == "latest" and kind == "all":
                pinned = exclude = self.pinned_post_key(record)
            rows, following = index.account_posts(
                account, limit=limit, cursor=cursor, sort=sort, kind=kind, exclude=exclude,
            )
            if pinned and not cursor:
                rows = index.posts_by_keys([pinned]) + rows
        elif source in {"likes", "saves"}:
            mark = "like" if source == "likes" else "save"
            offset = max(0, int(cursor.get("o", 0)))
            keys, total = state.page(mark, limit=limit, offset=offset, account_key=account)
            rows = index.posts_by_keys(keys)
            if offset + limit < total:
                following = {"o": offset + limit}
        elif source == "popular":
            rows, following = index.popular_posts(limit=limit, cursor=cursor, hidden=hidden)
        else:
            if query:
                field = {"tag": "tag", "music": "music"}.get(source, "all")
                rows, following = index.search_posts(
                    query, field=field, limit=limit, cursor=cursor, hidden=hidden,
                )
        return {
            "items": self.posts_payload(rows, pinned=pinned),
            "next_cursor": encode_cursor(following) if following else None,
        }

    def list_accounts(
        self, *, query: str, sort: str, scope: str, limit: int, offset: int,
    ) -> dict:
        only = self.state.targets("follow") if scope == "following" else None
        rows, total = self.index.accounts(
            query=query, sort=sort, limit=limit, offset=offset, only=only,
        )
        followed = self.state.marked("follow", [row["account_key"] for row in rows])
        return {
            "items": [self.account_payload(row, followed=followed) for row in rows],
            "total": total,
            "next_offset": offset + limit if offset + limit < total else None,
        }

    def top_tags(self) -> list[dict]:
        stamp, tags = self._tags
        if tags and monotonic() - stamp < _TAG_CACHE_SECONDS:
            return tags
        tags = self.index.top_tags()
        self._tags = (monotonic(), tags)
        return tags

    def me(self) -> dict:
        counts = self.state.counts()
        return {
            "likes": counts["like"],
            "saves": counts["save"],
            "following": counts["follow"],
            "hidden": counts["hide"],
            "index": self.status(),
        }

    def set_mark(self, mark: FeedMark) -> dict:
        account_key = ""
        if mark.kind in {"like", "save"}:
            post = self.index.post(mark.target)
            # Removing stays possible after the media itself has gone.
            if post is None and mark.on:
                raise HTTPException(status_code=404, detail="Post not found.")
            account_key = post["account_key"] if post else ""
        elif mark.on and self.index.account(mark.target) is None:
            raise HTTPException(status_code=404, detail="Account not found.")
        self.state.set_mark(mark.kind, mark.target, mark.on, account_key)
        return {"kind": mark.kind, "target": mark.target, "on": mark.on}

    # --------------------------------------------------------------- comments

    def _cached_comments(self, key: tuple) -> dict | None:
        hit = self.comment_cache.get(key)
        if hit is None:
            return None
        expires, payload = hit
        if monotonic() >= expires:
            self.comment_cache.pop(key, None)
            return None
        self.comment_cache.move_to_end(key)
        return payload

    def _remember_comments(self, key: tuple, payload: dict) -> None:
        self.comment_cache[key] = (monotonic() + _COMMENT_CACHE_SECONDS, payload)
        self.comment_cache.move_to_end(key)
        while len(self.comment_cache) > _COMMENT_CACHE_SIZE:
            self.comment_cache.popitem(last=False)

    async def _fetch_comments(
        self, work_id: str, cursor: int, count: int, reply_to: str,
    ) -> tuple[list, int | None]:
        """One live page and the platform's next cursor, or None when finished."""

        async def operation(worker, credentials, identity_id):
            options = {"detail_id": work_id, "pages": 1, "cursor": cursor, "count": count}
            if reply_to:
                fetcher = ReplyFetcher(
                    worker.parameter,
                    credentials.cookie or None,
                    credentials.proxy or None,
                    comment_id=reply_to,
                    **options,
                )
            else:
                fetcher = CommentFetcher(
                    worker.parameter,
                    credentials.cookie or None,
                    credentials.proxy or None,
                    count_reply=3,
                    **options,
                )
            # The usual post-response sleep paces batch crawls; here it would only
            # hold a finished answer back from the person waiting for it.
            fetcher.request_delay = 0
            data = await fetcher.run()
            answered = bool(data) or fetcher.last_response_payload is not None
            page = (data or [], None if fetcher.finished else fetcher.cursor)
            return page, int(answered), int(not answered)

        page, _, _ = await self.server._execute_collector_operation(
            platform=CollectorPlatform.DOUYIN,
            target_type="reply" if reply_to else "comment",
            target_key=f"{work_id}:{reply_to}" if reply_to else work_id,
            operation=operation,
            failure_error_code="comment_collection_failed",
        )
        return page

    async def comments(self, request: Request, post_key: str, cursor: int, reply_to: str) -> dict:
        post = await to_thread(self.index.post, post_key)
        if post is None:
            raise HTTPException(status_code=404, detail="Post not found.")
        if post["platform"] != "douyin":
            return {"items": [], "next_cursor": None, "unavailable": "暂不支持拉取 TikTok 评论"}
        work_id = post.get("work_id") or post.get("work_hint") or ""
        if not work_id:
            return {"items": [], "next_cursor": None, "unavailable": "这条作品没有可用的作品 ID"}
        cache_key = (work_id, reply_to, cursor)
        cached = self._cached_comments(cache_key)
        if cached is not None:
            return cached
        count = 20
        gap = _delay_seconds(getattr(self.server.parameter, "request_delay", 0))
        try:
            async with self.comment_slot:
                # The configured request delay still protects the identity, as
                # spacing between live fetches instead of a wait after each one.
                remaining = self.last_comment_fetch + gap - monotonic()
                if remaining > 0:
                    await sleep(remaining)
                # A viewer who moved on while queued should not cost a request.
                if await request.is_disconnected():
                    return {"items": [], "next_cursor": None}
                self.last_comment_fetch = monotonic()
                raw, next_cursor = await self._fetch_comments(work_id, cursor, count, reply_to)
        except HTTPException as error:
            # Routing refusals (no eligible identity, cooldown) are expected states.
            if error.status_code in {404, 409}:
                return {"items": [], "next_cursor": None, "unavailable": "当前没有可用的采集身份"}
            raise
        except Exception as error:
            self._log(f"Feed comments unavailable: {type(error).__name__}")
            return {"items": [], "next_cursor": None, "unavailable": "评论暂时无法加载"}
        items = [comment_payload(item) for item in raw if isinstance(item, dict)]
        payload = {"items": items, "next_cursor": next_cursor if items else None}
        if not items and not cursor and not reply_to and post.get("comments"):
            # A non-zero count with an empty response means the request was refused.
            return {**payload, "unavailable": "平台暂未返回评论，请稍后再试"}
        self._remember_comments(cache_key, payload)
        return payload


def register_feed_routes(server: "APIServer", token_dependency) -> None:
    app = server.server
    thumb_slots = Semaphore(3)

    def service() -> FeedService:
        # Created on first use: route-only test harnesses have no settings path.
        existing = getattr(server, "_feed_service", None)
        if existing is None:
            existing = server._feed_service = FeedService(server)
        existing.worker.touch()
        return existing

    @app.get("/ui/feed", include_in_schema=False)
    async def feed_page():
        index_file = server.WEBUI_STATIC_DIR.joinpath("index.html")
        if not index_file.is_file():
            raise HTTPException(status_code=404, detail="Web UI resources not found.")
        return FileResponse(index_file, headers={"Cache-Control": "no-cache"})

    @app.get("/ui/api/feed/status", tags=["沉浸浏览"], summary="沉浸浏览索引状态")
    def feed_status(token: str = Depends(token_dependency)):
        return service().status()

    @app.post("/ui/api/feed/refresh", tags=["沉浸浏览"], summary="重新扫描媒体库")
    def feed_refresh(
        force: bool = Query(False), token: str = Depends(token_dependency),
    ):
        feed = service()
        feed.worker.request_sync(force=force)
        return feed.status()

    @app.get("/ui/api/feed/posts", tags=["沉浸浏览"], summary="作品流")
    def feed_posts(
        source: str = Query("foryou", max_length=20),
        account: str = Query("", max_length=2300),
        q: str = Query("", max_length=120),
        sort: Literal["latest", "oldest", "popular"] = Query("latest"),
        kind: Literal["all", "video", "images"] = Query("all"),
        cursor: str = Query("", max_length=1024),
        limit: int = Query(12, ge=1, le=60),
        token: str = Depends(token_dependency),
    ):
        if source not in _POST_SOURCES:
            raise HTTPException(status_code=400, detail="Unknown feed source.")
        if source == "account" and not account:
            raise HTTPException(status_code=400, detail="account is required.")
        return service().list_posts(
            source=source,
            account=account,
            query=q.strip(),
            sort=sort,
            kind=kind,
            cursor=decode_cursor(cursor),
            limit=limit,
        )

    @app.get("/ui/api/feed/post", tags=["沉浸浏览"], summary="单个作品")
    def feed_post(
        key: str = Query(..., min_length=1, max_length=200),
        token: str = Depends(token_dependency),
    ):
        feed = service()
        row = feed.index.post(key)
        if row is None:
            raise HTTPException(status_code=404, detail="Post not found.")
        if not row.get("work_id"):
            feed.worker.prioritize(row["uid"])
        return feed.posts_payload([row])[0]

    @app.get("/ui/api/feed/account", tags=["沉浸浏览"], summary="账号主页")
    def feed_account(
        key: str = Query(..., min_length=1, max_length=2300),
        token: str = Depends(token_dependency),
    ):
        feed = service()
        try:
            feed.worker.sync_account_now(key)
        except OSError as error:
            feed._log(f"Feed account refresh skipped: {type(error).__name__}")
        account = feed.index.account(key)
        if account is None:
            raise HTTPException(status_code=404, detail="Account not found.")
        feed.worker.prioritize(account["uid"])
        payload = feed.account_payload(account)
        payload["liked"] = feed.state.page("like", limit=1, account_key=key)[1]
        payload["saved"] = feed.state.page("save", limit=1, account_key=key)[1]
        journal = getattr(server, "task_journal", None)
        activity = journal.list_account_activity(account["platform"], [account["url"]]) if journal else []
        if activity:
            payload["last_checked_at"] = activity[0].get("last_checked_at", "")
        return payload

    @app.get("/ui/api/feed/accounts", tags=["沉浸浏览"], summary="账号目录")
    def feed_accounts(
        q: str = Query("", max_length=120),
        sort: Literal["recent", "posts", "likes", "name"] = Query("recent"),
        scope: Literal["all", "following"] = Query("all"),
        limit: int = Query(30, ge=1, le=60),
        offset: int = Query(0, ge=0),
        token: str = Depends(token_dependency),
    ):
        return service().list_accounts(
            query=q.strip(), sort=sort, scope=scope, limit=limit, offset=offset,
        )

    @app.get("/ui/api/feed/tags", tags=["沉浸浏览"], summary="常见话题")
    def feed_tags(token: str = Depends(token_dependency)):
        return {"items": service().top_tags()}

    @app.get("/ui/api/feed/me", tags=["沉浸浏览"], summary="我的统计")
    def feed_me(token: str = Depends(token_dependency)):
        return service().me()

    @app.put("/ui/api/feed/marks", tags=["沉浸浏览"], summary="喜欢、收藏、关注或隐藏")
    def feed_marks(mark: FeedMark, token: str = Depends(token_dependency)):
        return service().set_mark(mark)

    @app.delete("/ui/api/feed/marks", tags=["沉浸浏览"], summary="恢复全部不看的账号")
    def feed_marks_clear(
        kind: Literal["hide"] = Query(...),
        token: str = Depends(token_dependency),
    ):
        return {"cleared": service().state.clear(kind)}

    @app.get("/ui/api/feed/comments", tags=["沉浸浏览"], summary="按需拉取作品评论")
    async def feed_comments(
        request: Request,
        key: str = Query(..., min_length=1, max_length=200),
        cursor: int = Query(0, ge=0),
        reply_to: str = Query("", max_length=64),
        token: str = Depends(token_dependency),
    ):
        return await service().comments(request, key, cursor, reply_to)

    @app.get("/ui/api/feed/thumb", tags=["沉浸浏览"], summary="作品与头像缩略图")
    async def feed_thumb(
        request: Request,
        path: str = Query(..., min_length=1, max_length=2048),
        scope: Literal["download", "project"] = Query("download"),
        second: int = Query(0, ge=0, le=3),
        w: int = Query(480, ge=64, le=1080),
        token: str = Depends(token_dependency),
    ):
        root = server._scope_root(scope)
        try:
            target = resolve_within_root(root, path)
        except ValueError:
            raise HTTPException(status_code=400, detail="Path out of scope.")
        server._ensure_public_file_scope_path(scope, root, target)
        try:
            stat = target.stat()
        except OSError:
            raise HTTPException(status_code=404, detail="File does not exist.")
        suffix = target.suffix.lower()
        is_image = suffix in IMAGE_SUFFIXES
        if not target.is_file() or not (is_image or (suffix in VIDEO_SUFFIXES and scope == "download")):
            raise HTTPException(status_code=404, detail="File does not exist.")
        etag = f'"{stat.st_mtime_ns:x}-{stat.st_size:x}-{w}-{second}"'
        # Downloads never change in place, but a regenerated avatar keeps its path.
        cache = _THUMB_CACHE if scope == "download" else "private, no-cache"
        headers = {"Cache-Control": cache, "ETag": etag}
        if request.headers.get("if-none-match") == etag:
            return Response(status_code=304, headers=headers)
        try:
            async with thumb_slots:
                if is_image:
                    frame = await to_thread(image_preview, target, stat.st_mtime_ns, stat.st_size, w)
                else:
                    frame = await to_thread(video_preview, target, stat.st_mtime_ns, stat.st_size, second)
        except (OSError, SubprocessError, ValueError):
            if is_image:
                # Formats Pillow cannot decode may still display in the browser.
                return FileResponse(target, headers=headers)
            raise HTTPException(status_code=422, detail="Preview unavailable.")
        return Response(frame, media_type="image/jpeg", headers=headers)
