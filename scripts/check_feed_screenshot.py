#!/usr/bin/env python3
"""Test exact tap-time video screenshots on the real feed, with a mocked OS share API.

Use a changing-frame MP4 via --video, and start Vite on port 5178.
The native iPhone share destination still requires a device check.
"""
import argparse
import json
from urllib.parse import urlparse, parse_qs

from playwright.sync_api import expect, sync_playwright
from check_feed_zoom import post


def check(engine, args):
    executable = getattr(args, engine.name)
    browser = engine.launch(**({'executable_path': executable} if executable else {}))
    page = browser.new_page(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True)
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.add_init_script('''
      localStorage.setItem('feed.sound','0');
      window.shared=[]; window.outcome='success'; window.fileSupported=true;
      window.pixels=async canvas => {
        const bytes=canvas.getContext('2d').getImageData(0,0,canvas.width,canvas.height).data;
        return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))).join(',');
      };
      window.filePixels=async file => {
        const url=URL.createObjectURL(file);
        try {
          const image=new Image(); image.src=url; await image.decode();
          const canvas=document.createElement('canvas'); canvas.width=image.width; canvas.height=image.height;
          canvas.getContext('2d').drawImage(image,0,0);
          return {width:canvas.width,height:canvas.height,hash:await pixels(canvas)};
        } finally {URL.revokeObjectURL(url);}
      };
      const drawImage=CanvasRenderingContext2D.prototype.drawImage;
      CanvasRenderingContext2D.prototype.drawImage=function(source,...args) {
        const result=drawImage.call(this,source,...args);
        if(source instanceof HTMLVideoElement) {
          window.captureDuringTap=window.inRailTap;
          window.captureTime=source.currentTime;
          window.expected=pixels(this.canvas);
        }
        return result;
      };
      document.addEventListener('click',event=>{
        const button=event.target.closest('button');
        window.inRailTap=button?.getAttribute('aria-label')==='分享与更多操作';
        if(inRailTap) {
          const video=button.closest('.fa-slide').querySelector('video');
          if(video?.readyState>=2) {
            window.tapTime=video.currentTime; window.tapPaused=video.paused;
          }
        }
        window.inShareTap=button?.textContent.includes('分享截图');
        setTimeout(()=>{window.inShareTap=false;window.inRailTap=false;},0);
      },true);
      Object.defineProperty(navigator,'canShare',{value:data=>fileSupported && data.files?.[0] instanceof File});
      Object.defineProperty(navigator,'share',{value:async data=>{
        const sync=window.inShareTap;
        const file=data.files[0];
        shared.push({name:file.name,type:file.type,count:data.files.length,url:data.url,
          sync,...await filePixels(file)});
        if(outcome!=='success') throw new DOMException('Test',outcome);
      }});
    ''')
    index = {'phase': 'idle', 'accounts': 1, 'posts': 2, 'error': '', 'done': 1, 'total': 1}

    def api(route):
        parsed = urlparse(route.request.url)
        result = {}
        if parsed.path == '/ui/api/feed/status': result = index
        elif parsed.path == '/ui/api/feed/me': result = {'following': 0, 'likes': 0, 'saves': 0, 'hidden': 0, 'index': index}
        elif parsed.path == '/ui/api/feed/posts': result = {'items': [post('video'), post('images')], 'next_cursor': None}
        elif parsed.path == '/ui/api/feed/accounts': result = {'items': [], 'total': 0, 'next_offset': None}
        elif parsed.path == '/ui/api/file' and parse_qs(parsed.query).get('path') == ['fixture.mp4']:
            route.fulfill(content_type='video/mp4', path=args.video); return
        elif parsed.path in ('/ui/api/file', '/ui/api/feed/thumb'):
            route.fulfill(content_type='image/svg+xml', body='<svg xmlns="http://www.w3.org/2000/svg" width="320" height="480"><rect width="320" height="480" fill="#345"/></svg>'); return
        route.fulfill(content_type='application/json', body=json.dumps(result))

    page.route('**/ui/api/**', api)
    active = page.locator('.fa-slide.is-active')
    open_share = active.get_by_role('button', name='分享与更多操作', exact=True)
    screenshot = page.get_by_role('button', name='分享截图', exact=True)
    close = page.locator('.fa-sheet-head').get_by_role('button', name='关闭', exact=True)

    def assert_file(expected):
        file = page.evaluate('shared.at(-1)')
        assert file['hash'] == expected, 'Shared pixels changed after the original Share tap'
        assert page.evaluate('captureDuringTap && Math.abs(captureTime-tapTime)<0.1'), 'Capture was delayed past the original tap'
        assert (file['width'], file['height'], file['type'], file['count']) == (320, 480, 'image/png', 1)
        assert file['name'].endswith('.png') and file['url'] is None and file['sync']

    try:
        page.goto(args.url + '/ui/feed')
        page.wait_for_function("document.querySelector('.fa-slide.is-active video')?.paused===false")
        page.wait_for_timeout(400)
        open_share.click()
        expect(screenshot).to_be_enabled()
        expected = page.evaluate('expected')
        assert page.evaluate('tapPaused') is False
        # Let playback advance to different pixels before choosing screenshot share.
        page.wait_for_function("document.querySelector('.fa-slide.is-active video').currentTime > tapTime+0.8")
        page.screenshot(path=f'/tmp/feed-screenshot-{engine.name}-sheet.png', animations='disabled')
        screenshot.click()
        expect(page.locator('.fa-sheet')).to_have_count(0)
        assert_file(expected)

        # Paused frames stay paused and retain exactly their existing pixels.
        active.locator('.fa-surface-video').tap(position={'x': 150, 'y': 220})
        page.wait_for_function("document.querySelector('.fa-slide.is-active video').paused")
        paused_time = page.evaluate("document.querySelector('.fa-slide.is-active video').currentTime")
        open_share.click()
        expect(screenshot).to_be_enabled()
        expected = page.evaluate('expected')
        assert page.evaluate('tapPaused') is True
        save = page.get_by_role('link', name='保存截图', exact=True)
        href = save.get_attribute('href')
        saved = page.evaluate('async url=>filePixels(await (await fetch(url)).blob())', href)
        assert saved['hash'] == expected
        page.set_viewport_size({'width': 1280, 'height': 800})
        expect(screenshot).to_be_visible()
        expect(save).to_be_visible()
        page.screenshot(path=f'/tmp/feed-screenshot-{engine.name}-desktop.png', animations='disabled')
        page.set_viewport_size({'width': 390, 'height': 844})
        page.evaluate("outcome='AbortError'")
        screenshot.click()
        expect(screenshot).to_be_enabled()
        assert_file(expected)
        page.evaluate("outcome='NotAllowedError'")
        screenshot.click()
        expect(page.locator('.fa-share-status')).to_contain_text('再次点')
        page.evaluate("outcome='success'")
        screenshot.click()
        expect(page.locator('.fa-sheet')).to_have_count(0)
        assert_file(expected)
        assert page.evaluate("document.querySelector('.fa-slide.is-active video').currentTime") == paused_time
        assert page.evaluate("document.querySelector('.fa-slide.is-active video').paused")
        assert page.evaluate('async url=>{try{await fetch(url);return false;}catch{return true;}}', href), 'Object URL leaked after closing'

        page.evaluate('fileSupported=false')
        open_share.click()
        screenshot.click()
        expect(page.locator('.fa-share-status')).to_contain_text('保存截图')
        expect(page.get_by_role('link', name='保存截图', exact=True)).to_be_visible()
        close.click()

        # Encoding failure must not silently share another frame or reject unhandled.
        page.evaluate("() => { window.realToBlob=HTMLCanvasElement.prototype.toBlob; HTMLCanvasElement.prototype.toBlob=()=>{throw new DOMException('Blocked','SecurityError')}; }")
        open_share.click()
        expect(page.get_by_role('button', name='截图不可用', exact=True)).to_be_disabled()
        expect(page.locator('.fa-share-status')).to_contain_text('无法读取')
        close.click()
        page.evaluate('() => { HTMLCanvasElement.prototype.toBlob=realToBlob; }')

        # Closing during asynchronous PNG encoding must never share afterward.
        page.evaluate('''() => {
          HTMLCanvasElement.prototype.toBlob=function(callback,...args) {
            window.finishSnapshot=()=>realToBlob.call(this,callback,...args);
          };
        }''')
        count = page.evaluate('shared.length')
        open_share.click()
        expect(page.get_by_role('button', name='正在截图…', exact=True)).to_be_disabled()
        close.click()
        page.evaluate('() => { finishSnapshot(); HTMLCanvasElement.prototype.toBlob=realToBlob; }')
        page.wait_for_timeout(150)
        assert page.evaluate('shared.length') == count
        expect(page.locator('.fa-sheet')).to_have_count(0)

        # Photos retain their normal image-sharing action, with no screenshot option.
        page.locator('.fa-pager').first.evaluate('(e)=>e.scrollTo({top:e.clientHeight,behavior:"instant"})')
        expect(active.locator('.fa-carousel')).to_be_visible()
        open_share.click()
        expect(page.get_by_role('button', name='分享图片', exact=True)).to_be_visible()
        expect(screenshot).to_have_count(0)
        assert not errors, errors
        print(engine.name, 'PASS: tap-time PNG pixels, playback advances, exact paused frame, save, cancellation/retry, synchronous OS share, unsupported fallback, encoding failure, URL cleanup, normal photo share')
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
