import datetime
import os
import random
import sqlite3
from src.logger_config import configure_logging
from src.config import DB_PATH, PLAYLIST_DIR, DOWNLOAD_DIR, IDENTS_DIR, RECENT_SONG_COUNT, ENABLE_IDENTS, IDENT_INTERVAL


def generate_playlist(emoji_id, emoji_name):
    logger = configure_logging('playlists.log', 'playlists_logger')
    total_length = 0

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        playlist_name = f"{emoji_name}.m3u"
        logger.info(f'Generating playlist: {playlist_name}')

        query = f"""
            SELECT filename, length
            FROM downloads
            WHERE emoji_id = ? AND emoji_name = ?
            ORDER BY timestamp DESC
            LIMIT {RECENT_SONG_COUNT}
        """
        cursor.execute(query, (emoji_id, emoji_name))

        rows = cursor.fetchall()

        randomized_rows = list(rows)
        random.shuffle(randomized_rows)

        ident_file = None
        if ENABLE_IDENTS:
            ident_path = os.path.join(IDENTS_DIR, f"{emoji_name}.mp3")
            if os.path.exists(ident_path):
                ident_file = ident_path
                logger.info(f'Found ident for {emoji_name}: {ident_file}')
            else:
                logger.info(f'No ident found for {emoji_name}, skipping idents')

        now = datetime.datetime.now()
        with open(os.path.join(PLAYLIST_DIR, playlist_name), "w") as f:
            song_count = 0

            for row in randomized_rows:
                track_filename, length = row
                length = float(length)
                total_length += length
                mp3_file_path = os.path.join(DOWNLOAD_DIR, track_filename)
                f.write(mp3_file_path + "\n")
                song_count += 1

                if (ident_file and
                    song_count % IDENT_INTERVAL == 0 and
                    song_count < len(randomized_rows)):
                    f.write(ident_file + "\n")
                    logger.info(f'Added ident after song {song_count}')

                update_query = """
                               UPDATE downloads
                               SET last_added = ?
                               WHERE filename = ?
                               """
                cursor.execute(update_query, (now, track_filename))

        conn.commit()
        logger.info(f'Playlist {playlist_name} generated with total length: {total_length} seconds and {len(rows)} songs.')
        if ident_file:
            logger.info(f'Idents enabled for {emoji_name} with interval: {IDENT_INTERVAL}')
    except Exception as e:
        logger.error(f'Error occurred: {e}', exc_info=True)
    finally:
        conn.close()

    return total_length


if __name__ == "__main__":
    generate_playlist()
