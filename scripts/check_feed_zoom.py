#!/usr/bin/env python3
"""Pinch/clean-screen regression on the real feed. Start Vite on port 5178.

Chromium uses real CDP touch input; desktop WebKit uses synthetic TouchEvents.
A physical iPhone gesture check is still required. Pass a small MP4 via --video.
"""
import argparse
import json
from urllib.parse import urlparse, parse_qs
from playwright.sync_api import sync_playwright, expect


def post(kind):
    return {'key': kind, 'kind': kind, 'published_ts': 1700000000, 'caption': 'Zoom fixture',
            'tags': [], 'duration': 12, 'width': 320, 'height': 480, 'stats': None, 'music': None,
            'work_id': '1', 'share_url': '', 'media': [{'kind': 'video', 'path': 'fixture.mp4'}]
            if kind == 'video' else [{'kind': 'image', 'path': f'photo_{i}.jpeg'} for i in range(2)],
            'cover': 'photo_0.jpeg', 'liked': False, 'saved': False, 'pinned': False, 'meta_pending': False,
            'author': {'key': 'fixture', 'platform': 'douyin', 'url': '', 'name': 'Test account', 'avatar': None, 'followed': False}}


def check(engine, args):
    executable = getattr(args, engine.name)
    browser = engine.launch(**({'executable_path': executable} if executable else {}))
    context = browser.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True)
    page = context.new_page()
    errors, marks = [], []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.add_init_script("localStorage.setItem('feed.sound','0')")
    index = {'phase': 'idle', 'accounts': 1, 'posts': 2, 'error': '', 'done': 1, 'total': 1}

    def api(route):
        parsed = urlparse(route.request.url)
        result = {}
        if parsed.path == '/ui/api/feed/status': result = index
        elif parsed.path == '/ui/api/feed/me': result = {'following': 0, 'likes': 0, 'saves': 0, 'hidden': 0, 'index': index}
        elif parsed.path == '/ui/api/feed/posts': result = {'items': [post('video'), post('images')], 'next_cursor': None}
        elif parsed.path == '/ui/api/feed/accounts': result = {'items': [], 'total': 0, 'next_offset': None}
        elif parsed.path == '/ui/api/feed/marks': marks.append(route.request.post_data)
        elif parsed.path == '/ui/api/file' and parse_qs(parsed.query).get('path') == ['fixture.mp4']:
            route.fulfill(content_type='video/mp4', path=args.video); return
        elif parsed.path in ('/ui/api/file', '/ui/api/feed/thumb'):
            route.fulfill(content_type='image/svg+xml', body='<svg xmlns="http://www.w3.org/2000/svg" width="320" height="480"><rect width="320" height="480" fill="#345"/><circle cx="160" cy="200" r="70" fill="#db9"/><path d="M0 400H320M160 0V480" stroke="white" stroke-width="3"/></svg>'); return
        route.fulfill(content_type='application/json', body=json.dumps(result))

    context.route('**/ui/api/**', api)
    cdp = context.new_cdp_session(page) if engine.name == 'chromium' else None

    def touch(kind, points):
        if cdp:
            cdp.send('Input.dispatchTouchEvent', {'type': kind, 'touchPoints': [
                {'x': x, 'y': y, 'id': i, 'radiusX': 4, 'radiusY': 4} for i, (x, y) in enumerate(points)]})
        else:
            page.evaluate('''({kind,points}) => {
              const target = window.touchTarget || document.querySelector('.fa-slide.is-active .fa-surface-video, .fa-slide.is-active .fa-carousel');
              window.touchTarget=points.length ? target : null;
              const touches=points.map(([x,y],identifier)=>({identifier,target,clientX:x,clientY:y,pageX:x,pageY:y}));
              const event=new Event(kind.toLowerCase(), {bubbles:true,cancelable:true});
              Object.defineProperties(event,{touches:{value:touches},targetTouches:{value:touches},changedTouches:{value:touches}});
              target.dispatchEvent(event);
            }''', {'kind': kind, 'points': points})
        page.wait_for_timeout(25)

    def pinch(start, end):
        bounds = stage.bounding_box()
        cx, cy = bounds['x'] + bounds['width'] / 2, bounds['y'] + bounds['height'] / 2
        touch('touchStart', [(cx-start, cy), (cx+start, cy)])
        for i in range(1, 7):
            distance = start + (end-start)*i/6
            touch('touchMove', [(cx-distance, cy), (cx+distance, cy)])
        touch('touchEnd', [])

    active = page.locator('.fa-slide.is-active')
    stage = active.locator('.fa-stage')

    def pager_geometry():
        return page.locator('.fa-pager').first.evaluate('(e)=>[e.clientHeight,e.scrollTop]')

    def full_display():
        bounds = stage.bounding_box()
        viewport = page.viewport_size
        assert bounds == {'x': 0, 'y': 0, 'width': viewport['width'], 'height': viewport['height']}, bounds
        assert page.evaluate('''() => !!document.elementFromPoint(innerWidth / 2, innerHeight - 12)
          ?.closest('.fa-stage[data-zoomed]')'''), 'Bottom navigation area must accept media gestures'

    try:
        page.goto(args.url + '/ui/feed')
        # Include the iPhone home-indicator inset in the previously black strip.
        page.add_style_tag(content='.fa { --fa-safe-bottom: 34px; }')
        page.wait_for_function("document.querySelector('.fa-slide.is-active video')?.paused === false")
        page.wait_for_timeout(350)  # Let initial viewport measurement/player binding settle.
        page.wait_for_function("() => { window.originalVideo=document.querySelector('.fa-slide.is-active video'); return originalVideo && !originalVideo.paused; }")
        active.locator('.fa-surface-video').tap(position={'x': 150, 'y': 220})
        page.wait_for_function('originalVideo.paused')
        before = page.evaluate('originalVideo.currentTime')
        fitted_bounds = stage.bounding_box()
        pager_before = pager_geometry()
        pinch(45, 120)
        expect(stage).to_have_attribute('data-zoomed', '')
        full_display()
        assert pager_geometry() == pager_before
        expect(page.locator('.fa-tabbar')).not_to_be_visible()
        expect(active.locator('.fa-rail')).not_to_be_visible()
        expect(active.locator('.fa-caption')).not_to_be_visible()
        expect(active.locator('.fa-center-icon')).not_to_be_visible()
        assert page.evaluate('originalVideo === document.querySelector(".fa-slide.is-active video") && originalVideo.paused')
        assert abs(page.evaluate('originalVideo.currentTime') - before) < .1
        transform = stage.get_attribute('style')
        touch('touchStart', [(195, 820)])
        touch('touchMove', [(125, 750)])
        touch('touchEnd', [])
        assert stage.get_attribute('style') != transform
        page.keyboard.press('ArrowDown')
        assert active.locator('video').count() == 1
        page.screenshot(path=f'/tmp/feed-zoom-{engine.name}-video.png')
        pinch(120, 35)
        expect(stage).not_to_have_attribute('data-zoomed', '')
        assert stage.bounding_box() == fitted_bounds
        assert pager_geometry() == pager_before
        expect(page.locator('.fa-tabbar')).to_be_visible()
        assert not marks
        assert page.locator('.fa-layer').count() == 0
        page.wait_for_timeout(400)
        # Native swipe must work after unlocking the pinch gesture.
        if cdp:
            touch('touchStart', [(180, 600)])
            for y in (550, 470, 390, 310, 200): touch('touchMove', [(180, y)])
            touch('touchEnd', [])
        else:
            page.locator('.fa-pager').first.evaluate('(e)=>e.scrollTo({top:e.clientHeight,behavior:"instant"})')
        expect(active.locator('.fa-carousel')).to_be_visible()
        page.wait_for_function("() => { const e=document.querySelector('.fa-pager'); return Math.abs(e.scrollTop-e.clientHeight)<0.5; }")
        carousel = active.locator('.fa-carousel')
        carousel.evaluate('(e)=>e.scrollTo({left:e.clientWidth,behavior:"instant"})')
        expect(active.locator('.fa-carousel-count')).to_have_text('2/2')
        pager_before = pager_geometry()
        pinch(45, 110)
        expect(stage).to_have_attribute('data-zoomed', '')
        full_display()
        assert pager_geometry() == pager_before
        selected = active.locator('.fa-carousel-item[data-current="true"] img')
        assert selected.get_attribute('src').endswith('photo_1.jpeg')
        assert selected.evaluate('(e)=>getComputedStyle(e).transform') != 'none'
        page.wait_for_timeout(4300)
        expect(active.locator('.fa-carousel-count')).to_have_text('2/2')
        page.screenshot(path=f'/tmp/feed-zoom-{engine.name}-photo.png')
        pinch(110, 35)
        expect(stage).not_to_have_attribute('data-zoomed', '')
        assert pager_geometry() == pager_before
        page.get_by_role('button', name='我', exact=True).filter(visible=True).click()
        switch = page.get_by_role('switch', name='双指缩放', exact=False)
        expect(switch).to_be_checked(); switch.uncheck()
        page.wait_for_function("localStorage.getItem('feed.pinch_zoom')==='0'")
        page.reload()
        page.wait_for_function("document.querySelector('.fa-slide.is-active video')?.paused === false")
        pinch(45, 110)
        expect(stage).not_to_have_attribute('data-zoomed', '')
        page.get_by_role('button', name='我', exact=True).filter(visible=True).click()
        expect(switch).not_to_be_checked(); switch.check()
        page.get_by_role('button', name='首页', exact=True).filter(visible=True).click()
        pinch(45, 110)
        expect(stage).to_have_attribute('data-zoomed', '')
        assert page.evaluate('document.querySelector(".fa-slide.is-active video").paused') is False
        page.set_viewport_size({'width': 844, 'height': 390})
        expect(stage).not_to_have_attribute('data-zoom-active', '')
        for size in ({'width': 844, 'height': 390}, {'width': 1280, 'height': 800}):
            page.set_viewport_size(size)
            page.wait_for_timeout(400)
            pager_before = pager_geometry()
            pinch(30, 75)
            expect(stage).to_have_attribute('data-zoomed', '')
            full_display()
            assert pager_geometry() == pager_before
            page.screenshot(path=f'/tmp/feed-zoom-{engine.name}-{size["width"]}.png')
            page.keyboard.press('Escape')
            expect(stage).not_to_have_attribute('data-zoomed', '')
            assert pager_geometry() == pager_before
        assert not errors, errors
        print(engine.name, 'PASS: full-display zoom including safe area, bottom-area pan, stable pager geometry, landscape/desktop, paused/playing video, swipe recovery, selected photo, timer held, persisted switch, rotation reset')
    finally:
        browser.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:5178')
    parser.add_argument('--video', required=True)
    parser.add_argument('--webkit')
    parser.add_argument('--chromium')
    args = parser.parse_args()
    with sync_playwright() as playwright:
        for engine in (playwright.webkit, playwright.chromium): check(engine, args)
