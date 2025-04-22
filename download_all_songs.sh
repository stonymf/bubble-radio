#!/bin/bash

# Script to download all songs in the database

# Set good default values for stealth operation
ARGS="--delay-min 7.0 --delay-max 15.0 --batch-size 5 --batch-break 60.0 --browser chrome"

echo "Starting download of all songs in the database..."
echo "This might take a while depending on how many songs are missing."
echo "Using safe delay settings to avoid detection (7-15 sec between downloads, 60 sec break every 5 downloads)"
echo "Use Ctrl+C to stop the process at any time."
echo

# Run the Python script in the Docker container
docker exec bubble-radio-bubble-radio-app-1 python -m src.download_all_songs $ARGS

echo
echo "Download process completed." 