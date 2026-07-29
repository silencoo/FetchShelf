from base64 import b64encode

import pytest

from src.collector import (
    AESGCMSecretCodec,
    SecretCodecError,
    SecretCodecUnavailable,
    load_identity_key,
)


def test_aesgcm_codec_roundtrip_uses_random_versioned_envelopes():
    codec = AESGCMSecretCodec(bytes(range(32)))
    context = b"collector:test"
    plaintext = b'{"cookie":"sessionid=secret"}'

    first = codec.seal(plaintext, context=context)
    second = codec.seal(plaintext, context=context)

    assert first != second
    assert plaintext not in first
    assert codec.open(first, context=context) == plaintext
    assert codec.open(second, context=context) == plaintext


def test_aesgcm_codec_rejects_tampering_and_context_swap():
    codec = AESGCMSecretCodec(b"k" * 32)
    envelope = codec.seal(b"sensitive", context=b"identity:a")
    tampered = envelope[:-1] + bytes([envelope[-1] ^ 1])

    with pytest.raises(SecretCodecError, match="authentication failed"):
        codec.open(tampered, context=b"identity:a")
    with pytest.raises(SecretCodecError, match="authentication failed"):
        codec.open(envelope, context=b"identity:b")


def test_load_identity_key_supports_file_base64_and_environment_hex(tmp_path):
    key = bytes(range(32))
    secret_file = tmp_path / "identity-key"
    secret_file.write_text(b64encode(key).decode("ascii"), encoding="ascii")

    assert load_identity_key(
        environment={"FETCHSHELF_IDENTITY_KEY_FILE": str(secret_file)}
    ) == key
    assert load_identity_key(
        environment={"FETCHSHELF_IDENTITY_KEY": f"hex:{key.hex()}"},
        default_key_file=tmp_path / "missing",
    ) == key


def test_load_identity_key_supports_exact_raw_file(tmp_path):
    key = b"r" * 32
    secret_file = tmp_path / "raw-key"
    secret_file.write_bytes(key)

    assert load_identity_key(
        environment={"FETCHSHELF_IDENTITY_KEY_FILE": str(secret_file)}
    ) == key


def test_load_identity_key_fails_closed_when_missing(tmp_path):
    with pytest.raises(SecretCodecUnavailable, match="key is missing"):
        load_identity_key(environment={}, default_key_file=tmp_path / "missing")


def test_aesgcm_codec_requires_256_bit_key():
    with pytest.raises(SecretCodecError, match="32-byte"):
        AESGCMSecretCodec(b"short")

