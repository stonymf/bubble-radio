import requests
import json

url = "http://localhost:5006/add_song"  # this port should match the port that your Flask server is running on
headers = {
    "Content-Type": "application/json",
    "Authorization": "trust"  # this value should match the SECRET_KEY value in your .env file
}
data = {
    "url": "https://www.youtube.com/watch?v=Dc28VOvgQOY",
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
