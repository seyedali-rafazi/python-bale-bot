# services/music.py

import hashlib
import logging
import subprocess
from services.cache_service import cache_get, cache_set
from services.youtube import _run_async_subprocess, get_base_search_cmd

logger = logging.getLogger(__name__)

_MUSIC_CACHE_TTL_SEC = 900  # 15 minutes


def _parse_tracks_output(stdout_text: str, limit: int | None = None) -> list[dict]:
    tracks: list[dict] = []
    for line in stdout_text.splitlines():
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
    return tracks[:limit] if limit is not None else tracks


def _parse_albums_output(stdout_text: str, limit: int) -> list[dict]:
    albums: list[dict] = []
    for line in stdout_text.splitlines():
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


def _parse_collection_tracks(stdout_text: str, collection_id: str) -> list[dict]:
    tracks: list[dict] = []
    for line in stdout_text.splitlines():
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
    if not tracks and len(collection_id) == 11:
        tracks.append(
            {
                "id": collection_id,
                "name": "آهنگ انتخابی",
                "artists": [{"name": "ناشناس"}],
                "url": f"https://www.youtube.com/watch?v={collection_id}",
            }
        )
    return tracks


def _parse_playlists_output(stdout_text: str, limit: int) -> list[dict]:
    playlists: list[dict] = []
    for line in stdout_text.splitlines():
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


def _build_track_search_cmd(query: str, limit: int) -> list[str]:
    search_query = (
        query
        if query.startswith("http://") or query.startswith("https://")
        else f"ytsearch{limit}:{query}"
    )
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
    return cmd


def _build_album_search_cmd(query: str, limit: int) -> list[str]:
    cmd = get_base_search_cmd()
    cmd.extend(
        [
            "--flat-playlist",
            "--print",
            "%(id)s|||%(title)s|||%(uploader)s",
            "--skip-download",
            f"ytsearch{limit}:{query} album",
        ]
    )
    return cmd


def _build_collection_tracks_cmd(collection_id: str) -> list[str]:
    target_url = (
        collection_id
        if collection_id.startswith("http://") or collection_id.startswith("https://")
        else f"https://www.youtube.com/playlist?list={collection_id}"
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
    return cmd


def _build_playlist_search_cmd(query: str, limit: int) -> list[str]:
    cmd = get_base_search_cmd()
    cmd.extend(
        [
            "--flat-playlist",
            "--print",
            "%(id)s|||%(title)s|||%(uploader)s",
            "--skip-download",
            f"ytsearch{limit}:{query} playlist",
        ]
    )
    return cmd


def _cache_key(prefix: str, text: str, limit: int = 0) -> str:
    digest = hashlib.md5(f"{text.lower()}:{limit}".encode("utf-8")).hexdigest()[:16]
    return f"music:{prefix}:{digest}"


# ------------------------------------------------------------------
# Async API (preferred for bot handlers; zero ThreadPool consumption)
# ------------------------------------------------------------------

async def async_search_track(query: str, limit: int = 10) -> list[dict]:
    if not query or not query.strip():
        return []
    clean = query.strip()
    key = _cache_key("track", clean, limit)
    cached = await cache_get(key)
    if isinstance(cached, list) and cached:
        return cached

    try:
        rc, out, err = await _run_async_subprocess(
            _build_track_search_cmd(clean, limit), timeout_sec=45.0
        )
        if rc != 0:
            logger.warning("Error searching music tracks: %s", err)
            return []
        tracks = _parse_tracks_output(out, limit)
        if tracks:
            await cache_set(key, tracks, ttl_sec=_MUSIC_CACHE_TTL_SEC)
        return tracks
    except Exception as e:
        logger.warning("Error in async_search_track: %s", e)
        return []


async def async_search_album(query: str, limit: int = 5) -> list[dict]:
    if not query or not query.strip():
        return []
    clean = query.strip()
    key = _cache_key("album", clean, limit)
    cached = await cache_get(key)
    if isinstance(cached, list) and cached:
        return cached

    try:
        rc, out, err = await _run_async_subprocess(
            _build_album_search_cmd(clean, limit), timeout_sec=45.0
        )
        if rc != 0:
            print("❌ Error searching albums:")
            print(err)
            return []
        albums = _parse_albums_output(out, limit)
        if albums:
            await cache_set(key, albums, ttl_sec=_MUSIC_CACHE_TTL_SEC)
        return albums
    except Exception as e:
        print(f"Error in async_search_album: {e}")
        return []


async def async_get_album_tracks(album_id: str) -> list[dict]:
    if not album_id:
        return []
    key = _cache_key("album_tracks", album_id)
    cached = await cache_get(key)
    if isinstance(cached, list) and cached:
        return cached

    try:
        rc, out, _ = await _run_async_subprocess(
            _build_collection_tracks_cmd(album_id), timeout_sec=45.0
        )
        tracks = _parse_collection_tracks(out if rc == 0 else "", album_id)
        if tracks:
            await cache_set(key, tracks, ttl_sec=_MUSIC_CACHE_TTL_SEC)
        return tracks
    except Exception as e:
        print(f"Error in async_get_album_tracks: {e}")
        return []


async def async_get_artist_top_tracks(artist_id: str) -> list[dict]:
    return await async_search_track(f"{artist_id} top songs", limit=10)


async def async_search_playlist(query: str, limit: int = 5) -> list[dict]:
    if not query or not query.strip():
        return []
    clean = query.strip()
    key = _cache_key("playlist", clean, limit)
    cached = await cache_get(key)
    if isinstance(cached, list) and cached:
        return cached

    try:
        rc, out, err = await _run_async_subprocess(
            _build_playlist_search_cmd(clean, limit), timeout_sec=45.0
        )
        if rc != 0:
            print("❌ Error searching playlists:")
            print(err)
            return []
        playlists = _parse_playlists_output(out, limit)
        if playlists:
            await cache_set(key, playlists, ttl_sec=_MUSIC_CACHE_TTL_SEC)
        return playlists
    except Exception as e:
        print(f"Error in async_search_playlist: {e}")
        return []


async def async_get_playlist_tracks(playlist_id: str) -> list[dict]:
    return await async_get_album_tracks(playlist_id)


# ------------------------------------------------------------------
# Sync compatibility API
# ------------------------------------------------------------------

def search_track(query: str, limit: int = 10) -> list[dict]:
    if not query or not query.strip():
        return []
    cmd = _build_track_search_cmd(query.strip(), limit)
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
        return _parse_tracks_output(result.stdout, limit)
    except Exception as e:
        print(f"Error in search_track: {e}")
        return []


def search_album(query: str, limit: int = 5) -> list[dict]:
    if not query or not query.strip():
        return []
    cmd = _build_album_search_cmd(query.strip(), limit)
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
        return _parse_albums_output(result.stdout, limit)
    except Exception as e:
        print(f"Error in search_album: {e}")
        return []


def get_album_tracks(album_id: str) -> list[dict]:
    if not album_id:
        return []
    cmd = _build_collection_tracks_cmd(album_id)
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
        return _parse_collection_tracks(
            result.stdout if result.returncode == 0 else "", album_id
        )
    except Exception as e:
        print(f"Error in get_album_tracks: {e}")
        return []


def search_artist(query: str, limit: int = 5) -> list[dict]:
    if not query or not query.strip():
        return []
    clean_query = query.strip()
    return [{"id": clean_query, "name": clean_query, "artist": clean_query}]


def get_artist_top_tracks(artist_id: str) -> list[dict]:
    return search_track(f"{artist_id} top songs", limit=10)


def search_playlist(query: str, limit: int = 5) -> list[dict]:
    if not query or not query.strip():
        return []
    cmd = _build_playlist_search_cmd(query.strip(), limit)
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
        return _parse_playlists_output(result.stdout, limit)
    except Exception as e:
        print(f"Error in search_playlist: {e}")
        return []


def get_playlist_tracks(playlist_id: str) -> list[dict]:
    return get_album_tracks(playlist_id)
