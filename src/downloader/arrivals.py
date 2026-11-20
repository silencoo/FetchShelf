"""Per-account notification for primary media that actually reached storage."""
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

SaveObserver = Callable[[str, str, Path, Path], None]
media_saved: ContextVar[SaveObserver | None] = ContextVar("media_saved", default=None)


@contextmanager
def observe_media_saves(observer: SaveObserver) -> Iterator[None]:
    token = media_saved.set(observer)
    try:
        yield
    finally:
        media_saved.reset(token)
