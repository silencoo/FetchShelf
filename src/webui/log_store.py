from collections import deque
from dataclasses import dataclass
from datetime import datetime
from threading import Lock

__all__ = ["LogStore", "LOG_STORE"]


@dataclass(slots=True)
class LogRecord:
    id: int
    timestamp: str
    level: str
    message: str

    def to_dict(self) -> dict[str, str | int]:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "level": self.level,
            "message": self.message,
        }


class LogStore:
    def __init__(self, maxlen: int = 3000):
        self._records: deque[LogRecord] = deque(maxlen=maxlen)
        self._next_id = 1
        self._lock = Lock()

    @staticmethod
    def _normalize_limit(limit: int, default: int = 200, max_value: int = 1000) -> int:
        try:
            n = int(limit)
        except (TypeError, ValueError):
            return default
        if n <= 0:
            return 0
        return min(n, max_value)

    @staticmethod
    def _normalize_after_id(after_id: int) -> int:
        try:
            return max(int(after_id), 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _normalize_text(message) -> str:
        if isinstance(message, str):
            return message.strip()
        return str(message).strip()

    def add(self, level: str, message) -> int | None:
        text = self._normalize_text(message)
        if not text:
            return None
        with self._lock:
            record = LogRecord(
                id=self._next_id,
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                level=str(level).upper(),
                message=text,
            )
            self._next_id += 1
            self._records.append(record)
            return record.id

    def latest(self, limit: int = 200) -> list[dict[str, str | int]]:
        n = self._normalize_limit(limit)
        if n == 0:
            return []
        with self._lock:
            return [item.to_dict() for item in list(self._records)[-n:]]

    def after(self, after_id: int = 0, limit: int = 200) -> list[dict[str, str | int]]:
        n = self._normalize_limit(limit)
        if n == 0:
            return []
        cursor = self._normalize_after_id(after_id)
        with self._lock:
            items = [item.to_dict() for item in self._records if item.id > cursor]
        return items[:n]

    def list_after(
        self, after_id: int = 0, limit: int = 200
    ) -> list[dict[str, str | int]]:
        return self.after(after_id=after_id, limit=limit)


LOG_STORE = LogStore()
