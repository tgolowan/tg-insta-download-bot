import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Bot configuration
BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is required")

# Download settings
DOWNLOAD_PATH = os.getenv('DOWNLOAD_PATH', './downloads')
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB limit for Telegram

# Supported TikTok content types
SUPPORTED_TYPES = ['video']

# Error messages
ERROR_MESSAGES = {
    'invalid_link': '❌ Invalid TikTok link. Please provide a valid TikTok video URL.',
    'download_failed': '❌ Failed to download video. The video might be private or unavailable.',
    'file_too_large': '❌ File is too large to send via Telegram (max 50MB).',
    'unsupported_type': '❌ This type of TikTok content is not supported.',
    'rate_limited': '⚠️ Rate limit reached. Please try again later.',
    'private_account': '❌ Cannot access private TikTok videos. The video might be private or age-restricted.',
    'connection_error': '❌ Connection error. Please check your internet and try again.',
    'forbidden': '❌ Access forbidden. This video might be private or require authentication.',
    'tiktok_unavailable': '❌ TikTok is currently unavailable. Please try again later.',
}
