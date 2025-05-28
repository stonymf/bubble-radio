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
    idents_path = "/usr/src/app/idents"
    total_length = 0

    # Get the song count limit from .env
    song_limit = int(os.getenv('RECENT_SONG_COUNT', '100'))
    
    # Get ident settings from .env
    enable_idents = os.getenv('ENABLE_IDENTS', 'false').lower() == 'true'
    ident_interval = int(os.getenv('IDENT_INTERVAL', '8'))

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

        # Check for ident file
        ident_file = None
        if enable_idents:
            ident_path = os.path.join(idents_path, f"{emoji_name}.mp3")
            if os.path.exists(ident_path):
                ident_file = ident_path
                logger.info(f'Found ident for {emoji_name}: {ident_file}')
            else:
                logger.info(f'No ident found for {emoji_name}, skipping idents')

        now = datetime.datetime.now()
        with open(os.path.join(playlist_dir, playlist_name), "w") as f:
            song_count = 0
            
            for row in randomized_rows:
                track_filename, length = row
                length = float(length)
                total_length += length
                mp3_file_path = os.path.join(base_mp3_path, track_filename)
                f.write(mp3_file_path + "\n")
                song_count += 1

                # Check if we should insert an ident
                if (ident_file and 
                    song_count % ident_interval == 0 and 
                    song_count < len(randomized_rows)):  # Don't add after last song
                    
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
            logger.info(f'Idents enabled for {emoji_name} with interval: {ident_interval}')
    except Exception as e:
        logger.error(f'Error occurred: {e}', exc_info=True)
    finally:
        conn.close()

    return total_length

if __name__ == "__main__":
    generate_playlist()
