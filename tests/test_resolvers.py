"""Provider parsing and routing tests with no external network calls."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ParamSpec, TypeVar

import pytest
from pytest import MonkeyPatch
from yt_dlp.utils import DownloadError

from neobatista.errors import MediaResolutionError
from neobatista.models import MediaSource, Stream, Track
from neobatista.resolvers import (
    CompositeResolver,
    SpotifyResolver,
    YTDLPResolver,
)

P = ParamSpec("P")
T = TypeVar("T")


@pytest.fixture(autouse=True)
def run_blocking_calls_inline(monkeypatch: MonkeyPatch) -> None:
    """Avoid leaving executor threads behind in the constrained test sandbox."""

    async def to_thread(
        function: Callable[P, T], /, *args: P.args, **kwargs: P.kwargs
    ) -> T:
        return function(*args, **kwargs)

    monkeypatch.setattr("neobatista.resolvers.asyncio.to_thread", to_thread)


def queued_track(title: str = "queued") -> Track:
    return Track(
        query="https://example.invalid/watch",
        title=title,
        webpage_url=None,
        duration_seconds=None,
        requester_id=1,
        requester_name="tester",
        source=MediaSource.URL,
    )


@pytest.mark.asyncio
async def test_ytdlp_expand_search_and_playlist(monkeypatch: MonkeyPatch) -> None:
    resolver = YTDLPResolver()
    search_data = {
        "entries": [
            {
                "id": "abc",
                "title": "Search result",
                "duration": 61,
                "extractor_key": "Youtube",
            }
        ]
    }
    monkeypatch.setattr(resolver, "_extract", lambda query, options: search_data)

    tracks = await resolver.expand(
        "some words", requester_id=7, requester_name="Neo", limit=10
    )

    assert tracks == [
        Track(
            query="https://www.youtube.com/watch?v=abc",
            title="Search result",
            webpage_url="https://www.youtube.com/watch?v=abc",
            duration_seconds=61,
            requester_id=7,
            requester_name="Neo",
            source=MediaSource.SEARCH,
        )
    ]

    playlist_data = {
        "entries": [
            {"url": f"https://video/{index}", "title": str(index)} for index in range(3)
        ]
    }
    monkeypatch.setattr(resolver, "_extract", lambda query, options: playlist_data)
    playlist = await resolver.expand(
        "https://playlist.invalid/list",
        requester_id=1,
        requester_name="Neo",
        limit=2,
    )
    assert [item.title for item in playlist] == ["0", "1"]


@pytest.mark.asyncio
async def test_ytdlp_expand_errors(monkeypatch: MonkeyPatch) -> None:
    resolver = YTDLPResolver()

    def fail(query: str, options: object) -> object:
        raise DownloadError("failed")

    monkeypatch.setattr(resolver, "_extract", fail)
    with pytest.raises(MediaResolutionError):
        await resolver.expand("missing", requester_id=1, requester_name="n", limit=1)

    monkeypatch.setattr(resolver, "_extract", lambda query, options: {"entries": []})
    with pytest.raises(MediaResolutionError):
        await resolver.expand("empty", requester_id=1, requester_name="n", limit=1)


@pytest.mark.asyncio
async def test_ytdlp_resolve_stream(monkeypatch: MonkeyPatch) -> None:
    resolver = YTDLPResolver()
    monkeypatch.setattr(
        resolver,
        "_extract",
        lambda query, options: {
            "url": "https://stream.invalid/audio",
            "title": "Resolved",
            "webpage_url": "https://page.invalid/video",
            "duration": 90.8,
        },
    )

    stream = await resolver.resolve_stream(queued_track())

    assert stream.title == "Resolved"
    assert stream.duration_seconds == 90
    assert stream.url == "https://stream.invalid/audio"

    monkeypatch.setattr(resolver, "_extract", lambda query, options: {})
    with pytest.raises(MediaResolutionError):
        await resolver.resolve_stream(queued_track())


def test_ytdlp_helpers() -> None:
    resolver = YTDLPResolver()

    assert resolver._entries({"title": "single"}) == [{"title": "single"}]
    assert resolver._webpage_url({"original_url": "https://original"}) == (
        "https://original"
    )
    assert resolver._webpage_url({"id": "id", "extractor_key": "Youtube"}) == (
        "https://www.youtube.com/watch?v=id"
    )
    assert resolver._webpage_url({}) is None
    assert resolver._duration({"duration": "unknown"}) is None


class FakeSpotifyClient:
    """Spotify client with one track and a two-page playlist."""

    def track(self, url: str) -> dict[str, Any]:
        return spotify_item("One")

    def playlist_items(self, url: str, *, limit: int) -> dict[str, Any]:
        return {"items": [{"track": spotify_item("One")}], "next": "page-2"}

    def next(self, result: dict[str, Any]) -> dict[str, Any]:
        return {
            "items": [{"track": spotify_item("Two")}, {"track": None}],
            "next": None,
        }


def spotify_item(name: str) -> dict[str, Any]:
    return {
        "name": name,
        "artists": [{"name": "Artist"}],
        "duration_ms": 123000,
        "external_urls": {"spotify": f"https://spotify/{name}"},
    }


def spotify_resolver() -> SpotifyResolver:
    resolver = object.__new__(SpotifyResolver)
    resolver._client = FakeSpotifyClient()
    return resolver


@pytest.mark.asyncio
async def test_spotify_track_and_playlist() -> None:
    resolver = spotify_resolver()

    single = await resolver.expand(
        "https://open.spotify.com/track/id",
        requester_id=1,
        requester_name="Neo",
        limit=10,
    )
    playlist = await resolver.expand(
        "https://open.spotify.com/playlist/id",
        requester_id=1,
        requester_name="Neo",
        limit=10,
    )

    assert single[0].query == "ytsearch1:One Artist audio"
    assert single[0].duration_seconds == 123
    assert [item.title for item in playlist] == [
        "One — Artist",
        "Two — Artist",
    ]


@pytest.mark.asyncio
async def test_spotify_rejects_unknown_url() -> None:
    with pytest.raises(MediaResolutionError):
        await spotify_resolver().expand(
            "https://open.spotify.com/album/id",
            requester_id=1,
            requester_name="Neo",
            limit=10,
        )


class StubYouTube:
    def __init__(self) -> None:
        self.expanded = False

    async def expand(self, query: str, **kwargs: object) -> list[Track]:
        self.expanded = True
        return [queued_track()]

    async def resolve_stream(self, track: Track) -> Stream:
        return Stream("url", track.title, None, None)


class StubSpotify:
    async def expand(self, query: str, **kwargs: object) -> list[Track]:
        return [queued_track("spotify")]


@pytest.mark.asyncio
async def test_composite_routing() -> None:
    youtube = StubYouTube()
    resolver = CompositeResolver(youtube, StubSpotify())  # type: ignore[arg-type]

    normal = await resolver.expand("words", requester_id=1, requester_name="n", limit=1)
    spotify = await resolver.expand(
        "https://open.spotify.com/track/id",
        requester_id=1,
        requester_name="n",
        limit=1,
    )

    assert normal[0].title == "queued"
    assert youtube.expanded
    assert spotify[0].title == "spotify"

    disabled = CompositeResolver(youtube, None)  # type: ignore[arg-type]
    with pytest.raises(MediaResolutionError):
        await disabled.expand(
            "https://open.spotify.com/track/id",
            requester_id=1,
            requester_name="n",
            limit=1,
        )
