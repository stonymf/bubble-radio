import os
import json
import sqlite3
import html
import io
import zipfile
import threading
import time
from functools import wraps
from urllib.parse import urlparse
from dotenv import load_dotenv
from src.downloader import download_audio
import requests
from flask import Flask, render_template, jsonify, request, redirect, url_for, Response, send_file, send_from_directory
from urllib.parse import unquote
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta

from src.logger_config import configure_logging
import src.playlists as playlists

# Global dictionary to store download progress
download_progress = {
    "status": "idle",  # idle, preparing, downloading, complete, error
    "total_songs": 0,
    "processed_songs": 0,
    "current_playlist": "",
    "timestamp": "",
    "error": None
}

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

app = Flask(__name__, 
            static_folder=os.path.join(os.path.dirname(__file__), "static"),
            static_url_path="/static")

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

def schedule_playlist_refresh(emoji_id, emoji_name):
    # Generate the playlist and get its total runtime
    total_length = playlists.generate_playlist(emoji_id, emoji_name)
    # Calculate the refresh interval based on total runtime
    refresh_interval = total_length 
    # Schedule the next refresh
    scheduler.add_job(schedule_playlist_refresh, 'date', run_date=datetime.now() + timedelta(seconds=refresh_interval), args=[emoji_id, emoji_name])

    minutes, seconds = divmod(refresh_interval, 60)
    
    logger.info(f"Playlist for {emoji_name} created. Next refresh in {minutes} minutes and {seconds} seconds.")

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
            # Schedule playlist generation for each unique combination
            schedule_playlist_refresh(emoji_id, emoji_name)
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
    # Get all unique emoji names
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT DISTINCT emoji_name FROM downloads")
    emoji_names = [row['emoji_name'] for row in cursor.fetchall()]
    emoji_names.sort()  # Sort alphabetically
    
    # Get the song count limit from .env
    song_limit = int(os.getenv('RECENT_SONG_COUNT', '100'))
    
    # Organize data by emoji name
    stations = {}
    
    for emoji_name in emoji_names:
        # Get all songs for this emoji
        cursor.execute("""
            SELECT id, title, url, username, timestamp 
            FROM downloads 
            WHERE emoji_name = ? 
            ORDER BY timestamp DESC
        """, (emoji_name,))
        all_songs = [dict(row) for row in cursor.fetchall()]
        
        # Get the actual playlist order from the m3u file
        playlist = []
        
        # Try to read the playlist file
        try:
            playlist_path = os.path.join(playlist_directory, f"{emoji_name}.m3u")
            
            if os.path.exists(playlist_path):
                with open(playlist_path, 'r') as f:
                    mp3_paths = f.read().splitlines()
                    for mp3_path in mp3_paths:
                        # Extract filename from path
                        filename = os.path.basename(mp3_path)
                        # Look up song details from the database
                        cursor.execute("""
                            SELECT id, title, url, username, timestamp 
                            FROM downloads 
                            WHERE filename = ?
                        """, (filename,))
                        song_data = cursor.fetchone()
                        if song_data:
                            playlist.append(dict(song_data))
        except Exception as e:
            logger.error(f"Error reading playlist for {emoji_name}: {e}")
        
        # Store all data for this emoji
        stations[emoji_name] = {
            'all': all_songs,
            'playlist': playlist
        }
    
    conn.close()
    
    return render_template("admin.html", stations=stations)

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
            schedule_playlist_refresh(emoji_id, emoji_name)
        
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
            schedule_playlist_refresh(emoji_id, emoji_name)
        
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

@app.route("/download_playlist/<playlist_name>")
@requires_auth
def download_playlist(playlist_name):
    try:
        # Use playlist_name directly as emoji_name
        emoji_name = playlist_name
        
        # Get songs for the specified playlist
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT id, title, filename FROM downloads WHERE emoji_name = ?", (emoji_name,))
        songs = cursor.fetchall()
        conn.close()
        
        if not songs:
            return "No songs found for this playlist", 404
        
        # Create a ZIP file in memory
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for song_id, title, filename in songs:
                file_path = os.path.join("/usr/src/app/downloads", filename)
                if os.path.exists(file_path):
                    # Add the file to the ZIP
                    zipf.write(file_path, arcname=filename)
                else:
                    logger.warning(f"File not found for song {title}: {file_path}")
        
        zip_buffer.seek(0)
        
        # Generate timestamp for the filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Return the ZIP file with a timestamped name
        return send_file(
            zip_buffer, 
            mimetype='application/zip',
            as_attachment=True, 
            download_name=f"{emoji_name}_{timestamp}.zip"
        )
    except Exception as e:
        logger.error(f"Error creating playlist ZIP: {e}")
        return "Error creating playlist ZIP", 500

@app.route("/feedthechao")
def feed_the_chao():
    """
    Show the download page with progress bar.
    The actual download will be initiated by client-side JavaScript.
    """
    # Only reset progress state if there's no download in progress
    global download_progress, zip_creation_in_progress
    
    # Don't reset anything if a download is already in progress
    if not zip_creation_in_progress:
        download_progress = {
            "status": "idle",
            "total_songs": 0,
            "processed_songs": 0,
            "current_playlist": "",
            "timestamp": datetime.now().strftime("%Y%m%d_%H%M%S"),
            "error": None
        }
    
    return render_template("download.html")

# ZIP creation in progress flag
zip_creation_in_progress = False
zip_buffer = None

def create_archive_in_background():
    """
    Background thread function to create the ZIP archive.
    Updates the global download_progress dictionary as it runs.
    """
    global download_progress, zip_creation_in_progress, zip_buffer
    
    try:
        logger.info("Starting background ZIP creation process")
        
        # Get all playlist files
        playlist_files = [f for f in os.listdir(playlist_directory) if f.endswith('.m3u')]
        
        if not playlist_files:
            download_progress["status"] = "error"
            download_progress["error"] = "No playlists found"
            zip_creation_in_progress = False
            logger.error("No playlist files found")
            return
        
        # Get songs from each playlist file
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # First, count total songs from all playlists
        total_songs = 0
        playlist_songs = {}
        
        logger.info(f"Found {len(playlist_files)} playlist files, counting songs...")
        
        for playlist_file in playlist_files:
            playlist_path = os.path.join(playlist_directory, playlist_file)
            try:
                with open(playlist_path, 'r') as f:
                    mp3_paths = f.read().splitlines()
                    song_count = len(mp3_paths)
                    total_songs += song_count
                    playlist_songs[playlist_file] = mp3_paths
                    logger.info(f"Playlist {playlist_file}: {song_count} songs")
            except Exception as e:
                logger.error(f"Error counting songs in playlist file {playlist_file}: {e}")
        
        download_progress["total_songs"] = total_songs
        download_progress["status"] = "downloading"
        logger.info(f"Total songs to process: {total_songs}")
        
        # Create a new ZIP file in memory
        new_zip_buffer = io.BytesIO()
        with zipfile.ZipFile(new_zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
            processed_songs = 0
            
            # Process each playlist file
            for playlist_file, mp3_paths in playlist_songs.items():
                emoji_name = os.path.splitext(playlist_file)[0]  # Get emoji name without extension
                download_progress["current_playlist"] = emoji_name
                logger.info(f"Processing playlist: {emoji_name}")
                
                # Process each song in the playlist
                for mp3_path in mp3_paths:
                    # Extract filename from path
                    filename = os.path.basename(mp3_path)
                    
                    # Get song details from database
                    cursor.execute("""
                        SELECT id, title FROM downloads WHERE filename = ?
                    """, (filename,))
                    song_data = cursor.fetchone()
                    
                    if song_data:
                        song_id, title = song_data
                        file_path = os.path.join("/usr/src/app/downloads", filename)
                        
                        if os.path.exists(file_path):
                            # Add the file to the ZIP in a folder named after the playlist
                            zipf.write(file_path, arcname=f"{emoji_name}/{filename}")
                            logger.debug(f"Added file to ZIP: {emoji_name}/{filename}")
                        else:
                            logger.warning(f"File not found for song {title}: {file_path}")
                    
                    # Update progress after each file and log every 10 files
                    processed_songs += 1
                    download_progress["processed_songs"] = processed_songs
                    if processed_songs % 10 == 0 or processed_songs == total_songs:
                        logger.info(f"Progress: {processed_songs}/{total_songs} songs processed ({int(processed_songs/total_songs*100)}%)")
                    
                    # Small sleep to ensure other threads can run
                    time.sleep(0.01)
        
        conn.close()
        new_zip_buffer.seek(0)
        
        # Update global ZIP buffer
        zip_buffer = new_zip_buffer
        
        # Update progress
        download_progress["status"] = "complete"
        logger.info("ZIP creation completed successfully")
        
    except Exception as e:
        logger.error(f"Error in background ZIP creation: {e}", exc_info=True)
        download_progress["status"] = "error"
        download_progress["error"] = str(e)
    finally:
        zip_creation_in_progress = False


@app.route("/download_archive")
def download_all_playlists():
    global download_progress, zip_creation_in_progress, zip_buffer
    
    # Check if this is an AJAX request from the progress page
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    
    try:
        # If AJAX request and ZIP creation already in progress, return status indicating it's already running
        if is_ajax and zip_creation_in_progress:
            return jsonify({
                "status": "in_progress",
                "message": "Someone is already downloading ~ Please try again in a few minutes"
            })
        
        # If AJAX request and ZIP is complete, return complete status
        if is_ajax and download_progress["status"] == "complete" and zip_buffer is not None:
            return jsonify({"status": "complete"})
        
        # If not AJAX request and ZIP is complete, send the file
        if not is_ajax and download_progress["status"] == "complete" and zip_buffer is not None:
            # Generate timestamp for the filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Return the ZIP file with a timestamped name
            return send_file(
                zip_buffer,
                mimetype='application/zip',
                as_attachment=True,
                download_name=f"corecore_{timestamp}.zip"
            )
        
        # Reset progress for a new ZIP creation process
        if not zip_creation_in_progress:
            download_progress = {
                "status": "preparing",
                "total_songs": 0,
                "processed_songs": 0,
                "current_playlist": "Initializing...",
                "timestamp": datetime.now().strftime("%Y%m%d_%H%M%S"),
                "error": None
            }
            
            # Start background thread for ZIP creation
            zip_creation_in_progress = True
            thread = threading.Thread(target=create_archive_in_background)
            thread.daemon = True
            thread.start()
            
            logger.info("Started background thread for ZIP creation")
            
            # If AJAX request, return started status
            if is_ajax:
                return jsonify({"status": "started"})
        
        # If direct request but ZIP not ready, redirect to feed_the_chao
        return redirect(url_for('feed_the_chao'))
            
    except Exception as e:
        logger.error(f"Error handling download request: {e}", exc_info=True)
        download_progress["status"] = "error"
        download_progress["error"] = str(e)
        if is_ajax:
            return jsonify({"status": "error", "message": str(e)})
        return "Error creating archive", 500

@app.route("/download_progress")
def check_download_progress():
    """Return the current download progress as JSON"""
    global download_progress
    
    # Calculate percentage
    if download_progress["total_songs"] > 0:
        percentage = int((download_progress["processed_songs"] / download_progress["total_songs"]) * 100)
    else:
        percentage = 0
    
    # Add percentage to the response
    response = download_progress.copy()
    response["percentage"] = percentage
    
    return jsonify(response)

@app.route("/static/<path:filename>")
def serve_static(filename):
    return send_from_directory(os.path.join(os.path.dirname(__file__), "static"), filename)

@app.route("/download_db")
@requires_auth
def download_db():
    try:
        # Connect to the database
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row  # This enables column access by name
        cursor = conn.cursor()
        
        # Get all tables in the database
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        
        # Create a dictionary to hold our database export
        database_export = {}
        
        # For each table, get all rows and add to the export
        for table in tables:
            table_name = table['name']
            cursor.execute(f"SELECT * FROM {table_name}")
            rows = cursor.fetchall()
            
            # Convert rows to list of dictionaries
            table_data = []
            for row in rows:
                row_dict = {key: row[key] for key in row.keys()}
                table_data.append(row_dict)
            
            database_export[table_name] = table_data
        
        conn.close()
        
        # Generate timestamp for the filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Create a JSON string from the dictionary
        json_str = json.dumps(database_export, indent=4)
        
        # Create a BytesIO object
        mem = io.BytesIO()
        mem.write(json_str.encode('utf-8'))
        mem.seek(0)
        
        # Return the JSON file
        return send_file(
            mem,
            mimetype='application/json',
            as_attachment=True,
            download_name=f"bubble_radio_db_{timestamp}.json"
        )
    except Exception as e:
        logger.error(f"Error exporting database: {e}")
        return "Error exporting database", 500

if __name__ == "__main__":
    start_scheduling()
    app.run(debug=True, host="0.0.0.0", port=5000)
    logger.info("Flask server started")

