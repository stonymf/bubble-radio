import datetime
import os
import sqlite3
from dotenv import load_dotenv
from src.logger_config import configure_logging

def generate_playlists():
    logger = configure_logging('playlists.log', 'playlists_logger')

    logger.info("its startingggggg")

    # Grab .env values
    load_dotenv()
    playlist_max_length = int(os.getenv("PLAYLIST_MAX_LENGTH"))
    
    db_path = "/usr/src/app/db.db"
    playlist_dir = "/usr/src/app/playlists"
    base_mp3_path = "/usr/src/app/downloads"

    try:

        logger.info('inside tryyyyyyy')
        # Connect to the database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Retrieve unique server and channel combinations
        cursor.execute(
            """
            SELECT DISTINCT emoji_id, emoji_name
            FROM downloads
            """
        )
        server_inputs = cursor.fetchall()

        logger.info('server_inputs:')
        logger.info(server_inputs)

        def generate_playlist(playlist_name, emoji_name, emoji_id, recent=False):

            logger.info('insideeee generate_playlist before query')

            query = """
                    SELECT filename, length
                    FROM downloads
                    WHERE emoji_id = ? AND emoji_name = ?
                    """
            if recent:
                query += " AND JULIANDAY('now') - JULIANDAY(timestamp) <= 30"
            query += " ORDER BY RANDOM() * (JULIANDAY('now') - IFNULL(JULIANDAY(last_added), 0)) DESC"

            logger.info('after query')

            cursor.execute(query, (emoji_id, emoji_name))
            rows = cursor.fetchall()

            total_length = 0
            now = datetime.datetime.now()
            with open(os.path.join(playlist_dir, playlist_name), "w") as f:
                for row in rows:
                    track_filename, length = row
                    length = float(length)
                    if total_length > playlist_max_length * 60 * 60:
                        break
                    total_length += length
                    mp3_file_path = os.path.join(base_mp3_path, track_filename)
                    f.write(mp3_file_path + "\n")

                    query = """
                            UPDATE downloads
                            SET last_added = ?
                            WHERE filename = ?
                            """

                    cursor.execute(query, (now, track_filename))
            conn.commit()
            logger.info(f'Playlist {playlist_name} generated with total length: {total_length} seconds.')

        # Generate playlists for each server and channel
        for emoji_id, emoji_name in server_inputs:
            generate_playlist(f"{emoji_name}_all.m3u", emoji_name, emoji_id)
            generate_playlist(f"{emoji_name}_recent.m3u", emoji_name, emoji_id, recent=True)

        conn.close()
        logger.info('All playlists generated successfully.')

    except Exception as e:
        logger.error(f'Error occurred: {e}', exc_info=True)

if __name__ == "__main__":
    generate_playlists()