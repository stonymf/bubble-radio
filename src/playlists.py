import datetime
import os
import sqlite3
from dotenv import load_dotenv
from src.logger_config import configure_logging

def generate_playlist(emoji_id, emoji_name):
    logger = configure_logging('playlists.log', 'playlists_logger')
    load_dotenv()
    db_path = "/usr/src/app/db.db"
    playlist_dir = "/usr/src/app/playlists"
    base_mp3_path = "/usr/src/app/downloads"
    total_length = 0

    # Get the song count limit from .env
    song_limit = int(os.getenv('RECENT_SONG_COUNT', '100'))

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        playlist_name = f"{emoji_name}.m3u"
        logger.info(f'Generating playlist: {playlist_name}')

        # Get the most recent songs up to the count limit
        query = f"""
            SELECT filename, length 
            FROM downloads 
            WHERE emoji_id = ? AND emoji_name = ? 
            ORDER BY timestamp DESC 
            LIMIT {song_limit}
        """
        cursor.execute(query, (emoji_id, emoji_name))
        
        rows = cursor.fetchall()
        
        # Randomize the order of tracks for the playlist
        import random
        randomized_rows = list(rows)
        random.shuffle(randomized_rows)

        now = datetime.datetime.now()
        with open(os.path.join(playlist_dir, playlist_name), "w") as f:
            for row in randomized_rows:
                track_filename, length = row
                length = float(length)
                total_length += length
                mp3_file_path = os.path.join(base_mp3_path, track_filename)
                f.write(mp3_file_path + "\n")

                update_query = """
                               UPDATE downloads
                               SET last_added = ?
                               WHERE filename = ?
                               """
                cursor.execute(update_query, (now, track_filename))
        conn.commit()
        logger.info(f'Playlist {playlist_name} generated with total length: {total_length} seconds and {len(rows)} songs.')
    except Exception as e:
        logger.error(f'Error occurred: {e}', exc_info=True)
    finally:
        conn.close()

    return total_length

if __name__ == "__main__":
    generate_playlist()
