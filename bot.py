import asyncio
import html
import logging
import os
import threading
import time

from telegram import Update
from telegram.ext import (
    Application,
    BaseHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from config import (
    BOT_TOKEN,
    ENABLE_TIKTOK_DOWNLOAD,
    MIRROR_HOST,
    RESTART_ON_STOP,
)
from link_mirror import replace_instagram_hosts
from tiktok_downloader import TikTokDownloader
from tiktok_urls import extract_tiktok_urls

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


class EditedPlainTextHandler(BaseHandler):
    """Plain-text messages that were edited (not slash commands)."""

    def __init__(self, callback):
        super().__init__(callback)

    def check_update(self, update: Update) -> bool:
        msg = update.edited_message
        return bool(msg and msg.text and not msg.text.startswith("/"))


class SocialLinksBot:
    """
    Instagram: rewrite links to a mirror host for Telegram previews.
    TikTok: download via yt-dlp and send the MP4 (optional).
    """

    def __init__(self):
        self.mirror_host = MIRROR_HOST
        self.downloader = TikTokDownloader() if ENABLE_TIKTOK_DOWNLOAD else None
        self.application = Application.builder().token(BOT_TOKEN).build()
        self._register_handlers()

    def _register_handlers(self) -> None:
        self.application.add_handler(CommandHandler("start", self.cmd_start))
        self.application.add_handler(CommandHandler("help", self.cmd_help))

        async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
            await self._handle_incoming(update, context)

        self.application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text)
        )
        self.application.add_handler(EditedPlainTextHandler(handle_text))

        self.application.add_error_handler(self.error_handler)

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        host = html.escape(self.mirror_host)
        tt = (
            " I can also download <b>TikTok</b> videos and send the file here."
            if ENABLE_TIKTOK_DOWNLOAD
            else ""
        )
        await update.message.reply_text(
            "Send an Instagram post, reel, or TV link - I'll reply with the same "
            f"URL on <b>www.{host}</b> so Telegram can show a preview.{tt}\n\n"
            "Works in groups and DMs. Use /help.",
            parse_mode="HTML",
        )

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        host = html.escape(self.mirror_host)
        lines = [
            "<b>Instagram</b>",
            "Paste any <code>instagram.com</code> link. I'll rewrite the host to ",
            f"<code>www.{host}</code> (set <code>MIRROR_HOST</code>) for link previews.",
        ]
        if ENABLE_TIKTOK_DOWNLOAD:
            lines += [
                "",
                "<b>TikTok</b>",
                "Paste a <code>tiktok.com</code> or <code>vm.tiktok.com</code> link. "
                "I'll download it with yt-dlp and send the video (max ~50&nbsp;MB). "
                "Set <code>ENABLE_TIKTOK_DOWNLOAD=false</code> to turn this off.",
            ]
        lines += ["", "<i>Only one polling instance per bot token (local vs Railway).</i>"]
        await update.message.reply_text("\n".join(lines), parse_mode="HTML")

    async def _handle_incoming(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        message = update.message or update.edited_message
        if not message or not message.text:
            return

        text = message.text

        mirror_text, ig_changed = replace_instagram_hosts(text, self.mirror_host)
        if ig_changed:
            thread_id = getattr(message, "message_thread_id", None)
            await message.reply_text(
                mirror_text,
                disable_web_page_preview=False,
                reply_to_message_id=message.message_id,
                message_thread_id=thread_id,
            )

        if self.downloader:
            for link in extract_tiktok_urls(text):
                if self.downloader.is_valid_tiktok_url(link):
                    await self._process_tiktok(context, message, link)

    async def _process_tiktok(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        message,
        link: str,
    ) -> None:
        chat_id = message.chat_id
        thread_id = getattr(message, "message_thread_id", None)

        status = await context.bot.send_message(
            chat_id=chat_id,
            text=f"⏳ Downloading TikTok…\n<code>{html.escape(link)}</code>",
            parse_mode="HTML",
            reply_to_message_id=message.message_id,
            message_thread_id=thread_id,
        )

        try:
            ok, detail, media_files = await asyncio.to_thread(
                self.downloader.download_video, link
            )
        except Exception as e:
            logger.exception("TikTok download crashed: %s", e)
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=status.message_id,
                text="❌ TikTok download failed unexpectedly.",
                message_thread_id=thread_id,
            )
            return

        if not ok:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=status.message_id,
                text=str(detail)[:3900],
                message_thread_id=thread_id,
            )
            return

        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=status.message_id,
            text="✅ Sending video…",
            message_thread_id=thread_id,
        )

        try:
            for media in media_files:
                cap = html.escape(media.get("title") or "TikTok")[:1020]
                with open(media["file_path"], "rb") as vf:
                    await context.bot.send_video(
                        chat_id=chat_id,
                        video=vf,
                        caption=cap[:1024],
                        parse_mode="HTML",
                        message_thread_id=thread_id,
                    )
                await asyncio.sleep(0.4)
        except Exception as e:
            logger.exception("Sending TikTok video failed: %s", e)
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"❌ Could not upload the video: {e}",
                message_thread_id=thread_id,
            )
        finally:
            await asyncio.to_thread(self.downloader.cleanup_files, media_files)
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=status.message_id)
            except Exception:
                pass

    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        logger.error(
            "Unhandled error while processing update",
            exc_info=context.error,
        )

    def start_web_server(self) -> bool:
        """Health endpoint for Railway and similar hosts."""
        try:
            from flask import Flask, jsonify

            app = Flask(__name__)

            @app.route("/health")
            def health_check():
                return jsonify(
                    {
                        "status": "healthy",
                        "service": "social-links-bot",
                        "mirror": self.mirror_host,
                        "tiktok": bool(self.downloader),
                        "timestamp": time.time(),
                    }
                )

            @app.route("/")
            def root():
                return jsonify(
                    {
                        "status": "running",
                        "health": "/health",
                        "mirror": self.mirror_host,
                        "tiktok": bool(self.downloader),
                    }
                )

            def run_flask() -> None:
                port = int(os.environ.get("PORT", "8000"))
                app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

            threading.Thread(target=run_flask, daemon=True).start()
            logger.info("Health server on port %s", os.environ.get("PORT", "8000"))
            return True
        except ImportError:
            logger.warning("Flask not installed; skipping /health server")
            return False
        except Exception as e:
            logger.error("Failed to start health server: %s", e)
            return False

    def run(self) -> None:
        logger.info(
            "Starting bot (IG mirror → %s, TikTok download=%s)",
            self.mirror_host,
            bool(self.downloader),
        )
        threading.Thread(target=self.start_web_server, daemon=True).start()

        while True:
            try:
                self.application.run_polling(allowed_updates=Update.ALL_TYPES)
            except Exception as e:
                logger.error("Polling stopped: %s", e)

            if RESTART_ON_STOP:
                logger.warning("Restarting in 5 seconds...")
                time.sleep(5)
            else:
                break


def main() -> None:
    SocialLinksBot().run()


if __name__ == "__main__":
    main()
