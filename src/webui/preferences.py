"""Small, shared UI preferences; never includes credentials or browsing history."""

import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import RLock
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class BoardPreferences(BaseModel):
    model_config = ConfigDict(extra="forbid")

    viewMode: Literal["avatar", "media", "immersive"] = "avatar"
    columns: int = Field(default=4, ge=1, le=12, strict=True)
    pageSize: Literal[12, 18, 24, 36] = 24
    refreshKind: Literal["auto", "video", "image"] = "auto"
    platform: Literal["douyin", "tiktok"] = "douyin"
    status: Literal[
        "all", "attention", "success", "no_updates", "skipped",
        "legacy_success", "failed", "never", "no_avatar",
    ] = "all"
    sort: Literal[
        "configured", "folder_updated_desc", "latest_desc", "latest_asc", "checked_desc",
    ] = "configured"


class BoardPreferenceStore:
    def __init__(self, path: Path):
        self.path = path
        self.lock = RLock()

    def read(self) -> dict:
        with self.lock:
            if not self.path.exists():
                return {}
            return BoardPreferences.model_validate_json(
                self.path.read_text(encoding="utf-8"),
            ).model_dump(exclude_unset=True)

    def update(self, patch: BoardPreferences, *, initialize: bool = False) -> dict:
        with self.lock:
            current = self.read()
            updates = patch.model_dump(exclude_unset=True)
            if initialize:
                updates = {key: value for key, value in updates.items() if key not in current}
            current.update(updates)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = None
            try:
                with NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent,
                                        prefix=".ui-preferences-", delete=False) as output:
                    temporary = Path(output.name)
                    json.dump(current, output, ensure_ascii=False)
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(temporary, self.path)
            finally:
                if temporary:
                    temporary.unlink(missing_ok=True)
            return current
