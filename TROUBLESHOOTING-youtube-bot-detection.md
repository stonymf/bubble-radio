# YouTube "Sign in to confirm you're not a bot" — yt-dlp

## Status: RESOLVED (Feb 2026)

## Root Cause

Two separate issues:

1. **Incomplete cookie file** — the exported cookies were missing critical auth cookies (`LOGIN_INFO`, `__Secure-1PSID`, `__Secure-3PSID`, `__Secure-*PAPISID`, `__Secure-*PSIDTS`, `__Secure-*PSIDCC`). Without these, YouTube sees requests as unauthenticated and returns `LOGIN_REQUIRED` from all player APIs.

2. **Missing `remote_components` config** — yt-dlp needs `remote_components: {"ejs": "github"}` to download JS challenge solver scripts for Deno. Without this, signature solving fails.

## What Fixed It

1. **Fresh, complete cookie export** from Chrome using "Get cookies.txt LOCALLY" extension while on youtube.com and logged in. The file needs ~26 cookies including all `__Secure-*` variants. Old file only had 15 cookies (mostly `.google.com` domain, missing YouTube-specific auth).

2. **Added `remote_components` to yt-dlp opts** in `src/downloader.py`:
   ```python
   "remote_components": {"ejs": "github"},
   ```

## Current Working Setup

- **yt-dlp version:** 2026.02.21
- **Runtime:** Deno 2.7.1 (installed in Dockerfile.app)
- **Cookies:** Netscape-format file at `/usr/src/app/cookies/youtube.com.txt` with full auth cookies
- **PO token provider:** `brainicism/bgutil-ytdlp-pot-provider:latest` sidecar on port 4416 (fallback, not needed with proper cookies)
- **Plugin:** `bgutil-ytdlp-pot-provider` 1.2.2 pip package
- **Config in `src/downloader.py`:**
  ```python
  opts = {
      "format": "bestaudio/best",
      "extractor_args": {
          "youtube": {"player_client": ["default"]},
          "youtubepot-bgutilhttp": {"base_url": ["http://pot-provider:4416"]},
      },
      "remote_components": {"ejs": "github"},
  }
  ```

## Key Diagnostic Commands

```bash
# Verbose test (shows plugin loading, cookie detection, PO token flow)
docker exec corecore-bubble-radio-app-1 yt-dlp -v --skip-download \
  --cookies /usr/src/app/cookies/youtube.com.txt \
  --extractor-args 'youtube:player_client=default' \
  --extractor-args 'youtubepot-bgutilhttp:base_url=http://pot-provider:4416' \
  --remote-components ejs:github \
  'https://www.youtube.com/watch?v=fYT7969YIwU'

# Check Deno
docker exec corecore-bubble-radio-app-1 deno --version

# Check pot-provider
docker exec corecore-bubble-radio-app-1 curl -s http://pot-provider:4416
docker logs corecore-pot-provider-1

# Check cookie count and key cookies
docker exec corecore-bubble-radio-app-1 grep -c '^[^#]' /usr/src/app/cookies/youtube.com.txt
docker exec corecore-bubble-radio-app-1 grep -E '(LOGIN_INFO|__Secure-1PSID)' /usr/src/app/cookies/youtube.com.txt
```

## Signs It's Working

In verbose output, look for:
- `Found YouTube account cookies` — cookies are being read
- `Detected YouTube Premium subscription` — auth is working (if account has Premium)
- `Downloading tv downgraded player API JSON` — not `LOGIN_REQUIRED`
- `Downloading challenge solver lib script` — remote components working
- `Downloading 1 format(s): ...` — success

## If It Breaks Again

- **Cookies expire** — re-export from Chrome periodically. The `__Secure-*PSIDTS` cookies have ~6 month expiry.
- **YouTube changes bot detection** — check yt-dlp GitHub issues, update yt-dlp version
- **Datacenter IP flagging** — if cookies alone stop working, the PO token provider is already in place as fallback

## Community Context

- [Issue #10128](https://github.com/yt-dlp/yt-dlp/issues/10128) — original "Sign in to confirm" issue
- [Issue #15012](https://github.com/yt-dlp/yt-dlp/issues/15012) — external JS runtime required (>= 2025.11.12)
- [Issue #15676](https://github.com/yt-dlp/yt-dlp/issues/15676) — JS challenge solving fails in Docker (Node OOM)
- [bgutil-ytdlp-pot-provider](https://github.com/Brainicism/bgutil-ytdlp-pot-provider) — automatic PO token generation
- [yt-dlp EJS wiki](https://github.com/yt-dlp/yt-dlp/wiki/EJS) — JS challenge solver setup
