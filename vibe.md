# Corecore

Community radio station powered by Discord. Users submit songs via a Discord bot, which are downloaded, organized into playlists, and streamed via Icecast.

## Architecture

```
Discord Bot (src/bot.py) → POST /add_song → Flask app → yt-dlp download → SQLite DB
                                                                        ↓
                                                          Playlist generation (APScheduler)
                                                                        ↓
                                                          Liquidsoap → Icecast → Listeners
```

**Stack:** Flask, discord.py, SQLite, yt-dlp, Liquidsoap, Icecast, Nginx, Docker Compose

## Project Structure

```
src/
  config.py          # Centralized config (all paths, settings from .env)
  bot.py             # Discord bot — watches ❤️/:2radio:/:3radio: reacts, configurable threshold (!threshold)
  app.py             # App factory, registers blueprints, /health endpoint
  db.py              # get_db() context manager
  auth.py            # @requires_auth decorator (HTTP Basic Auth)
  scheduler.py       # APScheduler for playlist refresh cycles
  downloader.py      # yt-dlp download, MP3 tagging, DB insertion
  playlists.py       # M3U playlist generation with optional idents
  download_all_songs.py  # CLI tool to backfill missing audio files
  logger_config.py   # File-based logging setup
  routes/
    api.py           # /add_song (Discord bot endpoint)
    streams.py       # /demo, /demo/<stream>, /get_original_url/<stream>
    admin.py         # /admin, /admin/edit_song, /admin/delete_song
    archive.py       # /feedthechao, /download_archive, /download_progress
    downloads.py     # /download/<id>, /download_playlist/<name>, /download_db
```

## Key Decisions

- **Single gunicorn worker** (`--preload --workers 1`) — required for global state (archive progress, scheduler)
- **ICECAST_INTERNAL_URL** — container-to-container status queries use internal Docker networking, not public URL
- **Centralized config** — all paths derived from `BASE_DIR` env var (default `/usr/src/app`)
- **Blueprint architecture** — monolith split into 5 route blueprints + shared modules

## Deployment

- **Server:** rashomon.blue at `~/dev/corecore`
- **Auto-deploy:** Cron checks `origin/main` every minute, pulls + rebuilds if changed
- **GitHub:** github.com/stonymf/corecore (private)
- **Remote:** `corecore` (not `origin` — `origin` still points to old bubble-radio repo)
- **Shared storage:** Downloads at `/mnt/bandit/bubble-radio` (external mount)

## Current State

- Refactoring complete (Feb 2026): all 8 phases implemented
- Discord bot integrated into project (was previously external)
- Production running on corecore containers (6 services: app, bot, pot-provider, icecast, streams, nginx)
- Bot connected as corecore#8570 (app ID: 1476853275742699623)
- Emoji mapping: ❤️→1radio, :2radio:→2radio, :3radio:→3radio
- YouTube downloads working again (Feb 2026) — required complete cookie export (with `LOGIN_INFO`, `__Secure-*` cookies) + `remote_components: {"ejs": "github"}` in yt-dlp opts. See `TROUBLESHOOTING-youtube-bot-detection.md` for details. Cookies will need periodic re-export (~6 months).
- Health check: `curl https://stream.rashomon.blue/health`
