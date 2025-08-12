# Instagram Download Telegram Bot

A powerful Telegram bot that automatically detects Instagram links in chats and downloads the media content (images, videos, carousel posts) directly to the chat.

## Features

- 🤖 **Automatic Detection**: Automatically detects Instagram post and reel links in Telegram messages
- 📸 **Multi-Media Support**: Downloads images, videos, and carousel posts
- 🎯 **Smart Parsing**: Supports both `/p/` (posts) and `/reel/` (reels) Instagram URLs
- 🧹 **Auto-Cleanup**: Automatically removes downloaded files after sending to save storage
- 📱 **Group & Private Chat Support**: Works in both Telegram groups and private chats
- ⚡ **Real-time Processing**: Immediate response with progress updates
- 🛡️ **Error Handling**: Comprehensive error handling with user-friendly messages

## Supported Content Types

- ✅ Single Instagram images
- ✅ Single Instagram videos
- ✅ Carousel posts (multiple images/videos)
- ✅ Instagram reels
- ✅ Public accounts (private accounts with login)

## Prerequisites

- Python 3.8 or higher
- Telegram Bot Token (get from [@BotFather](https://t.me/BotFather))
- Instagram account credentials (optional but recommended)

## Installation

1. **Clone the repository:**
   ```bash
   git clone <your-repo-url>
   cd tg-insta-download-bot
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up environment variables:**
   ```bash
   cp env.example .env
   # Edit .env with your actual values
   ```

4. **Configure your bot:**
   - Get a bot token from [@BotFather](https://t.me/BotFather)
   - Add your Instagram credentials (optional)
   - Update the `.env` file

## Configuration

### Required Environment Variables

- `BOT_TOKEN`: Your Telegram bot token from @BotFather

### Optional Environment Variables

- `INSTAGRAM_USERNAME`: Your Instagram username (helps avoid rate limiting)
- `INSTAGRAM_PASSWORD`: Your Instagram password (helps avoid rate limiting)
- `DOWNLOAD_PATH`: Directory to store temporary downloads (default: `./downloads`)

### Example .env file:
```env
BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
INSTAGRAM_USERNAME=your_username
INSTAGRAM_PASSWORD=your_password
DOWNLOAD_PATH=./downloads
```

## Usage

### Starting the Bot

```bash
python bot.py
```

### Bot Commands

- `/start` - Welcome message and basic instructions
- `/help` - Detailed help and troubleshooting
- `/status` - Bot status and Instagram login status

### How It Works

1. **Add the bot to your Telegram group or start a private chat**
2. **Paste any Instagram link** (post or reel)
3. **The bot automatically:**
   - Detects the Instagram link
   - Downloads the media content
   - Sends it back to the chat
   - Cleans up temporary files

### Example Instagram Links

The bot supports these Instagram URL formats:
- `https://www.instagram.com/p/ABC123/` (posts)
- `https://instagram.com/reel/XYZ789/` (reels)
- `https://www.instagram.com/p/ABC123/?utm_source=ig_web_copy_link` (with parameters)

## Features in Detail

### Automatic Link Detection
The bot uses regex patterns to automatically detect Instagram links in messages, supporting:
- Standard Instagram post URLs
- Instagram reel URLs
- URLs with query parameters
- Both `www.instagram.com` and `instagram.com` domains

### Media Download
- **Images**: Downloads in highest available quality
- **Videos**: Downloads original video files
- **Carousels**: Downloads all items in multi-media posts
- **Size Limits**: Respects Telegram's 50MB file size limit

### Error Handling
- Invalid Instagram links
- Private account access issues
- Rate limiting protection
- File size limitations
- Network errors

## Troubleshooting

### Common Issues

1. **Bot not responding to Instagram links:**
   - Ensure the bot has permission to read messages in the group
   - Check that the Instagram link format is correct

2. **"Failed to download media" error:**
   - The Instagram post might be private
   - Instagram might be rate-limiting requests
   - Try adding Instagram credentials to `.env`

3. **"File too large" error:**
   - Instagram videos over 50MB cannot be sent via Telegram
   - This is a Telegram limitation, not the bot's fault

4. **Rate limiting issues:**
   - Add Instagram credentials to reduce rate limiting
   - Wait a few minutes before trying again

### Instagram Login Benefits

Adding Instagram credentials provides:
- Reduced rate limiting
- Access to some private content
- Better download success rates
- Higher quality media access

## Security Considerations

- **Never share your `.env` file** - it contains sensitive credentials
- **Use environment variables** for production deployments
- **Regularly update dependencies** to patch security vulnerabilities
- **Monitor bot usage** to prevent abuse

## Development

### Project Structure

```
tg-insta-download-bot/
├── bot.py                 # Main Telegram bot logic
├── instagram_downloader.py # Instagram media downloading
├── config.py              # Configuration and constants
├── requirements.txt       # Python dependencies
├── env.example           # Environment variables template
├── README.md             # This file
└── downloads/            # Temporary download directory
```

### Adding New Features

1. **New Media Types**: Extend the `InstagramDownloader` class
2. **Additional Commands**: Add handlers in `bot.py`
3. **Enhanced Error Handling**: Update error messages in `config.py`

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

If you encounter issues:
1. Check the troubleshooting section above
2. Review the bot logs for error details
3. Ensure all dependencies are properly installed
4. Verify your environment variables are set correctly

## Disclaimer

This bot is for educational and personal use. Please respect Instagram's Terms of Service and rate limits. The developers are not responsible for misuse of this tool.
