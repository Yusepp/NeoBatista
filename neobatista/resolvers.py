"""Blocking media APIs wrapped behind async, typed resolver services."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable, Mapping
from itertools import islice
from typing import Any, Protocol, cast
from urllib.parse import urlparse

import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from .errors import MediaResolutionError
from .models import MediaSource, Stream, Track

LOGGER = logging.getLogger(__name__)


class MediaResolver(Protocol):
    """Interface consumed by guild playback workers and commands."""

    async def expand(
        self,
        query: str,
        *,
        requester_id: int,
        requester_name: str,
        limit: int,
    ) -> list[Track]:
        """Expand a query or playlist into stable queue entries."""

    async def resolve_stream(self, track: Track) -> Stream:
        """Resolve a fresh playable stream URL for one queue entry."""


class YTDLPResolver:
    """Resolve searches and supported URLs through yt-dlp."""

    _metadata_options: Mapping[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": False,
        "extract_flat": "in_playlist",
        "skip_download": True,
        "default_search": "ytsearch1",
        "socket_timeout": 20,
        "js_runtimes": {"node": {}},
    }
    _stream_options: Mapping[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "skip_download": True,
        "format": "bestaudio/best",
        "default_search": "ytsearch1",
        "socket_timeout": 20,
        "js_runtimes": {"node": {}},
    }

    async def expand(
        self,
        query: str,
        *,
        requester_id: int,
        requester_name: str,
        limit: int,
    ) -> list[Track]:
        """Extract queue metadata without downloading media."""
        try:
            data = await asyncio.to_thread(self._extract, query, self._metadata_options)
        except DownloadError as exc:
            raise MediaResolutionError(
                "No pude encontrar eso. Hasta la bomba tiene límites."
            ) from exc

        entries = self._entries(data, limit=limit)
        tracks = [
            self._to_track(
                entry,
                fallback_query=query,
                requester_id=requester_id,
                requester_name=requester_name,
            )
            for entry in entries
            if entry
        ]
        if not tracks:
            raise MediaResolutionError("No apareció ningún tema reproducible.")
        return tracks

    async def resolve_stream(self, track: Track) -> Stream:
        """Resolve an expiring media URL immediately before FFmpeg starts."""
        try:
            data = await asyncio.to_thread(
                self._extract, track.query, self._stream_options
            )
        except DownloadError as exc:
            raise MediaResolutionError(f"No pude preparar **{track.title}**.") from exc

        entries = self._entries(data, limit=1)
        if not entries:
            raise MediaResolutionError(f"**{track.title}** ya no está disponible.")
        entry = entries[0]
        stream_url = entry.get("url")
        if not isinstance(stream_url, str) or not stream_url:
            raise MediaResolutionError(f"**{track.title}** no entregó audio.")
        return Stream(
            url=stream_url,
            title=str(entry.get("title") or track.title),
            webpage_url=self._webpage_url(entry) or track.webpage_url,
            duration_seconds=self._duration(entry) or track.duration_seconds,
        )

    @staticmethod
    def _extract(query: str, options: Mapping[str, Any]) -> Mapping[str, Any]:
        with YoutubeDL(dict(options)) as ydl:
            result = ydl.extract_info(query, download=False)
            if result is None:
                raise MediaResolutionError("yt-dlp returned no media information.")
            return cast(Mapping[str, Any], result)

    @staticmethod
    def _entries(
        data: Mapping[str, Any],
        *,
        limit: int | None = None,
    ) -> list[Mapping[str, Any]]:
        raw_entries = data.get("entries")
        if isinstance(raw_entries, Iterable) and not isinstance(
            raw_entries, (str, bytes, Mapping)
        ):
            entries = raw_entries if limit is None else islice(raw_entries, limit)
            return [
                cast(Mapping[str, Any], entry)
                for entry in entries
                if isinstance(entry, Mapping)
            ]
        return [data]

    def _to_track(
        self,
        entry: Mapping[str, Any],
        *,
        fallback_query: str,
        requester_id: int,
        requester_name: str,
    ) -> Track:
        webpage_url = self._webpage_url(entry)
        query = webpage_url or str(entry.get("url") or fallback_query)
        source = (
            MediaSource.YOUTUBE
            if "youtube" in (entry.get("extractor_key") or "").lower()
            else MediaSource.URL
        )
        if not urlparse(fallback_query).scheme:
            source = MediaSource.SEARCH
        return Track(
            query=query,
            title=str(entry.get("title") or "Tema misterioso"),
            webpage_url=webpage_url,
            duration_seconds=self._duration(entry),
            requester_id=requester_id,
            requester_name=requester_name,
            source=source,
        )

    @staticmethod
    def _webpage_url(entry: Mapping[str, Any]) -> str | None:
        for key in ("webpage_url", "original_url"):
            value = entry.get(key)
            if isinstance(value, str) and value:
                return value
        entry_id = entry.get("id")
        extractor = str(entry.get("extractor_key") or "").lower()
        if isinstance(entry_id, str) and "youtube" in extractor:
            return f"https://www.youtube.com/watch?v={entry_id}"
        return None

    @staticmethod
    def _duration(entry: Mapping[str, Any]) -> int | None:
        value = entry.get("duration")
        return int(value) if isinstance(value, (int, float)) else None


class SpotifyResolver:
    """Convert Spotify metadata into yt-dlp search-backed queue entries."""

    def __init__(self, client_id: str, client_secret: str) -> None:
        auth = SpotifyClientCredentials(
            client_id=client_id, client_secret=client_secret
        )
        self._client = spotipy.Spotify(auth_manager=auth, requests_timeout=20)

    async def expand(
        self,
        url: str,
        *,
        requester_id: int,
        requester_name: str,
        limit: int,
    ) -> list[Track]:
        """Fetch a Spotify track or playlist, including all playlist pages."""
        try:
            return await asyncio.to_thread(
                self._expand_sync,
                url,
                requester_id,
                requester_name,
                limit,
            )
        except spotipy.SpotifyException as exc:
            raise MediaResolutionError(
                "Spotify no quiso colaborar con LA **NEO**BOMBA."
            ) from exc

    def _expand_sync(
        self,
        url: str,
        requester_id: int,
        requester_name: str,
        limit: int,
    ) -> list[Track]:
        if "/track/" in url:
            item = self._client.track(url)
            return [self._to_track(item, url, requester_id, requester_name)]
        if "/playlist/" not in url:
            raise MediaResolutionError("Ese enlace de Spotify no es track ni playlist.")

        result = self._client.playlist_items(url, limit=min(limit, 100))
        items: list[Mapping[str, Any]] = list(result.get("items", []))
        while result.get("next") and len(items) < limit:
            result = self._client.next(result)
            items.extend(result.get("items", []))
        tracks = []
        for wrapper in items[:limit]:
            item = wrapper.get("track") if isinstance(wrapper, Mapping) else None
            if isinstance(item, Mapping):
                tracks.append(self._to_track(item, url, requester_id, requester_name))
        if not tracks:
            raise MediaResolutionError("La playlist de Spotify está vacía.")
        return tracks

    @staticmethod
    def _to_track(
        item: Mapping[str, Any],
        fallback_url: str,
        requester_id: int,
        requester_name: str,
    ) -> Track:
        artists = ", ".join(
            str(artist.get("name"))
            for artist in item.get("artists", [])
            if isinstance(artist, Mapping) and artist.get("name")
        )
        title = str(item.get("name") or "Tema misterioso")
        search = f"ytsearch1:{title} {artists} audio"
        external = item.get("external_urls")
        webpage_url = (
            str(external.get("spotify"))
            if isinstance(external, Mapping) and external.get("spotify")
            else fallback_url
        )
        duration_ms = item.get("duration_ms")
        duration = (
            int(duration_ms) // 1000 if isinstance(duration_ms, (int, float)) else None
        )
        return Track(
            query=search,
            title=f"{title} — {artists}" if artists else title,
            webpage_url=webpage_url,
            duration_seconds=duration,
            requester_id=requester_id,
            requester_name=requester_name,
            source=MediaSource.SPOTIFY,
        )


class CompositeResolver:
    """Route Spotify URLs and delegate playback resolution to yt-dlp."""

    def __init__(
        self,
        youtube: YTDLPResolver,
        spotify: SpotifyResolver | None,
    ) -> None:
        self._youtube = youtube
        self._spotify = spotify

    async def expand(
        self,
        query: str,
        *,
        requester_id: int,
        requester_name: str,
        limit: int,
    ) -> list[Track]:
        """Resolve an input query with the appropriate provider."""
        if "open.spotify.com/" in query:
            if self._spotify is None:
                raise MediaResolutionError(
                    "Spotify no está configurado en este camerino."
                )
            return await self._spotify.expand(
                query,
                requester_id=requester_id,
                requester_name=requester_name,
                limit=limit,
            )
        return await self._youtube.expand(
            query,
            requester_id=requester_id,
            requester_name=requester_name,
            limit=limit,
        )

    async def resolve_stream(self, track: Track) -> Stream:
        """Resolve every provider's queue entry through yt-dlp."""
        return await self._youtube.resolve_stream(track)
