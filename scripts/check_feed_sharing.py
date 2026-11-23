#!/usr/bin/env python3
"""Verify file payloads and share UI with a mocked OS share API, via Vite.

This does not verify the native iPhone share sheet or destination apps.
"""
import argparse
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import expect, sync_playwright


def check_anchoring(page):
    trigger = page.locator("#share-trigger")
    dialog = page.get_by_role("dialog", name="分享与更多")

    def expect_next_to(bounds, viewport):
        expect(dialog).to_have_attribute("data-share-positioned", "")
        page.wait_for_function("""({anchor, viewport}) => {
            const panel = document.querySelector('[data-share-positioned]');
            if (!panel) return false;
            const rect = panel.getBoundingClientRect();
            const top = Math.max(12, Math.min(anchor.y + (anchor.height - rect.height) / 2,
                viewport.height - 12 - rect.height));
            return Math.abs(rect.right - (anchor.x - 12)) < 2
                && Math.abs(rect.top - top) < 2
                && rect.left >= 0 && rect.top >= 0 && rect.right <= viewport.width
                && rect.bottom <= viewport.height;
        }""", arg={"anchor": bounds, "viewport": viewport})

    tablet = {"width": 820, "height": 1180}
    page.set_viewport_size(tablet)
    page.evaluate("showShareFixture('images', true)")
    trigger.tap()
    expect_next_to(trigger.bounding_box(), tablet)
    landscape = {"width": 1180, "height": 820}
    page.set_viewport_size(landscape)
    expect_next_to(trigger.bounding_box(), landscape)
    dialog.press("Escape")
    expect(dialog).to_have_count(0)
    expect(trigger).to_be_focused()

    page.set_viewport_size(tablet)
    page.evaluate("showShareFixture('images', true, true)")
    expect(trigger).to_have_attribute("data-detach-on-open", "true")
    saved_bounds = trigger.bounding_box()
    trigger.tap()
    expect(trigger).to_have_count(0)
    expect_next_to(saved_bounds, tablet)

    phone = {"width": 390, "height": 844}
    page.set_viewport_size(phone)
    page.evaluate("showShareFixture('images', true)")
    trigger.tap()
    expect(dialog).to_be_visible()
    page.wait_for_function("""height => {
        const dialog = document.querySelector('.fa-sheet');
        return dialog && Math.abs(dialog.getBoundingClientRect().bottom - height) < 2;
    }""", arg=phone["height"])


def check(engine, args):
    executable = getattr(args, engine.name)
    browser = engine.launch(**({"executable_path": executable} if executable else {}))
    page = browser.new_page(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    errors, requests = [], []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.add_init_script("""
      window.shareCalls = []; window.shareOutcome = 'success'; window.fileSupported = true;
      window.tapActive = false;
      Object.defineProperty(navigator, 'userActivation', {value:{get isActive(){return window.tapActive;}}});
      Object.defineProperty(navigator, 'canShare', {value:data => window.fileSupported && data.files?.[0] instanceof File});
      Object.defineProperty(navigator, 'share', {value:async data => {
        window.shareCalls.push({url:data.url, files:await Promise.all((data.files || []).map(async file =>
          ({name:file.name, type:file.type, content:await file.text()})))});
        if (window.shareOutcome !== 'success') throw new DOMException('Test failure', window.shareOutcome);
      }});
    """)

    def respond(route):
        path = parse_qs(urlparse(route.request.url).query)["path"][0]
        assert route.request.headers.get("token") == "share-test-token"
        requests.append(path)
        route.fulfill(content_type="application/octet-stream", body="actual-file-" + path)

    page.route("**/ui/api/file?**", respond)
    try:
        page.goto(args.url + "/tests/media-share.html")
        page.get_by_role("button", name="分享图片", exact=True).click()
        ready = page.get_by_role("button", name="继续分享", exact=True)
        expect(ready).to_be_enabled()
        assert page.evaluate("shareCalls.length") == 0
        assert requests == ["selected_2.jpeg"]
        page.screenshot(path=f"/tmp/feed-share-{engine.name}-phone.png")
        ready.click()
        expect(page.locator("#root")).to_have_text("Closed")
        assert page.evaluate("shareCalls[0].url") is None
        assert page.evaluate("shareCalls[0].files") == [
            {"name": "selected_2.jpeg", "type": "image/jpeg", "content": "actual-file-selected_2.jpeg"}
        ]

        # A short preparation can share on the original tap while activation lasts.
        page.evaluate("tapActive=true; showShareFixture('video')")
        page.get_by_role("button", name="分享视频", exact=True).click()
        expect(page.locator("#root")).to_have_text("Closed")
        assert page.evaluate("shareCalls.at(-1).files[0].type") == "video/mp4"

        # Canceling the OS sheet keeps the prepared file for a retry.
        page.evaluate("shareOutcome='AbortError'; showShareFixture()")
        page.get_by_role("button", name="分享图片", exact=True).click()
        expect(ready).to_be_enabled()
        expect(page.locator(".fa-share-status")).to_have_count(0)
        count = len(requests)
        page.evaluate("shareOutcome='NotAllowedError'")
        ready.click()
        expect(page.locator(".fa-share-status")).to_contain_text("再次点")
        page.evaluate("shareOutcome='success'")
        ready.click()
        expect(page.locator("#root")).to_have_text("Closed")
        assert len(requests) == count

        page.evaluate("fileSupported=false; showShareFixture()")
        page.get_by_role("button", name="分享图片", exact=True).click()
        expect(page.locator(".fa-share-status")).to_contain_text("文件格式")
        expect(page.get_by_role("link", name="下载当前", exact=True)).to_be_visible()
        page.set_viewport_size({"width": 1280, "height": 800})
        page.screenshot(path=f"/tmp/feed-share-{engine.name}-desktop.png")

        # Closing our sheet aborts preparation rather than sharing afterwards.
        page.evaluate("""() => {
          fileSupported=true; window.originalFetch=fetch;
          window.fetch=(url,init)=>new Promise((resolve,reject)=> {
            init.signal.addEventListener('abort',()=> {
              window.fetchAborted=true; reject(new DOMException('Canceled','AbortError'));
            });
          });
          showShareFixture();
        }""")
        page.get_by_role("button", name="分享图片", exact=True).click()
        expect(page.get_by_role("button", name="准备分享…", exact=True)).to_be_disabled()
        page.locator(".fa-sheet-head").get_by_role("button", name="关闭", exact=True).click()
        page.wait_for_function("window.fetchAborted === true")
        page.evaluate("window.fetch=window.originalFetch")

        page.evaluate("Object.defineProperty(window,'isSecureContext',{value:false}); showShareFixture()")
        count = len(requests)
        page.get_by_role("button", name="分享图片", exact=True).click()
        expect(page.locator(".fa-share-status")).to_contain_text("HTTPS")
        assert len(requests) == count
        check_anchoring(page)
        assert not errors, errors
        print(engine.name, "PASS: media sharing, anchored tablet menu, detached trigger, and phone sheet")
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
