"""Queue and worker concurrency tests."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

import discord
import pytest

from neobatista.errors import PlayerError, QueuePositionError
from neobatista.models import MediaSource, Track
from neobatista.player import GuildPlayer
from tests.fakes import FakeResolver, FakeSink, FakeVoice


def track(title: str) -> Track:
    return Track(
        query=title,
        title=title,
        webpage_url=f"https://example.invalid/{title}",
        duration_seconds=60,
        requester_id=1,
        requester_name="tester",
        source=MediaSource.SEARCH,
    )


class FakeAudioSource(discord.AudioSource):
    """No-op audio source accepted by the typed player boundary."""

    def read(self) -> bytes:
        return b""

    def is_opus(self) -> bool:
        return False


async def wait_until(predicate: Callable[[], bool], limit: float = 1) -> None:
    async def poll() -> None:
        while not predicate():  # noqa: ASYNC110 - deterministic fake callback polling
            await asyncio.sleep(0)

    await asyncio.wait_for(poll(), limit)


@pytest.mark.asyncio
async def test_queue_operations() -> None:
    player = GuildPlayer(1, FakeResolver(), default_volume=50)
    await player.enqueue([track("a"), track("b"), track("c")])

    removed = await player.remove(2)
    moved = await player.move(2, 1)

    assert removed.title == "b"
    assert moved.title == "c"
    assert [item.title for item in await player.snapshot()] == ["c", "a"]
    assert await player.clear() == 2


@pytest.mark.asyncio
async def test_enqueue_enforces_limit_inside_lock() -> None:
    player = GuildPlayer(1, FakeResolver(), default_volume=50)

    first, second = await asyncio.gather(
        player.enqueue([track("a"), track("b")], maximum_size=3),
        player.enqueue([track("c"), track("d")], maximum_size=3),
    )

    assert len(first) + len(second) == 3
    assert len(await player.snapshot()) == 3
    with pytest.raises(PlayerError):
        await player.enqueue([track("e")], maximum_size=3)


@pytest.mark.asyncio
async def test_invalid_queue_positions() -> None:
    player = GuildPlayer(1, FakeResolver(), default_volume=50)
    await player.enqueue([track("a")])

    for position in (0, -1, 2):
        with pytest.raises(QueuePositionError):
            await player.remove(position)
    with pytest.raises(QueuePositionError):
        await player.move(1, 2)


@pytest.mark.asyncio
async def test_shuffle_requires_two_tracks() -> None:
    player = GuildPlayer(1, FakeResolver(), default_volume=50)
    await player.enqueue([track("a")])

    with pytest.raises(PlayerError):
        await player.shuffle()


@pytest.mark.asyncio
async def test_worker_serializes_playback_and_skip_advances_once() -> None:
    resolver = FakeResolver()
    voice = FakeVoice()
    sink = FakeSink()
    player = GuildPlayer(
        1,
        resolver,
        default_volume=50,
        audio_factory=lambda stream, volume: FakeAudioSource(),
    )
    await player.attach(voice, sink)  # type: ignore[arg-type]
    await asyncio.gather(
        player.enqueue([track("a")]),
        player.enqueue([track("b"), track("c")]),
    )
    await wait_until(lambda: voice.play_count == 1)

    player.skip()
    await wait_until(lambda: voice.play_count == 2)

    assert resolver.resolved[:2] == ["a", "b"]
    assert [item.title for item in await player.snapshot()] == ["c"]
    voice.finish()
    await wait_until(lambda: voice.play_count == 3)
    voice.finish()
    await player.disconnect()


@pytest.mark.asyncio
async def test_failed_track_continues_to_next() -> None:
    resolver = FakeResolver(fail_titles={"broken"})
    voice = FakeVoice()
    player = GuildPlayer(
        1,
        resolver,
        default_volume=50,
        audio_factory=lambda stream, volume: FakeAudioSource(),
    )
    await player.attach(voice, FakeSink())  # type: ignore[arg-type]
    await player.enqueue([track("broken"), track("good")])

    await wait_until(lambda: voice.play_count == 1)
    assert resolver.resolved == ["broken", "good"]
    voice.finish()
    await player.disconnect()


@pytest.mark.asyncio
async def test_pause_is_active_and_stop_clears_queue() -> None:
    voice = FakeVoice()
    player = GuildPlayer(
        1,
        FakeResolver(),
        default_volume=50,
        audio_factory=lambda stream, volume: FakeAudioSource(),
    )
    await player.attach(voice, FakeSink())  # type: ignore[arg-type]
    await player.enqueue([track("a"), track("b")])
    await wait_until(lambda: voice.play_count == 1)

    player.pause()
    assert player.is_active
    player.resume()
    await player.stop()

    assert not await player.snapshot()
    await player.disconnect()


@pytest.mark.asyncio
async def test_volume_validation_and_disconnect() -> None:
    player = GuildPlayer(1, FakeResolver(), default_volume=50)
    voice = FakeVoice()
    await player.attach(voice, FakeSink())  # type: ignore[arg-type]

    player.set_volume(80)
    assert player.volume == 80
    with pytest.raises(PlayerError):
        player.set_volume(101)

    await player.disconnect()
    assert not voice.connected
