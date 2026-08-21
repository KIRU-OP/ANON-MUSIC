"""
multi_platform_fallback.py

Drop-in fallback resolver for AnonMusic-style Telegram music bots.

Chain: YouTube -> SoundCloud (full track, via yt-dlp) -> Deezer (30s preview, official API)

WIRING NOTES (you must adjust these to match your project):
  1. Replace the `youtube_download(query)` stub below with a call to your
     existing YouTube module, e.g.:
         from AnonMusic.platforms.Youtube import YouTubeAPI
         yt = YouTubeAPI()
         file_path, direct = await yt.download(link, ...)
  2. This module assumes yt-dlp is already installed (it is, since your
     YouTube backend already depends on it).
  3. Call `resolve_audio(query)` from wherever you currently call your
     YouTube-only download function (usually in your /play command handler
     or in AnonMusic/platforms/__init__.py's stream resolver).
  4. Adjust LOGGER to your project's logger (this file uses a local one).
"""

import asyncio
import logging
import os
import tempfile
from dataclasses import dataclass
from typing import Optional

import requests
import yt_dlp

LOGGER = logging.getLogger("AnonMusic.fallback")

DOWNLOAD_DIR = os.environ.get("DOWNLOAD_DIR", "downloads")


class AllPlatformsFailedError(Exception):
    """Raised when YouTube, SoundCloud, and Deezer all fail to provide audio."""


@dataclass
class ResolvedAudio:
    source: str          # "youtube" | "soundcloud" | "deezer_preview"
    file_path: str        # local path to the audio file
    title: str
    duration: Optional[int] = None   # seconds; None for previews or unknown
    is_preview: bool = False          # True only for Deezer 30s clips


# ---------------------------------------------------------------------------
# 1. YOUTUBE (your existing backend — plug in here)
# ---------------------------------------------------------------------------

async def youtube_download(query: str) -> ResolvedAudio:
    """
    STUB — replace this body with your project's real YouTube download call.
    Must raise an exception (any Exception) on failure so the fallback chain
    proceeds — do not swallow errors here.
    """
    from AnonMusic.platforms.Youtube import YouTubeAPI  # your existing module

    yt = YouTubeAPI()
    # Example shape — adjust to match your actual method signature/return:
    file_path, direct_link, title, duration = await yt.download(query)
    if not file_path:
        raise RuntimeError("YouTube backend returned no file path")
    return ResolvedAudio(source="youtube", file_path=file_path, title=title, duration=duration)


# ---------------------------------------------------------------------------
# 2. SOUNDCLOUD (full track, no cookies needed)
# ---------------------------------------------------------------------------

def _soundcloud_search_and_download_sync(query: str) -> ResolvedAudio:
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    out_tmpl = os.path.join(DOWNLOAD_DIR, "%(id)s.%(ext)s")

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": out_tmpl,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "default_search": "scsearch1",  # SoundCloud search, top 1 result
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }],
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(query, download=True)
        # extract_info on a search query returns a playlist-like dict with 'entries'
        if "entries" in info:
            if not info["entries"]:
                raise RuntimeError("SoundCloud returned no results")
            info = info["entries"][0]

        file_path = ydl.prepare_filename(info)
        # after postprocessing, extension becomes .mp3
        base, _ = os.path.splitext(file_path)
        mp3_path = base + ".mp3"
        final_path = mp3_path if os.path.exists(mp3_path) else file_path

        return ResolvedAudio(
            source="soundcloud",
            file_path=final_path,
            title=info.get("title", query),
            duration=info.get("duration"),
        )


async def soundcloud_download(query: str) -> ResolvedAudio:
    return await asyncio.to_thread(_soundcloud_search_and_download_sync, query)


# ---------------------------------------------------------------------------
# 3. DEEZER (official public API — 30-second preview only, legal last resort)
# ---------------------------------------------------------------------------

def _deezer_search_sync(query: str) -> dict:
    resp = requests.get(
        "https://api.deezer.com/search",
        params={"q": query, "limit": 1},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    results = data.get("data") or []
    if not results:
        raise RuntimeError("Deezer returned no results")
    return results[0]


async def deezer_preview_download(query: str) -> ResolvedAudio:
    track = await asyncio.to_thread(_deezer_search_sync, query)
    preview_url = track.get("preview")
    if not preview_url:
        raise RuntimeError("Deezer track has no preview clip available")

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(suffix=".mp3", dir=DOWNLOAD_DIR)
    os.close(fd)

    def _fetch():
        r = requests.get(preview_url, timeout=15)
        r.raise_for_status()
        with open(tmp_path, "wb") as f:
            f.write(r.content)

    await asyncio.to_thread(_fetch)

    return ResolvedAudio(
        source="deezer_preview",
        file_path=tmp_path,
        title=track.get("title", query),
        duration=30,
        is_preview=True,
    )


# ---------------------------------------------------------------------------
# ORCHESTRATOR — call this one function from your bot
# ---------------------------------------------------------------------------

async def resolve_audio(query: str) -> ResolvedAudio:
    """
    Try YouTube, then SoundCloud, then Deezer preview.
    Returns a ResolvedAudio on the first success.
    Raises AllPlatformsFailedError if every platform fails.
    """
    errors = []

    try:
        LOGGER.info(f"🎵 Trying YouTube for: {query}")
        return await youtube_download(query)
    except Exception as e:
        LOGGER.warning(f"⚠️ YouTube failed for '{query}': {e}")
        errors.append(f"YouTube: {e}")

    try:
        LOGGER.info(f"🎵 Falling back to SoundCloud for: {query}")
        return await soundcloud_download(query)
    except Exception as e:
        LOGGER.warning(f"⚠️ SoundCloud failed for '{query}': {e}")
        errors.append(f"SoundCloud: {e}")

    try:
        LOGGER.info(f"🎵 Falling back to Deezer preview for: {query}")
        return await deezer_preview_download(query)
    except Exception as e:
        LOGGER.warning(f"⚠️ Deezer preview failed for '{query}': {e}")
        errors.append(f"Deezer: {e}")

    raise AllPlatformsFailedError(
        "All platforms failed to provide audio for '{}':\n{}".format(
            query, "\n".join(errors)
        )
)
