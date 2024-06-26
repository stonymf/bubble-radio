import datetime
import os
import sqlite3
from dotenv import load_dotenv
from src.logger_config import configure_logging

def generate_playlist(emoji_id, emoji_name, recent=False):
    logger = configure_logging('playlists.log', 'playlists_logger')
    load_dotenv()
    db_path = "/usr/src/app/db.db"
    playlist_dir = "/usr/src/app/playlists"
    base_mp3_path = "/usr/src/app/downloads"
    total_length = 0

    # Retrieve the time interval and minimum song count from the .env file
    recency_period = int(os.getenv('RECENCY_PERIOD', '30'))
    min_song_count = int(os.getenv('MIN_SONG_COUNT', '100'))

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        playlist_name = f"{emoji_name}_{'recent' if recent else 'all'}.m3u"
        logger.info(f'Generating playlist: {playlist_name}')

        query = """SELECT * FROM
                (SELECT filename, length
                FROM downloads
                WHERE emoji_id = ? AND emoji_name = ?
                ORDER BY timestamp DESC
                LIMIT 1)

                UNION

                SELECT * FROM
                (SELECT filename, length
                FROM downloads
                WHERE emoji_id = ? AND emoji_name = ?
                AND filename NOT IN (SELECT filename
                                     FROM downloads
                                     WHERE emoji_id = ? AND emoji_name = ?
                                     ORDER BY timestamp DESC
                                     LIMIT 1)"""
        if recent:
            query += f" AND JULIANDAY('now') - JULIANDAY(timestamp) <= {recency_period}"
        query += " ORDER BY RANDOM() * (JULIANDAY('now') - IFNULL(JULIANDAY(last_added), 0)) DESC);"

        cursor.execute(query, (emoji_id, emoji_name, emoji_id, emoji_name, emoji_id, emoji_name))
        rows = cursor.fetchall()

        # Check if the fetched songs are less than the minimum required
        if len(rows) < min_song_count:
            additional_songs_needed = min_song_count - len(rows)
            # Fetch additional songs, excluding the ones already selected
            additional_query = """SELECT filename, length FROM downloads
                                  WHERE emoji_id = ? AND emoji_name = ?
                                  AND filename NOT IN (SELECT filename FROM downloads
                                                       WHERE emoji_id = ? AND emoji_name = ?
                                                       ORDER BY timestamp DESC)
                                  ORDER BY RANDOM() LIMIT ?;"""
            cursor.execute(additional_query, (emoji_id, emoji_name, emoji_id, emoji_name, additional_songs_needed))
            additional_rows = cursor.fetchall()
            rows.extend(additional_rows)

        now = datetime.datetime.now()
        with open(os.path.join(playlist_dir, playlist_name), "w") as f:
            for row in rows:
                track_filename, length = row
                length = float(length)
                if total_length > 6 * 60 * 60:
                    break
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
