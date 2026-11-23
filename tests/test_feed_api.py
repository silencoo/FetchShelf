from pathlib import Path
import sqlite3
from time import monotonic, time
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
        deleted_accounts=[],
        deleted_accounts_tiktok=[],
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
        ("get", "/ui/api/feed/liked-accounts"),
        ("get", "/ui/api/feed/saved-accounts"),
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


@pytest.mark.parametrize(
    ("mark", "source", "path", "other_mark"),
    [
        ("like", "likes", "/ui/api/feed/liked-accounts", "save"),
        ("save", "saves", "/ui/api/feed/saved-accounts", "like"),
    ],
)
def test_marked_accounts_group_posts_and_page_by_latest_mark(harness, mark, source, path, other_mark):
    ann_key = "douyin::https://example.test/ann"
    bob_key = "douyin::https://example.test/bob"
    assert get(harness, path) == {"items": [], "next_offset": None}

    first, second = "1:20260101100000:v", "1:20260102100000:v"
    gallery, bob = "1:20260103100000:i", "2:20260201100000:v"
    assert put_mark(harness, other_mark, gallery).status_code == 200
    assert get(harness, path)["items"] == []
    for key in (first, second, gallery, bob):
        assert put_mark(harness, mark, key).status_code == 200
    result = get(harness, path, limit=1, platform="douyin")
    assert result["next_offset"] == 1
    assert result["items"][0]["author"]["key"] == bob_key
    assert result["items"][0]["count"] == 1

    group = get(harness, path, limit=1, offset=1)["items"][0]
    assert group["author"]["key"] == ann_key
    assert group["count"] == 3
    assert [post["key"] for post in group["previews"]] == [gallery, second, first]
    assert not get(harness, path, platform="tiktok")["items"]

    assert put_mark(harness, mark, gallery, on=False).status_code == 200
    linked = get(harness, "/ui/api/feed/posts", source=source, account=ann_key)
    assert linked["available_total"] == 2
    assert [post["key"] for post in linked["items"]] == [second, first]
    assert get(harness, path, offset=1, limit=1)["items"][0]["count"] == 2


@pytest.mark.parametrize("caption", ["7708565108570498673", "12345", "1234567890123456789"])
def test_feed_hides_id_placeholder_and_preserves_other_numeric_captions(harness, caption):
    work_id = "7708565108570498673"
    harness.service.index.apply_detail_rows(
        "1",
        [("2026-01-01 10:00:00", work_id, caption, "", "", "", None, None, "",
          "", "", "", "", "", "", None, None, None, None, None)],
        "UID1_Ann_发布作品",
        1,
    )
    post = get(harness, "/ui/api/feed/post", key="1:20260101100000:v")
    assert post["caption"] == ("" if caption == work_id else caption)
    assert post["work_id"] == work_id
    assert post["share_url"] == f"https://www.douyin.com/video/{work_id}"


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


def test_archived_profile_keeps_its_media_and_shows_reason_until_restored(harness):
    server = harness.server
    rows = server._active_account_rows("douyin")
    ann = rows.pop(0)
    server.parameter.deleted_accounts = [
        {**ann, "reason": "自动归档：已注销", "deleted_at": "2025-01-02 03:04:05"}
    ]
    harness.service.worker.run_once()
    key = "douyin::https://example.test/ann"
    assert get(harness, "/ui/api/feed/accounts", q="Ann")["items"][0]["key"] == key
    post = get(harness, "/ui/api/feed/posts", source="account", account=key)["items"][0]
    profile = get(harness, "/ui/api/feed/account", key=post["author"]["key"])
    assert profile["stats"]["posts"] == 3
    assert profile["archive"]["removed_at"].startswith("2025-01-02T03:04:05")
    assert profile["archive"]["reason"] == "自动归档：已注销"
    assert put_mark(harness, "block", key).status_code == 200
    assert get(harness, "/ui/api/feed/account", key=key)["blocked"]
    assert get(harness, "/ui/api/accounts/board", status="blocked")["total"] == 0
    rows.append(ann)
    harness.service.worker.run_once()
    assert get(harness, "/ui/api/feed/account", key=key)["archive"] is None


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


def test_block_account_for_board_review_and_unblock(harness):
    key = "douyin::https://example.test/bob"
    account_route = "/ui/api/feed/account"
    posts_route = "/ui/api/feed/posts"
    board_route = "/ui/api/accounts/board"

    assert put_mark(harness, "follow", key).status_code == 200
    assert get(harness, account_route, key=key)["can_block"]
    assert put_mark(harness, "block", key).status_code == 200
    assert put_mark(harness, "block", key).status_code == 200
    assert get(harness, account_route, key=key)["blocked"]
    for source in ("latest", "following", "foryou", "popular"):
        assert all(post["author"]["key"] != key for post in get(harness, posts_route, source=source)["items"])
    assert get(harness, posts_route, source="account", account=key)["items"]
    assert get(harness, "/ui/api/feed/accounts", scope="following")["total"] == 0
    assert get(harness, "/ui/api/feed/accounts", q="Bob")["items"][0]["key"] == key

    # A newly opened dashboard reads the durable mark without starting the feed worker.
    del harness.server.feed_state
    del harness.server._feed_service
    page = get(harness, board_route, status="blocked", search="Bo")
    assert page["unfiltered_total"] == 2
    assert page["total"] == 1
    assert page["items"][0]["mark"] == "Bob"
    assert page["items"][0]["blocked"]
    assert get(harness, board_route, status="blocked", search="Ann")["total"] == 0
    assert get(harness, board_route, status="blocked", platform="tiktok")["total"] == 0
    assert not hasattr(harness.server, "_feed_service")
    harness.server._feed_service = harness.service
    assert put_mark(harness, "block", key, on=False).status_code == 200
    assert not get(harness, account_route, key=key)["blocked"]
    assert get(harness, board_route, status="blocked")["total"] == 0
    assert get(harness, posts_route, source="following")["items"][0]["author"]["key"] == key


def test_avatar_prefers_generated_then_pinned_then_newest(harness, monkeypatch):
    server = harness.server
    ann = "douyin::https://example.test/ann"
    account = lambda: get(harness, "/ui/api/feed/account", key=ann)["avatar"]
    assert account()["path"].endswith("photos_1.jpeg")

    pinned = "UID1_Ann_发布作品/2026-01-02 10.00.00-视频-Ann-two.mp4"
    server._save_account_board_pins({ann: {"path": pinned, "source": "manual", "second": 3}})
    assert account() == {"scope": "download", "path": pinned, "second": 3}

    project = harness.tmp / "project"
    (project / "profile_avatars").mkdir(parents=True)
    make_image(project / "profile_avatars/ann.png")
    monkeypatch.setattr(server, "_scope_root", lambda scope: project if scope == "project" else harness.root)
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
    assert state.counts() == {"block": 0, "follow": 1, "hide": 0, "like": 1, "save": 1}
    assert set(state.affinity_accounts()) == {"a1", "a2", "a3"}
    assert state.marked("like", ["p1", "p9"]) == {"p1"}
    assert state.marked("like", []) == set()
    assert state.page("like", limit=5) == (["p1"], 1)
    assert state.page("like", limit=5, account_key="a9") == ([], 0)
    with pytest.raises(ValueError):
        state.set_mark("boost", "p1", True)
    assert state.clear("follow") == 1


@pytest.mark.parametrize("rename_folder", [False, True])
def test_discover_repairs_old_pin_preserving_photo_number(harness, rename_folder):
    key = "douyin::https://example.test/ann"
    old = "UID1_Ann_发布作品/2026-01-03 10.00.00-图集-Ann-photos_2.jpeg"
    pin = {"path": old, "source": "manual", "second": 2}
    harness.server._save_account_board_pins({key: pin})
    # Prime the pin cache, then rename without changing the pin settings file.
    assert harness.service.avatar_for(key, old)["path"] == old
    original = harness.root / old
    renamed = original.with_name(original.name.replace("-Ann-", "-Renamed-"))
    original.rename(renamed)
    if rename_folder:
        folder = renamed.parent.with_name("UID1_Renamed_发布作品")
        renamed.parent.rename(folder)
        renamed = folder / renamed.name
    expected = renamed.relative_to(harness.root).as_posix()
    # Use the current cover's folder even before the background scan updates files.
    result = harness.service.avatar_for(key, expected.replace("_2.jpeg", "_1.jpeg"))
    assert result == {"scope": "download", "path": expected, "second": 2}
    assert harness.server._load_account_board_pins()[key] == {**pin, "path": expected}
    response = harness.client.get("/ui/api/feed/thumb", params={"path": result["path"]}, headers=HEADERS)
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"


@pytest.mark.parametrize("failure", ["missing", "ambiguous", "other_account", "outside", "symlink"])
def test_invalid_pin_falls_back_without_changing_selection(harness, failure):
    key = "douyin::https://example.test/ann"
    folder = harness.root / "UID1_Ann_发布作品"
    fallback = (folder / "2026-01-03 10.00.00-图集-Ann-photos_1.jpeg").relative_to(harness.root).as_posix()
    old = folder / "2026-01-03 10.00.00-图集-Ann-photos_2.jpeg"
    old.unlink()
    if failure == "ambiguous":
        for nickname in ("New", "Another"):
            make_image(old.with_name(old.name.replace("-Ann-", f"-{nickname}-")))
    elif failure == "symlink":
        external = harness.tmp / "outside.jpeg"
        make_image(external)
        old.symlink_to(external)
    path = old.relative_to(harness.root).as_posix()
    if failure == "other_account":
        path = path.replace("UID1_", "UID2_")
    elif failure == "outside":
        path = "../outside.jpeg"
        make_image(harness.tmp / "outside.jpeg")
    pin = {"path": path, "source": "manual", "second": 3}
    harness.server._save_account_board_pins({key: pin})
    assert harness.service.avatar_for(key, fallback) == {"scope": "download", "path": fallback, "second": 0}
    assert harness.server._load_account_board_pins()[key] == pin


def test_missing_generated_avatar_and_missing_fallback_do_not_return_bad_urls(harness):
    key = "douyin::https://example.test/ann"
    harness.server._load_account_board_avatars = lambda: {key: "profile_avatars/deleted.png"}
    assert harness.service.avatar_for(key, "deleted.jpeg") is None
    fallback = "UID1_Ann_发布作品/2026-01-03 10.00.00-图集-Ann-photos_1.jpeg"
    assert harness.service.avatar_for(key, fallback)["path"] == fallback


def test_shared_preferences_merge_initialize_validate_and_persist(harness):
    url = "/ui/api/feed/preferences"
    assert harness.client.get(url).status_code == 403
    assert harness.client.patch(url, json={"sound": False}).status_code == 403
    assert get(harness, url) == {}
    first = {"sound": False, "autoNext": True, "showPauseIcon": False, "pinchZoom": True}
    response = harness.client.patch(url + "?initialize=true", headers=HEADERS, json=first)
    assert response.json() == first
    assert response.headers["cache-control"] == "no-store"
    # Another device's old local settings cannot overwrite the shared values.
    assert harness.client.patch(url + "?initialize=true", headers=HEADERS,
                                json={"sound": True, "autoNext": False}).json() == first
    harness.client.patch(url, headers=HEADERS, json={"sound": True})
    harness.client.patch(url, headers=HEADERS, json={"pinchZoom": False})
    ultra = {"ultraImmersive": True, "ultraOpenSingle": False, "ultraPauseBatch": True,
             "ultraRows": 10, "ultraColumns": 12, "ultraVideos": 16, "ultraLayout": "rows"}
    harness.client.patch(url, headers=HEADERS, json=ultra)
    expected = {**first, **ultra, "sound": True, "pinchZoom": False}
    assert harness.client.patch(url + "?initialize=true", headers=HEADERS,
                                json={"ultraRows": 1, "ultraImmersive": False, "ultraPauseBatch": False,
                                      "ultraLayout": "adaptive"}).json() == expected
    assert get(harness, url) == expected
    assert FeedState(harness.service.state.path).preferences() == expected
    for invalid in ({"sound": None}, {"sound": "false"}, {"unknown": True},
                    {"ultraRows": 0}, {"ultraColumns": 2**53}, {"ultraVideos": True},
                    {"ultraVideos": "2"}, {"ultraRows": 1.5}, {"ultraLayout": 1}, {"ultraLayout": "unknown"},
                    {"ultraPauseBatch": "true"}):
        assert harness.client.patch(url, headers=HEADERS, json=invalid).status_code == 422
    for layout in ("portrait", "adaptive"):
        expected["ultraLayout"] = layout
        result = harness.client.patch(url, headers=HEADERS, json={"ultraLayout": layout})
        assert result.status_code == 200 and result.json() == expected
        assert FeedState(harness.service.state.path).preferences() == expected


def test_preferences_upgrade_preserves_saved_limits_and_accepts_custom_values(tmp_path):
    path = tmp_path / "ui_feed_state.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE preference_limits "
                           "(key TEXT PRIMARY KEY, value INTEGER NOT NULL CHECK(value BETWEEN 1 AND 8)) WITHOUT ROWID")
        connection.execute("INSERT INTO preference_limits VALUES ('ultraRows', 4), ('ultraVideos', 2)")

    state = FeedState(path)
    assert state.preferences() == {"ultraRows": 4, "ultraVideos": 2}
    assert state.update_preferences({"ultraVideos": 12}) == {"ultraRows": 4, "ultraVideos": 12}
    assert FeedState(path).preferences() == {"ultraRows": 4, "ultraVideos": 12}


@pytest.mark.asyncio
async def test_arrivals_use_first_actual_media_save_and_page_the_entire_task(harness, monkeypatch):
    from src.downloader.download import Downloader
    from src.translation import _
    from src.webui import feed_state

    state = harness.server.feed_state
    now = int(time())
    folder = harness.root / "UID1_Ann_发布作品"
    account = {"url": "https://example.test/ann", "mark": "Ann"}
    path = "/ui/api/feed/posts"
    state.start_arrival_run("T19", partial=False)
    state.start_arrival_run("T20", partial=False)
    count = SimpleNamespace(account_folder=folder, downloaded_video=set(), downloaded_image=set(), downloaded_live=set())
    monkeypatch.setattr(feed_state, "time", lambda: now - 8 * 86400)
    with harness.server._observe_account_downloads("douyin", account, "T19"):
        file = folder / "2020-01-01 01.00.00-视频-Ann-old.mp4"
        file.touch()
        Downloader.add_count(f"【{_('视频')}】old", "old", count, file)
    monkeypatch.setattr(feed_state, "time", lambda: now)
    with harness.server._observe_account_downloads("douyin", account, "T20"):
        for i in range(39):
            file = folder / f"2020-01-01 02.00.{i:02d}-视频-Ann-{i}.mp4"
            file.touch()
            Downloader.add_count(f"【{_('视频')}】{i}", str(i), count, file)
        for slide in (1, 2):
            file = folder / f"2020-01-01 03.00.00-图集-Ann-trip_{slide}.jpeg"
            make_image(file)
            Downloader.add_count(f"【{_('图集')}】trip", "trip", count, file)
        Downloader.add_count(f"【{_('音乐')}】music", "sidecar", count, file)
    # A later successful transfer of the same work cannot take credit or move the seven-day window.
    with harness.server._observe_account_downloads("douyin", account, "T21"):
        count.downloaded_video.clear()
        Downloader.add_count(f"【{_('视频')}】old", "old", count, folder / "2020-01-01 01.00.00-视频-Ann-old.mp4")
    page = get(harness, path, source="arrivals", task_id="T20", limit=12)
    assert page["available_total"] == 40
    assert page["summary"] == {"total": 40, "videos": 39, "images": 1, "live": 0, "tracked": True, "partial": False}
    assert len(page["items"][0]["media"]) == 2
    posts = list(page["items"])
    while page["next_cursor"]:
        page = get(harness, path, source="arrivals", task_id="T20", limit=12, cursor=page["next_cursor"])
        posts.extend(page["items"])
    assert len({p["key"] for p in posts}) == 40
    assert all(p["first_saved_at"] == now and p["published_ts"] < now - 86400 * 365 for p in posts)
    assert len(get(harness, path, source="arrivals", limit=60)["items"]) == 40
    assert not get(harness, path, source="arrivals", platform="tiktok")["items"]
    assert len(get(harness, path, source="arrivals", task_id="T19")["items"]) == 1
    assert not get(harness, path, source="arrivals", task_id="T21")["items"]
    # Alternate folders and identical publication timestamps must not replace a profile's posts.
    side = harness.root / "UID1_Ann_喜欢作品"
    side.mkdir()
    name = "2020-01-01 02.00.00-视频-Ann-other.mp4"
    (side / name).touch()
    count.account_folder = side
    with harness.server._observe_account_downloads("douyin", account, "T22"):
        Downloader.add_count(f"【{_('视频')}】other", "other", count, side / name)
    other = get(harness, path, source="arrivals", task_id="T22")["items"][0]
    assert other["key"] not in {p["key"] for p in posts}
    assert other["media"][0]["path"] == f"{side.name}/{name}"
    assert put_mark(harness, "save", other["key"]).status_code == 200
    assert get(harness, path, source="saves")["items"][0]["key"] == other["key"]
    assert get(harness, "/ui/api/feed/post", key=other["key"])["work_id"] == "other"
    (side / name).unlink()
    assert get(harness, path, source="arrivals", task_id="T22")["items"] == []
    assert put_mark(harness, "block", "douyin::https://example.test/ann").status_code == 200
    blocked = get(harness, path, source="arrivals", task_id="T20")
    assert blocked["summary"]["total"] == 40 and blocked["available_total"] == 0
    assert not blocked["items"]


@pytest.mark.asyncio
async def test_arrival_is_written_after_the_media_file_is_committed(harness):
    from unittest.mock import AsyncMock, Mock
    from httpx import ReadError
    from src.downloader.download import Downloader
    from src.translation import _

    folder = harness.root / "UID1_Ann_发布作品"
    final = folder / "2021-04-06 12.00.00-视频-Ann-confirmed.mp4"
    cache = harness.tmp / "transfer.part"
    writer = Downloader.__new__(Downloader)
    writer.truncate, writer.chunk = 80, 1024
    writer.log, writer.recorder = Mock(), AsyncMock()
    count = SimpleNamespace(account_folder=folder, downloaded_video=set())
    account = {"url": "https://example.test/ann", "mark": "Ann"}

    async def failing(_):
        yield b"partial"
        raise ReadError("interrupted")

    async def complete(_):
        yield b"saved"

    args = (cache, final, f"【{_('视频')}】sample", "fresh")
    tail = (5, 0, count, Mock())
    with harness.server._observe_account_downloads("douyin", account, "T90"):
        assert not await writer.download_file(*args, SimpleNamespace(aiter_bytes=failing), *tail)
        assert not final.exists()
        assert harness.service.state.arrival_summary("T90")["total"] == 0
        cache.unlink()
        assert await writer.download_file(*args, SimpleNamespace(aiter_bytes=complete), *tail)
    assert final.read_bytes() == b"saved"
    page = get(harness, "/ui/api/feed/posts", source="arrivals", task_id="T90")
    assert page["summary"]["total"] == 1
    assert page["items"][0]["media"][0]["path"].endswith(final.name)
