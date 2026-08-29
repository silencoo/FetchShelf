from types import SimpleNamespace

import pytest

from src.config import parameter as parameter_module
from src.config.parameter import Parameter
from src.encrypt import DouYinParams
from src.encrypt.xGnarly import XGnarly
from src.interface import template as template_module
from src.interface.template import API, APITikTok
from src.tools import dynamic_import


class _Console:
    def __init__(self):
        self.infos = []
        self.errors = []

    def info(self, message, *args, **kwargs):
        self.infos.append(str(message))

    def error(self, message, *args, **kwargs):
        self.errors.append(str(message))


@pytest.mark.asyncio
async def test_douyin_signer_receives_effective_request_contract():
    calls = []

    class Signer:
        def get_value(self, **kwargs):
            calls.append(kwargs)
            return "douyin-signature"

    api = API.__new__(API)
    api.ab = Signer()
    api.headers = {"User-Agent": "default-agent"}
    api.proxy = None
    dispatched = {}

    async def request_get(url, params, headers, **kwargs):
        dispatched.update(url=url, params=params, headers=headers)
        return {"ok": True}

    api.request_data_get = request_get
    result = await API.request_data(
        api,
        "https://example.test/data",
        params={"cursor": 1},
        headers={"User-Agent": "request-agent"},
    )

    assert result == {"ok": True}
    assert calls == [
        {
            "query": "cursor=1",
            "data": None,
            "method": "GET",
            "user_agent": "request-agent",
        }
    ]
    assert dispatched["headers"]["User-Agent"] == "request-agent"
    assert dispatched["params"].endswith("a_bogus=douyin-signature")


@pytest.mark.asyncio
async def test_tiktok_post_signer_receives_request_contract():
    calls = []
    body = {"room_id": "123", "enter_source": "others-others"}

    class TikTokSigner:
        available = True

        def sign_url(self, **kwargs):
            calls.append(kwargs)
            return "aid=1988&X-Dynosaur=dyno&X-Bogus=xb&X-Gnarly=xg"

    api = APITikTok.__new__(APITikTok)
    api.tiktok_params = TikTokSigner()
    api.params = {"msToken": "session-token"}
    api.headers = {"User-Agent": "default-agent"}
    api.proxy = None
    dispatched = {}

    async def request_post(url, params, data, headers, **kwargs):
        dispatched.update(url=url, params=params, data=data, headers=headers)
        return {"ok": True}

    api.request_data_post = request_post
    result = await APITikTok.request_data(
        api,
        "https://example.test/live",
        params={"aid": "1988"},
        data=body,
        method="POST",
        headers={"User-Agent": "request-agent"},
    )

    assert result == {"ok": True}
    assert calls == [
        {
            "query": "aid=1988",
            "data": body,
            "method": "POST",
            "user_agent": "request-agent",
            "ms_token": "session-token",
        }
    ]
    assert dispatched["data"] is body
    assert "X-Dynosaur=dyno" in dispatched["params"]
    assert "X-Bogus=xb" in dispatched["params"]
    assert "X-Gnarly=xg" in dispatched["params"]


def test_builtin_x_gnarly_accepts_form_body():
    result = XGnarly().generate(
        query="aid=1988",
        data={"room_id": "123"},
        method="POST",
        user_agent="test-agent",
    )

    assert isinstance(result, str)
    assert result


def test_api_request_params_are_isolated_per_identity():
    template = API.params.copy()
    first = SimpleNamespace(
        headers={"User-Agent": "first"},
        logger=None,
        ab=None,
        console=None,
        max_retry=1,
        timeout=10,
        request_delay=6,
        client=None,
        proxy=None,
        api_params={"browser_language": "zh-CN", "uifid": "first-id"},
    )
    second = SimpleNamespace(
        **{
            **vars(first),
            "headers": {"User-Agent": "second"},
            "api_params": {"browser_language": "en-US", "uifid": "second-id"},
        }
    )

    first_api = API(first)
    second_api = API(second)
    first_api.params["cursor"] = "100"

    assert first_api.params["uifid"] == "first-id"
    assert second_api.params["uifid"] == "second-id"
    assert second_api.params["browser_language"] == "en-US"
    assert "cursor" not in second_api.params
    assert API.params == template


def test_builtin_douyin_contract_uses_current_impersonated_profile_and_signer():
    params = SimpleNamespace(
        headers={"User-Agent": "legacy-agent"},
        logger=None,
        ab=object(),
        console=None,
        max_retry=1,
        timeout=10,
        request_delay=0,
        client=None,
        proxy=None,
        api_params={
            "browser_platform": "Win32",
            "browser_version": "139.0.0.0",
        },
        _external_signers=set(),
    )

    api = API(params)
    signed = api.deal_url_params({"cursor": 1})

    assert api.params["browser_platform"] == "MacIntel"
    assert api.params["browser_version"] == "146.0.0.0"
    assert signed.endswith(f"a_bogus={DouYinParams.A_BOGUS}")


@pytest.mark.asyncio
async def test_douyin_transport_uses_curl_impersonation_without_legacy_user_agent(
    monkeypatch,
):
    captured = {}

    class Response:
        url = "https://example.test/data"
        status_code = 200
        headers = {}

        @staticmethod
        def raise_for_status():
            return None

        @staticmethod
        def json():
            return {"ok": True}

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_value, traceback):
            return None

        async def request(self, method, url, **kwargs):
            captured.update(method=method, url=url, **kwargs)
            return Response()

    monkeypatch.setattr(template_module, "CurlAsyncSession", Session)
    params = SimpleNamespace(
        headers={"User-Agent": "legacy-agent", "Cookie": "sessionid=secret"},
        logger=SimpleNamespace(
            info=lambda *args, **kwargs: None,
            warning=lambda *args, **kwargs: None,
            error=lambda *args, **kwargs: None,
        ),
        ab=object(),
        console=None,
        max_retry=0,
        timeout=10,
        request_delay=0,
        client=None,
        proxy=None,
        api_params={},
        _external_signers=set(),
    )

    result = await API(params).request_data_get(
        "https://example.test/data",
        "cursor=1",
        params.headers,
    )

    assert result == {"ok": True}
    assert captured["impersonate"] == "chrome146"
    assert "User-Agent" not in captured["headers"]
    assert captured["headers"]["Cookie"] == "sessionid=secret"


def test_dynamic_loader_uses_documented_encipher_filename(tmp_path, monkeypatch):
    console = _Console()
    monkeypatch.delenv("FETCHSHELF_ENCIPHER_PATH", raising=False)
    (tmp_path / "encipher.py").write_text(
        "class XBogus:\n"
        "    def get_x_bogus(self, **kwargs):\n"
        "        return 'external'\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(dynamic_import, "get_base_dir", lambda: tmp_path)

    objects = dynamic_import.load_objects_from_external_py(
        "encipher.py",
        ["XBogus", "XGnarly"],
        console,
    )

    assert set(objects) == {"XBogus"}
    assert objects["XBogus"]().get_x_bogus() == "external"
    assert console.errors == []


def test_dynamic_loader_supports_nas_settings_mount(tmp_path, monkeypatch):
    console = _Console()
    settings_dir = tmp_path / "settings"
    settings_dir.mkdir()
    (settings_dir / "encipher.py").write_text(
        "class XBogus:\n"
        "    def get_x_bogus(self, **kwargs):\n"
        "        return 'nas-external'\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("FETCHSHELF_ENCIPHER_PATH", raising=False)
    monkeypatch.setattr(dynamic_import, "get_base_dir", lambda: tmp_path)

    objects = dynamic_import.load_objects_from_external_py(
        "encipher.py",
        ["XBogus"],
        console,
    )

    assert objects["XBogus"]().get_x_bogus() == "nas-external"


def test_dynamic_loader_falls_back_after_module_error(tmp_path, monkeypatch):
    console = _Console()
    (tmp_path / "encipher.py").write_text("this is invalid python :", encoding="utf-8")
    monkeypatch.setattr(dynamic_import, "get_base_dir", lambda: tmp_path)

    objects = dynamic_import.load_objects_from_external_py(
        "encipher.py",
        ["XBogus"],
        console,
    )

    assert objects == {}
    assert console.errors


def test_parameter_selects_partial_external_signers_and_falls_back(monkeypatch):
    console = _Console()
    builtins = (SimpleNamespace(name="ab"), SimpleNamespace(name="xb"), SimpleNamespace(name="xg"))

    class ExternalXBogus:
        def get_x_bogus(self, **kwargs):
            return "external"

    class BrokenXGnarly:
        def __init__(self):
            raise RuntimeError("broken")

    monkeypatch.setattr(
        parameter_module,
        "load_objects_from_external_py",
        lambda *args, **kwargs: {
            "XBogus": ExternalXBogus,
            "XGnarly": BrokenXGnarly,
        },
    )

    ab, xb, xg, loaded = Parameter.load_signing_objects(console, *builtins)

    assert ab is builtins[0]
    assert isinstance(xb, ExternalXBogus)
    assert xg is builtins[2]
    assert loaded == {"XBogus"}
    assert console.errors
