import asyncio
import html
import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional

from telegram import InputMediaPhoto, MessageEntity, Update
from telegram.constants import ChatType
from telegram.error import Conflict, NetworkError, TelegramError, TimedOut
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
    CHECK_LINK_PREVIEW,
    ENABLE_INSTAGRAM_REEL_DOWNLOAD,
    ENABLE_TIKTOK_DOWNLOAD,
    LOG_LINK_ACTIVITY,
    MIRROR_FALLBACK_HOSTS,
    MIRROR_HOST,
    IG_MIRROR_BUDGET_SECONDS,
    PREVIEW_FALLBACK_UNCHECKED,
    PREVIEW_PROBE_TIMEOUT,
    RESTART_ON_STOP,
    TELEGRAM_MEDIA_WRITE_TIMEOUT,
    TELEGRAM_CONNECT_TIMEOUT,
    TELEGRAM_GET_UPDATES_READ_TIMEOUT,
    TELEGRAM_POOL_TIMEOUT,
    TELEGRAM_READ_TIMEOUT,
    TELEGRAM_WRITE_TIMEOUT,
)
from link_mirror import (
    collect_message_link_text,
    extract_instagram_urls,
    fast_mirror_instagram_text,
    replace_instagram_hosts_checked,
)
from instagram_reel_downloader import InstagramReelDownloader
from preview_check import is_instagram_reel, is_instagram_story, mirror_host_chain
from tiktok_downloader import TikTokDownloader, compress_for_telegram_upload
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
    """Edited captions or plain text (but not slash-command lines)."""

    def __init__(self, callback):
        super().__init__(callback)

    def check_update(self, update: Update) -> bool:
        msg = update.edited_message
        if not msg:
            return False
        body = collect_message_link_text(msg)
        return bool(body) and not body.lstrip().startswith("/")


class SocialLinksBot:
    """
    Instagram: rewrite links to a mirror host for Telegram previews.
    TikTok: download via yt-dlp and send the MP4 (optional).
    """

    def __init__(self):
        self.mirror_host = MIRROR_HOST
        self._mirror_hosts = mirror_host_chain(MIRROR_HOST, MIRROR_FALLBACK_HOSTS)
        self._check_preview = CHECK_LINK_PREVIEW
        self._preview_fallback_unchecked = PREVIEW_FALLBACK_UNCHECKED
        self._preview_timeout = PREVIEW_PROBE_TIMEOUT
        self._allowed_chat_ids = ALLOWED_CHAT_IDS
        # Telegram re-sends edited_message when link previews attach (same text).
        self._handled_bodies: dict[tuple[int, int], str] = {}
        self._handled_bodies_max = 4000
        self.downloader = TikTokDownloader() if ENABLE_TIKTOK_DOWNLOAD else None
        self.ig_reels = (
            InstagramReelDownloader() if ENABLE_INSTAGRAM_REEL_DOWNLOAD else None
        )
        self._build_application()

    def _build_application(self) -> None:
        self.application = (
            Application.builder()
            .token(BOT_TOKEN)
            .connect_timeout(TELEGRAM_CONNECT_TIMEOUT)
            .read_timeout(TELEGRAM_READ_TIMEOUT)
            .write_timeout(TELEGRAM_WRITE_TIMEOUT)
            .pool_timeout(TELEGRAM_POOL_TIMEOUT)
            .get_updates_read_timeout(TELEGRAM_GET_UPDATES_READ_TIMEOUT)
            .build()
        )
        self._register_handlers()

    def _register_handlers(self) -> None:
        self.application.add_handler(CommandHandler("chatid", self.cmd_chatid))
        self.application.add_handler(CommandHandler("start", self.cmd_start))
        self.application.add_handler(CommandHandler("help", self.cmd_help))

        async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
            await self._handle_incoming(update, context)

        msg_filter = (
            filters.TEXT
            | filters.CAPTION
            | filters.Entity(MessageEntity.URL)
            | filters.Entity(MessageEntity.TEXT_LINK)
        ) & ~filters.COMMAND
        self.application.add_handler(MessageHandler(msg_filter, handle_text))
        self.application.add_handler(EditedPlainTextHandler(handle_text))

        self.application.add_error_handler(self.error_handler)

    def _chat_is_allowed(self, chat) -> bool:
        if self._allowed_chat_ids is None:
            return True
        if ALLOW_PRIVATE_CHAT and chat.type == ChatType.PRIVATE:
            return True
        return chat.id in self._allowed_chat_ids

    def _remember_handled_body(self, chat_id: int, message_id: int, body: str) -> None:
        if len(self._handled_bodies) >= self._handled_bodies_max:
            drop = self._handled_bodies_max // 2
            for key in list(self._handled_bodies.keys())[:drop]:
                del self._handled_bodies[key]
        self._handled_bodies[(chat_id, message_id)] = body

    def _already_handled(self, chat_id: int, message_id: int, body: str) -> bool:
        return self._handled_bodies.get((chat_id, message_id)) == body

    async def _mirror_instagram_body(self, body: str) -> tuple[str, bool]:
        """Probe mirrors with a time budget; fall back to vx/kkclip rewrite without probes."""
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(
                    replace_instagram_hosts_checked,
                    body,
                    self._mirror_hosts,
                    verify_preview=self._check_preview,
                    preview_timeout=self._preview_timeout,
                    fallback_unchecked=self._preview_fallback_unchecked,
                ),
                timeout=IG_MIRROR_BUDGET_SECONDS,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "Instagram mirror probes exceeded %.0fs budget — using fast mirror",
                IG_MIRROR_BUDGET_SECONDS,
            )
        except Exception as exc:
            logger.warning("Instagram mirror probes failed: %s — using fast mirror", exc)
        return await asyncio.to_thread(
            fast_mirror_instagram_text, body, self._mirror_hosts
        )

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
            "Send an Instagram post, reel, or TV link - I'll reply with the same URL on "
            f"<b>www.{host}</b> so Telegram can show a preview.{tt}\n\n"
            "Forum topics: replies stay in the topic. "
            "Works in groups and DMs. Use /help.",
            parse_mode="HTML",
        )

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._chat_is_allowed(update.effective_chat):
            return
        host = html.escape(self.mirror_host)
        lines = [
            "<b>Instagram</b>",
            "Paste a link in message text <i>or</i> in a photo/video <b>caption</b>. ",
            f"I'll try mirrors in order (<code>eeinstagram.com</code> first for video previews), ",
            "probe each page, then fall back if needed.",
        ]
        if self._check_preview:
            fb = ", ".join(html.escape(h) for h in self._mirror_hosts[1:3])
            if fb:
                lines.append(f"Fallback hosts: <code>{fb}</code> …")
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
        if not message:
            return
        body = collect_message_link_text(message)
        if not body:
            return

        if message.from_user and message.from_user.is_bot:
            return

        if not self._chat_is_allowed(message.chat):
            if LOG_LINK_ACTIVITY:
                logger.info(
                    "Ignored link chat_id=%s (not in ALLOWED_CHAT_IDS)",
                    message.chat_id,
                )
            return

        is_edit = update.edited_message is not None
        if is_edit and self._already_handled(message.chat_id, message.message_id, body):
            if LOG_LINK_ACTIVITY:
                logger.info(
                    "Skip duplicate chat_id=%s msg_id=%s (edited/preview attach)",
                    message.chat_id,
                    message.message_id,
                )
            return

        tiktok_links: List[str] = []
        if self.downloader:
            raw_tt_links = extract_tiktok_urls(body)
            seen_tt_keys: set[str] = set()
            for link in raw_tt_links:
                if not self.downloader.is_valid_tiktok_url(link):
                    continue
                key = link
                if len(raw_tt_links) > 1:
                    try:
                        key = await asyncio.to_thread(self.downloader.content_key, link)
                    except Exception:
                        key = link
                if key in seen_tt_keys:
                    continue
                seen_tt_keys.add(key)
                tiktok_links.append(link)

        ig_urls = extract_instagram_urls(body)
        has_story_link = any(is_instagram_story(u) for u in ig_urls)
        reel_urls = [
            u
            for u in ig_urls
            if is_instagram_reel(u) and not is_instagram_story(u)
        ]
        mirror_ig_urls = bool(ig_urls) and (
            bool([u for u in ig_urls if u not in reel_urls])
            or (bool(reel_urls) and not self.ig_reels)
        )
        will_handle = bool(ig_urls) or bool(tiktok_links)

        thread_id = getattr(message, "message_thread_id", None)
        replied = False

        if self.ig_reels and reel_urls:
            for link in reel_urls:
                if LOG_LINK_ACTIVITY:
                    logger.info(
                        "Instagram reel download start chat_id=%s %s…",
                        message.chat_id,
                        link[:48],
                    )
                await self._process_instagram_reel(context, message, link, body)
            replied = True

        mirror_text, mirrored = "", False
        if mirror_ig_urls:
            if has_story_link:
                mirror_text, mirrored = await asyncio.to_thread(
                    fast_mirror_instagram_text, body, self._mirror_hosts
                )
            else:
                mirror_text, mirrored = await self._mirror_instagram_body(body)
                if ig_urls and not mirrored:
                    mirror_text, mirrored = await asyncio.to_thread(
                        fast_mirror_instagram_text, body, self._mirror_hosts
                    )

        if mirrored:
            if LOG_LINK_ACTIVITY:
                logger.info(
                    "Handled Instagram mirror chat_id=%s topic=%s",
                    message.chat_id,
                    thread_id,
                )
            try:
                reply_text = mirror_text
                if has_story_link:
                    reply_text += (
                        "\n\nℹ️ Instagram Stories usually can't show a preview in Telegram "
                        "(they expire after ~24h). Open the mirrored link in the Instagram app "
                        "if the preview is empty."
                    )
                await message.reply_text(
                    reply_text,
                    disable_web_page_preview=False,
                    message_thread_id=thread_id,
                )
                replied = True
            except TelegramError as exc:
                logger.error(
                    "Instagram mirror reply failed chat_id=%s msg_id=%s: %s",
                    message.chat_id,
                    message.message_id,
                    exc,
                )
        elif mirror_ig_urls and ig_urls:
            logger.warning(
                "Instagram link(s) in chat_id=%s: could not mirror",
                message.chat_id,
            )
            try:
                hint = (
                    "Story share links often don't work with preview mirrors — open them in the Instagram app."
                    if has_story_link
                    else "Try again in a minute or paste a direct reel/post URL."
                )
                await message.reply_text(
                    "⚠️ Could not mirror this Instagram link (no preview mirror responded). "
                    f"{hint}",
                    message_thread_id=thread_id,
                )
                replied = True
            except TelegramError as exc:
                logger.error("Mirror failure notice not sent: %s", exc)

        if self.downloader:
            for link in tiktok_links:
                if LOG_LINK_ACTIVITY:
                    logger.info(
                        "TikTok download start chat_id=%s host=%s…",
                        message.chat_id,
                        link[:48],
                    )
                await self._process_tiktok(context, message, link)
                replied = True

        if replied or will_handle:
            self._remember_handled_body(message.chat_id, message.message_id, body)

    async def _process_instagram_reel(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        message,
        link: str,
        body: str,
    ) -> None:
        chat_id = message.chat_id
        thread_id = getattr(message, "message_thread_id", None)
        status = await message.reply_text(
            f"⏳ Downloading Instagram reel…\n<code>{html.escape(link)}</code>",
            parse_mode="HTML",
            message_thread_id=thread_id,
        )
        try:
            ok, detail, media_files = await asyncio.to_thread(
                self.ig_reels.download_reel, link
            )
        except Exception as exc:
            logger.exception("Instagram reel download crashed: %s", exc)
            ok, detail, media_files = False, "❌ Reel download failed unexpectedly.", []

        if not ok or not media_files:
            mirror_text, mirrored = await asyncio.to_thread(
                fast_mirror_instagram_text, body, self._mirror_hosts
            )
            note = str(detail)
            if mirrored:
                note = f"{mirror_text}\n\n⚠️ Reel download failed — mirror link only (preview may not show):\n{detail}"
            await self._safe_edit_message(
                context, chat_id, status.message_id, thread_id, note[:3900]
            )
            return

        await self._safe_edit_message(
            context, chat_id, status.message_id, thread_id, "✅ Sending reel…"
        )
        media = media_files[0]
        path = media["file_path"]
        try:
            raw_cap = media.get("title") or ""
            cap = html.escape(raw_cap.strip())[:1020] if raw_cap.strip() else ""
            video_kw = dict(
                chat_id=chat_id,
                filename=os.path.basename(path),
                message_thread_id=thread_id,
                supports_streaming=True,
                write_timeout=TELEGRAM_MEDIA_WRITE_TIMEOUT,
                read_timeout=TELEGRAM_MEDIA_WRITE_TIMEOUT,
            )
            w, h = media.get("width"), media.get("height")
            if w and h:
                video_kw["width"] = int(w)
                video_kw["height"] = int(h)
            dur = media.get("duration")
            if dur:
                video_kw["duration"] = int(dur)
            if cap:
                video_kw["caption"] = cap[:1024]
                video_kw["parse_mode"] = "HTML"
            # Upload a real multipart file, not a URL/path hint. Audio presence was
            # verified before this point and normalization requires an audio stream.
            with open(path, "rb") as video_file:
                video_kw["video"] = video_file
                sent = await context.bot.send_video(**video_kw)
            logger.info(
                "Instagram reel sent file_id=%s size=%s duration=%s",
                getattr(getattr(sent, "video", None), "file_id", None),
                getattr(getattr(sent, "video", None), "file_size", None),
                getattr(getattr(sent, "video", None), "duration", None),
            )
        finally:
            await asyncio.to_thread(self.ig_reels.cleanup_files, media_files)
            try:
                await context.bot.delete_message(
                    chat_id=chat_id,
                    message_id=status.message_id,
                    api_kwargs=_forum_topic_api_kwargs(thread_id),
                )
            except Exception:
                pass

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
            "✅ Sending…",
        )

        try:
            photos = [m for m in media_files if m.get("type") == "photo"]
            videos = [m for m in media_files if m.get("type") != "photo"]

            if photos:
                cap = ""
                if photos[0].get("title"):
                    cap = html.escape(str(photos[0]["title"]).strip())[:1020]
                batch: List[InputMediaPhoto] = []
                opened: List[Any] = []
                for i, media in enumerate(photos[:10]):
                    fh = open(media["file_path"], "rb")
                    opened.append(fh)
                    media_kw: Dict[str, Any] = {"media": fh}
                    if i == 0 and cap:
                        media_kw["caption"] = cap[:1024]
                        media_kw["parse_mode"] = "HTML"
                    batch.append(InputMediaPhoto(**media_kw))
                try:
                    await context.bot.send_media_group(
                        chat_id=chat_id,
                        media=batch,
                        message_thread_id=thread_id,
                    )
                finally:
                    for fh in opened:
                        fh.close()
                for media in photos[10:]:
                    await context.bot.send_photo(
                        chat_id=chat_id,
                        photo=media["file_path"],
                        message_thread_id=thread_id,
                    )

            for media in videos:
                path = media["file_path"]
                raw_cap = media.get("title") or ""
                cap = html.escape(raw_cap.strip())[:1020] if raw_cap.strip() else ""
                vid_kw = dict(
                    chat_id=chat_id,
                    video=path,
                    message_thread_id=thread_id,
                    supports_streaming=True,
                    write_timeout=TELEGRAM_MEDIA_WRITE_TIMEOUT,
                    read_timeout=TELEGRAM_MEDIA_WRITE_TIMEOUT,
                )
                w, h = media.get("width"), media.get("height")
                if w and h:
                    vid_kw["width"] = int(w)
                    vid_kw["height"] = int(h)
                dur = media.get("duration")
                if dur:
                    vid_kw["duration"] = int(dur)
                if cap:
                    vid_kw["caption"] = cap[:1024]
                    vid_kw["parse_mode"] = "HTML"
                sent = False
                for attempt in range(2):
                    try:
                        await context.bot.send_video(**vid_kw)
                        sent = True
                        break
                    except TelegramError as send_err:
                        err_s = str(send_err).lower()
                        is_slow = isinstance(send_err, TimedOut) or "504" in err_s or "gateway timeout" in err_s
                        if attempt == 0 and is_slow and self.downloader:
                            smaller = await asyncio.to_thread(
                                compress_for_telegram_upload, path
                            )
                            if smaller != path:
                                path = smaller
                                vid_kw["video"] = path
                                await asyncio.sleep(3)
                                continue
                        logger.warning(
                            "send_video failed (%s); retrying as document", send_err
                        )
                        break
                if not sent:
                    doc_kw = dict(
                        chat_id=chat_id,
                        document=path,
                        filename=os.path.basename(path),
                        message_thread_id=thread_id,
                        write_timeout=TELEGRAM_MEDIA_WRITE_TIMEOUT,
                        read_timeout=TELEGRAM_MEDIA_WRITE_TIMEOUT,
                    )
                    if cap:
                        doc_kw["caption"] = cap[:1024]
                        doc_kw["parse_mode"] = "HTML"
                    await context.bot.send_document(**doc_kw)
                await asyncio.sleep(0.4)
        except TimedOut:
            logger.exception("Sending TikTok media timed out")
            await context.bot.send_message(
                chat_id=chat_id,
                text="❌ Upload timed out — video may be too large or the connection was slow. Try again.",
                message_thread_id=thread_id,
            )
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
        if isinstance(err, (TimedOut, NetworkError)):
            logger.warning("Transient Telegram network error: %s", err)
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
            except KeyboardInterrupt:
                logger.info("Bot stopped by user")
                return
            except (TimedOut, NetworkError) as e:
                logger.warning(
                    "Telegram API unreachable (%s); retry in 10 seconds…",
                    e,
                )
                time.sleep(10)
                self._build_application()
                continue
            except Exception as e:
                logger.error("Polling stopped: %s", e, exc_info=True)

            if not RESTART_ON_STOP:
                return

            logger.warning("Rebuilding application; restarting in 5 seconds...")
            time.sleep(5)
            self._build_application()


def main() -> None:
    SocialLinksBot().run()


if __name__ == "__main__":
    main()
