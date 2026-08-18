import asyncio
import requests
from pathlib import Path
from urllib.parse import urlsplit

from config import COOKIE_URL
from AnonMusic.utils.errors import capture_internal_err

COOKIE_PATH = Path("AnonMusic/assets/cookies.txt")

# values that mean "not actually configured" even though they're truthy strings
_INVALID_URL_VALUES = {"", "none", "null", "false", "0", "n/a", "na"}


def _extract_paste_id(url: str) -> str:
    path = urlsplit(url).path.rstrip("/")
    parts = [p for p in path.split("/") if p]
    return parts[-1] if parts else ""


def _is_valid_cookie_url(url: str) -> bool:
    """Guards against literal 'None'/'null'/empty strings and missing schemes."""
    if not url:
        return False
    if url.strip().lower() in _INVALID_URL_VALUES:
        return False
    parsed = urlsplit(url.strip())
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def resolve_raw_cookie_url(url: str) -> str:
    url = (url or "").strip()
    low = url.lower()

    if "pastebin.com/" in low and "/raw/" not in low:
        paste_id = _extract_paste_id(url)
        return f"https://pastebin.com/raw/{paste_id}" if paste_id else url

    if "batbin.me/" in low and "/raw/" not in low:
        paste_id = _extract_paste_id(url)
        return f"https://batbin.me/raw/{paste_id}" if paste_id else url

    return url


@capture_internal_err
async def fetch_and_store_cookies():
    if not _is_valid_cookie_url(COOKIE_URL):
        raise EnvironmentError(
            "⚠️ ᴄᴏᴏᴋɪᴇ_ᴜʀʟ ɴᴏᴛ sᴇᴛ (ᴏʀ ɪɴᴠᴀʟɪᴅ) ɪɴ ᴇɴᴠ. "
            f"ɢᴏᴛ: {COOKIE_URL!r} — sᴇᴛ ᴀ ᴠᴀʟɪᴅ ʜᴛᴛᴘ(s) ᴜʀʟ."
        )

    raw_url = resolve_raw_cookie_url(COOKIE_URL)

    if not _is_valid_cookie_url(raw_url):
        raise ValueError(f"⚠️ ʀᴇsᴏʟᴠᴇᴅ ᴄᴏᴏᴋɪᴇ ᴜʀʟ ɪs ɪɴᴠᴀʟɪᴅ: {raw_url!r}")

    try:
        response = await asyncio.to_thread(
            requests.get,
            raw_url,
            timeout=15,
            headers={"User-Agent": "vishal-cookie-fetcher/1.0"},
        )
        response.raise_for_status()
    except Exception as e:
        raise ConnectionError(f"⚠️ ᴄᴀɴ'ᴛ ꜰᴇᴛᴄʜ ᴄᴏᴏᴋɪᴇs:\n{e}")

    cookies = (response.text or "").strip()

    if not cookies.startswith("# Netscape"):
        raise ValueError("⚠️ ɪɴᴠᴀʟɪᴅ ᴄᴏᴏᴋɪᴇ ꜰᴏʀᴍᴀᴛ. ɴᴇᴇᴅs ɴᴇᴛsᴄᴀᴘᴇ ꜰᴏʀᴍᴀᴛ.")

    if len(cookies) < 100:
        raise ValueError("⚠️ ᴄᴏᴏᴋɪᴇ ᴄᴏɴᴛᴇɴᴛ ᴛᴏᴏ sʜᴏʀᴛ. ᴘᴏssɪʙʟʏ ɪɴᴠᴀʟɪᴅ.")

    COOKIE_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        COOKIE_PATH.write_text(cookies, encoding="utf-8")
    except Exception as e:
        raise IOError(f"⚠️ ғᴀɪʟᴇᴅ ᴛᴏ sᴀᴠᴇ ᴄᴏᴏᴋɪᴇs: {e}")
