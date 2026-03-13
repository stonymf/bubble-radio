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

bp = Blueprint('admin', __name__, url_prefix=None)
bp.strict_slashes = False


@bp.route("/admin", strict_slashes=False)
@requires_auth
def admin():
    with get_db() as conn:
        conn.row_factory = __import__('sqlite3').Row
        cursor = conn.cursor()

        cursor.execute("SELECT DISTINCT emoji_id, emoji_name FROM downloads")
        station_map = {row['emoji_name']: row['emoji_id'] for row in cursor.fetchall()}
        emoji_names = sorted(station_map.keys())

        stations = {}

        for emoji_name in emoji_names:
            cursor.execute("""
                SELECT id, title, url, username, timestamp, filename
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
                                SELECT id, title, url, username, timestamp, filename
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

    return render_template("admin.html", stations=stations, station_map=station_map)


@bp.route("/admin/search")
@requires_auth
def search():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify([])

    with get_db() as conn:
        conn.row_factory = __import__('sqlite3').Row
        rows = conn.execute("""
            SELECT id, title, url, username, timestamp, filename, emoji_name
            FROM downloads
            WHERE title LIKE ? OR username LIKE ? OR url LIKE ?
            ORDER BY timestamp DESC
            LIMIT 50
        """, (f"%{q}%", f"%{q}%", f"%{q}%")).fetchall()

    return jsonify([dict(r) for r in rows])


@bp.route("/admin/edit_song", methods=['POST'])
@requires_auth
def edit_song():
    song_id = request.form.get('id')
    title = request.form.get('title')
    username = request.form.get('username')
    url = request.form.get('url')
    new_emoji_name = request.form.get('emoji_name')
    new_emoji_id = request.form.get('emoji_id')

    try:
        with get_db() as conn:
            cursor = conn.cursor()

            # Get current station before update
            cursor.execute("SELECT emoji_id, emoji_name, filename FROM downloads WHERE id = ?", (song_id,))
            old = cursor.fetchone()
            if not old:
                return jsonify({"status": "error", "message": "Song not found"}), 404
            old_emoji_id, old_emoji_name, filename = old

            # Build update
            if new_emoji_name and new_emoji_id:
                cursor.execute("""
                    UPDATE downloads
                    SET title = ?, username = ?, url = ?, emoji_name = ?, emoji_id = ?
                    WHERE id = ?
                """, (title, username, url, new_emoji_name, new_emoji_id, song_id))
            else:
                cursor.execute("""
                    UPDATE downloads
                    SET title = ?, username = ?, url = ?
                    WHERE id = ?
                """, (title, username, url, song_id))
            conn.commit()

            # Update MP3 tag
            if filename:
                try:
                    mp3_path = os.path.join(DOWNLOAD_DIR, filename)
                    if os.path.exists(mp3_path):
                        audio = MP3(mp3_path, ID3=ID3)
                        audio.tags.add(TIT2(encoding=3, text=title))
                        audio.save()
                        logger.info(f"Updated MP3 tag for file: {filename}")
                except Exception as e:
                    logger.error(f"Error updating MP3 tag: {e}")

            # Refresh old station playlist
            schedule_playlist_refresh(old_emoji_id, old_emoji_name)

            # If station changed, refresh new station too
            if new_emoji_name and new_emoji_name != old_emoji_name:
                schedule_playlist_refresh(new_emoji_id, new_emoji_name)

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
