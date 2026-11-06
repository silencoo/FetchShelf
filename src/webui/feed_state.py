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

MARK_KINDS = frozenset({"like", "save", "follow", "hide"})
_POST_KINDS = frozenset({"like", "save"})

_SCHEMA = """
CREATE TABLE IF NOT EXISTS marks (
    kind TEXT NOT NULL,
    target TEXT NOT NULL,
    account_key TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    PRIMARY KEY (kind, target)
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
        self, kind: str, *, limit: int, offset: int = 0, account_key: str = "",
    ) -> tuple[list[str], int]:
        condition = "kind = ?"
        params: list = [kind]
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

    def counts(self) -> dict[str, int]:
        with self._connect() as connection:
            found = dict(
                connection.execute("SELECT kind, COUNT(*) FROM marks GROUP BY kind").fetchall()
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
