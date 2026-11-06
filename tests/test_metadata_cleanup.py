import json
import sqlite3

import pytest

from scripts.clean_post_metadata import clean
from test_post_metadata import TABLE, logger, query, values
from src.storage.manager import RecordManager


def legacy(root):
    path = root / 'DetailData.db'
    with sqlite3.connect(path) as db:
        columns = ','.join(f'"{n}" {t}' for n, t in zip(RecordManager.detail_name, RecordManager.detail_type))
        db.execute(f'CREATE TABLE "{TABLE}" ({columns})')
        observations = [
            values(**{'采集时间':'2026-11-01 10:00:00'}),
            values(**{'采集时间':'2026-11-02 10:00:00', '点赞数量':20}),
            values(**{'采集时间':'2026-11-03 10:00:00', '作品描述':'edit', '点赞数量':30}),
            values(**{'采集时间':'2026-11-04 10:00:00', '作品描述':'', '点赞数量':40}),
            values(**{'作品ID':'222'}),
        ]
        db.executemany(f'INSERT INTO "{TABLE}" VALUES ({",".join("?" for _ in RecordManager.detail_name)})',observations)
        db.execute('CREATE TABLE unrelated (value TEXT)')
        db.execute("INSERT INTO unrelated VALUES ('keep')")
    return path


def inspect(path):
    with sqlite3.connect(path) as db:
        current = db.execute(f'SELECT 作品ID,作品描述,点赞数量 FROM "{TABLE}" ORDER BY 作品ID').fetchall()
        history = db.execute('SELECT metadata,changed_at FROM _post_metadata_history ORDER BY id').fetchall()
        assert db.execute('SELECT * FROM unrelated').fetchall() == [('keep',)]
        assert not db.execute("SELECT name FROM sqlite_master WHERE name LIKE '_legacy_posts_%'").fetchall()
    return current, [(json.loads(row)['作品描述'], at) for row, at in history]


def test_cleanup_collapses_observations_and_preserves_edits(tmp_path):
    source = legacy(tmp_path)
    output = tmp_path/'clean.db'
    result = clean(source, output)
    assert result['current_posts'] == 2
    assert result['snapshots'] == 1
    assert inspect(output) == ([('111','edit',40),('222','original',10)], [('original','2026-11-03 10:00:00')])
    assert query(tmp_path,f'SELECT count(*) FROM "{TABLE}"') == [(5,)]
    second = tmp_path/'again.db'
    clean(output,second)
    assert inspect(second) == inspect(output)


@pytest.mark.asyncio
async def test_cleanup_combines_archived_and_new_history(tmp_path):
    source=legacy(tmp_path)
    async with logger(tmp_path) as log:
        await log.save(values(**{'采集时间':'2026-11-05 10:00:00','作品描述':'new edit','点赞数量':50}))
        await log.save(values(**{'采集时间':'2026-11-06 10:00:00','作品描述':'new edit','点赞数量':60}))
    output=tmp_path/'clean.db'
    result=clean(source,output)
    assert result['archives_removed']==1
    assert inspect(output)==([('111','new edit',60),('222','original',10)], [
        ('original','2026-11-03 10:00:00'),('edit','2026-11-05 10:00:00')])
    second=tmp_path/'again.db'
    clean(output,second)
    assert inspect(second)==inspect(output)


def test_refuses_unknown_archive(tmp_path):
    source=legacy(tmp_path)
    with sqlite3.connect(source) as db:
        db.execute('CREATE TABLE _legacy_posts_unknown (value TEXT)')
    with pytest.raises(ValueError,match='Unregistered'):
        clean(source,tmp_path/'clean.db')
    assert query(tmp_path,f'SELECT count(*) FROM "{TABLE}"')==[(5,)]
