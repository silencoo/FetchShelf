from datetime import datetime
from pathlib import Path
from typing import Literal

ScopeType = Literal["project", "download"]

IMAGE_SUFFIXES = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".gif",
    ".bmp",
    ".avif",
    ".heic",
}
VIDEO_SUFFIXES = {
    ".mp4",
    ".m4v",
    ".mov",
    ".mkv",
    ".avi",
    ".flv",
    ".webm",
}
AUDIO_SUFFIXES = {
    ".mp3",
    ".m4a",
    ".wav",
    ".ogg",
    ".aac",
    ".flac",
}

__all__ = [
    "ScopeType",
    "resolve_within_root",
    "relative_path",
    "serialize_entry",
]


def resolve_within_root(root: Path, current_path: str | None = None) -> Path:
    root_path = root.expanduser().resolve()
    normalized = (current_path or "").replace("\\", "/").strip().strip("/")
    target = root_path.joinpath(normalized).resolve()
    if target != root_path and root_path not in target.parents:
        raise ValueError("path_out_of_scope")
    return target


def relative_path(root: Path, target: Path) -> str:
    root_path = root.expanduser().resolve()
    target_path = target.expanduser().resolve()
    if target_path == root_path:
        return ""
    return target_path.relative_to(root_path).as_posix()


def _entry_kind(path: Path) -> str:
    if path.is_dir():
        return "dir"
    suffix = path.suffix.lower()
    if suffix in IMAGE_SUFFIXES:
        return "image"
    if suffix in VIDEO_SUFFIXES:
        return "video"
    if suffix in AUDIO_SUFFIXES:
        return "audio"
    if suffix in {".txt", ".json", ".md", ".csv", ".log"}:
        return "text"
    return "file"


def _modified(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds")


def serialize_entry(root: Path, path: Path) -> dict:
    is_dir = path.is_dir()
    return {
        "name": path.name,
        "path": relative_path(root, path),
        "kind": _entry_kind(path),
        "is_dir": is_dir,
        "size": None if is_dir else path.stat().st_size,
        "modified_at": _modified(path),
    }
