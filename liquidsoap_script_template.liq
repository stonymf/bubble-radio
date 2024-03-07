# Liquidsoap script template

# Define the playlist
playlist_{{stream_name}} = playlist(mode="normal", reload=86400, "{{playlist_path}}")

# Define a silent fallback source (which is also fallible)
silent_fallback = blank(duration = 1.0)

# Define the live input source
# Replace `your_harbor_password` with a secure password
# The mount point here is `/live`, adjust as needed
live_input = input.harbor("/live", port={{port}}, password="{{password}}", icy=true, max=10., buffer=3.)

# Combine the live input, playlist, and silent fallback
# The order here means live input is preferred over the playlist, which is preferred over silence
radio = fallback(track_sensitive = false, [live_input, playlist_{{stream_name}}, silent_fallback])

# Define the Icecast output
output.icecast(%mp3,
  host = "{{host}}",
  port = {{port}},
  password = "{{password}}",
  mount = "{{mount}}",
  radio,
  fallible=true)