from __future__ import annotations

from contextlib import suppress
from datetime import datetime, timezone
from json import dumps, loads
from pathlib import Path
from sqlite3 import Connection, Row, connect
from threading import RLock
from typing import Iterable

from .models import (
    CollectorAssignment,
    CollectorAuthMode,
    CollectorCredentials,
    CollectorIdentity,
    CollectorIdentityPublic,
    CollectorPlatform,
    CollectorPolicy,
    CollectorRuntimeState,
    IdentityStatus,
    LegacyMigrationResult,
    RouteCandidate,
)
from .secrets import (
    SecretCodec,
    SecretCodecError,
    SecretCodecUnavailable,
    UnavailableSecretCodec,
    require_secure_codec,
)


DEFAULT_STORE_NAME = "collector_pool.sqlite3"
SCHEMA_VERSION = 3


class CollectorStoreError(RuntimeError):
    pass


class IdentityNotFoundError(CollectorStoreError):
    pass


class IdentityInUseError(CollectorStoreError):
    pass


class IdentityPlatformError(CollectorStoreError):
    pass


def _now_text() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _secret_context(identity_id: str) -> bytes:
    return f"collector-identity:{identity_id}:credentials:v1".encode("utf-8")


class CollectorStore:
    """SQLite persistence for identity metadata and sealed credentials.

    The store is synchronous by design: operations are small, serialized by an
    in-process lock, and commit before returning. Network validation and scraping
    must remain outside this class.
    """

    def __init__(
        self,
        path: str | Path,
        *,
        codec: SecretCodec | None = None,
    ) -> None:
        self.path = Path(path)
        self.codec = codec or UnavailableSecretCodec()
        self._lock = RLock()
        self._closed = False
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = connect(self.path, timeout=30, check_same_thread=False)
        self._connection.row_factory = Row
        self._initialize()
        with suppress(OSError):
            self.path.chmod(0o600)

    @classmethod
    def in_settings_dir(
        cls,
        settings_dir: str | Path,
        *,
        codec: SecretCodec | None = None,
    ) -> "CollectorStore":
        return cls(Path(settings_dir).joinpath(DEFAULT_STORE_NAME), codec=codec)

    @property
    def connection(self) -> Connection:
        if self._closed:
            raise CollectorStoreError("collector store is closed")
        return self._connection

    def _initialize(self) -> None:
        with self._lock, self.connection:
            self.connection.execute("PRAGMA foreign_keys = ON")
            self.connection.execute("PRAGMA journal_mode = WAL")
            self.connection.execute("PRAGMA synchronous = FULL")
            self.connection.execute("PRAGMA busy_timeout = 30000")
            self.connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS collector_identities (
                    identity_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    platform TEXT NOT NULL CHECK(platform IN ('douyin', 'tiktok')),
                    auth_mode TEXT NOT NULL DEFAULT 'authenticated'
                        CHECK(auth_mode IN ('authenticated', 'adult_authenticated', 'anonymous')),
                    enabled INTEGER NOT NULL CHECK(enabled IN (0, 1)),
                    weight REAL NOT NULL CHECK(weight > 0),
                    request_delay REAL NOT NULL CHECK(request_delay >= 0),
                    max_concurrency INTEGER NOT NULL CHECK(max_concurrency >= 1),
                    credential_configured INTEGER NOT NULL DEFAULT 0 CHECK(credential_configured IN (0, 1)),
                    cookie_configured INTEGER NOT NULL DEFAULT 0 CHECK(cookie_configured IN (0, 1)),
                    proxy_configured INTEGER NOT NULL DEFAULT 0 CHECK(proxy_configured IN (0, 1)),
                    user_agent_configured INTEGER NOT NULL DEFAULT 0 CHECK(user_agent_configured IN (0, 1)),
                    device_id_configured INTEGER NOT NULL DEFAULT 0 CHECK(device_id_configured IN (0, 1)),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS collector_secrets (
                    identity_id TEXT PRIMARY KEY,
                    codec_id TEXT NOT NULL,
                    envelope BLOB NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(identity_id) REFERENCES collector_identities(identity_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS collector_runtime (
                    identity_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL DEFAULT 'untested',
                    active_leases INTEGER NOT NULL DEFAULT 0 CHECK(active_leases >= 0),
                    consecutive_failures INTEGER NOT NULL DEFAULT 0 CHECK(consecutive_failures >= 0),
                    total_successes INTEGER NOT NULL DEFAULT 0 CHECK(total_successes >= 0),
                    total_failures INTEGER NOT NULL DEFAULT 0 CHECK(total_failures >= 0),
                    risk_failures INTEGER NOT NULL DEFAULT 0 CHECK(risk_failures >= 0),
                    cooldown_until TEXT NOT NULL DEFAULT '',
                    last_validated_at TEXT NOT NULL DEFAULT '',
                    last_success_at TEXT NOT NULL DEFAULT '',
                    last_failure_at TEXT NOT NULL DEFAULT '',
                    last_error_code TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(identity_id) REFERENCES collector_identities(identity_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS collector_assignments (
                    platform TEXT NOT NULL CHECK(platform IN ('douyin', 'tiktok')),
                    target_type TEXT NOT NULL,
                    target_key TEXT NOT NULL,
                    identity_id TEXT NOT NULL,
                    source TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(platform, target_type, target_key),
                    FOREIGN KEY(identity_id) REFERENCES collector_identities(identity_id) ON DELETE RESTRICT
                );

                CREATE TABLE IF NOT EXISTS collector_policies (
                    platform TEXT PRIMARY KEY CHECK(platform IN ('douyin', 'tiktok')),
                    strategy TEXT NOT NULL,
                    default_identity_id TEXT NOT NULL DEFAULT '',
                    fallback_identity_ids TEXT NOT NULL DEFAULT '[]',
                    global_max_parallel INTEGER NOT NULL,
                    binding_failure TEXT NOT NULL,
                    failure_threshold INTEGER NOT NULL,
                    cooldown_seconds INTEGER NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS collector_identities_platform_idx
                    ON collector_identities(platform, enabled);
                CREATE INDEX IF NOT EXISTS collector_assignments_identity_idx
                    ON collector_assignments(identity_id);
                """
            )
            columns = {
                str(row["name"])
                for row in self.connection.execute(
                    "PRAGMA table_info(collector_runtime)"
                ).fetchall()
            }
            if "risk_failures" not in columns:
                self.connection.execute(
                    "ALTER TABLE collector_runtime "
                    "ADD COLUMN risk_failures INTEGER NOT NULL DEFAULT 0 "
                    "CHECK(risk_failures >= 0)"
                )
            identity_columns = {
                str(row["name"])
                for row in self.connection.execute(
                    "PRAGMA table_info(collector_identities)"
                ).fetchall()
            }
            if "auth_mode" not in identity_columns:
                self.connection.execute(
                    "ALTER TABLE collector_identities "
                    "ADD COLUMN auth_mode TEXT NOT NULL DEFAULT 'authenticated' "
                    "CHECK(auth_mode IN "
                    "('authenticated', 'adult_authenticated', 'anonymous'))"
                )
            self.connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            # A lease belongs to a process lifetime. Never resurrect a stale count.
            self.connection.execute(
                "UPDATE collector_runtime SET active_leases = 0, updated_at = ?",
                (_now_text(),),
            )

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._connection.close()
            self._closed = True

    def __enter__(self) -> "CollectorStore":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def _identity_row(self, identity_id: str) -> Row:
        row = self.connection.execute(
            "SELECT * FROM collector_identities WHERE identity_id = ?",
            (identity_id,),
        ).fetchone()
        if row is None:
            raise IdentityNotFoundError(f"collector identity not found: {identity_id}")
        return row

    def _identity_platform(self, identity_id: str) -> CollectorPlatform:
        return CollectorPlatform(self._identity_row(identity_id)["platform"])

    def _upsert_identity_locked(self, identity: CollectorIdentity, now: str) -> None:
        existing = self.connection.execute(
            "SELECT platform FROM collector_identities WHERE identity_id = ?",
            (identity.identity_id,),
        ).fetchone()
        if existing is not None and existing["platform"] != identity.platform.value:
            raise IdentityPlatformError("collector identity platform is immutable")
        self.connection.execute(
            """
            INSERT INTO collector_identities (
                identity_id, name, platform, auth_mode, enabled, weight,
                request_delay, max_concurrency, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(identity_id) DO UPDATE SET
                name = excluded.name,
                auth_mode = excluded.auth_mode,
                enabled = excluded.enabled,
                weight = excluded.weight,
                request_delay = excluded.request_delay,
                max_concurrency = excluded.max_concurrency,
                updated_at = excluded.updated_at
            """,
            (
                identity.identity_id,
                identity.name,
                identity.platform.value,
                identity.auth_mode.value,
                int(identity.enabled),
                identity.weight,
                identity.request_delay,
                identity.max_concurrency,
                now,
                now,
            ),
        )
        initial_status = (
            IdentityStatus.UNTESTED.value
            if identity.enabled
            else IdentityStatus.DISABLED.value
        )
        self.connection.execute(
            """
            INSERT INTO collector_runtime (identity_id, status, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(identity_id) DO UPDATE SET
                status = CASE
                    WHEN ? = 0 THEN 'disabled'
                    WHEN collector_runtime.status = 'disabled' THEN 'untested'
                    ELSE collector_runtime.status
                END,
                updated_at = excluded.updated_at
            """,
            (
                identity.identity_id,
                initial_status,
                now,
                int(identity.enabled),
            ),
        )

    def upsert_identity(self, identity: CollectorIdentity) -> CollectorIdentity:
        now = _now_text()
        with self._lock, self.connection:
            self._upsert_identity_locked(identity, now)
        return identity

    def save_identity(
        self,
        identity: CollectorIdentity,
        *,
        credentials: CollectorCredentials | None = None,
    ) -> CollectorIdentity:
        """Atomically save metadata and optional replacement credentials.

        ``credentials=None`` preserves an existing envelope. Passing an empty
        credentials model explicitly clears it.
        """

        envelope = (
            self._seal_credentials(identity.identity_id, credentials)
            if credentials is not None and credentials.configured
            else None
        )
        now = _now_text()
        with self._lock, self.connection:
            self._upsert_identity_locked(identity, now)
            if credentials is None:
                return identity
            if envelope is None:
                self._clear_credentials_locked(identity.identity_id, now)
            else:
                self._write_credentials_locked(
                    identity.identity_id,
                    credentials,
                    envelope,
                    now,
                )
        return identity

    def get_identity(self, identity_id: str) -> CollectorIdentity:
        with self._lock:
            row = self._identity_row(identity_id)
            return CollectorIdentity(
                identity_id=row["identity_id"],
                name=row["name"],
                platform=row["platform"],
                auth_mode=row["auth_mode"],
                enabled=bool(row["enabled"]),
                weight=row["weight"],
                request_delay=row["request_delay"],
                max_concurrency=row["max_concurrency"],
            )

    def list_identities(
        self,
        platform: CollectorPlatform | None = None,
    ) -> list[CollectorIdentity]:
        with self._lock:
            if platform is None:
                rows = self.connection.execute(
                    "SELECT identity_id FROM collector_identities ORDER BY platform, identity_id"
                ).fetchall()
            else:
                rows = self.connection.execute(
                    """SELECT identity_id FROM collector_identities
                       WHERE platform = ? ORDER BY identity_id""",
                    (platform.value,),
                ).fetchall()
            return [self.get_identity(row["identity_id"]) for row in rows]

    def delete_identity(self, identity_id: str) -> None:
        with self._lock, self.connection:
            self._identity_row(identity_id)
            assignment_count = self.connection.execute(
                "SELECT COUNT(*) FROM collector_assignments WHERE identity_id = ?",
                (identity_id,),
            ).fetchone()[0]
            policy_rows = self.connection.execute(
                "SELECT default_identity_id, fallback_identity_ids FROM collector_policies"
            ).fetchall()
            policy_references = any(
                row["default_identity_id"] == identity_id
                or identity_id in loads(row["fallback_identity_ids"] or "[]")
                for row in policy_rows
            )
            if assignment_count or policy_references:
                raise IdentityInUseError(
                    "collector identity is referenced by assignments or policy"
                )
            self.connection.execute(
                "DELETE FROM collector_identities WHERE identity_id = ?",
                (identity_id,),
            )

    def _seal_credentials(
        self,
        identity_id: str,
        credentials: CollectorCredentials,
    ) -> bytes:
        require_secure_codec(self.codec)
        plaintext = dumps(
            credentials.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        try:
            return self.codec.seal(plaintext, context=_secret_context(identity_id))
        except SecretCodecError:
            raise
        except Exception:
            raise SecretCodecError("failed to seal collector credentials") from None

    def _write_credentials_locked(
        self,
        identity_id: str,
        credentials: CollectorCredentials,
        envelope: bytes,
        now: str,
    ) -> None:
        self._identity_row(identity_id)
        self.connection.execute(
            """
            INSERT INTO collector_secrets (identity_id, codec_id, envelope, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(identity_id) DO UPDATE SET
                codec_id = excluded.codec_id,
                envelope = excluded.envelope,
                updated_at = excluded.updated_at
            """,
            (identity_id, self.codec.codec_id, envelope, now),
        )
        self.connection.execute(
            """
            UPDATE collector_identities SET
                credential_configured = ?, cookie_configured = ?,
                proxy_configured = ?, user_agent_configured = ?,
                device_id_configured = ?, updated_at = ?
            WHERE identity_id = ?
            """,
            (
                int(credentials.configured),
                int(bool(credentials.cookie)),
                int(bool(credentials.proxy)),
                int(bool(credentials.user_agent)),
                int(bool(credentials.device_id)),
                now,
                identity_id,
            ),
        )

    def write_credentials(
        self,
        identity_id: str,
        credentials: CollectorCredentials,
    ) -> None:
        if not credentials.configured:
            self.clear_credentials(identity_id)
            return
        envelope = self._seal_credentials(identity_id, credentials)
        now = _now_text()
        with self._lock, self.connection:
            self._write_credentials_locked(identity_id, credentials, envelope, now)

    def load_credentials(self, identity_id: str) -> CollectorCredentials:
        """Internal-only credential read; never use this object in API responses."""

        with self._lock:
            self._identity_row(identity_id)
            row = self.connection.execute(
                "SELECT codec_id, envelope FROM collector_secrets WHERE identity_id = ?",
                (identity_id,),
            ).fetchone()
            if row is None:
                return CollectorCredentials()
            require_secure_codec(self.codec)
            if row["codec_id"] != self.codec.codec_id:
                raise SecretCodecUnavailable(
                    f"collector credentials require codec {row['codec_id']}"
                )
            try:
                plaintext = self.codec.open(
                    bytes(row["envelope"]),
                    context=_secret_context(identity_id),
                )
                payload = loads(plaintext.decode("utf-8"))
                return CollectorCredentials.model_validate(payload)
            except SecretCodecError:
                raise
            except Exception:
                # Decoding/validation errors may embed credential values in their
                # repr, so do not retain them as a chained public exception.
                raise SecretCodecError("failed to open collector credentials") from None

    def _clear_credentials_locked(self, identity_id: str, now: str) -> None:
        self._identity_row(identity_id)
        self.connection.execute(
            "DELETE FROM collector_secrets WHERE identity_id = ?",
            (identity_id,),
        )
        self.connection.execute(
            """
            UPDATE collector_identities SET
                credential_configured = 0, cookie_configured = 0,
                proxy_configured = 0, user_agent_configured = 0,
                device_id_configured = 0, updated_at = ?
            WHERE identity_id = ?
            """,
            (now, identity_id),
        )

    def clear_credentials(self, identity_id: str) -> None:
        with self._lock, self.connection:
            self._clear_credentials_locked(identity_id, _now_text())

    def get_runtime(self, identity_id: str) -> CollectorRuntimeState:
        with self._lock:
            self._identity_row(identity_id)
            row = self.connection.execute(
                "SELECT * FROM collector_runtime WHERE identity_id = ?",
                (identity_id,),
            ).fetchone()
            return CollectorRuntimeState(
                identity_id=identity_id,
                status=row["status"],
                active_leases=row["active_leases"],
                consecutive_failures=row["consecutive_failures"],
                total_successes=row["total_successes"],
                total_failures=row["total_failures"],
                risk_failures=row["risk_failures"],
                cooldown_until=row["cooldown_until"],
                last_validated_at=row["last_validated_at"],
                last_success_at=row["last_success_at"],
                last_failure_at=row["last_failure_at"],
                last_error_code=row["last_error_code"],
            )

    def save_runtime(self, state: CollectorRuntimeState) -> None:
        now = _now_text()
        with self._lock, self.connection:
            identity = self.get_identity(state.identity_id)
            status = state.status
            if not identity.enabled:
                status = IdentityStatus.DISABLED
            self.connection.execute(
                """
                UPDATE collector_runtime SET
                    status = ?, active_leases = ?, consecutive_failures = ?,
                    total_successes = ?, total_failures = ?, risk_failures = ?,
                    cooldown_until = ?,
                    last_validated_at = ?, last_success_at = ?, last_failure_at = ?,
                    last_error_code = ?, updated_at = ?
                WHERE identity_id = ?
                """,
                (
                    status.value,
                    state.active_leases,
                    state.consecutive_failures,
                    state.total_successes,
                    state.total_failures,
                    state.risk_failures,
                    state.cooldown_until,
                    state.last_validated_at,
                    state.last_success_at,
                    state.last_failure_at,
                    state.last_error_code,
                    now,
                    state.identity_id,
                ),
            )

    def list_public(
        self,
        platform: CollectorPlatform | None = None,
    ) -> list[CollectorIdentityPublic]:
        query = """
            SELECT i.*, r.status, r.active_leases, r.consecutive_failures,
                   r.total_successes, r.total_failures, r.risk_failures,
                   r.cooldown_until, r.last_validated_at, r.last_success_at,
                   r.last_failure_at, r.last_error_code
            FROM collector_identities AS i
            JOIN collector_runtime AS r ON r.identity_id = i.identity_id
        """
        params: tuple[str, ...] = ()
        if platform is not None:
            query += " WHERE i.platform = ?"
            params = (platform.value,)
        query += " ORDER BY i.platform, i.identity_id"
        with self._lock:
            rows = self.connection.execute(query, params).fetchall()
            return [
                CollectorIdentityPublic(
                    identity_id=row["identity_id"],
                    name=row["name"],
                    platform=row["platform"],
                    auth_mode=row["auth_mode"],
                    enabled=bool(row["enabled"]),
                    weight=row["weight"],
                    request_delay=row["request_delay"],
                    max_concurrency=row["max_concurrency"],
                    credential_configured=bool(row["credential_configured"]),
                    cookie_configured=bool(row["cookie_configured"]),
                    proxy_configured=bool(row["proxy_configured"]),
                    user_agent_configured=bool(row["user_agent_configured"]),
                    device_id_configured=bool(row["device_id_configured"]),
                    route_configured=(
                        row["platform"] == CollectorPlatform.TIKTOK.value
                        and row["auth_mode"] == CollectorAuthMode.ANONYMOUS.value
                    )
                    or bool(row["cookie_configured"]),
                    status=(
                        IdentityStatus.DISABLED
                        if not row["enabled"]
                        else row["status"]
                    ),
                    active_leases=row["active_leases"],
                    consecutive_failures=row["consecutive_failures"],
                    total_successes=row["total_successes"],
                    total_failures=row["total_failures"],
                    risk_failures=row["risk_failures"],
                    cooldown_until=row["cooldown_until"],
                    last_validated_at=row["last_validated_at"],
                    last_success_at=row["last_success_at"],
                    last_failure_at=row["last_failure_at"],
                    last_error_code=row["last_error_code"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )
                for row in rows
            ]

    def route_candidates(
        self,
        platform: CollectorPlatform,
    ) -> list[RouteCandidate]:
        return [
            RouteCandidate(
                identity_id=item.identity_id,
                platform=item.platform,
                enabled=item.enabled,
                weight=item.weight,
                active_leases=item.active_leases,
                max_concurrency=item.max_concurrency,
                status=item.status,
                cooldown_until=item.cooldown_until,
            )
            for item in self.list_public(platform)
        ]

    def _validate_policy_references(self, policy: CollectorPolicy) -> None:
        ids = [policy.default_identity_id, *policy.fallback_identity_ids]
        for identity_id in filter(None, ids):
            if self._identity_platform(identity_id) != policy.platform:
                raise IdentityPlatformError(
                    "policy references an identity from another platform"
                )

    def upsert_policy(self, policy: CollectorPolicy) -> CollectorPolicy:
        now = _now_text()
        with self._lock, self.connection:
            self._validate_policy_references(policy)
            self.connection.execute(
                """
                INSERT INTO collector_policies (
                    platform, strategy, default_identity_id, fallback_identity_ids,
                    global_max_parallel, binding_failure, failure_threshold,
                    cooldown_seconds, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(platform) DO UPDATE SET
                    strategy = excluded.strategy,
                    default_identity_id = excluded.default_identity_id,
                    fallback_identity_ids = excluded.fallback_identity_ids,
                    global_max_parallel = excluded.global_max_parallel,
                    binding_failure = excluded.binding_failure,
                    failure_threshold = excluded.failure_threshold,
                    cooldown_seconds = excluded.cooldown_seconds,
                    updated_at = excluded.updated_at
                """,
                (
                    policy.platform.value,
                    policy.strategy.value,
                    policy.default_identity_id,
                    dumps(policy.fallback_identity_ids, separators=(",", ":")),
                    policy.global_max_parallel,
                    policy.binding_failure.value,
                    policy.failure_threshold,
                    policy.cooldown_seconds,
                    now,
                ),
            )
        return policy

    def get_policy(self, platform: CollectorPlatform) -> CollectorPolicy:
        with self._lock:
            row = self.connection.execute(
                "SELECT * FROM collector_policies WHERE platform = ?",
                (platform.value,),
            ).fetchone()
            if row is None:
                return CollectorPolicy(platform=platform)
            return CollectorPolicy(
                platform=row["platform"],
                strategy=row["strategy"],
                default_identity_id=row["default_identity_id"],
                fallback_identity_ids=loads(row["fallback_identity_ids"] or "[]"),
                global_max_parallel=row["global_max_parallel"],
                binding_failure=row["binding_failure"],
                failure_threshold=row["failure_threshold"],
                cooldown_seconds=row["cooldown_seconds"],
            )

    def _validate_assignment(self, assignment: CollectorAssignment) -> None:
        if self._identity_platform(assignment.identity_id) != assignment.platform:
            raise IdentityPlatformError(
                "assignment references an identity from another platform"
            )

    def upsert_assignments(
        self,
        assignments: Iterable[CollectorAssignment],
    ) -> list[CollectorAssignment]:
        items = list(assignments)
        now = _now_text()
        with self._lock, self.connection:
            for item in items:
                self._validate_assignment(item)
                self.connection.execute(
                    """
                    INSERT INTO collector_assignments (
                        platform, target_type, target_key, identity_id, source, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(platform, target_type, target_key) DO UPDATE SET
                        identity_id = excluded.identity_id,
                        source = excluded.source,
                        updated_at = excluded.updated_at
                    """,
                    (
                        item.platform.value,
                        item.target_type,
                        item.target_key,
                        item.identity_id,
                        item.source.value,
                        now,
                    ),
                )
        return [item.model_copy(update={"updated_at": now}) for item in items]

    def get_assignment(
        self,
        platform: CollectorPlatform,
        target_type: str,
        target_key: str,
    ) -> CollectorAssignment | None:
        with self._lock:
            row = self.connection.execute(
                """
                SELECT * FROM collector_assignments
                WHERE platform = ? AND target_type = ? AND target_key = ?
                """,
                (platform.value, target_type, target_key),
            ).fetchone()
            if row is None:
                return None
            return CollectorAssignment(**dict(row))

    def list_assignments(
        self,
        platform: CollectorPlatform | None = None,
        *,
        target_type: str | None = None,
    ) -> list[CollectorAssignment]:
        clauses: list[str] = []
        params: list[str] = []
        if platform is not None:
            clauses.append("platform = ?")
            params.append(platform.value)
        if target_type is not None:
            clauses.append("target_type = ?")
            params.append(target_type)
        query = "SELECT * FROM collector_assignments"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY platform, target_type, target_key"
        with self._lock:
            rows = self.connection.execute(query, tuple(params)).fetchall()
            return [CollectorAssignment(**dict(row)) for row in rows]

    def list_assignments_page(
        self,
        platform: CollectorPlatform | None = None,
        *,
        target_type: str | None = None,
        search: str = "",
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[CollectorAssignment], int, int, int]:
        """Return one stable assignment page and its pagination metadata."""

        page = max(1, int(page))
        page_size = max(1, min(int(page_size), 200))
        clauses: list[str] = []
        params: list[str] = []
        if platform is not None:
            clauses.append("platform = ?")
            params.append(platform.value)
        if target_type is not None:
            clauses.append("target_type = ?")
            params.append(target_type)
        normalized_search = str(search or "").strip()
        if normalized_search:
            clauses.append(
                "("
                "instr(lower(target_key), lower(?)) > 0 OR "
                "instr(lower(identity_id), lower(?)) > 0 OR "
                "instr(lower(source), lower(?)) > 0"
                ")"
            )
            params.extend([normalized_search] * 3)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self._lock:
            total = int(
                self.connection.execute(
                    f"SELECT COUNT(*) FROM collector_assignments{where}",
                    tuple(params),
                ).fetchone()[0]
            )
            pages = max(1, (total + page_size - 1) // page_size)
            page = min(page, pages)
            offset = (page - 1) * page_size
            rows = self.connection.execute(
                "SELECT * FROM collector_assignments"
                f"{where} ORDER BY platform, target_type, target_key LIMIT ? OFFSET ?",
                (*params, page_size, offset),
            ).fetchall()
            return (
                [CollectorAssignment(**dict(row)) for row in rows],
                total,
                page,
                pages,
            )

    def delete_assignment(
        self,
        platform: CollectorPlatform,
        target_type: str,
        target_key: str,
    ) -> bool:
        with self._lock, self.connection:
            cursor = self.connection.execute(
                """
                DELETE FROM collector_assignments
                WHERE platform = ? AND target_type = ? AND target_key = ?
                """,
                (platform.value, target_type, target_key),
            )
            return cursor.rowcount > 0

    def apply_legacy_migration(self, result: LegacyMigrationResult) -> bool:
        """Persist a pure migration result as one transaction."""

        if not result.migrated:
            return False
        sealed: dict[str, bytes] = {}
        for identity in result.identities:
            credential = result.credentials.get(identity.identity_id)
            if credential and credential.configured:
                sealed[identity.identity_id] = self._seal_credentials(
                    identity.identity_id,
                    credential,
                )
        now = _now_text()
        with self._lock, self.connection:
            for identity in result.identities:
                self._upsert_identity_locked(identity, now)
                credential = result.credentials.get(identity.identity_id)
                if credential and credential.configured:
                    self._write_credentials_locked(
                        identity.identity_id,
                        credential,
                        sealed[identity.identity_id],
                        now,
                    )
            for policy in result.policies:
                self._validate_policy_references(policy)
                self.connection.execute(
                    """
                    INSERT OR REPLACE INTO collector_policies (
                        platform, strategy, default_identity_id, fallback_identity_ids,
                        global_max_parallel, binding_failure, failure_threshold,
                        cooldown_seconds, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        policy.platform.value,
                        policy.strategy.value,
                        policy.default_identity_id,
                        dumps(policy.fallback_identity_ids, separators=(",", ":")),
                        policy.global_max_parallel,
                        policy.binding_failure.value,
                        policy.failure_threshold,
                        policy.cooldown_seconds,
                        now,
                    ),
                )
        return True
