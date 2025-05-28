# Idents Directory

This directory contains ident audio files that are automatically interpolated into playlists.

## For Corecore Deployment

Place your ident MP3 files here with these exact names:

- `1radio.mp3` - Ident for the /1radio stream
- `2radio.mp3` - Ident for the /2radio stream  
- `3radio.mp3` - Ident for the /3radio stream

## File Requirements

- Files must be in MP3 format
- Keep files relatively short (5-30 seconds recommended)
- Ensure audio levels match your music content
- File names must exactly match the stream/emoji names

## Configuration

Enable idents in your `.env` file:

```bash
ENABLE_IDENTS=true
IDENT_INTERVAL=8  # Play ident every 8 songs
```

## For Other Deployments

For deployments with different stream names, simply name your ident files to match:
- `[emoji_name].mp3` - where emoji_name matches your stream name

The system will automatically detect and use any ident files that match existing stream names. 