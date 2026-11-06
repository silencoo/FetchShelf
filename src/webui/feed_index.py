"""Rebuildable index of downloaded posts for the immersive feed.

Files stay the source of truth: a post exists only while its media exists. The
optional crawl database adds captions and counts when they are available, and
is only ever opened read-only in short batches so a running crawl keeps its
write lock. Deleting the index file is always safe; it is rebuilt on next use.
"""

from __future__ import annotations

from base64 import urlsafe_b64decode, urlsafe_b64encode
from collections import deque
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from hashlib import sha1
from json import dumps, loads
import os
from pathlib import Path
from random import randrange
from re import compile as compile_pattern, sub
import sqlite3
from threading import Event, Lock, Thread
from time import monotonic, sleep, time

from .files import IMAGE_SUFFIXES, VIDEO_SUFFIXES

SCHEMA_VERSION = 1
SHUFFLE_SPACE = 1 << 31
RECENT_WINDOW_SECONDS = 45 * 86_400
MAX_SCAN_DEPTH = 2

_TIME_IN_NAME = compile_pattern(
    r"(?<!\d)((?:19|20)\d{2})[-_.](\d{2})[-_.](\d{2})"
    r"[ T_.-](\d{2})[.:-](\d{2})[.:-](\d{2})(?!\d)"
)
_KIND_AFTER_TIME = compile_pattern(
    r"^[-_ .]?(视频|图集|实况|Video|Image|LivePhoto)(?:[-_ .](.*))?$"
)
_LEGACY_KIND_SUFFIX = compile_pattern(r"[-_ ](video|image)(?:[-_](\d{1,4}))?$")
_CAROUSEL_INDEX = compile_pattern(r"_(\d{1,4})$")
_WORK_ID = compile_pattern(r"^\d{15,20}$")
_FOLDER_UID = compile_pattern(r"^UID(\d+)_")
_FOLDER_NAME = compile_pattern(r"^UID\d+_(.*?)(?:_[^_]*)?$")
_TABLE_UID = compile_pattern(r"^UID(\d+)_")
_NOT_A_POSTS_TABLE = compile_pattern(r"(喜欢作品|收藏作品|Likes?|Collections?)$")

_KIND_BY_TOKEN = {
    "视频": "video",
    "Video": "video",
    "video": "video",
    "图集": "images",
    "Image": "images",
    "image": "images",
    "实况": "live",
    "LivePhoto": "live",
}
_KIND_CODE = {"video": "v", "images": "i", "live": "l"}

# Stable Chinese column names; the record manager never localizes them.
_DETAIL_COLUMNS = (
    "发布时间", "作品ID", "作品描述", "作品话题", "隐藏标签", "视频时长",
    "视频高度", "视频宽度", "作品链接", "账号昵称", "ID", "账号签名",
    "音乐作者", "音乐标题", "音乐链接", "点赞数量", "评论数量", "收藏数量",
    "分享数量", "播放数量",
)

_SCHEMA = """
CREATE TABLE accounts (
    account_key TEXT PRIMARY KEY,
    platform TEXT NOT NULL,
    url TEXT NOT NULL,
    mark TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL DEFAULT '',
    uid TEXT NOT NULL DEFAULT '',
    folder TEXT NOT NULL DEFAULT '',
    folder_mtime_ns INTEGER NOT NULL DEFAULT 0,
    scanned INTEGER NOT NULL DEFAULT 0,
    post_count INTEGER NOT NULL DEFAULT 0,
    video_count INTEGER NOT NULL DEFAULT 0,
    image_count INTEGER NOT NULL DEFAULT 0,
    total_likes INTEGER NOT NULL DEFAULT 0,
    latest_ts INTEGER NOT NULL DEFAULT 0,
    cover_path TEXT NOT NULL DEFAULT '',
    nickname TEXT NOT NULL DEFAULT '',
    handle TEXT NOT NULL DEFAULT '',
    bio TEXT NOT NULL DEFAULT ''
);
CREATE INDEX accounts_uid ON accounts(uid);
CREATE INDEX accounts_latest ON accounts(latest_ts DESC);

CREATE TABLE posts (
    id INTEGER PRIMARY KEY,
    post_key TEXT NOT NULL UNIQUE,
    account_key TEXT NOT NULL,
    uid TEXT NOT NULL,
    time_key TEXT NOT NULL,
    kind TEXT NOT NULL,
    published_ts INTEGER NOT NULL,
    caption TEXT NOT NULL DEFAULT '',
    work_hint TEXT NOT NULL DEFAULT '',
    files TEXT NOT NULL,
    poster TEXT NOT NULL DEFAULT '',
    shuffle INTEGER NOT NULL
);
CREATE INDEX posts_account_time ON posts(account_key, published_ts);
CREATE INDEX posts_time ON posts(published_ts);
CREATE INDEX posts_shuffle ON posts(shuffle);
CREATE INDEX posts_uid_time ON posts(uid, time_key);

CREATE TABLE meta (
    uid TEXT NOT NULL,
    time_key TEXT NOT NULL,
    work_id TEXT NOT NULL DEFAULT '',
    caption TEXT NOT NULL DEFAULT '',
    tags TEXT NOT NULL DEFAULT '',
    hidden_tags TEXT NOT NULL DEFAULT '',
    duration INTEGER,
    width INTEGER,
    height INTEGER,
    share_url TEXT NOT NULL DEFAULT '',
    music_author TEXT NOT NULL DEFAULT '',
    music_title TEXT NOT NULL DEFAULT '',
    music_url TEXT NOT NULL DEFAULT '',
    likes INTEGER,
    comments INTEGER,
    saves INTEGER,
    shares INTEGER,
    plays INTEGER,
    PRIMARY KEY (uid, time_key)
) WITHOUT ROWID;
CREATE INDEX meta_likes ON meta(likes);

CREATE TABLE meta_tables (
    table_name TEXT PRIMARY KEY,
    uid TEXT NOT NULL,
    last_rowid INTEGER NOT NULL DEFAULT 0
);
"""

_POST_COLUMNS = """
    p.id, p.post_key, p.account_key, p.uid, p.time_key, p.kind, p.published_ts,
    p.caption, p.work_hint, p.files, p.poster, p.shuffle,
    a.platform, a.url, a.mark, a.name, a.folder, a.cover_path,
    m.work_id, m.caption AS full_caption, m.tags, m.duration, m.width, m.height,
    m.share_url, m.music_author, m.music_title, m.music_url,
    m.likes, m.comments, m.saves, m.shares, m.plays
"""
_POST_SOURCE = """
    FROM posts p
    JOIN accounts a ON a.account_key = p.account_key
    LEFT JOIN meta m ON m.uid = p.uid AND m.time_key = p.time_key
"""
_POST_SELECT = f"SELECT {_POST_COLUMNS} {_POST_SOURCE}"


@dataclass(frozen=True)
class AccountSource:
    key: str
    platform: str
    url: str
    mark: str
    folder: Path | None


@dataclass(frozen=True, slots=True)
class ParsedName:
    time_key: str
    kind: str
    index: int
    base: str
    caption: str


@dataclass(slots=True)
class ScannedPost:
    post_key: str
    time_key: str
    kind: str
    published_ts: int
    caption: str
    work_hint: str
    files: list[str]
    poster: str = ""


def media_kind(name: str) -> str:
    suffix = os.path.splitext(name)[1].lower()
    if suffix in VIDEO_SUFFIXES:
        return "video"
    if suffix in IMAGE_SUFFIXES:
        return "image"
    return ""


def uid_from_folder(name: str) -> str:
    match = _FOLDER_UID.match(name)
    if match:
        return match.group(1)
    return "f" + sha1(name.encode("utf-8")).hexdigest()[:14]


def name_from_folder(name: str) -> str:
    match = _FOLDER_NAME.match(name)
    return (match.group(1) if match else name).strip("_ ")


def time_key_from_text(value: object) -> str:
    digits = sub(r"\D", "", str(value or ""))
    return digits if len(digits) == 14 else ""


def _timestamp(time_key: str) -> int | None:
    try:
        return int(
            datetime(
                int(time_key[:4]), int(time_key[4:6]), int(time_key[6:8]),
                int(time_key[8:10]), int(time_key[10:12]), int(time_key[12:14]),
            ).timestamp()
        )
    except (ValueError, OverflowError, OSError):
        return None


def _strip_nickname(rest: str, account_name: str) -> str:
    if account_name and rest.startswith(account_name):
        return rest[len(account_name):].lstrip("-_ .")
    # Nicknames rarely contain the separator; a wrong guess only trims a
    # filename caption, and the crawl record replaces it when one exists.
    head, separator, tail = rest.partition("-")
    return tail if separator else ""


def parse_media_name(name: str, account_name: str = "") -> ParsedName:
    """Understand both download naming schemes without trusting either."""
    stem = os.path.splitext(name)[0]
    file_kind = media_kind(name)
    match = _TIME_IN_NAME.search(stem)
    time_key = "".join(match.groups()) if match else ""
    if time_key and _timestamp(time_key) is None:
        time_key = ""
        match = None
    after = stem[match.end():] if match else stem

    kind_match = _KIND_AFTER_TIME.match(after) if match else None
    if kind_match:
        kind = _KIND_BY_TOKEN[kind_match.group(1)]
        rest = kind_match.group(2) or ""
        index = 0
        base = stem
        if kind != "video":
            numbered = _CAROUSEL_INDEX.search(rest)
            if numbered:
                index = int(numbered.group(1))
                rest = rest[:numbered.start()]
                base = stem[:stem.rfind(numbered.group(0))]
        return ParsedName(time_key, kind, index, base, _strip_nickname(rest, account_name))

    legacy = _LEGACY_KIND_SUFFIX.search(after)
    if match and legacy:
        kind = _KIND_BY_TOKEN[legacy.group(1)]
        index = int(legacy.group(2) or 0)
        base = stem[: match.end() + legacy.start()]
        caption = after[: legacy.start()].strip("_- .").replace("_", " ")
        return ParsedName(time_key, kind, index, base, caption)

    kind = "video" if file_kind == "video" else "images"
    index = 0
    base = stem
    if kind == "images":
        numbered = _CAROUSEL_INDEX.search(stem)
        if numbered:
            index = int(numbered.group(1))
            base = stem[: numbered.start()]
    caption = _CAROUSEL_INDEX.sub("", after) if kind == "images" else after
    return ParsedName(time_key, kind, index, base, caption.strip("_- ."))


def _scan_media_names(folder: Path) -> Iterator[str]:
    """Yield media paths relative to an account folder (bounded, no stat)."""
    stack = [(folder, "", 0)]
    while stack:
        current, prefix, depth = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    if entry.name.startswith("."):
                        continue
                    relative = f"{prefix}{entry.name}"
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            if depth < MAX_SCAN_DEPTH:
                                stack.append((Path(entry.path), f"{relative}/", depth + 1))
                        elif media_kind(entry.name):
                            yield relative
                    except OSError:
                        continue
        except OSError:
            continue


def _newest_mtime(folder: Path, names: Iterable[str]) -> int:
    newest = 0
    for name in names:
        try:
            newest = max(newest, folder.joinpath(name).stat().st_mtime_ns)
        except OSError:
            continue
    return newest


def scan_folder(folder: Path, uid: str, account_name: str = "") -> list[ScannedPost]:
    """Group the media in one account folder into posts."""
    groups: dict[tuple[str, str], dict[str, list[tuple[int, str]]]] = {}
    captions: dict[str, str] = {}
    for relative in _scan_media_names(folder):
        parsed = parse_media_name(os.path.basename(relative), account_name)
        time_key = parsed.time_key or "x" + sha1(parsed.base.encode("utf-8")).hexdigest()[:14]
        groups.setdefault((time_key, parsed.kind), {}).setdefault(parsed.base, []).append(
            (parsed.index, relative)
        )
        captions.setdefault(parsed.base, parsed.caption)

    posts = []
    for (time_key, kind), bases in groups.items():
        # A nickname or caption edit re-downloads the same work under a new
        # stem. Every sampled same-second pair was byte-identical, so keep one.
        base = next(iter(bases))
        if len(bases) > 1:
            base = max(
                bases,
                key=lambda value: (
                    len(bases[value]),
                    _newest_mtime(folder, (name for _, name in bases[value])),
                    value,
                ),
            )
        files = [name for _, name in sorted(bases[base])]
        videos = [name for name in files if media_kind(name) == "video"]
        images = [name for name in files if media_kind(name) == "image"]
        poster = ""
        if kind == "video":
            if videos:
                # Optional sidecar covers share the stem; they are not slides.
                poster = images[0] if images else ""
                files = videos
            else:
                kind = "images"
        elif kind == "live" and not videos:
            kind = "images"
        elif kind == "images" and videos:
            kind = "live"

        if time_key.startswith("x"):
            published_ts = int(_newest_mtime(folder, files) / 1_000_000_000)
        else:
            published_ts = _timestamp(time_key) or 0
        caption = captions.get(base, "")
        work_hint = ""
        if _WORK_ID.match(caption):
            work_hint, caption = caption, ""
        posts.append(
            ScannedPost(
                post_key=f"{uid}:{time_key}:{_KIND_CODE[kind]}",
                time_key=time_key,
                kind=kind,
                published_ts=published_ts,
                caption=caption,
                work_hint=work_hint,
                files=files,
                poster=poster,
            )
        )
    return posts


def encode_cursor(value: dict) -> str:
    raw = dumps(value, separators=(",", ":")).encode("utf-8")
    return urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(value: str) -> dict:
    if not value:
        return {}
    try:
        decoded = loads(urlsafe_b64decode(value + "=" * (-len(value) % 4)))
    except (ValueError, TypeError):
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _like_pattern(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _positive(value: object) -> int | None:
    """Normalize crawl counts, where -1 and empty both mean unknown."""
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _duration_seconds(value: object) -> int | None:
    text = str(value or "").strip()
    if not text or text == "-1":
        return None
    try:
        total = 0
        for part in text.split(":"):
            total = total * 60 + int(part)
    except ValueError:
        return None
    return total if total > 0 else None


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _kind_clause(kind: str) -> str:
    if kind == "video":
        return " AND p.kind = 'video'"
    if kind == "images":
        return " AND p.kind != 'video'"
    return ""


class FeedIndex:
    """SQLite-backed queries and reconciliation; safe across threads."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._prepared = False
        self._prepare_lock = Lock()

    def _prepare(self) -> None:
        if self._prepared:
            return
        with self._prepare_lock:
            if self._prepared:
                return
            self.path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(self.path, timeout=10, isolation_level=None)
            try:
                version = connection.execute("PRAGMA user_version").fetchone()[0]
                if version != SCHEMA_VERSION:
                    connection.close()
                    # A cache with an old layout is cheaper to rebuild than migrate.
                    for suffix in ("", "-wal", "-shm"):
                        Path(f"{self.path}{suffix}").unlink(missing_ok=True)
                    connection = sqlite3.connect(self.path, timeout=10, isolation_level=None)
                    connection.execute("PRAGMA journal_mode=WAL")
                    connection.executescript(
                        f"BEGIN;{_SCHEMA}PRAGMA user_version={SCHEMA_VERSION};COMMIT;"
                    )
            finally:
                connection.close()
            self._prepared = True

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        self._prepare()
        connection = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA synchronous=NORMAL")
            yield connection
        finally:
            connection.close()

    @staticmethod
    @contextmanager
    def _transaction(connection: sqlite3.Connection) -> Iterator[None]:
        connection.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            connection.execute("ROLLBACK")
            raise
        connection.execute("COMMIT")

    # ------------------------------------------------------------------ files

    def sync_account(self, source: AccountSource, root: Path, *, force: bool = False) -> bool:
        """Reconcile one account folder. Returns whether anything was rescanned."""
        folder = source.folder
        folder_rel = ""
        mtime_ns = 0
        uid = ""
        name = source.mark
        if folder is not None:
            try:
                mtime_ns = folder.stat().st_mtime_ns
                folder_rel = folder.relative_to(root).as_posix()
                uid = uid_from_folder(folder.name)
                name = source.mark or name_from_folder(folder.name)
            except (OSError, ValueError):
                folder = None
                mtime_ns = 0

        with self._connect() as connection:
            current = connection.execute(
                "SELECT folder, folder_mtime_ns, scanned, mark FROM accounts WHERE account_key = ?",
                (source.key,),
            ).fetchone()
            if (
                current
                and not force
                and current["scanned"]
                and current["folder"] == folder_rel
                and current["folder_mtime_ns"] == mtime_ns
            ):
                if current["mark"] != source.mark:
                    connection.execute(
                        "UPDATE accounts SET mark = ?, name = ? WHERE account_key = ?",
                        (source.mark, name, source.key),
                    )
                return False

        scanned = scan_folder(folder, uid, name) if folder is not None else []
        by_key = {post.post_key: post for post in scanned}
        newest = max(scanned, key=lambda post: post.published_ts, default=None)
        cover_path = ""
        if newest is not None:
            cover_path = f"{folder_rel}/{newest.poster or newest.files[0]}"
        with self._connect() as connection:
            with self._transaction(connection):
                existing = {
                    row["post_key"]: row
                    for row in connection.execute(
                        "SELECT post_key, kind, caption, files, poster, published_ts "
                        "FROM posts WHERE account_key = ?",
                        (source.key,),
                    )
                }
                for key in existing.keys() - by_key.keys():
                    connection.execute("DELETE FROM posts WHERE post_key = ?", (key,))
                for key, post in by_key.items():
                    files = dumps(post.files, ensure_ascii=False)
                    previous = existing.get(key)
                    if previous is not None and (
                        previous["files"] == files
                        and previous["caption"] == post.caption
                        and previous["poster"] == post.poster
                        and previous["kind"] == post.kind
                        and previous["published_ts"] == post.published_ts
                    ):
                        continue
                    connection.execute(
                        """
                        INSERT INTO posts (post_key, account_key, uid, time_key, kind,
                            published_ts, caption, work_hint, files, poster, shuffle)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(post_key) DO UPDATE SET
                            account_key = excluded.account_key, kind = excluded.kind,
                            published_ts = excluded.published_ts, caption = excluded.caption,
                            work_hint = excluded.work_hint, files = excluded.files,
                            poster = excluded.poster
                        """,
                        (
                            key, source.key, uid, post.time_key, post.kind, post.published_ts,
                            post.caption, post.work_hint, files, post.poster,
                            randrange(SHUFFLE_SPACE),
                        ),
                    )
                video_count = sum(post.kind == "video" for post in scanned)
                connection.execute(
                    """
                    INSERT INTO accounts (account_key, platform, url, mark, name, uid, folder,
                        folder_mtime_ns, scanned, post_count, video_count, image_count,
                        latest_ts, cover_path)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?)
                    ON CONFLICT(account_key) DO UPDATE SET
                        platform = excluded.platform, url = excluded.url, mark = excluded.mark,
                        name = excluded.name, uid = excluded.uid, folder = excluded.folder,
                        folder_mtime_ns = excluded.folder_mtime_ns, scanned = 1,
                        post_count = excluded.post_count, video_count = excluded.video_count,
                        image_count = excluded.image_count, latest_ts = excluded.latest_ts,
                        cover_path = excluded.cover_path
                    """,
                    (
                        source.key, source.platform, source.url, source.mark, name, uid,
                        folder_rel, mtime_ns, len(scanned), video_count,
                        len(scanned) - video_count,
                        newest.published_ts if newest else 0, cover_path,
                    ),
                )
                self._refresh_account_totals(connection, uid)
        return True

    def retire_accounts(self, active_keys: set[str]) -> int:
        """Forget accounts that left the configured lists; media stays on disk."""
        with self._connect() as connection:
            known = {row[0] for row in connection.execute("SELECT account_key FROM accounts")}
            removed = known - active_keys
            if removed:
                with self._transaction(connection):
                    for key in removed:
                        connection.execute("DELETE FROM posts WHERE account_key = ?", (key,))
                        connection.execute("DELETE FROM accounts WHERE account_key = ?", (key,))
            return len(removed)

    @staticmethod
    def _refresh_account_totals(connection: sqlite3.Connection, uid: str) -> None:
        if not uid:
            return
        connection.execute(
            """
            UPDATE accounts SET total_likes = (
                SELECT COALESCE(SUM(m.likes), 0)
                FROM posts p JOIN meta m ON m.uid = p.uid AND m.time_key = p.time_key
                WHERE p.account_key = accounts.account_key
            ) WHERE uid = ?
            """,
            (uid,),
        )

    # ------------------------------------------------------------- crawl data

    def apply_detail_rows(self, uid: str, rows: Iterable[tuple], table: str, last_rowid: int) -> None:
        """Store crawl rows (ascending rowid) so the newest row of a work wins."""
        latest: dict[str, tuple] = {}
        for row in rows:
            time_key = time_key_from_text(row[0])
            if time_key:
                latest[time_key] = row
        profile = {}
        records = []
        for time_key, row in latest.items():
            (
                _, work_id, caption, tags, hidden_tags, duration, height, width, share_url,
                nickname, handle, bio, music_author, music_title, music_url, likes, comments,
                saves, shares, plays,
            ) = row
            profile = {"nickname": nickname, "handle": handle, "bio": bio}
            records.append(
                (
                    uid, time_key, str(work_id or ""), str(caption or ""), str(tags or ""),
                    str(hidden_tags or ""), _duration_seconds(duration),
                    _positive(width) or None, _positive(height) or None, str(share_url or ""),
                    str(music_author or ""), str(music_title or ""), str(music_url or ""),
                    _positive(likes), _positive(comments), _positive(saves), _positive(shares),
                    _positive(plays),
                )
            )
        with self._connect() as connection:
            with self._transaction(connection):
                connection.executemany(
                    """
                    INSERT INTO meta (uid, time_key, work_id, caption, tags, hidden_tags,
                        duration, width, height, share_url, music_author, music_title, music_url,
                        likes, comments, saves, shares, plays)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(uid, time_key) DO UPDATE SET
                        work_id = excluded.work_id, caption = excluded.caption,
                        tags = excluded.tags, hidden_tags = excluded.hidden_tags,
                        duration = excluded.duration, width = excluded.width,
                        height = excluded.height, share_url = excluded.share_url,
                        music_author = excluded.music_author, music_title = excluded.music_title,
                        music_url = excluded.music_url, likes = excluded.likes,
                        comments = excluded.comments, saves = excluded.saves,
                        shares = excluded.shares, plays = excluded.plays
                    """,
                    records,
                )
                connection.execute(
                    """
                    INSERT INTO meta_tables (table_name, uid, last_rowid) VALUES (?, ?, ?)
                    ON CONFLICT(table_name) DO UPDATE SET last_rowid = excluded.last_rowid
                    """,
                    (table, uid, last_rowid),
                )
                if profile:
                    connection.execute(
                        """
                        UPDATE accounts SET
                            nickname = COALESCE(NULLIF(?, ''), nickname),
                            handle = COALESCE(NULLIF(?, ''), handle),
                            bio = COALESCE(NULLIF(?, ''), bio)
                        WHERE uid = ?
                        """,
                        (
                            str(profile["nickname"] or ""), str(profile["handle"] or ""),
                            str(profile["bio"] or ""), uid,
                        ),
                    )

    def finish_detail_table(self, uid: str) -> None:
        with self._connect() as connection:
            self._refresh_account_totals(connection, uid)

    def detail_watermarks(self) -> dict[str, int]:
        with self._connect() as connection:
            return {
                row["table_name"]: row["last_rowid"]
                for row in connection.execute("SELECT table_name, last_rowid FROM meta_tables")
            }

    def indexed_uids(self) -> set[str]:
        with self._connect() as connection:
            return {row[0] for row in connection.execute("SELECT uid FROM accounts WHERE uid != ''")}

    # ---------------------------------------------------------------- queries

    def counts(self) -> dict:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS accounts,
                       COALESCE(SUM(scanned), 0) AS scanned,
                       COALESCE(SUM(post_count), 0) AS posts
                FROM accounts
                """
            ).fetchone()
            return dict(row)

    def post(self, post_key: str) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                f"{_POST_SELECT} WHERE p.post_key = ?", (post_key,)
            ).fetchone()
            return dict(row) if row else None

    def posts_by_keys(self, keys: list[str]) -> list[dict]:
        if not keys:
            return []
        with self._connect() as connection:
            rows = connection.execute(
                f"{_POST_SELECT} WHERE p.post_key IN (SELECT value FROM json_each(?))",
                (dumps(keys),),
            ).fetchall()
        by_key = {row["post_key"]: dict(row) for row in rows}
        return [by_key[key] for key in keys if key in by_key]

    def account(self, account_key: str) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM accounts WHERE account_key = ?", (account_key,)
            ).fetchone()
            return dict(row) if row else None

    def accounts(
        self,
        *,
        query: str = "",
        sort: str = "recent",
        limit: int = 30,
        offset: int = 0,
        only: list[str] | None = None,
    ) -> tuple[list[dict], int]:
        clauses = ["post_count > 0"]
        params: list = []
        if query:
            clauses.append("(mark LIKE ? ESCAPE '\\' OR nickname LIKE ? ESCAPE '\\')")
            params += [_like_pattern(query)] * 2
        if only is not None:
            clauses.append("account_key IN (SELECT value FROM json_each(?))")
            params.append(dumps(only))
        order = {
            "posts": "post_count DESC, latest_ts DESC",
            "likes": "total_likes DESC, latest_ts DESC",
            "name": "name COLLATE NOCASE ASC",
        }.get(sort, "latest_ts DESC")
        where = " AND ".join(clauses)
        with self._connect() as connection:
            total = connection.execute(
                f"SELECT COUNT(*) FROM accounts WHERE {where}", params
            ).fetchone()[0]
            rows = connection.execute(
                f"SELECT * FROM accounts WHERE {where} ORDER BY {order} LIMIT ? OFFSET ?",
                [*params, limit, offset],
            ).fetchall()
        return [dict(row) for row in rows], total

    def latest_posts(
        self,
        *,
        limit: int,
        cursor: dict,
        only: list[str] | None = None,
        hidden: list[str] | None = None,
    ) -> tuple[list[dict], dict | None]:
        clauses = ["1 = 1"]
        params: list = []
        if only is not None:
            clauses.append("p.account_key IN (SELECT value FROM json_each(?))")
            params.append(dumps(only))
        if hidden:
            clauses.append("p.account_key NOT IN (SELECT value FROM json_each(?))")
            params.append(dumps(hidden))
        if "t" in cursor and "i" in cursor:
            clauses.append("(p.published_ts, p.id) < (?, ?)")
            params += [cursor["t"], cursor["i"]]
        query = (
            f"{_POST_SELECT} WHERE {' AND '.join(clauses)} "
            "ORDER BY p.published_ts DESC, p.id DESC LIMIT ?"
        )
        with self._connect() as connection:
            rows = [dict(row) for row in connection.execute(query, [*params, limit + 1])]
        following = None
        if len(rows) > limit:
            rows = rows[:limit]
            following = {"t": rows[-1]["published_ts"], "i": rows[-1]["id"]}
        return rows, following

    def account_posts(
        self,
        account_key: str,
        *,
        limit: int,
        cursor: dict,
        sort: str = "latest",
        kind: str = "all",
        exclude: str = "",
    ) -> tuple[list[dict], dict | None]:
        clauses = ["p.account_key = ?"]
        params: list = [account_key]
        if exclude:
            clauses.append("p.post_key != ?")
            params.append(exclude)
        where = " AND ".join(clauses) + _kind_clause(kind)
        if sort == "popular":
            offset = max(0, int(cursor.get("o", 0)))
            query = (
                f"{_POST_SELECT} WHERE {where} "
                "ORDER BY COALESCE(m.likes, -1) DESC, p.published_ts DESC, p.id DESC LIMIT ? OFFSET ?"
            )
            with self._connect() as connection:
                rows = [dict(row) for row in connection.execute(query, [*params, limit + 1, offset])]
            following = None
            if len(rows) > limit:
                rows = rows[:limit]
                following = {"o": offset + limit}
            return rows, following

        ascending = sort == "oldest"
        if "t" in cursor and "i" in cursor:
            where += f" AND (p.published_ts, p.id) {'>' if ascending else '<'} (?, ?)"
            params += [cursor["t"], cursor["i"]]
        direction = "ASC" if ascending else "DESC"
        query = (
            f"{_POST_SELECT} WHERE {where} "
            f"ORDER BY p.published_ts {direction}, p.id {direction} LIMIT ?"
        )
        with self._connect() as connection:
            rows = [dict(row) for row in connection.execute(query, [*params, limit + 1])]
        following = None
        if len(rows) > limit:
            rows = rows[:limit]
            following = {"t": rows[-1]["published_ts"], "i": rows[-1]["id"]}
        return rows, following

    def popular_posts(
        self, *, limit: int, cursor: dict, hidden: list[str] | None = None,
    ) -> tuple[list[dict], dict | None]:
        offset = max(0, int(cursor.get("o", 0)))
        params: list = []
        clause = ""
        if hidden:
            clause = "AND p.account_key NOT IN (SELECT value FROM json_each(?))"
            params.append(dumps(hidden))
        query = f"""
            SELECT {_POST_COLUMNS}
            FROM meta m
            CROSS JOIN posts p ON p.uid = m.uid AND p.time_key = m.time_key
            JOIN accounts a ON a.account_key = p.account_key
            WHERE m.likes IS NOT NULL {clause}
            ORDER BY m.likes DESC LIMIT ? OFFSET ?
        """
        with self._connect() as connection:
            rows = [dict(row) for row in connection.execute(query, [*params, limit + 1, offset])]
        following = None
        if len(rows) > limit:
            rows = rows[:limit]
            following = {"o": offset + limit}
        return rows, following

    def search_posts(
        self,
        text: str,
        *,
        field: str = "all",
        limit: int,
        cursor: dict,
        hidden: list[str] | None = None,
    ) -> tuple[list[dict], dict | None]:
        """Scan each text column on its own, then join only what matched.

        Filtering a joined walk over every post costs two index probes per post,
        which took seconds for a rare word on a 300k-post library.
        """
        offset = max(0, int(cursor.get("o", 0)))
        from_meta = (
            "SELECT p.id FROM meta m CROSS JOIN posts p "
            "ON p.uid = m.uid AND p.time_key = m.time_key WHERE "
        )
        matches: list[tuple[str, list]] = []
        if field == "music":
            matches.append((f"{from_meta}m.music_title = ?", [text]))
        elif field == "tag":
            tag = _like_pattern(f"#{text}")
            matches.append((
                f"{from_meta}m.caption LIKE ? ESCAPE '\\' "
                "OR (' ' || m.tags || ' ') LIKE ? ESCAPE '\\'",
                [tag, _like_pattern(f" {text} ")],
            ))
            matches.append(("SELECT id FROM posts WHERE caption LIKE ? ESCAPE '\\'", [tag]))
        else:
            pattern = _like_pattern(text)
            matches.append((
                f"{from_meta}m.caption LIKE ? ESCAPE '\\' OR m.tags LIKE ? ESCAPE '\\' "
                "OR m.hidden_tags LIKE ? ESCAPE '\\'",
                [pattern, pattern, pattern],
            ))
            matches.append(("SELECT id FROM posts WHERE caption LIKE ? ESCAPE '\\'", [pattern]))
            matches.append((
                "SELECT p.id FROM accounts a CROSS JOIN posts p ON p.account_key = a.account_key "
                "WHERE a.mark LIKE ? ESCAPE '\\'",
                [pattern],
            ))
        union = " UNION ".join(sql for sql, _ in matches)
        params = [value for _, values in matches for value in values]
        hidden_clause = ""
        if hidden:
            hidden_clause = "WHERE p.account_key NOT IN (SELECT value FROM json_each(?))"
            params.append(dumps(hidden))
        query = f"""
            WITH found(id) AS ({union}),
            page(id) AS (
                SELECT p.id FROM found CROSS JOIN posts p ON p.id = found.id
                {hidden_clause}
                ORDER BY p.published_ts DESC, p.id DESC LIMIT ? OFFSET ?
            )
            SELECT {_POST_COLUMNS}
            FROM page
            CROSS JOIN posts p ON p.id = page.id
            JOIN accounts a ON a.account_key = p.account_key
            LEFT JOIN meta m ON m.uid = p.uid AND m.time_key = p.time_key
            ORDER BY p.published_ts DESC, p.id DESC
        """
        with self._connect() as connection:
            rows = [dict(row) for row in connection.execute(query, [*params, limit + 1, offset])]
        following = None
        if len(rows) > limit:
            rows = rows[:limit]
            following = {"o": offset + limit}
        return rows, following

    def top_tags(self, limit: int = 24) -> list[dict]:
        counts: dict[str, int] = {}
        with self._connect() as connection:
            for (tags,) in connection.execute(
                "SELECT m.tags FROM meta m JOIN posts p ON p.uid = m.uid AND p.time_key = m.time_key "
                "WHERE m.tags != ''"
            ):
                for tag in set(str(tags).split()):
                    counts[tag] = counts.get(tag, 0) + 1
        ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]
        return [{"tag": tag, "count": count} for tag, count in ranked]

    # --------------------------------------------------------------- For You

    @staticmethod
    def _pool_take(
        connection: sqlite3.Connection,
        condition: str,
        params: list,
        state: list[int],
        count: int,
    ) -> list[dict]:
        """Walk one shuffled pool once, wrapping around its random start."""
        taken: list[dict] = []
        position, start, wrapped, done = state
        while len(taken) < count and not done:
            upper = "AND p.shuffle <= ?" if wrapped else ""
            query = (
                f"{_POST_SELECT} WHERE p.shuffle > ? {upper} AND {condition} "
                "ORDER BY p.shuffle LIMIT ?"
            )
            arguments = [position, *([start] if wrapped else []), *params, count - len(taken)]
            rows = connection.execute(query, arguments).fetchall()
            taken += [dict(row) for row in rows]
            if rows:
                position = rows[-1]["shuffle"]
            if len(taken) < count:
                if wrapped:
                    done = 1
                else:
                    wrapped, position = 1, -1
        state[:] = [position, start, wrapped, done]
        return taken

    @staticmethod
    def _spread_authors(rows: list[dict]) -> list[dict]:
        """Keep two posts by one author from sitting next to each other."""
        remaining = list(rows)
        ordered: list[dict] = []
        while remaining:
            previous = ordered[-1]["account_key"] if ordered else None
            choice = next(
                (index for index, row in enumerate(remaining) if row["account_key"] != previous),
                0,
            )
            ordered.append(remaining.pop(choice))
        return ordered

    def foryou_page(
        self,
        *,
        limit: int,
        cursor: dict,
        favorites: list[str],
        hidden: list[str],
        now: float | None = None,
    ) -> tuple[list[dict], dict | None]:
        """Mix recent work, accounts you responded to, and the whole library.

        Each pool is a single pass over a fixed shuffle from a random start, so
        paging is O(log n) and needs no server-side watch history. The "all"
        pool covers everything, so nothing is lost when the feed ends with it.
        """

        def pool(name: str) -> list[int]:
            state = cursor.get(name)
            if isinstance(state, list) and len(state) == 4:
                return [int(value) for value in state]
            start = randrange(SHUFFLE_SPACE)
            return [start, start, 0, 0]

        pools = {name: pool(name) for name in ("r", "f", "a")}
        recent_since = int((now if now is not None else time()) - RECENT_WINDOW_SECONDS)
        hidden_clause = ""
        hidden_params: list = []
        if hidden:
            hidden_clause = " AND p.account_key NOT IN (SELECT value FROM json_each(?))"
            hidden_params = [dumps(hidden)]
        conditions = {
            "r": (f"p.published_ts >= ?{hidden_clause}", [recent_since, *hidden_params]),
            "f": (
                f"p.account_key IN (SELECT value FROM json_each(?)){hidden_clause}",
                [dumps(favorites), *hidden_params],
            ),
            "a": (f"1 = 1{hidden_clause}", hidden_params),
        }
        order = ["r", "a", "f", "a"] if favorites else ["r", "a", "a"]
        rows: list[dict] = []
        keys: set[str] = set()
        with self._connect() as connection:
            position = 0
            misses = 0
            while len(rows) < limit and misses < len(order):
                name = order[position % len(order)]
                position += 1
                condition, params = conditions[name]
                taken = self._pool_take(connection, condition, params, pools[name], 1)
                fresh = [row for row in taken if row["post_key"] not in keys]
                keys.update(row["post_key"] for row in fresh)
                rows += fresh
                misses = 0 if taken else misses + 1
        following = None if pools["a"][3] else pools
        return self._spread_authors(rows), following


@dataclass
class WorkerStatus:
    phase: str = "idle"
    done: int = 0
    total: int = 0
    metadata_available: bool = False
    metadata_done: int = 0
    metadata_total: int = 0
    last_finished_at: float = 0.0
    error: str = ""
    rescanned: int = 0


class FeedWorker:
    """Keeps the index current in the background while the feed is in use."""

    PASS_INTERVAL = 600.0
    ACTIVITY_WINDOW = 6 * 3600.0
    TOUCH_RESCAN_AFTER = 120.0
    DETAIL_BATCH = 500
    FOLDER_PAUSE = 0.001

    def __init__(
        self,
        index: FeedIndex,
        sources: Callable[[], list[AccountSource]],
        root: Callable[[], Path],
        detail_database: Callable[[], Path | None],
        *,
        log: Callable[[str], None] | None = None,
        throttle: bool = True,
    ):
        self.index = index
        self.sources = sources
        self.root = root
        self.detail_database = detail_database
        self.log = log or (lambda message: None)
        self.throttle = throttle
        self.status = WorkerStatus()
        self._thread: Thread | None = None
        self._wake = Event()
        self._stop = Event()
        self._last_touch = 0.0
        self._finished_monotonic = 0.0
        self._force_files = False
        self._detail_stamp: tuple[int, int] | None = None
        self._priority: deque[str] = deque(maxlen=64)
        self._priority_lock = Lock()
        self._account_lock = Lock()

    def touch(self) -> None:
        self._last_touch = monotonic()
        if self._thread is None or not self._thread.is_alive():
            self._stop.clear()
            self.status.phase = "listing"
            self._thread = Thread(target=self._run, name="feed-index", daemon=True)
            self._thread.start()
        elif (
            self.status.phase == "idle"
            and monotonic() - self._finished_monotonic > self.TOUCH_RESCAN_AFTER
        ):
            self._wake.set()

    def request_sync(self, *, force: bool = False) -> None:
        self._force_files = self._force_files or force
        self.touch()
        self._wake.set()

    def prioritize(self, uid: str) -> None:
        if not uid:
            return
        with self._priority_lock:
            if uid not in self._priority:
                self._priority.append(uid)

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    def sync_account_now(self, account_key: str) -> None:
        """Pick up new files immediately when a profile is opened."""
        account = self.index.account(account_key)
        if not account or not account["folder"]:
            return
        root = self.root()
        source = AccountSource(
            key=account_key,
            platform=account["platform"],
            url=account["url"],
            mark=account["mark"],
            folder=root.joinpath(account["folder"]),
        )
        with self._account_lock:
            self.index.sync_account(source, root)

    def _run(self) -> None:
        while not self._stop.is_set():
            self._wake.clear()
            if monotonic() - self._last_touch <= self.ACTIVITY_WINDOW:
                try:
                    self.run_once()
                except Exception as error:  # A library hiccup must not end the service.
                    self.status.error = type(error).__name__
                    self.status.phase = "idle"
                    self.log(f"Feed index pass failed: {type(error).__name__}: {error}")
            self._wake.wait(self.PASS_INTERVAL)

    def run_once(self) -> None:
        force = self._force_files
        self._force_files = False
        self.status.error = ""
        self._sync_files(force)
        self._sync_details()
        self.status.phase = "idle"
        self.status.last_finished_at = time()
        self._finished_monotonic = monotonic()

    def _sync_files(self, force: bool) -> None:
        root = self.root()
        self.status.phase = "listing"
        sources = self.sources()
        self.index.retire_accounts({source.key for source in sources})
        self.status.phase = "scanning"
        self.status.done = 0
        self.status.total = len(sources)
        self.status.rescanned = 0
        for source in sources:
            if self._stop.is_set():
                return
            with self._account_lock:
                if self.index.sync_account(source, root, force=force):
                    self.status.rescanned += 1
                    if self.throttle:
                        sleep(self.FOLDER_PAUSE)
            self.status.done += 1

    def _sync_details(self) -> None:
        path = self.detail_database()
        self.status.metadata_available = bool(path and path.is_file())
        if not self.status.metadata_available:
            return
        stat = path.stat()
        stamp = (stat.st_mtime_ns, stat.st_size)
        if stamp == self._detail_stamp:
            return
        self.status.phase = "enriching"
        source = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True, timeout=5)
        source.isolation_level = None
        try:
            source.execute("PRAGMA query_only=ON")
            indexed = self.index.indexed_uids()
            tables: dict[str, list[str]] = {}
            for (name,) in source.execute("SELECT name FROM sqlite_master WHERE type = 'table'"):
                match = _TABLE_UID.match(name)
                if match and match.group(1) in indexed and not _NOT_A_POSTS_TABLE.search(name):
                    tables.setdefault(match.group(1), []).append(name)
            watermarks = self.index.detail_watermarks()
            pending = deque(
                (uid, name) for uid, names in tables.items() for name in names
            )
            self.status.metadata_total = len(pending)
            self.status.metadata_done = 0
            complete = True
            while pending:
                if self._stop.is_set():
                    return
                uid, name = self._next_detail_table(pending)
                try:
                    finished = self._sync_detail_table(source, uid, name, watermarks.get(name, 0))
                except sqlite3.Error as error:
                    # Usually a busy crawl database; the next pass resumes here.
                    self.log(f"Feed metadata read deferred: {type(error).__name__}")
                    complete = False
                    self.status.metadata_done += 1
                    continue
                if finished:
                    self.status.metadata_done += 1
                else:
                    watermarks = self.index.detail_watermarks()
                    pending.append((uid, name))
            if complete:
                self._detail_stamp = stamp
        finally:
            source.close()

    def _next_detail_table(self, pending: deque[tuple[str, str]]) -> tuple[str, str]:
        with self._priority_lock:
            while self._priority:
                wanted = self._priority.popleft()
                matches = [item for item in pending if item[0] == wanted]
                if matches:
                    pending.remove(matches[0])
                    return matches[0]
        return pending.popleft()

    def _priority_waiting(self, uid: str) -> bool:
        with self._priority_lock:
            return any(item != uid for item in self._priority)

    def _sync_detail_table(
        self, source: sqlite3.Connection, uid: str, table: str, watermark: int,
    ) -> bool:
        """Copy new rows in short statements; returns False when preempted."""
        quoted = _quote(table)
        newest = source.execute(f"SELECT MAX(rowid) FROM {quoted}").fetchone()[0] or 0
        if newest <= watermark:
            return True
        columns = ", ".join(_quote(column) for column in _DETAIL_COLUMNS)
        last = watermark
        while last < newest:
            started = monotonic()
            # Each fetch is its own read transaction: the shared lock ends
            # before the next batch, so crawl commits never wait for long.
            rows = source.execute(
                f"SELECT rowid, {columns} FROM {quoted} WHERE rowid > ? ORDER BY rowid LIMIT ?",
                (last, self.DETAIL_BATCH),
            ).fetchall()
            if not rows:
                break
            last = rows[-1][0]
            self.index.apply_detail_rows(uid, [row[1:] for row in rows], table, last)
            if self._stop.is_set():
                return True
            if self.throttle:
                sleep(min(0.5, monotonic() - started))
            if last < newest and self._priority_waiting(uid):
                self.index.finish_detail_table(uid)
                return False
        self.index.finish_detail_table(uid)
        return True
