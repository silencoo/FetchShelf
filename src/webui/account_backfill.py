from typing import Any, Callable

__all__ = ["attach_settings_index_by_url"]


def _row_url(row: Any) -> str:
    if isinstance(row, dict):
        return str(row.get("url", "") or "")
    return str(getattr(row, "url", "") or "")


def attach_settings_index_by_url(
    items: list[dict],
    settings_rows: list[Any],
    normalizer: Callable[[Any], str] | None = None,
) -> None:
    normalize = normalizer or (lambda value: str(value or "").strip())
    index_by_url: dict[str, int] = {}
    for index, row in enumerate(settings_rows):
        url = normalize(_row_url(row))
        if url and url not in index_by_url:
            index_by_url[url] = index
    for item in items:
        if not isinstance(item, dict):
            continue
        url = normalize(item.get("url", ""))
        row_index = index_by_url.get(url)
        if row_index is not None:
            item["_settings_index"] = row_index
