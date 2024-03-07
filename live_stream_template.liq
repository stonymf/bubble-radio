# Liquidsoap script template for live broadcasting

# Define a silent fallback source (which is also fallible)
silent_fallback = blank(duration = 1.0)

# Define the live input source
live_input = input.harbor("/live", port=8765, password="{{password}}", icy=true, max=10., buffer=3.)

# Fallback to silence if no live input is present
radio = fallback(track_sensitive = false, [live_input, silent_fallback])

# Define the Icecast output
output.icecast(%mp3,
  host = "{{host}}",
  port = {{port}},
  password = "{{password}}",
  mount = "{{mount}}",
  radio,
  fallible=true)