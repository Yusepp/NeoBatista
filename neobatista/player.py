"""Concurrency-safe per-guild playback workers and lifecycle management."""

from __future__ import annotations

import asyncio
import logging
import random
import time
from collections.abc import Callable, Sequence
from typing import Protocol

import discord

from .errors import PlayerError, QueuePositionError
from .models import Stream, Track, format_duration
from .resolvers import MediaResolver

LOGGER = logging.getLogger(__name__)

FFMPEG_BEFORE_OPTIONS = "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
FFMPEG_OPTIONS = "-vn"


class MessageSink(Protocol):
    """Minimal channel interface needed by the player."""

    async def send(self, content: str | None = None, **kwargs: object) -> object:
        """Send a playback notification."""


AudioFactory = Callable[[Stream, int], discord.AudioSource]


def default_audio_factory(stream: Stream, volume: int) -> discord.AudioSource:
    """Create a reconnecting FFmpeg source with adjustable volume."""
    pcm = discord.FFmpegPCMAudio(
        stream.url,
        before_options=FFMPEG_BEFORE_OPTIONS,
        options=FFMPEG_OPTIONS,
    )
    return discord.PCMVolumeTransformer(pcm, volume=volume / 100)


class GuildPlayer:
    """Own one guild's queue, voice connection, and playback worker."""

    def __init__(
        self,
        guild_id: int,
        resolver: MediaResolver,
        *,
        default_volume: int,
        audio_factory: AudioFactory = default_audio_factory,
    ) -> None:
        self.guild_id = guild_id
        self._resolver = resolver
        self._audio_factory = audio_factory
        self._queue: list[Track] = []
        self._condition = asyncio.Condition()
        self._voice: discord.VoiceClient | None = None
        self._sink: MessageSink | None = None
        self._worker: asyncio.Task[None] | None = None
        self._closed = False
        self._playback_done: asyncio.Future[Exception | None] | None = None
        self.current: Track | None = None
        self.volume = default_volume
        self.last_activity = time.monotonic()
        self.alone_since: float | None = None

    @property
    def voice(self) -> discord.VoiceClient | None:
        """Return the current voice client."""
        return self._voice

    @property
    def is_active(self) -> bool:
        """Return whether a track is playing or paused."""
        return bool(
            self._voice and (self._voice.is_playing() or self._voice.is_paused())
        )

    async def attach(
        self,
        voice: discord.VoiceClient,
        sink: MessageSink,
    ) -> None:
        """Attach Discord resources and start the worker if necessary."""
        self._voice = voice
        self._sink = sink
        self.touch()
        if self._worker is None or self._worker.done():
            self._closed = False
            self._worker = asyncio.create_task(
                self._run(), name=f"guild-player-{self.guild_id}"
            )

    async def enqueue(
        self,
        tracks: Sequence[Track],
        *,
        maximum_size: int | None = None,
    ) -> tuple[Track, ...]:
        """Append tracks atomically, enforcing an optional queue limit."""
        if not tracks:
            return ()
        async with self._condition:
            available = (
                len(tracks)
                if maximum_size is None
                else max(0, maximum_size - len(self._queue))
            )
            accepted = tuple(tracks[:available])
            if not accepted:
                raise PlayerError("La cola está llena hasta la bandera.")
            self._queue.extend(accepted)
            self.touch()
            self._condition.notify()
            return accepted

    async def snapshot(self) -> tuple[Track, ...]:
        """Return an immutable queue snapshot."""
        async with self._condition:
            return tuple(self._queue)

    async def remove(self, position: int) -> Track:
        """Remove and return a one-based queue position."""
        async with self._condition:
            index = self._index(position)
            self.touch()
            return self._queue.pop(index)

    async def move(self, source: int, destination: int) -> Track:
        """Move one queue entry using one-based positions."""
        async with self._condition:
            source_index = self._index(source)
            if not 1 <= destination <= len(self._queue):
                raise QueuePositionError("La posición de destino no existe.")
            track = self._queue.pop(source_index)
            self._queue.insert(destination - 1, track)
            self.touch()
            return track

    async def shuffle(self) -> None:
        """Randomize queued tracks without touching the current track."""
        async with self._condition:
            if len(self._queue) < 2:
                raise PlayerError("Necesito al menos dos temas para barajar.")
            random.shuffle(self._queue)
            self.touch()

    async def clear(self) -> int:
        """Clear queued tracks and return the removed count."""
        async with self._condition:
            count = len(self._queue)
            self._queue.clear()
            self.touch()
            return count

    def pause(self) -> None:
        """Pause active playback."""
        if not self._voice or not self._voice.is_playing():
            raise PlayerError("No hay nada sonando para pausar.")
        self._voice.pause()
        self.touch()

    def resume(self) -> None:
        """Resume paused playback."""
        if not self._voice or not self._voice.is_paused():
            raise PlayerError("No hay ninguna pausa dramática activa.")
        self._voice.resume()
        self.touch()

    def skip(self) -> None:
        """Stop the current source; its callback advances the worker once."""
        if not self._voice or not self.is_active:
            raise PlayerError("No hay ningún tema que saltar.")
        self._voice.stop()
        self.touch()

    async def stop(self) -> None:
        """Clear the queue and stop the current source."""
        await self.clear()
        if self._voice and self.is_active:
            self._voice.stop()
        self.touch()

    def set_volume(self, volume: int) -> None:
        """Set current and future playback volume."""
        if not 0 <= volume <= 100:
            raise PlayerError("El volumen debe estar entre 0 y 100.")
        self.volume = volume
        if self._voice and isinstance(self._voice.source, discord.PCMVolumeTransformer):
            self._voice.source.volume = volume / 100
        self.touch()

    async def disconnect(self) -> None:
        """Stop playback, cancel the worker, and disconnect from voice."""
        self._closed = True
        await self.clear()
        voice, self._voice = self._voice, None
        if voice and voice.is_connected():
            if voice.is_playing() or voice.is_paused():
                voice.stop()
            await voice.disconnect(force=True)
        worker, self._worker = self._worker, None
        if worker and worker is not asyncio.current_task():
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)
        self.current = None

    def touch(self) -> None:
        """Record user or playback activity using a monotonic clock."""
        self.last_activity = time.monotonic()

    def _index(self, position: int) -> int:
        if not 1 <= position <= len(self._queue):
            raise QueuePositionError("Esa posición no existe en la cola.")
        return position - 1

    async def _run(self) -> None:
        """Consume the queue serially; this is the only advancing code path."""
        while True:
            async with self._condition:
                await self._condition.wait_for(
                    lambda: self._closed or bool(self._queue)
                )
                if self._closed:
                    return
                track = self._queue.pop(0)
            self.current = track
            self.touch()
            try:
                stream = await self._resolver.resolve_stream(track)
                await self._play(stream)
            except asyncio.CancelledError:
                raise
            except Exception:
                LOGGER.exception(
                    "Track playback failed",
                    extra={"guild_id": self.guild_id, "track": track.title},
                )
                await self._notify(
                    f"**{track.title}** falló en pleno escenario. "
                    "LA **NEO**BOMBA sigue con el siguiente."
                )
            finally:
                self.current = None
                self._playback_done = None
                self.touch()

    async def _play(self, stream: Stream) -> None:
        voice = self._voice
        if not voice or not voice.is_connected():
            raise PlayerError("La conexión de voz desapareció.")
        source = self._audio_factory(stream, self.volume)
        loop = asyncio.get_running_loop()
        done: asyncio.Future[Exception | None] = loop.create_future()
        self._playback_done = done

        # discord.py invokes `after` from its audio thread. Transfer only the
        # Future mutation to the asyncio event-loop thread.
        def after(error: Exception | None) -> None:
            def finish() -> None:
                if not done.done():
                    done.set_result(error)

            loop.call_soon_threadsafe(finish)

        voice.play(source, after=after)
        await self._notify(
            f"Ahora suena **{stream.title}** "
            f"({format_duration(stream.duration_seconds)})."
        )
        error = await done
        if error is not None:
            raise PlayerError("FFmpeg terminó con un error.") from error

    async def _notify(self, message: str) -> None:
        if self._sink is None:
            return
        try:
            await self._sink.send(message)
        except discord.HTTPException:
            LOGGER.warning(
                "Could not send playback notification",
                extra={"guild_id": self.guild_id},
            )


class PlayerManager:
    """Create, monitor, and dispose per-guild players."""

    def __init__(
        self,
        resolver: MediaResolver,
        *,
        default_volume: int,
        idle_timeout_seconds: int,
        alone_timeout_seconds: int,
    ) -> None:
        self._resolver = resolver
        self._default_volume = default_volume
        self._idle_timeout = idle_timeout_seconds
        self._alone_timeout = alone_timeout_seconds
        self._players: dict[int, GuildPlayer] = {}
        self._monitor: asyncio.Task[None] | None = None

    def get(self, guild_id: int) -> GuildPlayer | None:
        """Return an existing player without creating one."""
        return self._players.get(guild_id)

    def get_or_create(self, guild_id: int) -> GuildPlayer:
        """Return a guild player, creating it on first use."""
        player = self._players.get(guild_id)
        if player is None:
            player = GuildPlayer(
                guild_id,
                self._resolver,
                default_volume=self._default_volume,
            )
            self._players[guild_id] = player
        return player

    def start(self) -> None:
        """Start the lifecycle monitor."""
        if self._monitor is None or self._monitor.done():
            self._monitor = asyncio.create_task(
                self._monitor_players(), name="player-monitor"
            )

    async def remove(self, guild_id: int) -> None:
        """Disconnect and remove one guild player."""
        player = self._players.pop(guild_id, None)
        if player:
            await player.disconnect()

    async def close(self) -> None:
        """Cancel monitoring and close every guild player."""
        if self._monitor:
            self._monitor.cancel()
            await asyncio.gather(self._monitor, return_exceptions=True)
            self._monitor = None
        players = list(self._players.values())
        self._players.clear()
        await asyncio.gather(
            *(player.disconnect() for player in players),
            return_exceptions=True,
        )

    async def _monitor_players(self) -> None:
        while True:
            await asyncio.sleep(15)
            now = time.monotonic()
            for guild_id, player in list(self._players.items()):
                try:
                    if await self._should_disconnect(player, now):
                        await self.remove(guild_id)
                except Exception:
                    LOGGER.exception(
                        "Player monitor iteration failed",
                        extra={"guild_id": guild_id},
                    )

    async def _should_disconnect(self, player: GuildPlayer, now: float) -> bool:
        voice = player.voice
        if not voice or not voice.is_connected():
            return True

        members = getattr(voice.channel, "members", ())
        alone = len([member for member in members if not member.bot]) == 0
        if alone:
            player.alone_since = player.alone_since or now
            if now - player.alone_since >= self._alone_timeout:
                return True
        else:
            player.alone_since = None

        queue = await player.snapshot()
        idle = not player.is_active and player.current is None and not queue
        return idle and now - player.last_activity >= self._idle_timeout
