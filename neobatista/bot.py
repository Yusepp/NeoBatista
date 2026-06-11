"""Discord client lifecycle and dependency composition."""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

import discord
from discord.ext import commands

from .cog import MusicCog
from .config import Settings
from .player import PlayerManager
from .resolvers import CompositeResolver, SpotifyResolver, YTDLPResolver

LOGGER = logging.getLogger(__name__)
HEARTBEAT_FILE = Path("/tmp/neobatista-heartbeat")


class NeoBatistaBot(commands.Bot):
    """Compose services and own startup/shutdown tasks."""

    def __init__(self, settings: Settings) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(
            command_prefix=settings.command_prefix,
            intents=intents,
            help_command=commands.DefaultHelpCommand(dm_help=False),
            allowed_mentions=discord.AllowedMentions.none(),
        )
        self.settings = settings
        youtube = YTDLPResolver()
        spotify = (
            SpotifyResolver(
                settings.spotify_client_id,
                settings.spotify_client_secret,
            )
            if settings.spotify_client_id and settings.spotify_client_secret
            else None
        )
        self.resolver = CompositeResolver(youtube, spotify)
        self.players = PlayerManager(
            self.resolver,
            default_volume=settings.default_volume,
            idle_timeout_seconds=settings.idle_timeout_seconds,
            alone_timeout_seconds=settings.alone_timeout_seconds,
        )
        self._heartbeat_task: asyncio.Task[None] | None = None

    async def setup_hook(self) -> None:
        """Register commands, synchronize the tree, and start services."""
        await self.add_cog(MusicCog(self, self.settings, self.resolver, self.players))
        self.players.start()
        self._heartbeat_task = asyncio.create_task(
            self._heartbeat(), name="health-heartbeat"
        )

        if self.settings.development_guild_id is not None:
            guild = discord.Object(id=self.settings.development_guild_id)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            LOGGER.info("Synchronized %d development commands", len(synced))
        else:
            synced = await self.tree.sync()
            LOGGER.info("Synchronized %d global commands", len(synced))

    async def on_ready(self) -> None:
        """Log successful gateway readiness without exposing credentials."""
        LOGGER.info(
            "Connected as %s to %d guilds",
            self.user,
            len(self.guilds),
        )

    async def on_guild_remove(self, guild: discord.Guild) -> None:
        """Release a player when the bot leaves a guild."""
        await self.players.remove(guild.id)

    async def close(self) -> None:
        """Gracefully release health, playback, voice, and gateway resources."""
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            await asyncio.gather(self._heartbeat_task, return_exceptions=True)
            self._heartbeat_task = None
        await self.players.close()
        await asyncio.to_thread(HEARTBEAT_FILE.unlink, missing_ok=True)
        await super().close()

    async def _heartbeat(self) -> None:
        while True:
            await asyncio.to_thread(
                HEARTBEAT_FILE.write_text,
                str(time.time()),
                encoding="ascii",
            )
            await asyncio.sleep(15)
