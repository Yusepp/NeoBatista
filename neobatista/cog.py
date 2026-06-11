"""Hybrid command interface for the music player."""

from __future__ import annotations

import logging
from typing import Any, cast

import discord
from discord import app_commands
from discord.ext import commands

from . import messages
from .config import Settings
from .errors import NeoBatistaError, PlayerError
from .models import Track, format_duration
from .player import GuildPlayer, MessageSink, PlayerManager
from .resolvers import MediaResolver

LOGGER = logging.getLogger(__name__)


class MusicCog(commands.Cog):
    """Expose one consistent command implementation to slash and prefix users."""

    def __init__(
        self,
        bot: commands.Bot,
        settings: Settings,
        resolver: MediaResolver,
        players: PlayerManager,
    ) -> None:
        self.bot = bot
        self.settings = settings
        self.resolver = resolver
        self.players = players

    async def cog_command_error(
        self,
        ctx: commands.Context[Any],
        error: Exception,
    ) -> None:
        """Translate expected prefix-command failures."""
        cause = getattr(error, "original", error)
        if isinstance(cause, NeoBatistaError):
            await ctx.send(str(cause))
            return
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("Falta un argumento. Consulta `/help` o `!help`.")
            return
        if isinstance(error, commands.BadArgument):
            await ctx.send("Ese argumento viene con las piezas cambiadas.")
            return
        LOGGER.exception(
            "Unhandled command error",
            exc_info=(type(error), error, error.__traceback__),
        )
        await ctx.send("LA **NEO**BOMBA tuvo una avería inesperada.")

    @commands.hybrid_command(
        name="play",
        aliases=["p"],
        description="Play a URL, playlist, or search.",
    )
    @commands.guild_only()
    @app_commands.describe(query="URL, playlist, or words to search")
    async def play(
        self,
        ctx: commands.Context[Any],
        *,
        query: str,
    ) -> None:
        """Resolve media, connect if needed, and enqueue it atomically."""
        guild = self._guild(ctx)
        channel = self._author_voice_channel(ctx)
        await self._defer(ctx)

        player = self.players.get_or_create(guild.id)
        voice_protocol = guild.voice_client
        voice: discord.VoiceClient
        joined = False
        if voice_protocol:
            voice = cast(discord.VoiceClient, voice_protocol)
        else:
            voice = cast(discord.VoiceClient, await channel.connect())
            joined = True
        if voice.is_connected():
            if voice.channel.id != channel.id:
                raise PlayerError(messages.WRONG_VOICE)
        else:
            voice = cast(discord.VoiceClient, await channel.connect())
            joined = True
        if joined:
            await ctx.send(messages.JOINED)

        await player.attach(voice, self._sink(ctx))
        queued = await player.snapshot()
        available = self.settings.queue_limit - len(queued)
        if available <= 0:
            raise PlayerError(
                f"La cola alcanzó el límite de {self.settings.queue_limit} temas."
            )

        resolved_tracks = await self.resolver.expand(
            query.strip(),
            requester_id=ctx.author.id,
            requester_name=ctx.author.display_name,
            limit=available,
        )
        tracks = await player.enqueue(
            resolved_tracks,
            maximum_size=self.settings.queue_limit,
        )
        if len(tracks) == 1:
            await ctx.send(f"**{tracks[0].title}** entra en la cola.")
        else:
            suffix = (
                " La playlist fue recortada al límite del local."
                if len(tracks) == available
                else ""
            )
            await ctx.send(
                f"Playlist aceptada: **{len(tracks)} temas** en la cola.{suffix}"
            )

    @commands.hybrid_command(
        name="queue",
        description="Show the current music queue.",
    )
    @commands.guild_only()
    async def queue(self, ctx: commands.Context[Any]) -> None:
        """Display current and queued tracks in paginated embeds."""
        player = self._existing_player(ctx)
        tracks = await player.snapshot()
        if player.current is None and not tracks:
            await ctx.send(messages.QUEUE_EMPTY)
            return

        pages = self._queue_embeds(player.current, tracks)
        for embed in pages:
            await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="nowplaying",
        aliases=["np"],
        description="Show the current track.",
    )
    @commands.guild_only()
    async def now_playing(self, ctx: commands.Context[Any]) -> None:
        """Show the currently selected queue entry."""
        player = self._existing_player(ctx)
        track = player.current
        if track is None:
            await ctx.send(messages.NOTHING_PLAYING)
            return
        await ctx.send(embed=self._track_embed(track, "Ahora mismo"))

    @commands.hybrid_command(name="skip", description="Skip the current track.")
    @commands.guild_only()
    async def skip(self, ctx: commands.Context[Any]) -> None:
        """Stop the current source and let the worker advance once."""
        player = self._controlled_player(ctx)
        player.skip()
        await ctx.send(messages.SKIPPED)

    @commands.hybrid_command(name="pause", description="Pause playback.")
    @commands.guild_only()
    async def pause(self, ctx: commands.Context[Any]) -> None:
        """Pause active playback."""
        player = self._controlled_player(ctx)
        player.pause()
        await ctx.send(messages.PAUSED)

    @commands.hybrid_command(name="resume", description="Resume playback.")
    @commands.guild_only()
    async def resume(self, ctx: commands.Context[Any]) -> None:
        """Resume paused playback."""
        player = self._controlled_player(ctx)
        player.resume()
        await ctx.send(messages.RESUMED)

    @commands.hybrid_command(
        name="stop",
        description="Stop playback and clear the queue.",
    )
    @commands.guild_only()
    async def stop(self, ctx: commands.Context[Any]) -> None:
        """Stop the current source and clear pending entries."""
        player = self._controlled_player(ctx)
        await player.stop()
        await ctx.send(messages.STOPPED)

    @commands.hybrid_command(
        name="remove",
        description="Remove a queued track by position.",
    )
    @commands.guild_only()
    async def remove(
        self,
        ctx: commands.Context[Any],
        position: int,
    ) -> None:
        """Remove a one-based queue position."""
        player = self._controlled_player(ctx)
        track = await player.remove(position)
        await ctx.send(f"**{track.title}** abandona la cola.")

    @commands.hybrid_command(
        name="move",
        description="Move a queued track to another position.",
    )
    @commands.guild_only()
    async def move(
        self,
        ctx: commands.Context[Any],
        source: int,
        destination: int,
    ) -> None:
        """Move a queue entry using one-based positions."""
        player = self._controlled_player(ctx)
        track = await player.move(source, destination)
        await ctx.send(f"**{track.title}** pasa a la posición {destination}.")

    @commands.hybrid_command(
        name="shuffle",
        description="Shuffle queued tracks.",
    )
    @commands.guild_only()
    async def shuffle(self, ctx: commands.Context[Any]) -> None:
        """Shuffle pending queue entries."""
        player = self._controlled_player(ctx)
        await player.shuffle()
        await ctx.send(messages.SHUFFLED)

    @commands.hybrid_command(
        name="clear",
        description="Clear queued tracks without stopping the current one.",
    )
    @commands.guild_only()
    async def clear(self, ctx: commands.Context[Any]) -> None:
        """Remove all pending queue entries."""
        player = self._controlled_player(ctx)
        removed = await player.clear()
        await ctx.send(f"{messages.CLEARED} **{removed} temas** fuera.")

    @commands.hybrid_command(
        name="volume",
        description="Set playback volume from 0 to 100.",
    )
    @commands.guild_only()
    async def volume(
        self,
        ctx: commands.Context[Any],
        level: app_commands.Range[int, 0, 100],
    ) -> None:
        """Set volume for current and future tracks."""
        player = self._controlled_player(ctx)
        player.set_volume(int(level))
        await ctx.send(f"Volumen al **{level}%**. Los vecinos toman nota.")

    @commands.hybrid_command(
        name="leave",
        description="Disconnect and destroy this server's player.",
    )
    @commands.guild_only()
    async def leave(self, ctx: commands.Context[Any]) -> None:
        """Disconnect and release all guild playback resources."""
        player = self._controlled_player(ctx)
        await self.players.remove(player.guild_id)
        await ctx.send(messages.LEFT)

    def _guild(self, ctx: commands.Context[Any]) -> discord.Guild:
        if ctx.guild is None:
            raise PlayerError("Este espectáculo solo funciona dentro de un servidor.")
        return ctx.guild

    def _author_voice_channel(
        self, ctx: commands.Context[Any]
    ) -> discord.VoiceChannel | discord.StageChannel:
        author = ctx.author
        if not isinstance(author, discord.Member) or author.voice is None:
            raise PlayerError(messages.NOT_IN_VOICE)
        channel = author.voice.channel
        if not isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
            raise PlayerError(messages.NOT_IN_VOICE)
        return channel

    def _existing_player(self, ctx: commands.Context[Any]) -> GuildPlayer:
        guild = self._guild(ctx)
        player = self.players.get(guild.id)
        if player is None:
            raise PlayerError(messages.NOTHING_PLAYING)
        return player

    def _controlled_player(self, ctx: commands.Context[Any]) -> GuildPlayer:
        player = self._existing_player(ctx)
        channel = self._author_voice_channel(ctx)
        if player.voice is None or player.voice.channel.id != channel.id:
            raise PlayerError(messages.WRONG_VOICE)
        return player

    @staticmethod
    async def _defer(ctx: commands.Context[Any]) -> None:
        interaction = ctx.interaction
        if interaction is not None and not interaction.response.is_done():
            await interaction.response.defer(thinking=True)

    @staticmethod
    def _sink(ctx: commands.Context[Any]) -> MessageSink:
        return ctx.channel  # type: ignore[return-value]

    @staticmethod
    def _track_embed(track: Track, title: str) -> discord.Embed:
        embed = discord.Embed(title=title, color=discord.Color.orange())
        value = f"`{format_duration(track.duration_seconds)}`"
        if track.webpage_url:
            value = f"[{track.title}]({track.webpage_url}) · {value}"
        else:
            value = f"{track.title} · {value}"
        embed.description = value
        embed.set_footer(text=f"Pedido por {track.requester_name}")
        return embed

    def _queue_embeds(
        self,
        current: Track | None,
        tracks: tuple[Track, ...],
    ) -> list[discord.Embed]:
        pages: list[discord.Embed] = []
        page_size = 10
        total_pages = max(1, (len(tracks) + page_size - 1) // page_size)
        for page_number, offset in enumerate(
            range(0, max(len(tracks), 1), page_size), start=1
        ):
            embed = discord.Embed(
                title="Cola de LA NEO BOMBA",
                color=discord.Color.orange(),
            )
            if current and page_number == 1:
                embed.add_field(
                    name="Sonando",
                    value=(
                        f"{current.title} · "
                        f"`{format_duration(current.duration_seconds)}`"
                    ),
                    inline=False,
                )
            chunk = tracks[offset : offset + page_size]
            queue_text = "\n".join(
                f"`{offset + index}.` {track.title} "
                f"`{format_duration(track.duration_seconds)}`"
                for index, track in enumerate(chunk, start=1)
            )
            embed.add_field(
                name="A continuación",
                value=queue_text or messages.QUEUE_EMPTY,
                inline=False,
            )
            embed.set_footer(text=f"Página {page_number}/{total_pages}")
            pages.append(embed)
        return pages
