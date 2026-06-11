"""Player manager lifecycle and timeout tests."""

from __future__ import annotations

import time

import pytest

from neobatista.player import PlayerManager
from tests.fakes import FakeResolver, FakeSink, FakeVoice


@pytest.mark.asyncio
async def test_manager_create_remove_and_close() -> None:
    manager = PlayerManager(
        FakeResolver(),
        default_volume=50,
        idle_timeout_seconds=30,
        alone_timeout_seconds=15,
    )
    first = manager.get_or_create(1)
    assert manager.get_or_create(1) is first
    assert manager.get(2) is None

    voice = FakeVoice()
    await first.attach(voice, FakeSink())  # type: ignore[arg-type]
    await manager.remove(1)
    assert manager.get(1) is None
    assert not voice.connected

    manager.start()
    manager.start()
    await manager.close()


@pytest.mark.asyncio
async def test_manager_disconnect_decisions() -> None:
    manager = PlayerManager(
        FakeResolver(),
        default_volume=50,
        idle_timeout_seconds=30,
        alone_timeout_seconds=15,
    )
    player = manager.get_or_create(1)
    assert await manager._should_disconnect(player, time.monotonic())

    voice = FakeVoice()
    await player.attach(voice, FakeSink())  # type: ignore[arg-type]
    now = time.monotonic()
    player.last_activity = now
    assert not await manager._should_disconnect(player, now)

    player.last_activity = now - 31
    assert await manager._should_disconnect(player, now)

    player.last_activity = now
    player.alone_since = now - 16
    assert await manager._should_disconnect(player, now)
    await manager.close()
