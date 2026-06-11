"""Container health check based on the bot's event-loop heartbeat."""

from __future__ import annotations

import time
from pathlib import Path

HEARTBEAT_FILE = Path("/tmp/neobatista-heartbeat")
MAX_AGE_SECONDS = 45


def main() -> int:
    """Return success while the event-loop heartbeat remains fresh."""
    try:
        heartbeat = float(HEARTBEAT_FILE.read_text(encoding="ascii"))
    except (OSError, ValueError):
        return 1
    return 0 if time.time() - heartbeat <= MAX_AGE_SECONDS else 1


if __name__ == "__main__":
    raise SystemExit(main())
