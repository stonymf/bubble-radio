import os
import re
import sqlite3
import yt_dlp
from urllib.parse import urlparse
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TIT2
from src.logger_config import configure_logging
from src.config import DB_PATH, DOWNLOAD_DIR, COOKIE_FILE, MAX_LENGTH, get_disallowed_domains

logger = configure_logging('downloader.log', 'downloader_logger')


def init_db():
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS downloads (
            id INTEGER PRIMARY KEY,
            title TEXT,
            username TEXT,
            channel_id INTEGER,
            server_id INTEGER,
            emoji_name TEXT,
            emoji_id TEXT,
            timestamp DATETIME,
            url TEXT,
            filename TEXT,
            length REAL,
            last_added DATETIME
        )
        """
    )
    conn.commit()
    conn.close()


def sanitize_filename(filename):
    filename = re.sub(r"[:\uff5c]", "", filename)
    filename = re.sub(r'[<>:"/\\|?*]', "", filename)
    return filename


def _get_ydl_opts(extra_opts=None):
    opts = {
        "format": "bestaudio/best",
        "extractor_args": {
            "youtube": {"player_client": ["default"]},
            "youtubepot-bgutilhttp": {"base_url": ["http://pot-provider:4416"]},
        },
    }
    if os.path.exists(COOKIE_FILE):
        opts["cookiefile"] = COOKIE_FILE
    if extra_opts:
        opts.update(extra_opts)
    return opts


def _validate_url(url):
    disallowed_domains = get_disallowed_domains()
    domain = urlparse(url).netloc

    if any(domain.endswith(disallowed) for disallowed in disallowed_domains):
        logger.info(f"The domain {domain} is disallowed.")
        return "Error: The domain is disallowed."

    if "bandcamp.com/album/" in url:
        logger.info(f"Bandcamp album URL declined: {url}")
        return "Error: Bandcamp album URLs are not allowed."

    return None


def _extract_info(url):
    logger.info(f"Starting extraction info for URL: {url}")
    with yt_dlp.YoutubeDL(_get_ydl_opts({"skip_download": True})) as ydl:
        info_dict = ydl.extract_info(url, download=False)

    logger.info(f"Info extraction complete for URL: {url}")
    if not isinstance(info_dict, dict):
        raise ValueError(f"Expected a dictionary for {url} but got {type(info_dict)}")

    return info_dict


def _download_and_convert(url, outtmpl):
    ydl_opts = _get_ydl_opts({
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }],
        "outtmpl": f"{outtmpl}.%(ext)s",
        "skip_download": False,
    })

    with yt_dlp.YoutubeDL(ydl_opts) as ydl_download:
        logger.info(f"Starting download for URL: {url}")
        ydl_download.extract_info(url, download=True)
        logger.info(f"Download completed for URL: {url}")


def _tag_mp3(mp3_file_path, title):
    audio = MP3(mp3_file_path, ID3=ID3)
    length = audio.info.length

    try:
        audio.add_tags()
    except Exception:
        logger.info("Tags already present, continuing to update tags.")

    audio.tags.add(TIT2(encoding=3, text=title))
    audio.save()
    logger.info(f"Tagging completed for: {os.path.basename(mp3_file_path)}")
    return length


def download_audio(url, user, timestamp, channel_id, server_id, emoji_name, emoji_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        error = _validate_url(url)
        if error:
            return error

        cursor.execute(
            "SELECT id FROM downloads WHERE url = ? AND emoji_name = ?",
            (url, emoji_name)
        )
        if cursor.fetchone():
            logger.info(f"Duplicate URL in playlist {emoji_name}: {url}")
            return "Error: This song is already in this playlist."

        try:
            info_dict = _extract_info(url)
        except Exception as e:
            logger.error(f"Extraction failed for {url}: {e}")
            return "Error: Could not extract info from this URL. The site may not be supported or the link may be broken."

        duration = info_dict.get("duration", 0)
        if not (0 < duration < MAX_LENGTH):
            logger.info(f"Skipping download due to length ({duration} seconds) for {url}")
            return "Error: Skipping download due to length."

        original_title = info_dict.get("title", "Unknown Title")
        sanitized_title = sanitize_filename(original_title)
        outtmpl = os.path.join(DOWNLOAD_DIR, sanitized_title)

        _download_and_convert(url, outtmpl)

        sanitized_mp3_filename = f"{sanitized_title}.mp3"
        mp3_file_path = os.path.join(DOWNLOAD_DIR, sanitized_mp3_filename)

        if not os.path.exists(mp3_file_path):
            logger.error(f"MP3 file not found after download: {sanitized_mp3_filename}")
            return "Error: MP3 file not found after download."

        logger.info(f"File found, starting tagging: {sanitized_mp3_filename}")
        length = _tag_mp3(mp3_file_path, sanitized_title)

        cursor.execute(
            """
            INSERT INTO downloads (title, username, timestamp, url, filename, length, channel_id, server_id, emoji_name, emoji_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (sanitized_title, user, timestamp, url, sanitized_mp3_filename, float(length), channel_id, server_id, emoji_name, emoji_id),
        )
        conn.commit()
        return "Success"
    except Exception as e:
        logger.error(f"Error processing {url}: {e}", exc_info=True)
        return f"Error: {e}"
    finally:
        conn.close()


def download_file_only(url, user, timestamp, channel_id, server_id, emoji_name, emoji_id, existing_filename=None):
    try:
        error = _validate_url(url)
        if error:
            return error

        try:
            info_dict = _extract_info(url)
        except Exception as e:
            logger.error(f"Extraction failed for {url}: {e}")
            return "Error: Could not extract info from this URL. The site may not be supported or the link may be broken."

        duration = info_dict.get("duration", 0)
        if not (0 < duration < MAX_LENGTH):
            logger.info(f"Skipping download due to length ({duration} seconds) for {url}")
            return "Error: Skipping download due to length."

        if existing_filename:
            sanitized_title = os.path.splitext(existing_filename)[0]
        else:
            original_title = info_dict.get("title", "Unknown Title")
            sanitized_title = sanitize_filename(original_title)

        outtmpl = os.path.join(DOWNLOAD_DIR, sanitized_title)
        _download_and_convert(url, outtmpl)

        sanitized_mp3_filename = f"{sanitized_title}.mp3"
        mp3_file_path = os.path.join(DOWNLOAD_DIR, sanitized_mp3_filename)

        if not os.path.exists(mp3_file_path):
            logger.error(f"MP3 file not found after download: {sanitized_mp3_filename}")
            return "Error: MP3 file not found after download."

        logger.info(f"File found, starting tagging: {sanitized_mp3_filename}")
        _tag_mp3(mp3_file_path, sanitized_title)

        return "Success"
    except Exception as e:
        logger.error(f"Error processing {url}: {e}", exc_info=True)
        return f"Error: {e}"
