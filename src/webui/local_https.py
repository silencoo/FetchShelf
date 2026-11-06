"""Optional local TLS, sharing one application and worker lifecycle with HTTP."""

import asyncio
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from ipaddress import ip_address
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from uvicorn import Config, Server


def _private_write(path: Path, data: bytes):
    with NamedTemporaryFile(dir=path.parent, delete=False) as file:
        temporary = Path(file.name)
        try:
            os.chmod(temporary, 0o600)
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def ensure_certificate(settings: Path, hosts: str) -> tuple[Path, Path]:
    """Reuse the private key and renew a self-signed leaf when names/expiry change."""
    names = set()
    for host in {"localhost", "127.0.0.1", "::1", *hosts.split(",")}:
        host = host.strip()
        if not host:
            continue
        try:
            names.add(x509.IPAddress(ip_address(host)))
        except ValueError:
            if any(char in host for char in "/:* \t\n"):
                raise ValueError("FETCHSHELF_HTTPS_HOSTS requires hostnames or IPs, not URLs")
            names.add(x509.DNSName(host.encode("idna").decode("ascii").lower()))
    directory = settings / ".secrets" / "https"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    certificate, key_file = directory / "certificate.pem", directory / "private.key"
    if key_file.exists():
        key_file.chmod(0o600)
        key = serialization.load_pem_private_key(key_file.read_bytes(), password=None)
    else:
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        _private_write(key_file, key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ))
    now = datetime.now(timezone.utc)
    if certificate.exists():
        certificate.chmod(0o600)
        try:
            current = x509.load_pem_x509_certificate(certificate.read_bytes())
            current.verify_directly_issued_by(current)
            if (current.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
                    == key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
                    and set(current.extensions.get_extension_for_class(x509.SubjectAlternativeName).value) == names
                    and current.not_valid_before_utc <= now
                    and current.not_valid_after_utc > now + timedelta(days=30)):
                return certificate, key_file
        except (ValueError, InvalidSignature, x509.ExtensionNotFound):
            pass
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "FetchShelf local HTTPS")])
    certificate_data = (x509.CertificateBuilder()
        .subject_name(subject).issuer_name(subject).public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=365))
        .add_extension(x509.SubjectAlternativeName(sorted(names, key=lambda name: str(name.value))), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .sign(key, hashes.SHA256()))
    _private_write(certificate, certificate_data.public_bytes(serialization.Encoding.PEM))
    return certificate, key_file


def https_config(http: Config, settings: Path) -> Config | None:
    if os.environ.get("FETCHSHELF_AUTO_HTTPS", "0").lower() not in {"1", "true", "yes"}:
        return None
    port = int(os.environ.get("FETCHSHELF_HTTPS_PORT", "5557"))
    if not 1 <= port <= 65535 or port == http.port:
        raise ValueError("HTTPS requires a valid port different from HTTP")
    certificate, key = ensure_certificate(settings, os.environ.get("FETCHSHELF_HTTPS_HOSTS", ""))
    return Config(http.app, host=http.host, port=port, log_level=http.log_level,
                  lifespan="off", ssl_certfile=str(certificate), ssl_keyfile=str(key),
                  timeout_graceful_shutdown=10)


class _Listener(Server):
    """The pair has one signal owner, with shutdown propagated to both listeners."""

    @contextmanager
    def capture_signals(self):
        yield

    def handle_exit(self, sig, frame):
        for peer in self.peers:
            Server.handle_exit(peer, sig, frame)


async def serve_listeners(http: Config, https: Config | None):
    if https is None:
        await Server(http).serve()
        return
    listeners = [_Listener(http), _Listener(https)]
    for listener in listeners:
        listener.peers = listeners

    async def serve(listener):
        try:
            await listener.serve()
        except SystemExit as error:
            # A bind failure must close its sibling, not escape the asyncio loop.
            raise RuntimeError(f"Unable to start WebUI port {listener.config.port}") from error

    with Server.capture_signals(listeners[0]):
        tasks = [asyncio.create_task(serve(listener)) for listener in listeners]
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for listener in listeners:
                listener.should_exit = True
            results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, BaseException):
                raise result
