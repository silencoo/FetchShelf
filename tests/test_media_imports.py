import json
import pytest
from src.webui.media_imports import load_import_sources
from src.webui.feed_index import FeedIndex
from src.webui.feed_state import FeedState


def test_same_names_and_files_are_separate_platform_accounts(tmp_path):
    rows = []
    for platform in ('douyin', 'tiktok', 'kuaishou', 'rednote', 'weibo'):
        folder = tmp_path / platform / 'UID1_Same_作品'
        folder.mkdir(parents=True)
        (folder / '2026-11-01 10.00.00-视频-Same-holiday.mp4').write_bytes(b'video')
        rows.append(dict(platform=platform, id='1', name='Same', folder=str(folder.relative_to(tmp_path))))
    manifest = tmp_path / 'imports.json'
    manifest.write_text(json.dumps(rows))
    index = FeedIndex(tmp_path / 'index.db')
    state = FeedState(tmp_path / 'state.db')
    sources = load_import_sources(manifest, tmp_path)
    for source in sources:
        index.sync_account(source, tmp_path)
    keys = set()
    for source in sources:
        accounts, total = index.accounts(platform=source.platform)
        assert total == 1 and accounts[0]['account_key'] == source.key
        posts, _ = index.latest_posts(limit=1, cursor={}, platform=source.platform)
        assert len(posts) == 1 and posts[0]['account_key'] == source.key
        keys.add(posts[0]['post_key'])
        state.set_mark('like', posts[0]['post_key'], True, account_key=source.key)
        recommended, _ = index.foryou_page(limit=5, cursor={}, favorites=[], hidden=[], platform=source.platform)
        assert recommended and all(p['account_key'] == source.key for p in recommended)
        found, _ = index.search_posts('holiday', field='all', limit=5, cursor={}, platform=source.platform)
        assert found and all(p['account_key'] == source.key for p in found)
    assert len(keys) == 5
    assert state.counts(platform='weibo')['like'] == 1
    assert len(state.page('like', limit=10, platform='tiktok')[0]) == 1


def test_import_rejects_outside_root_and_duplicate_ids(tmp_path):
    manifest = tmp_path / 'imports.json'
    row = dict(platform='weibo', id='1', name='Same', folder='../outside')
    manifest.write_text(json.dumps([row]))
    with pytest.raises(ValueError):
        load_import_sources(manifest, tmp_path)
    row['folder'] = 'inside'
    manifest.write_text(json.dumps([row, row]))
    with pytest.raises(ValueError):
        load_import_sources(manifest, tmp_path)
