import asyncio
import json
import sqlite3

import pytest

from src.storage.manager import RecordManager
from src.storage.sqlite import SQLLogger

TABLE = "UID9_Ann_发布作品"


def logger(root, name=TABLE, old=None):
    return SQLLogger(root, name=name, old=old, **RecordManager.LoggerParams["detail"])


def values(**changes):
    record = dict.fromkeys(RecordManager.detail_name, "")
    record.update({
        "作品ID": "111", "作品描述": "original", "作品话题": "tag",
        "采集时间": "2026-11-01 10:00:00", "发布时间": "2026-01-01 10:00:00",
        "作品类型": "视频", "视频URI": "stable-media-id", "点赞数量": 10,
    })
    record.update(changes)
    return [record[k] for k in RecordManager.detail_name]


def query(root, sql):
    with sqlite3.connect(root / "DetailData.db") as db:
        return db.execute(sql).fetchall()


@pytest.mark.asyncio
async def test_refresh_then_content_change(tmp_path):
    async with logger(tmp_path) as log:
        await log.save(values())
        await log.save(values(**{"采集时间": "2026-11-02 10:00:00", "点赞数量": 20,
                                  "下载地址": "https://cdn/new-signature"}))
        await log.save(values(**{"采集时间": "2026-11-03 10:00:00", "作品描述": "edited", "点赞数量": 30}))
    assert query(tmp_path, f'SELECT count(*),作品描述,点赞数量,_first_seen_at,_last_seen_at FROM "{TABLE}"') == [
        (1, "edited", 30, "2026-11-01 10:00:00", "2026-11-03 10:00:00")]
    history = query(tmp_path, "SELECT changed_fields,metadata FROM _post_metadata_history")
    assert len(history) == 1
    assert json.loads(history[0][0]) == ["作品描述"]
    assert json.loads(history[0][1])["点赞数量"] == 20


@pytest.mark.asyncio
async def test_missing_and_stale_data_do_not_erase_content(tmp_path):
    async with logger(tmp_path) as log:
        await log.save(values())
        await log.save(values(**{"采集时间": "2026-11-02 10:00:00", "作品描述": "",
                                  "作品话题": None, "点赞数量": -1, "发布时间": "2026-11-02 10:00:00"}))
        await log.save(values(**{"采集时间": "2026-10-01 10:00:00", "作品描述": "stale"}))
        await log.save(values(**{"作品ID": ""}))
    assert query(tmp_path, f'SELECT 作品描述,作品话题,点赞数量,发布时间 FROM "{TABLE}"') == [
        ("original", "tag", 10, "2026-01-01 10:00:00")]
    assert query(tmp_path, "SELECT count(*) FROM _post_metadata_history") == [(0,)]


@pytest.mark.asyncio
async def test_migration_preserves_legacy_and_reopens(tmp_path):
    with sqlite3.connect(tmp_path / "DetailData.db") as db:
        cols = ",".join(f'"{n}" {t}' for n, t in zip(RecordManager.detail_name, RecordManager.detail_type))
        db.execute(f'CREATE TABLE "{TABLE}" ({cols})')
        marks = ",".join("?" for _ in RecordManager.detail_name)
        for record in [values(), values(**{"采集时间": "2026-11-02 10:00:00", "点赞数量": 20, "作品描述": ""})]:
            db.execute(f'INSERT INTO "{TABLE}" VALUES ({marks})', record)
    async with logger(tmp_path) as log:
        assert query(tmp_path, f'SELECT 作品描述 FROM "{TABLE}"') == [("original",)]
        await log.save(values(**{"采集时间": "2026-11-03 10:00:00", "点赞数量": 30}))
    async with logger(tmp_path) as log:
        await log.save(values(**{"采集时间": "2026-11-04 10:00:00", "点赞数量": 40}))
    assert query(tmp_path, f'SELECT count(*),点赞数量,_revision,_first_seen_at FROM "{TABLE}"') == [
        (1, 40, 6, "2026-11-01 10:00:00")]
    archives = query(tmp_path, "SELECT name FROM sqlite_master WHERE name LIKE '_legacy_posts_%'")
    assert len(archives) == 1
    assert query(tmp_path, f'SELECT count(*) FROM "{archives[0][0]}"') == [(2,)]


@pytest.mark.asyncio
async def test_rename_keeps_revision_and_history(tmp_path):
    async with logger(tmp_path) as log:
        await log.save(values())
        await log.save(values(**{"作品描述": "edit"}))
    name = "UID9_New_发布作品"
    async with logger(tmp_path, name=name, old="Ann_发布作品") as log:
        await log.save(values(**{"作品描述": "edit"}))
    assert query(tmp_path, f'SELECT count(*),_revision FROM "{name}"') == [(1, 3)]
    assert query(tmp_path, "SELECT table_name FROM _post_metadata_history") == [(name,)]


@pytest.mark.asyncio
async def test_separate_writers_do_not_duplicate(tmp_path):
    async def write():
        async with logger(tmp_path) as log:
            await log.save(values())
    await asyncio.gather(write(), write())
    assert query(tmp_path, f'SELECT count(*) FROM "{TABLE}"') == [(1,)]


@pytest.mark.asyncio
async def test_snapshot_and_update_roll_back_together(tmp_path):
    async with logger(tmp_path) as log:
        await log.save(values())
        await log.db.execute(f"""CREATE TRIGGER fail_update BEFORE UPDATE ON "{TABLE}"
            BEGIN SELECT RAISE(ABORT, 'fixture failure'); END""")
        await log.db.commit()
        with pytest.raises(sqlite3.IntegrityError):
            await log.save(values(**{"作品描述": "edit"}))
    assert query(tmp_path, "SELECT count(*) FROM _post_metadata_history") == [(0,)]
    assert query(tmp_path, f'SELECT 作品描述,_revision FROM "{TABLE}"') == [("original", 1)]


@pytest.mark.asyncio
async def test_feed_sees_updates_without_new_posts(tmp_path):
    from test_feed_index import touch, source, worker_for
    from src.webui.feed_index import FeedIndex

    root = tmp_path / "media"
    touch(root / TABLE, "2026-01-01 10.00.00-视频-Ann-original.mp4")
    data = root / "Data"
    data.mkdir()
    async with logger(data) as log:
        await log.save(values())
    index = FeedIndex(tmp_path / "feed.sqlite3")
    worker = worker_for(index, root, [source(root, "Ann", TABLE)])
    worker.run_once()
    key = "9:20260101100000:v"
    assert index.post(key)["likes"] == 10
    async with logger(data) as log:
        await log.save(values(**{"采集时间": "2026-11-02 10:00:00", "作品描述": "edited", "点赞数量": 50}))
    worker.run_once()
    assert index.post(key)["full_caption"] == "edited"
    assert index.post(key)["likes"] == 50
    assert index.counts()["posts"] == 1
    assert index.detail_watermarks()[TABLE] == 2


@pytest.mark.asyncio
async def test_existing_feed_watermark_survives_migration(tmp_path):
    from test_feed_index import touch, source, worker_for, detail_database
    from src.webui.feed_index import FeedIndex

    root = tmp_path / "media"
    touch(root / TABLE, "2026-01-01 10.00.00-视频-Ann-original.mp4")
    base = dict(zip(RecordManager.detail_name, values()))
    detail_database(root, TABLE, [base, {**base, "作品描述": "", "点赞数量": 20}])
    index = FeedIndex(tmp_path / "feed.sqlite3")
    worker = worker_for(index, root, [source(root, "Ann", TABLE)])
    worker.run_once()
    assert index.detail_watermarks()[TABLE] == 2
    async with logger(root / "Data"):
        pass  # Merely opening migrates; no new scrape is needed to refresh.
    worker.run_once()
    post = index.post("9:20260101100000:v")
    assert post["full_caption"] == "original"
    assert post["likes"] == 20
    assert index.counts()["posts"] == 1
    assert index.detail_watermarks()[TABLE] > 2


@pytest.mark.asyncio
async def test_non_post_records_keep_existing_behavior(tmp_path):
    async with SQLLogger(tmp_path, **RecordManager.LoggerParams["user"]) as log:
        row = ["" for _ in RecordManager.user_name]
        await log.save(row.copy())
        await log.save(row.copy())
    with sqlite3.connect(tmp_path / "UserData.db") as db:
        assert db.execute("SELECT count(*) FROM Download").fetchone() == (2,)
        assert not db.execute("SELECT 1 FROM sqlite_master WHERE name='_post_metadata_tables'").fetchall()
