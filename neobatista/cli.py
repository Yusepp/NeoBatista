"""Command-line entry point for NeoBatista."""

from __future__ import annotations

import logging
import sys

from dotenv import load_dotenv

from .bot import NeoBatistaBot
from .config import Settings
from .errors import ConfigurationError


def main() -> int:
    """Load configuration and run the Discord gateway client."""
    load_dotenv()
    try:
        settings = Settings.from_env()
    except ConfigurationError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    logging.basicConfig(
        level=getattr(logging, settings.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    bot = NeoBatistaBot(settings)
    bot.run(settings.discord_token, log_handler=None)
    return 0
