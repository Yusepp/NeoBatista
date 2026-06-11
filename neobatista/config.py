"""Environment-backed application configuration."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

from .errors import ConfigurationError


def _read_int(
    values: Mapping[str, str],
    name: str,
    default: int,
    *,
    minimum: int,
    maximum: int,
) -> int:
    """Read and range-check one integer environment setting."""
    raw = values.get(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer.") from exc
    if not minimum <= value <= maximum:
        raise ConfigurationError(f"{name} must be between {minimum} and {maximum}.")
    return value


@dataclass(frozen=True, slots=True)
class Settings:
    """Validated runtime settings loaded from environment variables."""

    discord_token: str
    spotify_client_id: str | None = None
    spotify_client_secret: str | None = None
    command_prefix: str = "!"
    log_level: str = "INFO"
    queue_limit: int = 200
    default_volume: int = 50
    idle_timeout_seconds: int = 300
    alone_timeout_seconds: int = 60
    development_guild_id: int | None = None

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Settings:
        """Build settings from an environment mapping and fail fast."""
        values = os.environ if environ is None else environ
        token = values.get("DISCORD_TOKEN", "").strip()
        if not token:
            raise ConfigurationError("DISCORD_TOKEN is required.")

        spotify_id = values.get("SPOTIFY_CLIENT_ID", "").strip() or None
        spotify_secret = values.get("SPOTIFY_CLIENT_SECRET", "").strip() or None
        if bool(spotify_id) != bool(spotify_secret):
            raise ConfigurationError(
                "SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET must be set together."
            )

        prefix = values.get("COMMAND_PREFIX", "!").strip()
        if not prefix:
            raise ConfigurationError("COMMAND_PREFIX cannot be empty.")

        log_level = values.get("LOG_LEVEL", "INFO").strip().upper()
        if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ConfigurationError("LOG_LEVEL is not valid.")

        development_guild_id: int | None = None
        raw_guild_id = values.get("DEVELOPMENT_GUILD_ID", "").strip()
        if raw_guild_id:
            try:
                development_guild_id = int(raw_guild_id)
            except ValueError as exc:
                raise ConfigurationError(
                    "DEVELOPMENT_GUILD_ID must be an integer."
                ) from exc

        return cls(
            discord_token=token,
            spotify_client_id=spotify_id,
            spotify_client_secret=spotify_secret,
            command_prefix=prefix,
            log_level=log_level,
            queue_limit=_read_int(values, "QUEUE_LIMIT", 200, minimum=1, maximum=1000),
            default_volume=_read_int(
                values, "DEFAULT_VOLUME", 50, minimum=0, maximum=100
            ),
            idle_timeout_seconds=_read_int(
                values, "IDLE_TIMEOUT_SECONDS", 300, minimum=30, maximum=86400
            ),
            alone_timeout_seconds=_read_int(
                values, "ALONE_TIMEOUT_SECONDS", 60, minimum=15, maximum=3600
            ),
            development_guild_id=development_guild_id,
        )

    @property
    def spotify_enabled(self) -> bool:
        """Return whether both Spotify application credentials are available."""
        return bool(self.spotify_client_id and self.spotify_client_secret)
