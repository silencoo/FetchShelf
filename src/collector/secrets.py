from __future__ import annotations

from abc import ABC, abstractmethod
from base64 import b64decode, urlsafe_b64decode
from binascii import Error as BinasciiError
from os import environ, urandom
from pathlib import Path
from typing import Mapping

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class SecretCodecError(RuntimeError):
    """Raised when collector credentials cannot be safely sealed or opened."""


class SecretCodecUnavailable(SecretCodecError):
    pass


class SecretCodec(ABC):
    """Authenticated secret-envelope boundary.

    Production implementations should use a reviewed authenticated-encryption
    primitive and keep its key outside ``settings``. The collector core does not
    ship a home-grown cipher or silently fall back to plaintext storage.
    """

    codec_id: str
    secure: bool = True

    @abstractmethod
    def seal(self, plaintext: bytes, *, context: bytes) -> bytes:
        """Return an opaque authenticated envelope for ``plaintext``."""

    @abstractmethod
    def open(self, envelope: bytes, *, context: bytes) -> bytes:
        """Authenticate and decrypt an envelope created by :meth:`seal`."""


class UnavailableSecretCodec(SecretCodec):
    """Fail-closed default used until the application injects a real codec."""

    codec_id = "unavailable"
    secure = False

    def seal(self, plaintext: bytes, *, context: bytes) -> bytes:
        raise SecretCodecUnavailable(
            "collector credential storage requires a configured secure SecretCodec"
        )

    def open(self, envelope: bytes, *, context: bytes) -> bytes:
        raise SecretCodecUnavailable(
            "collector credential storage requires a configured secure SecretCodec"
        )


class AESGCMSecretCodec(SecretCodec):
    """Versioned AES-256-GCM envelope with caller context bound as AAD."""

    codec_id = "aesgcm-v1"
    secure = True
    _MAGIC = b"DOUKID\x01"
    _NONCE_BYTES = 12
    _AAD_PREFIX = b"douK.collector.credentials\x00v1\x00"

    def __init__(self, key: bytes):
        if not isinstance(key, bytes) or len(key) != 32:
            raise SecretCodecError("AESGCMSecretCodec requires an exact 32-byte key")
        self._cipher = AESGCM(key)

    def seal(self, plaintext: bytes, *, context: bytes) -> bytes:
        if not isinstance(plaintext, bytes) or not isinstance(context, bytes):
            raise TypeError("plaintext and context must be bytes")
        nonce = urandom(self._NONCE_BYTES)
        ciphertext = self._cipher.encrypt(
            nonce,
            plaintext,
            self._AAD_PREFIX + context,
        )
        return self._MAGIC + nonce + ciphertext

    def open(self, envelope: bytes, *, context: bytes) -> bytes:
        if not isinstance(envelope, bytes) or not isinstance(context, bytes):
            raise TypeError("envelope and context must be bytes")
        minimum = len(self._MAGIC) + self._NONCE_BYTES + 16
        if len(envelope) < minimum or not envelope.startswith(self._MAGIC):
            raise SecretCodecError("invalid collector credential envelope")
        offset = len(self._MAGIC)
        nonce = envelope[offset : offset + self._NONCE_BYTES]
        ciphertext = envelope[offset + self._NONCE_BYTES :]
        try:
            return self._cipher.decrypt(
                nonce,
                ciphertext,
                self._AAD_PREFIX + context,
            )
        except InvalidTag as error:
            raise SecretCodecError(
                "collector credential envelope authentication failed"
            ) from error

    @classmethod
    def from_environment(
        cls,
        *,
        environment: Mapping[str, str] | None = None,
        default_key_file: str | Path = "/run/secrets/douk_identity_key",
    ) -> "AESGCMSecretCodec":
        return cls(
            load_identity_key(
                environment=environment,
                default_key_file=default_key_file,
            )
        )


def _decode_key_material(value: bytes) -> bytes:
    if len(value) == 32:
        return value
    stripped = value.strip()
    lowered = stripped.lower()

    if lowered.startswith(b"hex:"):
        candidate = stripped[4:]
        try:
            decoded = bytes.fromhex(candidate.decode("ascii"))
        except (UnicodeDecodeError, ValueError) as error:
            raise SecretCodecError("invalid hex collector identity key") from error
        if len(decoded) == 32:
            return decoded
        raise SecretCodecError("collector identity key must decode to 32 bytes")

    if lowered.startswith(b"base64:"):
        stripped = stripped[7:]

    if len(stripped) == 64:
        try:
            decoded = bytes.fromhex(stripped.decode("ascii"))
        except (UnicodeDecodeError, ValueError):
            decoded = b""
        if len(decoded) == 32:
            return decoded

    for decoder in (b64decode, urlsafe_b64decode):
        try:
            decoded = (
                decoder(stripped, validate=True)
                if decoder is b64decode
                else decoder(stripped)
            )
        except (BinasciiError, ValueError):
            continue
        if len(decoded) == 32:
            return decoded

    if len(stripped) == 32:
        return stripped
    raise SecretCodecError(
        "collector identity key must be 32 raw bytes or decode from hex/base64 to 32 bytes"
    )


def load_identity_key(
    *,
    environment: Mapping[str, str] | None = None,
    default_key_file: str | Path = "/run/secrets/douk_identity_key",
) -> bytes:
    """Load an identity key without ever creating or persisting one.

    File-based Docker secrets take precedence. ``DOUK_IDENTITY_KEY`` is an
    explicit fallback for environments that cannot mount a secret file.
    """

    values = environ if environment is None else environment
    configured_path = values.get("DOUK_IDENTITY_KEY_FILE", "").strip()
    key_path = Path(configured_path or default_key_file)
    try:
        if key_path.is_file():
            return _decode_key_material(key_path.read_bytes())
    except OSError as error:
        raise SecretCodecUnavailable(
            f"unable to read collector identity key file: {key_path}"
        ) from error

    if inline := values.get("DOUK_IDENTITY_KEY", ""):
        return _decode_key_material(inline.encode("utf-8"))

    raise SecretCodecUnavailable(
        "collector identity key is missing; mount DOUK_IDENTITY_KEY_FILE "
        f"(default {key_path}) or set DOUK_IDENTITY_KEY"
    )


def require_secure_codec(codec: SecretCodec) -> None:
    codec_id = str(getattr(codec, "codec_id", "") or "").strip()
    if not codec_id or not getattr(codec, "secure", False):
        raise SecretCodecUnavailable(
            "collector credential storage requires a named secure SecretCodec"
        )
