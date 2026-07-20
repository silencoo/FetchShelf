from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.application.main_server import APIServer
from src.collector import (
    AESGCMSecretCodec,
    CollectorPlatform,
    CollectorStore,
    IdentityLeaseManager,
)


def _collector_test_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DOUK_API_TOKEN", "collector-test-token")
    server = APIServer.__new__(APIServer)
    server.server = FastAPI()
    server.collector_store = CollectorStore(
        tmp_path / "collector.sqlite3",
        codec=AESGCMSecretCodec(b"k" * 32),
    )
    server.collector_leases = IdentityLeaseManager()
    server.collector_vault_error = ""
    server.ui_schedules = {}
    server.ui_tasks = {}
    server.parameter = SimpleNamespace(
        timeout=10,
        headers={"User-Agent": "test"},
        headers_tiktok={"User-Agent": "test"},
    )
    server.setup_routes()
    return server, TestClient(server.server)


def test_collector_identity_api_never_returns_credentials(tmp_path, monkeypatch):
    server, client = _collector_test_client(tmp_path, monkeypatch)
    headers = {"token": "collector-test-token"}
    created = client.post(
        "/ui/api/collector-identities",
        headers=headers,
        json={
            "name": "TikTok US 01",
            "platform": "tiktok",
            "request_delay": 8,
            "max_concurrency": 1,
        },
    )
    assert created.status_code == 200, created.text
    identity_id = created.json()["identity"]["identity_id"]

    credentials = client.put(
        f"/ui/api/collector-identities/{identity_id}/credentials",
        headers=headers,
        json={
            "cookie": "sessionid=top-secret",
            "proxy": "socks5://user:pass@proxy.test:1080",
            "device_id": "device-secret",
        },
    )
    assert credentials.status_code == 200, credentials.text
    serialized = credentials.text
    assert "top-secret" not in serialized
    assert "user:pass" not in serialized
    assert "device-secret" not in serialized

    malformed = client.put(
        f"/ui/api/collector-identities/{identity_id}/credentials",
        headers=headers,
        json=[
            "sessionid=malformed-secret",
            "socks5://user:password@proxy.test:1080",
        ],
    )
    assert malformed.status_code == 422
    assert "malformed-secret" not in malformed.text
    assert "user:password" not in malformed.text

    listed = client.get("/ui/api/collector-identities", headers=headers)
    assert listed.status_code == 200
    public = listed.json()["items"][0]
    assert public["cookie_configured"] is True
    assert public["proxy_configured"] is True
    assert public["device_id_configured"] is True
    assert "cookie" not in public
    assert "proxy" not in public
    assert "device_id" not in public
    server.collector_store.close()


def test_collector_binding_and_route_preview(tmp_path, monkeypatch):
    server, client = _collector_test_client(tmp_path, monkeypatch)
    headers = {"token": "collector-test-token"}
    identities = []
    for name in ("A", "B"):
        response = client.post(
            "/ui/api/collector-identities",
            headers=headers,
            json={"name": name, "platform": "douyin"},
        )
        identity_id = response.json()["identity"]["identity_id"]
        identities.append(identity_id)
        assert client.put(
            f"/ui/api/collector-identities/{identity_id}/credentials",
            headers=headers,
            json={"cookie": f"sessionid={name}"},
        ).status_code == 200

    binding = client.put(
        "/ui/api/collector-assignments",
        headers=headers,
        json={
            "assignments": [
                {
                    "platform": "douyin",
                    "target_type": "account",
                    "target_key": "target-one",
                    "identity_id": identities[1],
                    "source": "explicit",
                }
            ]
        },
    )
    assert binding.status_code == 200, binding.text

    preview = client.post(
        "/ui/api/collector-policies/preview",
        headers=headers,
        json={
            "platform": "douyin",
            "target_type": "account",
            "strategy": "sticky_balanced",
            "targets": [
                {"target_key": "target-one"},
                {"target_key": "target-two"},
            ],
        },
    )
    assert preview.status_code == 200, preview.text
    routes = {item["target_key"]: item for item in preview.json()["assignments"]}
    assert routes["target-one"]["identity_id"] == identities[1]
    assert routes["target-one"]["reason"] == "fixed_binding"
    assert routes["target-two"]["identity_id"] in identities
    server.collector_store.close()


def test_rejected_identity_delete_restores_runtime_lease(tmp_path, monkeypatch):
    server, client = _collector_test_client(tmp_path, monkeypatch)
    headers = {"token": "collector-test-token"}
    created = client.post(
        "/ui/api/collector-identities",
        headers=headers,
        json={"name": "Bound", "platform": "douyin"},
    )
    identity_id = created.json()["identity"]["identity_id"]
    assert client.put(
        "/ui/api/collector-assignments",
        headers=headers,
        json={
            "assignments": [
                {
                    "platform": "douyin",
                    "target_type": "account",
                    "target_key": "target-bound",
                    "identity_id": identity_id,
                }
            ]
        },
    ).status_code == 200

    rejected = client.delete(
        f"/ui/api/collector-identities/{identity_id}",
        headers=headers,
    )
    assert rejected.status_code == 409
    # Creating a lease handle is a synchronous proof that the rejected delete
    # did not leave the still-persisted identity unconfigured.
    server.collector_leases.lease(identity_id)
    server.collector_store.close()


def test_account_binding_and_preview_use_canonical_url_without_mutating_sticky_state(
    tmp_path,
    monkeypatch,
):
    server, client = _collector_test_client(tmp_path, monkeypatch)
    headers = {"token": "collector-test-token"}
    identities = []
    for name in ("A", "B"):
        created = client.post(
            "/ui/api/collector-identities",
            headers=headers,
            json={"name": name, "platform": "douyin"},
        )
        identity_id = created.json()["identity"]["identity_id"]
        identities.append(identity_id)
        client.put(
            f"/ui/api/collector-identities/{identity_id}/credentials",
            headers=headers,
            json={"cookie": f"sessionid={name}"},
        )

    canonical = "https://www.douyin.com/user/demo"
    noisy = f"{canonical}/?from=share#profile"
    saved = client.put(
        "/ui/api/collector-assignments",
        headers=headers,
        json={
            "assignments": [
                {
                    "platform": "douyin",
                    "target_type": "account",
                    "target_key": noisy,
                    "identity_id": identities[1],
                }
            ]
        },
    )
    assert saved.status_code == 200
    assert saved.json()["assignments"][0]["target_key"] == canonical

    preview = client.post(
        "/ui/api/collector-policies/preview",
        headers=headers,
        json={
            "platform": "douyin",
            "target_type": "account",
            "targets": [{"target_key": noisy}],
        },
    )
    assert preview.status_code == 200, preview.text
    route = preview.json()["assignments"][0]
    assert route["target_key"] == canonical
    assert route["identity_id"] == identities[1]
    assert route["reason"] == "fixed_binding"

    unbound = "https://www.douyin.com/user/unbound"
    automatic = client.post(
        "/ui/api/collector-policies/preview",
        headers=headers,
        json={
            "platform": "douyin",
            "target_type": "account",
            "targets": [{"target_key": f"{unbound}?preview=1"}],
        },
    )
    assert automatic.status_code == 200, automatic.text
    assert (
        server.collector_store.get_assignment(
            CollectorPlatform.DOUYIN,
            "account",
            unbound,
        )
        is None
    )
    server.collector_store.close()


def test_identity_referenced_by_schedule_cannot_be_deleted(tmp_path, monkeypatch):
    server, client = _collector_test_client(tmp_path, monkeypatch)
    headers = {"token": "collector-test-token"}
    created = client.post(
        "/ui/api/collector-identities",
        headers=headers,
        json={"name": "Scheduled", "platform": "tiktok"},
    )
    identity_id = created.json()["identity"]["identity_id"]
    server.ui_schedules["S000001"] = {
        "schedule_id": "S000001",
        "schedule_type": server.ACCOUNT_BATCH_SCHEDULE,
        "identity_id": identity_id,
    }

    rejected = client.delete(
        f"/ui/api/collector-identities/{identity_id}",
        headers=headers,
    )
    assert rejected.status_code == 409
    server.collector_leases.lease(identity_id)
    server.collector_store.close()


def test_collect_monitor_exception_response_does_not_echo_transport_secrets(
    tmp_path,
    monkeypatch,
):
    server, client = _collector_test_client(tmp_path, monkeypatch)
    headers = {"token": "collector-test-token"}
    server.ui_schedules["S000001"] = {
        "schedule_id": "S000001",
        "schedule_type": server.COLLECT_MONITOR_SCHEDULE,
        "name": "Monitor",
        "collect_id": "123",
        "enabled": False,
        "interval_minutes": 30,
        "identity_id": "",
    }

    async def fail_monitor(schedule):
        raise RuntimeError(
            "GET https://example.test/?device_id=device-secret "
            "via socks5://user:password@proxy.test:1080"
        )

    async def ignore_notification(**kwargs):
        return None

    server._run_collect_monitor_once = fail_monitor
    server._notify_collect_monitor = ignore_notification
    server._persist_ui_schedules = lambda: None

    response = client.post(
        "/ui/api/collect-monitors/S000001/run",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["result"]["error_code"] == "monitor_execution_failed"
    assert "device-secret" not in response.text
    assert "user:password" not in response.text
    server.collector_store.close()
