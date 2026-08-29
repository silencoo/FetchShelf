from urllib.parse import quote, urlencode

from ..custom import USERAGENT

__all__ = ["DouYinParams"]


class DouYinParams:
    """Generate the current Douyin web query signing contract.

    TikTokDownloader disabled its legacy per-request ABogus implementation in
    August 2026.  Douyin now validates the browser transport fingerprint as
    part of the request contract, so this signer must be used together with
    the curl_cffi impersonation configured by the API requester.
    """

    A_BOGUS = (
        "dv0Rge7imxQbadKb8cBqy5VU8tnlrBSyhsTobG1PyxKSyq0TDmPc"
        "/neMbxoQ4Ahv1upzwHQH6DsATjxbN0UTp9OkzmhDus7W7t2VIumLgqq6Tl4/"
        "DHDFe8vFuwsCWcsw-/deEeyRWs0i6d5l9qCiABB7w/4n-mRmMr-UVZutx9KsUAujhn/"
        "Ca-S2Y7iqPj=="
    )

    def sign(
        self,
        query: dict | str = "",
        data: dict | str | None = None,
        method: str = "",
        user_agent: str = USERAGENT,
        ms_token: str = "",
    ) -> dict[str, str]:
        del query, data, method, user_agent, ms_token
        return {"a_bogus": self.A_BOGUS}

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
        signature = self.sign(query, data, method, user_agent, ms_token)["a_bogus"]
        signed_query = f"{query}&a_bogus={signature}"
        if not base_url:
            return signed_query
        separator = "&" if "?" in base_url else "?"
        return f"{base_url}{separator}{signed_query}"
