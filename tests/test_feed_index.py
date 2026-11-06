import sqlite3
from pathlib import Path

import pytest

from src.webui.feed_index import (
    AccountSource,
    FeedIndex,
    FeedWorker,
    decode_cursor,
    encode_cursor,
    name_from_folder,
    parse_media_name,
    scan_folder,
    time_key_from_text,
    uid_from_folder,
)

DETAIL_COLUMNS = (
    "作品类型", "采集时间", "UID", "SEC_UID", "ID", "作品ID", "作品描述", "作品话题", "视频时长",
    "视频高度", "视频宽度", "作品链接", "发布时间", "视频URI", "账号昵称", "年龄", "账号签名",
    "下载地址", "音乐作者", "音乐标题", "音乐链接", "静态封面", "动态封面", "隐藏标签", "点赞数量",
    "评论数量", "收藏数量", "分享数量", "播放数量", "额外信息",
)


def touch(folder: Path, *names: str) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for name in names:
        folder.joinpath(name).write_bytes(b"fixture")


def source(root: Path, name: str, folder: str | None = None) -> AccountSource:
    return AccountSource(
        key=f"douyin::https://example.test/{name}",
        platform="douyin",
        url=f"https://example.test/{name}",
        mark=name,
        folder=root / folder if folder else None,
    )


def detail_database(root: Path, table: str, rows: list[dict]) -> Path:
    path = root / "Data" / "DetailData.db"
    path.parent.mkdir(exist_ok=True)
    connection = sqlite3.connect(path)
    columns = ", ".join(f'"{column}"' for column in DETAIL_COLUMNS)
    connection.execute(f'CREATE TABLE IF NOT EXISTS "{table}" ({columns})')
    for row in rows:
        values = [row.get(column, "") for column in DETAIL_COLUMNS]
        marks = ",".join("?" for _ in DETAIL_COLUMNS)
        connection.execute(f'INSERT INTO "{table}" VALUES ({marks})', values)
    connection.commit()
    connection.close()
    return path


@pytest.mark.parametrize(
    ("name", "time_key", "kind", "index", "caption"),
    [
        ("2026-09-25 20.22.24-视频-Ann-sample dance.mp4", "20260925202224", "video", 0, "sample dance"),
        ("2026-01-01 09.56.05-图集-Ann-hello #tag_3.jpeg", "20260101095605", "images", 3, "hello #tag"),
        ("2025-05-05 01.02.03-实况-Ann-moment_2.mp4", "20250505010203", "live", 2, "moment"),
        ("2026-02-02 02.02.02-Video-Ann-english.mp4", "20260202020202", "video", 0, "english"),
        ("2026-02-02 02.02.02-LivePhoto-Ann-en_1.jpeg", "20260202020202", "live", 1, "en"),
        ("2024-12-28 14-42-53_sample_#tag_#fun_image_3.jpg", "20241228144253", "images", 3, "sample #tag #fun"),
        ("2024-09-14 10-13-54_sample_clip_video.mp4", "20240914101354", "video", 0, "sample clip"),
        # A caption can end in an index-like suffix; only carousels strip it.
        ("2026-03-03 03.03.03-视频-Ann-episode_2.mp4", "20260303030303", "video", 0, "episode_2"),
    ],
)
def test_parses_both_download_naming_schemes(name, time_key, kind, index, caption):
    parsed = parse_media_name(name, "Ann")
    assert (parsed.time_key, parsed.kind, parsed.index, parsed.caption) == (time_key, kind, index, caption)


def test_unusual_names_still_become_posts_without_inventing_a_time():
    parsed = parse_media_name("holiday_3.jpg")
    assert (parsed.time_key, parsed.kind, parsed.index, parsed.base) == ("", "images", 3, "holiday")
    parsed = parse_media_name("2026-13-45 25.61.61-视频-Ann-bad date.mp4")
    assert parsed.time_key == ""
    assert parse_media_name("holiday.mp4").kind == "video"


def test_groups_files_into_posts_and_merges_redownloaded_stems(tmp_path):
    folder = tmp_path / "UID7_Ann_发布作品"
    touch(
        folder,
        "2026-01-01 10.00.00-图集-Ann-trip_2.jpeg",
        "2026-01-01 10.00.00-图集-Ann-trip_1.jpeg",
        "2026-01-01 10.00.00-图集-Ann-trip_10.jpeg",
        "2026-02-01 10.00.00-实况-Ann-mixed_1.jpeg",
        "2026-02-01 10.00.00-实况-Ann-mixed_2.mp4",
        "2026-03-01 10.00.00-视频-Ann-clip.mp4",
        "2026-03-01 10.00.00-视频-Ann-clip.jpeg",
        # The same work saved again after its caption was edited.
        "2026-04-01 10.00.00-视频-Ann-old caption.mp4",
        "2026-04-01 10.00.00-视频-Ann-new caption.mp4",
        "2026-05-01 10.00.00-视频-Ann-7690929144531524442.mp4",
        "notes.json",
        ".hidden.mp4",
    )
    posts = {post.time_key: post for post in scan_folder(folder, "7", "Ann")}
    assert len(posts) == 5

    carousel = posts["20260101100000"]
    assert carousel.kind == "images"
    assert carousel.post_key == "7:20260101100000:i"
    assert [name.rsplit("_", 1)[1] for name in carousel.files] == ["1.jpeg", "2.jpeg", "10.jpeg"]

    live = posts["20260201100000"]
    assert live.kind == "live"
    assert [Path(name).suffix for name in live.files] == [".jpeg", ".mp4"]

    video = posts["20260301100000"]
    assert video.kind == "video"
    assert video.files == ["2026-03-01 10.00.00-视频-Ann-clip.mp4"]
    assert video.poster == "2026-03-01 10.00.00-视频-Ann-clip.jpeg"

    assert len(posts["20260401100000"].files) == 1

    numeric = posts["20260501100000"]
    assert numeric.caption == ""
    assert numeric.work_hint == "7690929144531524442"


def test_folder_helpers():
    assert uid_from_folder("UID123_Ann_发布作品") == "123"
    assert uid_from_folder("weird").startswith("f")
    assert name_from_folder("UID123_Ann_B_发布作品") == "Ann_B"
    assert time_key_from_text("2026-09-20 17:06:24") == "20260920170624"
    assert time_key_from_text("yesterday") == ""


def test_cursor_round_trip_and_bad_input():
    assert decode_cursor(encode_cursor({"t": 1, "i": 2})) == {"t": 1, "i": 2}
    assert decode_cursor("") == {}
    assert decode_cursor("%%%") == {}
    assert decode_cursor(encode_cursor({"t": 1})[:-1] + "!") in ({}, {"t": 1})


def test_sync_is_incremental_and_retires_removed_posts_and_accounts(tmp_path):
    root = tmp_path / "media"
    touch(root / "UID1_Ann_发布作品", "2026-01-01 10.00.00-视频-Ann-one.mp4")
    index = FeedIndex(tmp_path / "index.sqlite3")
    account = source(root, "Ann", "UID1_Ann_发布作品")

    assert index.sync_account(account, root) is True
    assert index.sync_account(account, root) is False
    assert index.counts()["posts"] == 1
    first = index.post("1:20260101100000:v")
    assert first["name"] == "Ann" and first["uid"] == "1"

    added = root / "UID1_Ann_发布作品" / "2026-01-02 10.00.00-视频-Ann-two.mp4"
    added.write_bytes(b"fixture")
    assert index.sync_account(account, root) is True
    assert index.counts()["posts"] == 2
    # A work keeps its place in the shuffle across rescans.
    assert index.post("1:20260101100000:v")["shuffle"] == first["shuffle"]

    added.unlink()
    assert index.sync_account(account, root) is True
    assert index.post("1:20260102100000:v") is None

    assert index.retire_accounts(set()) == 1
    assert index.counts() == {"accounts": 0, "scanned": 0, "posts": 0}


def test_missing_folder_is_an_empty_account_not_an_error(tmp_path):
    index = FeedIndex(tmp_path / "index.sqlite3")
    assert index.sync_account(source(tmp_path, "Ghost"), tmp_path) is True
    assert index.counts()["posts"] == 0


def worker_for(index, root, sources):
    return FeedWorker(
        index,
        lambda: sources,
        lambda: root,
        lambda: root / "Data" / "DetailData.db",
        throttle=False,
    )


def test_crawl_rows_enrich_posts_and_newest_row_wins(tmp_path):
    root = tmp_path / "media"
    folder = "UID9_Ann_发布作品"
    touch(
        root / folder,
        "2026-01-01 10.00.00-视频-Ann-short caption....mp4",
        "2026-01-02 10.00.00-视频-Ann-no record.mp4",
    )
    base = {
        "作品ID": "111", "发布时间": "2026-01-01 10:00:00", "作品描述": "full caption #tag",
        "作品话题": "tag other", "隐藏标签": "topic", "视频时长": "00:01:05", "视频高度": 1280,
        "视频宽度": 720, "作品链接": "https://example.test/video/111", "账号昵称": "Nick",
        "音乐标题": "tune", "音乐作者": "singer", "音乐链接": "https://example.test/a.mp3",
        "点赞数量": 10, "评论数量": 2, "收藏数量": 3, "分享数量": 4, "播放数量": -1,
    }
    detail_database(root, f"UID9_Ann_发布作品", [base, {**base, "点赞数量": 25}])
    index = FeedIndex(tmp_path / "index.sqlite3")
    worker = worker_for(index, root, [source(root, "Ann", folder)])
    worker.run_once()

    enriched = index.post("9:20260101100000:v")
    assert enriched["full_caption"] == "full caption #tag"
    assert (enriched["likes"], enriched["comments"], enriched["saves"], enriched["shares"]) == (25, 2, 3, 4)
    assert enriched["plays"] is None  # -1 means unknown, never "negative plays"
    assert enriched["duration"] == 65
    assert (enriched["width"], enriched["height"]) == (720, 1280)
    assert enriched["work_id"] == "111"

    plain = index.post("9:20260102100000:v")
    assert plain["likes"] is None and plain["caption"] == "no record"

    account = index.account("douyin::https://example.test/Ann")
    assert account["total_likes"] == 25 and account["nickname"] == "Nick"
    assert worker.status.metadata_available and worker.status.metadata_total == 1

    # New crawl rows land incrementally from the stored watermark.
    detail_database(root, "UID9_Ann_发布作品", [{**base, "点赞数量": 40}])
    worker.run_once()
    assert index.post("9:20260101100000:v")["likes"] == 40
    assert index.detail_watermarks()["UID9_Ann_发布作品"] == 3


def test_a_database_that_did_not_change_is_not_read_again(tmp_path, monkeypatch):
    root = tmp_path / "media"
    folder = "UID9_Ann_发布作品"
    touch(root / folder, "2026-01-01 10.00.00-视频-Ann-one.mp4")
    detail_database(root, folder, [{"作品ID": "1", "发布时间": "2026-01-01 10:00:00"}])
    index = FeedIndex(tmp_path / "index.sqlite3")
    worker = worker_for(index, root, [source(root, "Ann", folder)])
    worker.run_once()
    monkeypatch.setattr(worker, "_sync_detail_table", lambda *args: pytest.fail("no change to read"))
    worker.run_once()


def test_only_posts_tables_enrich_an_account(tmp_path):
    root = tmp_path / "media"
    folder = "UID9_Ann_发布作品"
    touch(root / folder, "2026-01-01 10.00.00-视频-Ann-one.mp4")
    # Another person's liked work can share a timestamp; it must not relabel this post.
    detail_database(root, "UID9_Ann_喜欢作品", [{"作品ID": "x", "发布时间": "2026-01-01 10:00:00"}])
    index = FeedIndex(tmp_path / "index.sqlite3")
    worker_for(index, root, [source(root, "Ann", folder)]).run_once()
    assert index.post("9:20260101100000:v")["work_id"] is None


def test_worker_works_without_any_crawl_database(tmp_path):
    root = tmp_path / "media"
    folder = "UID9_Ann_发布作品"
    touch(root / folder, "2026-01-01 10.00.00-视频-Ann-from filename.mp4")
    index = FeedIndex(tmp_path / "index.sqlite3")
    worker = worker_for(index, root, [source(root, "Ann", folder)])
    worker.run_once()
    assert worker.status.metadata_available is False
    assert index.post("9:20260101100000:v")["caption"] == "from filename"


def library(tmp_path, accounts=6, posts=30):
    root = tmp_path / "media"
    index = FeedIndex(tmp_path / "index.sqlite3")
    sources = []
    for account in range(accounts):
        name = f"A{account}"
        folder = f"UID{account + 1}_{name}_发布作品"
        names = [
            f"2026-{(post % 12) + 1:02d}-{(post % 27) + 1:02d} 10.{account:02d}.{post % 60:02d}-视频-{name}-p{post}.mp4"
            for post in range(posts)
        ]
        touch(root / folder, *names)
        sources.append(source(root, name, folder))
        index.sync_account(sources[-1], root)
    return index, root, sources


def for_you_all_pages(index, **options):
    cursor = {}
    pages = []
    while cursor is not None:
        rows, cursor = index.foryou_page(limit=6, cursor=cursor, **options)
        pages.append(rows)
        cursor = decode_cursor(encode_cursor(cursor)) if cursor else None
        assert len(pages) < 200, "the feed must terminate"
    return pages


def test_for_you_shows_every_post_and_then_ends(tmp_path):
    index, _, _ = library(tmp_path, accounts=6, posts=20)
    # "recent" also spans the whole library here, which is the worst case for overlap.
    pages = for_you_all_pages(index, favorites=[], hidden=[], now=0)
    seen = {row["post_key"] for rows in pages for row in rows}
    assert len(seen) == 120
    for rows in pages:
        keys = [row["post_key"] for row in rows]
        assert len(keys) == len(set(keys)), "no repeats within a page"


def test_for_you_works_for_a_single_tiny_account(tmp_path):
    index, _, _ = library(tmp_path, accounts=1, posts=3)
    pages = for_you_all_pages(index, favorites=[], hidden=[], now=0)
    assert {row["post_key"] for rows in pages for row in rows} and len(
        {row["post_key"] for rows in pages for row in rows}
    ) == 3


def test_for_you_spaces_out_posts_by_the_same_author(tmp_path):
    rows = [{"account_key": key} for key in "aabbc"]
    ordered = [row["account_key"] for row in FeedIndex._spread_authors(rows)]
    assert sorted(ordered) == sorted("aabbc")
    assert all(left != right for left, right in zip(ordered, ordered[1:]))
    assert FeedIndex._spread_authors([]) == []


def test_for_you_on_an_empty_library(tmp_path):
    index = FeedIndex(tmp_path / "index.sqlite3")
    assert index.foryou_page(limit=6, cursor={}, favorites=[], hidden=[]) == ([], None)


def test_for_you_mixes_in_favorites_and_respects_hidden_accounts(tmp_path):
    index, _, sources = library(tmp_path, accounts=6, posts=30)
    favorite, hidden = sources[0].key, sources[1].key
    cursor = {}
    authors = []
    for _ in range(12):
        rows, cursor = index.foryou_page(
            limit=6, cursor=cursor, favorites=[favorite], hidden=[hidden], now=0,
        )
        authors += [row["account_key"] for row in rows]
        if cursor is None:
            break
    assert hidden not in authors
    assert authors.count(favorite) >= len(authors) * 0.15


def test_latest_pages_in_order_without_gaps(tmp_path):
    index, _, sources = library(tmp_path, accounts=3, posts=10)
    cursor = {}
    times = []
    keys = []
    while cursor is not None:
        rows, cursor = index.latest_posts(limit=7, cursor=cursor)
        times += [row["published_ts"] for row in rows]
        keys += [row["post_key"] for row in rows]
    assert times == sorted(times, reverse=True)
    assert len(keys) == len(set(keys)) == 30
    only, _ = index.latest_posts(limit=50, cursor={}, only=[sources[0].key])
    assert {row["account_key"] for row in only} == {sources[0].key}
    assert not {row["account_key"] for row in index.latest_posts(limit=50, cursor={}, hidden=[sources[0].key])[0]} & {sources[0].key}


def test_account_sorting_filters_and_search(tmp_path):
    root = tmp_path / "media"
    folder = "UID5_Ann_发布作品"
    touch(
        root / folder,
        "2026-01-01 10.00.00-视频-Ann-first #fun.mp4",
        "2026-01-02 10.00.00-视频-Ann-second.mp4",
        "2026-01-03 10.00.00-图集-Ann-third 100%_1.jpeg",
    )
    detail_database(root, folder, [
        {"作品ID": "1", "发布时间": "2026-01-01 10:00:00", "点赞数量": 5, "作品话题": "fun", "音乐标题": "song"},
        {"作品ID": "2", "发布时间": "2026-01-02 10:00:00", "点赞数量": 50, "作品描述": "second words"},
    ])
    index = FeedIndex(tmp_path / "index.sqlite3")
    account = source(root, "Ann", folder)
    worker_for(index, root, [account]).run_once()
    key = account.key
    order = lambda sort: [r["time_key"][6:8] for r in index.account_posts(key, limit=9, cursor={}, sort=sort)[0]]
    assert order("latest") == ["03", "02", "01"]
    assert order("oldest") == ["01", "02", "03"]
    assert order("popular") == ["02", "01", "03"]
    assert [r["kind"] for r in index.account_posts(key, limit=9, cursor={}, kind="images")[0]] == ["images"]
    assert len(index.account_posts(key, limit=9, cursor={}, kind="video")[0]) == 2
    first, cursor = index.account_posts(key, limit=2, cursor={})
    second, end = index.account_posts(key, limit=2, cursor=cursor)
    assert (len(first), len(second), end) == (2, 1, None)

    assert [r["likes"] for r in index.popular_posts(limit=5, cursor={})[0]] == [50, 5]
    assert len(index.search_posts("second", limit=5, cursor={})[0]) == 1
    assert len(index.search_posts("Ann", limit=5, cursor={})[0]) == 3
    # LIKE wildcards in a query are literal text.
    assert len(index.search_posts("100%", limit=5, cursor={})[0]) == 1
    assert index.search_posts("1%0", limit=5, cursor={})[0] == []
    assert len(index.search_posts("fun", field="tag", limit=5, cursor={})[0]) == 1
    assert len(index.search_posts("song", field="music", limit=5, cursor={})[0]) == 1
    assert index.top_tags() == [{"tag": "fun", "count": 1}]
    rows, total = index.accounts(query="an")
    assert total == 1 and rows[0]["name"] == "Ann"
    assert index.accounts(only=[])[1] == 0


def test_topic_suggestions_include_all_tags_ranked_by_frequency(tmp_path):
    root = tmp_path / "media"
    folder = "UID5_Ann_发布作品"
    touch(
        root / folder,
        "2026-01-01 10.00.00-视频-Ann-one.mp4",
        "2026-01-02 10.00.00-视频-Ann-two.mp4",
    )
    detail_database(root, folder, [
        {"作品ID": "1", "发布时间": "2026-01-01 10:00:00", "作品话题": "旅行 高中生 未成年日常"},
        {"作品ID": "2", "发布时间": "2026-01-02 10:00:00", "作品话题": "旅行 女高中生"},
    ])
    index = FeedIndex(tmp_path / "index.sqlite3")
    worker_for(index, root, [source(root, "Ann", folder)]).run_once()
    assert index.top_tags() == [
        {"tag": "旅行", "count": 2},
        {"tag": "女高中生", "count": 1},
        {"tag": "未成年日常", "count": 1},
        {"tag": "高中生", "count": 1},
    ]
    # Suggestions and search both retain the original metadata.
    assert len(index.search_posts("高中生", limit=5, cursor={})[0]) == 2


def test_schema_change_rebuilds_the_cache(tmp_path):
    path = tmp_path / "index.sqlite3"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE stale (x)")
    connection.execute("PRAGMA user_version = 999")
    connection.commit()
    connection.close()
    assert FeedIndex(path).counts()["accounts"] == 0
