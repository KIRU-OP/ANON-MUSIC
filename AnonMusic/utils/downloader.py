import os
import re
import time
import random
import asyncio
import logging
import functools

import requests
import yt_dlp

from AnonMusic.utils.cookie_handler import COOKIE_PATH

_logger = logging.getLogger("AnonMusic.utils.yt_dlp_download")

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

MIN_VALID_SIZE = 10240  # 10 KB - anything smaller is treated as a failed/corrupt download
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 2  # multiplied by attempt number

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# ---------------------------------------------------------------------------
# Invidious config
# ---------------------------------------------------------------------------
# Invidious har request YouTube ko khud proxy karta hai, isliye humein direct
# YouTube 403 / bot-detection ka utna saamna nahi karna padta. Hum kuch known
# public instances rakhte hain aur unhe randomly try karte hain taaki load
# ek hi instance par na pade. Docs: https://docs.invidious.io/api/
INVIDIOUS_INSTANCES = [
    "https://invidious.f5.si",
    "https://yewtu.be",
    "https://invidious.nerdvpn.de",
    "https://iv.ggtyler.dev",
    "https://invidious.jing.rocks",
    "https://inv.nadeko.net",
]

INVIDIOUS_TIMEOUT = 8          # seconds, per API/instance request
INVIDIOUS_DOWNLOAD_TIMEOUT = 25  # seconds, for the actual stream download
INVIDIOUS_INSTANCES_URL = "https://api.invidious.io/instances.json?sort_by=health"


def _cookie_opts() -> dict:
    opts = {}
    try:
        if COOKIE_PATH and os.path.exists(COOKIE_PATH) and os.path.getsize(COOKIE_PATH) > 0:
            opts["cookiefile"] = str(COOKIE_PATH)
        else:
            _logger.warning("Cookie file missing/empty at %s — downloading without auth.", COOKIE_PATH)
    except Exception as e:
        _logger.error("Error checking cookie file: %s", e)
    return opts


def _video_id(link: str) -> str:
    return link.split("v=")[-1].split("&")[0] if "v=" in link else link


def _safe_filename(name: str) -> str:
    # search query ko safe filename me convert karta hai
    name = re.sub(r"[^\w\-_. ]", "_", name)
    return name.strip()[:80] or "audio"


def _is_valid_file(file_path: str) -> bool:
    return os.path.exists(file_path) and os.path.getsize(file_path) > MIN_VALID_SIZE


# ---------------------------------------------------------------------------
# Invidious helpers
# ---------------------------------------------------------------------------
_JSON_HEADERS = {"User-Agent": _UA, "Accept": "application/json"}

# Live instance list cache — baar baar api.invidious.io ko hit karne se bachne
# ke liye thodi der cache karte hain.
_instance_cache = {"list": None, "fetched_at": 0}
_INSTANCE_CACHE_TTL = 15 * 60  # 15 minutes


def _shuffled_instances() -> list:
    instances = INVIDIOUS_INSTANCES[:]
    random.shuffle(instances)
    return instances


def _fetch_instance_list() -> list:
    """
    Live Invidious instance list ko public directory se le aata hai (aur
    thodi der cache karta hai). Yeh isliye zaroori hai kyunki hardcoded
    instances aksar down/maintenance me chale jaate hain aur dead instance
    par baar baar hit karne se sirf time waste hota hai. Fail ho jaye to
    hardcoded INVIDIOUS_INSTANCES fallback list use hoti hai.
    """
    now = time.time()
    if _instance_cache["list"] and (now - _instance_cache["fetched_at"] < _INSTANCE_CACHE_TTL):
        return _instance_cache["list"]

    try:
        resp = requests.get(
            INVIDIOUS_INSTANCES_URL,
            headers=_JSON_HEADERS,
            timeout=INVIDIOUS_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        live = []
        for name, info in data:
            uri = info.get("uri")
            api_enabled = info.get("api", True)
            health_type = info.get("type")
            https_only = uri and uri.startswith("https://") and health_type == "https"
            if uri and api_enabled and https_only:
                live.append(uri.rstrip("/"))
        if live:
            random.shuffle(live)
            live = live[:12]  # itne hi kaafi hain, saari list try karne ki zaroorat nahi
            # hardcoded list ko bhi end me jod dete hain as extra safety net
            combined = live + [i for i in INVIDIOUS_INSTANCES if i not in live]
            _instance_cache["list"] = combined
            _instance_cache["fetched_at"] = now
            return combined
    except Exception as e:
        _logger.warning("Could not refresh Invidious instance list, using fallback: %s", e)

    return _shuffled_instances()


def _safe_json(resp: "requests.Response", context: str):
    """
    resp.json() ko safely call karta hai. Kai instances kabhi kabhi 200 status
    ke saath HTML (maintenance/Cloudflare challenge) page bhej dete hain, jo
    JSONDecodeError deta hai — is case me clear diagnostic log deke None
    return karte hain taaki caller agla instance try kar sake.
    """
    content_type = resp.headers.get("Content-Type", "")
    if "json" not in content_type.lower():
        snippet = resp.text[:150].replace("\n", " ")
        raise ValueError(
            f"{context}: expected JSON but got Content-Type={content_type!r}, "
            f"status={resp.status_code}, body starts with: {snippet!r}"
        )
    try:
        return resp.json()
    except ValueError as e:
        snippet = resp.text[:150].replace("\n", " ")
        raise ValueError(
            f"{context}: invalid JSON (status={resp.status_code}): {e}; body starts with: {snippet!r}"
        )


def _invidious_get_video_json(video_id: str, instance: str) -> dict:
    url = f"{instance}/api/v1/videos/{video_id}"
    resp = requests.get(url, headers=_JSON_HEADERS, timeout=INVIDIOUS_TIMEOUT)
    resp.raise_for_status()
    return _safe_json(resp, f"videos/{video_id} @ {instance}")


def _invidious_search_video_id(query: str, instance: str) -> str:
    url = f"{instance}/api/v1/search"
    resp = requests.get(
        url,
        params={"q": query, "type": "video"},
        headers=_JSON_HEADERS,
        timeout=INVIDIOUS_TIMEOUT,
    )
    resp.raise_for_status()
    results = _safe_json(resp, f"search {query!r} @ {instance}")
    for item in results:
        if item.get("type") == "video" and item.get("videoId"):
            return item["videoId"]
    return None


def _pick_audio_stream(data: dict) -> str:
    """adaptiveFormats me se sabse best audio-only stream chunta hai."""
    best_url, best_bitrate = None, -1
    for fmt in data.get("adaptiveFormats", []):
        fmt_type = fmt.get("type", "")
        if not fmt_type.startswith("audio/"):
            continue
        try:
            bitrate = int(fmt.get("bitrate", 0))
        except (TypeError, ValueError):
            bitrate = 0
        if bitrate > best_bitrate and fmt.get("url"):
            best_bitrate = bitrate
            best_url = fmt["url"]
    return best_url


def _pick_video_stream(data: dict) -> str:
    """formatStreams se muxed (audio+video) stream chunta hai, <=720p preferred."""
    candidates = [f for f in data.get("formatStreams", []) if f.get("url")]
    if not candidates:
        return None

    def height_of(fmt):
        try:
            return int((fmt.get("resolution") or "0p").rstrip("p"))
        except ValueError:
            return 0

    under_720 = [f for f in candidates if height_of(f) <= 720]
    pool = under_720 if under_720 else candidates
    pool.sort(key=height_of, reverse=True)
    return pool[0]["url"]


def _stream_download(url: str, file_path: str) -> bool:
    try:
        with requests.get(
            url,
            headers={"User-Agent": _UA},
            stream=True,
            timeout=INVIDIOUS_DOWNLOAD_TIMEOUT,
        ) as resp:
            resp.raise_for_status()
            tmp_path = file_path + ".part"
            with open(tmp_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=1024 * 256):
                    if chunk:
                        f.write(chunk)
            os.replace(tmp_path, file_path)
        return _is_valid_file(file_path)
    except Exception as e:
        _logger.warning("Invidious stream download failed for %s: %s", url, e)
        try:
            if os.path.exists(file_path + ".part"):
                os.remove(file_path + ".part")
        except OSError:
            pass
        return False


def _invidious_download_by_id(video_id: str, type: str, file_path: str) -> str:
    """
    Kai instances try karta hai jab tak kisi se valid stream URL na mile
    aur download successful na ho jaye. Kuch bhi fail hone par None return
    karta hai taaki caller yt-dlp fallback pe switch kar sake.
    """
    for instance in _fetch_instance_list():
        try:
            data = _invidious_get_video_json(video_id, instance)
        except Exception as e:
            _logger.warning("Invidious instance %s failed for %s: %s", instance, video_id, e)
            continue

        stream_url = _pick_audio_stream(data) if type == "audio" else _pick_video_stream(data)
        if not stream_url:
            _logger.warning("Instance %s returned no usable %s stream for %s", instance, type, video_id)
            continue

        if _stream_download(stream_url, file_path):
            _logger.info("Downloaded %s via Invidious instance %s", video_id, instance)
            return file_path

    return None


def _invidious_resolve_and_download(query_or_id: str, type: str, file_path: str, is_search: bool) -> str:
    for instance in _fetch_instance_list():
        try:
            video_id = (
                _invidious_search_video_id(query_or_id, instance)
                if is_search
                else query_or_id
            )
        except Exception as e:
            _logger.warning("Invidious search failed on %s: %s", instance, e)
            continue

        if not video_id:
            continue

        result = _invidious_download_by_id(video_id, type, file_path)
        if result:
            return result

    return None


# ---------------------------------------------------------------------------
# yt-dlp fallback (original logic, unchanged)
# ---------------------------------------------------------------------------
def _base_ydl_opts(file_path: str, type: str) -> dict:
    return {
        "quiet": True,
        "no_warnings": True,
        "geo_bypass": True,
        "force_ipv4": True,
        "noplaylist": True,
        "outtmpl": file_path,
        "http_headers": {"User-Agent": _UA},
        "format": (
            "best[height<=?720][width<=?1280]/best"
            if type == "video"
            else "bestaudio[ext=webm]/bestaudio/best"
        ),
    }


def _download_with_retries(ydl_opts: dict, target: str, file_path: str) -> str:
    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([target])
            if _is_valid_file(file_path):
                return file_path
            last_err = "downloaded file missing or too small"
        except Exception as e:
            last_err = e
            msg = str(e)
            # 403s from YouTube are often transient / cookie-related — retry with backoff
            if "403" in msg or "Forbidden" in msg:
                _logger.warning(
                    "Attempt %d/%d: 403 Forbidden for %s — retrying.",
                    attempt, MAX_RETRIES, target,
                )
            else:
                _logger.error(
                    "Attempt %d/%d: download failed for %s: %s",
                    attempt, MAX_RETRIES, target, e,
                )
                # non-403 errors (bad link, no results, etc.) rarely fix themselves - stop early
                break

        if attempt < MAX_RETRIES:
            time.sleep(RETRY_BACKOFF_SECONDS * attempt)

    _logger.error("Giving up on %s after retries. Last error: %s", target, last_err)
    return None


def _yt_dlp_fallback_download(link: str, type: str, file_path: str) -> str:
    ydl_opts = _base_ydl_opts(file_path, type)
    ydl_opts.update(_cookie_opts())
    return _download_with_retries(ydl_opts, link, file_path)


def _yt_dlp_fallback_search(query: str, type: str, file_path: str) -> str:
    ydl_opts = _base_ydl_opts(file_path, type)
    ydl_opts["default_search"] = "ytsearch1"
    ydl_opts.update(_cookie_opts())
    return _download_with_retries(ydl_opts, f"ytsearch1:{query}", file_path)


# ---------------------------------------------------------------------------
# Public sync entry points — Invidious first, yt-dlp as fallback
# ---------------------------------------------------------------------------
def _sync_download(link: str, type: str = "audio") -> str:
    video_id = _video_id(link)
    if not video_id or len(video_id) < 3:
        _logger.warning("Invalid/short video id extracted from link: %s", link)
        return None

    ext = "mp4" if type == "video" else "webm"
    file_path = os.path.join(DOWNLOAD_DIR, f"{video_id}.{ext}")

    if _is_valid_file(file_path):
        return file_path

    result = _invidious_download_by_id(video_id, type, file_path)
    if result:
        return result

    _logger.warning("Invidious download failed for %s, falling back to yt-dlp.", video_id)
    return _yt_dlp_fallback_download(link, type, file_path)


def _sync_download_by_name(query: str, type: str = "audio") -> str:
    """
    Song/video ka naam (query) leke pehle Invidious search API se video
    resolve karta hai aur usi se direct download karta hai. Fail hone par
    yt-dlp ke ytsearch1 fallback pe chala jaata hai.
    """
    if not query or len(query.strip()) < 2:
        _logger.warning("Empty/too-short search query received.")
        return None

    ext = "mp4" if type == "video" else "webm"
    safe_name = _safe_filename(query)
    file_path = os.path.join(DOWNLOAD_DIR, f"{safe_name}.{ext}")

    if _is_valid_file(file_path):
        return file_path

    result = _invidious_resolve_and_download(query, type, file_path, is_search=True)
    if result:
        return result

    _logger.warning("Invidious search/download failed for %r, falling back to yt-dlp.", query)
    return _yt_dlp_fallback_search(query, type, file_path)


# ---------------------------------------------------------------------------
# Async wrappers (unchanged interface)
# ---------------------------------------------------------------------------
async def yt_dlp_download(link: str, type: str = "audio") -> str:
    loop = asyncio.get_event_loop()
    func = functools.partial(_sync_download, link, type)
    return await loop.run_in_executor(None, func)


async def yt_dlp_download_by_name(query: str, type: str = "audio") -> str:
    loop = asyncio.get_event_loop()
    func = functools.partial(_sync_download_by_name, query, type)
    return await loop.run_in_executor(None, func)


async def download_audio_concurrent(link: str) -> str:
    return await yt_dlp_download(link, type="audio")


async def download_song_by_name(query: str) -> str:
    """Song naam se direct download (audio)."""
    return await yt_dlp_download_by_name(query, type="audio")
