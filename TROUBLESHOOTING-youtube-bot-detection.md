# YouTube "Sign in to confirm you're not a bot" — yt-dlp

## Status: RESOLVED (Mar 2026)

YouTube downloads now route through a residential IP proxy on smilerelax.net.

## Root Cause

YouTube blocks all yt-dlp player API requests from DigitalOcean datacenter IPs (165.232.x.x) with `LOGIN_REQUIRED`. This is IP-level detection — no client type (mweb, tv, android, web_safari), PO tokens, or cookies can bypass it. Cookies exported from residential IPs get invalidated on first use from datacenter.

## Solution

Lightweight download proxy on smilerelax.net (Beelink Mini S13 at restaurant, residential ISP IP):

```
Corecore (rashomon.blue)                    smilerelax.net
─────────────────────────                   ──────────────
_is_youtube_url(url)?
  ├─ No → local yt-dlp (SoundCloud, Bandcamp)
  └─ Yes → POST /cc/extract  ──Cloudflare──→  yt-dlp extract_info
           POST /cc/download ──Cloudflare──→  yt-dlp download → MP3
```

### Config

**Corecore `.env` on rashomon.blue:**
```
YT_PROXY_URL=https://smilerelax.net
YT_PROXY_SECRET=corecore-yt-proxy
```

**Proxy service on smilerelax.net:**
- Source: `villageglobal/cc-youtube/app.py`
- Systemd service: `cc-youtube`
- Port: 8999, route: `smilerelax.net/cc*` via Cloudflare tunnel
- Venv: `/home/village/cc-youtube/venv/`

### Redeploy proxy

```bash
cd ~/dev/villageglobal/cc-youtube && bash deploy.sh
```

### Diagnostic commands

```bash
# Test proxy health
curl https://smilerelax.net/cc/health

# Test extraction (no download)
curl -X POST https://smilerelax.net/cc/extract \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://www.youtube.com/watch?v=vKYIew27R0Y","secret":"corecore-yt-proxy"}'

# Check proxy logs on smilerelax.net
ssh village "sudo journalctl -u cc-youtube -n 50"

# Test all platforms from corecore
# (use !testdownloads in Discord, or hit /test_downloads endpoint)
```

## History

- **Mar 13, 2026** — Resolved via residential proxy. Tried mweb, tv, android, PO tokens — all blocked from datacenter IP.
- Earlier sessions — cookie export/import cycle, `cookies_update=False`, `remote_components` format fix. All ultimately failed due to IP-level blocking.
