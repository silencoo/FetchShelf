#!/usr/bin/env python3
"""Check the built Immersive player while a paused drag is still in progress."""
import argparse
from io import BytesIO
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory
from urllib.parse import parse_qs, urlsplit

from PIL import Image
from playwright.sync_api import expect, sync_playwright


def jpeg(color):
    output = BytesIO()
    Image.new("RGB", (180, 320), color).save(output, "JPEG")
    return output.getvalue()


def check(engine, assets, executable):
    with TemporaryDirectory() as temp:
        path = Path(temp) / "fixture.mp4"
        subprocess.run([
            "ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=red:size=180x320:rate=24",
            "-t", "18", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(path),
        ], check=True)
        video = path.read_bytes()
    cover, middle, end = (jpeg(color) for color in ("red", "green", "blue"))
    origin = "https://paused-scrub.test"
    post = {
        "key": "fixture", "kind": "video", "caption": "", "published_ts": 1700000000,
        "tags": [], "duration": 18, "width": 180, "height": 320, "cover": "cover.jpg",
        "media": [{"path": "fixture.mp4", "kind": "video"}],
        "author": {"key": "fixture", "name": "Fixture", "platform": "douyin"},
    }
    held = []
    requested = []

    def route_media(route):
        url = urlsplit(route.request.url)
        if url.path == "/ui/feed":
            return route.fulfill(path=assets / "index.html")
        if url.path.startswith("/ui/static/"):
            return route.fulfill(path=assets / url.path.removeprefix("/ui/static/"))
        if url.path == "/ui/api/file":
            headers = {"Accept-Ranges": "bytes"}
            span = re.fullmatch(r"bytes=(\d+)-(\d*)", route.request.headers.get("range", ""))
            if span:
                start = int(span[1])
                stop = min(int(span[2]) if span[2] else len(video) - 1, len(video) - 1)
                headers["Content-Range"] = f"bytes {start}-{stop}/{len(video)}"
                return route.fulfill(status=206, body=video[start:stop + 1], content_type="video/mp4", headers=headers)
            return route.fulfill(body=video, content_type="video/mp4", headers=headers)
        if url.path == "/ui/api/feed/thumb":
            time = int(parse_qs(url.query).get("at_ms", ["0"])[0])
            if time:
                requested.append(time)
            if time >= 12000:
                held.append((time, route))
                return
            return route.fulfill(body=middle if time >= 6000 else cover, content_type="image/jpeg")
        result = {
            "/ui/api/feed/posts": {"items": [post], "next_cursor": None},
            "/ui/api/feed/status": {"phase": "idle", "accounts": 1, "posts": 1},
            "/ui/api/feed/preferences": {"sound": False, "showPauseIcon": False, "ultraImmersive": False},
        }
        return route.fulfill(json=result.get(url.path, {}))

    browser = engine.launch(**({"executable_path": executable} if executable else {}))
    try:
        page = browser.new_page(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
        page.set_default_timeout(5000)
        page.route(origin + "/**", route_media)
        page.add_init_script("""
            window.WebSocket = class extends EventTarget { close() {} send() {} };
            HTMLVideoElement.prototype.requestVideoFrameCallback = () => 1;
        """)
        page.goto(origin + "/ui/feed")
        slide = page.locator(".fa-slide.is-active")
        surface = slide.locator(".fa-surface-video")
        video_selector = ".fa-slide.is-active video"
        page.wait_for_function(f"document.querySelector('{video_selector}')?.currentTime > 0.25")
        surface.tap()
        page.wait_for_function(f"document.querySelector('{video_selector}')?.paused")
        # Stale native composition stays red. The scrub preview must paint the
        # correct color above it even if there is no native frame callback.
        slide.locator("video").evaluate("video => { video.style.visibility = 'hidden'; }")
        page.wait_for_timeout(650)
        bounds = slide.locator(".fa-seek").bounding_box()
        assert bounds
        y = bounds["y"] + 11
        touch = page.context.new_cdp_session(page) if engine.name == "chromium" else None

        def pointer(action, fraction=0):
            x = bounds["x"] + bounds["width"] * fraction
            if touch:
                points = [] if action == "End" else [{"x": x, "y": y}]
                touch.send("Input.dispatchTouchEvent", {"type": "touch" + action, "touchPoints": points})
            elif action == "End":
                page.mouse.up()
            else:
                page.mouse.move(x, y)
                if action == "Start":
                    page.mouse.down()

        def visible_color():
            x, y = 195, 400
            image = Image.open(BytesIO(page.screenshot(clip={"x": x, "y": y, "width": 2, "height": 2})))
            r, g, b = image.getpixel((0, 0))[:3]
            channels = {"red": r, "green": g, "blue": b}
            return max(channels, key=channels.get)

        def wait_for_held():
            for _ in range(100):
                if held:
                    return held.pop(0)
                page.wait_for_timeout(20)
            raise AssertionError("No timed preview requested")

        pointer("Start", 0.18)
        for sample in range(16):
            pointer("Move", 0.28 + sample * 0.013)
            page.wait_for_timeout(45)
        assert visible_color() == "green", ("The picture did not move with the ongoing drag", requested)
        pointer("Move", 0.76)
        first_time, first = wait_for_held()
        assert abs(first_time - 13680) < 250
        assert visible_color() == "green", "The old paused picture flashed during the next seek"
        pointer("Move", 0.89)
        pointer("End")
        first.fulfill(body=end, content_type="image/jpeg")
        final_time, final = wait_for_held()
        assert abs(final_time - 16020) < 250
        assert visible_color() == "green", "A superseded frame painted after release"
        final.fulfill(body=end, content_type="image/jpeg")
        expect(slide.locator(".fa-paused-frame")).to_have_attribute("src", f"/ui/api/feed/thumb?path=fixture.mp4&at_ms={final_time}")
        assert visible_color() == "blue"
        page.wait_for_function(f"""() => {{
            const video = document.querySelector('{video_selector}');
            return video.paused && Math.abs(video.currentTime - 16.02) < 0.25;
        }}""")
        print(f"{engine.name} PASS: frames move during paused drag, old frame stays hidden, release uses final timestamp")
    finally:
        browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", type=Path, default=Path(__file__).resolve().parents[1] / "src/webui/static")
    parser.add_argument("--webkit")
    parser.add_argument("--chromium")
    args = parser.parse_args()
    with sync_playwright() as playwright:
        check(playwright.webkit, args.assets, args.webkit)
        check(playwright.chromium, args.assets, args.chromium)
