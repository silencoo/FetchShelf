"""Keep saved cover selections attached to media moved by the collector."""

from json import dumps, loads
from pathlib import Path
from tempfile import NamedTemporaryFile


def remap_cover_pins(path: Path, renames: list[tuple[str, str]], encoding="utf-8") -> None:
    if not renames or not path.is_file():
        return
    payload = loads(path.read_text(encoding=encoding))
    pins = payload.get("pins", payload)
    details = payload.get("cover_details", {})
    moved_folders = {old.split("/", 1)[0] for old, _ in renames}
    changed = False
    for key, original in list(pins.items()):
        if not isinstance(original, str):
            continue
        current = original.replace("\\", "/")
        if current.split("/", 1)[0] not in moved_folders:
            continue
        for old, new in renames:
            if current == old or current.startswith(old + "/"):
                current = new + current[len(old):]
        if current == original:
            continue
        pins[key] = current
        detail = details.get(key)
        if isinstance(detail, dict) and detail.get("path") == original:
            detail["path"] = current
        changed = True
    if not changed:
        return
    handle = NamedTemporaryFile(mode="w", encoding=encoding, dir=path.parent, delete=False)
    temporary = Path(handle.name)
    try:
        with handle:
            handle.write(dumps(payload, ensure_ascii=False, indent=2))
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
