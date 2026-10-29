from urllib.parse import parse_qs
from src.encrypt import DouYinParams
from src.encrypt.sm3 import sm3_hexdigest
from src.encrypt.websign import normalize_query, sign


def test_sm3_standard_abc_vector():
    assert sm3_hexdigest(b"abc") == "66c7f0f462eeedd9d1f2d46bdc10e4e24167c4875cf2f7a2297da02b8f4ba8e0"


def test_websign_preserves_encoded_values_and_single_uifid():
    query = "uifid=abc%2B123&text=a%20b&a_bogus=a%2F%3D"
    signed, signature = sign(query, "abc+123", timestamp=123)
    values = parse_qs(signed)
    assert values["uifid"] == ["abc+123"]
    assert values["text"] == ["a b"]
    assert values["a_bogus"] == ["a/="]
    assert values["timestamp"] == ["123"]
    assert values["x-secsdk-web-signature"] == [signature]
    assert signed.startswith(normalize_query(query))
    assert signature != sign(query.replace("a%20b", "different"), "abc+123", timestamp=123)[1]


def test_native_signer_preserves_ms_token_and_adds_protected_signature(monkeypatch):
    calls = []
    def fake(self, query, data, user_agent):
        calls.append((query, data, user_agent))
        return "a/="
    monkeypatch.setattr(DouYinParams, "_get_a_bogus", fake)
    query = {"uifid": "a+b", "msToken": "token=+/", "cursor": 0}
    original = query.copy()
    signed = DouYinParams().sign_url(
        url="https://www.douyin.com/aweme/v1/web/aweme/post/",
        query=query, user_agent="signed-agent",
    )
    values = parse_qs(signed)
    assert query == original
    assert values["msToken"] == ["token=+/"]
    assert values["uifid"] == ["a+b"]
    assert values["a_bogus"] == ["a/="]
    assert "x-secsdk-web-signature" in values
    assert calls[0][2] == "signed-agent"
    assert parse_qs(calls[0][0])["msToken"] == ["token=+/"]


def test_unprotected_endpoint_or_missing_uifid_has_no_websign(monkeypatch):
    monkeypatch.setattr(DouYinParams, "_get_a_bogus", lambda *args: "native")
    for url, query in [
        ("https://www.douyin.com/aweme/v1/web/user/profile/other/", {"uifid": "user"}),
        ("https://www.douyin.com/aweme/v1/web/aweme/post/", {"cursor": 0}),
    ]:
        result = parse_qs(DouYinParams().sign_url(url=url, query=query))
        assert result["a_bogus"] == ["native"]
        assert "x-secsdk-web-signature" not in result
