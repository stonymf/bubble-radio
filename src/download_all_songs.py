#!/usr/bin/env python3
import os
import sys
import sqlite3
import time
import argparse
import random
from dotenv import load_dotenv
from src.downloader import download_audio, download_file_only
from src.logger_config import configure_logging

# Configure logging
logger = configure_logging('download_all.log', 'download_all_logger')

def main():
    """
    Script to check the database for all songs and download any that are missing.
    """
    # Set up command line arguments
    parser = argparse.ArgumentParser(description='Download all songs in the database that are missing.')
    parser.add_argument('--browser', choices=['chrome', 'firefox', 'edge', 'safari', 'opera', 'brave'], 
                        default='chrome', help='Browser to extract cookies from (default: chrome)')
    parser.add_argument('--delay-min', type=float, default=2.0, 
                        help='Minimum delay between downloads in seconds (default: 2.0)')
    parser.add_argument('--delay-max', type=float, default=5.0, 
                        help='Maximum delay between downloads in seconds (default: 5.0)')
    parser.add_argument('--start-at', type=int, default=1, 
                        help='Start at a specific song index (default: 1)')
    parser.add_argument('--limit', type=int, default=0, 
                        help='Limit the number of downloads (default: 0 for no limit)')
    parser.add_argument('--retry-failed', action='store_true', 
                        help='Retry songs that previously failed to download')
    parser.add_argument('--batch-size', type=int, default=10,
                        help='Number of songs to download before taking a longer break (default: 10)')
    parser.add_argument('--batch-break', type=float, default=30.0,
                        help='Longer break duration after each batch in seconds (default: 30.0)')
    
    args = parser.parse_args()
    
    # Validate delay arguments
    if args.delay_min > args.delay_max:
        print(f"Warning: delay-min ({args.delay_min}) is greater than delay-max ({args.delay_max})")
        print("Setting delay-min equal to delay-max")
        args.delay_min = args.delay_max
    
    # Update the browser choice in downloader.py (using environment variable)
    os.environ['BROWSER_CHOICE'] = args.browser
    print(f"Using cookies from {args.browser.capitalize()} browser")
    print(f"Delay between downloads: {args.delay_min}-{args.delay_max} seconds")
    print(f"Batch size: {args.batch_size} songs with {args.batch_break} second break between batches")
    
    # Load environment variables
    load_dotenv()
    
    # Database path
    db_path = "/usr/src/app/db.db"
    download_directory = "/usr/src/app/downloads"
    
    # Connect to the database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Get all songs from the database
        cursor.execute("""
            SELECT id, url, title, username, timestamp, channel_id, server_id, emoji_name, emoji_id, filename
            FROM downloads
            ORDER BY id
        """)
        
        songs = cursor.fetchall()
        total_songs = len(songs)
        
        print(f"Found {total_songs} songs in the database.")
        
        if args.limit > 0:
            print(f"Limiting to {args.limit} downloads")
        
        if args.start_at > 1:
            print(f"Starting at song #{args.start_at}")
            
        print("Starting download process...")
        
        success_count = 0
        missing_count = 0
        error_count = 0
        already_downloaded = 0
        skipped_count = 0
        
        # Keep track of URLs we've seen to avoid duplicates
        processed_urls = set()
        
        # Process each song
        for i, song in enumerate(songs, 1):
            # Skip songs before the start index
            if i < args.start_at:
                skipped_count += 1
                continue
                
            # Stop if we've reached the limit
            if args.limit > 0 and (success_count + error_count) >= args.limit:
                print(f"Download limit of {args.limit} reached.")
                break
                
            song_id, url, title, username, timestamp, channel_id, server_id, emoji_name, emoji_id, filename = song
            
            # Skip if we've already processed this URL (prevents duplicates)
            if url in processed_urls:
                print(f"[{i}/{total_songs}] Already processed this URL (skipping duplicate): {title}")
                skipped_count += 1
                continue
            
            processed_urls.add(url)
            
            # Check if the file already exists
            file_path = os.path.join(download_directory, filename)
            
            if os.path.exists(file_path) and not args.retry_failed:
                print(f"[{i}/{total_songs}] Already downloaded: {title}")
                already_downloaded += 1
                continue
            
            print(f"[{i}/{total_songs}] Downloading: {title} from {url}")
            
            try:
                # Check if we need to bypass the database insert
                # We don't want to add another database entry if one already exists
                if not os.path.exists(file_path) and not args.retry_failed:
                    # Custom download that doesn't insert into database
                    result = download_file_only(url, username, timestamp, channel_id, server_id, emoji_name, emoji_id, filename)
                else:
                    # Regular download (for retry cases)
                    result = download_audio(url, username, timestamp, channel_id, server_id, emoji_name, emoji_id)
                
                if result == "Success":
                    print(f"✓ Successfully downloaded: {title}")
                    success_count += 1
                else:
                    print(f"✗ Error downloading: {title} - {result}")
                    error_count += 1
                
                # Take a batch break if needed
                download_count = success_count + error_count
                if download_count > 0 and download_count % args.batch_size == 0:
                    batch_break = args.batch_break
                    print(f"Completed batch of {args.batch_size} downloads. Taking a {batch_break:.1f} second break...")
                    time.sleep(batch_break)
                else:
                    # Take a random delay between downloads
                    delay = random.uniform(args.delay_min, args.delay_max)
                    print(f"Waiting {delay:.1f} seconds before next download...")
                    time.sleep(delay)
                
            except Exception as e:
                logger.error(f"Error processing song {song_id} ({title}): {e}")
                print(f"✗ Exception downloading {title}: {e}")
                error_count += 1
                
                # Even on errors, we should still pause
                delay = random.uniform(args.delay_min, args.delay_max)
                print(f"Waiting {delay:.1f} seconds before next download...")
                time.sleep(delay)
        
        # Print summary
        print("\n--- Download Summary ---")
        print(f"Total songs: {total_songs}")
        print(f"Already downloaded: {already_downloaded}")
        print(f"Successfully downloaded: {success_count}")
        print(f"Failed to download: {error_count}")
        print(f"Skipped (duplicates or start index): {skipped_count}")
        
    except Exception as e:
        logger.error(f"Error in main process: {e}")
        print(f"An error occurred: {e}")
        return 1
    finally:
        conn.close()
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 