#!/bin/bash
# Weekly rebuild of the app + bot images from scratch, so the unpinned yt-dlp
# (and the Python base image) stay current. The deploy cron only rebuilds when
# main changes, so without this yt-dlp freezes at whatever the last deploy
# installed and site fixes (Bandcamp, SoundCloud) never arrive.
# Run by cron on rashomon (see vibe.md). Recreates app, bot, streams and nginx,
# so the radio streams drop for a few seconds.
set -e
cd "$(dirname "$0")"
echo "[$(date -Is)] weekly rebuild"
docker compose build --pull --no-cache corecore-app corecore-bot
docker compose up -d
docker image prune -f
echo "yt-dlp $(docker compose exec -T corecore-app yt-dlp --version)"
