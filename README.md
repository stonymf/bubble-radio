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

# maximum length for a playlist (in hours)
# this is also the value for how often the playlists will get refreshed by liquidsoap
# it _does not_ mean that you will only have this many hours of music streaming on your station
# because playlists will contain different songs each time they are created, and underplayed
# songs are prioritized by the playlist creation script, to ensure equal play frequency
PLAYLIST_MAX_LENGTH=6

# where you want audio files to be downloaded
DOWNLOAD_DIRECTORY=/mnt/somevolume/media

# url where streams are being served publicly by icecast
# easiest to make a subdomain like 'stream' that just points to your icecast port
BASE_STREAM_URL=https://stream.yoururl.com

# secret key to verify POST requests from Bubble
SECRET_KEY=your_secret_key

# port that Flask server will listen on
FLASK_PORT=5000


## Network config

# you probably should not change this
ICECAST_HOST=bubble-radio-icecast

# set this to an available port and make sure it matches with the <port> value in icecast.xml
ICECAST_PORT=8000

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

You can try sending a test POST request with `python src/test_post_request.py <any youtube song url>`

If a success status is returned, the song should now be in the downloads directory you specified in the `.env` file.

Playlists will periodically (every X hours, where X is the value of `PLAYLIST_MAX_LENGTH` from the `.env` file) generate playlist files according to the server and channel that the downloaded songs originated from. These playlists will show up in `/playlists`.

Your streams should be listenable at `https://stream.yoururl.com/<playlist_name>` and you should also be able to view the basic frontend by visiting the flask server port, which can also be configured to a subdomain of `yoururl.com`.

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