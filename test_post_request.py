import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()
flask_port = os.getenv("FLASK_PORT")
secret_key = os.getenv("SECRET_KEY")

url = f"http://localhost:{flask_port}/add_song"  # this port should match the port that your Flask server is running on
headers = {
    "Content-Type": "application/json",
    "Authorization": secret_key  # this secret key authorizes the POST request with Flask
}
data = {
    "url": "https://www.youtube.com/watch?v=ah-WNi-VbIw",
    "user": "test_user",
    "timestamp": "2024-03-06T00:00:00",
    "channel_name": "test_channel",
    "channel_id": 987654321,
    "server_name": "test_server",
    "server_id": 123456789
}

response = requests.post(url, headers=headers, data=json.dumps(data))

print("Status Code:", response.status_code)
print("Response Text:", response.text)
