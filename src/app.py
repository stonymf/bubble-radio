import os
import json
import sqlite3
import html
from urllib.parse import urlparse
from dotenv import load_dotenv
from src.downloader import download_audio
import requests
from flask import Flask, render_template, jsonify, request
from urllib.parse import unquote
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta

from src.logger_config import configure_logging
import src.playlists as playlists

logger = configure_logging('app.log', 'app_logger')

# Grab .env values
load_dotenv()
secret_key = os.getenv("SECRET_KEY")
base_stream_url = os.getenv("BASE_STREAM_URL")

db_path = "/usr/src/app/db.db"
playlist_directory = "/usr/src/app/playlists"

app = Flask(__name__)

scheduler = BackgroundScheduler()
scheduler.start()

def schedule_playlist_refresh(emoji_id, emoji_name, recent=False):
    # Generate the playlist and get its total runtime
    total_length = playlists.generate_playlist(emoji_id, emoji_name, recent)
    # Calculate the refresh interval based on total runtime
    refresh_interval = total_length 
    # Schedule the next refresh
    scheduler.add_job(schedule_playlist_refresh, 'date', run_date=datetime.now() + timedelta(seconds=refresh_interval), args=[emoji_id, emoji_name, recent])

    minutes, seconds = divmod(refresh_interval, 60)
    
    logger.info(f"Playlist for {emoji_name} ({'recent' if recent else 'all'}) created. Next refresh in {minutes} minutes and {seconds} seconds.")

def start_scheduling():
    logger.info("Starting scheduling...")
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        # Retrieve unique emoji_id and emoji_name combinations
        cursor.execute("SELECT DISTINCT emoji_id, emoji_name FROM downloads")
        server_inputs = cursor.fetchall()
        logger.info(f"Found {len(server_inputs)} unique emoji_id and emoji_name combinations.")
        for emoji_id, emoji_name in server_inputs:
            # Schedule both all-time and recent playlists for each unique combination
            schedule_playlist_refresh(emoji_id, emoji_name, recent=False)
            schedule_playlist_refresh(emoji_id, emoji_name, recent=True)
    except Exception as e:
        logger.error(f"Error occurred during scheduling: {e}")
    finally:
        conn.close()

start_scheduling()

def get_disallowed_domains():
    with open('disallow.txt', 'r') as file:
        return [line.strip() for line in file]
    
@app.route("/add_song", methods=['POST'])
def add_song():
    if request.headers.get("Authorization") != secret_key:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
    
    data = request.json
    url = data.get('url')
    user = data.get('user')
    timestamp = data.get('timestamp')
    channel_id = data.get('channel_id')
    server_id = data.get('server_id')
    emoji_name = data.get('emoji_name')
    emoji_id = extract_emoji_id(data.get('emoji_id'))
    
    result = download_audio(url, user, timestamp, channel_id, server_id, emoji_name, emoji_id)
    
    if result != "Success":
        return jsonify({"status": "error", "message": result}), 500
    else:
        return jsonify({"status": "success", "message": "Song added successfully."}), 200

def get_current_song_info(stream_name):
    try:
        # Fetch the JSON data from Icecast's JSON status page
        response = requests.get(base_stream_url + "/status-json.xsl")
        response.raise_for_status()

        data = json.loads(response.text)

        # Connect to the database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Initialize title and url
        title = "Unknown"
        url = "No URL provided"

        sources = data["icestats"]["source"]
        if isinstance(sources, dict):
            sources = [sources]  # Make it a list if it's a single dictionary

        # Navigate through the JSON to find your stream and extract the current song title
        for source in sources:
            if source["listenurl"].endswith(f"/{stream_name}"):
                title = source.get("title", "Unknown")
                if title != "Unknown":
                    title = html.unescape(title)  # Decode HTML entities

                # Query the database for the original URL
                cursor.execute("SELECT url FROM downloads WHERE title = ?", (title,))
                url_result = cursor.fetchone()
                if url_result:
                    url = url_result[0]

        # Close the database connection
        conn.close()
        return title, url

    except requests.RequestException as e:
        logger.error(f"Error fetching data from Icecast: {e}")
        return "Error fetching data", "No URL available"

    return "Unknown", "No URL provided"


@app.route("/get_original_url/<stream_name>")
def get_original_url(stream_name):
    stream_name = unquote(stream_name)
    title, _ = get_current_song_info(stream_name)
    # Assuming title is not "Unknown" or "Error fetching data"
    if title not in ["Unknown", "Error fetching data"]:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT url FROM downloads WHERE title = ?", (title,))
            url_result = cursor.fetchone()
            if url_result:
                return url_result[0]
    return "No URL provided"


@app.route("/demo/<stream_name>")
def stream(stream_name):
    title, url = get_current_song_info(stream_name)
    return render_template("stream.html", stream_name=stream_name, title=title, url=url, base_stream_url=base_stream_url)


@app.route("/demo")
def index():
    # Name streams based on playlist file names
    streams = [os.path.splitext(file)[0] for file in os.listdir(playlist_directory) if file.endswith('.m3u')]
    return render_template("index.html", streams=streams)

def extract_emoji_id(emoji_id_str):
    # This function is necessary as long as we're receiving `emoji_id` values from Bubble bot that
    # are inside of angle brackets, which is the raw data format vs the id number itself
    if not emoji_id_str:
        return None
    # Check if it's in Discord format <:name:id> or <a:name:id>
    if emoji_id_str.startswith('<') and emoji_id_str.endswith('>'):
        # Extract the last part after the last colon
        return emoji_id_str.split(':')[-1][:-1]
    return emoji_id_str

if __name__ == "__main__":
    start_scheduling()
    app.run(debug=True, host="0.0.0.0", port=5000)
    logger.info("Flask server started")

