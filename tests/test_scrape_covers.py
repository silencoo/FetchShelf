import asyncio
from types import SimpleNamespace

import pytest

from src.application import main_server
from src.application.main_server import APIServer
from src.tools import Cleaner


def server_for(tmp_path, names):
    server = APIServer.__new__(APIServer)
    rows = [{"url": name.lower(), "mark": name, "enable": True} for name in names]
    server.parameter = SimpleNamespace(
        root=tmp_path, CLEANER=Cleaner(),
        settings=SimpleNamespace(path=tmp_path / 'settings.json', encode='utf-8'),
    )
    server._active_account_rows = lambda platform: rows
    server.logger = SimpleNamespace(warning=lambda *args: None)
    for name in names:
        folder = tmp_path / f'UID1_{name}'
        folder.mkdir()
        (folder / 'a.jpg').write_bytes(b'fixture')
        (folder / 'b.mp4').write_bytes(b'fixture')
    return server, rows


@pytest.mark.asyncio
async def test_without_any_page_visit_selects_and_persists_cover(tmp_path, monkeypatch):
    server, rows = server_for(tmp_path, ['Alpha'])
    assert not server._account_board_pin_file().exists()
    monkeypatch.setattr(main_server, 'choose_face_cover', lambda *args: {'path': 'UID1_Alpha/b.mp4', 'second': 3})
    counts = await server._pin_scraped_account_covers('douyin', ['alpha'])
    assert counts == {'pinned': 1, 'unchanged': 0, 'no_media': 0, 'failed': 0}
    assert server._load_account_board_pins()['douyin::alpha'] == {
        'path': 'UID1_Alpha/b.mp4', 'second': 3, 'source': 'face_auto'}
    monkeypatch.setattr(main_server, 'choose_face_cover', lambda *args: pytest.fail('Must not reroll a pin'))
    assert (await server._pin_scraped_account_covers('douyin', ['alpha']))['unchanged'] == 1


@pytest.mark.asyncio
async def test_keeps_all_finished_pins_and_completes_pending_or_missing_files(tmp_path, monkeypatch):
    server, rows = server_for(tmp_path, ['Manual', 'Legacy', 'Face', 'Fallback', 'Pending', 'Missing', 'Fresh'])
    sources = ['manual', 'legacy', 'face_auto', 'fallback', 'pending', 'face_auto']
    pins = {f'douyin::{row["url"]}': {'path': f'UID1_{row["mark"]}/a.jpg', 'source': source}
            for row, source in zip(rows, sources)}
    pins['douyin::missing']['path'] = 'gone.jpg'
    server._save_account_board_pins(pins)
    monkeypatch.setattr(main_server, 'choose_face_cover', lambda *args: None)
    result = await server._pin_scraped_account_covers('douyin', [r['url'] for r in rows])
    assert result['pinned'] == 3 and result['unchanged'] == 4
    after = server._load_account_board_pins()
    for key in ('manual', 'legacy', 'face', 'fallback'):
        assert after['douyin::' + key] == pins['douyin::' + key]
    assert all(after['douyin::' + key]['source'] == 'fallback' for key in ('pending', 'missing', 'fresh'))


@pytest.mark.asyncio
async def test_only_requested_active_enabled_accounts_and_media_are_used(tmp_path, monkeypatch):
    server, rows = server_for(tmp_path, ['Requested', 'Other', 'Disabled', 'Empty'])
    rows[2]['enable'] = False
    for path in (tmp_path / 'UID1_Empty').iterdir(): path.unlink()
    monkeypatch.setattr(main_server, 'choose_face_cover', lambda *args: None)
    result = await server._pin_scraped_account_covers('tiktok', ['requested', 'disabled', 'empty', 'archived'])
    assert result['pinned'] == 1 and result['no_media'] == 1
    assert set(server._load_account_board_pins()) == {'tiktok::requested'}


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['manual', 'archive'])
async def test_user_changes_during_face_selection_win(tmp_path, monkeypatch, change):
    server, rows = server_for(tmp_path, ['Alpha'])
    async def compute(fn):
        selected = fn()
        if change == 'manual':
            server._save_account_board_pins({'douyin::alpha': {'path': 'UID1_Alpha/b.mp4', 'source': 'manual'}})
        else:
            rows.clear()
        return selected
    monkeypatch.setattr(main_server, 'to_thread', compute)
    monkeypatch.setattr(main_server, 'choose_face_cover', lambda *args: None)
    result = await server._ensure_scraped_account_cover('douyin', 'alpha', tmp_path, server._board_folder_index(tmp_path))
    assert result == 'unchanged'
    pins = server._load_account_board_pins()
    if change == 'manual': assert pins['douyin::alpha']['source'] == 'manual'
    else: assert not pins


@pytest.mark.asyncio
async def test_cover_failure_does_not_abort_other_accounts(tmp_path, monkeypatch):
    server, _ = server_for(tmp_path, ['Alpha', 'Beta'])
    def select(root, images, *args):
        if 'Alpha' in images[0]: raise OSError('fixture decoding failed')
        return None
    monkeypatch.setattr(main_server, 'choose_face_cover', select)
    result = await server._pin_scraped_account_covers('douyin', ['alpha', 'beta'])
    assert result['failed'] == 1 and result['pinned'] == 1
    assert set(server._load_account_board_pins()) == {'douyin::beta'}


@pytest.mark.asyncio
async def test_pause_boundary_progress_and_cancel_are_preserved(tmp_path, monkeypatch):
    server, _ = server_for(tmp_path, ['Alpha', 'Beta'])
    monkeypatch.setattr(main_server, 'choose_face_cover', lambda *args: None)
    visited, labels = [], []
    async def checkpoint():
        visited.append('checkpoint')
        if visited.count('checkpoint') == 2: raise asyncio.CancelledError
    with pytest.raises(asyncio.CancelledError):
        await server._pin_scraped_account_covers('douyin', ['alpha', 'beta'], progress=labels.append,
            pause_control={'checkpoint': checkpoint, 'unit_started': lambda: visited.append('start'),
                           'unit_finished': lambda: visited.append('finish')})
    assert visited == ['checkpoint', 'start', 'finish', 'checkpoint']
    assert len(labels) == 1 and '1/2' in labels[0]
    assert set(server._load_account_board_pins()) == {'douyin::alpha'}


@pytest.mark.asyncio
async def test_concurrent_cover_requests_share_one_selection_slot(tmp_path, monkeypatch):
    from threading import Lock
    from time import sleep
    server, _ = server_for(tmp_path, ['Alpha', 'Beta'])
    guard = Lock()
    active = peak = 0
    def select(*args):
        nonlocal active, peak
        with guard:
            active += 1
            peak = max(peak, active)
        sleep(0.03)
        with guard: active -= 1
        return None
    monkeypatch.setattr(main_server, 'choose_face_cover', select)
    results = await asyncio.gather(
        server._pin_scraped_account_covers('douyin', ['alpha']),
        server._pin_scraped_account_covers('douyin', ['beta']),
    )
    assert peak == 1
    assert [result['pinned'] for result in results] == [1, 1]
    assert len(server._load_account_board_pins()) == 2
