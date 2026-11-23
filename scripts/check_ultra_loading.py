#!/usr/bin/env python3
"""Check that a slow cursor page cannot change a visible Ultra Immersive batch."""
import argparse
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import expect, sync_playwright


STATIC = Path(__file__).resolve().parents[1] / "src/webui/static"
ORIGIN = "https://ultra-fixture.test"
POSTER = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="128">'
    '<rect width="16" height="128" fill="#345"/></svg>'
)


def fixture_posts(start, end):
    return [
        {
            "key": f"post-{i}", "kind": "video", "caption": f"Post {i}", "tags": [],
            "width": 16, "height": 128, "duration": 8, "published_ts": 1700000000,
            "work_id": str(i), "share_url": "", "stats": None, "music": None,
            "media": [{"kind": "video", "path": f"{i}.mp4"}], "cover": "poster.svg",
            "liked": False, "saved": False, "pinned": False, "meta_pending": False,
            "author": {
                "key": "fixture", "name": "Fixture", "platform": "douyin",
                "url": "", "avatar": None, "followed": False,
            },
        }
        for i in range(start, end)
    ]


def check(engine, executable, viewport, static):
    with_browser = {"executable_path": executable} if executable else {}
    browser = engine.launch(**with_browser)
    try:
        mobile = viewport["width"] < 500
        page = browser.new_page(viewport=viewport, is_mobile=mobile, has_touch=mobile)
        page.add_init_script("localStorage.setItem('feed.ultra_immersive', '1')")
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        pending = {}
        page_sizes = []

        def serve(route):
            request = urlsplit(route.request.url)
            path = request.path
            if path == "/ui/feed":
                return route.fulfill(path=static / "index.html")
            if path.startswith("/ui/static/"):
                return route.fulfill(path=static / path.removeprefix("/ui/static/"))
            if path == "/ui/api/feed/posts":
                query = parse_qs(request.query)
                page_sizes.append(query["limit"][0])
                cursor = query.get("cursor", [""])[0]
                if not cursor:
                    return route.fulfill(json={"items": fixture_posts(0, 3), "next_cursor": "second"})
                pending[cursor] = route
                return
            if path == "/ui/api/feed/preferences":
                return route.fulfill(json={
                    "ultraImmersive": True, "ultraColumns": 8, "ultraRows": 1,
                    "ultraVideos": 8, "ultraLayout": "rows", "ultraOpenSingle": False,
                })
            if path == "/ui/api/feed/status":
                return route.fulfill(json={"phase": "idle", "posts": 25})
            if path == "/ui/api/feed/thumb":
                return route.fulfill(content_type="image/svg+xml", body=POSTER)
            if path == "/ui/api/file":
                return route.fulfill(status=404)
            return route.fulfill(json={"items": []})

        def wait_for_request(cursor):
            for _ in range(100):
                if cursor in pending:
                    return pending[cursor]
                page.wait_for_timeout(25)
            raise AssertionError(f"Feed did not request cursor {cursor!r}")

        def respond(cursor, **options):
            wait_for_request(cursor).fulfill(**options)
            del pending[cursor]

        pager = page.locator(".fa-ultra")
        batches = pager.locator(".fa-ultra-batch")
        active_tiles = batches.locator("xpath=self::*[not(@inert)]").locator(".fa-ultra-tile")

        def keys():
            return active_tiles.evaluate_all("tiles => tiles.map(tile => tile.getAttribute('aria-label'))")

        def go(index):
            pager.evaluate("(node, index) => { node.scrollTop = index * node.clientHeight; }", index)
            expect(batches.nth(index)).not_to_have_attribute("inert", "")

        page.route(ORIGIN + "/**", serve)
        page.goto(ORIGIN + "/ui/feed", wait_until="domcontentloaded")
        wait_for_request("second")
        expect(batches).to_have_count(0)
        expect(pager).to_have_attribute("aria-busy", "true")
        expect(pager.get_by_role("status", name="正在加载作品")).to_be_visible()
        respond("second", json={"items": fixture_posts(3, 15), "next_cursor": "third"})
        expect(active_tiles.first).to_be_visible()
        last_ready = batches.count() - 1
        go(last_ready)
        before = keys()
        expect(page.get_by_role("status", name="正在加载更多作品")).to_be_visible()
        respond("third", status=503, json={"detail": "Fixture temporary error"})
        page.get_by_role("button", name="重试", exact=True).click()
        respond("third", json={"items": fixture_posts(15, 25), "next_cursor": None})
        expect(pager).to_have_attribute("aria-busy", "false")
        assert keys() == before, (engine.name, before, keys())
        go(0)
        go(last_ready)
        assert keys() == before, (engine.name, before, keys())

        visited = []
        for index in range(batches.count()):
            go(index)
            visited.extend(keys())
        assert visited == [f"Fixture · Post {i}" for i in range(25)], visited
        assert page_sizes == ["24"] * 4, page_sizes
        assert not errors, errors
        print(f"{engine.name}: held incomplete batch, preserved ready batches, and showed all 25 posts")
    finally:
        browser.close()


def check_sources(engine, executable, viewport, static):
    browser = engine.launch(**({"executable_path": executable} if executable else {}))
    try:
        page = browser.new_page(viewport=viewport)
        prefs = {
            "ultraImmersive": True, "ultraColumns": 8, "ultraRows": 1, "ultraOpenSingle": True,
            "ultraVideos": 2, "ultraLayout": "rows", "ultraPauseBatch": False,
            "sound": False, "autoNext": False, "showPauseIcon": True, "pinchZoom": True,
        }
        author = {
            "key": "fixture", "platform": "douyin", "name": "Fixture", "avatar": None,
            "cover": "poster.svg", "followed": False, "latest_ts": 1700000000,
            "stats": {"posts": 24, "likes": 0, "videos": 24, "images": 0},
        }
        delayed_likes = []
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.add_init_script("localStorage.setItem('feed.ultra_immersive', '1')")

        def serve(route):
            url = urlsplit(route.request.url)
            path = url.path
            if path == "/ui/feed":
                return route.fulfill(path=static / "index.html")
            if path.startswith("/ui/static/"):
                return route.fulfill(path=static / path.removeprefix("/ui/static/"))
            if path == "/ui/api/feed/posts":
                query = parse_qs(url.query)
                if query["source"] == ["likes"]:
                    if query.get("cursor"):
                        delayed_likes.append(route)
                        return
                    return route.fulfill(json={"items": fixture_posts(0, 13), "next_cursor": "later"})
                return route.fulfill(json={"items": fixture_posts(0, 24), "next_cursor": None})
            if path == "/ui/api/feed/preferences":
                if route.request.method == "PATCH":
                    prefs.update(route.request.post_data_json)
                return route.fulfill(json=prefs)
            if path == "/ui/api/feed/account":
                return route.fulfill(json=author)
            if path == "/ui/api/feed/accounts":
                return route.fulfill(json={"items": [author], "next_offset": None, "total": 1})
            if path == "/ui/api/feed/thumb":
                return route.fulfill(content_type="image/svg+xml", body=POSTER)
            if path == "/ui/api/file":
                return route.fulfill(status=404)
            if path == "/ui/api/feed/status":
                return route.fulfill(json={"phase": "idle", "posts": 24})
            return route.fulfill(json={"items": []})

        page.route(ORIGIN + "/**", serve)
        page.goto(ORIGIN + "/ui/feed", wait_until="domcontentloaded")
        player = page.locator('.fa-layer-player[aria-hidden="false"]')
        nav = page.locator(".fa-nav" if viewport["width"] >= 700 else ".fa-tabbar")

        def open_post(grid, number):
            grid.get_by_role("button", name=f"Post {number}", exact=True).click()
            expect(player.locator(".fa-ultra")).to_be_visible()
            return player.locator(".fa-ultra-batch:not([inert])").get_by_role(
                "button", name=f"Fixture · Post {number}", exact=True
            )

        nav.get_by_role("button", name="喜欢", exact=True).click()
        liked = open_post(page.locator(".fa-tab-pane:visible"), 12)
        expect(player.get_by_role("status", name="正在加载作品")).to_be_visible()
        for _ in range(100):
            if delayed_likes:
                break
            page.wait_for_timeout(25)
        assert delayed_likes, "The selected batch did not request the next page"
        delayed_likes.pop().fulfill(json={"items": fixture_posts(13, 24), "next_cursor": None})
        expect(liked).to_be_visible()
        assert player.locator(".fa-ultra").evaluate("node => node.scrollTop > 0")
        player.get_by_role("button", name="全屏观看", exact=True).click()
        expect(page.locator(".fa[data-ultra-fullscreen]")).to_be_visible()
        expect(player.get_by_role("button", name="返回", exact=True)).to_be_hidden()
        player.get_by_role("button", name="退出全屏", exact=True).click()
        expect(liked).to_be_visible()
        liked.dblclick()
        expect(player.locator(".fa-pager:not(.fa-ultra) .fa-slide.is-active").get_by_text("Post 12")).to_be_visible()
        player.get_by_role("button", name="返回", exact=True).click()
        expect(liked).to_be_visible()
        player.get_by_role("button", name="返回", exact=True).click()
        expect(player).to_have_count(0)

        nav.get_by_role("button", name="收藏", exact=True).click()
        expect(open_post(page.locator(".fa-tab-pane:visible"), 10)).to_be_visible()
        player.get_by_role("button", name="返回", exact=True).click()
        nav.get_by_role("button", name="发现", exact=True).click()
        page.get_by_role("tab", name="热门作品").click()
        expect(open_post(page.locator(".fa-tab-pane:visible"), 9)).to_be_visible()
        player.get_by_role("button", name="返回", exact=True).click()
        page.get_by_role("tab", name="账号").click()
        page.get_by_role("button", name="打开 Fixture 的主页").click()
        profile = page.locator('.fa-layer-profile[aria-hidden="false"]')
        expect(open_post(profile, 11)).to_be_visible()
        player.get_by_role("button", name="返回", exact=True).click()
        expect(profile).to_be_visible()
        assert not errors, errors
        print(f"{engine.name}: Ultra Immersive opened from likes, saves, Discover, and an account profile")
    finally:
        browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--static", type=Path, default=STATIC)
    parser.add_argument("--chromium")
    parser.add_argument("--webkit")
    args = parser.parse_args()
    with sync_playwright() as playwright:
        check(playwright.chromium, args.chromium, {"width": 1280, "height": 720}, args.static)
        check(playwright.webkit, args.webkit, {"width": 390, "height": 844}, args.static)
        check_sources(playwright.chromium, args.chromium, {"width": 1280, "height": 900}, args.static)
        check_sources(playwright.webkit, args.webkit, {"width": 820, "height": 1180}, args.static)
