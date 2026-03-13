# YouTube "Sign in to confirm you're not a bot" — yt-dlp

## Status: TESTING FIX (Mar 2026)

Switched from cookie-based auth to cookie-free `mweb` client + PO tokens via bgutil-ytdlp-pot-provider. Needs deploy to verify.

## Root Cause (identified Mar 13, 2026)

**YouTube invalidates cookies when used from a different IP range than where they were exported.** Cookies exported from a residential IP (Chrome on Mac) get killed on first use from a datacenter IP (rashomon.blue). This is IP-binding, not a yt-dlp bug — confirmed by yt-dlp maintainers closing [#15865](https://github.com/yt-dlp/yt-dlp/issues/15865) and [#8227](https://github.com/yt-dlp/yt-dlp/issues/8227) as "not a bug."

The cookie-based approach is fundamentally broken for server deployments.

## Fix Applied

**Switched to cookie-free `mweb` client** per the [PO Token Guide](https://github.com/yt-dlp/yt-dlp/wiki/PO-Token-Guide):

> "TL;DR recommended setup: Use a PO Token Provider plugin to provide the `mweb` client with a PO Token for GVS requests."

Changes in `src/downloader.py` `_get_ydl_opts()`:
- `player_client`: `["default"]` → `["mweb"]`
- Removed `cookiefile` and `cookies_update` — no longer needed
- `remote_components` and `pot-provider` config unchanged

## Deploy Steps

```bash
# On rashomon.blue:
cd ~/dev/corecore
git pull

# Pull latest pot-provider image (1.3.1 has Deno + ytAtP challenge support)
docker compose pull pot-provider

# Rebuild and restart
docker compose up --build -d

# Test
docker exec corecore-corecore-app-1 yt-dlp -v --skip-download \
  --extractor-args 'youtube:player_client=mweb' \
  --extractor-args 'youtubepot-bgutilhttp:base_url=http://pot-provider:4416' \
  --remote-components ejs:github \
  'https://www.youtube.com/watch?v=vKYIew27R0Y'
```

## Architecture (updated)

```
src/downloader.py: _get_ydl_opts()
     → extractor_args.youtube.player_client = ["mweb"]
     → extractor_args.youtubepot-bgutilhttp.base_url = ["http://pot-provider:4416"]
     → remote_components = ["ejs:github"]
     ↓
yt-dlp → bgutil pot-provider (PO token) → Deno (JS challenge solver) → YouTube mweb API
```

No cookies involved. PO tokens are generated per-video by the pot-provider container.

## Signs It's Working (mweb)

In verbose output, look for:
- `Downloading mweb player API JSON` — mweb client in use
- `Downloading challenge solver lib script` — remote components working
- PO token generation logs from pot-provider container
- `Downloading 1 format(s): ...` — success

## Signs It's Broken

- `Sign in to confirm you're not a bot` — still failing, may need cookies after all
- `Remote components challenge solver script (deno) and NPM package (deno) were skipped` — remote_components not being passed
- pot-provider errors in `docker logs corecore-pot-provider-1`

## Diagnostic Commands

```bash
CONTAINER=corecore-corecore-app-1

# Verbose test (cookie-free, mweb client)
docker exec $CONTAINER yt-dlp -v --skip-download \
  --extractor-args 'youtube:player_client=mweb' \
  --extractor-args 'youtubepot-bgutilhttp:base_url=http://pot-provider:4416' \
  --remote-components ejs:github \
  'https://www.youtube.com/watch?v=vKYIew27R0Y'

# Check versions
docker exec $CONTAINER yt-dlp --version
docker exec $CONTAINER deno --version
docker exec $CONTAINER pip show bgutil-ytdlp-pot-provider | grep Version

# Check pot-provider server version + logs
docker logs corecore-pot-provider-1 2>&1 | head -20

# Check Deno/EJS cache
docker exec $CONTAINER ls -la /root/.cache/yt-dlp/ 2>/dev/null
```

## Fallback Plan

If mweb + pot-provider alone doesn't work:
1. Try `player_client=["mweb","default"]` to add fallback clients
2. Re-add cookies but export from Firefox (not Chrome — [Chrome 127+ encrypts cookies](https://dev.to/osovsky/6-ways-to-get-youtube-cookies-for-yt-dlp-in-2026-only-1-works-2cnb))
3. Try the Rust pot-provider alternative: `ghcr.io/jim60105/yt-dlp:pot`

## History

### Mar 13, 2026 — Cookie-free approach
- Identified root cause: YouTube IP-binds cookies, invalidates on datacenter use
- Switched to `mweb` client + PO tokens (no cookies)
- Updated pot-provider to pull latest image

### Previous sessions
- Exported fresh cookies, fixed `remote_components` format (dict→list), added `cookies_update=False`
- First download succeeded but cookies were overwritten/invalidated
- Re-exported cookies still failed — YouTube had already blacklisted the session

## Community Context

- [PO Token Guide](https://github.com/yt-dlp/yt-dlp/wiki/PO-Token-Guide) — official guide, recommends mweb + PO token provider
- [Issue #10128](https://github.com/yt-dlp/yt-dlp/issues/10128) — original "Sign in to confirm" issue
- [Issue #8227](https://github.com/yt-dlp/yt-dlp/issues/8227) — cookies invalidated from different IP
- [bgutil-ytdlp-pot-provider](https://github.com/Brainicism/bgutil-ytdlp-pot-provider) — automatic PO token generation
- [yt-dlp EJS wiki](https://github.com/yt-dlp/yt-dlp/wiki/EJS) — JS challenge solver setup
