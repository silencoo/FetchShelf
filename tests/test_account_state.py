from copy import deepcopy
from types import SimpleNamespace

import pytest

from src.application.main_server import APIServer
from src.application.main_terminal import TikTok
from src.collector.account_state import confirmed_douyin_restriction, validate_archive_evidence
from src.config.settings import Settings


def profile(state):
    if state == 'deleted':
        return {'user_deleted': True, 'special_state_info': {
            'title': '账号已经注销', 'content': '用户已将自己账号注销，所属内容已无法查看'}}
    message = {'muted': '该用户被禁言，查看详情', 'banned': '该用户被封禁',
               'follow_restricted': '该用户被禁止关注'}[state]
    return {'sec_uid': 'target', 'uid': '123', 'is_ban': True,
            'punish_remind_info': {'is_punish': True, 'ban_type': 2,
                                   'prompt_bar': {'content': message}}}


@pytest.mark.parametrize('state', ['deleted', 'muted', 'banned', 'follow_restricted'])
def test_explicit_restrictions_roundtrip_and_target_binding(state):
    proof = confirmed_douyin_restriction(profile(state), 'target', {'api_status': 0})
    assert proof['state'] == state
    assert validate_archive_evidence(proof, 'target') == proof
    assert validate_archive_evidence(proof, 'other') is None
    conflicting = profile(state) | {'sec_uid': 'other'}
    assert confirmed_douyin_restriction(conflicting, 'target', {'api_status': 0}) is None


@pytest.mark.parametrize('value', [
    {}, {'nickname': '已注销'}, {'aweme_count': 0},
    {'sec_uid': 'target', 'uid': '123', 'secret': 1},
    {'user_deleted': True}, {'special_state_info': {'title': '账号已经注销'}},
    {'sec_uid': 'target', 'uid': '123', 'is_ban': True},
    {'sec_uid': 'target', 'uid': '123', 'punish_remind_info': {'is_punish': True, 'ban_type': 2}},
    {'sec_uid': 'target', 'uid': '123', 'nickname': '该用户被禁言', 'is_ban': True},
])
def test_unknown_private_empty_or_names_are_not_archive_evidence(value):
    assert confirmed_douyin_restriction(value, 'target', {'api_status': 0}) is None


@pytest.mark.parametrize('diagnostic', [
    {}, {'api_status': 8}, {'api_status': 0, 'http_status': 403},
    {'api_status': 0, 'error_type': 'CaptchaError'}, {'api_status': 0, '_error': 'timeout'},
])
def test_unsuccessful_responses_cannot_archive(diagnostic):
    assert confirmed_douyin_restriction(profile('deleted'), 'target', diagnostic) is None


def archive_server(tmp_path):
    class Parameter:
        auto_archive_restricted_accounts = True
        accounts_urls_tiktok = []
        deleted_accounts_tiktok = []
        def get_settings_data(self):
            return {'accounts_urls': [vars(row) for row in self.accounts_urls],
                    'deleted_accounts': self.deleted_accounts}
        check_urls_params = staticmethod(lambda rows: [SimpleNamespace(**row) for row in rows])
        check_deleted_accounts = staticmethod(lambda rows: deepcopy(rows))
    parameter = Parameter()
    parameter.accounts_urls = [SimpleNamespace(url='https://www.douyin.com/user/target', mark='Test', enable=True)]
    parameter.deleted_accounts = []
    parameter.settings = Settings.__new__(Settings)
    parameter.settings.path = tmp_path / 'settings.json'
    parameter.settings.console = SimpleNamespace(info=lambda *a: None)
    parameter.settings.update(parameter.get_settings_data())
    server = APIServer.__new__(APIServer)
    server.parameter = parameter
    server._backup_settings_file = lambda **kw: 'backup.json'
    server.collector_store = SimpleNamespace(delete_assignment=lambda *a, **kw: True)
    server.logger = SimpleNamespace(warning=lambda *a: None, info=lambda *a: None)
    return server


def execution():
    return {'item': {'url': 'https://www.douyin.com/user/target'}, 'sec_uid': 'target',
            'context': {'account_state': confirmed_douyin_restriction(
                profile('muted'), 'target', {'api_status': 0})}}


def test_archive_is_reversible_idempotent_and_preserves_media(tmp_path):
    server = archive_server(tmp_path)
    media = tmp_path / 'keep.mp4'
    media.write_bytes(b'unchanged media')
    result = execution()
    server._auto_archive_restricted_account(result, tiktok=False)
    assert result['context']['auto_archived'] is True
    assert server.parameter.accounts_urls == []
    trash = server.parameter.deleted_accounts
    assert len(trash) == 1 and trash[0]['mark'] == 'Test'
    assert trash[0]['enable'] is False and trash[0]['deleted_at']
    assert '禁言' in trash[0]['reason']
    server._auto_archive_restricted_account(execution(), tiktok=False)
    assert len(server.parameter.deleted_accounts) == 1
    assert media.read_bytes() == b'unchanged media'


@pytest.mark.parametrize('mode', ['disabled', 'tiktok', 'no_evidence', 'wrong_target'])
def test_archive_guards(tmp_path, mode):
    server = archive_server(tmp_path)
    result = execution()
    if mode == 'disabled':
        server.parameter.auto_archive_restricted_accounts = False
    elif mode == 'no_evidence':
        result['context'] = {}
        result['outcome_code'] = 'account_deleted'
    elif mode == 'wrong_target':
        result['sec_uid'] = 'other'
    server._auto_archive_restricted_account(result, tiktok=mode == 'tiktok')
    assert len(server.parameter.accounts_urls) == 1
    assert not server.parameter.deleted_accounts


def test_failed_save_rolls_back_both_lists(tmp_path):
    server = archive_server(tmp_path)
    before = server.parameter.settings.path.read_bytes()
    def fail(data):
        raise OSError('disk full')
    server.parameter.settings.update = fail
    result = execution()
    server._auto_archive_restricted_account(result, tiktok=False)
    assert result['context']['auto_archive_error'] == 'OSError'
    assert len(server.parameter.accounts_urls) == 1
    assert not server.parameter.deleted_accounts
    assert server.parameter.settings.path.read_bytes() == before


def test_atomic_settings_write_preserves_file_on_serialization_failure(tmp_path):
    server = archive_server(tmp_path)
    settings = server.parameter.settings
    before = settings.path.read_bytes()
    with pytest.raises(TypeError):
        settings.update({'invalid': object()})
    assert settings.path.read_bytes() == before
    assert not list(tmp_path.glob('.settings-*'))
    assert Settings.default['auto_archive_restricted_accounts'] is True


@pytest.mark.asyncio
async def test_full_profile_is_used_and_fallback_cannot_supply_proof(monkeypatch):
    from src.application import main_terminal as module
    calls = []
    class Full:
        last_request_error = None
        last_response_payload = {'status_code': 0}
        async def run(self):
            calls.append('full')
            return profile('muted')
        def __init__(self, *a): pass
    class Abbreviated(Full):
        async def run(self):
            calls.append('fallback')
            return {'uid': '123', 'sec_uid': 'target', 'nickname': 'Test'}
    monkeypatch.setattr(module, 'User', Full)
    monkeypatch.setattr(module, 'Info', Abbreviated)
    worker = TikTok.__new__(TikTok)
    worker.parameter = SimpleNamespace()
    await worker._get_info_data(sec_user_id='target')
    assert calls == ['full']
    assert worker._confirmed_account_state['state'] == 'muted'
    async def empty(self): return {}
    monkeypatch.setattr(Full, 'run', empty)
    await worker._get_info_data(sec_user_id='target')
    assert calls[-1] == 'fallback'
    assert worker._confirmed_account_state is None


def test_deleted_nickname_is_not_enough_for_manual_verification(tmp_path):
    server = archive_server(tmp_path)
    exists, _ = server._verify_user_info_state(
        {'sec_uid': 'target', 'uid': '123', 'nickname': '账号已注销'}, 'target', False)
    assert exists is True


@pytest.mark.asyncio
async def test_batch_archives_immediately_and_updates_current_remaining_row(tmp_path):
    from src.collector import CollectorStore, AESGCMSecretCodec
    server = archive_server(tmp_path)
    server.collector_store = CollectorStore(tmp_path / 'collector.sqlite3', codec=AESGCMSecretCodec(b'x' * 32))
    server.parameter.accounts_urls.append(SimpleNamespace(
        url='https://www.douyin.com/user/keep', mark='', enable=True))
    server.parameter.earliest_update_days = 3
    server.parameter.auto_backfill_mark = True
    persisted = []
    server._persist_account_runtime_updates = lambda **kw: persisted.append(kw)
    async def check(url, tiktok=False): return url.rsplit('/', 1)[-1]
    async def collect(*args, **kwargs):
        if kwargs['sec_user_id'] == 'target':
            return server._restricted_account_outcome(execution()['context']['account_state'])
        assert len(server.parameter.deleted_accounts) == 1  # Before next account finishes.
        assert len(server.parameter.accounts_urls) == 1
        return {'mark': 'Updated name'}
    server.check_sec_user_id = check
    server.deal_account_detail = collect
    result = await server._run_ui_account_batch(
        {'use_settings': True, 'cookie': 'sessionid=synthetic-fixture'}, tiktok=False)
    assert result.data['auto_archived'] == 1
    assert result.data['success'] == 1 and result.data['skipped'] == 1
    assert result.data['failed'] == 0
    assert server.parameter.accounts_urls[0].mark == 'Updated name'
    assert len(server.parameter.accounts_urls) == 1
    assert persisted[-1]['mark_updated'] == 1
    server.collector_store.close()
