from pathlib import Path
from time import monotonic
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
import pytest

from src.application import feed_routes
from src.application.feed_routes import FeedService, comment_payload
from src.application.main_server import APIServer
from src.tools import Cleaner
from src.webui.feed_state import FeedState

HEADERS = {"token": "fixture-token"}


def make_image(path: Path, size=(1200, 1600)) -> None:
    Image.new("RGB", size, (40, 90, 160)).save(path, "JPEG")


@pytest.fixture
def harness(tmp_path, monkeypatch):
    monkeypatch.setenv("FETCHSHELF_API_TOKEN", "fixture-token")
    root = tmp_path / "media"
    ann = root / "UID1_Ann_发布作品"
    bob = root / "UID2_Bob_发布作品"
    ann.mkdir(parents=True)
    bob.mkdir()
    (ann / "2026-01-01 10.00.00-视频-Ann-one #fun.mp4").write_bytes(b"not really a video")
    (ann / "2026-01-02 10.00.00-视频-Ann-two.mp4").write_bytes(b"not really a video")
    make_image(ann / "2026-01-03 10.00.00-图集-Ann-photos_1.jpeg")
    make_image(ann / "2026-01-03 10.00.00-图集-Ann-photos_2.jpeg")
    (bob / "2026-02-01 10.00.00-视频-Bob-hello.mp4").write_bytes(b"not really a video")

    rows = {
        "douyin": [
            {"url": "https://example.test/ann", "mark": "Ann", "enable": True},
            {"url": "https://example.test/bob", "mark": "Bob", "enable": True},
        ],
        "tiktok": [],
    }
    server = APIServer.__new__(APIServer)
    server.server = FastAPI()
    server.parameter = SimpleNamespace(
        root=root,
        CLEANER=Cleaner(),
        settings=SimpleNamespace(path=tmp_path / "settings.json", encode="utf-8"),
    )
    server._active_account_rows = lambda platform: rows[platform]
    server.logger = SimpleNamespace(warning=lambda *args: None)
    server.setup_routes()
    client = TestClient(server.server)
    service = FeedService(server)
    server._feed_service = service
    # Tests drive the worker directly so results never depend on timing.
    service.worker.touch = lambda: None
    service.worker.throttle = False
    service.worker.run_once()
    return SimpleNamespace(client=client, server=server, service=service, root=root, tmp=tmp_path)


def get(harness, path, **params):
    response = harness.client.get(path, params=params, headers=HEADERS)
    assert response.status_code == 200, response.text
    return response.json()


def put_mark(harness, kind, target, on=True):
    return harness.client.put(
        "/ui/api/feed/marks", headers=HEADERS, json={"kind": kind, "target": target, "on": on},
    )


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/ui/api/feed/status"),
        ("get", "/ui/api/feed/posts"),
        ("get", "/ui/api/feed/post?key=x"),
        ("get", "/ui/api/feed/account?key=x"),
        ("get", "/ui/api/feed/accounts"),
        ("get", "/ui/api/feed/tags"),
        ("get", "/ui/api/feed/me"),
        ("get", "/ui/api/feed/comments?key=x"),
        ("get", "/ui/api/feed/thumb?path=x"),
        ("post", "/ui/api/feed/refresh"),
        ("delete", "/ui/api/feed/marks?kind=hide"),
    ],
)
def test_every_feed_route_requires_the_token(harness, method, path):
    assert getattr(harness.client, method)(path).status_code == 403


def test_marks_route_requires_the_token(harness):
    response = harness.client.put(
        "/ui/api/feed/marks", json={"kind": "like", "target": "x", "on": True},
    )
    assert response.status_code == 403


def test_feed_page_serves_the_same_app_shell(harness, tmp_path, monkeypatch):
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<html>shell</html>", encoding="utf-8")
    monkeypatch.setattr(APIServer, "WEBUI_STATIC_DIR", static)
    response = harness.client.get("/ui/feed")
    assert response.status_code == 200 and "shell" in response.text
    assert response.headers["cache-control"] == "no-cache"


def test_post_payload_has_media_author_and_never_absolute_paths(harness):
    payload = get(harness, "/ui/api/feed/posts", source="latest", limit=10)
    posts = {post["key"]: post for post in payload["items"]}
    assert len(posts) == 4 and payload["next_cursor"] is None
    photos = posts["1:20260103100000:i"]
    assert photos["kind"] == "images"
    assert [item["kind"] for item in photos["media"]] == ["image", "image"]
    assert photos["media"][0]["path"].startswith("UID1_Ann_发布作品/")
    assert photos["author"]["name"] == "Ann"
    assert photos["author"]["avatar"]["scope"] == "download"
    assert photos["stats"] is None
    assert str(harness.root) not in str(payload)
    assert str(harness.tmp) not in str(payload)


def test_unknown_source_and_missing_account_are_rejected(harness):
    client = harness.client
    assert client.get("/ui/api/feed/posts?source=nope", headers=HEADERS).status_code == 400
    assert client.get("/ui/api/feed/posts?source=account", headers=HEADERS).status_code == 400
    assert client.get("/ui/api/feed/posts?source=account&account=x", headers=HEADERS).status_code == 404
    assert client.get("/ui/api/feed/post?key=none", headers=HEADERS).status_code == 404
    assert client.get("/ui/api/feed/account?key=none", headers=HEADERS).status_code == 404
    assert client.get("/ui/api/feed/posts?limit=1000", headers=HEADERS).status_code == 422


def test_likes_saves_and_follows_round_trip(harness):
    key = "1:20260101100000:v"
    ann = "douyin::https://example.test/ann"
    assert put_mark(harness, "like", key).status_code == 200
    assert put_mark(harness, "save", key).status_code == 200
    assert put_mark(harness, "follow", ann).status_code == 200

    post = get(harness, "/ui/api/feed/post", key=key)
    assert post["liked"] and post["saved"] and post["author"]["followed"]
    assert [item["key"] for item in get(harness, "/ui/api/feed/posts", source="likes")["items"]] == [key]
    assert [item["key"] for item in get(harness, "/ui/api/feed/posts", source="saves")["items"]] == [key]
    assert get(harness, "/ui/api/feed/posts", source="likes", account=ann)["items"]
    assert not get(harness, "/ui/api/feed/posts", source="likes", account="douyin::https://example.test/bob")["items"]

    following = get(harness, "/ui/api/feed/posts", source="following")["items"]
    assert {item["author"]["key"] for item in following} == {ann}
    me = get(harness, "/ui/api/feed/me")
    assert (me["likes"], me["saves"], me["following"], me["hidden"]) == (1, 1, 1, 0)
    assert get(harness, "/ui/api/feed/accounts", scope="following")["total"] == 1
    assert get(harness, "/ui/api/feed/account", key=ann)["liked"] == 1

    assert put_mark(harness, "like", key, on=False).status_code == 200
    assert get(harness, "/ui/api/feed/posts", source="likes")["items"] == []


def test_following_is_empty_until_someone_is_followed(harness):
    assert get(harness, "/ui/api/feed/posts", source="following")["items"] == []


@pytest.mark.parametrize("source", ["account", "likes", "saves"])
def test_profile_posts_refresh_renamed_files_before_returning_links(harness, source):
    account = "douyin::https://example.test/ann"
    key = "1:20260103100000:i"
    put_mark(harness, "like", key)
    put_mark(harness, "save", key)
    folder = harness.root / "UID1_Ann_发布作品"
    for path in folder.iterdir():
        path.rename(path.with_name(path.name.replace("-Ann-", "-Renamed-")))

    # The grid can request posts before the parallel profile request refreshes
    # the index. It must never publish the cached, now missing filenames.
    items = get(harness, "/ui/api/feed/posts", source=source, account=account)["items"]
    assert items
    for post in items:
        assert (harness.root / post["cover"]).is_file()
        assert all((harness.root / media["path"]).is_file() for media in post["media"])
    photos = next(post for post in items if post["key"] == key)
    assert photos["liked"] and photos["saved"]
    response = harness.client.get(
        "/ui/api/feed/thumb", params={"path": photos["cover"]}, headers=HEADERS,
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"


def test_marks_survive_a_rebuild_of_the_index(harness):
    key = "1:20260101100000:v"
    put_mark(harness, "like", key)
    index_path = harness.service.index.path
    for suffix in ("", "-wal", "-shm"):
        Path(f"{index_path}{suffix}").unlink(missing_ok=True)
    harness.service.index._prepared = False
    harness.service.worker.run_once()
    assert get(harness, "/ui/api/feed/post", key=key)["liked"] is True
    assert (harness.tmp / "ui_feed_state.sqlite3").exists()


def test_marks_validate_targets_but_can_always_be_removed(harness):
    assert put_mark(harness, "like", "missing").status_code == 404
    assert put_mark(harness, "follow", "missing").status_code == 404
    assert put_mark(harness, "like", "missing", on=False).status_code == 200
    bad = harness.client.put(
        "/ui/api/feed/marks", headers=HEADERS, json={"kind": "boost", "target": "x", "on": True},
    )
    assert bad.status_code == 422


def test_hidden_accounts_leave_discovery_and_can_be_restored(harness):
    bob = "douyin::https://example.test/bob"
    put_mark(harness, "hide", bob)
    for source in ("latest", "foryou"):
        authors = {item["author"]["key"] for item in get(harness, "/ui/api/feed/posts", source=source, limit=20)["items"]}
        assert bob not in authors
    response = harness.client.delete("/ui/api/feed/marks?kind=hide", headers=HEADERS)
    assert response.json() == {"cleared": 1}
    authors = {item["author"]["key"] for item in get(harness, "/ui/api/feed/posts", source="latest")["items"]}
    assert bob in authors


def test_avatar_prefers_generated_then_pinned_then_newest(harness):
    server = harness.server
    ann = "douyin::https://example.test/ann"
    account = lambda: get(harness, "/ui/api/feed/account", key=ann)["avatar"]
    assert account()["path"].endswith("photos_1.jpeg")

    pinned = "UID1_Ann_发布作品/2026-01-02 10.00.00-视频-Ann-two.mp4"
    server._save_account_board_pins({ann: {"path": pinned, "source": "manual", "second": 3}})
    assert account() == {"scope": "download", "path": pinned, "second": 3}

    server._load_account_board_avatars = lambda: {ann: "profile_avatars/ann.png"}
    server._account_board_avatar_file().write_text("{}", encoding="utf-8")
    assert account() == {"scope": "project", "path": "profile_avatars/ann.png", "second": 0}


def test_pinned_cover_leads_the_profile_once(harness):
    server = harness.server
    ann = "douyin::https://example.test/ann"
    pinned = "UID1_Ann_发布作品/2026-01-01 10.00.00-视频-Ann-one #fun.mp4"
    server._save_account_board_pins({ann: {"path": pinned, "source": "manual"}})
    first = get(harness, "/ui/api/feed/posts", source="account", account=ann, limit=1)
    keys = [item["key"] for item in first["items"]]
    assert keys[0] == "1:20260101100000:v" and first["items"][0]["pinned"] is True
    assert first["next_cursor"]
    rest = get(harness, "/ui/api/feed/posts", source="account", account=ann, limit=1, cursor=first["next_cursor"])
    assert "1:20260101100000:v" not in [item["key"] for item in rest["items"]]
    assert len(keys) + len(rest["items"]) == 3


def test_thumbnails_downscale_cache_and_stay_in_scope(harness):
    client = harness.client
    path = "UID1_Ann_发布作品/2026-01-03 10.00.00-图集-Ann-photos_1.jpeg"
    response = client.get("/ui/api/feed/thumb", params={"path": path, "w": 240}, headers=HEADERS)
    assert response.status_code == 200 and response.headers["content-type"] == "image/jpeg"
    assert response.headers["cache-control"].startswith("private")
    from io import BytesIO

    with Image.open(BytesIO(response.content)) as image:
        assert image.width <= 240
    again = client.get(
        "/ui/api/feed/thumb",
        params={"path": path, "w": 240},
        headers={**HEADERS, "If-None-Match": response.headers["etag"]},
    )
    assert again.status_code == 304

    assert client.get("/ui/api/feed/thumb", params={"path": "../secret.jpg"}, headers=HEADERS).status_code == 400
    assert client.get("/ui/api/feed/thumb", params={"path": "UID1_Ann_发布作品/none.jpg"}, headers=HEADERS).status_code == 404
    # A broken clip reports failure instead of hanging or leaking details.
    bad = client.get(
        "/ui/api/feed/thumb",
        params={"path": "UID1_Ann_发布作品/2026-01-02 10.00.00-视频-Ann-two.mp4"},
        headers=HEADERS,
    )
    assert bad.status_code == 422


def test_project_scope_only_serves_images(harness, monkeypatch, tmp_path):
    settings = tmp_path / "settings_scope"
    settings.mkdir()
    (settings / "clip.mp4").write_bytes(b"x")
    make_image(settings / "face.jpg", size=(64, 64))
    original = harness.server._scope_root
    monkeypatch.setattr(
        harness.server, "_scope_root", lambda scope: settings if scope == "project" else original(scope),
    )
    client = harness.client
    assert client.get("/ui/api/feed/thumb", params={"path": "face.jpg", "scope": "project"}, headers=HEADERS).status_code == 200
    assert client.get("/ui/api/feed/thumb", params={"path": "clip.mp4", "scope": "project"}, headers=HEADERS).status_code == 404


def seed_work_id(harness, work_id="123"):
    with harness.service.index._connect() as connection:
        connection.execute(
            "INSERT INTO meta (uid, time_key, work_id, comments) VALUES (?, ?, ?, ?)",
            ("1", "20260101100000", work_id, 9),
        )


RAW_COMMENT = {
    "cid": "c1",
    "text": "nice",
    "digg_count": 7,
    "create_time": 1700000000,
    "ip_label": "somewhere",
    "reply_comment_total": 2,
    "user": {
        "nickname": "viewer",
        "avatar_thumb": {"url_list": ["https://example.test/a.jpg"]},
        "sec_uid": "must-not-pass-through",
    },
}


class FakeFetcher:
    created = []
    answer = [RAW_COMMENT]

    def __init__(self, params, cookie, proxy, **options):
        self.options = options
        self.cookie = cookie
        self.request_delay = 6.0
        self.last_response_payload = {"status_code": 0}
        self.finished = True
        self.cursor = 0
        FakeFetcher.created.append(self)

    async def run(self):
        assert self.request_delay == 0, "an interactive fetch must not sleep after the response"
        return FakeFetcher.answer


@pytest.fixture
def live_comments(harness, monkeypatch):
    FakeFetcher.created = []
    FakeFetcher.answer = [RAW_COMMENT]
    monkeypatch.setattr(feed_routes, "CommentFetcher", FakeFetcher)
    monkeypatch.setattr(feed_routes, "ReplyFetcher", FakeFetcher)
    executions = []

    async def execute(**options):
        executions.append(options)
        worker = SimpleNamespace(parameter=harness.server.parameter)
        credentials = SimpleNamespace(cookie="identity-cookie", proxy="")
        result, ok, failed = await options["operation"](worker, credentials, "identity")
        executions[-1]["counts"] = (ok, failed)
        return result, "identity", "policy"

    harness.server._execute_collector_operation = execute
    harness.executions = executions
    seed_work_id(harness)
    return harness


def test_comments_go_through_identity_routing_and_are_cached(live_comments):
    harness = live_comments
    first = get(harness, "/ui/api/feed/comments", key="1:20260101100000:v")
    assert first["items"][0]["text"] == "nice" and first["items"][0]["author"] == "viewer"
    assert "must-not-pass-through" not in str(first)
    assert first["next_cursor"] is None
    get(harness, "/ui/api/feed/comments", key="1:20260101100000:v")
    assert len(FakeFetcher.created) == 1, "a repeat view is served from the cache"
    execution = harness.executions[0]
    assert execution["target_key"] == "123" and execution["counts"] == (1, 0)
    assert FakeFetcher.created[0].cookie == "identity-cookie"
    assert FakeFetcher.created[0].options["pages"] == 1


def test_replies_use_the_reply_endpoint(live_comments):
    harness = live_comments
    get(harness, "/ui/api/feed/comments", key="1:20260101100000:v", reply_to="c1")
    assert FakeFetcher.created[0].options["comment_id"] == "c1"
    assert harness.executions[0]["target_type"] == "reply"


def test_the_configured_delay_spaces_fetches_without_delaying_the_answer(live_comments):
    harness = live_comments
    harness.server.parameter.request_delay = 0.4
    started = monotonic()
    get(harness, "/ui/api/feed/comments", key="1:20260101100000:v")
    assert monotonic() - started < 0.3, "the first answer comes back immediately"
    get(harness, "/ui/api/feed/comments", key="1:20260101100000:v", cursor=20)
    assert monotonic() - started >= 0.4, "the next live fetch still waits its turn"


def test_a_post_without_comments_does_not_count_against_the_identity(live_comments):
    harness = live_comments
    FakeFetcher.answer = []
    with harness.service.index._connect() as connection:
        connection.execute("UPDATE meta SET comments = 0")
    payload = get(harness, "/ui/api/feed/comments", key="1:20260101100000:v")
    assert payload == {"items": [], "next_cursor": None}
    assert harness.executions[0]["counts"] == (1, 0)


def test_comment_failures_become_a_calm_message(live_comments):
    from fastapi import HTTPException

    harness = live_comments

    async def refused(**options):
        raise HTTPException(status_code=409, detail="no eligible collector identity")

    harness.server._execute_collector_operation = refused
    payload = get(harness, "/ui/api/feed/comments", key="1:20260101100000:v")
    assert payload["items"] == [] and payload["unavailable"] == "当前没有可用的采集身份"

    async def broken(**options):
        raise RuntimeError("secret upstream detail")

    harness.server._execute_collector_operation = broken
    payload = get(harness, "/ui/api/feed/comments", key="1:20260101100000:v")
    assert payload["unavailable"] == "评论暂时无法加载"
    assert "secret" not in str(payload)

    async def empty(**options):
        return ([], None), "identity", "policy"

    harness.server._execute_collector_operation = empty
    payload = get(harness, "/ui/api/feed/comments", key="1:20260101100000:v")
    assert payload["unavailable"]  # the post reports comments, so empty means refused

    payload = get(harness, "/ui/api/feed/comments", key="1:20260102100000:v")
    assert payload["unavailable"] == "这条作品没有可用的作品 ID"


@pytest.mark.parametrize("reply_to", ["", "c1"])
def test_real_fetchers_page_through_the_platform_response(harness, monkeypatch, reply_to):
    """Everything but the network call is the production comment code."""
    from rich.console import Console

    from src.interface import Comment, Reply

    requests = []

    async def respond(self, url, params=None, *args, **kwargs):
        requests.append({"url": url, "cursor": self.cursor, "delay": self.request_delay})
        self.last_response_payload = {"status_code": 0}
        return {"comments": [RAW_COMMENT], "cursor": 40, "has_more": 1}

    monkeypatch.setattr(Comment, "request_data", respond)
    monkeypatch.setattr(Reply, "request_data", respond)
    parameter = SimpleNamespace(
        headers={}, api_params={}, logger=SimpleNamespace(info=lambda *a: None, warning=lambda *a: None, error=lambda *a: None),
        ab=None, console=Console(quiet=True), max_retry=0, timeout=5, request_delay=6.0,
        client=None, proxy=None, max_pages=0, root=harness.root,
        settings=harness.server.parameter.settings,
    )

    async def execute(**options):
        result, ok, failed = await options["operation"](
            SimpleNamespace(parameter=parameter), SimpleNamespace(cookie="", proxy=""), "",
        )
        assert (ok, failed) == (1, 0)
        return result, "", "global_fallback"

    harness.server._execute_collector_operation = execute
    seed_work_id(harness)
    params = {"key": "1:20260101100000:v", "cursor": 20}
    if reply_to:
        params["reply_to"] = reply_to
    payload = get(harness, "/ui/api/feed/comments", **params)
    assert payload["items"][0]["text"] == "nice"
    assert payload["next_cursor"] == 40, "the platform's cursor, not a guess"
    assert len(requests) == 1 and requests[0]["cursor"] == 20 and requests[0]["delay"] == 0
    assert ("reply" in requests[0]["url"]) is bool(reply_to)


def test_comment_payload_ignores_malformed_and_unsafe_values():
    assert comment_payload({})["text"] == ""
    payload = comment_payload(
        {"user": {"avatar_thumb": {"url_list": ["javascript:alert(1)"]}}, "digg_count": "bad", "image_list": [{}]},
    )
    assert payload["avatar"] == "" and payload["likes"] == 0 and payload["image"] == ""


def test_state_store_keeps_first_time_and_ranks_affinity(tmp_path):
    state = FeedState(tmp_path / "state.sqlite3")
    state.set_mark("like", "p1", True, "a1")
    state.set_mark("save", "p2", True, "a2")
    state.set_mark("follow", "a3", True)
    state.set_mark("like", "p1", True, "a1")
    assert state.counts() == {"follow": 1, "hide": 0, "like": 1, "save": 1}
    assert set(state.affinity_accounts()) == {"a1", "a2", "a3"}
    assert state.marked("like", ["p1", "p9"]) == {"p1"}
    assert state.marked("like", []) == set()
    assert state.page("like", limit=5) == (["p1"], 1)
    assert state.page("like", limit=5, account_key="a9") == ([], 0)
    with pytest.raises(ValueError):
        state.set_mark("boost", "p1", True)
    assert state.clear("follow") == 1
