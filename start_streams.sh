#!/bin/bash

# Load environment variables from .env file
export $(grep -v '^#' .env | sed 's/#.*//' | xargs)

# Flask server readiness check using nc
# FLASK_READY_HOST="localhost"
# FLASK_READY_PORT="${FLASK_PORT}" # Adjust if you have a specific health check endpoint

# echo "Waiting for Flask server to be ready..."
# while ! nc -z $FLASK_READY_HOST $FLASK_READY_PORT; do
#     printf '.'
#     sleep 5
# done
# echo "Flask server is ready."

# Determine the directory of the current script
SCRIPT_DIR=$(dirname "$0")

# Ensure the logs directory exists
mkdir -p "/usr/src/app/logs"

# Print the environment variables to verify they're loaded correctly
echo "Loaded Environment Variables:"
echo "ICECAST_HOST=$ICECAST_HOST"
echo "ICECAST_PORT=$ICECAST_PORT"
echo "ICECAST_PASSWORD=$ICECAST_PASSWORD"
echo "PLAYLIST_DIRECTORY=/usr/src/app/playlists"
echo "LIQUIDSOAP_PLAYLIST_TEMPLATE_PATH=/usr/src/app/liq_config/playlist_stream_template.liq.tmp"
echo "LIQUIDSOAP_LIVE_TEMPLATE_PATH=/usr/src/app/liq_config/live_stream_template.liq.tmp" # Path to the live broadcast template
echo "LOG_DIRECTORY=/usr/src/app/logs"
echo "LIVE_STREAM_PORT=$LIVE_STREAM_PORT"
echo "--------------------------------"

# Generate and start a Liquidsoap instance for live broadcasting
LIVE_STREAM_SCRIPT="/usr/src/app/liq_config/live_stream.liq"
cp "/usr/src/app/liq_config/live_stream_template.liq.tmp" "$LIVE_STREAM_SCRIPT"

# Replace placeholders in the live broadcast script with actual values
sed -i "s|{{live_stream_port}}|$LIVE_STREAM_PORT|g" "$LIVE_STREAM_SCRIPT"
sed -i "s|{{host}}|$ICECAST_HOST|g" "$LIVE_STREAM_SCRIPT"
sed -i "s|{{icecast_port}}|$ICECAST_PORT|g" "$LIVE_STREAM_SCRIPT"
sed -i "s|{{password}}|$ICECAST_PASSWORD|g" "$LIVE_STREAM_SCRIPT"
sed -i "s|{{mount}}|/live|g" "$LIVE_STREAM_SCRIPT"

# Start the Liquidsoap instance for live broadcasting and redirect output to log file
LOG_FILE="/usr/src/app/logs/liq_live_stream.log"
liquidsoap "$LIVE_STREAM_SCRIPT" > "$LOG_FILE" 2>&1 &

echo "Started Liquidsoap Live Stream Session"

# Directory containing playlist files
PLAYLIST_DIR="/usr/src/app/playlists"

# Iterate over each .m3u file in the playlist directory
for playlist in "$PLAYLIST_DIR"/*.m3u; do
  # Extract the base name of the playlist file for use in Liquidsoap script
  playlist_name=$(basename "$playlist" .m3u)
  
  # Generate a Liquidsoap script for the playlist
  LIQUIDSOAP_SCRIPT="/usr/src/app/liq_config/${playlist_name}.liq"
  cp "/usr/src/app/liq_config/playlist_stream_template.liq.tmp" "$LIQUIDSOAP_SCRIPT"
  
  # Replace placeholders in the Liquidsoap script with actual values
  sed -i "s|{{playlist_path}}|$playlist|g" "$LIQUIDSOAP_SCRIPT"
  sed -i "s|{{stream_name}}|$playlist_name|g" "$LIQUIDSOAP_SCRIPT"
  sed -i "s|{{host}}|$ICECAST_HOST|g" "$LIQUIDSOAP_SCRIPT"
  sed -i "s|{{icecast_port}}|$ICECAST_PORT|g" "$LIQUIDSOAP_SCRIPT"
  sed -i "s|{{password}}|$ICECAST_PASSWORD|g" "$LIQUIDSOAP_SCRIPT"
  sed -i "s|{{mount}}|/$playlist_name|g" "$LIQUIDSOAP_SCRIPT"
  
  # Print the final Liquidsoap script to verify the replacements
  echo "Generated Liquidsoap Script for $playlist_name:"
  cat "$LIQUIDSOAP_SCRIPT"
  echo "--------------------------------"
  
  # Start a Liquidsoap instance for the generated script and redirect output to log file
  LOG_FILE="/usr/src/app/logs/liq_${playlist_name}.log"
  liquidsoap "$LIQUIDSOAP_SCRIPT" > "$LOG_FILE" 2>&1 &
done

# Optionally, wait for all background processes to finish
wait