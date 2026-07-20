from re import compile
from typing import TYPE_CHECKING

from ..custom import wait
from ..tools import DownloaderError, Retry, capture_error_request, create_client

if TYPE_CHECKING:
    from httpx import AsyncClient

    from ..config import Parameter

__all__ = ["Requester"]


class Requester:
    URL = compile(r"(https?://[^\s\"<>\\^`{|}，。；！？、【】《》]+)")

    def __init__(
        self,
        params: "Parameter",
        client: "AsyncClient",
        headers: dict[str, str],
    ):
        self.client = client
        self.headers = headers
        self.log = params.logger
        self.max_retry = params.max_retry
        self.timeout = params.timeout
        self.request_delay = getattr(params, "request_delay", None)
        self.configured_proxy = (
            getattr(params, "proxy_tiktok", None)
            if client is getattr(params, "client_tiktok", None)
            else getattr(params, "proxy", None)
        )

    async def run(
        self,
        text: str,
        proxy: str = None,
    ) -> str:
        urls = self.URL.finditer(text)
        if not urls:
            return ""
        result = []
        for i in urls:
            result.append(
                await self.request_url(
                    u := i.group(),
                    proxy=proxy,
                )
                or u
            )
            await wait(self.request_delay)
        return " ".join(i for i in result if i)

    @Retry.retry
    @capture_error_request
    async def request_url(
        self,
        url: str,
        content="url",
        proxy: str = None,
    ):
        self.log.info(f"URL: {url}", False)
        match bool(proxy):
            # case True, True:
            #     response = self.request_url_head_proxy(
            #         url,
            #         proxy,
            #     )
            # case True, False:
            #     response = await self.request_url_head(url)
            case True:
                response = await self.request_url_get_proxy(
                    url,
                    proxy,
                )
            case False:
                response = await self.request_url_get(url)
            case _:
                raise DownloaderError
        self.log.info(f"Response URL: {response.url}", False)
        self.log.info(f"Response Code: {response.status_code}", False)
        # 记录请求体数据会导致日志文件体积过大，仅在必要时记录
        # self.log.info(f"Response Content: {response.content}", False)
        self.log.info(f"Response Headers: {dict(response.headers)}", False)
        match content:
            case "text":
                return response.text
            case "content":
                return response.content
            case "json":
                return response.json()
            case "headers":
                return response.headers
            case "url":
                return str(response.url)
            case _:
                raise DownloaderError

    async def request_url_head(
        self,
        url: str,
    ):
        return await self.client.head(
            url,
            headers=self.headers,
        )

    async def request_url_head_proxy(
        self,
        url: str,
        proxy: str,
    ):
        client = self.client
        owned_client = None
        if proxy != self.configured_proxy:
            owned_client = create_client(timeout=self.timeout, proxy=proxy)
            client = owned_client
        try:
            return await client.head(url, headers=self.headers)
        finally:
            if owned_client is not None:
                await owned_client.aclose()

    async def request_url_get(
        self,
        url: str,
    ):
        response = await self.client.get(
            url,
            headers=self.headers,
        )
        response.raise_for_status()
        return response

    async def request_url_get_proxy(
        self,
        url: str,
        proxy: str,
    ):
        client = self.client
        owned_client = None
        if proxy != self.configured_proxy:
            owned_client = create_client(timeout=self.timeout, proxy=proxy)
            client = owned_client
        try:
            response = await client.get(url, headers=self.headers)
            response.raise_for_status()
            return response
        finally:
            if owned_client is not None:
                await owned_client.aclose()
