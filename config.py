import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Bot configuration
BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is required")

# Instagram configuration
INSTAGRAM_USERNAME = os.getenv('INSTAGRAM_USERNAME', '')
INSTAGRAM_PASSWORD = os.getenv('INSTAGRAM_PASSWORD', '')

# Download settings
DOWNLOAD_PATH = os.getenv('DOWNLOAD_PATH', './downloads')
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB limit for Telegram

# Supported Instagram content types
SUPPORTED_TYPES = ['image', 'video', 'carousel']

# Error messages
ERROR_MESSAGES = {
    'invalid_link': '❌ Invalid Instagram link. Please provide a valid Instagram post URL.',
    'download_failed': '❌ Failed to download media. The post might be private or unavailable.',
    'file_too_large': '❌ File is too large to send via Telegram (max 50MB).',
    'unsupported_type': '❌ This type of Instagram content is not supported.',
    'rate_limited': '⚠️ Instagram rate limit reached. Please try again later.',
    'private_account': '❌ Cannot access private Instagram accounts.',
}
