# Liquidsoap script template

# Define the playlist
playlist_{{stream_name}} = playlist(mode="normal", reload=86400, "{{playlist_path}}")

# Define a silent fallback source (which is also fallible)
silent_fallback = blank(duration = 1.0)

# Combine the playlist with the silent fallback
radio = fallback(track_sensitive = false, [playlist_{{stream_name}}, silent_fallback])

# Define the Icecast output
output.icecast(%mp3,
  host = "{{host}}",
  port = {{port}},
  password = "{{password}}",
  mount = "{{mount}}",
  radio,
  fallible=true)