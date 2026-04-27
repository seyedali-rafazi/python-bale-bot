# ایجاد فایل جدید services/music.py

import os
import subprocess
import glob
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from dotenv import load_dotenv

load_dotenv()
SPOTIPY_CLIENT_ID = os.getenv("SPOTIPY_CLIENT_ID")
SPOTIPY_CLIENT_SECRET = os.getenv("SPOTIPY_CLIENT_SECRET")

# تنظیم کلاینت اسپاتیفای
sp = spotipy.Spotify(
    auth_manager=SpotifyClientCredentials(
        client_id=SPOTIPY_CLIENT_ID, client_secret=SPOTIPY_CLIENT_SECRET
    )
)


def search_spotify(query, type="track", limit=5):
    try:
        return sp.search(q=query, type=type, limit=limit)
    except Exception as e:
        print(f"Spotify Search Error: {e}")
        return None


def get_album_tracks(album_id):
    return sp.album_tracks(album_id)


def get_playlist_tracks(playlist_id):
    return sp.playlist_tracks(playlist_id, limit=10)


def get_artist_top_tracks(artist_id):
    return sp.artist_top_tracks(artist_id)


def get_artist_info(artist_id):
    return sp.artist(artist_id)


def get_track_info(track_id):
    return sp.track(track_id)


def download_spotify_track(url, chat_id):
    try:
        download_dir = f"temp_spotify_{chat_id}"
        os.makedirs(download_dir, exist_ok=True)
        command = ["spotdl", url, "--output", download_dir]
        subprocess.run(command, capture_output=True, text=True)
        files = glob.glob(os.path.join(download_dir, "*.mp3"))
        if files:
            return files[0]
        return None
    except Exception as e:
        print(f"Spotify Error: {e}")
        return None
