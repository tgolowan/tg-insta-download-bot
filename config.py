import os

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is required")

# Host only, e.g. kkclip.com -> URLs become https://www.kkclip.com/...
MIRROR_HOST = os.getenv("MIRROR_HOST", "kkclip.com")

RESTART_ON_STOP = os.getenv("RESTART_ON_STOP", "true").lower() in ("1", "true", "yes")
