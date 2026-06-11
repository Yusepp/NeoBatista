# NeoBatista

NeoBatista is a Discord music bot with hybrid slash and `!` commands, per-server
playback workers, YouTube/search streaming through yt-dlp, and optional Spotify
playlist conversion.

## Security notice

An old Spotify client secret was committed before this redesign. Moving secrets
to environment variables prevents new source exposure, but **does not make the
old credential safe**. It should be revoked and replaced. The current plan
deliberately leaves Git history unchanged.

## Requirements

- Docker, or Python 3.12
- FFmpeg
- Node.js for current yt-dlp YouTube extraction
- A Discord application with a bot token
- Message Content privileged intent enabled for legacy `!` commands
- Optional Spotify application credentials

## Configuration

Copy `.env.example` to `.env` for local development and fill in
`DISCORD_TOKEN`. Spotify requires both `SPOTIFY_CLIENT_ID` and
`SPOTIFY_CLIENT_SECRET`; omit both to disable Spotify URLs.

`DEVELOPMENT_GUILD_ID` makes slash-command updates appear immediately in one
test server. Without it, commands are synchronized globally and Discord may
take time to propagate them.

Never commit `.env`.

## Run with Docker

```bash
docker build -t neobatista .
docker run --env-file .env --name neobatista neobatista
```

The image runs as a non-root user and reports unhealthy if the bot event loop
stops refreshing its heartbeat.

## Run directly

```bash
uv sync --extra dev
uv run python neo_batista.py
```

FFmpeg and Node.js must be available on `PATH`.

## Commands

Every command works as `/command` and `!command`:

- `play`, `p`: URL, YouTube playlist, Spotify URL, or search phrase
- `queue`, `nowplaying`
- `pause`, `resume`, `skip`, `stop`
- `remove`, `move`, `shuffle`, `clear`
- `volume`
- `leave`

Control commands require the caller to share the bot's voice channel. Queues
are isolated per guild and capped at 200 tracks by default.

## Quality checks

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy neobatista neo_batista.py scripts tests
uv run pytest
```

Tests mock Discord, Spotify, and yt-dlp; they do not contact external services.

## Operational notes

- The bot streams audio and does not retain downloaded media.
- Expiring stream URLs are resolved immediately before playback.
- Idle players disconnect after five minutes; players alone in voice disconnect
  after one minute. Both values are configurable.
- Keep yt-dlp current because upstream site extractors change frequently.
- Operators are responsible for complying with media-provider terms and
  applicable copyright law.
