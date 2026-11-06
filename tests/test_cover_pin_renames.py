from json import dumps, loads
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.manager.cache import Cache
from src.webui.cover_pins import remap_cover_pins


@pytest.mark.parametrize("solo", [False, True])
@pytest.mark.asyncio
async def test_collector_keeps_pin_through_folder_and_nickname_rename(tmp_path, solo):
    folder = tmp_path / "UID1_OldMark_发布作品"
    work = folder / "2026-01-01-OldName" if solo else folder
    work.mkdir(parents=True)
    photo = work / "2026-01-01 10.00.00-图集-OldName-caption_3.jpeg"
    photo.write_bytes(b"fixture")
    settings = SimpleNamespace(path=tmp_path / "settings.json", encode="utf-8")
    pinfile = tmp_path / "account_profile_pins.json"
    old = photo.relative_to(tmp_path).as_posix()
    pinfile.write_text(dumps({"version": 2, "pins": {"account": old, "other": "unrelated.jpg"},
                             "cover_details": {"account": {"path": old, "source": "manual", "second": 2}}}))
    parameter = SimpleNamespace(root=tmp_path, settings=settings,
                                console=SimpleNamespace(error=lambda *a: pytest.fail(str(a))),
                                logger=SimpleNamespace(info=lambda *a: None, warning=lambda *a: pytest.fail(str(a))))
    database = SimpleNamespace(read_mapping_data=AsyncMock(return_value={"mark": "OldMark", "name": "OldName"}),
                               update_mapping_data=AsyncMock())
    cache = Cache(parameter, database, mark=False, name=True)
    await cache.update_cache(solo, "UID", "发布作品", "1", "NewName", "NewMark")
    payload = loads(pinfile.read_text())
    expected = old.replace("OldMark", "NewMark").replace("OldName", "NewName")
    assert payload["pins"] == {"account": expected, "other": "unrelated.jpg"}
    assert payload["cover_details"]["account"] == {"path": expected, "source": "manual", "second": 2}
    assert (tmp_path / expected).is_file()


def test_remap_handles_legacy_pins_without_matching_similar_prefixes(tmp_path):
    path = tmp_path / "pins.json"
    path.write_text(dumps({"a": "old/photo.jpeg", "b": "old-other/photo.jpeg"}))
    remap_cover_pins(path, [("old", "new")])
    assert loads(path.read_text()) == {"a": "new/photo.jpeg", "b": "old-other/photo.jpeg"}
