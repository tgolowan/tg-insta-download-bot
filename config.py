import os
from typing import FrozenSet, Optional

from dotenv import load_dotenv

load_dotenv()


def _parse_allowed_chat_ids(raw: Optional[str]) -> Optional[FrozenSet[int]]:
    """
    None -> no whitelist (every chat allowed).
    frozenset -> only these chats get link/TikTok handling.
    Groups/supergroups use negative ids (e.g. -1001234567890).
    """
    if raw is None:
        return None
    s = raw.strip()
    if not s:
        return None
    out: set[int] = set()
    for part in s.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.add(int(part))
        except ValueError:
            continue
    return frozenset(out)


BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is required")

# Host only, e.g. kkclip.com -> URLs become https://www.kkclip.com/...
MIRROR_HOST = os.getenv("MIRROR_HOST", "kkclip.com")

RESTART_ON_STOP = os.getenv("RESTART_ON_STOP", "true").lower() in ("1", "true", "yes")

ENABLE_TIKTOK_DOWNLOAD = os.getenv(
    "ENABLE_TIKTOK_DOWNLOAD", "true"
).lower() in ("1", "true", "yes")

DOWNLOAD_PATH = os.getenv("DOWNLOAD_PATH", "./downloads")
MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE_MB", "50")) * 1024 * 1024

ERROR_MESSAGES = {
    "invalid_link": "❌ Invalid TikTok link.",
    "download_failed": "❌ Failed to download the video.",
    "file_too_large": "❌ File is too large to send via Telegram (max 50MB).",
    "unsupported_type": "❌ This TikTok format is not supported.",
    "rate_limited": "⚠️ Rate limited. Try again later.",
    "private_account": "❌ This video is private, age-restricted, or unavailable.",
    "connection_error": "❌ Connection error.",
    "forbidden": "❌ Access forbidden.",
    "tiktok_unavailable": "❌ TikTok temporarily unavailable.",
}

# Comma-separated chat_id list. Unset or empty = allow all chats.
ALLOWED_CHAT_IDS = _parse_allowed_chat_ids(os.getenv("ALLOWED_CHAT_IDS"))
