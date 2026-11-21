"""Durable personal marks for the immersive feed: likes, saves, follows, hides.

Kept apart from the rebuildable index so clearing that cache cannot lose them.
Marks never touch the source platform. They contain no credentials and no
watch history.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from json import dumps
from pathlib import Path
import sqlite3
from threading import Lock
from time import time

MARK_KINDS = frozenset({"like", "save", "follow", "hide", "block"})
_POST_KINDS = frozenset({"like", "save"})

_SCHEMA = """
CREATE TABLE IF NOT EXISTS marks (
    kind TEXT NOT NULL,
    target TEXT NOT NULL,
    account_key TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    PRIMARY KEY (kind, target)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS arrival_runs (
    task_id TEXT PRIMARY KEY,
    partial INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS arrivals (
    id INTEGER PRIMARY KEY,
    platform TEXT NOT NULL,
    work_id TEXT NOT NULL,
    account_key TEXT NOT NULL,
    post_key TEXT NOT NULL,
    kind TEXT NOT NULL,
    saved_at INTEGER NOT NULL,
    task_id TEXT NOT NULL,
    name TEXT NOT NULL,
    folder TEXT NOT NULL,
    files TEXT NOT NULL,
    caption TEXT NOT NULL,
    published_ts INTEGER NOT NULL,
    UNIQUE(platform, work_id),
    UNIQUE(post_key)
);
CREATE INDEX IF NOT EXISTS arrivals_task ON arrivals(task_id, id);
CREATE INDEX IF NOT EXISTS arrivals_week ON arrivals(saved_at);
CREATE TABLE IF NOT EXISTS preferences (
    key TEXT PRIMARY KEY,
    value INTEGER NOT NULL CHECK(value IN (0, 1))
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS marks_recent ON marks(kind, created_at);
CREATE INDEX IF NOT EXISTS marks_account ON marks(kind, account_key, created_at);
"""


class FeedState:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._prepared = False
        self._prepare_lock = Lock()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        if not self._prepared:
            with self._prepare_lock:
                if not self._prepared:
                    self.path.parent.mkdir(parents=True, exist_ok=True)
                    connection = sqlite3.connect(self.path, timeout=10, isolation_level=None)
                    try:
                        connection.execute("PRAGMA journal_mode=WAL")
                        connection.executescript(_SCHEMA)
                    finally:
                        connection.close()
                    self._prepared = True
        connection = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        try:
            yield connection
        finally:
            connection.close()

    def start_arrival_run(self, task_id: str, partial: bool) -> None:
        with self._connect() as connection:
            connection.execute("INSERT OR IGNORE INTO arrival_runs VALUES (?, ?)", (task_id, partial))

    def record_arrival(self, *, platform: str, work_id: str, account_key: str, post_key: str,
                       kind: str, task_id: str, name: str, folder: str, file: str,
                       caption: str, published_ts: int | None) -> None:
        # Concurrent slides and resumed tasks attach files to the original receipt.
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO arrivals(platform, work_id, account_key, post_key, kind, saved_at, task_id, "
                "name, folder, files, caption, published_ts) "
                "VALUES (?, ?, ?, CASE WHEN EXISTS(SELECT 1 FROM arrivals WHERE post_key=? AND "
                "(platform<>? OR work_id<>?)) THEN ? ELSE ? END, ?, ?, ?, ?, ?, json_array(?), ?, ?) "
                "ON CONFLICT(platform, work_id) DO UPDATE SET files=json_insert(arrivals.files, '$[#]', ?) "
                "WHERE arrivals.folder=excluded.folder AND arrivals.post_key=excluded.post_key "
                "AND NOT EXISTS (SELECT 1 FROM json_each(arrivals.files) WHERE value=?)",
                (platform, work_id, account_key, post_key, platform, work_id, f"arrival:{platform}:{work_id}",
                 post_key, kind, int(time()), task_id, name, folder,
                 file, caption, published_ts or 0, file, file),
            )

    def arrival_page(self, *, task_id: str, platform: str, hidden: list[str], cursor: dict,
                     limit: int) -> tuple[list[dict], dict | None, int | None]:
        if task_id:
            clauses, params = ["task_id=?"], [task_id]
        else:
            clauses, params = ["saved_at>=?"], [int(time()) - 7 * 86400]
        if platform:
            clauses.append("platform=?")
            params.append(platform)
        if hidden:
            clauses.append("account_key NOT IN (SELECT value FROM json_each(?))")
            params.append(dumps(hidden))
        if isinstance(cursor.get("before"), int):
            clauses.append("id<?")
            params.append(cursor["before"])
        where = " AND ".join(clauses)
        with self._connect() as connection:
            connection.row_factory = sqlite3.Row
            total = None
            if task_id and not cursor:
                total = connection.execute(f"SELECT COUNT(*) FROM arrivals WHERE {where}", params).fetchone()[0]
            rows = connection.execute(f"SELECT * FROM arrivals WHERE {where} ORDER BY id DESC LIMIT ?",
                                      [*params, limit + 1]).fetchall()
        following = {"before": rows[limit - 1]["id"]} if len(rows) > limit else None
        return [dict(row) for row in rows[:limit]], following, total

    def arrivals_by_keys(self, keys: list[str]) -> list[dict]:
        with self._connect() as connection:
            connection.row_factory = sqlite3.Row
            return [dict(row) for row in connection.execute(
                "SELECT * FROM arrivals WHERE post_key IN (SELECT value FROM json_each(?))", (dumps(keys),)
            )]

    def arrival_summary(self, task_id: str) -> dict:
        with self._connect() as connection:
            run = connection.execute("SELECT partial FROM arrival_runs WHERE task_id=?", (task_id,)).fetchone()
            counts = dict(connection.execute(
                "SELECT kind, COUNT(*) FROM arrivals WHERE task_id=? GROUP BY kind", (task_id,)
            ))
        return {"tracked": run is not None, "partial": bool(run and run[0]), "total": sum(counts.values()),
                "videos": counts.get("video", 0), "images": counts.get("images", 0), "live": counts.get("live", 0)}

    def preferences(self) -> dict:
        with self._connect() as connection:
            return {key: bool(value) for key, value in connection.execute("SELECT key, value FROM preferences")}

    def update_preferences(self, values: dict, *, initialize: bool = False) -> dict:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                for key, value in values.items():
                    if key not in {"sound", "autoNext", "showPauseIcon", "pinchZoom"} or type(value) is not bool:
                        raise ValueError("invalid feed preference")
                    sql = "INSERT OR IGNORE INTO preferences VALUES (?, ?)" if initialize else (
                        "INSERT INTO preferences VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value")
                    connection.execute(sql, (key, int(value)))
                result = {key: bool(value) for key, value in connection.execute("SELECT key, value FROM preferences")}
                connection.commit()
                return result
            except BaseException:
                connection.rollback()
                raise

    def set_mark(self, kind: str, target: str, on: bool, account_key: str = "") -> None:
        if kind not in MARK_KINDS:
            raise ValueError("unknown mark kind")
        with self._connect() as connection:
            if on:
                # A repeated tap keeps the original time, so lists stay stable.
                connection.execute(
                    "INSERT OR IGNORE INTO marks (kind, target, account_key, created_at) "
                    "VALUES (?, ?, ?, ?)",
                    (kind, target, account_key, time()),
                )
            else:
                connection.execute(
                    "DELETE FROM marks WHERE kind = ? AND target = ?", (kind, target),
                )

    def clear(self, kind: str) -> int:
        with self._connect() as connection:
            return connection.execute("DELETE FROM marks WHERE kind = ?", (kind,)).rowcount

    def marked(self, kind: str, targets: list[str]) -> set[str]:
        if not targets:
            return set()
        with self._connect() as connection:
            return {
                row[0]
                for row in connection.execute(
                    "SELECT target FROM marks WHERE kind = ? "
                    "AND target IN (SELECT value FROM json_each(?))",
                    (kind, dumps(targets)),
                )
            }

    def targets(self, kind: str) -> list[str]:
        with self._connect() as connection:
            return [
                row[0]
                for row in connection.execute(
                    "SELECT target FROM marks WHERE kind = ? ORDER BY created_at DESC", (kind,),
                )
            ]

    def page(
        self, kind: str, *, limit: int, offset: int = 0, account_key: str = "", platform: str = "",
    ) -> tuple[list[str], int]:
        condition = "kind = ?"
        params: list = [kind]
        if platform:
            condition += " AND account_key LIKE ?"
            params.append(platform + "::%")
        if account_key:
            condition += " AND account_key = ?"
            params.append(account_key)
        with self._connect() as connection:
            total = connection.execute(
                f"SELECT COUNT(*) FROM marks WHERE {condition}", params,
            ).fetchone()[0]
            rows = connection.execute(
                f"SELECT target FROM marks WHERE {condition} "
                "ORDER BY created_at DESC LIMIT ? OFFSET ?",
                [*params, limit, offset],
            ).fetchall()
        return [row[0] for row in rows], total

    def liked_accounts(self, *, platform: str, limit: int, offset: int) -> tuple[list[dict], int | None]:
        condition = "kind='like' AND account_key<>''"
        params = []
        if platform:
            condition += " AND account_key LIKE ?"
            params.append(platform + "::%")
        with self._connect() as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                f"""
                WITH accounts AS (
                    SELECT account_key, COUNT(*) AS count, MAX(created_at) AS latest_like
                    FROM marks WHERE {condition}
                    GROUP BY account_key
                    ORDER BY latest_like DESC, account_key LIMIT ? OFFSET ?
                )
                SELECT account_key, count, (
                    SELECT json_group_array(target) FROM (
                        SELECT target FROM marks
                        WHERE kind='like' AND account_key=accounts.account_key
                        ORDER BY created_at DESC, target LIMIT 3
                    )
                ) AS previews
                FROM accounts ORDER BY latest_like DESC, account_key
                """,
                [*params, limit + 1, offset],
            ).fetchall()
        return [dict(row) for row in rows[:limit]], offset + limit if len(rows) > limit else None

    def counts(self, platform: str = "") -> dict[str, int]:
        with self._connect() as connection:
            found = dict(
                connection.execute("SELECT kind, COUNT(*) FROM marks WHERE ? = '' OR "
                    "(CASE WHEN kind IN ('follow', 'hide', 'block') THEN target ELSE account_key END) LIKE ? GROUP BY kind",
                    (platform, platform + "::%"),
                ).fetchall()
            )
        return {kind: int(found.get(kind, 0)) for kind in sorted(MARK_KINDS)}

    def affinity_accounts(self, limit: int = 200) -> list[str]:
        """Accounts the viewer responded to, most recent first."""
        placeholders = ",".join("?" for _ in _POST_KINDS)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT account FROM (
                    SELECT target AS account, created_at FROM marks WHERE kind = 'follow'
                    UNION ALL
                    SELECT account_key AS account, created_at FROM marks
                    WHERE kind IN ({placeholders}) AND account_key != ''
                )
                GROUP BY account ORDER BY MAX(created_at) DESC LIMIT ?
                """,
                [*sorted(_POST_KINDS), limit],
            ).fetchall()
        return [row[0] for row in rows]
