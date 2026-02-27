import os
from flask import Blueprint, jsonify, request, render_template
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TIT2
from src.auth import requires_auth
from src.db import get_db
from src.scheduler import schedule_playlist_refresh
from src.logger_config import configure_logging
from src.config import PLAYLIST_DIR, DOWNLOAD_DIR, RECENT_SONG_COUNT

logger = configure_logging('app.log', 'app_logger')

bp = Blueprint('admin', __name__)


@bp.route("/admin")
@requires_auth
def admin():
    with get_db() as conn:
        conn.row_factory = __import__('sqlite3').Row
        cursor = conn.cursor()

        cursor.execute("SELECT DISTINCT emoji_name FROM downloads")
        emoji_names = [row['emoji_name'] for row in cursor.fetchall()]
        emoji_names.sort()

        stations = {}

        for emoji_name in emoji_names:
            cursor.execute("""
                SELECT id, title, url, username, timestamp
                FROM downloads
                WHERE emoji_name = ?
                ORDER BY timestamp DESC
            """, (emoji_name,))
            all_songs = [dict(row) for row in cursor.fetchall()]

            playlist = []

            try:
                playlist_path = os.path.join(PLAYLIST_DIR, f"{emoji_name}.m3u")

                if os.path.exists(playlist_path):
                    with open(playlist_path, 'r') as f:
                        mp3_paths = f.read().splitlines()
                        for mp3_path in mp3_paths:
                            filename = os.path.basename(mp3_path)
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

            stations[emoji_name] = {
                'all': all_songs,
                'playlist': playlist
            }

    return render_template("admin.html", stations=stations)


@bp.route("/admin/edit_song", methods=['POST'])
@requires_auth
def edit_song():
    song_id = request.form.get('id')
    title = request.form.get('title')
    username = request.form.get('username')
    url = request.form.get('url')

    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE downloads
                SET title = ?, username = ?, url = ?
                WHERE id = ?
            """, (title, username, url, song_id))
            conn.commit()

            cursor.execute("SELECT filename FROM downloads WHERE id = ?", (song_id,))
            filename = cursor.fetchone()
            if filename:
                try:
                    mp3_path = os.path.join(DOWNLOAD_DIR, filename[0])
                    if os.path.exists(mp3_path):
                        audio = MP3(mp3_path, ID3=ID3)
                        audio.tags.add(TIT2(encoding=3, text=title))
                        audio.save()
                        logger.info(f"Updated MP3 tag for file: {filename[0]}")
                except Exception as e:
                    logger.error(f"Error updating MP3 tag: {e}")

            cursor.execute("SELECT emoji_id, emoji_name FROM downloads WHERE id = ?", (song_id,))
            emoji_info = cursor.fetchone()
            if emoji_info:
                emoji_id, emoji_name = emoji_info
                schedule_playlist_refresh(emoji_id, emoji_name)

        return jsonify({"status": "success"})
    except Exception as e:
        logger.error(f"Error updating song: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@bp.route("/admin/delete_song", methods=['POST'])
@requires_auth
def delete_song():
    song_id = request.form.get('id')

    try:
        with get_db() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT emoji_id, emoji_name, filename FROM downloads WHERE id = ?", (song_id,))
            result = cursor.fetchone()
            if result:
                emoji_id, emoji_name, filename = result

                cursor.execute("DELETE FROM downloads WHERE id = ?", (song_id,))
                conn.commit()

                try:
                    mp3_path = os.path.join(DOWNLOAD_DIR, filename)
                    if os.path.exists(mp3_path):
                        os.remove(mp3_path)
                        logger.info(f"Deleted MP3 file: {filename}")
                except Exception as e:
                    logger.error(f"Error deleting MP3 file: {e}")

                schedule_playlist_refresh(emoji_id, emoji_name)

        return jsonify({"status": "success"})
    except Exception as e:
        logger.error(f"Error deleting song: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
