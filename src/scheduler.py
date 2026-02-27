import sqlite3
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from src.logger_config import configure_logging
from src.config import DB_PATH
import src.playlists as playlists

logger = configure_logging('app.log', 'app_logger')

scheduler = BackgroundScheduler()


def schedule_playlist_refresh(emoji_id, emoji_name):
    try:
        total_length = playlists.generate_playlist(emoji_id, emoji_name)
        refresh_interval = total_length
    except Exception as e:
        logger.error(f"Error generating playlist for {emoji_name}: {e}", exc_info=True)
        refresh_interval = 3600  # 1-hour fallback

    scheduler.add_job(
        schedule_playlist_refresh,
        'date',
        run_date=datetime.now() + timedelta(seconds=refresh_interval),
        args=[emoji_id, emoji_name],
        id=f"playlist_refresh_{emoji_name}",
        replace_existing=True,
    )

    minutes, seconds = divmod(refresh_interval, 60)
    logger.info(f"Playlist for {emoji_name} created. Next refresh in {minutes} minutes and {seconds} seconds.")


def start_scheduling():
    logger.info("Starting scheduling...")
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT emoji_id, emoji_name FROM downloads")
        server_inputs = cursor.fetchall()
        logger.info(f"Found {len(server_inputs)} unique emoji_id and emoji_name combinations.")
        for emoji_id, emoji_name in server_inputs:
            schedule_playlist_refresh(emoji_id, emoji_name)
    except Exception as e:
        logger.error(f"Error occurred during scheduling: {e}")
    finally:
        if conn:
            conn.close()


def init_scheduler():
    scheduler.start()
    start_scheduling()
