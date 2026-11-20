"""Immersive feed API: posts, profiles and personal marks over the local library."""

from __future__ import annotations

from asyncio import Semaphore, sleep, to_thread
from collections import OrderedDict
from datetime import datetime
from json import dumps, loads
import os
from pathlib import Path
from subprocess import SubprocessError
from time import monotonic
from typing import TYPE_CHECKING, Literal

from fastapi import Depends, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from ..collector import CollectorPlatform
from ..interface import Comment as CommentFetcher, Reply as ReplyFetcher
from ..webui.feed_index import (
    AccountSource,
    FeedIndex,
    FeedWorker,
    _scan_media_names,
    decode_cursor,
    encode_cursor,
    media_kind,
    parse_media_name,
    uid_from_folder,
)
from ..webui.files import IMAGE_SUFFIXES, VIDEO_SUFFIXES, resolve_within_root
from ..webui.video_preview import image_preview, video_preview

if TYPE_CHECKING:
    from .main_server import APIServer

__all__ = ["FeedService", "register_feed_routes"]

_POST_SOURCES = frozenset(
    {"foryou", "arrivals", "latest", "following", "account", "likes", "saves", "popular", "search", "tag", "music"}
)
_COMMENT_CACHE_SECONDS = 900.0
_COMMENT_CACHE_SIZE = 64
_TAG_CACHE_SECONDS = 1800.0
_THUMB_CACHE = "private, max-age=2592000"


class FeedPreferencesPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sound: StrictBool = True
    autoNext: StrictBool = False
    showPauseIcon: StrictBool = True
    pinchZoom: StrictBool = True


class FeedMark(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["like", "save", "follow", "hide", "block"]
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
        self.index = FeedIndex(Path(server.parameter.settings.path).parent / "ui_feed_index.sqlite3")
        self.state = server.feed_state
        self.worker = FeedWorker(
            self.index,
            self.account_sources,
            self.media_root,
            self.detail_database,
            log=self._log,
        )
        self._covers_signature: tuple | None = None
        self._covers: tuple[dict, dict] = ({}, {})
        self._tags: dict[str, tuple[float, list[dict]]] = {}
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
        manifest = Path(server.parameter.settings.path).parent / "media_imports.json"
        if manifest.is_file():
            from src.webui.media_imports import load_import_sources
            for source in load_import_sources(manifest, root):
                if source.folder not in owned:
                    sources.append(source)
                    owned.add(source.folder)
        keys = {source.key for source in sources}
        for platform in ("douyin", "tiktok"):
            for row in server._account_rows(platform == "tiktok", deleted=True):
                url = server._normalize_string(row.get("url"))
                key = server._account_pin_key(platform, url)
                if not url or key in keys:
                    continue
                folder = server._indexed_account_folder(row, folder_index)
                if folder is None or folder in owned:
                    continue
                sources.append(AccountSource(key, platform, url, row.get("mark", ""), folder))
                keys.add(key)
                owned.add(folder)
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

    def _valid_cover(self, scope: str, path: str) -> bool:
        if not path:
            return False
        root = self.server._scope_root(scope)
        try:
            target = resolve_within_root(root, path)
            self.server._ensure_public_file_scope_path(scope, root, target)
            allowed = IMAGE_SUFFIXES | VIDEO_SUFFIXES if scope == "download" else IMAGE_SUFFIXES
            return target.suffix.lower() in allowed and target.is_file()
        except (OSError, ValueError, RuntimeError, HTTPException):
            return False

    def _recover_cover_pin(self, account_key: str, pin: dict, cover_path: str) -> str:
        """Repair older stale pins only when the same media item is unambiguous."""
        old = Path(pin["path"])
        current = Path(cover_path)
        if len(old.parts) < 2 or len(current.parts) < 2:
            return ""
        uid = uid_from_folder(old.parts[0])
        if uid.startswith("f") or uid != uid_from_folder(current.parts[0]):
            return ""
        parsed = parse_media_name(old.name)
        if not parsed.time_key:
            return ""
        try:
            folder = resolve_within_root(self.media_root(), current.parts[0])
        except (ValueError, OSError, RuntimeError):
            return ""
        matches = []
        for name in _scan_media_names(folder):
            candidate = parse_media_name(Path(name).name)
            if (candidate.time_key, candidate.kind, candidate.index, Path(name).suffix.lower()) != (
                parsed.time_key, parsed.kind, parsed.index, old.suffix.lower()
            ):
                continue
            path = (Path(current.parts[0]) / name).as_posix()
            if self._valid_cover("download", path):
                matches.append(path)
                if len(matches) > 1:
                    return ""
        if not matches:
            return ""
        repaired = matches[0]
        # Reload before saving so other accounts' selections are retained.
        try:
            pins = self.server._load_account_board_pins()
            if pins.get(account_key) == pin:
                pins[account_key] = {**pin, "path": repaired}
                self.server._save_account_board_pins(pins)
                self._covers_signature = None
        except (OSError, ValueError):
            pass  # A read-only settings directory must not break browsing.
        return repaired

    def avatar_for(self, account_key: str, cover_path: str) -> dict | None:
        pins, avatars = self._cover_sources()
        if self._valid_cover("project", avatars.get(account_key, "")):
            return {"scope": "project", "path": avatars[account_key], "second": 0}
        pin = pins.get(account_key)
        if pin and pin.get("path"):
            path = pin["path"]
            if not self._valid_cover("download", path):
                path = self._recover_cover_pin(account_key, pin, cover_path)
            if path:
                return {"scope": "download", "path": path, "second": pin.get("second", 0)}
        if self._valid_cover("download", cover_path):
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
                    **({"first_saved_at": row["first_saved_at"]} if "first_saved_at" in row else {}),
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

    @staticmethod
    def can_block_account(account: dict) -> bool:
        return account["platform"] in {"douyin", "tiktok"} and not account["url"].startswith("local://")

    def profile_archive(self, account: dict) -> dict | None:
        platform = account["platform"]
        if platform not in {"douyin", "tiktok"} or account["url"].startswith("local://"):
            return None
        for row in self.server._account_rows(platform == "tiktok", deleted=True):
            if self.server._account_pin_key(platform, row.get("url", "")) != account["account_key"]:
                continue
            if self.server._find_active_account_row(platform, account["url"]):
                return None
            try:
                # The archive stores the server's local time. Include its UTC offset for clients.
                removed_at = datetime.fromisoformat(row.get("deleted_at") or "").astimezone().isoformat()
            except (TypeError, ValueError):
                removed_at = ""
            return {"removed_at": removed_at, "reason": row.get("reason") or ""}
        return None

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

    def refresh_account_files(self, account: str) -> None:
        try:
            self.worker.sync_account_now(account)
        except OSError as error:
            self._log(f"Feed account refresh skipped: {type(error).__name__}")

    def arrival_rows(self, receipts: list[dict], indexed: dict | None = None) -> list[dict]:
        if indexed is None:
            indexed = {r["post_key"]: r for r in self.index.posts_by_keys([r["post_key"] for r in receipts])}
        result = []
        for receipt in receipts:
            key = receipt["post_key"]
            row = indexed.get(key)
            files = loads(receipt["files"])
            if (row and row["account_key"] == receipt["account_key"] and (
                (row["folder"] == receipt["folder"] and set(files).issubset(loads(row["files"])))
                or (row["folder"] != receipt["folder"] and row.get("work_id") == receipt["work_id"])
            )):
                row = {**row, "work_id": row.get("work_id") or receipt["work_id"]}
            else:
                # A completed job can be opened before the indexer reaches its folder.
                # Editor-only targets and alternate tabs can also live outside the profile index.
                try:
                    folder = resolve_within_root(self.media_root(), receipt["folder"])
                    files = [name for name in files if resolve_within_root(folder, name).is_file()]
                except (OSError, ValueError):
                    continue
                if not files:
                    continue
                files.sort(key=lambda name: (parse_media_name(os.path.basename(name)).index, name))
                row = {**receipt, "files": dumps(files), "poster": "", "url": receipt["account_key"].partition("::")[2]}
            result.append({**row, "first_saved_at": receipt["saved_at"]})
        return result

    def stored_posts(self, keys: list[str]) -> list[dict]:
        rows = {r["post_key"]: r for r in self.index.posts_by_keys(keys)}
        missing = [key for key in keys if key not in rows]
        if missing:
            rows.update((r["post_key"], r) for r in self.arrival_rows(self.state.arrivals_by_keys(missing), {}))
        return [rows[key] for key in keys if key in rows]

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
        platform: str = "",
        task_id: str = "",
    ) -> dict:
        # The profile and its grid load in parallel. Refresh here as well so a
        # grid cannot keep old filenames after a collector nickname rename.
        if account and source in {"account", "likes", "saves"}:
            self.refresh_account_files(account)
        index = self.index
        state = self.state
        blocked = state.targets("block")
        hidden = state.targets("hide") + blocked
        pinned = ""
        rows: list[dict] = []
        following: dict | None = None
        available_total = None
        if source == "foryou":
            rows, following = index.foryou_page(
                limit=limit,
                cursor=cursor,
                favorites=state.affinity_accounts(),
                hidden=hidden, platform=platform,
            )
        elif source == "arrivals":
            receipts, following, available_total = state.arrival_page(
                task_id=task_id, platform=platform, hidden=hidden, cursor=cursor, limit=limit,
            )
            rows = self.arrival_rows(receipts)
            while len(rows) < limit and following is not None:
                receipts, following, _ = state.arrival_page(
                    task_id=task_id, platform=platform, hidden=hidden, cursor=following, limit=limit-len(rows),
                )
                rows.extend(self.arrival_rows(receipts))
            if not cursor and following is None:
                available_total = len(rows)
        elif source == "latest":
            rows, following = index.latest_posts(limit=limit, cursor=cursor, hidden=hidden, platform=platform)
        elif source == "following":
            followed = state.targets("follow")
            if followed:
                rows, following = index.latest_posts(limit=limit, cursor=cursor, only=followed, hidden=blocked, platform=platform)
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
            keys, total = state.page(mark, limit=limit, offset=offset, account_key=account, platform=platform)
            rows = self.stored_posts(keys)
            if offset + limit < total:
                following = {"o": offset + limit}
        elif source == "popular":
            rows, following = index.popular_posts(limit=limit, cursor=cursor, hidden=hidden, platform=platform)
        else:
            if query:
                field = {"tag": "tag", "music": "music"}.get(source, "all")
                rows, following = index.search_posts(
                    query, field=field, limit=limit, cursor=cursor, hidden=hidden, platform=platform,
                )
        return {
            **({"available_total": available_total} if available_total is not None else {}),
            **({"summary": state.arrival_summary(task_id)} if task_id and source == "arrivals" and not cursor else {}),
            "items": self.posts_payload(rows, pinned=pinned),
            "next_cursor": encode_cursor(following) if following else None,
        }

    def list_accounts(
        self, *, query: str, sort: str, scope: str, limit: int, offset: int, platform: str = "",
    ) -> dict:
        only = self.state.targets("follow") if scope == "following" else None
        rows, total = self.index.accounts(
            query=query, sort=sort, limit=limit, offset=offset, only=only, platform=platform,
            hidden=[] if query else self.state.targets("block"),
        )
        followed = self.state.marked("follow", [row["account_key"] for row in rows])
        return {
            "items": [self.account_payload(row, followed=followed) for row in rows],
            "total": total,
            "next_offset": offset + limit if offset + limit < total else None,
        }

    def top_tags(self, platform: str = "") -> list[dict]:
        stamp, tags = self._tags.get(platform, (0.0, []))
        if tags and monotonic() - stamp < _TAG_CACHE_SECONDS:
            return tags
        tags = self.index.top_tags(platform=platform)
        self._tags[platform] = (monotonic(), tags)
        return tags

    def me(self, platform: str = "") -> dict:
        counts = self.state.counts(platform=platform)
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
            posts = self.stored_posts([mark.target])
            post = posts[0] if posts else None
            # Removing stays possible after the media itself has gone.
            if post is None and mark.on:
                raise HTTPException(status_code=404, detail="Post not found.")
            account_key = post["account_key"] if post else ""
        elif mark.on:
            account = self.index.account(mark.target)
            if account is None:
                raise HTTPException(status_code=404, detail="Account not found.")
            if mark.kind == "block" and not self.can_block_account(account):
                raise HTTPException(status_code=409, detail="仅采集账号可加入屏蔽审核")
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
        posts = await to_thread(self.stored_posts, [post_key])
        post = posts[0] if posts else None
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

    @app.get("/ui/api/feed/preferences", tags=["沉浸浏览"])
    def feed_preferences(response: Response, token: str = Depends(token_dependency)):
        response.headers["Cache-Control"] = "no-store"
        return service().state.preferences()

    @app.patch("/ui/api/feed/preferences", tags=["沉浸浏览"])
    def update_feed_preferences(payload: FeedPreferencesPatch, response: Response,
                                initialize: bool = False, token: str = Depends(token_dependency)):
        response.headers["Cache-Control"] = "no-store"
        return service().state.update_preferences(payload.model_dump(exclude_unset=True), initialize=initialize)

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
        platform: Literal["", "douyin", "tiktok", "kuaishou", "rednote", "weibo"] = Query(""),
        source: str = Query("foryou", max_length=20),
        task_id: str = Query("", max_length=80),
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
        if source == "arrivals" and task_id and not cursor:
            summary = server.feed_state.arrival_summary(task_id)
            if summary["total"] == 0:
                return {"items": [], "next_cursor": None, "available_total": 0, "summary": summary}
        return service().list_posts(
            source=source,
            task_id=task_id,
            account=account,
            query=q.strip(),
            platform=platform,
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
        posts = feed.stored_posts([key])
        row = posts[0] if posts else None
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
        feed.refresh_account_files(key)
        account = feed.index.account(key)
        if account is None:
            raise HTTPException(status_code=404, detail="Account not found.")
        feed.worker.prioritize(account["uid"])
        payload = feed.account_payload(account)
        payload["archive"] = feed.profile_archive(account)
        payload["can_block"] = feed.can_block_account(account)
        payload["blocked"] = key in feed.state.marked("block", [key])
        payload["liked"] = feed.state.page("like", limit=1, account_key=key)[1]
        payload["saved"] = feed.state.page("save", limit=1, account_key=key)[1]
        journal = getattr(server, "task_journal", None)
        activity = journal.list_account_activity(account["platform"], [account["url"]]) if journal else []
        if activity:
            payload["last_checked_at"] = activity[0].get("last_checked_at", "")
        return payload

    @app.get("/ui/api/feed/accounts", tags=["沉浸浏览"], summary="账号目录")
    def feed_accounts(
        platform: Literal["", "douyin", "tiktok", "kuaishou", "rednote", "weibo"] = Query(""),
        q: str = Query("", max_length=120),
        sort: Literal["recent", "posts", "likes", "name"] = Query("recent"),
        scope: Literal["all", "following"] = Query("all"),
        limit: int = Query(30, ge=1, le=60),
        offset: int = Query(0, ge=0),
        token: str = Depends(token_dependency),
    ):
        return service().list_accounts(
            query=q.strip(), sort=sort, scope=scope, limit=limit, offset=offset, platform=platform,
        )

    @app.get("/ui/api/feed/tags", tags=["沉浸浏览"], summary="常见话题")
    def feed_tags(platform: Literal["", "douyin", "tiktok", "kuaishou", "rednote", "weibo"] = Query(""), token: str = Depends(token_dependency)):
        return {"items": service().top_tags(platform)}

    @app.get("/ui/api/feed/me", tags=["沉浸浏览"], summary="我的统计")
    def feed_me(platform: Literal["", "douyin", "tiktok", "kuaishou", "rednote", "weibo"] = Query(""), token: str = Depends(token_dependency)):
        return service().me(platform)

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
