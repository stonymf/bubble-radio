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

from src.logger_config import configure_logging
import src.playlists as playlists

logger = configure_logging('app.log', 'app_logger')

# Grab .env values
load_dotenv()
secret_key = os.getenv("SECRET_KEY")
playlist_max_length = int(os.getenv("PLAYLIST_MAX_LENGTH"))
flask_port = os.getenv("FLASK_PORT")
base_stream_url = os.getenv("BASE_STREAM_URL")

db_path = "/usr/src/app/db.db"
playlist_directory = "/usr/src/app/playlists"

app = Flask(__name__)

# Generate playlists and then initialize scheduler to do it periodically
playlists.generate_playlists()
scheduler = BackgroundScheduler()
scheduler.add_job(playlists.generate_playlists, 'interval', hours=playlist_max_length)
scheduler.start()

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
    channel_name = data.get('channel_name')
    channel_id = data.get('channel_id')
    server_name = data.get('server_name')
    server_id = data.get('server_id')
    
    result = download_audio(url, user, timestamp, channel_name, channel_id, server_name, server_id)
    
    if result != "Success":
        return jsonify({"status": "error", "message": result}), 500
    else:
        return jsonify({"status": "success", "message": "Song added successfully."}), 200

def get_current_song_info(stream_name):
    try:
        # Fetch the JSON data from Icecast's JSON status page
        response = requests.get(base_stream_url + "/status-json.xsl")
        response.raise_for_status()  # Will raise an exception for HTTP errors

        # Parse the JSON
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


@app.route("/stream/<stream_name>")
def stream(stream_name):
    title, url = get_current_song_info(stream_name)
    return render_template("stream.html", stream_name=stream_name, title=title, url=url, base_stream_url=base_stream_url)


@app.route("/")
def index():
    # Name streams based on playlist file names
    streams = [os.path.splitext(file)[0] for file in os.listdir(playlist_directory) if file.endswith('.m3u')]
    return render_template("index.html", streams=streams)

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=flask_port)

    logger.info("Flask server started")
