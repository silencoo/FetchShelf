from __future__ import annotations

from contextlib import suppress
from datetime import datetime, timezone
from json import dumps, loads
from pathlib import Path
from sqlite3 import Connection, Row, connect
from threading import RLock
from typing import Any, Iterable


DEFAULT_TASK_JOURNAL_NAME = "ui_task_runtime.sqlite3"
SCHEMA_VERSION = 2
ACTIVE_TASK_STATUSES = frozenset(
    {
        "pending",
        "running",
        "pausing",
        "paused",
        "canceling",
    }
)
TERMINAL_ACCOUNT_STATUSES = frozenset({"success", "failed", "skipped"})


def _now_text() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _json(value: Any) -> str:
    return dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def _load_object(value: str, default):
    try:
        parsed = loads(value)
    except (TypeError, ValueError):
        return default
    return parsed if isinstance(parsed, type(default)) else default


class TaskJournal:
    """Small synchronous SQLite journal for Web UI tasks and account checkpoints.

    Writes are deliberately short, guarded by an in-process lock and committed
    before returning. Scraping and network work must never happen while this
    lock is held.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._closed = False
        self._connection = connect(self.path, timeout=30, check_same_thread=False)
        self._connection.row_factory = Row
        self._initialize()
        with suppress(OSError):
            self.path.chmod(0o600)

    @classmethod
    def in_settings_dir(cls, settings_dir: str | Path) -> "TaskJournal":
        return cls(Path(settings_dir).joinpath(DEFAULT_TASK_JOURNAL_NAME))

    @property
    def connection(self) -> Connection:
        if self._closed:
            raise RuntimeError("task journal is closed")
        return self._connection

    def _initialize(self) -> None:
        with self._lock, self.connection:
            self.connection.execute("PRAGMA foreign_keys = ON")
            self.connection.execute("PRAGMA journal_mode = WAL")
            self.connection.execute("PRAGMA synchronous = FULL")
            self.connection.execute("PRAGMA busy_timeout = 30000")
            self.connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS ui_tasks (
                    task_id TEXT PRIMARY KEY,
                    endpoint TEXT NOT NULL,
                    status TEXT NOT NULL,
                    schedule_id TEXT NOT NULL DEFAULT '',
                    task_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS ui_task_accounts (
                    task_id TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    item_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    identity_id TEXT NOT NULL DEFAULT '',
                    reason TEXT NOT NULL DEFAULT '',
                    started_at TEXT NOT NULL DEFAULT '',
                    finished_at TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(task_id, position),
                    FOREIGN KEY(task_id) REFERENCES ui_tasks(task_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS ui_tasks_schedule_status_idx
                    ON ui_tasks(schedule_id, status);
                CREATE INDEX IF NOT EXISTS ui_task_accounts_status_idx
                    ON ui_task_accounts(task_id, status, position);

                CREATE TABLE IF NOT EXISTS ui_account_activity (
                    platform TEXT NOT NULL,
                    url TEXT NOT NULL,
                    sec_uid TEXT NOT NULL DEFAULT '',
                    mark TEXT NOT NULL DEFAULT '',
                    latest_seen_work_at TEXT NOT NULL DEFAULT '',
                    latest_seen_work_id TEXT NOT NULL DEFAULT '',
                    latest_saved_work_at TEXT NOT NULL DEFAULT '',
                    latest_saved_work_id TEXT NOT NULL DEFAULT '',
                    last_checked_at TEXT NOT NULL DEFAULT '',
                    last_success_at TEXT NOT NULL DEFAULT '',
                    last_failure_at TEXT NOT NULL DEFAULT '',
                    last_status TEXT NOT NULL DEFAULT 'never',
                    last_error TEXT NOT NULL DEFAULT '',
                    last_item_count INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(platform, url)
                );

                CREATE INDEX IF NOT EXISTS ui_account_activity_platform_status_idx
                    ON ui_account_activity(platform, last_status, last_checked_at);
                """
            )
            self.connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._connection.close()
            self._closed = True

    def __enter__(self) -> "TaskJournal":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    @staticmethod
    def _serializable_task(task: dict) -> dict:
        return {
            key: value
            for key, value in task.items()
            if not str(key).startswith("_")
        }

    def save_task(self, task: dict) -> None:
        public = self._serializable_task(task)
        task_id = str(public.get("task_id") or "").strip()
        if not task_id:
            return
        now = str(public.get("updated_at") or _now_text())
        created_at = str(public.get("created_at") or now)
        with self._lock, self.connection:
            self.connection.execute(
                """
                INSERT INTO ui_tasks (
                    task_id, endpoint, status, schedule_id, task_json,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    endpoint = excluded.endpoint,
                    status = excluded.status,
                    schedule_id = excluded.schedule_id,
                    task_json = excluded.task_json,
                    updated_at = excluded.updated_at
                """,
                (
                    task_id,
                    str(public.get("endpoint") or ""),
                    str(public.get("status") or "pending"),
                    str(public.get("schedule_id") or ""),
                    _json(public),
                    created_at,
                    now,
                ),
            )

    def load_tasks(self, limit: int = 2000) -> list[dict]:
        size = max(1, min(int(limit or 1), 10000))
        with self._lock:
            rows = self.connection.execute(
                """
                SELECT task_json
                FROM ui_tasks
                ORDER BY CAST(SUBSTR(task_id, 2) AS INTEGER) DESC
                LIMIT ?
                """,
                (size,),
            ).fetchall()
        return [
            task
            for row in rows
            if (task := _load_object(row["task_json"], {}))
        ]

    def recover_interrupted(self) -> None:
        """Return process-bound work to a resumable state after a restart."""

        now = _now_text()
        with self._lock, self.connection:
            rows = self.connection.execute(
                """
                SELECT task_id, task_json
                FROM ui_tasks
                WHERE status IN ('running', 'pausing', 'canceling')
                """
            ).fetchall()
            for row in rows:
                task = _load_object(row["task_json"], {})
                if not task:
                    continue
                task["status"] = "pending"
                task["worker"] = None
                task["finished_at"] = None
                task["updated_at"] = now
                task["message"] = "服务重启后已恢复，等待继续执行"
                task["recovered_after_restart"] = True
                self.connection.execute(
                    """
                    UPDATE ui_tasks
                    SET status = 'pending', task_json = ?, updated_at = ?
                    WHERE task_id = ?
                    """,
                    (_json(task), now, row["task_id"]),
                )
            self.connection.execute(
                """
                UPDATE ui_task_accounts
                SET status = 'pending', started_at = '', finished_at = '',
                    updated_at = ?
                WHERE status = 'running'
                """,
                (now,),
            )

    def prepare_accounts(
        self,
        task_id: str,
        items: Iterable[dict],
    ) -> list[dict]:
        """Create a stable account snapshot once, then always return that snapshot."""

        with self._lock, self.connection:
            existing = self.connection.execute(
                """
                SELECT position, item_json, status, attempts, identity_id,
                       reason, started_at, finished_at, updated_at
                FROM ui_task_accounts
                WHERE task_id = ?
                ORDER BY position
                """,
                (task_id,),
            ).fetchall()
            if not existing:
                now = _now_text()
                self.connection.executemany(
                    """
                    INSERT INTO ui_task_accounts (
                        task_id, position, item_json, status, attempts,
                        identity_id, reason, started_at, finished_at, updated_at
                    ) VALUES (?, ?, ?, 'pending', 0, '', '', '', '', ?)
                    """,
                    [
                        (task_id, position, _json(dict(item)), now)
                        for position, item in enumerate(items, start=1)
                    ],
                )
                existing = self.connection.execute(
                    """
                    SELECT position, item_json, status, attempts, identity_id,
                           reason, started_at, finished_at, updated_at
                    FROM ui_task_accounts
                    WHERE task_id = ?
                    ORDER BY position
                    """,
                    (task_id,),
                ).fetchall()
        return [self._account_row(row) for row in existing]

    @staticmethod
    def _account_row(row: Row) -> dict:
        return {
            "position": int(row["position"]),
            "item": _load_object(row["item_json"], {}),
            "status": str(row["status"]),
            "attempts": int(row["attempts"]),
            "identity_id": str(row["identity_id"]),
            "reason": str(row["reason"]),
            "started_at": str(row["started_at"]),
            "finished_at": str(row["finished_at"]),
            "updated_at": str(row["updated_at"]),
        }

    def list_accounts(
        self,
        task_id: str,
        *,
        status: str = "",
        limit: int = 1000,
        offset: int = 0,
    ) -> list[dict]:
        params: list[Any] = [task_id]
        where = "task_id = ?"
        if status:
            where += " AND status = ?"
            params.append(status)
        params.extend(
            [
                max(1, min(int(limit or 1), 5000)),
                max(0, int(offset or 0)),
            ]
        )
        with self._lock:
            rows = self.connection.execute(
                f"""
                SELECT position, item_json, status, attempts, identity_id,
                       reason, started_at, finished_at, updated_at
                FROM ui_task_accounts
                WHERE {where}
                ORDER BY position
                LIMIT ? OFFSET ?
                """,
                tuple(params),
            ).fetchall()
        return [self._account_row(row) for row in rows]

    def mark_account_running(
        self,
        task_id: str,
        position: int,
        *,
        identity_id: str = "",
    ) -> None:
        now = _now_text()
        with self._lock, self.connection:
            self.connection.execute(
                """
                UPDATE ui_task_accounts
                SET status = 'running', attempts = attempts + 1,
                    identity_id = ?, reason = '', started_at = ?,
                    finished_at = '', updated_at = ?
                WHERE task_id = ? AND position = ?
                """,
                (identity_id, now, now, task_id, int(position)),
            )

    def mark_account_finished(
        self,
        task_id: str,
        position: int,
        *,
        status: str,
        identity_id: str = "",
        reason: str = "",
    ) -> None:
        normalized_status = (
            status if status in TERMINAL_ACCOUNT_STATUSES else "failed"
        )
        now = _now_text()
        with self._lock, self.connection:
            self.connection.execute(
                """
                UPDATE ui_task_accounts
                SET status = ?, identity_id = ?, reason = ?,
                    finished_at = ?, updated_at = ?
                WHERE task_id = ? AND position = ?
                """,
                (
                    normalized_status,
                    identity_id,
                    reason,
                    now,
                    now,
                    task_id,
                    int(position),
                ),
            )

    def reset_running_accounts(self, task_id: str) -> None:
        now = _now_text()
        with self._lock, self.connection:
            self.connection.execute(
                """
                UPDATE ui_task_accounts
                SET status = 'pending', started_at = '', finished_at = '',
                    updated_at = ?
                WHERE task_id = ? AND status = 'running'
                """,
                (now, task_id),
            )

    def account_summary(self, task_id: str) -> dict:
        with self._lock:
            rows = self.connection.execute(
                """
                SELECT status, COUNT(*) AS count
                FROM ui_task_accounts
                WHERE task_id = ?
                GROUP BY status
                """,
                (task_id,),
            ).fetchall()
        counts = {str(row["status"]): int(row["count"]) for row in rows}
        total = sum(counts.values())
        return {
            "total": total,
            "pending": counts.get("pending", 0),
            "running": counts.get("running", 0),
            "success": counts.get("success", 0),
            "failed": counts.get("failed", 0),
            "skipped": counts.get("skipped", 0),
        }

    def failed_items(self, task_id: str) -> list[dict]:
        return [
            account["item"]
            for account in self.list_accounts(
                task_id,
                status="failed",
                limit=5000,
            )
        ]

    @staticmethod
    def _activity_row(row: Row) -> dict:
        return {
            "platform": str(row["platform"]),
            "url": str(row["url"]),
            "sec_uid": str(row["sec_uid"]),
            "mark": str(row["mark"]),
            "latest_seen_work_at": str(row["latest_seen_work_at"]),
            "latest_seen_work_id": str(row["latest_seen_work_id"]),
            "latest_saved_work_at": str(row["latest_saved_work_at"]),
            "latest_saved_work_id": str(row["latest_saved_work_id"]),
            "last_checked_at": str(row["last_checked_at"]),
            "last_success_at": str(row["last_success_at"]),
            "last_failure_at": str(row["last_failure_at"]),
            "last_status": str(row["last_status"]),
            "last_error": str(row["last_error"]),
            "last_item_count": int(row["last_item_count"]),
            "updated_at": str(row["updated_at"]),
        }

    def save_account_activity(
        self,
        *,
        platform: str,
        url: str,
        sec_uid: str = "",
        mark: str = "",
        latest_seen_work_at: str = "",
        latest_seen_work_id: str = "",
        latest_saved_work_at: str = "",
        latest_saved_work_id: str = "",
        status: str,
        error: str = "",
        item_count: int = 0,
    ) -> dict:
        normalized_platform = str(platform or "").strip().lower()
        normalized_url = str(url or "").strip()
        if normalized_platform not in {"douyin", "tiktok"}:
            raise ValueError("platform must be douyin or tiktok")
        if not normalized_url:
            raise ValueError("url is required")
        normalized_status = status if status in {"success", "failed"} else "failed"
        now = _now_text()
        success_at = now if normalized_status == "success" else ""
        failure_at = now if normalized_status == "failed" else ""
        with self._lock, self.connection:
            self.connection.execute(
                """
                INSERT INTO ui_account_activity (
                    platform, url, sec_uid, mark,
                    latest_seen_work_at, latest_seen_work_id,
                    latest_saved_work_at, latest_saved_work_id,
                    last_checked_at, last_success_at, last_failure_at,
                    last_status, last_error, last_item_count, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(platform, url) DO UPDATE SET
                    sec_uid = CASE
                        WHEN excluded.sec_uid != '' THEN excluded.sec_uid
                        ELSE ui_account_activity.sec_uid
                    END,
                    mark = CASE
                        WHEN excluded.mark != '' THEN excluded.mark
                        ELSE ui_account_activity.mark
                    END,
                    latest_seen_work_at = CASE
                        WHEN excluded.latest_seen_work_at > ui_account_activity.latest_seen_work_at
                            THEN excluded.latest_seen_work_at
                        ELSE ui_account_activity.latest_seen_work_at
                    END,
                    latest_seen_work_id = CASE
                        WHEN excluded.latest_seen_work_at > ui_account_activity.latest_seen_work_at
                            THEN excluded.latest_seen_work_id
                        WHEN ui_account_activity.latest_seen_work_id = ''
                            THEN excluded.latest_seen_work_id
                        ELSE ui_account_activity.latest_seen_work_id
                    END,
                    latest_saved_work_at = CASE
                        WHEN excluded.latest_saved_work_at > ui_account_activity.latest_saved_work_at
                            THEN excluded.latest_saved_work_at
                        ELSE ui_account_activity.latest_saved_work_at
                    END,
                    latest_saved_work_id = CASE
                        WHEN excluded.latest_saved_work_at > ui_account_activity.latest_saved_work_at
                            THEN excluded.latest_saved_work_id
                        WHEN ui_account_activity.latest_saved_work_id = ''
                            THEN excluded.latest_saved_work_id
                        ELSE ui_account_activity.latest_saved_work_id
                    END,
                    last_checked_at = excluded.last_checked_at,
                    last_success_at = CASE
                        WHEN excluded.last_success_at != '' THEN excluded.last_success_at
                        ELSE ui_account_activity.last_success_at
                    END,
                    last_failure_at = CASE
                        WHEN excluded.last_failure_at != '' THEN excluded.last_failure_at
                        ELSE ui_account_activity.last_failure_at
                    END,
                    last_status = excluded.last_status,
                    last_error = excluded.last_error,
                    last_item_count = excluded.last_item_count,
                    updated_at = excluded.updated_at
                """,
                (
                    normalized_platform,
                    normalized_url,
                    str(sec_uid or "").strip(),
                    str(mark or "").strip(),
                    str(latest_seen_work_at or "").strip(),
                    str(latest_seen_work_id or "").strip(),
                    str(latest_saved_work_at or "").strip(),
                    str(latest_saved_work_id or "").strip(),
                    now,
                    success_at,
                    failure_at,
                    normalized_status,
                    str(error or "").strip(),
                    max(0, int(item_count or 0)),
                    now,
                ),
            )
            row = self.connection.execute(
                """
                SELECT *
                FROM ui_account_activity
                WHERE platform = ? AND url = ?
                """,
                (normalized_platform, normalized_url),
            ).fetchone()
        return self._activity_row(row)

    def list_account_activity(self, platform: str) -> list[dict]:
        normalized_platform = str(platform or "").strip().lower()
        with self._lock:
            rows = self.connection.execute(
                """
                SELECT *
                FROM ui_account_activity
                WHERE platform = ?
                ORDER BY last_checked_at DESC, url
                """,
                (normalized_platform,),
            ).fetchall()
        return [self._activity_row(row) for row in rows]

    def has_active_schedule_task(self, schedule_id: str) -> bool:
        if not schedule_id:
            return False
        placeholders = ",".join("?" for _ in ACTIVE_TASK_STATUSES)
        with self._lock:
            row = self.connection.execute(
                f"""
                SELECT 1
                FROM ui_tasks
                WHERE schedule_id = ? AND status IN ({placeholders})
                LIMIT 1
                """,
                (schedule_id, *sorted(ACTIVE_TASK_STATUSES)),
            ).fetchone()
        return row is not None
