import html
import json
import os
from flask import Blueprint, render_template
from urllib.parse import unquote
import requests
from src.db import get_db
from src.logger_config import configure_logging
from src.config import BASE_STREAM_URL, ICECAST_INTERNAL_URL, PLAYLIST_DIR

logger = configure_logging('app.log', 'app_logger')

bp = Blueprint('streams', __name__)


def get_current_song_info(stream_name):
    try:
        response = requests.get(ICECAST_INTERNAL_URL + "/status-json.xsl")
        response.raise_for_status()

        data = json.loads(response.text)

        with get_db() as conn:
            cursor = conn.cursor()

            title = "Unknown"
            url = "No URL provided"

            sources = data["icestats"]["source"]
            if isinstance(sources, dict):
                sources = [sources]

            for source in sources:
                if source["listenurl"].endswith(f"/{stream_name}"):
                    title = source.get("title", "Unknown")
                    if title != "Unknown":
                        title = html.unescape(title)

                    cursor.execute("SELECT url FROM downloads WHERE title = ?", (title,))
                    url_result = cursor.fetchone()
                    if url_result:
                        url = url_result[0]

            return title, url

    except requests.RequestException as e:
        logger.error(f"Error fetching data from Icecast: {e}")
        return "Error fetching data", "No URL available"


@bp.route("/get_original_url/<stream_name>")
def get_original_url(stream_name):
    stream_name = unquote(stream_name)
    title, _ = get_current_song_info(stream_name)
    if title not in ["Unknown", "Error fetching data"]:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT url FROM downloads WHERE title = ?", (title,))
            url_result = cursor.fetchone()
            if url_result:
                return url_result[0]
    return "No URL provided"


@bp.route("/demo/<stream_name>")
def stream(stream_name):
    title, url = get_current_song_info(stream_name)
    return render_template("stream.html", stream_name=stream_name, title=title, url=url, base_stream_url=BASE_STREAM_URL)


@bp.route("/demo")
def index():
    streams = [os.path.splitext(file)[0] for file in os.listdir(PLAYLIST_DIR) if file.endswith('.m3u')]
    return render_template("index.html", streams=streams)
