"""Small Discord and resolver fakes for deterministic unit tests."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ClassVar

from neobatista.models import Stream, Track


class FakeResolver:
    """Resolve each track to a predictable in-memory stream."""

    def __init__(self, *, fail_titles: set[str] | None = None) -> None:
        self.resolved: list[str] = []
        self.fail_titles = fail_titles or set()

    async def expand(
        self,
        query: str,
        *,
        requester_id: int,
        requester_name: str,
        limit: int,
    ) -> list[Track]:
        raise NotImplementedError

    async def resolve_stream(self, track: Track) -> Stream:
        self.resolved.append(track.title)
        if track.title in self.fail_titles:
            raise RuntimeError("resolution failed")
        return Stream(
            url=f"https://stream.invalid/{track.title}",
            title=track.title,
            webpage_url=track.webpage_url,
            duration_seconds=track.duration_seconds,
        )


class FakeChannel:
    """Voice channel with configurable membership."""

    id = 42
    members: ClassVar[list[Any]] = []


class FakeVoice:
    """Voice client whose completion callback is controlled by tests."""

    def __init__(self) -> None:
        self.channel = FakeChannel()
        self.source: Any = None
        self.after: Callable[[Exception | None], None] | None = None
        self.connected = True
        self.playing = False
        self.paused = False
        self.play_count = 0

    def is_connected(self) -> bool:
        return self.connected

    def is_playing(self) -> bool:
        return self.playing

    def is_paused(self) -> bool:
        return self.paused

    def play(
        self,
        source: Any,
        *,
        after: Callable[[Exception | None], None],
    ) -> None:
        if self.playing:
            raise RuntimeError("already playing")
        self.source = source
        self.after = after
        self.playing = True
        self.play_count += 1

    def finish(self, error: Exception | None = None) -> None:
        callback, self.after = self.after, None
        self.playing = False
        self.paused = False
        if callback:
            callback(error)

    def stop(self) -> None:
        self.finish()

    def pause(self) -> None:
        self.playing = False
        self.paused = True

    def resume(self) -> None:
        self.paused = False
        self.playing = True

    async def disconnect(self, *, force: bool = False) -> None:
        self.connected = False


class FakeSink:
    """Collect playback notifications."""

    def __init__(self) -> None:
        self.messages: list[str] = []

    async def send(self, content: str | None = None, **kwargs: object) -> object:
        if content:
            self.messages.append(content)
        return object()
