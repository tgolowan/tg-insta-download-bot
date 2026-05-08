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

from config import BOT_TOKEN, MIRROR_HOST, RESTART_ON_STOP
from link_mirror import replace_instagram_hosts

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


class IgMirrorTelegramBot:
    def __init__(self):
        self.mirror_host = MIRROR_HOST
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
        await update.message.reply_text(
            "Send an Instagram post, reel, or TV link - I'll reply with the same "
            f"URL on <b>www.{host}</b> so Telegram can show a preview.\n\n"
            "Works in groups and DMs. Use /help for details.",
            parse_mode="HTML",
        )

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        host = html.escape(self.mirror_host)
        await update.message.reply_text(
            "Paste any <code>instagram.com</code> link (optionally with other text). "
            "I'll echo your message with the host swapped for the mirror so link "
            "previews load.\n\n"
            f"Mirror host: <code>www.{host}</code> (set <code>MIRROR_HOST</code> to change).\n"
            "If previews are missing, the mirror may be down or omit Open Graph tags.",
            parse_mode="HTML",
        )

    async def _handle_incoming(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.message or update.edited_message
        if not message or not message.text:
            return

        new_text, changed = replace_instagram_hosts(message.text, self.mirror_host)
        if not changed:
            return

        thread_id = getattr(message, "message_thread_id", None)
        kw = dict(
            text=new_text,
            disable_web_page_preview=False,
            reply_to_message_id=message.message_id,
            message_thread_id=thread_id,
        )
        await message.reply_text(**kw)

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
                        "service": "ig-link-mirror",
                        "mirror": self.mirror_host,
                        "timestamp": time.time(),
                    }
                )

            @app.route("/")
            def root():
                return jsonify(
                    {"status": "running", "health": "/health", "mirror": self.mirror_host}
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
        logger.info("Starting Instagram → %s mirror bot", self.mirror_host)
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
    IgMirrorTelegramBot().run()


if __name__ == "__main__":
    main()
