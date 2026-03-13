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
  bot.py             # Discord bot — watches emoji reacts, !threshold, !testdownloads, daily download test
  app.py             # App factory, registers blueprints, /health endpoint
  db.py              # get_db() context manager
  auth.py            # @requires_auth decorator (HTTP Basic Auth)
  scheduler.py       # APScheduler for playlist refresh cycles
  downloader.py      # yt-dlp download, MP3 tagging, DB insertion
  playlists.py       # M3U playlist generation with optional idents
  download_all_songs.py  # CLI tool to backfill missing audio files
  logger_config.py   # File-based logging setup
  routes/
    api.py           # /add_song, /test_downloads, /settings
    streams.py       # /demo, /demo/<stream>, /get_original_url/<stream>
    admin.py         # /admin (Blue Design System UI), /admin/edit_song, /admin/delete_song
    archive.py       # /feedthechao, /download_archive, /download_progress
    downloads.py     # /download/<id>, /play/<id>, /download_playlist/<name>, /download_db
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
- **Remote:** `corecore` on GitHub
- **Shared storage:** Downloads at `/mnt/bandit/corecore` (external mount)

## Current State

- Production running on corecore containers (6 services: app, bot, pot-provider, icecast, streams, nginx)
- Emoji mapping: ❤️→1radio, :2radio:→2radio, :3radio:→3radio
- Streams served at `corecore.void.beauty/stream/{1radio,2radio,3radio}` (stream.void.beauty redirects there)
- Admin panel at `corecore.void.beauty/admin` — Blue Design System, inline audio playback, station transfers, edit/delete
- External nginx at `/etc/nginx/sites-enabled/void.beauty` (certbot-managed SSL — re-run certbot after scp'ing config changes). **Important:** `sites-enabled` must be a symlink to `sites-available`, not a copy — run `sudo ln -sf /etc/nginx/sites-available/void.beauty /etc/nginx/sites-enabled/void.beauty` if in doubt
- CORS headers for stream endpoints handled in Docker `nginx.conf` (with `always` flag), NOT in external nginx. `/get_original_url/` also has CORS headers.
- Bot commands restricted to `#dev-chat` channel. Members intent enabled in Discord Developer Portal.
- Daily download test: bot runs `!testdownloads` equivalent every 24h, DMs `tonymf` on failure. Tests YouTube, SoundCloud, Bandcamp via `/test_downloads` endpoint.
- **YouTube downloads BROKEN (Mar 2026)** — cookies keep getting invalidated. `cookies_update=False` added to prevent yt-dlp from overwriting cookie file. `remote_components` format changed from dict to list (`["ejs:github"]`). See `TROUBLESHOOTING-youtube-bot-detection.md`.
- Cookies are gitignored — must be scp'd to server manually: `scp cookies/youtube.com.txt rashomon.blue:~/dev/corecore/cookies/`
