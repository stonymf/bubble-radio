#!/bin/bash

# Load environment variables from .env file
export $(grep -v '^#' .env | sed 's/#.*//' | xargs)

# Determine the directory of the current script
SCRIPT_DIR=$(dirname "$0")

# Ensure the logs directory exists
mkdir -p "$LOG_DIRECTORY"

# Print the environment variables to verify they're loaded correctly
echo "Loaded Environment Variables:"
echo "ICECAST_HOST=$ICECAST_HOST"
echo "ICECAST_PORT=$ICECAST_PORT"
echo "ICECAST_PASSWORD=$ICECAST_PASSWORD"
echo "PLAYLIST_DIRECTORY=$PLAYLIST_DIRECTORY"
echo "LIQUIDSOAP_PLAYLIST_TEMPLATE_PATH=$LIQUIDSOAP_PLAYLIST_TEMPLATE_PATH"
echo "LIQUIDSOAP_LIVE_TEMPLATE_PATH=$LIQUIDSOAP_LIVE_TEMPLATE_PATH" # Path to the live broadcast template
echo "LOG_DIRECTORY=$LOG_DIRECTORY"
echo "LIVE_STREAM_PORT=$LIVE_STREAM_PORT"
echo "--------------------------------"

# Generate and start a Liquidsoap instance for live broadcasting
LIVE_STREAM_SCRIPT="/tmp/live_stream.liq"
cp "$LIQUIDSOAP_LIVE_TEMPLATE_PATH" "$LIVE_STREAM_SCRIPT"

# Replace placeholders in the live broadcast script with actual values
sed -i "s|{{live_stream_port}}|$LIVE_STREAM_PORT|g" "$LIVE_STREAM_SCRIPT"
sed -i "s|{{host}}|$ICECAST_HOST|g" "$LIVE_STREAM_SCRIPT"
sed -i "s|{{icecast_port}}|$ICECAST_PORT|g" "$LIVE_STREAM_SCRIPT"
sed -i "s|{{password}}|$ICECAST_PASSWORD|g" "$LIVE_STREAM_SCRIPT"
sed -i "s|{{mount}}|/live|g" "$LIVE_STREAM_SCRIPT"

# Start the Liquidsoap instance for live broadcasting and redirect output to log file
LOG_FILE="$LOG_DIRECTORY/liq_live_stream.log"
liquidsoap "$LIVE_STREAM_SCRIPT" > "$LOG_FILE" 2>&1 &

echo "Started Liquidsoap Live Stream Session"

# Directory containing playlist files
PLAYLIST_DIR=$PLAYLIST_DIRECTORY

# Iterate over each .m3u file in the playlist directory
for playlist in "$PLAYLIST_DIR"/*.m3u; do
  # Extract the base name of the playlist file for use in Liquidsoap script
  playlist_name=$(basename "$playlist" .m3u)
  
  # Generate a Liquidsoap script for the playlist
  LIQUIDSOAP_SCRIPT="/tmp/${playlist_name}.liq"
  cp "$LIQUIDSOAP_PLAYLIST_TEMPLATE_PATH" "$LIQUIDSOAP_SCRIPT"
  
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
  LOG_FILE="$LOG_DIRECTORY/liq_${playlist_name}.log"
  liquidsoap "$LIQUIDSOAP_SCRIPT" > "$LOG_FILE" 2>&1 &
done

# Optionally, wait for all background processes to finish
wait