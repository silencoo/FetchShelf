"""Transient, identity-scoped TikTok HTTP session recovery."""


class TikTokVerificationRequired(RuntimeError):
    pass


class TikTokHTTPChallenge(RuntimeError):
    """Internal signal: interrupt ordinary retries before JSON parsing."""


def is_tiktok_challenge(text: str) -> bool:
    text = (text or "").lower()
    if not text.lstrip().startswith("<"):
        return False
    return any(marker in text for marker in (
        "_wafchallengeid", "waf-aiso/", 'id="captcha-verify-container"',
        "secsdk-captcha-drag-icon",
    ))


def apply_tiktok_session(params, session: dict) -> None:
    from .format import cookie_dict_to_str

    cookies = dict(session["cookies"])
    header = cookie_dict_to_str(cookies)
    params.cookie_dict_tiktok = cookies
    params.cookie_str_tiktok = header
    params.cookie_tiktok_state = bool(cookies)
    params.ms_token_tiktok = cookies.get("msToken", "")
    api_params = getattr(params, "api_params_tiktok", {})
    api_params.update(session.get("params") or {})
    api_params["msToken"] = params.ms_token_tiktok
    params.api_params_tiktok = api_params
    user_agent = session.get("user_agent")
    if user_agent:
        params.browser_info_tiktok["User-Agent"] = user_agent
    for name in ("headers_tiktok", "headers_download_tiktok", "headers_params_tiktok"):
        headers = getattr(params, name, None)
        if headers is not None:
            if user_agent:
                headers["User-Agent"] = user_agent
            if name != "headers_params_tiktok":
                headers["Cookie"] = header
