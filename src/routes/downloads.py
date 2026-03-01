import io
import json
import os
import zipfile
from datetime import datetime
from flask import Blueprint, jsonify, send_file
from src.auth import requires_auth
from src.db import get_db
from src.logger_config import configure_logging
from src.config import DOWNLOAD_DIR

logger = configure_logging('app.log', 'app_logger')

bp = Blueprint('downloads', __name__)


@bp.route("/download/<int:song_id>")
@requires_auth
def download(song_id):
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT filename FROM downloads WHERE id = ?", (song_id,))
            result = cursor.fetchone()

        if result:
            filename = result[0]
            file_path = os.path.join(DOWNLOAD_DIR, filename)

            logger.info(f"Attempting to download file: {file_path}")

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


@bp.route("/play/<int:song_id>")
@requires_auth
def play(song_id):
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT filename FROM downloads WHERE id = ?", (song_id,))
            result = cursor.fetchone()

        if result:
            filename = result[0]
            file_path = os.path.join(DOWNLOAD_DIR, filename)

            if os.path.exists(file_path):
                return send_file(file_path, mimetype='audio/mpeg')
            else:
                return "File not found", 404
        else:
            return "Song not found", 404
    except Exception as e:
        logger.error(f"Error playing file: {e}")
        return "Error processing play request", 500


@bp.route("/download_playlist/<playlist_name>")
@requires_auth
def download_playlist(playlist_name):
    try:
        emoji_name = playlist_name

        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, title, filename FROM downloads WHERE emoji_name = ?", (emoji_name,))
            songs = cursor.fetchall()

        if not songs:
            return "No songs found for this playlist", 404

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for song_id, title, filename in songs:
                file_path = os.path.join(DOWNLOAD_DIR, filename)
                if os.path.exists(file_path):
                    zipf.write(file_path, arcname=filename)
                else:
                    logger.warning(f"File not found for song {title}: {file_path}")

        zip_buffer.seek(0)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        return send_file(
            zip_buffer,
            mimetype='application/zip',
            as_attachment=True,
            download_name=f"{emoji_name}_{timestamp}.zip"
        )
    except Exception as e:
        logger.error(f"Error creating playlist ZIP: {e}")
        return "Error creating playlist ZIP", 500


@bp.route("/download_db")
@requires_auth
def download_db():
    try:
        with get_db() as conn:
            conn.row_factory = __import__('sqlite3').Row
            cursor = conn.cursor()

            # Hardcoded table name to prevent SQL injection
            cursor.execute("SELECT * FROM downloads")
            rows = cursor.fetchall()

            table_data = []
            for row in rows:
                row_dict = {key: row[key] for key in row.keys()}
                table_data.append(row_dict)

            database_export = {"downloads": table_data}

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        json_str = json.dumps(database_export, indent=4)

        mem = io.BytesIO()
        mem.write(json_str.encode('utf-8'))
        mem.seek(0)

        return send_file(
            mem,
            mimetype='application/json',
            as_attachment=True,
            download_name=f"corecore_db_{timestamp}.json"
        )
    except Exception as e:
        logger.error(f"Error exporting database: {e}")
        return "Error exporting database", 500
