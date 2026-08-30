from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Callable
from urllib.parse import parse_qs, unquote, urlsplit

from playwright.async_api import BrowserContext, Page, async_playwright

__all__ = [
    "DouyinBrowserCollectionError",
    "cookie_header_to_playwright",
    "fetch_douyin_collection_via_browser",
    "fetch_douyin_favorites_via_browser",
]


class DouyinBrowserCollectionError(RuntimeError):
    """Raised when Douyin's browser-only collection flow cannot be completed."""

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "douyin_browser_collection_failed",
    ) -> None:
        super().__init__(message)
        self.error_code = str(error_code or "douyin_browser_collection_failed")
        self.identity_id = ""


def cookie_header_to_playwright(cookie: str) -> list[dict[str, Any]]:
    """Convert a Cookie header value into cookies scoped only to Douyin."""

    value = str(cookie or "").strip()
    if value.lower().startswith("cookie:"):
        value = value.split(":", 1)[1].strip()

    cookies: list[dict[str, Any]] = []
    for part in value.split(";"):
        if "=" not in part:
            continue
        name, item = part.strip().split("=", 1)
        if not name:
            continue
        cookies.append(
            {
                "name": name,
                "value": item,
                "domain": ".douyin.com",
                "path": "/",
                "secure": True,
            }
        )
    return cookies


def _playwright_proxy(proxy: str | None) -> dict[str, str] | None:
    value = str(proxy or "").strip()
    if not value:
        return None
    parsed = urlsplit(value)
    if not parsed.scheme or not parsed.hostname:
        return {"server": value}

    host = parsed.hostname
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    server = f"{parsed.scheme}://{host}"
    if parsed.port:
        server = f"{server}:{parsed.port}"
    result = {"server": server}
    if parsed.username:
        result["username"] = unquote(parsed.username)
    if parsed.password:
        result["password"] = unquote(parsed.password)
    return result


def _should_update_collection_pagination(
    existing_count: int,
    response_count: int,
) -> bool:
    """Ignore a late one-item folder-card preview after the full page arrived."""

    return not (existing_count > 1 and response_count <= 1)


async def _click_first_visible(locator, timeout_seconds: float) -> bool:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds
    while loop.time() < deadline:
        try:
            for index in range(await locator.count()):
                item = locator.nth(index)
                if await item.is_visible():
                    await item.click()
                    return True
        except Exception:
            # Douyin replaces parts of the page while hydrating. Retry a fresh
            # locator until the deadline instead of retaining a detached node.
            pass
        await asyncio.sleep(0.5)
    return False


async def _wait_for(
    predicate: Callable[[], bool],
    timeout_seconds: float,
    interval: float = 0.25,
) -> bool:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds
    while loop.time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(interval)
    return predicate()


async def _open_context(browser, user_agent: str = "") -> BrowserContext:
    options: dict[str, Any] = {
        "locale": "zh-CN",
        "viewport": {"width": 1536, "height": 864},
    }
    if value := str(user_agent or "").strip():
        options["user_agent"] = value
    return await browser.new_context(**options)


async def _douyin_login_prompt_visible(page: Page) -> bool:
    """Return whether the self page is presenting an interactive login panel."""

    for label in ("验证码登录", "扫码登录"):
        locator = page.get_by_text(label, exact=True)
        try:
            for index in range(await locator.count()):
                if await locator.nth(index).is_visible():
                    return True
        except Exception:
            # Hydration can replace the login panel while it is being checked.
            # A later check after the collection-tab lookup will retry it.
            continue
    return False


def _collection_trace(event: str, **data: Any) -> None:
    if os.environ.get("FETCHSHELF_COLLECTION_TRACE") != "1":
        return
    print(
        json.dumps({"collection_trace": event, **data}, ensure_ascii=False),
        flush=True,
    )


async def _scroll_collection_surfaces(page: Page) -> list[dict[str, Any]]:
    """Scroll document and nested virtual-list containers to their bottoms."""

    result = await page.evaluate(
        """
        () => {
          const nodes = [document.scrollingElement, ...document.querySelectorAll('*')];
          const seen = new Set();
          const scrolled = [];
          for (const node of nodes) {
            if (!node || seen.has(node)) continue;
            seen.add(node);
            const clientHeight = Number(node.clientHeight || 0);
            const scrollHeight = Number(node.scrollHeight || 0);
            if (clientHeight <= 0 || scrollHeight <= clientHeight + 40) continue;
            const style = window.getComputedStyle(node);
            const overflowY = String(style.overflowY || '');
            const isDocument = node === document.scrollingElement;
            if (!isDocument && !['auto', 'scroll', 'overlay'].includes(overflowY)) {
              continue;
            }
            const before = Number(node.scrollTop || 0);
            node.scrollTop = scrollHeight;
            node.dispatchEvent(new Event('scroll', {bubbles: true}));
            scrolled.push({
              tag: String(node.tagName || 'document').toLowerCase(),
              class_name: String(node.className || '').slice(0, 120),
              overflow_y: overflowY,
              before,
              after: Number(node.scrollTop || 0),
              client_height: clientHeight,
              scroll_height: scrollHeight,
            });
          }
          window.scrollTo(0, document.body.scrollHeight);
          return scrolled
            .sort((a, b) => (b.scroll_height - b.client_height) - (a.scroll_height - a.client_height))
            .slice(0, 12);
        }
        """
    )
    return result if isinstance(result, list) else []


async def fetch_douyin_collection_via_browser(
    collect_id: str,
    cookie: str,
    proxy: str | None,
    limit: int,
    user_agent: str = "",
) -> list[dict]:
    """Fetch one private Douyin collection through its signed browser flow.

    Douyin currently requires a page-generated ``x-secsdk-web-signature`` for
    the private collection endpoints. This function lets the official page
    generate that short-lived value and consumes only the matching collection
    response; session cookies never leave the in-memory browser context.
    """

    target_id = str(collect_id or "").strip()
    target = max(1, int(limit or 1))
    cookies = cookie_header_to_playwright(cookie)
    if not target_id or not cookies:
        raise DouyinBrowserCollectionError(
            "抖音收藏夹浏览器请求缺少收藏夹 ID 或 Cookie。",
            error_code="douyin_cookie_missing",
        )

    items: list[dict] = []
    seen_aweme_ids: set[str] = set()
    target_title = ""
    target_declared_count = 0
    folder_list_seen = False
    target_response_seen = False
    target_has_more = True
    response_failed = False
    pending: set[asyncio.Task] = set()

    async with async_playwright() as playwright:
        launch_options: dict[str, Any] = {
            "headless": True,
            "channel": "chromium",
            "args": ["--no-sandbox", "--disable-dev-shm-usage"],
        }
        if proxy_settings := _playwright_proxy(proxy):
            launch_options["proxy"] = proxy_settings

        browser = await playwright.chromium.launch(**launch_options)
        try:
            context = await _open_context(browser, user_agent=user_agent)
            await context.add_cookies(cookies)
            page: Page = await context.new_page()

            async def capture(response) -> None:
                nonlocal folder_list_seen
                nonlocal response_failed
                nonlocal target_has_more
                nonlocal target_response_seen
                nonlocal target_title
                nonlocal target_declared_count

                parsed = urlsplit(response.url)
                path = parsed.path
                is_folder_list = path.endswith("/collects/list/")
                is_video_list = path.endswith("/collects/video/list/")
                if not is_folder_list and not is_video_list:
                    return

                if is_video_list:
                    response_id = (parse_qs(parsed.query).get("collects_id") or [
                        ""
                    ])[0]
                    if response_id != target_id:
                        return
                    target_response_seen = True

                if response.status >= 400:
                    response_failed = True
                    return
                try:
                    payload = await response.json()
                except Exception:
                    response_failed = True
                    return
                if not isinstance(payload, dict) or payload.get("status_code") not in (
                    None,
                    0,
                ):
                    response_failed = True
                    return

                if is_folder_list:
                    folder_list_seen = True
                    folders = payload.get("collects_list")
                    if not isinstance(folders, list):
                        return
                    for folder in folders:
                        if not isinstance(folder, dict):
                            continue
                        folder_id = str(
                            folder.get("collects_id")
                            or folder.get("collect_id")
                            or folder.get("id")
                            or ""
                        )
                        if folder_id != target_id:
                            continue
                        target_title = str(
                            folder.get("collects_name")
                            or folder.get("name")
                            or folder.get("title")
                            or ""
                        ).strip()
                        for key in (
                            "total",
                            "total_count",
                            "aweme_count",
                            "video_count",
                            "count",
                        ):
                            try:
                                target_declared_count = max(
                                    target_declared_count,
                                    int(folder.get(key) or 0),
                                )
                            except (TypeError, ValueError):
                                pass
                        _collection_trace(
                            "folder_matched",
                            collect_id=target_id,
                            title=target_title,
                            declared_count=target_declared_count,
                            available_fields=sorted(folder),
                        )
                        break
                    return

                aweme_list = payload.get("aweme_list")
                if not isinstance(aweme_list, list):
                    return
                update_pagination = _should_update_collection_pagination(
                    len(items),
                    len(aweme_list),
                )
                if update_pagination:
                    target_has_more = bool(payload.get("has_more"))
                before_count = len(items)
                for item in aweme_list:
                    if not isinstance(item, dict):
                        continue
                    aweme_id = str(item.get("aweme_id") or "").strip()
                    if aweme_id and aweme_id in seen_aweme_ids:
                        continue
                    if aweme_id:
                        seen_aweme_ids.add(aweme_id)
                    items.append(item)
                query = parse_qs(parsed.query)
                _collection_trace(
                    "video_page",
                    request_cursor=(query.get("cursor") or [""])[0],
                    response_cursor=payload.get("cursor"),
                    received=len(aweme_list),
                    added=len(items) - before_count,
                    total_items=len(items),
                    has_more=payload.get("has_more"),
                    pagination_updated=update_pagination,
                )

            def schedule_capture(response) -> None:
                path = urlsplit(response.url).path
                if not (
                    path.endswith("/collects/list/")
                    or path.endswith("/collects/video/list/")
                ):
                    return
                task = asyncio.create_task(capture(response))
                pending.add(task)
                task.add_done_callback(pending.discard)

            page.on("response", schedule_capture)
            navigation = await page.goto(
                "https://www.douyin.com/user/self?showTab=favorite_collection",
                # Douyin keeps enough parser-blocking resources open that
                # ``domcontentloaded`` can time out even after the document and
                # authenticated API hooks are available. ``commit`` confirms
                # the navigation response, then the explicit hydration wait
                # below owns readiness.
                wait_until="commit",
                timeout=90000,
            )
            if navigation is not None and navigation.status >= 400:
                raise DouyinBrowserCollectionError(
                    "抖音收藏夹页面访问失败，请检查网络或代理。",
                    error_code="douyin_navigation_failed",
                )

            # The self page is a hydrated SPA. Its navigation completes well
            # before the collection sub-tabs and request hooks are ready.
            await page.wait_for_timeout(20000)
            if await _douyin_login_prompt_visible(page):
                raise DouyinBrowserCollectionError(
                    "抖音登录状态已失效或需要验证，请打开对应采集身份的登录浏览器重新登录。",
                    error_code="douyin_auth_required",
                )
            tab = page.get_by_text("收藏夹", exact=True)
            if not await _click_first_visible(tab, 30):
                if await _douyin_login_prompt_visible(page):
                    raise DouyinBrowserCollectionError(
                        "抖音登录状态已失效或需要验证，请打开对应采集身份的登录浏览器重新登录。",
                        error_code="douyin_auth_required",
                    )
                raise DouyinBrowserCollectionError(
                    "抖音页面未显示收藏夹入口，页面结构可能已变化，请稍后重试。",
                    error_code="douyin_collection_tab_missing",
                )

            await _wait_for(lambda: bool(target_title), 12)
            for _ in range(12):
                if target_title:
                    break
                await page.mouse.wheel(0, 1800)
                await asyncio.sleep(0.75)
            if not target_title:
                message = (
                    "当前登录账号中未找到指定抖音收藏夹。"
                    if folder_list_seen
                    else "抖音收藏夹列表未能加载，请重新登录后重试。"
                )
                raise DouyinBrowserCollectionError(
                    message,
                    error_code=(
                        "douyin_collection_not_found"
                        if folder_list_seen
                        else "douyin_collection_list_unavailable"
                    ),
                )

            target_link = page.locator(f'[href*="{target_id}"]')
            clicked = await _click_first_visible(target_link, 2)
            if not clicked:
                clicked = await _click_first_visible(
                    page.get_by_text(target_title, exact=True),
                    10,
                )
            if not clicked:
                raise DouyinBrowserCollectionError(
                    "指定抖音收藏夹无法打开，页面结构可能已变化。",
                    error_code="douyin_collection_entry_unavailable",
                )

            # Folder cards may prefetch a one-item preview. Give the opened
            # folder time to replace that preview with its normal first page.
            await asyncio.sleep(4)
            await _wait_for(lambda: target_response_seen, 25)
            if not target_response_seen:
                raise DouyinBrowserCollectionError(
                    "打开收藏夹后未检测到作品接口响应。",
                    error_code="douyin_collection_response_missing",
                )
            if response_failed and not items:
                raise DouyinBrowserCollectionError(
                    "抖音收藏夹浏览器接口返回异常。",
                    error_code="douyin_collection_response_failed",
                )

            screenshot_path = os.environ.get(
                "FETCHSHELF_COLLECTION_TRACE_SCREENSHOT",
                "",
            ).strip()
            if screenshot_path:
                await page.screenshot(path=screenshot_path, full_page=False)
            _collection_trace(
                "folder_opened",
                initial_items=len(items),
                has_more=target_has_more,
                declared_count=target_declared_count,
            )

            unchanged_rounds = 0
            previous_count = len(items)
            scroll_round = 0
            while (
                len(items) < target
                and unchanged_rounds < 12
                and (
                    target_has_more
                    or target_declared_count > len(items)
                    or scroll_round < 3
                )
            ):
                scroll_round += 1
                surfaces = await _scroll_collection_surfaces(page)
                await page.mouse.wheel(0, 2400)
                await asyncio.sleep(1.5)
                if pending:
                    await asyncio.gather(
                        *tuple(pending),
                        return_exceptions=True,
                    )
                current_count = len(items)
                _collection_trace(
                    "scroll_round",
                    round=scroll_round,
                    before=previous_count,
                    after=current_count,
                    has_more=target_has_more,
                    declared_count=target_declared_count,
                    surfaces=surfaces,
                )
                if current_count == previous_count:
                    unchanged_rounds += 1
                else:
                    unchanged_rounds = 0
                    previous_count = current_count

            _collection_trace(
                "pagination_finished",
                total_items=len(items),
                has_more=target_has_more,
                declared_count=target_declared_count,
                scroll_rounds=scroll_round,
                unchanged_rounds=unchanged_rounds,
            )
            return items[:target]
        finally:
            if pending:
                await asyncio.gather(*tuple(pending), return_exceptions=True)
            await browser.close()


async def fetch_douyin_favorites_via_browser(
    cookie: str,
    proxy: str | None,
    limit: int,
) -> list[dict]:
    """Fetch the signed-in account's general favorite-work feed."""

    target = max(1, int(limit or 1))
    cookies = cookie_header_to_playwright(cookie)
    if not cookies:
        raise DouyinBrowserCollectionError(
            "Douyin favorites browser fallback requires cookies."
        )

    items: list[dict] = []
    seen_aweme_ids: set[str] = set()
    response_seen = False
    response_failed = False
    has_more = True
    pending: set[asyncio.Task] = set()

    async with async_playwright() as playwright:
        launch_options: dict[str, Any] = {
            "headless": True,
            "channel": "chromium",
            "args": ["--no-sandbox", "--disable-dev-shm-usage"],
        }
        if proxy_settings := _playwright_proxy(proxy):
            launch_options["proxy"] = proxy_settings

        browser = await playwright.chromium.launch(**launch_options)
        try:
            context = await _open_context(browser)
            await context.add_cookies(cookies)
            page: Page = await context.new_page()

            async def capture(response) -> None:
                nonlocal has_more
                nonlocal response_failed
                nonlocal response_seen

                if not urlsplit(response.url).path.endswith(
                    "/aweme/listcollection/"
                ):
                    return
                response_seen = True
                if response.status >= 400:
                    response_failed = True
                    return
                try:
                    payload = await response.json()
                except Exception:
                    response_failed = True
                    return
                if not isinstance(payload, dict) or payload.get("status_code") not in (
                    None,
                    0,
                ):
                    response_failed = True
                    return
                aweme_list = payload.get("aweme_list")
                if not isinstance(aweme_list, list):
                    return
                has_more = bool(payload.get("has_more"))
                for item in aweme_list:
                    if not isinstance(item, dict):
                        continue
                    aweme_id = str(item.get("aweme_id") or "").strip()
                    if aweme_id and aweme_id in seen_aweme_ids:
                        continue
                    if aweme_id:
                        seen_aweme_ids.add(aweme_id)
                    items.append(item)

            def schedule_capture(response) -> None:
                if not urlsplit(response.url).path.endswith(
                    "/aweme/listcollection/"
                ):
                    return
                task = asyncio.create_task(capture(response))
                pending.add(task)
                task.add_done_callback(pending.discard)

            page.on("response", schedule_capture)
            navigation = await page.goto(
                "https://www.douyin.com/user/self?showTab=favorite_collection",
                wait_until="commit",
                timeout=90000,
            )
            if navigation is not None and navigation.status >= 400:
                raise DouyinBrowserCollectionError(
                    "Douyin favorites page navigation failed."
                )

            await page.wait_for_timeout(20000)
            await _wait_for(lambda: response_seen, 30)
            if not response_seen:
                raise DouyinBrowserCollectionError(
                    "Douyin favorites response was not observed."
                )
            if response_failed and not items:
                raise DouyinBrowserCollectionError(
                    "Douyin favorites browser request failed."
                )

            unchanged_rounds = 0
            previous_count = len(items)
            while len(items) < target and has_more and unchanged_rounds < 8:
                await page.mouse.wheel(0, 3000)
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(1.25)
                current_count = len(items)
                if current_count == previous_count:
                    unchanged_rounds += 1
                else:
                    unchanged_rounds = 0
                    previous_count = current_count

            return items[:target]
        finally:
            if pending:
                await asyncio.gather(*tuple(pending), return_exceptions=True)
            await browser.close()
