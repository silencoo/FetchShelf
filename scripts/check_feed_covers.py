#!/usr/bin/env python3
"""Exercise the actual cover component's network failures via the Vite fixture."""
import argparse
from collections import Counter
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import sync_playwright


def check(engine, args):
    executable = getattr(args, engine.name)
    browser = engine.launch(**({"executable_path": executable} if executable else {}))
    page = browser.new_page(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    requests = Counter()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))

    def respond(route):
        path = parse_qs(urlparse(route.request.url).query)["path"][0]
        requests[path] += 1
        if path.startswith("missing"):
            route.fulfill(status=404, body="Missing file")
        elif path.startswith("corrupt"):
            route.fulfill(content_type="image/jpeg", body="Not a decodable image")
        else:
            route.fulfill(content_type="image/svg+xml", body=
                          '<svg xmlns="http://www.w3.org/2000/svg" width="360" height="560">'
                          '<rect width="360" height="560" fill="#38556b"/>'
                          '<circle cx="180" cy="230" r="90" fill="#e6b99c"/></svg>')

    def loaded(path):
        page.wait_for_function("""path => {
          const images = [...document.querySelectorAll('img')];
          return images.length === 2 && images.every(img => img.complete && img.naturalWidth > 0
            && new URL(img.src).searchParams.get('path') === path);
        }""", arg=path)

    def show(preferred, fallback):
        page.evaluate("([p,f]) => window.coverFixture(p,f)", [preferred, fallback])

    page.route("**/ui/api/feed/thumb?**", respond)
    try:
        page.goto(args.url + "/tests/account-cover.html")
        loaded("chosen.jpeg")
        assert requests["current.jpeg"] == 0
        show("missing-pin.jpeg", "current.jpeg")
        loaded("current.jpeg")
        show("corrupt-pin.jpeg", "another.jpeg")
        loaded("another.jpeg")
        for size in ({"width": 390, "height": 844}, {"width": 1280, "height": 800}):
            page.set_viewport_size(size)
            loaded("another.jpeg")
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.screenshot(path=f"/tmp/fetchshelf-covers-{engine.name}-{size['width']}.png")
        show("missing-both.jpeg", "corrupt-both.jpeg")
        page.wait_for_function("document.querySelectorAll('img').length === 0")
        show("missing-same.jpeg", "missing-same.jpeg")
        page.wait_for_function("document.querySelectorAll('img').length === 0")
        assert requests["missing-same.jpeg"] == 2  # Once per card/hero, no retry loop.
        show("recovered.jpeg", "current.jpeg")
        loaded("recovered.jpeg")
        assert not errors, errors
        print(engine.name, "PASS: saved cover, 404/decode fallback, exhaustion, no loops, refresh, narrow/wide")
    finally:
        browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:5178")
    parser.add_argument("--webkit")
    parser.add_argument("--chromium")
    args = parser.parse_args()
    with sync_playwright() as playwright:
        for engine in (playwright.webkit, playwright.chromium):
            check(engine, args)
