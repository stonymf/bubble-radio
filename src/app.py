import os
import json
import sqlite3
import html
from functools import wraps
from urllib.parse import urlparse
from dotenv import load_dotenv
from src.downloader import download_audio
import requests
from flask import Flask, render_template, jsonify, request, redirect, url_for, Response, send_file
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
# Read admin credentials from .env file with fallback defaults
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "bubbleradio")

db_path = "/usr/src/app/db.db"
playlist_directory = "/usr/src/app/playlists"

app = Flask(__name__)

# Basic authentication function
def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or auth.username != ADMIN_USERNAME or auth.password != ADMIN_PASSWORD:
            return Response(
                'Please login with valid credentials', 401,
                {'WWW-Authenticate': 'Basic realm="Admin Access"'})
        return f(*args, **kwargs)
    return decorated

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
    emoji_id = data.get('emoji_id')
 
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

@app.route("/admin")
@requires_auth
def admin():
    # Get all playlists and sort them alphabetically
    playlists = sorted([os.path.splitext(file)[0] for file in os.listdir(playlist_directory) if file.endswith('.m3u')])
    
    # Get songs for each playlist
    playlist_songs = {}
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    for playlist_name in playlists:
        # Extract emoji_name and whether it's recent or all
        parts = playlist_name.split('_')
        if len(parts) > 1:
            emoji_name = parts[0]
            playlist_type = parts[1]  # 'recent' or 'all'
            
            # Query to get songs for this playlist's emoji
            cursor.execute("""
                SELECT id, title, url, username, timestamp 
                FROM downloads 
                WHERE emoji_name = ? 
                ORDER BY timestamp DESC
            """, (emoji_name,))
            
            songs = [dict(row) for row in cursor.fetchall()]
            playlist_songs[playlist_name] = songs
    
    conn.close()
    
    return render_template("admin.html", playlists=playlists, playlist_songs=playlist_songs)

@app.route("/admin/edit_song", methods=['POST'])
@requires_auth
def edit_song():
    song_id = request.form.get('id')
    title = request.form.get('title')
    username = request.form.get('username')
    url = request.form.get('url')
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE downloads 
            SET title = ?, username = ?, url = ? 
            WHERE id = ?
        """, (title, username, url, song_id))
        conn.commit()
        
        # Also update the MP3 file title if possible (optional)
        cursor.execute("SELECT filename FROM downloads WHERE id = ?", (song_id,))
        filename = cursor.fetchone()
        if filename:
            try:
                import os
                from mutagen.mp3 import MP3
                from mutagen.id3 import ID3, TIT2
                mp3_path = os.path.join("/usr/src/app/downloads", filename[0])
                if os.path.exists(mp3_path):
                    audio = MP3(mp3_path, ID3=ID3)
                    audio.tags.add(TIT2(encoding=3, text=title))
                    audio.save()
                    logger.info(f"Updated MP3 tag for file: {filename[0]}")
            except Exception as e:
                logger.error(f"Error updating MP3 tag: {e}")
        
        # Trigger playlist refresh to reflect changes
        cursor.execute("SELECT emoji_id, emoji_name FROM downloads WHERE id = ?", (song_id,))
        emoji_info = cursor.fetchone()
        if emoji_info:
            emoji_id, emoji_name = emoji_info
            # Schedule playlist refresh for this emoji
            schedule_playlist_refresh(emoji_id, emoji_name, False)  # all-time playlist
            schedule_playlist_refresh(emoji_id, emoji_name, True)   # recent playlist
        
        conn.close()
        return jsonify({"status": "success"})
    except Exception as e:
        logger.error(f"Error updating song: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/admin/delete_song", methods=['POST'])
@requires_auth
def delete_song():
    song_id = request.form.get('id')
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Get emoji and filename info before deletion
        cursor.execute("SELECT emoji_id, emoji_name, filename FROM downloads WHERE id = ?", (song_id,))
        result = cursor.fetchone()
        if result:
            emoji_id, emoji_name, filename = result
            
            # Delete record from database
            cursor.execute("DELETE FROM downloads WHERE id = ?", (song_id,))
            conn.commit()
            
            # Remove MP3 file if possible (optional)
            try:
                import os
                mp3_path = os.path.join("/usr/src/app/downloads", filename)
                if os.path.exists(mp3_path):
                    os.remove(mp3_path)
                    logger.info(f"Deleted MP3 file: {filename}")
            except Exception as e:
                logger.error(f"Error deleting MP3 file: {e}")
            
            # Trigger playlist refresh to reflect changes
            schedule_playlist_refresh(emoji_id, emoji_name, False)  # all-time playlist
            schedule_playlist_refresh(emoji_id, emoji_name, True)   # recent playlist
        
        conn.close()
        return jsonify({"status": "success"})
    except Exception as e:
        logger.error(f"Error deleting song: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/download/<int:song_id>")
@requires_auth
def download(song_id):
    try:
        # Query the database to get the filename for the given song ID
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT filename FROM downloads WHERE id = ?", (song_id,))
        result = cursor.fetchone()
        conn.close()
        
        if result:
            filename = result[0]
            # Use the container path for downloads directory
            # In docker-compose.yml, DOWNLOAD_DIRECTORY is mapped to /usr/src/app/downloads
            file_path = os.path.join("/usr/src/app/downloads", filename)
            
            logger.info(f"Attempting to download file: {file_path}")
            
            # Check if the file exists
            if os.path.exists(file_path):
                return send_file(file_path, as_attachment=True)
            else:
                logger.error(f"File not found at path: {file_path}")
                return "File not found", 404
        else:
            return "Song not found", 404
    except Exception as e:
        logger.error(f"Error downloading file: {e}")
        return "Error processing download request", 500

if __name__ == "__main__":
    start_scheduling()
    app.run(debug=True, host="0.0.0.0", port=5000)
    logger.info("Flask server started")

