# services/music.py

from ytmusicapi import YTMusic
import os

ytmusic = YTMusic()


def search_track(query, limit=10):
    try:
        results = ytmusic.search(query, filter="songs", limit=limit)
        tracks = []
        for item in results:
            if item["videoId"]:
                tracks.append(
                    {
                        "id": item["videoId"],
                        "name": item["title"],
                        "artists": [
                            {"name": artist["name"]}
                            for artist in item.get("artists", [])
                        ],
                        "url": f"https://music.youtube.com/watch?v={item['videoId']}",
                    }
                )
        return tracks
    except Exception as e:
        print(f"YTMusic Track Search Error: {e}")
        return []


def search_album(query, limit=5):
    try:
        results = ytmusic.search(query, filter="albums", limit=limit)
        albums = []
        for item in results:
            if item["browseId"]:
                albums.append(
                    {
                        "id": item["browseId"],
                        "name": item["title"],
                        "artists": [
                            {"name": artist["name"]}
                            for artist in item.get("artists", [])
                        ],
                    }
                )
        return albums
    except Exception as e:
        print(f"YTMusic Album Search Error: {e}")
        return []


def get_album_tracks(album_id):
    try:
        album = ytmusic.get_album(album_id)
        tracks = []
        for item in album.get("tracks", []):
            if item["videoId"]:
                tracks.append(
                    {
                        "id": item["videoId"],
                        "name": item["title"],
                        "artists": [
                            {"name": artist["name"]}
                            for artist in item.get("artists", [])
                        ]
                        if item.get("artists")
                        else album.get("artists", []),
                        "url": f"https://music.youtube.com/watch?v={item['videoId']}",
                    }
                )
        return tracks
    except Exception as e:
        print(f"YTMusic Get Album Tracks Error: {e}")
        return []


def search_artist(query, limit=5):
    try:
        results = ytmusic.search(query, filter="artists", limit=limit)
        artists = []
        for item in results:
            if item["browseId"]:
                artists.append({"id": item["browseId"], "name": item["artist"]})
        return artists
    except Exception as e:
        print(f"YTMusic Artist Search Error: {e}")
        return []


def get_artist_top_tracks(artist_id):
    try:
        artist = ytmusic.get_artist(artist_id)
        tracks = []
        # ytmusicapi معمولا آهنگ‌ها را در songs برمی‌گرداند
        songs = artist.get("songs", {}).get("results", [])
        for item in songs:
            if item["videoId"]:
                tracks.append(
                    {
                        "id": item["videoId"],
                        "name": item["title"],
                        "artists": [{"name": artist["name"]}],
                        "url": f"https://music.youtube.com/watch?v={item['videoId']}",
                    }
                )
        return tracks
    except Exception as e:
        print(f"YTMusic Get Artist Tracks Error: {e}")
        return []


def search_playlist(query, limit=5):
    try:
        results = ytmusic.search(query, filter="playlists", limit=limit)
        playlists = []
        for item in results:
            if item["browseId"]:
                playlists.append(
                    {
                        "id": item["browseId"],
                        "name": item["title"],
                        "owner": item.get("author", "YouTube Music"),
                    }
                )
        return playlists
    except Exception as e:
        print(f"YTMusic Playlist Search Error: {e}")
        return []


def get_playlist_tracks(playlist_id):
    try:
        playlist = ytmusic.get_playlist(playlist_id)
        tracks = []
        for item in playlist.get("tracks", []):
            if item["videoId"]:
                tracks.append(
                    {
                        "id": item["videoId"],
                        "name": item["title"],
                        "artists": [
                            {"name": artist["name"]}
                            for artist in item.get("artists", [])
                        ],
                        "url": f"https://music.youtube.com/watch?v={item['videoId']}",
                    }
                )
        return tracks
    except Exception as e:
        print(f"YTMusic Get Playlist Tracks Error: {e}")
        return []
