"""Typed media and playback models."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class MediaSource(StrEnum):
    """Origin of a queued track."""

    YOUTUBE = "youtube"
    SPOTIFY = "spotify"
    SEARCH = "search"
    URL = "url"


@dataclass(frozen=True, slots=True)
class Track:
    """Stable queue metadata; stream URLs are deliberately not retained."""

    query: str
    title: str
    webpage_url: str | None
    duration_seconds: int | None
    requester_id: int
    requester_name: str
    source: MediaSource


@dataclass(frozen=True, slots=True)
class Stream:
    """Ephemeral audio stream resolved immediately before playback."""

    url: str
    title: str
    webpage_url: str | None
    duration_seconds: int | None


def format_duration(seconds: int | None) -> str:
    """Format a duration for compact Discord output."""
    if seconds is None:
        return "live/unknown"
    minutes, remaining = divmod(max(seconds, 0), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{remaining:02d}"
    return f"{minutes}:{remaining:02d}"
