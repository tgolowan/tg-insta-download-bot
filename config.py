import logging
import os
from typing import FrozenSet, Optional

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


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
    if not out:
        logger.warning(
            "ALLOWED_CHAT_IDS is non-empty but no valid integers were parsed; ignoring "
            "allowlist so the bot stays usable — fix Railway / .env (typos)."
        )
        return None
    return frozenset(out)


BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is required")

# Display / fallback host — probe order always tries instagram7.com first.
MIRROR_HOST = os.getenv("MIRROR_HOST", "instagram7.com")

def _parse_mirror_fallbacks(raw: Optional[str]) -> tuple:
    default = (
        "instagram7.com",
        "vxinstagram.com",
        "zzinstagram.com",
    )
    if raw is None:
        return default
    s = raw.strip()
    if not s:
        return default
    out = tuple(p.strip() for p in s.split(",") if p.strip())
    return out if out else default


MIRROR_FALLBACK_HOSTS = _parse_mirror_fallbacks(os.getenv("MIRROR_FALLBACK_HOSTS"))

PREVIEW_PROBE_TIMEOUT = float(os.getenv("PREVIEW_PROBE_TIMEOUT", "8"))

CHECK_LINK_PREVIEW = os.getenv("CHECK_LINK_PREVIEW", "true").lower() in (
    "1",
    "true",
    "yes",
)

# When every mirror fails the preview probe, still reply with the first fallback host
# (usually instagram7.com) without probing — avoids silent no-ops on slow networks.
PREVIEW_FALLBACK_UNCHECKED = os.getenv("PREVIEW_FALLBACK_UNCHECKED", "true").lower() in (
    "1",
    "true",
    "yes",
)

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

# When ALLOWED_CHAT_IDS is set: allow one-to-one DMs without listing your user id (default).
# Set to false so only chats whose id appears in ALLOWED_CHAT_IDS work (add your user id for DM).
ALLOW_PRIVATE_CHAT = os.getenv("ALLOW_PRIVATE_CHAT", "true").lower() in (
    "1",
    "true",
    "yes",
)

# When true, INFO-log each Instagram mirror / TikTok job (visible in Railway runtime logs).
LOG_LINK_ACTIVITY = os.getenv("LOG_LINK_ACTIVITY", "false").lower() in (
    "1",
    "true",
    "yes",
)
