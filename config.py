import re
from os import getenv

from dotenv import load_dotenv
from pyrogram import filters

import os

YTDL_COOKIES = os.getenv("YTDL_COOKIES", "cookies.txt")

# Load variables from .env file
load_dotenv()

# Telegram API credentials (get from https://my.telegram.org/apps)
API_ID = int(getenv("API_ID"))
API_HASH = getenv("API_HASH")

# Bot token (from @BotFather)
BOT_TOKEN = getenv("BOT_TOKEN")

# MongoDB connection URI (for storing user & session data)
MONGO_DB_URI = getenv("MONGO_DB_URI", None)

# YouTube streaming proxy and key (used in API backend)
YTPROXY_URL = getenv("YTPROXY_URL", "http://80.211.135.205:1470/youtube/")
YT_API_KEY = getenv("YT_API_KEY", "AIzaSyCNDWhirI16BIMq66vMVsibtSiUQ6swguY")
DOWNLOADS_DIR = getenv("DOWNLOADS_DIR", "downloads")

BOT_DOCS =  getenv("BOT_DOCS", "https://radha-music.vercel.app")
MINI_APP =  getenv("MINI_APP", "https://heroku-club.vercel.app")

COOKIES_URL = getenv("COOKIES_URL", None)
COOKIE_URL = getenv("COOKIE_URL", "https://pastebin.com/RurxsvMF")
# Limits and durations
DURATION_LIMIT_MIN = int(getenv("DURATION_LIMIT", 300))  # Max duration in minutes
ASSISTANT_LEAVE_TIME = int(getenv("ASSISTANT_LEAVE_TIME", 5400))  # Time after which assistant leaves (in seconds)
CACHE_DURATION = int(getenv("CACHE_DURATION", 86400))  # Duration to cache files
CACHE_SLEEP = int(getenv("CACHE_SLEEP", 3600))  # Interval to clean cache

# Logging & ownership
LOGGER_ID = int(getenv("LOGGER_ID"))  # Chat ID where logs go
OWNER_ID = int(getenv("OWNER_ID"))    # Your Telegram ID

# Heroku deployment (optional)
HEROKU_APP_NAME = getenv("HEROKU_APP_NAME")
HEROKU_API_KEY = getenv("HEROKU_API_KEY")

# Git repo details (for updates & deployment)
UPSTREAM_REPO = getenv("UPSTREAM_REPO", "https://github.com/VNI0X/ANONMUSIC")
UPSTREAM_BRANCH = getenv("UPSTREAM_BRANCH", "Master")
GIT_TOKEN = getenv("GIT_TOKEN")  # Only required for private repos

# Support & community
SUPPORT_CHANNEL = getenv("SUPPORT_CHANNEL", "https://t.me/heroku_club")
SUPPORT_CHAT = getenv("SUPPORT_CHAT", "https://t.me/nobita_support")

# Assistant auto-leave =Voice Chat and Chat's setting
AUTO_LEAVING_ASSISTANT = bool(getenv("AUTO_LEAVING_ASSISTANT", False))
AUTO_END_STREAM = bool(getenv("AUTO_END_STREAM", False))

# Spotify credentials (from https://developer.spotify.com/dashboard)
SPOTIFY_CLIENT_ID = getenv("SPOTIFY_CLIENT_ID", "22b6125bfe224587b722d6815002db2b")
SPOTIFY_CLIENT_SECRET = getenv("SPOTIFY_CLIENT_SECRET", "c9c63c6fbf2f467c8bc68624851e9773")

# Playlist track fetch limit
PLAYLIST_FETCH_LIMIT = int(getenv("PLAYLIST_FETCH_LIMIT", 25))

# File size limits in bytes (check https://www.gbmb.org/mb-to-bytes)
TG_AUDIO_FILESIZE_LIMIT = int(getenv("TG_AUDIO_FILESIZE_LIMIT", 204857600))  # ~195 MB
TG_VIDEO_FILESIZE_LIMIT = int(getenv("TG_VIDEO_FILESIZE_LIMIT", 2073741824))  # ~1.93 GB

# Private mode memory limit
PRIVATE_BOT_MODE_MEM = int(getenv("PRIVATE_BOT_MODE_MEM", 1))

# Pyrogram session strings (get from @SESSIONxGENxBOT)
STRING1 = getenv("STRING_SESSION")
STRING2 = getenv("STRING_SESSION2")
STRING3 = getenv("STRING_SESSION3")
STRING4 = getenv("STRING_SESSION4")
STRING5 = getenv("STRING_SESSION5")

# In-memory bot data and cache
BANNED_USERS = filters.user()
adminlist = {}
lyrical = {}
votemode = {}
autoclean = []
confirmer = {}
file_cache: dict[str, float] = {}

# Bot images used in replies and menus
START_IMG_URLS = [
    "https://files.catbox.moe/3b02mr.jpg",
    "https://files.catbox.moe/32kq7b.jpg",
    "https://files.catbox.moe/6dpnb9.jpg",
    "https://files.catbox.moe/wlbp8e.jpg",
    "https://files.catbox.moe/v7hzfr.jpg",
    "https://files.catbox.moe/8vfwuk.jpg",
    "https://files.catbox.moe/3urmnu.jpg",
    "https://files.catbox.moe/puzag2.jpg",
    "https://files.catbox.moe/e87w5q.jpg",
    "https://files.catbox.moe/i84mwm.jpg",
]

START_IMG_URL = getenv("START_IMG_URL", "https://files.catbox.moe/x3a3nc.jpg")
PING_IMG_URL = getenv("PING_IMG_URL", "https://files.catbox.moe/x3a3nc.jpg")
PLAYLIST_IMG_URL = getenv("PLAYLIST_IMG_URL", "https://files.catbox.moe/v7u8ji.jpg")
STATS_IMG_URL = getenv("STATS_IMG_URL", "https://files.catbox.moe/7g7j9f.jpg")
TELEGRAM_AUDIO_URL = getenv("TELEGRAM_AUDIO_URL", "https://files.catbox.moe/fahcob.jpg")
TELEGRAM_VIDEO_URL = getenv("TELEGRAM_VIDEO_URL", "https://files.catbox.moe/gy14qk.jpg")
STREAM_IMG_URL = getenv("STREAM_IMG_URL", "https://files.catbox.moe/h0m0wz.jpg")
SOUNCLOUD_IMG_URL = getenv("SOUNCLOUD_IMG_URL", "https://files.catbox.moe/ieduw9.jpg")
YOUTUBE_IMG_URL = getenv("YOUTUBE_IMG_URL", "https://files.catbox.moe/rnwmfw.jpg")
SPOTIFY_ARTIST_IMG_URL = getenv("SPOTIFY_ARTIST_IMG_URL", "https://files.catbox.moe/66ye0m.jpg")
SPOTIFY_ALBUM_IMG_URL = getenv("SPOTIFY_ALBUM_IMG_URL", "https://files.catbox.moe/66ye0m.jpg")
SPOTIFY_PLAYLIST_IMG_URL = getenv("SPOTIFY_PLAYLIST_IMG_URL", "https://files.catbox.moe/66ye0m.jpg")

# Convert time (hh:mm:ss) to seconds
def time_to_seconds(time: str) -> int:
    return sum(int(x) * 60 ** i for i, x in enumerate(reversed(time.split(":"))))

# Duration limit in seconds
DURATION_LIMIT = time_to_seconds(f"{DURATION_LIMIT_MIN}:00")

# Validate URLs for support links
if SUPPORT_CHANNEL and not re.match(r"^(?:http|https)://", SUPPORT_CHANNEL):
    raise SystemExit("[ERROR] - SUPPORT_CHANNEL URL must start with http/https.")

if SUPPORT_CHAT and not re.match(r"^(?:http|https)://", SUPPORT_CHAT):
    raise SystemExit("[ERROR] - SUPPORT_CHAT URL must start with http/https.")
