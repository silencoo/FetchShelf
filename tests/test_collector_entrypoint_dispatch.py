import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.application import main_server as main_server_module
from src.application.main_server import APIServer
from src.collector import (
    AESGCMSecretCodec,
    CollectorAssignment,
    CollectorCredentials,
    CollectorIdentity,
    CollectorPlatform,
    CollectorPolicy,
    CollectorStore,
    IdentityLeaseManager,
    IdentityStatus,
)
from src.models import DetailTikTok


class _AsyncRecord:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc_value, traceback):
        return None


class _Record:
    @staticmethod
    def run(parameter):
        return Path("."), {}, lambda *args, **kwargs: _AsyncRecord()


class _Runtime:
    def __init__(self, identity, *, close_error=False):
        self.parameter = SimpleNamespace(collector_identity_id=identity.identity_id)
        self.close_error = close_error

    async def close(self):
        if self.close_error:
            raise RuntimeError("close failed")


def _server(tmp_path: Path) -> APIServer:
    server = APIServer.__new__(APIServer)
    server.collector_store = CollectorStore(
        tmp_path / "collector.sqlite3",
        codec=AESGCMSecretCodec(b"e" * 32),
    )
    server.collector_leases = IdentityLeaseManager()
    server.database = object()
    server.console = SimpleNamespace()
    server.logger = SimpleNamespace(
        info=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
    )
    server.parameter = SimpleNamespace(
        settings=SimpleNamespace(
            path=tmp_path / "settings.json",
            update=lambda value: None,
        ),
        cookie_str="",
        cookie_dict={},
        proxy=None,
    )
    return server


def _save_identity(
    server: APIServer,
    identity_id: str,
    platform: CollectorPlatform,
    *,
    cookie: str | None = None,
    proxy: str = "",
):
    server.collector_store.save_identity(
        CollectorIdentity(
            identity_id=identity_id,
            name=identity_id,
            platform=platform,
            max_concurrency=1,
        ),
        credentials=CollectorCredentials(
            cookie=cookie or f"sessionid={identity_id}",
            proxy=proxy,
        ),
    )


@pytest.mark.asyncio
async def test_tiktok_detail_url_uses_selected_identity_proxy_before_fetch(
    tmp_path,
    monkeypatch,
):
    server = _server(tmp_path)
    _save_identity(
        server,
        "tt-main",
        CollectorPlatform.TIKTOK,
        cookie="sessionid=vault-cookie",
        proxy="socks5://vault-proxy:1080",
    )
    captured = {}

    class Worker:
        def __init__(self, parameter, database, server_mode=True):
            self.parameter = parameter
            self.console = SimpleNamespace()
            self.record = _Record()

        async def _parse_tiktok_detail_targets(self, text, proxy):
            captured["parse"] = (text, proxy)
            return [{"id": "7300000000000000000", "url": text}]

        @staticmethod
        def _split_tiktok_detail_targets(items):
            return [items[0]["id"]], [items[0]["url"]]

        async def _handle_detail(self, ids, tiktok, record, *args, **kwargs):
            captured["fetch"] = (ids, args[2], args[3])
            return [{"id": ids[0]}]

    monkeypatch.setattr(main_server_module, "TikTok", Worker)
    monkeypatch.setattr(
        main_server_module,
        "build_collector_runtime",
        lambda base, identity, credentials, settings_dir: _Runtime(identity),
    )

    response = await server.handle_detail(
        DetailTikTok(
            detail_url="https://www.tiktok.com/@demo/video/7300000000000000000",
            identity_id="tt-main",
            cookie="request-cookie-must-not-win",
            proxy="http://request-proxy:8080",
        ),
        True,
    )

    assert captured["parse"][1] == "socks5://vault-proxy:1080"
    assert captured["fetch"] == (
        ["7300000000000000000"],
        "sessionid=vault-cookie",
        "socks5://vault-proxy:1080",
    )
    assert response.params["selected_identity_id"] == "tt-main"
    assert response.params["selected_by"] == "task_override"
    assert "vault-cookie" not in str(response.params)
    server.collector_store.close()


@pytest.mark.asyncio
async def test_detail_links_routes_each_link_and_parallelizes_identity_groups(
    tmp_path,
    monkeypatch,
):
    server = _server(tmp_path)
    for identity_id in ("dy-one", "dy-two"):
        _save_identity(server, identity_id, CollectorPlatform.DOUYIN)
    links = [
        "https://www.douyin.com/video/111",
        "https://www.douyin.com/video/222",
    ]
    server.collector_store.upsert_assignments(
        [
            CollectorAssignment(
                platform=CollectorPlatform.DOUYIN,
                target_type="detail",
                target_key=link,
                identity_id=identity_id,
            )
            for link, identity_id in zip(links, ("dy-one", "dy-two"))
        ]
    )
    active = 0
    max_active = 0

    class Worker:
        def __init__(self, parameter, database, server_mode=True):
            self.parameter = parameter
            self.identity_id = parameter.collector_identity_id
            self.console = SimpleNamespace()
            self.record = _Record()
            self.links = SimpleNamespace(run=self.parse)
            self.links_tiktok = SimpleNamespace()
            self.downloader = SimpleNamespace(run=self.download)

        async def parse(self, text, proxy=None):
            return [text.rsplit("/", 1)[-1]]

        async def _handle_detail(self, ids, *args, **kwargs):
            nonlocal active, max_active
            active += 1
            max_active = max(max_active, active)
            await asyncio.sleep(0.02)
            active -= 1
            return [{"id": item} for item in ids]

        async def download(self, data, mode, tiktok=False):
            return None

        @staticmethod
        def _get_preview_image(data):
            return f"preview:{data['id']}"

    monkeypatch.setattr(main_server_module, "TikTok", Worker)
    monkeypatch.setattr(
        main_server_module,
        "build_collector_runtime",
        lambda base, identity, credentials, settings_dir: _Runtime(identity),
    )

    response = await server._run_ui_detail_links({"links": links}, False)

    assert max_active == 2
    assert response.data["downloaded"] == 2
    assert [item["identity_id"] for item in response.data["routes"]] == [
        "dy-one",
        "dy-two",
    ]
    assert response.data["selected_by"] == "fixed_binding"
    server.collector_store.close()


@pytest.mark.asyncio
async def test_collect_monitor_uses_identity_runtime_and_only_forces_explicit_crawl(
    tmp_path,
    monkeypatch,
):
    server = _server(tmp_path)
    _save_identity(
        server,
        "dy-monitor",
        CollectorPlatform.DOUYIN,
        cookie="sessionid=monitor",
        proxy="http://monitor-proxy:8080",
    )
    server.parameter.get_settings_data = lambda: {}
    server._account_rows = lambda *args, **kwargs: []
    server._set_account_rows = lambda *args, **kwargs: None
    captured_fetches = []
    captured_batches = []

    async def fetch(*, collect_id, cookie, proxy, limit, parameter=None):
        captured_fetches.append((cookie, proxy, parameter.collector_identity_id))
        return [
            {
                "aweme_id": f"aweme-{len(captured_fetches)}",
                "author": {"sec_uid": f"sec-{len(captured_fetches)}"},
            }
        ]

    async def batch(payload, tiktok):
        captured_batches.append(payload)
        return SimpleNamespace(message="ok", data={})

    server._collect_monitor_fetch_aweme_items = fetch
    server._run_ui_account_batch = batch
    monkeypatch.setattr(main_server_module, "TikTok", lambda *args, **kwargs: SimpleNamespace(
        parameter=args[0]
    ))
    monkeypatch.setattr(
        main_server_module,
        "build_collector_runtime",
        lambda base, identity, credentials, settings_dir: _Runtime(identity),
    )

    explicit = await server._run_collect_monitor_once(
        {
            "collect_id": "123",
            "identity_id": "dy-monitor",
            "immediate_crawl": True,
        }
    )
    automatic = await server._run_collect_monitor_once(
        {
            "collect_id": "456",
            "immediate_crawl": True,
        }
    )

    assert captured_fetches == [
        ("sessionid=monitor", "http://monitor-proxy:8080", "dy-monitor"),
        ("sessionid=monitor", "http://monitor-proxy:8080", "dy-monitor"),
    ]
    assert explicit["selected_identity_id"] == "dy-monitor"
    assert automatic["selected_identity_id"] == "dy-monitor"
    assert captured_batches[0]["identity_id"] == "dy-monitor"
    assert captured_batches[1]["identity_id"] == ""
    server.collector_store.close()


@pytest.mark.asyncio
async def test_collect_monitor_without_pool_or_global_cookie_returns_clean_failure(tmp_path):
    server = _server(tmp_path)

    result = await server._run_collect_monitor_once({"collect_id": "123"})

    assert result["ok"] is False
    assert result["selected_identity_id"] == ""
    assert result["selected_by"] == "global_fallback"
    assert result["immediate_result"] == {}
    server.collector_store.close()


@pytest.mark.asyncio
async def test_collect_monitor_propagates_request_failure(tmp_path, monkeypatch):
    server = _server(tmp_path)

    class FailedCollector:
        cursor = 0
        finished = True
        last_request_error = RuntimeError("403 Forbidden")

        def __init__(self, *args, **kwargs):
            pass

        async def run(self, **kwargs):
            return []

    monkeypatch.setattr(main_server_module, "CollectsDetail", FailedCollector)

    async def failed_browser_fetch(**kwargs):
        raise RuntimeError("browser failed")

    monkeypatch.setattr(
        main_server_module,
        "fetch_douyin_collection_via_browser",
        failed_browser_fetch,
    )

    with pytest.raises(RuntimeError, match="direct and browser paths"):
        await server._collect_monitor_fetch_aweme_items(
            collect_id="123",
            cookie="sessionid=secret",
            proxy=None,
            limit=1,
        )

    server.collector_store.close()


@pytest.mark.asyncio
async def test_collect_monitor_falls_back_to_browser(tmp_path, monkeypatch):
    server = _server(tmp_path)

    class FailedCollector:
        cursor = 0
        finished = True
        last_request_error = RuntimeError("403 Forbidden")

        def __init__(self, *args, **kwargs):
            pass

        async def run(self, **kwargs):
            return []

    captured = {}

    async def browser_fetch(**kwargs):
        captured.update(kwargs)
        return [{"aweme_id": "browser-1"}]

    monkeypatch.setattr(main_server_module, "CollectsDetail", FailedCollector)
    monkeypatch.setattr(
        main_server_module,
        "fetch_douyin_collection_via_browser",
        browser_fetch,
    )

    result = await server._collect_monitor_fetch_aweme_items(
        collect_id="123",
        cookie="sessionid=secret",
        proxy="http://proxy:8080",
        limit=1,
    )

    assert result == [{"aweme_id": "browser-1"}]
    assert captured == {
        "collect_id": "123",
        "cookie": "sessionid=secret",
        "proxy": "http://proxy:8080",
        "limit": 1,
    }
    server.collector_store.close()


@pytest.mark.asyncio
async def test_runtime_close_failures_are_counted_and_enter_policy_cooldown(
    tmp_path,
    monkeypatch,
):
    server = _server(tmp_path)
    _save_identity(server, "dy-close", CollectorPlatform.DOUYIN)
    server.collector_store.upsert_policy(
        CollectorPolicy(
            platform=CollectorPlatform.DOUYIN,
            failure_threshold=2,
            cooldown_seconds=60,
        )
    )
    monkeypatch.setattr(
        main_server_module,
        "TikTok",
        lambda parameter, database, server_mode=True: SimpleNamespace(
            parameter=parameter
        ),
    )
    monkeypatch.setattr(
        main_server_module,
        "build_collector_runtime",
        lambda base, identity, credentials, settings_dir: _Runtime(
            identity,
            close_error=True,
        ),
    )

    async def operation(worker, credentials, identity_id):
        return {"ok": True}, 1, 0

    for _ in range(2):
        await server._execute_collector_identity_operation(
            CollectorPlatform.DOUYIN,
            "dy-close",
            operation,
        )

    state = server.collector_store.get_runtime("dy-close")
    assert state.status == IdentityStatus.COOLDOWN
    assert state.total_successes == 2
    assert state.total_failures == 2
    assert state.consecutive_failures == 2
    assert state.last_error_code == "identity_runtime_close_failed"
    server.collector_store.close()


@pytest.mark.asyncio
async def test_waiting_same_identity_does_not_block_other_identity_platform_slot(
    tmp_path,
    monkeypatch,
):
    server = _server(tmp_path)
    _save_identity(server, "dy-a", CollectorPlatform.DOUYIN)
    _save_identity(server, "dy-b", CollectorPlatform.DOUYIN)
    server.collector_store.upsert_policy(
        CollectorPolicy(
            platform=CollectorPlatform.DOUYIN,
            global_max_parallel=2,
        )
    )
    monkeypatch.setattr(
        main_server_module,
        "TikTok",
        lambda parameter, database, server_mode=True: SimpleNamespace(
            parameter=parameter
        ),
    )
    monkeypatch.setattr(
        main_server_module,
        "build_collector_runtime",
        lambda base, identity, credentials, settings_dir: _Runtime(identity),
    )
    first_a_started = asyncio.Event()
    b_started = asyncio.Event()
    release_a = asyncio.Event()
    a_calls = 0

    async def operation(worker, credentials, identity_id):
        nonlocal a_calls
        if identity_id == "dy-a":
            a_calls += 1
            if a_calls == 1:
                first_a_started.set()
                await release_a.wait()
        else:
            b_started.set()
        return {"ok": True}, 1, 0

    first_a = asyncio.create_task(
        server._execute_collector_identity_operation(
            CollectorPlatform.DOUYIN,
            "dy-a",
            operation,
        )
    )
    await first_a_started.wait()
    second_a = asyncio.create_task(
        server._execute_collector_identity_operation(
            CollectorPlatform.DOUYIN,
            "dy-a",
            operation,
        )
    )
    await asyncio.sleep(0.01)
    b_task = asyncio.create_task(
        server._execute_collector_identity_operation(
            CollectorPlatform.DOUYIN,
            "dy-b",
            operation,
        )
    )

    await asyncio.wait_for(b_started.wait(), timeout=0.2)
    assert first_a.done() is False
    release_a.set()
    await asyncio.gather(first_a, second_a, b_task)
    server.collector_store.close()


def test_non_account_policy_routes_do_not_create_hidden_sticky_assignments(tmp_path):
    server = _server(tmp_path)
    _save_identity(server, "dy-one", CollectorPlatform.DOUYIN)
    _save_identity(server, "dy-two", CollectorPlatform.DOUYIN)

    route = server._plan_collector_routes(
        CollectorPlatform.DOUYIN,
        [{"target_key": "7300000000000000000"}],
        target_type="detail",
    )[0]

    assert route["identity_id"] in {"dy-one", "dy-two"}
    assert server.collector_store.list_assignments(
        CollectorPlatform.DOUYIN,
        target_type="detail",
    ) == []
    server.collector_store.close()


@pytest.mark.asyncio
async def test_account_verify_reports_selected_identity_route(tmp_path):
    server = _server(tmp_path)
    server._account_rows = lambda *args, **kwargs: []

    async def execute(**kwargs):
        result, _, _ = await kwargs["operation"](
            SimpleNamespace(
                check_sec_user_id=lambda *args, **kw: _async_value("sec-1"),
                get_user_info_data=lambda **kw: _async_value(
                    {"nickname": "demo", "sec_uid": "sec-1", "uid": "uid-1"}
                ),
            ),
            CollectorCredentials(cookie="sessionid=vault"),
            "dy-verify",
        )
        return result, "dy-verify", "sticky_balanced"

    server._execute_collector_operation = execute
    result = await server._verify_accounts(
        {
            "platform": "douyin",
            "use_settings": False,
            "move_deleted": False,
            "items": [{"url": "https://www.douyin.com/user/demo"}],
        }
    )

    assert result["items"][0]["selected_identity_id"] == "dy-verify"
    assert result["items"][0]["selected_by"] == "sticky_balanced"
    server.collector_store.close()


@pytest.mark.asyncio
async def test_ui_executor_covers_complete_direct_collector_matrix():
    server = APIServer.__new__(APIServer)
    calls = []

    async def detail(extract, tiktok):
        calls.append(("detail", tiktok, extract.identity_id))
        return {}

    async def account(extract, tiktok):
        calls.append(("account", tiktok, extract.identity_id))
        return {}

    async def mix(extract, tiktok):
        calls.append(("mix", tiktok, extract.identity_id))
        return {}

    async def live(extract, tiktok):
        calls.append(("live", tiktok, extract.identity_id))
        return {}

    async def comment(extract):
        calls.append(("comment", False, extract.identity_id))
        return {}

    async def reply(extract):
        calls.append(("reply", False, extract.identity_id))
        return {}

    async def search(extract):
        calls.append((f"search-{extract.channel}", False, extract.identity_id))
        return {}

    server.handle_detail = detail
    server.handle_account = account
    server._handle_mix_request = mix
    server._handle_live_request = live
    server._handle_comment_request = comment
    server._handle_reply_request = reply
    server.handle_search = search

    cases = [
        ("/douyin/detail", {"detail_id": "1"}),
        ("/douyin/account", {"sec_user_id": "sec"}),
        ("/douyin/mix", {"mix_id": "mix"}),
        ("/douyin/live", {"web_rid": "live"}),
        ("/douyin/comment", {"detail_id": "1"}),
        ("/douyin/reply", {"detail_id": "1", "comment_id": "2"}),
        ("/douyin/search/general", {"keyword": "demo"}),
        ("/douyin/search/video", {"keyword": "demo"}),
        ("/douyin/search/user", {"keyword": "demo"}),
        ("/douyin/search/live", {"keyword": "demo"}),
        ("/tiktok/detail", {"detail_id": "1"}),
        ("/tiktok/account", {"sec_user_id": "sec"}),
        ("/tiktok/mix", {"mix_id": "mix"}),
        ("/tiktok/live", {"room_id": "live"}),
    ]
    for endpoint, payload in cases:
        await server._execute_ui_endpoint(
            endpoint,
            {**payload, "identity_id": "dy-route"},
        )

    assert len(calls) == len(cases)
    assert {item[0] for item in calls} >= {
        "detail",
        "account",
        "mix",
        "live",
        "comment",
        "reply",
        "search-0",
        "search-1",
        "search-2",
        "search-3",
    }
    assert all(item[2] == "dy-route" for item in calls)


async def _async_value(value):
    return value
