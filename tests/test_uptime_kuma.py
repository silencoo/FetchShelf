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


def test_schedule_normalizes_uptime_kuma_url():
    payload = {
        "platform": "douyin",
        "hour": 1,
        "minute": 2,
        "uptime_kuma_url": "https://kuma/push/abc",
    }
    server = APIServer.__new__(APIServer)
    server._now_text = lambda: "2026-03-13 00:00:00"
    normalized = APIServer._normalize_schedule_payload(server, payload)
    assert normalized["uptime_kuma_url"] == "https://kuma/push/abc"


def test_uptime_kuma_status_down_when_failed_counts():
    task = {
        "status": "success",
        "result": {"data": {"failed": 1, "queued": 2}},
    }
    status, msg = APIServer._build_uptime_kuma_status(task, "Task", "douyin")
    assert status == "down"
    assert "failed" in msg
