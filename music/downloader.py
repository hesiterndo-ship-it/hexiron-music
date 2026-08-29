import os

import requests
from radiojavanapi import Client as RJClient

DOWNLOAD_DIR = os.path.join(os.getenv("DATA_DIR", "/data"), "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

_rj = RJClient()


def _cache_path(song_id) -> str:
    return os.path.join(DOWNLOAD_DIR, f"rj_{song_id}.m4a")


def search_and_download(query: str) -> dict:
    """Search RadioJavan for `query` and return the first song result,
    downloaded and cached as an m4a. Returns None if nothing was found.

    Result shape: {"title": str, "duration": int, "file_path": str, "video_id": str}
    """
    results = _rj.search(query)
    if not results.songs:
        return None

    short = results.songs[0]
    song = _rj.get_song_by_id(short.id)

    cached = _cache_path(song.id)
    title = f"{song.artist} - {song.name}" if song.artist else song.name

    if not os.path.exists(cached):
        link = song.hq_link or song.lq_link
        resp = requests.get(link, timeout=30)
        resp.raise_for_status()
        with open(cached, "wb") as f:
            f.write(resp.content)

    return {
        "title": title,
        "duration": song.duration,
        "file_path": cached,
        "video_id": str(song.id),
    }