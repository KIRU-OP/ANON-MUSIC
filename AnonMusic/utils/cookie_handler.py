"""
AnonMusic/utils/cookie_handler.py

Fixes: ImportError: cannot import name 'COOKIE_PATH' from 'AnonMusic.utils.cookie_handler'

This module now exposes COOKIE_PATH as a module-level constant so that
`from AnonMusic.utils.cookie_handler import COOKIE_PATH` in youtube.py works.

It also includes the cookie-download logic (moved here so everything cookie-
related lives in one place — delete/merge your old standalone fetch script
once this is wired in, to avoid two different COOKIE_PATH definitions).
"""

import asyncio
import logging
from pathlib import Path
from urllib.parse import urlsplit

import requests

from config import COOKIE_URL

LOGGER = logging.getLogger("AnonMusic.cookie_handler")

# ---------------------------------------------------------------------------
# THIS is the constant youtube.py (and anything else) should import.
# ---------------------------------------------------------------------------
COOKIE_PATH = Path("AnonMusic/assets/cookies.txt")

_INVALID_URL_VALUES = {"", "none", "null", "false", "0", "n/a", "na"}


def _extract_paste_id(url: str) -> str:
    path = urlsplit(url).path.rstrip("/")
    parts = [p for p in path.split("/") if p]
    return parts[-1] if parts else ""


def _is_valid_cookie_url(url: str) -> bool:
    if not url:
        return False
    if str(url).strip().lower() in _INVALID_URL_VALUES:
        return False
    parsed = urlsplit(str(url).strip())
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


async def fetch_and_store_cookies() -> bool:
    """
    Downloads cookies from COOKIE_URL (config.py) and saves them to COOKIE_PATH.
    Returns True on success, False on failure (logs the reason either way,
    never raises — so a missing/invalid COOKIE_URL doesn't crash bot startup).
    """
    if not _is_valid_cookie_url(COOKIE_URL):
        LOGGER.warning(
            f"⚠️ COOKIE_URL not set or invalid in env. Got: {COOKIE_URL!r}. "
            "Skipping cookie download — YouTube playback may fail bot-check."
        )
        return False

    raw_url = resolve_raw_cookie_url(COOKIE_URL)

    if not _is_valid_cookie_url(raw_url):
        LOGGER.warning(f"⚠️ Resolved cookie URL is invalid: {raw_url!r}")
        return False

    try:
        response = await asyncio.to_thread(
            requests.get,
            raw_url,
            timeout=15,
            headers={"User-Agent": "anonmusic-cookie-fetcher/1.0"},
        )
        response.raise_for_status()
    except Exception as e:
        LOGGER.warning(f"⚠️ Can't fetch cookies: {e}")
        return False

    cookies = (response.text or "").strip()

    if not cookies.startswith("# Netscape"):
        LOGGER.warning("⚠️ Invalid cookie format. Needs Netscape format.")
        return False

    if len(cookies) < 100:
        LOGGER.warning("⚠️ Cookie content too short. Possibly invalid.")
        return False

    try:
        COOKIE_PATH.parent.mkdir(parents=True, exist_ok=True)
        COOKIE_PATH.write_text(cookies, encoding="utf-8")
    except Exception as e:
        LOGGER.warning(f"⚠️ Failed to save cookies: {e}")
        return False

    LOGGER.info(f"✅ Cookies saved to {COOKIE_PATH}")
    return True


def cookie_txt_file() -> str:
    """
    Some AnonXMusic forks call a function like this instead of importing
    COOKIE_PATH directly. Kept here for compatibility with older call sites.
    """
    return str(COOKIE_PATH)
