from copy import deepcopy

import pytest

from src.collector import (
    AESGCMSecretCodec,
    CollectorAssignment,
    CollectorCredentials,
    CollectorIdentity,
    CollectorPlatform,
    CollectorPolicy,
    CollectorRuntimeState,
    CollectorStore,
    IdentityInUseError,
    IdentityPlatformError,
    IdentityStatus,
    SecretCodecError,
    SecretCodecUnavailable,
    migrate_legacy_settings,
)


def identity(identity_id="tt-main", platform=CollectorPlatform.TIKTOK):
    return CollectorIdentity(
        identity_id=identity_id,
        name=identity_id,
        platform=platform,
    )


def test_store_seals_credentials_and_public_summary_has_no_secret_values(tmp_path):
    db = tmp_path / "collector_pool.sqlite3"
    credentials = CollectorCredentials(
        cookie="sessionid=super-secret",
        proxy="socks5://user:password@proxy.example:1080",
        user_agent="private-fingerprint-agent",
        device_id="1234567890123456789",
        browser_info={"region": "US"},
    )
    with CollectorStore(db, codec=AESGCMSecretCodec(b"k" * 32)) as store:
        store.upsert_identity(identity())
        store.write_credentials("tt-main", credentials)

        assert store.load_credentials("tt-main") == credentials
        public = store.list_public()[0].model_dump(mode="json")
        public_text = repr(public)
        assert public["credential_configured"] is True
        assert public["cookie_configured"] is True
        assert public["proxy_configured"] is True
        assert public["device_id_configured"] is True
        for forbidden in (
            "sessionid=super-secret",
            "proxy.example",
            "private-fingerprint-agent",
            "1234567890123456789",
            "cookie",
            "proxy",
            "device_id",
        ):
            if forbidden in {"cookie", "proxy", "device_id"}:
                assert forbidden not in public
            else:
                assert forbidden not in public_text

        row = store.connection.execute(
            "SELECT envelope FROM collector_secrets WHERE identity_id = 'tt-main'"
        ).fetchone()
        assert b"super-secret" not in bytes(row["envelope"])
        assert b"proxy.example" not in bytes(row["envelope"])


def test_store_fails_closed_without_codec_and_never_creates_secret_row(tmp_path):
    with CollectorStore(tmp_path / "collector.sqlite3") as store:
        store.upsert_identity(identity())
        with pytest.raises(SecretCodecUnavailable):
            store.write_credentials(
                "tt-main",
                CollectorCredentials(cookie="secret"),
            )
        count = store.connection.execute(
            "SELECT COUNT(*) FROM collector_secrets"
        ).fetchone()[0]
        assert count == 0


def test_atomic_identity_save_does_not_persist_metadata_when_sealing_fails(tmp_path):
    with CollectorStore(tmp_path / "collector.sqlite3") as store:
        with pytest.raises(SecretCodecUnavailable):
            store.save_identity(
                identity(),
                credentials=CollectorCredentials(cookie="secret"),
            )
        assert store.list_identities() == []


def test_identity_metadata_update_preserves_credentials_when_omitted(tmp_path):
    codec = AESGCMSecretCodec(b"p" * 32)
    with CollectorStore(tmp_path / "collector.sqlite3", codec=codec) as store:
        store.save_identity(
            identity(),
            credentials=CollectorCredentials(cookie="secret"),
        )
        updated = identity().model_copy(update={"name": "renamed"})
        store.save_identity(updated)

        assert store.get_identity("tt-main").name == "renamed"
        assert store.load_credentials("tt-main").cookie == "secret"


def test_store_detects_envelope_tampering(tmp_path):
    with CollectorStore(
        tmp_path / "collector.sqlite3",
        codec=AESGCMSecretCodec(b"x" * 32),
    ) as store:
        store.upsert_identity(identity())
        store.write_credentials("tt-main", CollectorCredentials(cookie="secret"))
        envelope = store.connection.execute(
            "SELECT envelope FROM collector_secrets WHERE identity_id = 'tt-main'"
        ).fetchone()[0]
        tampered = bytes(envelope[:-1]) + bytes([envelope[-1] ^ 1])
        store.connection.execute(
            "UPDATE collector_secrets SET envelope = ? WHERE identity_id = 'tt-main'",
            (tampered,),
        )
        store.connection.commit()

        with pytest.raises(SecretCodecError, match="authentication failed"):
            store.load_credentials("tt-main")


def test_identity_platform_is_immutable_and_cross_platform_binding_is_rejected(tmp_path):
    with CollectorStore(tmp_path / "collector.sqlite3") as store:
        store.upsert_identity(identity())
        with pytest.raises(IdentityPlatformError, match="immutable"):
            store.upsert_identity(identity(platform=CollectorPlatform.DOUYIN))
        with pytest.raises(IdentityPlatformError, match="another platform"):
            store.upsert_assignments(
                [
                    CollectorAssignment(
                        platform=CollectorPlatform.DOUYIN,
                        target_key="https://www.douyin.com/user/demo",
                        identity_id="tt-main",
                    )
                ]
            )


def test_policy_and_assignments_persist_and_guard_identity_delete(tmp_path):
    with CollectorStore(tmp_path / "collector.sqlite3") as store:
        store.upsert_identity(identity("tt-main"))
        store.upsert_identity(identity("tt-fallback"))
        policy = CollectorPolicy(
            platform=CollectorPlatform.TIKTOK,
            default_identity_id="tt-main",
            fallback_identity_ids=["tt-fallback"],
        )
        store.upsert_policy(policy)
        saved = store.upsert_assignments(
            [
                CollectorAssignment(
                    platform=CollectorPlatform.TIKTOK,
                    target_key="@demo",
                    identity_id="tt-main",
                )
            ]
        )[0]

        assert store.get_policy(CollectorPlatform.TIKTOK) == policy
        assert store.get_assignment(
            CollectorPlatform.TIKTOK,
            "account",
            "@demo",
        ) == saved
        with pytest.raises(IdentityInUseError):
            store.delete_identity("tt-main")


def test_runtime_state_persists_but_stale_active_lease_resets_on_reopen(tmp_path):
    db = tmp_path / "collector.sqlite3"
    with CollectorStore(db) as store:
        store.upsert_identity(identity())
        store.save_runtime(
            CollectorRuntimeState(
                identity_id="tt-main",
                status=IdentityStatus.WARNING,
                active_leases=1,
                consecutive_failures=2,
                last_error_code="empty_response",
            )
        )

    with CollectorStore(db) as reopened:
        state = reopened.get_runtime("tt-main")
        assert state.active_leases == 0
        assert state.status == IdentityStatus.WARNING
        assert state.consecutive_failures == 2


def test_legacy_migration_is_pure_and_store_applies_it_atomically(tmp_path):
    legacy = {
        "cookie": {"sessionid_ss": "dy-secret"},
        "proxy": "http://dy-proxy:8080",
        "browser_info": {"User-Agent": "dy-agent"},
        "cookie_tiktok": "sessionid=tt-secret",
        "proxy_tiktok": "socks5://tt-proxy:1080",
        "browser_info_tiktok": {
            "User-Agent": "tt-agent",
            "device_id": "987654321",
        },
        "request_delay": 8,
    }
    before = deepcopy(legacy)
    result = migrate_legacy_settings(legacy)

    assert legacy == before
    assert result.migrated is True
    assert {item.identity_id for item in result.identities} == {
        "legacy-douyin",
        "legacy-tiktok",
    }
    assert result.credentials["legacy-tiktok"].device_id == "987654321"

    with CollectorStore(
        tmp_path / "collector.sqlite3",
        codec=AESGCMSecretCodec(b"m" * 32),
    ) as store:
        assert store.apply_legacy_migration(result) is True
        assert len(store.list_public()) == 2
        assert store.get_policy(
            CollectorPlatform.TIKTOK
        ).default_identity_id == "legacy-tiktok"
        assert (
            store.load_credentials("legacy-douyin").cookie
            == "sessionid_ss=dy-secret"
        )


def test_legacy_migration_is_noop_once_schema_exists():
    assert migrate_legacy_settings(
        {"collector_schema_version": 1, "cookie": "must-not-reappear"}
    ).migrated is False


def test_legacy_migration_coerces_string_platform_switches():
    result = migrate_legacy_settings(
        {"douyin_platform": "false", "tiktok_platform": "true"}
    )
    states = {item.platform: item.enabled for item in result.identities}

    assert states[CollectorPlatform.DOUYIN] is False
    assert states[CollectorPlatform.TIKTOK] is True
