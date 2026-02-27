import io
import os
import threading
import time
import zipfile
from datetime import datetime
from flask import Blueprint, jsonify, render_template, request, redirect, url_for, send_file
from src.auth import requires_auth
from src.db import get_db
from src.logger_config import configure_logging
from src.config import PLAYLIST_DIR, DOWNLOAD_DIR

logger = configure_logging('app.log', 'app_logger')

bp = Blueprint('archive', __name__)

# Global archive state — requires single gunicorn worker
_lock = threading.Lock()
download_progress = {
    "status": "idle",
    "total_songs": 0,
    "processed_songs": 0,
    "current_playlist": "",
    "timestamp": "",
    "error": None
}
zip_creation_in_progress = False
zip_buffer = None


def create_archive_in_background():
    global download_progress, zip_creation_in_progress, zip_buffer

    try:
        logger.info("Starting background ZIP creation process")

        playlist_files = [f for f in os.listdir(PLAYLIST_DIR) if f.endswith('.m3u')]

        if not playlist_files:
            with _lock:
                download_progress["status"] = "error"
                download_progress["error"] = "No playlists found"
                zip_creation_in_progress = False
            logger.error("No playlist files found")
            return

        with get_db() as conn:
            cursor = conn.cursor()

            total_songs = 0
            playlist_songs = {}

            logger.info(f"Found {len(playlist_files)} playlist files, counting songs...")

            for playlist_file in playlist_files:
                playlist_path = os.path.join(PLAYLIST_DIR, playlist_file)
                try:
                    with open(playlist_path, 'r') as f:
                        mp3_paths = f.read().splitlines()
                        song_count = len(mp3_paths)
                        total_songs += song_count
                        playlist_songs[playlist_file] = mp3_paths
                        logger.info(f"Playlist {playlist_file}: {song_count} songs")
                except Exception as e:
                    logger.error(f"Error counting songs in playlist file {playlist_file}: {e}")

            with _lock:
                download_progress["total_songs"] = total_songs
                download_progress["status"] = "downloading"
            logger.info(f"Total songs to process: {total_songs}")

            new_zip_buffer = io.BytesIO()
            with zipfile.ZipFile(new_zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
                processed_songs = 0

                for playlist_file, mp3_paths in playlist_songs.items():
                    emoji_name = os.path.splitext(playlist_file)[0]
                    with _lock:
                        download_progress["current_playlist"] = emoji_name
                    logger.info(f"Processing playlist: {emoji_name}")

                    for mp3_path in mp3_paths:
                        filename = os.path.basename(mp3_path)

                        cursor.execute("""
                            SELECT id, title FROM downloads WHERE filename = ?
                        """, (filename,))
                        song_data = cursor.fetchone()

                        if song_data:
                            song_id, title = song_data
                            file_path = os.path.join(DOWNLOAD_DIR, filename)

                            if os.path.exists(file_path):
                                zipf.write(file_path, arcname=f"{emoji_name}/{filename}")
                                logger.debug(f"Added file to ZIP: {emoji_name}/{filename}")
                            else:
                                logger.warning(f"File not found for song {title}: {file_path}")

                        processed_songs += 1
                        with _lock:
                            download_progress["processed_songs"] = processed_songs
                        if processed_songs % 10 == 0 or processed_songs == total_songs:
                            logger.info(f"Progress: {processed_songs}/{total_songs} songs processed ({int(processed_songs/total_songs*100)}%)")

                        time.sleep(0.01)

        new_zip_buffer.seek(0)

        with _lock:
            zip_buffer = new_zip_buffer
            download_progress["status"] = "complete"
        logger.info("ZIP creation completed successfully")

    except Exception as e:
        logger.error(f"Error in background ZIP creation: {e}", exc_info=True)
        with _lock:
            download_progress["status"] = "error"
            download_progress["error"] = str(e)
    finally:
        with _lock:
            zip_creation_in_progress = False


@bp.route("/feedthechao")
@requires_auth
def feed_the_chao():
    global download_progress, zip_creation_in_progress

    with _lock:
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


@bp.route("/download_archive")
@requires_auth
def download_all_playlists():
    global download_progress, zip_creation_in_progress, zip_buffer

    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    try:
        with _lock:
            if is_ajax and zip_creation_in_progress:
                return jsonify({
                    "status": "in_progress",
                    "message": "Someone is already downloading ~ Please try again in a few minutes"
                })

            if is_ajax and download_progress["status"] == "complete" and zip_buffer is not None:
                return jsonify({"status": "complete"})

        if not is_ajax and download_progress["status"] == "complete" and zip_buffer is not None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            return send_file(
                zip_buffer,
                mimetype='application/zip',
                as_attachment=True,
                download_name=f"corecore_{timestamp}.zip"
            )

        with _lock:
            if not zip_creation_in_progress:
                download_progress = {
                    "status": "preparing",
                    "total_songs": 0,
                    "processed_songs": 0,
                    "current_playlist": "Initializing...",
                    "timestamp": datetime.now().strftime("%Y%m%d_%H%M%S"),
                    "error": None
                }

                zip_creation_in_progress = True
                thread = threading.Thread(target=create_archive_in_background)
                thread.daemon = True
                thread.start()

                logger.info("Started background thread for ZIP creation")

                if is_ajax:
                    return jsonify({"status": "started"})

        return redirect(url_for('archive.feed_the_chao'))

    except Exception as e:
        logger.error(f"Error handling download request: {e}", exc_info=True)
        with _lock:
            download_progress["status"] = "error"
            download_progress["error"] = str(e)
        if is_ajax:
            return jsonify({"status": "error", "message": str(e)})
        return "Error creating archive", 500


@bp.route("/download_progress")
@requires_auth
def check_download_progress():
    global download_progress

    with _lock:
        if download_progress["total_songs"] > 0:
            percentage = int((download_progress["processed_songs"] / download_progress["total_songs"]) * 100)
        else:
            percentage = 0

        response = download_progress.copy()
        response["percentage"] = percentage

    return jsonify(response)
