# TikTok-Api 集成与实现说明

> 基于当前本地仓库快照编写：`TikTok-Api/`
>
> 目标读者：准备把 `TikTok-Api` 的实现迁移/patch 到现有项目中的开发者。

## 1. 总体结论

`TikTok-Api` 不是“纯接口直连”的实现，而是 **浏览器辅助签名 + 浏览器上下文内发请求** 的实现。

核心思路如下：

1. 先用 `Playwright` 打开 TikTok 页面，拿到真实浏览器环境。
2. 记录浏览器请求头、生成 `msToken`、维持 Cookie 会话。
3. 在页面里调用 `window.byted_acrawler.frontierSign(...)` 给请求补 `X-Bogus`。
4. 再通过 `page.evaluate(fetch(...))` 在浏览器上下文里请求 TikTok Web API。
5. 对视频详情页这类场景，直接请求公开视频 HTML，并解析页面中的 JSON。

这也是它比“纯 requests + 固定签名参数”更容易存活的原因：**签名、Cookie、浏览器环境、JS 运行时都来自真实浏览器上下文**。

---

## 2. 请求链路总览

### 2.1 会话创建

入口是 `TikTokApi.create_sessions(...)`。

主要流程：

1. 启动 `Playwright`
2. 根据参数选择 `chromium` / `firefox` / `webkit`
3. 创建 BrowserContext
4. 注入已有 Cookie / `msToken`
5. 新建页面并执行 `stealth_async(page)`
6. 打开 `starting_url`
7. 采集浏览器环境参数，组装为公共 query 参数
8. 后续所有 API 请求都复用这个 session

### 2.2 公共 query 参数

绝大多数 Web API 请求都会自动带上这一批 session 级参数：

- `aid=1988`
- `app_language`
- `app_name=tiktok_web`
- `browser_language`
- `browser_name=Mozilla`
- `browser_online=true`
- `browser_platform`
- `browser_version`
- `channel=tiktok_web`
- `cookie_enabled=true`
- `device_id`
- `device_platform=web_pc`
- `focus_state=true`
- `from_page=user`
- `history_len`
- `is_fullscreen=false`
- `is_page_visible=true`
- `language`
- `os`
- `priority_region`
- `referer`
- `region`
- `screen_height`
- `screen_width`
- `tz_name`
- `webcast_language`

其中 `userAgent`、语言、平台、时区来自浏览器运行时；`device_id`、`history_len`、屏幕尺寸等由库在会话初始化时生成。

### 2.3 签名与请求发送

所有 Web API 请求基本都走统一的 `make_request(...)`：

1. 合并 session 公共参数和接口专属参数
2. 如果当前参数中没有 `msToken`，则优先从 session 中读取，再从 session cookies 中读取
3. 拼接 URL
4. 调用浏览器页面中的 `window.byted_acrawler.frontierSign(url)` 生成 `X-Bogus`
5. 把 `X-Bogus` 追加到 URL
6. 用 `page.evaluate(fetch(...))` 在页面上下文里执行请求
7. 解析返回的 JSON

因此它的关键并不只是知道某个接口 URL，而是：

- 要有能工作的浏览器上下文
- 要能从浏览器页面里生成 `X-Bogus`
- 要能在浏览器上下文里带着 Cookie 发起请求

---

## 3. 账户信息提取是怎么做的

### 3.1 用户基础信息 `user.info()`

调用链：

- `api.user(username=...).info()`
- 接口：`https://www.tiktok.com/api/user/detail/`

专属参数：

- `uniqueId`
- `secUid`（可为空；如果已有则会一起传）
- `msToken`（可显式传，也可由 session 自动补）

返回后，库会从以下字段里提取并回填对象属性：

- `userInfo.user.id`
- `userInfo.user.secUid`
- `userInfo.user.uniqueId`

因此对集成来说，**`user.detail` 是更可靠的 `secUid` 获取入口**，比手写正则从主页 HTML 里抓更稳。

### 3.2 用户视频列表 `user.videos()`

调用链：

- `api.user(...).videos(count=?, cursor=?)`
- 接口：`https://www.tiktok.com/api/post/item_list/`

专属参数：

- `secUid`
- `count`
- `cursor`

实现特点：

- 如果还没有 `secUid`，会先自动调用 `user.info()`
- 每页默认请求 `30`
- 通过 `hasMore` + `cursor` 翻页
- 每个 `itemList` 元素都会被包装成 `Video` 对象

### 3.3 用户合集列表 `user.playlists()`

调用链：

- `api.user(...).playlists(count=?, cursor=?)`
- 接口：`https://www.tiktok.com/api/user/playlist`

专属参数：

- `secUid`
- `count`
- `cursor`

### 3.4 用户喜欢列表 `user.liked()`

调用链：

- `api.user(...).liked(count=?, cursor=?)`
- 接口：`https://www.tiktok.com/api/favorite/item_list`

专属参数：

- `secUid`
- `count`
- `cursor`

注意：

- 这个实现针对的是 **公开可见的 liked/favorite 列表**
- 代码测试里使用的也是公开喜欢列表账号
- 登录态不会绕过目标用户自己的隐私设置

---

## 4. 视频信息提取与下载

### 4.1 `api.video(url=...)` 如何拿到视频 ID

如果你传的是视频 URL 而不是视频 ID：

1. 直接从传入 URL 解析 `/video/{id}`
2. 也兼容 `/photo/{id}` 这种规范作品链接
3. 如果传入的是短链/跳转链接，应该在外层先展开成规范作品链接再交给 `TikTokApi`

因此：

- 规范作品链接可以直接被解析
- 这一步不走 TikTok Web JSON API
- 现在也不会再为了拿视频 ID 额外发一次 `HEAD`

### 4.2 视频详情 `video.info()`

这一步 **不是调用 TikTok Web JSON API**，而是通过当前浏览器 session 打开公开视频页面并解析 HTML。

流程如下：

1. `get_session_page_payload(video_url)`，底层是当前浏览器页面 `page.goto(...)`
2. 优先解析页面里的：
   - `<script id="SIGI_STATE" type="application/json">`
3. 如果没有，再解析：
   - `<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__" type="application/json">`
4. 从页面 JSON 中提取视频结构：
   - `ItemModule[video_id]`
   - 或 `__DEFAULT_SCOPE__.webapp.video-detail.itemInfo.itemStruct`

这意味着：

- `video.info()` 对“公开视频”有较强兼容性
- 即使某些 `/api/...` 路由有风控，公开视频 HTML 仍然可能可用
- 这一页请求同样复用了浏览器 session，而不是退回 Python `requests`

### 4.3 视频下载 `video.bytes()`

视频下载并不是单独再去调某个固定 Web JSON 接口，而是直接使用视频对象数据里的媒体地址：

- 优先：`video.downloadAddr`
- 其次：`video.playAddr`
- 再补充：`PlayAddrStruct.UrlList`
- 再补充：`bitrateInfo[*].PlayAddr.UrlList`

下载流程：

1. 从 `self.as_dict["video"]` 中收集所有可用媒体地址
2. 读取当前 Playwright session cookies
3. 组装 headers：
   - `range: bytes=0-`
   - `accept-encoding: identity;q=1, *;q=0`
   - `referer: https://www.tiktok.com/`
4. 非流式模式：优先在浏览器上下文里 `fetch_binary(...)`
5. 如果浏览器 `fetch` 拿不到有效媒体，再回退到 `capture_media_response(...)`，通过页面网络响应捕获视频体
6. 流式模式：优先走浏览器 `Range` 分块抓取；如果 CDN / CORS 不配合，再退成浏览器整包抓取后按 chunk 吐出

也就是说，当前实现的媒体下载主路径已经不再是 Python `requests/httpx`，而是 **浏览器上下文优先**。

### 4.4 `video.bytes()` 的实际注意点

虽然仓库里已经有可运行实现，但仍要注意：

- `video.bytes()` 依赖 `video.as_dict`
- 如果你只有 `video_id`，而没有先拿到 `video.info()` 或列表返回的 `itemStruct`，下载很可能拿不到地址
- 上游代码中的 docstring 仍写着 `TODO: Not implemented yet`
- 对应测试 `test_video_bytes()` 也是跳过状态
- 浏览器上下文下载仍然依赖当前 profile、Cookie、地区与账号权限状态；它能降低 Python HTTP 客户端带来的额外风控暴露，但不能绕过视频本身的权限限制

所以在 patch 到你自己的项目时，推荐的下载顺序是：

1. 先通过 `user.videos()` / `search` / `video.info()` 拿到完整 `video.as_dict`
2. 再调用下载逻辑

### 4.5 非登录状态能不能下载视频

对 **公开视频** 来说，答案通常是 **可以，但不稳定**。

原因：

- `video.info()` 走的是公开 HTML 页面
- `bytes()` 走的是公开视频结构里返回的媒体地址
- 这两步本质上都不要求你先拥有“完整账号登录态”

但实际可用性取决于：

- 当前 IP/代理的风控情况
- 当前 `msToken` 是否还能工作
- 视频是否公开
- 是否有地区限制、年龄限制、作者权限限制
- TikTok 是否只返回 `playAddr` 而不返回 `downloadAddr`

因此更准确的结论是：

- **非登录态可以用于抓取和下载部分公开视频**
- **完整登录态通常只会提升稳定性与可见性，不保证绕过私密/权限限制**

---

## 5. 登录态与非登录态的区别

### 5.1 这个库“支持登录”吗

严格说：

- 它的路由设计仍然以 **公开数据读取** 为主
- 但它的 session 层 **支持带 Cookie 的登录浏览器上下文**
- 也支持自定义 `page_factory` / `browser_context_factory` 去做登录流程

所以更准确的说法是：

- **支持携带登录态的浏览器会话**
- **不等于实现了完整的“账号功能 API SDK”**

### 5.2 非登录态

典型输入：

- 不传完整登录 Cookie
- 只传 `msToken`
- 或完全依赖会话启动后自动生成 `msToken`

通常可做的事情：

- 读取公开用户资料
- 读取公开视频列表
- 读取公开视频详情页 HTML
- 下载部分公开视频
- 读取热门、公开挑战、公开音乐、公开视频评论等

常见问题：

- 返回空响应
- 视频数量不全
- 搜索结果异常
- 更容易触发风控

### 5.3 登录态

典型输入：

- 直接传完整浏览器 Cookie
- 或使用自定义 Playwright 登录流程，登录完成后再创建 session

可能带来的收益：

- 提高请求稳定性
- 减少“空响应 / JSON 失效”
- 更接近你在真实浏览器登录后看到的页面状态
- 某些列表完整度可能更高

但登录态 **不能保证**：

- 访问私密账号内容
- 绕过好友可见/年龄限制/地区限制
- 自动获取所有受限字段

### 5.4 维持登录态需要什么

如果你只是想“让 TikTok-Api 更像登录浏览器”：

- 推荐直接导入浏览器里导出的整包 TikTok Cookie

最关键的通常包括：

- `msToken`
- `sessionid`
- `sessionid_ss`
- `sid_tt`
- `uid_tt`
- `ttwid`
- `tt_csrf_token`
- `tt_chain_token`

其中：

- `msToken` 是几乎所有 Web API 请求都高度依赖的参数
- `sessionid/sessionid_ss/sid_tt` 更接近真正的账号登录态

如果只传 `msToken`，很多时候只是“更像一个带 token 的访客态”，并不等于完整登录。

---

## 6. Headless、浏览器、代理如何控制

### 6.1 `headless`

在 `create_sessions(...)` 里直接控制：

```python
await api.create_sessions(
    num_sessions=1,
    headless=True,
)
```

行为细节：

- `chromium` 下如果你传 `headless=True` 且没传 `override_browser_args`
- 库会自动改成 `args=["--headless=new"]`
- 并把 Playwright 的 `headless` 设为 `False`

这是它对 Chromium 新版 headless 模式做的兼容处理。

### 6.2 切换浏览器内核

可选值：

- `browser="chromium"`
- `browser="firefox"`
- `browser="webkit"`

在风控更严时，`webkit` 有时会比 `chromium` 更容易过。

### 6.3 代理

有两种模式：

### 方式 A：旧式 `proxies`

```python
await api.create_sessions(
    proxies=[{"server": "http://host:port"}],
)
```

### 方式 B：`proxy_provider`

适合轮换代理池，优先推荐。

### 6.4 自定义浏览器上下文

可以用 `browser_context_factory` 自己创建持久化浏览器上下文，例如：

- 复用本地用户目录
- 预置登录态
- 接入验证码处理器

### 6.5 自定义页面工厂

可以用 `page_factory`：

- 自己决定打开哪个页面
- 自己写登录动作
- 自己等待验证码完成

这个能力非常适合 patch 现有项目时做“首次人工登录，后续复用 Cookie”。

---

## 7. TikTok-Api 实际使用到的 TikTok 接口

下表列出当前代码里直接出现的主要 TikTok Web 路由。

### 7.1 用户相关

| 方法 | 接口 | 主要专属参数 | 说明 |
| --- | --- | --- | --- |
| `user.info()` | `/api/user/detail/` | `uniqueId`, `secUid`, `msToken` | 获取用户基础信息，返回 `userInfo` |
| `user.videos()` | `/api/post/item_list/` | `secUid`, `count`, `cursor` | 获取用户公开视频列表 |
| `user.playlists()` | `/api/user/playlist` | `secUid`, `count`, `cursor` | 获取用户合集列表 |
| `user.liked()` | `/api/favorite/item_list` | `secUid`, `count`, `cursor` | 获取公开喜欢列表 |

### 7.2 视频相关

| 方法 | 接口/来源 | 主要专属参数 | 说明 |
| --- | --- | --- | --- |
| `video.info()` | 视频公开 HTML 页 | 视频 URL | 解析 `SIGI_STATE` 或 `__UNIVERSAL_DATA_FOR_REHYDRATION__` |
| `video.comments()` | `/api/comment/list/` | `aweme_id`, `count`, `cursor` | 获取评论 |
| `video.related_videos()` | `/api/related/item_list/` | `itemID`, `count` | 获取相关视频 |
| `video.bytes()` | `downloadAddr` / `playAddr` / `PlayAddrStruct` / `bitrateInfo` | 无固定专属 query | 浏览器上下文优先请求 CDN 媒体地址 |

### 7.3 评论相关

| 方法 | 接口 | 主要专属参数 | 说明 |
| --- | --- | --- | --- |
| `comment.replies()` | `/api/comment/list/reply/` | `count`, `cursor`, `item_id`, `comment_id` | 获取评论回复 |

### 7.4 趋势 / 搜索 / 话题 / 音乐 / 合集

| 方法 | 接口 | 主要专属参数 | 说明 |
| --- | --- | --- | --- |
| `trending.videos()` | `/api/recommend/item_list/` | `from_page=fyp`, `count` | 热门/FYP 内容 |
| `search.users()` | `/api/search/user/full/` | `keyword`, `cursor`, `from_page`, `web_search_code`, `search_id?` | 搜索用户 |
| `hashtag.info()` | `/api/challenge/detail/` | `challengeName`, `msToken` | 话题详情 |
| `hashtag.videos()` | `/api/challenge/item_list/` | `challengeID`, `count`, `cursor` | 话题视频 |
| `sound.info()` | `/api/music/detail/` | `musicId`, `msToken` | 音乐详情 |
| `sound.videos()` | `/api/music/item_list/` | `musicID`, `count`, `cursor` | 音乐视频列表 |
| `playlist.info()` | `/api/mix/detail/` | `mixId`, `msToken` | 合集详情 |
| `playlist.videos()` | `/api/mix/item_list/` | `mixId`, `count`, `cursor` | 合集视频列表 |

补充说明：

- `search.search_type(...)` 支持泛化路由 `search/{obj_type}/full/`
- 但当前代码注释明确写了：公开稳定支持主要是 `user` 搜索，其他搜索类型可能需要更强的认证条件

### 7.5 所有这些接口的共同点

无论具体路由是什么，真正发出前通常都会自动附带：

- 会话级公共 query 参数
- `msToken`
- `X-Bogus`
- 浏览器会话 Cookie
- 浏览器请求头

所以迁移时不要只抄 endpoint 名称；**请求构造方式比 endpoint 本身更重要**。

---

## 8. 参数层面的迁移重点

如果你打算把这套逻辑 patch 到自己的项目，最值得迁移的是下面几个部分。

### 8.1 会话初始化

建议保留：

- Playwright 浏览器上下文
- `stealth_async(page)`
- Cookie 注入
- `msToken` 注入
- 浏览器环境参数采集

### 8.2 URL 签名

建议直接复用思路：

- 在页面里调用 `window.byted_acrawler.frontierSign(url)`
- 把返回的 `X-Bogus` 追加到 URL

如果你丢掉这一层，只保留 endpoint + 参数模板，请求大概率又会退回到“偶尔成功、经常空响应”的状态。

### 8.3 用户数据链路

推荐顺序：

1. `user.detail` 获取 `secUid`
2. `post.item_list` 获取视频列表
3. 必要时翻页，直到 `hasMore=false`

### 8.4 视频详情 fallback

建议把 `video.info()` 的 HTML 解析逻辑也一起迁移：

- 先尝试 `SIGI_STATE`
- 再尝试 `__UNIVERSAL_DATA_FOR_REHYDRATION__`

这能在 Web API 受限时补回视频结构和下载地址。

### 8.5 下载逻辑

推荐直接复用：

- `downloadAddr` 优先
- `playAddr` 兜底
- 带 session cookies
- 带 `Range` 头
- 带 `Referer: https://www.tiktok.com/`

---

## 9. 对当前 patch 工作的建议

如果你准备把这套实现并入现有项目，建议按下面优先级做：

### 第一阶段：先替换“请求底座”

替换现有：

- 纯 HTTP 请求层
- 自己拼签名的逻辑
- 单纯依赖固定接口模板的调用方式

换成：

- `Playwright session`
- 浏览器内签名
- 浏览器上下文发请求

### 第二阶段：替换 `secUid` 获取方式

不要再依赖脆弱的主页正则提取，改成：

- `user.detail` 返回的 `userInfo.user.secUid`

### 第三阶段：增加 HTML fallback

把 `video.info()` 这套：

- 公开页面 HTML
- `SIGI_STATE`
- `__UNIVERSAL_DATA_FOR_REHYDRATION__`

一起移植进去。

### 第四阶段：把 Cookie/登录态做成可插拔

建议支持三种模式：

1. 仅 `msToken`
2. 完整 Cookie 导入
3. Playwright 登录后回存 Cookie

这样便于你做长期 debug 和回归测试。

---

## 10. 一句话结论

如果你只想提炼最关键的设计：

- **账户信息提取**：靠 `user/detail` + `post/item_list`
- **视频详情 fallback**：靠公开视频 HTML 中的 `SIGI_STATE` / `__UNIVERSAL_DATA_FOR_REHYDRATION__`
- **视频下载**：靠 `downloadAddr` / `playAddr`
- **登录态**：完整 Cookie > 只有 `msToken` > 纯游客
- **稳定性的关键**：不是 endpoint 名字，而是 **浏览器上下文 + `X-Bogus` + Cookie + 页面内 fetch**
