import asyncio
import logging
import re
from typing import List, Dict
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode
from instagram_downloader import InstagramDownloader
from config import BOT_TOKEN, ERROR_MESSAGES
import asyncio
import logging
import re
import os
import time
from typing import List, Dict
import threading

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class InstagramDownloadBot:
    def __init__(self):
        """Initialize the bot with Instagram downloader."""
        self.downloader = InstagramDownloader()
        self.application = Application.builder().token(BOT_TOKEN).build()
        self.setup_handlers()
        self.web_app = None
        self.web_runner = None
    
    def setup_handlers(self):
        """Set up bot command and message handlers."""
        # Command handlers
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("status", self.status_command))
        
        # Message handler for Instagram links
        self.application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND, 
            self.handle_message
        ))
        
        # Error handler
        self.application.add_error_handler(self.error_handler)
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command."""
        welcome_message = """
🤖 **Instagram Download Bot**

I can download media from Instagram posts and reels!

**How to use:**
1. Simply paste an Instagram link in the chat
2. I'll automatically detect it and download the media
3. The media will be sent back to you

**Supported content:**
• Single images
• Single videos  
• Carousel posts (multiple images/videos)

**Commands:**
/help - Show this help message
/status - Check bot status

**Note:** I work in both private chats and groups!
        """
        
        await update.message.reply_text(
            welcome_message,
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command."""
        help_text = """
📖 **Help & Instructions**

**Basic Usage:**
• Paste any Instagram post or reel link
• I'll automatically download and send the media back

**What I can download:**
✅ Public Instagram posts
✅ Instagram reels
✅ Carousel posts (up to 10 items)
✅ Both images and videos

**Limitations:**
❌ Private accounts (unless I'm logged in)
❌ Stories (not supported)
❌ Files larger than 50MB
❌ Rate-limited by Instagram

**Troubleshooting:**
• Make sure the link is from a public post
• Try again later if you get rate-limited
• Contact admin if issues persist

**Example links:**
• https://www.instagram.com/p/ABC123/
• https://instagram.com/reel/XYZ789/
        """
        
        await update.message.reply_text(
            help_text,
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command."""
        status_text = """
📊 **Bot Status**

**Status:** ✅ Online
**Instagram Login:** {'✅ Logged in' if self.downloader.loader.context.is_logged_in else '❌ Not logged in'}
**Download Path:** `./downloads`
**Max File Size:** 50MB

**Recent Activity:** All systems operational
        """
        
        await update.message.reply_text(
            status_text,
            parse_mode=ParseMode.MARKDOWN
        )
    
    def extract_instagram_links(self, text: str) -> List[str]:
        """Extract Instagram links from text message."""
        # Regex pattern for Instagram URLs
        pattern = r'https?://(?:www\.)?instagram\.com/(?:p|reel)/[a-zA-Z0-9_-]+/?'
        return re.findall(pattern, text)
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle incoming messages and detect Instagram links."""
        message = update.message
        text = message.text
        
        if not text:
            return
        
        # Extract Instagram links
        instagram_links = self.extract_instagram_links(text)
        
        if not instagram_links:
            return
        
        # Process each Instagram link
        for link in instagram_links:
            await self.process_instagram_link(update, context, link)
    
    async def process_instagram_link(self, update: Update, context: ContextTypes.DEFAULT_TYPE, link: str):
        """Process a single Instagram link and download media."""
        chat_id = update.effective_chat.id
        message = update.message
        
        # Send processing message
        processing_msg = await context.bot.send_message(
            chat_id=chat_id,
            text=f"🔄 Processing Instagram link...\n{link}"
        )
        
        try:
            # Download the post
            success, message_text, media_files = self.downloader.download_post(link)
            
            if not success:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=processing_msg.message_id,
                    text=f"❌ {message_text}"
                )
                return
            
            # Send success message
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=processing_msg.message_id,
                text=f"✅ {message_text}"
            )
            
            # Send media files
            await self.send_media_files(context, chat_id, media_files)
            
            # Clean up downloaded files
            self.downloader.cleanup_files(media_files)
            
        except Exception as e:
            logger.error(f"Error processing Instagram link: {e}")
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=processing_msg.message_id,
                text="❌ An error occurred while processing the link. Please try again."
            )
    
    async def send_media_files(self, context: ContextTypes.DEFAULT_TYPE, chat_id: int, media_files: List[Dict]):
        """Send downloaded media files to the chat."""
        for media in media_files:
            try:
                if media['type'] == 'image':
                    await context.bot.send_photo(
                        chat_id=chat_id,
                        photo=open(media['file_path'], 'rb'),
                        caption=f"📸 Instagram Image\nSize: {media['file_size'] / 1024 / 1024:.1f}MB"
                    )
                elif media['type'] == 'video':
                    await context.bot.send_video(
                        chat_id=chat_id,
                        video=open(media['file_path'], 'rb'),
                        caption=f"🎥 Instagram Video\nSize: {media['file_size'] / 1024 / 1024:.1f}MB"
                    )
                
                # Small delay to avoid flooding
                await asyncio.sleep(0.5)
                
            except Exception as e:
                logger.error(f"Error sending media file: {e}")
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"❌ Failed to send media file: {media['file_path']}"
                )
    
    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle errors in the bot."""
        logger.error(f"Update {update} caused error {context.error}")
        
        if update and update.effective_chat:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❌ An error occurred. Please try again later."
            )
    
    def start_web_server(self):
        """Start web server for health checks using Flask (synchronous)."""
        try:
            from flask import Flask, jsonify
            import threading
            
            app = Flask(__name__)
            
            @app.route('/health')
            def health_check():
                return jsonify({
                    'status': 'healthy',
                    'bot': 'running',
                    'timestamp': time.time()
                })
            
            @app.route('/')
            def root():
                return jsonify({
                    'status': 'Instagram Download Bot is running',
                    'health': '/health'
                })
            
            def run_flask():
                port = int(os.environ.get('PORT', 8000))
                app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
            
            # Start Flask in a separate thread
            flask_thread = threading.Thread(target=run_flask, daemon=True)
            flask_thread.start()
            
            logger.info(f"Web server started on port {os.environ.get('PORT', 8000)}")
            return True
            
        except ImportError:
            logger.warning("Flask not available, using simple HTTP server")
            return self._start_simple_server()
        except Exception as e:
            logger.error(f"Failed to start web server: {e}")
            return False
    
    def _start_simple_server(self):
        """Fallback to simple HTTP server if Flask fails."""
        try:
            import http.server
            import socketserver
            
            class HealthCheckHandler(http.server.BaseHTTPRequestHandler):
                def do_GET(self):
                    if self.path == '/health':
                        self.send_response(200)
                        self.send_header('Content-type', 'application/json')
                        self.end_headers()
                        response = {
                            'status': 'healthy',
                            'bot': 'running',
                            'timestamp': time.time()
                        }
                        self.wfile.write(str(response).encode())
                    else:
                        self.send_response(200)
                        self.send_header('Content-type', 'text/plain')
                        self.end_headers()
                        self.wfile.write(b'Instagram Download Bot is running\nHealth: /health')
                
                def log_message(self, format, *args):
                    # Suppress logging for health checks
                    pass
            
            def run_simple_server():
                port = int(os.environ.get('PORT', 8000))
                with socketserver.TCPServer(("0.0.0.0", port), HealthCheckHandler) as httpd:
                    httpd.serve_forever()
            
            # Start simple server in a separate thread
            server_thread = threading.Thread(target=run_simple_server, daemon=True)
            server_thread.start()
            
            logger.info(f"Simple HTTP server started on port {os.environ.get('PORT', 8000)}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start simple server: {e}")
            return False
    
    def run(self):
        """Start the bot with web server and supervise unexpected stops."""
        logger.info("Starting Instagram Download Bot...")

        # Start web server in a separate thread
        web_thread = threading.Thread(target=self.start_web_server, daemon=True)
        web_thread.start()

        restart_on_stop = os.getenv('RESTART_ON_STOP', 'true').lower() in ['1', 'true', 'yes']

        while True:
            try:
                # This blocks until a stop signal is received or an unrecoverable error occurs
                self.application.run_polling(allowed_updates=Update.ALL_TYPES)
            except Exception as e:
                logger.error(f"Bot crashed with exception: {e}")

            if restart_on_stop:
                logger.warning("Application stopped. Restarting in 5 seconds...")
                time.sleep(5)
                continue
            else:
                logger.info("Application stopped. Exiting.")
                break

def main():
    """Main function to run the bot."""
    try:
        bot = InstagramDownloadBot()
        bot.run()
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        raise

if __name__ == "__main__":
    main()
