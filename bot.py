import asyncio
import html
import logging
import os
import threading
import time
from typing import Any, Dict, Optional

from telegram import Update
from telegram.constants import ChatType
from telegram.error import Conflict, TelegramError
from telegram.ext import (
    Application,
    BaseHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from config import (
    ALLOWED_CHAT_IDS,
    ALLOW_PRIVATE_CHAT,
    BOT_TOKEN,
    ENABLE_TIKTOK_DOWNLOAD,
    LOG_LINK_ACTIVITY,
    MIRROR_HOST,
    MIRROR_THREADS,
    RESTART_ON_STOP,
    THREADS_PREVIEW_MODE,
)
from link_mirror import replace_mirrored_social_links
from tiktok_downloader import TikTokDownloader
from tiktok_urls import extract_tiktok_urls

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def _forum_topic_api_kwargs(message_thread_id: Optional[int]) -> Optional[Dict[str, Any]]:
    """PTB v20 has no message_thread_id on edit/delete; pass it via api_kwargs for forum topics."""
    if message_thread_id is None:
        return None
    return {"message_thread_id": message_thread_id}


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
        self._mirror_threads = MIRROR_THREADS
        self._threads_preview_mode = THREADS_PREVIEW_MODE
        self._allowed_chat_ids = ALLOWED_CHAT_IDS
        self.downloader = TikTokDownloader() if ENABLE_TIKTOK_DOWNLOAD else None
        self.application = Application.builder().token(BOT_TOKEN).build()
        self._register_handlers()

    def _register_handlers(self) -> None:
        self.application.add_handler(CommandHandler("chatid", self.cmd_chatid))
        self.application.add_handler(CommandHandler("start", self.cmd_start))
        self.application.add_handler(CommandHandler("help", self.cmd_help))

        async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
            await self._handle_incoming(update, context)

        self.application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text)
        )
        self.application.add_handler(EditedPlainTextHandler(handle_text))

        self.application.add_error_handler(self.error_handler)

    def _chat_is_allowed(self, chat) -> bool:
        if self._allowed_chat_ids is None:
            return True
        if ALLOW_PRIVATE_CHAT and chat.type == ChatType.PRIVATE:
            return True
        return chat.id in self._allowed_chat_ids

    async def cmd_chatid(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Always works — use this to read a group's id before adding it to ALLOWED_CHAT_IDS."""
        chat = update.effective_chat
        user = update.effective_user
        if not chat or not update.message:
            return
        parts = [
            f"<b>chat id</b>: <code>{chat.id}</code>",
            f"<b>type</b>: <code>{html.escape(str(chat.type))}</code>",
        ]
        if getattr(chat, "title", None):
            parts.append(f"<b>title</b>: {html.escape(chat.title)}")
        if user:
            parts.append(f"<b>your user id</b>: <code>{user.id}</code>")
        parts += [
            "",
            "Add this <b>chat id</b> to the <code>ALLOWED_CHAT_IDS</code> env variable "
            "(comma-separated). Redeploy / restart the bot after changing it.",
        ]
        await update.message.reply_text("\n".join(parts), parse_mode="HTML")

    async def _safe_edit_message(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        chat_id: int,
        status_message_id: int,
        message_thread_id,
        text: str,
    ) -> None:
        """edit_message_text can fail when two pollers compete or Telegram rejects edits."""
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=status_message_id,
                text=text[:3900],
                api_kwargs=_forum_topic_api_kwargs(message_thread_id),
            )
        except TelegramError as exc:
            logger.warning("Could not edit status message: %s", exc)

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._chat_is_allowed(update.effective_chat):
            return
        host = html.escape(self.mirror_host)
        tt = (
            " I can also download <b>TikTok</b> videos and send the file here."
            if ENABLE_TIKTOK_DOWNLOAD
            else ""
        )
        await update.message.reply_text(
            "Send an Instagram or Meta Threads link - I'll reply with the same URL on "
            f"<b>www.{host}</b> when previews work on that mirror.{tt}\n\n"
            "Forum topics supported: replies stay inside the topic. "
            "Works in groups and DMs. Use /help.",
            parse_mode="HTML",
        )

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._chat_is_allowed(update.effective_chat):
            return
        host = html.escape(self.mirror_host)
        lines = [
            "<b>Instagram</b>",
            "Paste any <code>instagram.com</code> link. I'll rewrite the host to ",
            f"<code>www.{host}</code> (set <code>MIRROR_HOST</code>) for link previews.",
        ]
        if self._mirror_threads:
            lines.append(
                "Threads: <code>threads.net</code> → preview via "
                f"<code>{html.escape(self._threads_preview_mode)}</code> "
                "(<code>THREADS_PREVIEW_MODE</code>; try <code>vxthreads</code> or "
                "<code>fixthreads_seria</code>). Set <code>MIRROR_THREADS=false</code> to disable."
            )
        if ENABLE_TIKTOK_DOWNLOAD:
            lines += [
                "",
                "<b>TikTok</b>",
                "Paste a <code>tiktok.com</code> or <code>vm.tiktok.com</code> link. "
                "I'll download it with yt-dlp and send the video (max ~50&nbsp;MB). "
                "Set <code>ENABLE_TIKTOK_DOWNLOAD=false</code> to turn this off.",
            ]
        lines += ["", "<i>Only one polling instance per bot token (local vs Railway).</i>"]
        if self._allowed_chat_ids is not None:
            lines += [
                "",
                "<b>Access</b>: Groups are limited to <code>ALLOWED_CHAT_IDS</code>. "
                "Private chat with this bot is still allowed (set "
                "<code>ALLOW_PRIVATE_CHAT=false</code> to disable). "
                "Use <code>/chatid</code> to read an id.",
            ]
        await update.message.reply_text("\n".join(lines), parse_mode="HTML")

    async def _handle_incoming(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        message = update.message or update.edited_message
        if not message or not message.text:
            return

        if not self._chat_is_allowed(message.chat):
            return

        text = message.text

        mirror_text, mirrored = replace_mirrored_social_links(
            text,
            self.mirror_host,
            mirror_threads=self._mirror_threads,
            threads_preview_mode=self._threads_preview_mode,
        )
        if mirrored:
            if LOG_LINK_ACTIVITY:
                logger.info(
                    "Handled social mirror chat_id=%s topic=%s",
                    message.chat_id,
                    getattr(message, "message_thread_id", None),
                )
            await message.reply_text(
                mirror_text,
                disable_web_page_preview=False,
            )

        if self.downloader:
            for link in extract_tiktok_urls(text):
                if self.downloader.is_valid_tiktok_url(link):
                    if LOG_LINK_ACTIVITY:
                        logger.info(
                            "TikTok download start chat_id=%s host=%s…",
                            message.chat_id,
                            link[:48],
                        )
                    await self._process_tiktok(context, message, link)

    async def _process_tiktok(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        message,
        link: str,
    ) -> None:
        chat_id = message.chat_id
        thread_id = getattr(message, "message_thread_id", None)

        status = await message.reply_text(
            text=f"⏳ Downloading TikTok…\n<code>{html.escape(link)}</code>",
            parse_mode="HTML",
        )

        try:
            ok, detail, media_files = await asyncio.to_thread(
                self.downloader.download_video, link
            )
        except Exception as e:
            logger.exception("TikTok download crashed: %s", e)
            await self._safe_edit_message(
                context,
                chat_id,
                status.message_id,
                thread_id,
                "❌ TikTok download failed unexpectedly.",
            )
            return

        if not ok:
            await self._safe_edit_message(
                context,
                chat_id,
                status.message_id,
                thread_id,
                str(detail),
            )
            return

        if not media_files:
            await self._safe_edit_message(
                context,
                chat_id,
                status.message_id,
                thread_id,
                "❌ Download finished but no file was produced.",
            )
            return

        await self._safe_edit_message(
            context,
            chat_id,
            status.message_id,
            thread_id,
            "✅ Sending video…",
        )

        try:
            for media in media_files:
                path = media["file_path"]
                raw_cap = media.get("title") or ""
                cap = html.escape(raw_cap.strip())[:1020] if raw_cap.strip() else ""
                vid_kw = dict(
                    chat_id=chat_id,
                    video=path,
                    message_thread_id=thread_id,
                )
                if cap:
                    vid_kw["caption"] = cap[:1024]
                    vid_kw["parse_mode"] = "HTML"
                try:
                    await context.bot.send_video(**vid_kw)
                except TelegramError as send_err:
                    logger.warning(
                        "send_video failed (%s); retrying as document", send_err
                    )
                    doc_kw = dict(
                        chat_id=chat_id,
                        document=path,
                        filename=os.path.basename(path),
                        message_thread_id=thread_id,
                    )
                    if cap:
                        doc_kw["caption"] = cap[:1024]
                        doc_kw["parse_mode"] = "HTML"
                    await context.bot.send_document(**doc_kw)
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
                await context.bot.delete_message(
                    chat_id=chat_id,
                    message_id=status.message_id,
                    api_kwargs=_forum_topic_api_kwargs(thread_id),
                )
            except Exception:
                pass

    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        err = context.error
        if isinstance(err, Conflict):
            logger.warning(
                "Telegram Conflict: another client is polling with the same BOT_TOKEN. "
                "Stop the duplicate (e.g. local python bot.py vs Railway)."
            )
            return
        logger.error(
            "Unhandled error while processing update",
            exc_info=err,
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
