"""Explicit local media libraries, isolated from scraper targets and credentials."""
import json
from pathlib import Path
from .feed_index import AccountSource

PLATFORMS = {"tiktok", "kuaishou", "rednote", "weibo", "douyin"}


def load_import_sources(manifest: Path, root: Path) -> list[AccountSource]:
    rows = json.loads(manifest.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("Media imports must be a list")
    root = root.resolve()
    result = []
    keys = set()
    for row in rows:
        platform = row["platform"]
        identifier = str(row["id"]).strip()
        if platform not in PLATFORMS or not identifier or "/" in identifier:
            raise ValueError("Invalid imported account identity")
        relative = Path(row["folder"])
        folder = (root / relative).resolve()
        if relative.is_absolute() or folder == root or not folder.is_relative_to(root):
            raise ValueError("Imported folder must be inside the media root")
        url = f"local://{platform}/{identifier}"
        key = f"{platform}::{url}"
        if key in keys:
            raise ValueError("Duplicate imported account identity")
        keys.add(key)
        result.append(AccountSource(key, platform, url, str(row.get("name") or identifier), folder))
    return result
