from json.decoder import JSONDecodeError
from ssl import SSLError
from typing import TYPE_CHECKING, Union

from httpx import HTTPStatusError, NetworkError, RequestError, TimeoutException

from ..translation import _

if TYPE_CHECKING:
    from ..record import BaseLogger, LoggerManager

__all__ = [
    "capture_error_params",
    "capture_error_request",
]


def _get_invalid_json_response(error, limit=4096):
    if not isinstance(error, JSONDecodeError):
        return None
    response = (error.doc or "").strip()
    if not response:
        return "<empty response>"
    if len(response) <= limit:
        return response
    return (
        f"{response[:limit]}\n"
        f"... [truncated, total {len(response)} chars]"
    )


def capture_error_params(function):
    async def inner(logger: Union["BaseLogger", "LoggerManager"], *args, **kwargs):
        try:
            return await function(logger, *args, **kwargs)
        except (JSONDecodeError, UnicodeDecodeError) as error:
            logger.error(_("响应内容不是有效的 JSON 数据"))
            if isinstance(error, JSONDecodeError):
                logger.error(
                    _(
                        "JSON 解析失败位置：第 {line} 行，第 {column} 列（字符偏移 {pos}）"
                    ).format(
                        line=error.lineno,
                        column=error.colno,
                        pos=error.pos,
                    )
                )
            if response := _get_invalid_json_response(error):
                logger.error(
                    _("原始响应内容如下：\n{response}").format(response=response)
                )
        except HTTPStatusError as e:
            logger.error(_("响应码异常：{error}").format(error=e))
        except NetworkError as e:
            logger.error(_("网络异常：{error}").format(error=e))
        except TimeoutException as e:
            logger.error(_("请求超时：{error}").format(error=e))
        except (
            RequestError,
            SSLError,
        ) as e:
            logger.error(_("网络异常：{error}").format(error=e))
        return None

    return inner


def capture_error_request(function):
    async def inner(self, *args, **kwargs):
        try:
            return await function(self, *args, **kwargs)
        except (JSONDecodeError, UnicodeDecodeError) as error:
            self.log.error(_("响应内容不是有效的 JSON 数据，请尝试更新 Cookie！"))
            if isinstance(error, JSONDecodeError):
                self.log.error(
                    _(
                        "JSON 解析失败位置：第 {line} 行，第 {column} 列（字符偏移 {pos}）"
                    ).format(
                        line=error.lineno,
                        column=error.colno,
                        pos=error.pos,
                    )
                )
            if response := _get_invalid_json_response(error):
                self.log.error(
                    _("原始响应内容如下：\n{response}").format(response=response)
                )
        except HTTPStatusError as e:
            self.log.error(_("响应码异常：{error}").format(error=e))
        except NetworkError as e:
            self.log.error(_("网络异常：{error}").format(error=e))
        except TimeoutException as e:
            self.log.error(_("请求超时：{error}").format(error=e))
        except (
            RequestError,
            SSLError,
        ) as e:
            self.log.error(_("网络异常：{error}").format(error=e))
        return None

    return inner
