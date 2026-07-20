"""Cross-entrypoint security contract for collector identities.

These tests intentionally exercise both the direct FastAPI routes and the
public WebUI task boundary.  Identity credentials may be used at runtime, but
must never be copied back into request models, response ``params``, validation
errors, task payloads/results, or failure messages.
"""

from asyncio import Queue
from json import dumps
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, ValidationError

from src.application.main_server import APIServer
from src.collector import (
    AESGCMSecretCodec,
    CollectorCredentials,
    CollectorStore,
    IdentityLeaseManager,
)
from src.models import (
    Account,
    AccountTiktok,
    Comment,
    Detail,
    DetailTikTok,
    GeneralSearch,
    Live,
    LiveSearch,
    LiveTikTok,
    Mix,
    MixTikTok,
    Reply,
    UserSearch,
    VideoSearch,
)


IDENTITY_ID = "tt-main"
SECRETS = {
    # Keep these leak markers short.  Pydantic abbreviates long ``input_value``
    # representations; short markers prove even a partial validation error
    # cannot expose submitted identity material.
    "cookie": "sessionid=CK_LEAK_91",
    "proxy": "socks5://u:p@px:1080",
    "user_agent": "UA_LEAK_91",
    "device_id": "DEV_LEAK_91",
    "a_bogus": "AB_LEAK_91",
    "x_bogus": "XB_LEAK_91",
    "x_gnarly": "XG_LEAK_91",
    "ms_token": "MS_LEAK_91",
}


ENTRY_MODELS = (
    (Detail, {"detail_id": "7300000000000000000"}),
    (DetailTikTok, {"detail_url": "https://www.tiktok.com/@demo/video/1"}),
    (Account, {"sec_user_id": "douyin-sec-user"}),
    (AccountTiktok, {"sec_user_id": "tiktok-sec-user"}),
    (Mix, {"mix_id": "douyin-mix"}),
    (MixTikTok, {"mix_id": "tiktok-mix"}),
    (Live, {"web_rid": "douyin-live"}),
    (LiveTikTok, {"room_id": "tiktok-live"}),
    (Comment, {"detail_id": "7300000000000000000"}),
    (
        Reply,
        {
            "detail_id": "7300000000000000000",
            "comment_id": "comment-id",
        },
    ),
    (GeneralSearch, {"keyword": "douyin-general"}),
    (VideoSearch, {"keyword": "douyin-video"}),
    (UserSearch, {"keyword": "douyin-user"}),
    (LiveSearch, {"keyword": "douyin-live"}),
)


UI_TASK_PAYLOADS = (
    ("/douyin/detail", {"detail_id": "7300000000000000000"}),
    ("/douyin/account", {"sec_user_id": "douyin-sec-user"}),
    ("/douyin/mix", {"mix_id": "douyin-mix"}),
    ("/douyin/live", {"web_rid": "douyin-live"}),
    ("/douyin/comment", {"detail_id": "7300000000000000000"}),
    (
        "/douyin/reply",
        {
            "detail_id": "7300000000000000000",
            "comment_id": "comment-id",
        },
    ),
    ("/douyin/search/general", {"keyword": "douyin-general"}),
    ("/douyin/search/video", {"keyword": "douyin-video"}),
    ("/douyin/search/user", {"keyword": "douyin-user"}),
    ("/douyin/search/live", {"keyword": "douyin-live"}),
    ("/tiktok/detail", {"detail_url": "https://www.tiktok.com/@demo/video/1"}),
    ("/tiktok/account", {"sec_user_id": "tiktok-sec-user"}),
    ("/tiktok/mix", {"mix_id": "tiktok-mix"}),
    ("/tiktok/live", {"room_id": "tiktok-live"}),
    (
        "/workflow/douyin/account_batch",
        {"use_settings": False, "items": []},
    ),
    (
        "/workflow/tiktok/account_batch",
        {"use_settings": False, "items": []},
    ),
    (
        "/workflow/douyin/detail_links",
        {"links": ["https://www.douyin.com/video/1"]},
    ),
    (
        "/workflow/tiktok/detail_links",
        {"links": ["https://www.tiktok.com/@demo/video/1"]},
    ),
)


DIRECT_ENDPOINT_PAYLOADS = tuple(
    (endpoint, payload)
    for endpoint, payload in UI_TASK_PAYLOADS
    if not endpoint.startswith("/workflow/")
)


def _assert_secrets_absent(value) -> None:
    serialized = value if isinstance(value, str) else dumps(value, ensure_ascii=False)
    for secret in SECRETS.values():
        assert secret not in serialized


def _entrypoint_test_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DOUK_API_TOKEN", "entrypoint-test-token")
    server = APIServer.__new__(APIServer)
    server.server = FastAPI()
    server.collector_store = CollectorStore(
        tmp_path / "collector.sqlite3",
        codec=AESGCMSecretCodec(b"e" * 32),
    )
    server.collector_leases = IdentityLeaseManager()
    server.collector_vault_error = ""
    server.ui_schedules = {}
    server.ui_tasks = {}
    server.ui_task_counter = 0
    server.ui_task_queue = Queue()
    server.parameter = SimpleNamespace(
        timeout=10,
        headers={"User-Agent": "test"},
        headers_tiktok={"User-Agent": "test"},
    )
    server.setup_routes()
    return server, TestClient(server.server)


@pytest.mark.parametrize(("model", "payload"), ENTRY_MODELS)
def test_all_collector_entry_models_expose_identity_id(model, payload):
    default_extract = model(**payload)
    assert default_extract.identity_id == ""

    extract = model(**payload, identity_id=IDENTITY_ID)
    assert extract.identity_id == IDENTITY_ID
    assert extract.model_dump()["identity_id"] == IDENTITY_ID

    with pytest.raises(ValidationError):
        model(**payload, identity_id={"raw": "not-a-string"})


@pytest.mark.parametrize(
    ("validator", "payload"),
    (
        (
            APIServer._validate_ui_workflow_account_payload,
            {"use_settings": False, "items": []},
        ),
        (
            APIServer._validate_ui_workflow_detail_payload,
            {"links": ["https://www.tiktok.com/@demo/video/1"]},
        ),
    ),
)
def test_workflow_entry_models_validate_identity_id_as_a_string(validator, payload):
    validator({**payload, "identity_id": IDENTITY_ID})

    with pytest.raises(ValueError, match="identity_id"):
        validator({**payload, "identity_id": 123})


class _SensitiveExtract(BaseModel):
    identity_id: str
    detail_id: str
    cookie: str
    proxy: str
    user_agent: str
    device_id: str
    a_bogus: str
    x_bogus: str
    x_gnarly: str
    ms_token: str


@pytest.mark.parametrize("outcome", ("success", "failed"))
def test_response_helpers_never_echo_sensitive_extract_params(outcome):
    extract = _SensitiveExtract(
        identity_id=IDENTITY_ID,
        detail_id="7300000000000000000",
        **SECRETS,
    )

    if outcome == "success":
        response = APIServer.success_response(extract, {"ok": True})
    else:
        response = APIServer.failed_response(extract)

    public = response.model_dump(mode="json")
    assert public["params"]["identity_id"] == IDENTITY_ID
    assert public["params"]["detail_id"] == "7300000000000000000"
    _assert_secrets_absent(public)


def test_direct_api_failed_response_does_not_echo_explicit_credentials(
    tmp_path,
    monkeypatch,
):
    server, client = _entrypoint_test_client(tmp_path, monkeypatch)

    async def failed_detail(extract, tiktok=False):
        return APIServer.failed_response(extract)

    server.handle_detail = failed_detail
    try:
        for endpoint, payload in (
            ("/douyin/detail", {"detail_id": "7300000000000000000"}),
            ("/tiktok/detail", {"detail_id": "7300000000000000000"}),
        ):
            response = client.post(
                endpoint,
                headers={"token": "entrypoint-test-token"},
                json={
                    **payload,
                    "identity_id": IDENTITY_ID,
                    "cookie": SECRETS["cookie"],
                    "proxy": SECRETS["proxy"],
                },
            )
            assert response.status_code == 200, response.text
            assert response.json()["params"]["identity_id"] == IDENTITY_ID
            _assert_secrets_absent(response.text)
    finally:
        server.collector_store.close()


def test_direct_api_does_not_echo_credentials_loaded_for_selected_identity(
    tmp_path,
    monkeypatch,
):
    server, client = _entrypoint_test_client(tmp_path, monkeypatch)
    stored_credentials = CollectorCredentials(
        cookie=SECRETS["cookie"],
        proxy=SECRETS["proxy"],
        user_agent=SECRETS["user_agent"],
        device_id=SECRETS["device_id"],
        browser_info={
            "a_bogus": SECRETS["a_bogus"],
            "X-Bogus": SECRETS["x_bogus"],
            "X-Gnarly": SECRETS["x_gnarly"],
            "msToken": SECRETS["ms_token"],
        },
    )
    seen_runtime_extracts = []

    class FakeWorker:
        async def deal_search_data(self, runtime_extract, source):
            seen_runtime_extracts.append(runtime_extract)
            return []

    server._plan_collector_routes = lambda *args, **kwargs: [
        {
            "identity_id": IDENTITY_ID,
            "reason": "task_override",
        }
    ]

    async def execute_loaded_identity(platform, identity_id, operation, **kwargs):
        result, successes, failures = await operation(
            FakeWorker(),
            stored_credentials,
            identity_id,
        )
        assert successes == 0
        assert failures == 1
        return result

    server._execute_collector_identity_operation = execute_loaded_identity
    try:
        response = client.post(
            "/douyin/search/general",
            headers={"token": "entrypoint-test-token"},
            json={
                "keyword": "identity-bound-search",
                "identity_id": IDENTITY_ID,
            },
        )
        assert response.status_code == 200, response.text
        params = response.json()["params"]
        assert params["identity_id"] == IDENTITY_ID
        assert params["selected_identity_id"] == IDENTITY_ID
        assert params["selected_by"] == "task_override"
        _assert_secrets_absent(response.text)

        assert len(seen_runtime_extracts) == 1
        assert seen_runtime_extracts[0].cookie == SECRETS["cookie"]
        assert seen_runtime_extracts[0].proxy == SECRETS["proxy"]
    finally:
        server.collector_store.close()


def test_direct_api_malformed_inputs_never_echo_identity_material(
    tmp_path,
    monkeypatch,
):
    server, client = _entrypoint_test_client(tmp_path, monkeypatch)
    try:
        for endpoint, payload in DIRECT_ENDPOINT_PAYLOADS:
            response = client.post(
                endpoint,
                headers={"token": "entrypoint-test-token"},
                json={
                    **payload,
                    "identity_id": IDENTITY_ID,
                    "cookie": [SECRETS["cookie"]],
                },
            )
            assert response.status_code == 422, (endpoint, response.text)
            _assert_secrets_absent(response.text)

        for secret in SECRETS.values():
            response = client.post(
                "/tiktok/detail",
                headers={"token": "entrypoint-test-token"},
                json={
                    "detail_id": "7300000000000000000",
                    "identity_id": IDENTITY_ID,
                    "cookie": [secret],
                },
            )
            assert response.status_code == 422, response.text
            assert secret not in response.text
    finally:
        server.collector_store.close()


def test_ui_task_validation_errors_never_echo_identity_material(
    tmp_path,
    monkeypatch,
):
    server, client = _entrypoint_test_client(tmp_path, monkeypatch)
    try:
        for endpoint, payload in UI_TASK_PAYLOADS:
            response = client.post(
                "/ui/api/tasks",
                headers={"token": "entrypoint-test-token"},
                json={
                    "endpoint": endpoint,
                    "payload": {
                        **payload,
                        "identity_id": IDENTITY_ID,
                        "cookie": [SECRETS["cookie"]],
                    },
                },
            )
            assert response.status_code == 400, (endpoint, response.text)
            _assert_secrets_absent(response.text)

        # Exercise every credential/fingerprint class through a Pydantic-backed
        # task endpoint.  Putting it in an invalid string field makes it part of
        # ValidationError.input unless the HTTP boundary sanitizes the error.
        for secret in SECRETS.values():
            response = client.post(
                "/ui/api/tasks",
                headers={"token": "entrypoint-test-token"},
                json={
                    "endpoint": "/tiktok/detail",
                    "payload": {
                        "detail_id": "7300000000000000000",
                        "identity_id": IDENTITY_ID,
                        "cookie": [secret],
                    },
                },
            )
            assert response.status_code == 400, response.text
            assert secret not in response.text
    finally:
        server.collector_store.close()


def test_all_ui_task_entrypoints_accept_identity_without_exposing_credentials(
    tmp_path,
    monkeypatch,
):
    server, client = _entrypoint_test_client(tmp_path, monkeypatch)
    try:
        for endpoint, payload in UI_TASK_PAYLOADS:
            response = client.post(
                "/ui/api/tasks",
                headers={"token": "entrypoint-test-token"},
                json={
                    "endpoint": endpoint,
                    "payload": {
                        **payload,
                        "identity_id": IDENTITY_ID,
                        **SECRETS,
                    },
                },
            )
            assert response.status_code == 200, (endpoint, response.text)
            task = response.json()["task"]
            assert task["endpoint"] == endpoint
            assert task["payload"]["identity_id"] == IDENTITY_ID
            _assert_secrets_absent(response.text)
    finally:
        server.collector_store.close()


@pytest.mark.asyncio
async def test_ui_task_runtime_failure_hides_loaded_identity_material():
    server = APIServer.__new__(APIServer)
    task = {
        "task_id": "T000001",
        "endpoint": "/tiktok/detail",
        "payload": {
            "detail_id": "7300000000000000000",
            "identity_id": IDENTITY_ID,
        },
        "status": "pending",
        "created_at": "2026-07-14 00:00:00",
        "started_at": None,
        "finished_at": None,
        "updated_at": "2026-07-14 00:00:00",
        "retry_of": None,
        "worker": None,
        "error": "",
        "message": "",
        "result": None,
        "_runner": None,
    }
    server.ui_tasks = {task["task_id"]: task}

    async def fail_with_loaded_credentials(endpoint, payload):
        raise RuntimeError(dumps(SECRETS, ensure_ascii=False))

    server._execute_ui_endpoint = fail_with_loaded_credentials

    await server._execute_ui_task(task["task_id"], worker_id=1)
    public = server._public_ui_task(task)

    assert public["status"] == "failed"
    assert public["error"] == "task_execution_failed"
    assert public["payload"]["identity_id"] == IDENTITY_ID
    _assert_secrets_absent(public)


@pytest.mark.parametrize("endpoint", tuple(item[0] for item in UI_TASK_PAYLOADS))
def test_public_failed_ui_tasks_redact_payload_result_and_error_text(endpoint):
    task = {
        "task_id": "T000001",
        "endpoint": endpoint,
        "payload": {"identity_id": IDENTITY_ID, **SECRETS},
        "status": "failed",
        "error": (
            f"request failed via {SECRETS['proxy']} "
            f"device_id={SECRETS['device_id']}"
        ),
        "message": f"Cookie: {SECRETS['cookie']}",
        "result": {
            "message": "failed",
            "params": {"identity_id": IDENTITY_ID, **SECRETS},
        },
        "_runner": object(),
    }

    public = APIServer._public_ui_task(task)

    assert public["endpoint"] == endpoint
    assert public["payload"]["identity_id"] == IDENTITY_ID
    assert public["result"]["params"]["identity_id"] == IDENTITY_ID
    assert "_runner" not in public
    _assert_secrets_absent(public)
