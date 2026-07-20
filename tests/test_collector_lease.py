import asyncio

import pytest

from src.collector import IdentityLeaseManager, LeaseConfigurationError


@pytest.mark.asyncio
async def test_single_identity_lease_serializes_work_and_releases_after_exception():
    manager = IdentityLeaseManager()
    await manager.configure("tt-main", 1)
    first_entered = asyncio.Event()
    release_first = asyncio.Event()
    second_entered = asyncio.Event()

    async def first():
        async with manager.lease("tt-main"):
            first_entered.set()
            await release_first.wait()

    async def second():
        async with manager.lease("tt-main"):
            second_entered.set()

    first_task = asyncio.create_task(first())
    await first_entered.wait()
    second_task = asyncio.create_task(second())
    await asyncio.sleep(0)
    assert second_entered.is_set() is False

    release_first.set()
    await asyncio.gather(first_task, second_task)
    assert second_entered.is_set() is True
    assert (await manager.snapshot("tt-main")).active == 0

    with pytest.raises(RuntimeError):
        async with manager.lease("tt-main"):
            raise RuntimeError("boom")
    assert (await manager.snapshot("tt-main")).active == 0


@pytest.mark.asyncio
async def test_canceled_waiter_does_not_consume_or_leak_lease():
    manager = IdentityLeaseManager()
    await manager.configure("tt-main", 1)

    async with manager.lease("tt-main"):
        waiter = asyncio.create_task(manager.lease("tt-main").__aenter__())
        await asyncio.sleep(0)
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter
        assert (await manager.snapshot("tt-main")).active == 1

    assert (await manager.snapshot("tt-main")).active == 0


@pytest.mark.asyncio
async def test_active_lease_limit_cannot_be_reconfigured_or_removed():
    manager = IdentityLeaseManager()
    await manager.configure("tt-main", 1)
    async with manager.lease("tt-main"):
        with pytest.raises(LeaseConfigurationError, match="change"):
            await manager.configure("tt-main", 2)
        with pytest.raises(LeaseConfigurationError, match="remove"):
            await manager.remove("tt-main")


@pytest.mark.asyncio
async def test_canceling_lease_holder_releases_slot():
    manager = IdentityLeaseManager()
    await manager.configure("tt-main", 1)
    entered = asyncio.Event()

    async def holder():
        async with manager.lease("tt-main"):
            entered.set()
            await asyncio.Event().wait()

    task = asyncio.create_task(holder())
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert (await manager.snapshot("tt-main")).active == 0


@pytest.mark.asyncio
async def test_platform_gate_accepts_policy_limit_above_identity_limit():
    manager = IdentityLeaseManager()
    await manager.configure("platform:douyin", 64)

    assert (await manager.snapshot("platform:douyin")).limit == 64


@pytest.mark.asyncio
async def test_same_limit_configure_never_replaces_slot_under_awakened_waiter():
    manager = IdentityLeaseManager()
    await manager.configure("tt-main", 1)
    original_slot = manager._slots["tt-main"]
    holder = manager.lease("tt-main")
    await holder.__aenter__()
    waiter_entered = asyncio.Event()

    async def waiter():
        async with manager.lease("tt-main"):
            waiter_entered.set()

    waiter_task = asyncio.create_task(waiter())
    while (await manager.snapshot("tt-main")).waiting != 1:
        await asyncio.sleep(0)

    # Deterministically recreate the old active=0 / awakened-waiter window.
    # Queue configure on the state lock first, then wake the old semaphore
    # waiter before releasing that lock.
    await manager._state_lock.acquire()
    configure_task = asyncio.create_task(manager.configure("tt-main", 1))
    await asyncio.sleep(0)
    original_slot.active -= 1
    original_slot.semaphore.release()
    holder._acquired = False
    manager._state_lock.release()

    await configure_task
    await waiter_task
    assert waiter_entered.is_set() is True
    assert manager._slots["tt-main"] is original_slot
    snapshot = await manager.snapshot("tt-main")
    assert snapshot.active == 0
    assert snapshot.waiting == 0


@pytest.mark.asyncio
async def test_waiting_lease_blocks_limit_change_and_remove():
    manager = IdentityLeaseManager()
    await manager.configure("tt-main", 1)

    async with manager.lease("tt-main"):
        waiter = asyncio.create_task(manager.lease("tt-main").__aenter__())
        while (await manager.snapshot("tt-main")).waiting != 1:
            await asyncio.sleep(0)

        with pytest.raises(LeaseConfigurationError, match="active or waiting"):
            await manager.configure("tt-main", 2)
        with pytest.raises(LeaseConfigurationError, match="active or waiting"):
            await manager.remove("tt-main")

        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter
        assert (await manager.snapshot("tt-main")).waiting == 0
