import requests
import json
import os
import sys
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
flask_port = os.getenv("FLASK_PORT")
secret_key = os.getenv("SECRET_KEY")

# Check for the minimum number of arguments
if len(sys.argv) < 2:
    print("Usage: python test_post_request.py <url> [timestamp]")
    sys.exit(1)

# First command-line argument is the URL
song_url = "https://www.youtube.com/watch?v=KOFw2UPLdPk" #sys.argv[1]

# Use the current time as the default timestamp
timestamp = datetime.now().isoformat()

# If a second argument is provided, use it as the timestamp
if len(sys.argv) > 2:
    timestamp = sys.argv[2]

url = f"http://localhost:{flask_port}/add_song"
headers = {
    "Content-Type": "application/json",
    "Authorization": secret_key
}
data = {
    "url": song_url,
    "user": "test_user",
    "timestamp": timestamp,
    "channel_id": 987654321,
    "server_id": 123456789,
    "emoji_name": "emoji_name",
    "emoji_id": 123456789
}

response = requests.post(url, headers=headers, data=json.dumps(data))

print("Status Code:", response.status_code)
print("Response Text:", response.text)