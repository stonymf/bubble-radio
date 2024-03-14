import os
import re
import sqlite3
import yt_dlp
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TIT2
from dotenv import load_dotenv
from logger_config import configure_logging

# Configure logging
logger = configure_logging('downloader.log', 'downloader_logger')

# Grab .env values
load_dotenv()
max_length = int(os.getenv("MAX_LENGTH"))

download_directory = "/usr/src/app/downloads"
db_path = "/usr/src/app/db.db"

# Ensure the download directory exists
if not os.path.exists(download_directory):
    os.makedirs(download_directory)

# Database setup
conn = sqlite3.connect(db_path)
cursor = conn.cursor()
cursor.execute(
    """
    CREATE TABLE IF NOT EXISTS downloads (
        id INTEGER PRIMARY KEY,
        title TEXT,
        username TEXT,
        channel_name TEXT,
        channel_id INTEGER,
        server_name TEXT,
        server_id INTEGER,
        timestamp DATETIME,
        url TEXT,
        filename TEXT,
        length REAL,
        last_added DATETIME
    )
    """
)
conn.commit()

def sanitize_filename(filename):
    """
    Sanitize the filename by replacing or removing special characters.
    """
    filename = re.sub(r"[：｜]", "", filename)  # Replace full-width characters
    filename = re.sub(r'[<>:"/\\|?*]', "", filename)  # Replace other problematic characters
    return filename

def get_disallowed_domains():
    with open('disallow.txt', 'r') as file:
        return [line.strip() for line in file]

def download_audio(url, user, timestamp, channel_name, channel_id, server_name, server_id):
    # Create database connection
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        disallowed_domains = get_disallowed_domains()
        domain = urlparse(url).netloc

        if any(domain.endswith(disallowed) for disallowed in disallowed_domains):
            logger.info(f"The domain {domain} is disallowed.")
            return "Error: The domain is disallowed."

        logger.info(f"Starting extraction info for URL: {url}")
        with yt_dlp.YoutubeDL({"format": "bestaudio/best", "skip_download": True}) as ydl:
            info_dict = ydl.extract_info(url, download=False)

        logger.info(f"Info extraction complete for URL: {url}")
        if not isinstance(info_dict, dict):
            logger.error(f"Error: Expected a dictionary for {url} but got {type(info_dict)}")
            return "Error: Expected a dictionary."

        duration = info_dict.get("duration", 0)
        if 0 < duration < max_length:
            original_title = info_dict.get("title", "Unknown Title")
            sanitized_title = sanitize_filename(original_title)
            outtmpl = os.path.join(download_directory, sanitized_title)

            ydl_opts = {
                "format": "bestaudio/best",
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }],
                "outtmpl": f"{outtmpl}.%(ext)s",
                "skip_download": False,
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl_download:
                logger.info(f"Starting download for URL: {url}")
                ydl_download.extract_info(url, download=True)
                logger.info(f"Download completed for URL: {url}")

            sanitized_mp3_filename = f"{sanitized_title}.mp3"
            mp3_file_path = os.path.join(download_directory, sanitized_mp3_filename)

            if os.path.exists(mp3_file_path):
                logger.info(f"File found, starting tagging: {sanitized_mp3_filename}")

                audio = MP3(mp3_file_path, ID3=ID3)
                length = audio.info.length

                try:
                    audio.add_tags()
                except Exception as e:
                    logger.info("Tags already present, continuing to update tags.")

                audio.tags.add(TIT2(encoding=3, text=sanitized_title))
                audio.save()

                logger.info(f"Tagging completed for: {sanitized_mp3_filename}")
                cursor.execute(
                    """
                    INSERT INTO downloads (title, username, timestamp, url, filename, length, channel_name, channel_id, server_name, server_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (sanitized_title, user, timestamp, url, sanitized_mp3_filename, float(length), channel_name, channel_id, server_name, server_id),
                )
                conn.commit()
                return "Success"
            else:
                logger.error(f"MP3 file not found after download: {sanitized_mp3_filename}")
                return "Error: MP3 file not found after download."
        else:
            logger.info(f"Skipping download due to length ({duration} seconds) for {url}")
            return "Error: Skipping download due to length."
    except Exception as e:
        logger.error(f"Error processing {url}: {e}", exc_info=True)
        return f"Error: {e}"