import requests
import base64
import os
from app.config import settings

def get_zoom_access_token():
    # For OAuth, you would implement the full OAuth flow. For server-to-server, use client credentials.
    # Here, we assume JWT or server-to-server OAuth (recommended by Zoom for backend apps)
    client_id = settings.ZOOM_CLIENT_ID
    client_secret = settings.ZOOM_CLIENT_SECRET
    account_id = settings.ZOOM_ACCOUNT_ID
    token_url = "https://zoom.us/oauth/token"
    auth = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    headers = {
        "Authorization": f"Basic {auth}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    data = {
        "grant_type": "account_credentials",
        "account_id": account_id
    }
    response = requests.post(token_url, headers=headers, data=data)
    response.raise_for_status()
    return response.json()["access_token"]

def create_zoom_meeting(user_id, topic, start_time, duration=30):
    access_token = get_zoom_access_token()
    url = f"https://api.zoom.us/v2/users/{user_id}/meetings"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    payload = {
        "topic": topic,
        "type": 2,  # Scheduled meeting
        "start_time": start_time,  # ISO 8601 format
        "duration": duration,
        "timezone": "UTC",
        "settings": {
            "join_before_host": True,
            "waiting_room": False
        }
    }
    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    return response.json()  # Contains join_url, start_url, etc.
