import os
from dotenv import load_dotenv

load_dotenv()

# Base directory — all paths derived from this
BASE_DIR = os.getenv("BASE_DIR", "/usr/src/app")

# Derived paths
DB_PATH = os.path.join(BASE_DIR, "db.db")
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
PLAYLIST_DIR = os.path.join(BASE_DIR, "playlists")
LOG_DIR = os.path.join(BASE_DIR, "logs")
IDENTS_DIR = os.path.join(BASE_DIR, "idents")
COOKIE_FILE = os.path.join(BASE_DIR, "cookies", "youtube.com.txt")
DISALLOW_FILE = os.path.join(BASE_DIR, "disallow.txt")

# App settings
SECRET_KEY = os.getenv("SECRET_KEY", "change-me")
BASE_STREAM_URL = os.getenv("BASE_STREAM_URL", "https://stream.void.beauty")
ICECAST_INTERNAL_URL = os.getenv("ICECAST_INTERNAL_URL", "http://bubble-radio-icecast:8000")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "bubbleradio")
MAX_LENGTH = int(os.getenv("MAX_LENGTH", "4140"))
RECENT_SONG_COUNT = int(os.getenv("RECENT_SONG_COUNT", "100"))
ENABLE_IDENTS = os.getenv("ENABLE_IDENTS", "false").lower() == "true"
IDENT_INTERVAL = int(os.getenv("IDENT_INTERVAL", "8"))

# Discord bot
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
DISCORD_REACT_THRESHOLD = int(os.getenv("DISCORD_REACT_THRESHOLD", "3"))


def get_disallowed_domains():
    try:
        with open(DISALLOW_FILE, "r") as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        return []
