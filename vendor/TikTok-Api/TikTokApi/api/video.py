from __future__ import annotations
from ..helpers import extract_video_id_from_url
from typing import TYPE_CHECKING, ClassVar, AsyncIterator, Optional
from datetime import datetime
from ..exceptions import InvalidResponseException
import base64
import json
from typing import Union, AsyncIterator

if TYPE_CHECKING:
    from ..tiktok import TikTokApi
    from .user import User
    from .sound import Sound
    from .hashtag import Hashtag
    from .comment import Comment


class Video:
    """
    A TikTok Video class

    Example Usage
    ```py
    video = api.video(id='7041997751718137094')
    ```
    """

    parent: ClassVar[TikTokApi]

    id: Optional[str]
    """TikTok's ID of the Video"""
    url: Optional[str]
    """The URL of the Video"""
    create_time: Optional[datetime]
    """The creation time of the Video"""
    stats: Optional[dict]
    """TikTok's stats of the Video"""
    author: Optional[User]
    """The User who created the Video"""
    sound: Optional[Sound]
    """The Sound that is associated with the Video"""
    hashtags: Optional[list[Hashtag]]
    """A List of Hashtags on the Video"""
    as_dict: dict
    """The raw data associated with this Video."""

    def __init__(
        self,
        id: Optional[str] = None,
        url: Optional[str] = None,
        data: Optional[dict] = None,
        **kwargs,
    ):
        """
        You must provide the id or a valid url, else this will fail.
        """
        self.id = id
        self.url = url
        if data is not None:
            self.as_dict = data
            self.__extract_from_data()
        elif url is not None:
            try:
                self.id = extract_video_id_from_url(url)
            except TypeError:
                self.id = None

        if getattr(self, "id", None) is None and url is None:
            raise TypeError("You must provide id or url parameter.")

    @staticmethod
    def _extract_structured_video_info(html: str, video_id: Optional[str]) -> dict:
        start = html.find('<script id="SIGI_STATE" type="application/json">')
        if start != -1:
            start += len('<script id="SIGI_STATE" type="application/json">')
            end = html.find("</script>", start)

            if end == -1:
                raise InvalidResponseException(
                    html,
                    "TikTok returned an invalid response.",
                )

            data = json.loads(html[start:end])
            if not video_id:
                item_module = data.get("ItemModule") or {}
                if len(item_module) == 1:
                    return next(iter(item_module.values()))
                raise InvalidResponseException(
                    html,
                    "TikTok returned an invalid response structure.",
                )
            video_info = (data.get("ItemModule") or {}).get(video_id)
            if video_info is None:
                raise InvalidResponseException(
                    html,
                    "TikTok returned an invalid response structure.",
                )
            return video_info

        start = html.find(
            '<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__" type="application/json">'
        )
        if start == -1:
            raise InvalidResponseException(
                html,
                "TikTok returned an invalid response.",
            )

        start += len(
            '<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__" type="application/json">'
        )
        end = html.find("</script>", start)

        if end == -1:
            raise InvalidResponseException(
                html,
                "TikTok returned an invalid response.",
            )

        data = json.loads(html[start:end])
        default_scope = data.get("__DEFAULT_SCOPE__", {})
        video_detail = default_scope.get("webapp.video-detail", {})
        if video_detail.get("statusCode", 0) != 0:
            raise InvalidResponseException(
                html,
                "TikTok returned an invalid response structure.",
            )
        video_info = video_detail.get("itemInfo", {}).get("itemStruct")
        if video_info is None:
            raise InvalidResponseException(
                html,
                "TikTok returned an invalid response structure.",
            )
        return video_info

    @staticmethod
    def _is_media_payload(payload: dict) -> bool:
        content_type = str(payload.get("contentType", "") or "").lower()
        if any(token in content_type for token in ("text/", "json", "html")):
            return False
        try:
            size = int(payload.get("size") or 0)
        except (TypeError, ValueError):
            size = 0
        return (
            bool(payload.get("ok"))
            and size > 0
            and (
                "video" in content_type
                or "octet-stream" in content_type
                or not content_type
            )
        )

    @staticmethod
    def _decode_media_body(payload: dict) -> bytes:
        body_base64 = str(payload.get("bodyBase64", "") or "")
        if not body_base64:
            return b""
        return base64.b64decode(body_base64)

    @staticmethod
    def _content_range_total(payload: dict) -> int | None:
        content_range = str(payload.get("contentRange", "") or "").strip()
        if "/" not in content_range:
            return None
        total = content_range.rsplit("/", 1)[1].strip()
        if not total or total == "*":
            return None
        try:
            return int(total)
        except ValueError:
            return None

    async def info(self, **kwargs) -> dict:
        """
        Returns a dictionary of all data associated with a TikTok Video.

        Note: This is slow since it requires an HTTP request, avoid using this if possible.

        Returns:
            dict: A dictionary of all data associated with a TikTok Video.

        Raises:
            InvalidResponseException: If TikTok returns an invalid response, or one we don't understand.

        Example Usage:
            .. code-block:: python

                url = "https://www.tiktok.com/@davidteathercodes/video/7106686413101468970"
                video_info = await api.video(url=url).info()
        """
        i, session = self.parent._get_session(**kwargs)
        if self.url is None:
            raise TypeError("To call video.info() you need to set the video's url.")

        page_payload = await self.parent.get_session_page_payload(
            self.url,
            session_index=i,
        )
        status_code = page_payload.get("status")
        html = page_payload.get("content") or ""
        final_url = page_payload.get("url") or self.url

        if status_code and int(status_code) >= 400:
            raise InvalidResponseException(
                html,
                "TikTok returned an invalid response.",
                error_code=status_code,
            )

        if self.id is None:
            self.id = extract_video_id_from_url(final_url)

        video_info = self._extract_structured_video_info(html, self.id)

        self.as_dict = video_info
        self.__extract_from_data()
        return video_info

    async def bytes(
        self, stream: bool = False, **kwargs
    ) -> Union[bytes, AsyncIterator[bytes]]:
        """
        Returns the bytes of a TikTok Video.

        TODO:
            Not implemented yet.

        Example Usage:
            .. code-block:: python

                video_bytes = await api.video(id='7041997751718137094').bytes()

                # Saving The Video
                with open('saved_video.mp4', 'wb') as output:
                    output.write(video_bytes)

                # Streaming (if stream=True)
                async for chunk in api.video(id='7041997751718137094').bytes(stream=True):
                    # Process or upload chunk
        """
        i, session = self.parent._get_session(**kwargs)
        video_data = self.as_dict.get("video", {})

        candidate_urls = []
        seen = set()

        def add_candidate(url):
            if url and url not in seen:
                seen.add(url)
                candidate_urls.append(url)

        def score_url(url: str) -> tuple[int, int, int]:
            url_lower = str(url or "").lower()
            return (
                int("webapp-sg.tiktok.com" in url_lower),
                int("/mp4/main.mp4" in url_lower),
                int("aweme/v1/play" not in url_lower),
            )

        add_candidate(video_data.get("playAddr"))

        play_addr_struct = video_data.get("PlayAddrStruct") or {}
        for url in play_addr_struct.get("UrlList") or []:
            add_candidate(url)

        for entry in video_data.get("bitrateInfo") or []:
            play_addr = entry.get("PlayAddr") or {}
            for url in play_addr.get("UrlList") or []:
                add_candidate(url)

        candidate_urls.sort(key=score_url, reverse=True)

        if not candidate_urls:
            raise InvalidResponseException(
                self.as_dict,
                "TikTok video payload does not contain a usable media URL.",
            )

        cookies = await self.parent.get_session_cookies(session)

        h = dict(session.headers or {})
        h["range"] = "bytes=0-"
        h["accept-encoding"] = "identity;q=1, *;q=0"
        h["referer"] = "https://www.tiktok.com/"
        media_debug = kwargs.get("media_debug")
        browser_chunk_size = max(int(kwargs.get("browser_chunk_size", 512 * 1024)), 1)
        stream_chunk_size = max(int(kwargs.get("stream_chunk_size", 64 * 1024)), 1)

        def write_media_debug(name: str, payload) -> None:
            if not media_debug:
                return
            media_debug.mkdir(parents=True, exist_ok=True)
            target = media_debug / name
            if isinstance(payload, (dict, list)):
                target.write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            else:
                target.write_text(str(payload), encoding="utf-8")

        def iter_chunks(data: bytes):
            for start in range(0, len(data), stream_chunk_size):
                yield data[start : start + stream_chunk_size]

        async def fetch_browser_payload(
            candidate_url: str,
            index: int,
            *,
            range_header: str | None = None,
            debug_prefix: str = "browser",
        ) -> dict:
            request_headers = dict(h)
            if range_header is not None:
                request_headers["range"] = range_header
            payload = await self.parent.fetch_binary(
                candidate_url,
                headers=request_headers,
                session_index=i,
            )
            write_media_debug(
                f"{debug_prefix}_{index:02d}.json",
                {
                    **payload,
                    "request_headers": request_headers,
                },
            )
            return payload

        async def capture_browser_payload(candidate_url: str, index: int) -> dict:
            payload = await self.parent.capture_media_response(
                candidate_url,
                headers=h,
                session_index=i,
            )
            write_media_debug(
                f"capture_{index:02d}.json",
                {
                    **payload,
                    "request_headers": h,
                },
            )
            return payload

        write_media_debug(
            "candidate_urls.json",
            {
                "video_id": self.id,
                "candidate_urls": candidate_urls,
                "headers": h,
            },
        )

        if stream:

            async def stream_bytes():
                last_error = None
                for index, candidate_url in enumerate(candidate_urls, start=1):
                    started = False
                    offset = 0
                    try:
                        while True:
                            range_header = (
                                f"bytes={offset}-{offset + browser_chunk_size - 1}"
                            )
                            payload = await fetch_browser_payload(
                                candidate_url,
                                index,
                                range_header=range_header,
                                debug_prefix=f"browser_stream_{offset:012d}",
                            )
                            if not self._is_media_payload(payload):
                                raise InvalidResponseException(
                                    payload,
                                    "TikTok returned an invalid media response.",
                                )
                            chunk = self._decode_media_body(payload)
                            if not chunk:
                                raise InvalidResponseException(
                                    payload,
                                    "TikTok returned an empty media response.",
                                )
                            started = True
                            for output_chunk in iter_chunks(chunk):
                                yield output_chunk

                            if int(payload.get("status") or 0) != 206:
                                return
                            offset += len(chunk)
                            total_size = self._content_range_total(payload)
                            if total_size is not None and offset >= total_size:
                                return
                            if len(chunk) < browser_chunk_size:
                                return
                    except Exception as error:
                        if started:
                            raise InvalidResponseException(
                                repr(error),
                                "TikTok video stream interrupted after download started.",
                            ) from error
                        last_error = error

                    try:
                        capture_payload = await capture_browser_payload(
                            candidate_url, index
                        )
                        if not self._is_media_payload(capture_payload):
                            raise InvalidResponseException(
                                capture_payload,
                                "TikTok returned an invalid media response.",
                            )
                        body = self._decode_media_body(capture_payload)
                        if not body:
                            raise InvalidResponseException(
                                capture_payload,
                                "TikTok returned an empty media response.",
                            )
                        for output_chunk in iter_chunks(body):
                            yield output_chunk
                        return
                    except Exception as error:
                        last_error = error

                raise InvalidResponseException(
                    repr(last_error) if last_error else candidate_urls,
                    "TikTok returned an invalid response.",
                )

            return stream_bytes()
        else:
            last_error = None
            for index, candidate_url in enumerate(candidate_urls, start=1):
                try:
                    browser_payload = await fetch_browser_payload(candidate_url, index)
                    if self._is_media_payload(browser_payload):
                        body = self._decode_media_body(browser_payload)
                        if body:
                            return body
                except Exception as error:
                    last_error = error

                try:
                    capture_payload = await capture_browser_payload(
                        candidate_url, index
                    )
                    if self._is_media_payload(capture_payload):
                        body = self._decode_media_body(capture_payload)
                        if body:
                            return body
                except Exception as error:
                    last_error = error

            raise InvalidResponseException(
                repr(last_error) if last_error else candidate_urls,
                "TikTok returned an invalid response.",
            )

    def __extract_from_data(self) -> None:
        data = self.as_dict
        self.id = data["id"]

        timestamp = data.get("createTime", None)
        if timestamp is not None:
            try:
                timestamp = int(timestamp)
            except ValueError:
                pass

        self.create_time = datetime.fromtimestamp(timestamp or 0)
        self.stats = data.get("statsV2") or data.get("stats")

        author = data.get("author")
        if isinstance(author, str):
            self.author = self.parent.user(username=author)
        else:
            self.author = self.parent.user(data=author or {})  # type: ignore[arg-type]
        self.sound = self.parent.sound(data=data)  # type: ignore[arg-type]

        self.hashtags = [
            self.parent.hashtag(data=hashtag) for hashtag in data.get("challenges", [])
        ]

        if getattr(self, "id", None) is None:
            Video.parent.logger.error(
                f"Failed to create Video with data: {data}\nwhich has keys {data.keys()}"
            )

    async def comments(self, count=20, cursor=0, **kwargs) -> AsyncIterator[Comment]:
        """
        Returns the comments of a TikTok Video.

        Parameters:
            count (int): The amount of comments you want returned.
            cursor (int): The the offset of comments from 0 you want to get.

        Returns:
            async iterator/generator: Yields TikTokApi.comment objects.

        Example Usage
        .. code-block:: python

            async for comment in api.video(id='7041997751718137094').comments():
                # do something
        ```
        """
        found = 0
        while found < count:
            params = {
                "aweme_id": self.id,
                "count": 20,
                "cursor": cursor,
            }

            resp = await self.parent.make_request(
                url="https://www.tiktok.com/api/comment/list/",
                params=params,
                headers=kwargs.get("headers") or {},
                session_index=kwargs.get("session_index"),
            )

            if resp is None:
                raise InvalidResponseException(
                    resp, "TikTok returned an invalid response."
                )

            for video in resp.get("comments", []):
                yield self.parent.comment(data=video)
                found += 1

            if not resp.get("has_more", False):
                return

            cursor = resp.get("cursor")

    async def related_videos(
        self, count: int = 30, cursor: int = 0, **kwargs
    ) -> AsyncIterator[Video]:
        """
        Returns related videos of a TikTok Video.

        Parameters:
            count (int): The amount of comments you want returned.
            cursor (int): The the offset of comments from 0 you want to get.

        Returns:
            async iterator/generator: Yields TikTokApi.video objects.

        Example Usage
        .. code-block:: python

            async for related_videos in api.video(id='7041997751718137094').related_videos():
                # do something
        ```
        """
        found = 0
        while found < count:
            params = {
                "itemID": self.id,
                "count": 16,
            }

            resp = await self.parent.make_request(
                url="https://www.tiktok.com/api/related/item_list/",
                params=params,
                headers=kwargs.get("headers") or {},
                session_index=kwargs.get("session_index"),
            )

            if resp is None:
                raise InvalidResponseException(
                    resp, "TikTok returned an invalid response."
                )

            for video in resp.get("itemList", []):
                yield self.parent.video(data=video)
                found += 1

    def __repr__(self):
        return self.__str__()

    def __str__(self):
        return f"TikTokApi.video(id='{getattr(self, 'id', None)}')"
