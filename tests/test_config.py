"""Configuration validation tests."""

from __future__ import annotations

import pytest

from neobatista.config import Settings
from neobatista.errors import ConfigurationError


def test_minimal_configuration() -> None:
    settings = Settings.from_env({"DISCORD_TOKEN": "token"})

    assert settings.command_prefix == "!"
    assert settings.queue_limit == 200
    assert not settings.spotify_enabled


def test_complete_configuration() -> None:
    settings = Settings.from_env(
        {
            "DISCORD_TOKEN": "token",
            "SPOTIFY_CLIENT_ID": "id",
            "SPOTIFY_CLIENT_SECRET": "secret",
            "QUEUE_LIMIT": "25",
            "DEFAULT_VOLUME": "75",
            "DEVELOPMENT_GUILD_ID": "123",
        }
    )

    assert settings.spotify_enabled
    assert settings.queue_limit == 25
    assert settings.default_volume == 75
    assert settings.development_guild_id == 123


@pytest.mark.parametrize(
    "environment",
    [
        {},
        {"DISCORD_TOKEN": "x", "SPOTIFY_CLIENT_ID": "id"},
        {"DISCORD_TOKEN": "x", "QUEUE_LIMIT": "zero"},
        {"DISCORD_TOKEN": "x", "DEFAULT_VOLUME": "101"},
        {"DISCORD_TOKEN": "x", "LOG_LEVEL": "LOUD"},
        {"DISCORD_TOKEN": "x", "DEVELOPMENT_GUILD_ID": "guild"},
    ],
)
def test_invalid_configuration(environment: dict[str, str]) -> None:
    with pytest.raises(ConfigurationError):
        Settings.from_env(environment)
