#!/usr/bin/env python3
"""Capture the built WebUI using fictional records and licensed sample photos.

Requires Playwright. See docs/screenshot/webui/README.md for usage and credits.
All browser requests are intercepted; no production service is contacted.
"""
import argparse
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'src/webui/static'
OUTPUT = ROOT / 'docs/screenshot/webui'
NAMES = ['山野日记', '一杯慢生活', '城市漫步', '湖畔来信']
PHOTOS = ['mountains.jpg', 'coffee.jpg', 'city.jpg', 'lake.jpg']
STAMP = '2026-11-07 10:24:00'


def capture(args):
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for photo in PHOTOS:
        if not (args.media_dir / photo).is_file():
            raise SystemExit(f'Missing demo photo: {args.media_dir / photo}')
    accounts = [dict(key=f'demo-{i}', platform='douyin', url=f'https://example.com/demo/{i}',
                     name=name, nickname=name, handle=f'demo_{i}', bio='记录日常，收藏喜欢的风景。',
                     uid=f'demo-{i}', avatar={'scope':'download','path':PHOTOS[i],'second':0},
                     cover=PHOTOS[i], followed=i==0, latest_ts=1794018240,
                     stats={'posts':12+i*8,'videos':4+i*2,'images':8+i*6,'likes':1200+i*860})
                for i,name in enumerate(NAMES)]
    posts = [dict(key=f'post-{i}',kind='images',published_ts=1794018240-i*86400,
                  caption=['把山间的宁静，留在这一刻。 #山野 #旅行', '今天也从一杯咖啡开始。 #咖啡 #日常',
                           '天色渐暗，城市刚刚醒来。 #城市 #街拍', '在湖边，慢慢度过一个下午。 #自然 #旅行'][i%4],
                  tags=['旅行','日常'],duration=None,width=1000,height=1500,
                  stats={'likes':1280+i*91,'comments':26+i,'saves':184+i*12,'shares':38+i},
                  music=None,work_id=f'demo-post-{i}',share_url=f'https://example.com/demo/post/{i}',
                  media=[{'path':PHOTOS[i%4],'kind':'image'}],cover=PHOTOS[i%4],
                  liked=False,saved=False,pinned=False,meta_pending=False,author=accounts[i%4])
             for i in range(8)]
    board = [dict(platform='douyin',url=a['url'],mark=a['name'],enable=True,
                  folder_path=f"demo/{a['key']}",media_path=a['cover'],media_kind='image',pinned=True,
                  avatar_path=a['cover'],avatar_scope='download',last_status='success',
                  last_outcome_code='success',last_checked_at=STAMP,latest_work_at=STAMP,
                  latest_saved_work_at=STAMP) for a in accounts]
    board += [{**item, 'url':f'https://example.com/demo/{i+4}',
               'mark':['山间拾光','咖啡手记','雨夜街角','远山回声'][i]} for i,item in enumerate(board)]
    summary={'total':24,'success':18,'failed':0,'skipped':0,'pending':5,'running':1}
    task=dict(task_id='T000024',endpoint='/workflow/douyin/account_batch',status='running',
              created_at='2026-11-07 10:00:00',started_at='2026-11-07 10:00:00',updated_at=STAMP,
              message='正在采集账号：湖畔来信',progress={'current':18,'total':24,'success':18,'failed':0,
              'skipped':0,'percent':75,'label':'采集中'},account_summary=summary,pause_supported=True)
    completed={**task,'task_id':'T000023','status':'success','finished_at':'2026-11-06 10:32:00',
               'created_at':'2026-11-06 10:00:00','started_at':'2026-11-06 10:00:00','updated_at':'2026-11-06 10:32:00',
               'message':'账号批量下载任务完成','progress':{**task['progress'],'current':24,'success':24,'percent':100},
               'account_summary':{**summary,'success':24,'pending':0,'running':0}}
    status=dict(phase='idle',done=24,total=24,accounts=24,posts=864,metadata_available=True,
                metadata_done=864,metadata_total=864,last_finished_at=1794018240,error='')
    overview={'media':{'status':'ready','size':18432102400,'videos':324,'images':540,'files':864,
                      'folders':24,'other_files':0,'refreshed_at':STAMP,'latest_updated_at':STAMP,
                      'storage':{'used_percent':18.4,'free':81600000000},'integrity':{}},
              'crawl':{'current':task,'latest':task,'latest_success':completed,'latest_ended':completed},
              'collectors':{'total':2,'routable':2,'healthy':2,'proxy_configured':0,'active_leases':1,
                            'risk_failures':0,'cooldown':0,'cookie_configured':2,
                            'identities':[{'name':'演示身份 · 抖音','platform':'douyin','success_rate':100},
                                          {'name':'演示身份 · TikTok','platform':'tiktok','auth_mode':'cookie','success_rate':100}],
                            'platforms':{'douyin':1,'tiktok':1}},
              'maintenance':{}}
    errors=[]

    def route(r):
        u=urlsplit(r.request.url); p=u.path; q=parse_qs(u.query)
        if p in ('/ui','/ui/','/ui/feed'):
            return r.fulfill(path=ASSETS/'index.html',content_type='text/html')
        if p.startswith('/ui/static/'):
            target=(ASSETS/p.removeprefix('/ui/static/')).resolve()
            if target.is_relative_to(ASSETS.resolve()) and target.is_file():return r.fulfill(path=target)
            return r.fulfill(status=404,body='')
        if p in ('/ui/api/file','/ui/api/feed/thumb'):
            name=Path(q.get('path',[PHOTOS[0]])[0]).name
            return r.fulfill(path=args.media_dir/(name if name in PHOTOS else PHOTOS[0]),content_type='image/jpeg')
        data={'items':[],'preferences':{},'page':1,'pages':1,'total':0}
        if p=='/ui/api/overview':data=overview
        elif p=='/ui/api/tasks':data={'items':[task,completed],'running':1,'pending':0,'paused':0}
        elif p=='/ui/api/tasks/T000024':data={'task':task}
        elif p.endswith('/T000024/accounts'):
            data={'items':[{'position':i+1,'status':'success','configured':True,
                           'item':{'mark':name,'url':accounts[i]['url']},'outcome_code':'success',
                           'context':{'item_count':12+i*8},'reason':'采集完成，媒体已保存'} for i,name in enumerate(NAMES)],
                  'summary':summary,'page':1,'pages':1,'filtered_total':4,'category_counts':{}}
        elif p=='/ui/api/accounts/board':data={'items':board,'total':len(board),'unfiltered_total':len(board),'page':1,'pages':1}
        elif p=='/ui/api/feed/status':data=status
        elif p=='/ui/api/feed/posts':data={'items':posts,'next_cursor':None}
        elif p=='/ui/api/feed/accounts':data={'items':accounts,'total':4,'next_offset':None}
        elif p=='/ui/api/feed/account':data=next((a for a in accounts if a['key']==q.get('key',[''])[0]),accounts[0])
        elif p=='/ui/api/feed/me':data={'likes':12,'saves':8,'following':4,'hidden':0,'index':status}
        elif p=='/ui/api/feed/tags':data={'items':[{'tag':'旅行','count':32},{'tag':'日常','count':24}]}
        elif p=='/settings':data={'accounts_urls':[{'url':a['url'],'mark':a['name'],'enable':True} for a in accounts],'accounts_urls_tiktok':[],'deleted_accounts':[],'deleted_accounts_tiktok':[]}
        return r.fulfill(json=data)

    with sync_playwright() as pw:
        browser=pw.chromium.launch(**({'executable_path':args.chromium} if args.chromium else {}))
        def new_page(width,height):
            page=browser.new_page(viewport={'width':width,'height':height},device_scale_factor=1,
                                  is_mobile=width<700,has_touch=width<700)
            page.set_default_timeout(10000)
            page.route('**/*',route)
            page.route_web_socket('**/*',lambda ws:None)
            page.add_init_script("localStorage.setItem('webui.board.view_mode','immersive'); localStorage.setItem('feed.sound','0'); localStorage.setItem('webui.theme','light');")
            page.on('pageerror',lambda error:errors.append(str(error)))
            return page
        def shoot(page,name):
            page.evaluate("document.activeElement?.blur()")
            page.wait_for_timeout(1500)
            page.screenshot(path=OUTPUT/name,type='jpeg',quality=90,animations='disabled')
            print(name,flush=True)
        page=new_page(1440,1000)
        page.goto('https://demo.fetchshelf.test/ui')
        page.wait_for_timeout(1500)
        page.locator('#overview-video-count').filter(has_text='324').wait_for()
        page.locator('#workbench-quick-download').evaluate('(el)=>el.open=false')
        page.locator('#workbench-task-center').evaluate('(el)=>el.open=true')
        page.locator('.task-row[data-task-id="T000024"] .task-main-button').click()
        shoot(page,'workbench.jpg')
        page.locator('[data-tab-target="profiles"]').click()
        page.locator('.profile-card').first.wait_for()
        page.wait_for_function("[...document.querySelectorAll('.profile-media-wrap img')].every(i=>i.complete && i.naturalWidth>0)")
        page.set_viewport_size({'width':1440,'height':900})
        shoot(page,'account-board.jpg')
        page.goto('https://demo.fetchshelf.test/ui/feed')
        page.locator('.fa-slide .fa-caption').first.wait_for()
        page.wait_for_function("[...document.querySelectorAll('.fa-slide img')].some(i=>i.complete&&i.naturalWidth>0)")
        shoot(page,'immersive-desktop.jpg')
        posts[:] = posts[2:] + posts[:2]
        phone=new_page(390,844)
        phone.goto('https://demo.fetchshelf.test/ui/feed')
        phone.locator('.fa-slide .fa-caption').first.wait_for()
        phone.wait_for_function("[...document.querySelectorAll('.fa-slide img')].some(i=>i.complete&&i.naturalWidth>0)")
        shoot(phone,'immersive-mobile.jpg')
        assert not errors,errors
        browser.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--media-dir',type=Path,required=True)
    parser.add_argument('--chromium',help='Optional Chromium executable')
    capture(parser.parse_args())
