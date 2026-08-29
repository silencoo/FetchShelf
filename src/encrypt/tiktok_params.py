from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode

from javascript import require

from ..custom import USERAGENT
from ..tools.check_node import is_node_available

__all__ = ["TikTokParams"]

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_JS_FILE = _REPO_ROOT / "static" / "js" / "tiktok-web-params.js"

_DEFAULT_ENV: dict[str, int] = {
    "envcode": 1,
    "ubcode": 0,
    "txr": 11,
    "tfr": 22,
    "ixr": 33,
    "ifr": 44,
}


class TikTokParams:
    """Generate TikTok Web X-Dynosaur, X-Gnarly and X-Bogus parameters."""

    def __init__(self) -> None:
        self._js = require(str(_JS_FILE.resolve())) if is_node_available() else None

    @property
    def available(self) -> bool:
        return self._js is not None

    def sign(
        self,
        query: dict | str = "",
        data: dict | str | None = None,
        method: str = "",
        user_agent: str = USERAGENT,
        ms_token: str = "",
    ) -> dict[str, str]:
        del data, method
        if self._js is None:
            return {"X-Dynosaur": "", "X-Gnarly": "", "X-Bogus": ""}
        if isinstance(query, dict):
            query = urlencode(query, safe="=", quote_via=quote)
        opts: dict[str, Any] = {
            "ua": user_agent,
            "msToken": ms_token,
            "env": _DEFAULT_ENV,
        }
        result = self._js.signUrl(query, opts)
        return {
            "X-Dynosaur": result["dynosaur"],
            "X-Gnarly": result["gnarly"],
            "X-Bogus": result["xbogus"],
        }

    def sign_url(
        self,
        base_url: str = "",
        query: dict | str = "",
        data: dict | str | None = None,
        method: str = "",
        user_agent: str = USERAGENT,
        ms_token: str = "",
    ) -> str:
        if isinstance(query, dict):
            query = urlencode(query, safe="=", quote_via=quote)
        params = self.sign(query, data, method, user_agent, ms_token)
        signed_query = "&".join(
            (
                query,
                f"X-Dynosaur={params['X-Dynosaur']}",
                f"msToken={quote(str(ms_token), safe='')}",
                f"X-Bogus={params['X-Bogus']}",
                f"X-Gnarly={params['X-Gnarly']}",
            )
        )
        if not base_url:
            return signed_query
        separator = "&" if "?" in base_url else "?"
        return f"{base_url}{separator}{signed_query}"
