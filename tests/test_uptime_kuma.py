from urllib.parse import parse_qs, urlparse

from src.application.main_server import APIServer


def test_build_uptime_kuma_url_appends_status_and_msg():
    base = "https://kuma.example/push/abc?foo=bar"
    url = APIServer._build_uptime_kuma_url(base, "up", "hello world")
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    assert parsed.scheme == "https"
    assert parsed.netloc == "kuma.example"
    assert qs["foo"] == ["bar"]
    assert qs["status"] == ["up"]
    assert qs["msg"] == ["hello world"]
