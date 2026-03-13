import os
import tempfile
from flask import Blueprint, jsonify, request
from src.downloader import download_audio, _get_ydl_opts
from src.config import SECRET_KEY
from src.db import get_db
from src.logger_config import configure_logging
import yt_dlp

logger = configure_logging('app.log', 'app_logger')

bp = Blueprint('api', __name__)


@bp.route("/add_song", methods=['POST'])
def add_song():
    if request.headers.get("Authorization") != SECRET_KEY:
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


TEST_URLS = {
    "youtube": "https://www.youtube.com/watch?v=vKYIew27R0Y",
    "soundcloud": "https://soundcloud.com/innerinnerlife/balmy-feat-josephine-moriko",
    "bandcamp": "https://rimo5.bandcamp.com/track/revoc-izaguf-vomir",
}


@bp.route("/test_downloads", methods=['POST'])
def test_downloads():
    if request.headers.get("Authorization") != SECRET_KEY:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    results = {}
    for platform, url in TEST_URLS.items():
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                outtmpl = os.path.join(tmpdir, "test.%(ext)s")
                opts = _get_ydl_opts({
                    "postprocessors": [{
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "192",
                    }],
                    "outtmpl": outtmpl,
                })
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.extract_info(url, download=True)
                # Verify an mp3 was created
                files = [f for f in os.listdir(tmpdir) if f.endswith(".mp3")]
                if files:
                    results[platform] = {"status": "ok"}
                else:
                    results[platform] = {"status": "error", "message": "No MP3 file produced"}
        except Exception as e:
            logger.error(f"Download test failed for {platform}: {e}")
            results[platform] = {"status": "error", "message": str(e)}

    return jsonify(results), 200


@bp.route("/settings/<key>", methods=['GET'])
def get_setting(key):
    if request.headers.get("Authorization") != SECRET_KEY:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    with get_db() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    if row:
        return jsonify({"value": row[0]}), 200
    return jsonify({"value": None}), 404


@bp.route("/settings/<key>", methods=['PUT'])
def set_setting(key):
    if request.headers.get("Authorization") != SECRET_KEY:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    value = request.json.get("value")
    with get_db() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = ?",
            (key, value, value),
        )
        conn.commit()
    return jsonify({"status": "ok"}), 200
