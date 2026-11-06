#!/usr/bin/env python3
"""Browser regression for the real Pager. Start webui's Vite server first.

Requires Playwright and its browser engines. This exercises snap geometry and
virtualization; desktop WebKit cannot reproduce physical iPhone momentum.
"""
import argparse

from playwright.sync_api import sync_playwright


def check(engine, args):
    executable = getattr(args, engine.name)
    browser = engine.launch(**({"executable_path": executable} if executable else {}))
    page = browser.new_page(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.route("**/ui/api/**", lambda route: route.fulfill(
        content_type="image/svg+xml",
        body='<svg xmlns="http://www.w3.org/2000/svg" width="390" height="844">'
             '<rect width="390" height="844" fill="#345"/></svg>',
    ))
    try:
        page.goto(args.url + "/tests/pager-scroll.html")
        page.wait_for_function("window.activePost === 'fixture-0'")
        page.wait_for_timeout(300)  # Initial resize stabilization.
        if args.baseline:
            # Restore the old geometry: only virtual panels are snap targets.
            page.add_style_tag(content=".fa-pager-snap{display:none}.fa-slide{scroll-snap-align:start;scroll-snap-stop:always}")
        for target in (8, 17, 28, 3):
            # Cross the mounted window in one frame, as fast scrolling can do.
            page.eval_on_selector(".fa-pager", "(el,n)=>el.scrollTo({top:n*el.clientHeight,behavior:'instant'})", target)
            page.wait_for_timeout(350)
            actual = page.eval_on_selector(".fa-pager", "el=>el.scrollTop/el.clientHeight")
            assert abs(actual - target) < 0.01, (engine.name, "wanted", target, "landed", actual)
            assert page.evaluate("window.activePost") == f"fixture-{target}"
            assert page.locator(".fa-slide:not(.fa-slide-end)").count() <= 5
        page.screenshot(path=f"/tmp/fetchshelf-scroll-mobile-{engine.name}.png")
        # Native scrolling still has a stop at each post, even off-screen.
        assert page.locator(".fa-pager-snap").count() == 41
        page.evaluate("window.pagerFixture.append()")
        page.wait_for_timeout(300)
        assert page.evaluate("window.activePost") == "fixture-3"
        assert page.locator(".fa-pager-snap").count() == 61
        for size in ({"width":844,"height":390}, {"width":1280,"height":800}):
            page.set_viewport_size(size)
            page.wait_for_timeout(500)
            assert page.evaluate("window.activePost") == "fixture-3"
            actual = page.eval_on_selector(".fa-pager", "el=>el.scrollTop/el.clientHeight")
            assert abs(actual - 3) < 0.01
        for action, target in (("next",4),("previous",3)):
            page.evaluate(f"window.pagerFixture.handleRef.current.{action}()")
            page.wait_for_function(f"window.activePost === 'fixture-{target}'")
            page.wait_for_timeout(500)
            assert page.evaluate("window.activePost") == f"fixture-{target}"
        # The old footer becomes the first newly loaded post. Keeping the same
        # footer element as a moving snap target would jump to the NEW footer.
        page.eval_on_selector(".fa-pager", "el=>el.scrollTo({top:60*el.clientHeight,behavior:'instant'})")
        page.wait_for_timeout(350)
        page.evaluate("window.pagerFixture.append()")
        page.wait_for_timeout(500)
        actual = page.eval_on_selector(".fa-pager", "el=>el.scrollTop/el.clientHeight")
        assert abs(actual - 60) < 0.01
        assert page.evaluate("window.activePost") == "fixture-60"
        page.screenshot(path=f"/tmp/fetchshelf-scroll-{engine.name}.png")
        assert not errors, errors
        print(engine.name, "PASS: distant offsets, bounded media, append, resize, next/previous")
    finally:
        browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:5178")
    parser.add_argument("--webkit")
    parser.add_argument("--chromium")
    parser.add_argument("--baseline", action="store_true")
    args = parser.parse_args()
    with sync_playwright() as playwright:
        for engine in (playwright.webkit, playwright.chromium):
            check(engine, args)
