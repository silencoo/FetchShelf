import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from ipaddress import ip_address
import socket
import ssl

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from fastapi import FastAPI, Header, HTTPException, WebSocket
import httpx
import pytest
from uvicorn import Config
from websockets.asyncio.client import connect

from src.webui.local_https import ensure_certificate, https_config, serve_listeners
from src.webui_security import is_protected_project_path


def test_certificate_names_permissions_reuse_and_renewal(tmp_path):
    cert, key = ensure_certificate(tmp_path, "192.168.0.2,fetchshelf.local")
    original, original_key = cert.read_bytes(), key.read_bytes()
    parsed = x509.load_pem_x509_certificate(original)
    parsed.verify_directly_issued_by(parsed)
    san = parsed.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert ip_address("192.168.0.2") in san.get_values_for_type(x509.IPAddress)
    assert "fetchshelf.local" in san.get_values_for_type(x509.DNSName)
    assert key.stat().st_mode & 0o777 == 0o600
    assert cert.parent.stat().st_mode & 0o777 == 0o700
    assert is_protected_project_path(tmp_path, key)
    ensure_certificate(tmp_path, "fetchshelf.local,192.168.0.2")
    assert cert.read_bytes() == original
    ensure_certificate(tmp_path, "192.168.0.3")
    assert cert.read_bytes() != original
    assert key.read_bytes() == original_key
    # A near-expiry certificate is renewed, keeping the private key.
    parsed = x509.load_pem_x509_certificate(cert.read_bytes())
    private_key = serialization.load_pem_private_key(original_key, password=None)
    now = datetime.now(timezone.utc)
    builder = (x509.CertificateBuilder().subject_name(parsed.subject).issuer_name(parsed.issuer)
        .public_key(parsed.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=1)))
    for extension in parsed.extensions:
        builder = builder.add_extension(extension.value, extension.critical)
    cert.write_bytes(builder.sign(private_key, hashes.SHA256()).public_bytes(serialization.Encoding.PEM))
    ensure_certificate(tmp_path, "192.168.0.3")
    assert x509.load_pem_x509_certificate(cert.read_bytes()).not_valid_after_utc > now + timedelta(days=300)
    assert key.read_bytes() == original_key


def test_disabled_by_default_and_rejects_bad_configuration(tmp_path, monkeypatch):
    monkeypatch.delenv("FETCHSHELF_AUTO_HTTPS", raising=False)
    config = Config(FastAPI(), port=5555)
    assert https_config(config, tmp_path) is None
    assert not list(tmp_path.iterdir())
    monkeypatch.setenv("FETCHSHELF_AUTO_HTTPS", "1")
    monkeypatch.setenv("FETCHSHELF_HTTPS_PORT", "5555")
    with pytest.raises(ValueError, match="different from HTTP"):
        https_config(config, tmp_path)
    with pytest.raises(ValueError, match="not URLs"):
        ensure_certificate(tmp_path, "https://192.168.0.2:5557")


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.mark.asyncio
async def test_http_https_websocket_share_app_auth_and_single_lifecycle(tmp_path):
    lifecycle = []

    @asynccontextmanager
    async def lifespan(app):
        lifecycle.append("start")
        yield
        lifecycle.append("stop")

    app = FastAPI(lifespan=lifespan)

    @app.get("/private")
    async def private(token: str = Header(default="")):
        if token != "test-token":
            raise HTTPException(403)
        return {"ok": True}

    @app.websocket("/ws")
    async def websocket(ws: WebSocket):
        await ws.accept()
        await ws.send_text("same app")
        await ws.close()

    cert, key = ensure_certificate(tmp_path, "127.0.0.1")
    http_port, tls_port = free_port(), free_port()
    http = Config(app, host="127.0.0.1", port=http_port, log_level="error")
    tls = Config(app, host="127.0.0.1", port=tls_port, log_level="error", lifespan="off",
                 ssl_certfile=str(cert), ssl_keyfile=str(key), timeout_graceful_shutdown=1)
    context = ssl.create_default_context(cafile=str(cert))
    task = asyncio.create_task(serve_listeners(http, tls))
    try:
        async with httpx.AsyncClient(verify=context, trust_env=False) as client:
            for _ in range(100):
                try:
                    await client.get(f"https://127.0.0.1:{tls_port}/private")
                    break
                except httpx.ConnectError:
                    await asyncio.sleep(.03)
            else:
                pytest.fail("HTTPS did not start")
            for origin in (f"http://127.0.0.1:{http_port}", f"https://127.0.0.1:{tls_port}"):
                assert (await client.get(origin + "/private")).status_code == 403
                assert (await client.get(origin + "/private", headers={"token": "test-token"})).json() == {"ok": True}
            async with connect(f"wss://127.0.0.1:{tls_port}/ws", ssl=context) as ws:
                assert await ws.recv() == "same app"
            # The certificate is deliberately untrusted until the client trusts it.
            async with httpx.AsyncClient(trust_env=False) as untrusted:
                with pytest.raises(httpx.ConnectError):
                    await untrusted.get(f"https://127.0.0.1:{tls_port}/private")
        assert lifecycle == ["start"]
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 5)
    assert lifecycle == ["start", "stop"]
    for port in (http_port, tls_port):
        with socket.socket() as sock:
            assert sock.connect_ex(("127.0.0.1", port)) != 0


@pytest.mark.asyncio
async def test_https_bind_failure_stops_http(tmp_path):
    cert, key = ensure_certificate(tmp_path, "")
    http_port = free_port()
    with socket.socket() as occupied:
        occupied.bind(("127.0.0.1", 0))
        occupied.listen()
        app = FastAPI()
        http = Config(app, host="127.0.0.1", port=http_port, log_level="error")
        tls = Config(app, host="127.0.0.1", port=occupied.getsockname()[1], lifespan="off", log_level="error",
                     ssl_certfile=str(cert), ssl_keyfile=str(key))
        with pytest.raises(RuntimeError, match="Unable to start WebUI port"):
            await asyncio.wait_for(serve_listeners(http, tls), 5)
    with socket.socket() as sock:
        assert sock.connect_ex(("127.0.0.1", http_port)) != 0
