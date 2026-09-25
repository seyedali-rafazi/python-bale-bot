# services/music.py

import subprocess
import urllib.parse
from services.youtube import get_base_search_cmd


def search_track(query: str, limit: int = 10) -> list[dict]:
    """
    Search for music tracks on YouTube using yt-dlp with the same
    connection/network/IPv6 configuration established for video downloads.
    """
    if not query or not query.strip():
        return []

    query = query.strip()
    if not query.startswith("http://") and not query.startswith("https://"):
        search_query = f"ytsearch{limit}:{query}"
    else:
        search_query = query

    cmd = get_base_search_cmd()
    cmd.extend(
        [
            "--flat-playlist",
            "--print",
            "%(id)s|||%(title)s|||%(uploader)s|||%(artist)s",
            "--skip-download",
            search_query,
        ]
    )

    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=45,
        )

        if result.returncode != 0:
            print("❌ Error searching music tracks:")
            print(result.stderr)
            return []

        tracks = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line or "|||" not in line:
                continue

            parts = line.split("|||")
            if len(parts) < 2:
                continue

            video_id = parts[0].strip()
            raw_title = parts[1].strip() if len(parts) > 1 else "بدون عنوان"
            uploader = (
                parts[2].strip()
                if len(parts) > 2 and parts[2].strip().upper() != "NA"
                else ""
            )
            artist_tag = (
                parts[3].strip()
                if len(parts) > 3 and parts[3].strip().upper() != "NA"
                else ""
            )

            if not video_id:
                continue

            artist_name = artist_tag or uploader or "ناشناس"
            track_name = raw_title

            # Parse "Artist - Track Title" cleanly if available
            if " - " in raw_title:
                title_parts = raw_title.split(" - ", 1)
                parsed_artist = title_parts[0].strip()
                parsed_title = title_parts[1].strip()
                if not artist_tag:
                    artist_name = parsed_artist
                track_name = parsed_title

            tracks.append(
                {
                    "id": video_id,
                    "name": track_name,
                    "artists": [{"name": artist_name}],
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                }
            )

        return tracks[:limit]

    except Exception as e:
        print(f"Error in search_track: {e}")
        return []


def search_album(query: str, limit: int = 5) -> list[dict]:
    """
    Search for albums or album playlists on YouTube using yt-dlp.
    """
    if not query or not query.strip():
        return []

    query = query.strip()
    cmd = get_base_search_cmd()
    search_query = f"ytsearch{limit}:{query} album"

    cmd.extend(
        [
            "--flat-playlist",
            "--print",
            "%(id)s|||%(title)s|||%(uploader)s",
            "--skip-download",
            search_query,
        ]
    )

    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=45,
        )

        if result.returncode != 0:
            print("❌ Error searching albums:")
            print(result.stderr)
            return []

        albums = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line or "|||" not in line:
                continue

            parts = line.split("|||")
            if len(parts) < 2:
                continue

            item_id = parts[0].strip()
            title = parts[1].strip()
            uploader = (
                parts[2].strip()
                if len(parts) > 2 and parts[2].strip().upper() != "NA"
                else "ناشناس"
            )

            if not item_id:
                continue

            albums.append(
                {
                    "id": item_id,
                    "name": title,
                    "artists": [{"name": uploader}],
                }
            )

        return albums[:limit]

    except Exception as e:
        print(f"Error in search_album: {e}")
        return []


def get_album_tracks(album_id: str) -> list[dict]:
    """
    Extract tracks from an album/playlist ID or single video ID.
    """
    if not album_id:
        return []

    target_url = (
        album_id
        if album_id.startswith("http://") or album_id.startswith("https://")
        else f"https://www.youtube.com/playlist?list={album_id}"
    )

    cmd = get_base_search_cmd()
    cmd.extend(
        [
            "--flat-playlist",
            "--print",
            "%(id)s|||%(title)s|||%(uploader)s",
            "--skip-download",
            target_url,
        ]
    )

    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=45,
        )

        tracks = []
        if result.returncode == 0 and result.stdout.strip():
            for line in result.stdout.splitlines():
                line = line.strip()
                if not line or "|||" not in line:
                    continue
                parts = line.split("|||")
                if len(parts) < 2:
                    continue
                vid = parts[0].strip()
                title = parts[1].strip()
                uploader = (
                    parts[2].strip()
                    if len(parts) > 2 and parts[2].strip().upper() != "NA"
                    else "ناشناس"
                )
                if vid:
                    tracks.append(
                        {
                            "id": vid,
                            "name": title,
                            "artists": [{"name": uploader}],
                            "url": f"https://www.youtube.com/watch?v={vid}",
                        }
                    )

        if not tracks and len(album_id) == 11:
            tracks.append(
                {
                    "id": album_id,
                    "name": "آهنگ انتخابی",
                    "artists": [{"name": "ناشناس"}],
                    "url": f"https://www.youtube.com/watch?v={album_id}",
                }
            )

        return tracks

    except Exception as e:
        print(f"Error in get_album_tracks: {e}")
        return []


def search_artist(query: str, limit: int = 5) -> list[dict]:
    """
    Search for artists. Returns the artist name for querying top tracks.
    """
    if not query or not query.strip():
        return []

    clean_query = query.strip()
    return [{"id": clean_query, "name": clean_query, "artist": clean_query}]


def get_artist_top_tracks(artist_id: str) -> list[dict]:
    """
    Get top tracks for an artist using YouTube search.
    """
    return search_track(f"{artist_id} top songs", limit=10)


def search_playlist(query: str, limit: int = 5) -> list[dict]:
    """
    Search for playlists on YouTube.
    """
    if not query or not query.strip():
        return []

    query = query.strip()
    cmd = get_base_search_cmd()
    search_query = f"ytsearch{limit}:{query} playlist"

    cmd.extend(
        [
            "--flat-playlist",
            "--print",
            "%(id)s|||%(title)s|||%(uploader)s",
            "--skip-download",
            search_query,
        ]
    )

    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=45,
        )

        if result.returncode != 0:
            print("❌ Error searching playlists:")
            print(result.stderr)
            return []

        playlists = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line or "|||" not in line:
                continue

            parts = line.split("|||")
            if len(parts) < 2:
                continue

            item_id = parts[0].strip()
            title = parts[1].strip()
            uploader = (
                parts[2].strip()
                if len(parts) > 2 and parts[2].strip().upper() != "NA"
                else "ناشناس"
            )

            if not item_id:
                continue

            playlists.append(
                {
                    "id": item_id,
                    "name": title,
                    "owner": uploader,
                }
            )

        return playlists[:limit]

    except Exception as e:
        print(f"Error in search_playlist: {e}")
        return []


def get_playlist_tracks(playlist_id: str) -> list[dict]:
    """
    Extract tracks from a playlist.
    """
    return get_album_tracks(playlist_id)
