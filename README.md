# Bubble radio

**Bubble radio** is a song archiving and web radio platform that is designed to work in conjunction with Bubble, a Discord bot developed for Trust.

The main components of this project are:

- A **Flask server** which 
	- receives and processes POST requests from Bubble
	- downloads songs (**`downloader.py`**) based on links from those POST requests and commits the relevant metadata to a sqlite3 database
	- creates m3u playlist files (**`playlists.py`**) to be used when serving the playlist radio streams
	- serves up a rudimentary frontend to access the streams via browser (mostly for testing purposes)
- A **Icecast** service which makes the streams available to listeners
- A **liquidsoap** service which internally serves the playlist files to Icecast, and also makes a live mountpoint available for livestreaming

### Setup

The only configuration necessary should be the creation of an `.env` file appropriate to your system's configuration. You can place this `.env` file in the main project directory.

Below is a template. Use absolute paths wherever filepaths are required.

```
## General config

# maximum length in seconds above which songs will not be downloaded
MAX_LENGTH=4140

# recency period (in days) for _recent playlists; e.g. a value of 30 will cause the _recent playlists
# to only contain songs that have been added in the last 30 days
RECENCY_PERIOD=30

# minimum number of songs for recent playlists; if there aren't enough songs in the chosen recency
# period, random selections from the database will be added to meet the minimum
MIN_SONG_COUNT=100

# where you want audio files to be downloaded
DOWNLOAD_DIRECTORY=/mnt/somevolume/media

# url where streams are being served publicly by icecast
# this is only really necessary for the demo frontend and not crucial for core functionality
BASE_STREAM_URL=https://stream.yoururl.com

# secret key to verify POST requests from Bubble
SECRET_KEY=your_secret_key


## Network config

# you probably should not change this
ICECAST_HOST=bubble-radio-icecast

# set this to an available port that you want to use for bubble-radio
RADIO_PORT=8000

# this is the port you will tell people to livestream to
LIVE_STREAM_PORT=8765

# this needs to match with the source-password value in your icecast.xml
ICECAST_PASSWORD=icecastpassword
```

Now, before you run the docker image, just create two files:

1) `touch db.db`

This creates a placeholder database file for docker to mount its database to.

2) `touch disallow.txt`

 This is where you can add sites you would like to ignore, one url on each line. For example, I currently just have one line containing `substack.com` because `yt-dlp` does funny things with substack urls.

### Initial use

You should be able to `docker compose up --build` and, if your `.env` configuration and network/port settings are correct, everything should start up.

You can try sending a test POST request with `python src/test_post_request.py <any youtube song url> <an emoji name>`

If a success status is returned, the song should now be in the downloads directory you specified in the `.env` file.

Playlists will periodically (at a frequency equal to each respective playlist's length) generate playlist files according to the emoji/react that the downloaded songs originated from. These playlists will show up in `/playlists`.

Your streams should be listenable at `https://stream.yoururl.com/<playlist_name>` (provided you have created the subdomain `stream` and routed it to your RADIO_PORT) and you should also be able to view the basic frontend by visiting `https://stream.yoururl.com/demo`

### How to live stream to the live mountpoint

The easiest way to stream from your local computer to the mountpoint is by using [BUTT (broadcast using this tool)](https://danielnoethen.de/butt/).

Download it and then launch and click on Settings. 

On the Main tab, under Server Settings, click ADD, and use these settings:

```
Type: Icecast
Use SSL/TLS: Leave unchecked
Address: yoururl.com
Port: the LIVE_STREAM_PORT value in you .env
Password: the ICECAST_PASSWORD value in your .env
Icecast mountpoint: /live
Icecast user: leave as 'source'
```

Then hit Save, select your audio source and hit the Play button to start streaming.