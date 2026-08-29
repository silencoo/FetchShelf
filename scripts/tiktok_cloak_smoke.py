"""Exercise FetchShelf's TikTok signer with an ephemeral CloakBrowser session.

Anonymous cookie values stay in memory and are never printed or persisted.
"""

import argparse
import asyncio
import json
import re
from time import time
from types import SimpleNamespace
from urllib.parse import quote, urlencode

from curl_cffi.requests import Session

from src.custom import USERAGENT
from src.encrypt import ABogus, TikTokParams, XBogus, XGnarly
from src.interface.account_tiktok import AccountTikTok
from src.interface.template import API, APITikTok
from src.module import TikTokAPIBridge
from src.tools import create_client


class _Logger:
    def __init__(self) -> None:
        self.warnings: list[str] = []

    def info(self, *args, **kwargs) -> None:
        return None

    def warning(self, message, *args, **kwargs) -> None:
        self.warnings.append(str(message))

    def error(self, message, *args, **kwargs) -> None:
        self.warnings.append(str(message))


def _params(logger: _Logger, *, headless: bool) -> SimpleNamespace:
    return SimpleNamespace(
        logger=logger,
        cookie_dict_tiktok={},
        cookie_str_tiktok="",
        proxy_tiktok=None,
        browser_info_tiktok={
            "User-Agent": USERAGENT,
            "app_language": "en-US",
            "browser_language": "en-US",
            "language": "en-US",
            "priority_region": "US",
            "region": "US",
            "tz_name": "Asia/Tokyo",
            "webcast_language": "en-US",
        },
        tiktok_api_browser="chromium",
        tiktok_api_browser_engine="cloakbrowser",
        tiktok_api_headless=headless,
        tiktok_api_humanize=True,
        tiktok_api_human_preset="default",
        tiktok_api_sleep_after=5,
        tiktok_api_timeout_ms=60000,
        tiktok_api_page_size=6,
        max_pages=1,
        tiktok_api_reuse_session=False,
        tiktok_api_persistent_profile=False,
        tiktok_api_profile_dir="",
        tiktok_api_skip_on_risk=True,
        tiktok_api_risk_cooldown_seconds=0,
        tiktok_api_debug_capture_enabled=False,
        tiktok_api_debug_capture_slider=False,
        tiktok_api_debug_capture_dir="",
        ms_token_tiktok="",
    )


async def run(
    profile: str,
    *,
    headless: bool = True,
    sec_uid_override: str = "",
) -> dict[str, object]:
    profile = profile.strip().lstrip("@")
    profile_url = f"https://www.tiktok.com/@{profile}"
    logger = _Logger()
    runtime_params = _params(logger, headless=headless)
    bridge = TikTokAPIBridge(runtime_params)
    api = None
    try:
        api = await bridge._create_api(profile_url)
        if not api.sessions:
            raise RuntimeError("CloakBrowser did not create a TikTok session")
        browser_session = api.sessions[0]
        cookies = await api.get_session_cookies(browser_session)
        user_error = ""
        user_payload = {}
        if not sec_uid_override:
            try:
                user_payload = await api.user(username=profile).info()
            except Exception as error:
                user_error = f"{type(error).__name__}: {error}"
        user_info = user_payload.get("userInfo") or {}
        user = user_info.get("user") or {}
        sec_uid = str(sec_uid_override or user.get("secUid") or "")
        if not sec_uid:
            html = await browser_session.page.content()
            if match := re.search(r'"secUid":"([^"]+)"', html):
                sec_uid = match.group(1)
        user_agent = await browser_session.page.evaluate("() => navigator.userAgent")
        if not sec_uid:
            return {
                "browser_session": True,
                "anonymous_cookie_names": sorted(cookies),
                "ms_token_found": bool(cookies.get("msToken")),
                "user_info_found": False,
                "page_url": browser_session.page.url,
                "page_title": await browser_session.page.title(),
                "user_error": user_error,
                "api_attempted": False,
                "warnings": logger.warnings[-3:],
            }

        params = APITikTok.params.copy()
        params.update(browser_session.params or {})
        params.update(
            {
                "WebIdLastTime": int(time()),
                "count": "6",
                "cursor": "0",
                "from_page": "user",
                "msToken": cookies.get("msToken", ""),
                "needPinnedItemIds": "true",
                "post_item_list_request_type": "0",
                "secUid": sec_uid,
            }
        )
        ms_token = str(params.pop("msToken", ""))
        query = urlencode(params, safe="=", quote_via=quote)
        signed_query = TikTokParams().sign_url(
            query=query,
            user_agent=user_agent,
            ms_token=ms_token,
        )
        api_url = f"https://www.tiktok.com/api/post/item_list/?{signed_query}"
        browser_result = await browser_session.page.evaluate(
            """
            async (url) => {
                const response = await fetch(url, {
                    credentials: "include",
                    headers: {accept: "application/json, text/plain, */*"},
                });
                const body = await response.text();
                return {status: response.status, body};
            }
            """,
            api_url,
        )
        try:
            browser_payload = json.loads(browser_result["body"])
        except (json.JSONDecodeError, TypeError, ValueError):
            browser_payload = None
        with Session(impersonate="chrome146", cookies=cookies) as client:
            response = client.get(
                api_url,
                headers={
                    "Accept": "application/json, text/plain, */*",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Referer": profile_url,
                    "User-Agent": user_agent,
                },
                timeout=30,
            )
        try:
            payload = response.json()
        except (json.JSONDecodeError, ValueError):
            payload = None

        cookie_string = "; ".join(f"{key}={value}" for key, value in cookies.items())
        runtime_params.headers = {"User-Agent": user_agent}
        runtime_params.headers_tiktok = {
            "Accept": "application/json, text/plain, */*",
            "Referer": profile_url,
            "User-Agent": user_agent,
            "Cookie": cookie_string,
        }
        runtime_params.api_params = {}
        runtime_params.api_params_tiktok = {
            **(browser_session.params or {}),
            "msToken": ms_token,
        }
        runtime_params.ab = ABogus()
        runtime_params.xb = XBogus()
        runtime_params.xg = XGnarly()
        runtime_params.tiktok_params = TikTokParams()
        runtime_params.console = None
        runtime_params.max_retry = 0
        runtime_params.timeout = 30
        runtime_params.request_delay = 0
        runtime_params.proxy = None
        runtime_params.client = create_client(timeout=30)
        runtime_params.client_tiktok = create_client(timeout=30)
        runtime_params._external_signers = set()
        API.init_progress_object(server_mode=True)
        try:
            app_result = await AccountTikTok(
                runtime_params,
                cookie=cookie_string,
                sec_user_id=sec_uid,
                pages=1,
                count=6,
            ).run(single_page=True)
            app_items = app_result
        finally:
            await runtime_params.client.aclose()
            await runtime_params.client_tiktok.aclose()
        return {
            "browser_session": True,
            "anonymous_cookie_names": sorted(cookies),
            "ms_token_found": bool(cookies.get("msToken")),
            "user_info_found": True,
            "sec_uid_found": True,
            "api_attempted": True,
            "browser_api_status": browser_result["status"],
            "browser_api_bytes": len(browser_result["body"].encode("utf-8")),
            "browser_api_json": isinstance(browser_payload, dict),
            "browser_item_count": len(browser_payload.get("itemList") or [])
            if isinstance(browser_payload, dict)
            else 0,
            "api_status": response.status_code,
            "api_bytes": len(response.content),
            "api_json": isinstance(payload, dict),
            "api_status_code": payload.get("statusCode") if isinstance(payload, dict) else None,
            "item_count": len(payload.get("itemList") or []) if isinstance(payload, dict) else 0,
            "has_more": payload.get("hasMore") if isinstance(payload, dict) else None,
            "fetchshelf_item_count": len(app_items),
            "warnings": logger.warnings[-3:],
        }
    finally:
        if api is not None:
            await bridge._close_api(api)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="tiktok")
    parser.add_argument("--sec-uid", default="")
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            asyncio.run(
                run(
                    args.profile,
                    headless=not args.headed,
                    sec_uid_override=args.sec_uid,
                )
            ),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
