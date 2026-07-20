from __future__ import annotations

from asyncio import CancelledError, Lock, Semaphore, create_task, shield
from dataclasses import dataclass
from time import monotonic


class LeaseConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class LeaseSnapshot:
    identity_id: str
    active: int
    limit: int
    waiting: int = 0


class _LeaseSlot:
    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.semaphore = Semaphore(limit)
        self.active = 0
        self.waiting = 0


class IdentityLease:
    """Cancellation-safe async lease for one collector identity."""

    def __init__(self, manager: "IdentityLeaseManager", identity_id: str) -> None:
        self._manager = manager
        self.identity_id = identity_id
        self.acquired_at: float | None = None
        self._acquired = False

    async def __aenter__(self) -> "IdentityLease":
        if self._acquired:
            raise LeaseConfigurationError("collector lease cannot be entered twice")
        await self._manager._acquire(self.identity_id)
        self._acquired = True
        self.acquired_at = monotonic()
        return self

    async def __aexit__(self, exc_type, exc_value, traceback) -> None:
        if self._acquired:
            release_task = create_task(self._manager._release(self.identity_id))
            try:
                await shield(release_task)
            except CancelledError:
                # A second cancellation must not leak an acquired identity slot.
                await release_task
                raise
            finally:
                self._acquired = False


class IdentityLeaseManager:
    def __init__(self) -> None:
        self._slots: dict[str, _LeaseSlot] = {}
        self._state_lock = Lock()

    async def configure(self, identity_id: str, max_concurrency: int = 1) -> None:
        if not identity_id:
            raise LeaseConfigurationError("identity_id is required")
        # Per-identity models cap this at 16; platform-wide policy gates may
        # intentionally be higher when many isolated identities participate.
        if not 1 <= int(max_concurrency) <= 64:
            raise LeaseConfigurationError("max_concurrency must be between 1 and 64")
        max_concurrency = int(max_concurrency)
        async with self._state_lock:
            existing = self._slots.get(identity_id)
            if existing:
                # Reapplying the effective configuration is intentionally a
                # no-op. Replacing the Semaphore would strand tasks that were
                # already awakened or queued on the old slot.
                if existing.limit == max_concurrency:
                    return
                if existing.active or existing.waiting:
                    raise LeaseConfigurationError(
                        "cannot change lease limit while identity is active or waiting"
                    )
            self._slots[identity_id] = _LeaseSlot(max_concurrency)

    async def remove(self, identity_id: str) -> None:
        async with self._state_lock:
            slot = self._slots.get(identity_id)
            if slot and (slot.active or slot.waiting):
                raise LeaseConfigurationError(
                    "cannot remove an active or waiting identity lease"
                )
            self._slots.pop(identity_id, None)

    def lease(self, identity_id: str) -> IdentityLease:
        if identity_id not in self._slots:
            raise LeaseConfigurationError(
                f"collector identity lease is not configured: {identity_id}"
            )
        return IdentityLease(self, identity_id)

    async def _acquire(self, identity_id: str) -> None:
        async with self._state_lock:
            slot = self._slots.get(identity_id)
            if slot is None:
                raise LeaseConfigurationError(
                    f"collector identity lease is not configured: {identity_id}"
                )
            slot.waiting += 1
        try:
            await slot.semaphore.acquire()
        except BaseException:
            # asyncio tasks only interleave at await points; this synchronous
            # rollback cannot race configure/remove on the same event loop.
            slot.waiting -= 1
            raise

        # Do not await between the semaphore wake-up and state promotion. This
        # closes the active=0/waiter-awakened window that previously allowed a
        # configure call to replace the slot under the waiter.
        slot.waiting -= 1
        current = self._slots.get(identity_id)
        if current is not slot:
            slot.semaphore.release()
            raise LeaseConfigurationError("collector identity lease was reconfigured")
        slot.active += 1

    async def _release(self, identity_id: str) -> None:
        async with self._state_lock:
            slot = self._slots.get(identity_id)
            if slot is None or slot.active <= 0:
                raise LeaseConfigurationError("collector identity lease is not active")
            slot.active -= 1
            slot.semaphore.release()

    async def snapshot(self, identity_id: str) -> LeaseSnapshot:
        async with self._state_lock:
            slot = self._slots.get(identity_id)
            if slot is None:
                raise LeaseConfigurationError(
                    f"collector identity lease is not configured: {identity_id}"
                )
            return LeaseSnapshot(
                identity_id,
                slot.active,
                slot.limit,
                slot.waiting,
            )
