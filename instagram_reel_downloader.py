"""Download public Instagram reels with yt-dlp for native Telegram video playback."""

from __future__ import annotations

import logging
import os
import re
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

import httpx
import yt_dlp

from config import DOWNLOAD_PATH, MAX_FILE_SIZE, TIKTOK_YTDLP_SOCKET_TIMEOUT
from link_mirror import canonical_instagram_url
from preview_check import is_instagram_reel, is_instagram_story
from tiktok_downloader import prepare_for_telegram_upload, probe_video_file

logger = logging.getLogger(__name__)

_REEL_ID_RE = re.compile(r"/reel/([^/?#]+)", re.IGNORECASE)
_HH_FETCH_HEADERS = {
    "User-Agent": "TelegramBot (like TwitterBot)",
    "Accept": "video/mp4,*/*",
}


def _reel_shortcode(canonical_url: str) -> Optional[str]:
    m = _REEL_ID_RE.search(urlparse(canonical_url).path)
    return m.group(1) if m else None


def hh_proxy_video_url(canonical_url: str) -> Optional[str]:
    code = _reel_shortcode(canonical_url)
    if not code:
        return None
    return f"https://www.hhinstagram.com/proxy/video/{code}?type=reel"


class InstagramReelDownloader:
    def __init__(self) -> None:
        os.makedirs(DOWNLOAD_PATH, exist_ok=True)
        self._ydl_opts = {
            "format": "best[ext=mp4]/best",
            "outtmpl": os.path.join(DOWNLOAD_PATH, "ig_%(id)s.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "socket_timeout": TIKTOK_YTDLP_SOCKET_TIMEOUT,
            "noplaylist": True,
        }

    @staticmethod
    def is_reel_url(url: str) -> bool:
        u = canonical_instagram_url(url)
        return is_instagram_reel(u) and not is_instagram_story(u)

    def _pack_video_file(self, path: str, title: str = "") -> Tuple[bool, str, List[Dict]]:
        path = prepare_for_telegram_upload(path)
        size = os.path.getsize(path)
        if size > MAX_FILE_SIZE:
            os.remove(path)
            return False, "❌ Reel is too large to send via Telegram (max 50MB).", []
        meta = probe_video_file(path)
        return True, "✅ Reel downloaded", [
            {
                "type": "video",
                "file_path": path,
                "file_size": size,
                "mime_type": "video/mp4",
                "title": title[:200],
                "duration": meta.get("duration"),
                "width": meta.get("width"),
                "height": meta.get("height"),
            }
        ]

    def _download_via_hh_proxy(self, link: str) -> Tuple[bool, str, List[Dict]]:
        proxy = hh_proxy_video_url(link)
        if not proxy:
            return False, "❌ Invalid reel URL.", []
        code = _reel_shortcode(link) or "reel"
        dest = os.path.join(DOWNLOAD_PATH, f"ig_hh_{code}.mp4")
        try:
            with httpx.stream(
                "GET",
                proxy,
                headers=_HH_FETCH_HEADERS,
                follow_redirects=True,
                timeout=120.0,
            ) as resp:
                if resp.status_code >= 400:
                    return False, f"❌ Mirror video unavailable (HTTP {resp.status_code}).", []
                cl = resp.headers.get("content-length")
                if cl and int(cl) > MAX_FILE_SIZE:
                    return False, "❌ Reel is too large to send via Telegram (max 50MB).", []
                size = 0
                with open(dest, "wb") as fh:
                    for chunk in resp.iter_bytes():
                        size += len(chunk)
                        if size > MAX_FILE_SIZE:
                            fh.close()
                            os.remove(dest)
                            return False, "❌ Reel is too large to send via Telegram (max 50MB).", []
                        fh.write(chunk)
        except Exception as exc:
            logger.warning("hhinstagram proxy download failed: %s", exc)
            if os.path.isfile(dest):
                try:
                    os.remove(dest)
                except OSError:
                    pass
            return False, "❌ Could not fetch reel from preview mirror.", []
        if size < 1024:
            try:
                os.remove(dest)
            except OSError:
                pass
            return False, "❌ Mirror returned an empty video.", []
        return self._pack_video_file(dest)

    def _download_via_ytdlp(self, link: str) -> Tuple[bool, str, List[Dict]]:
        path = ""
        info: Optional[dict] = None
        try:
            with yt_dlp.YoutubeDL(self._ydl_opts) as ydl:
                info = ydl.extract_info(link, download=True)
                path = ydl.prepare_filename(info)
        except yt_dlp.utils.DownloadError as exc:
            logger.warning("Instagram yt-dlp failed: %s", exc)
            return False, str(exc)[:200], []
        if not path or not os.path.isfile(path):
            return False, "no file", []
        title = (info or {}).get("title") or (info or {}).get("description") or ""
        return self._pack_video_file(path, str(title))

    def download_reel(self, url: str) -> Tuple[bool, str, List[Dict]]:
        link = canonical_instagram_url(url)
        if not self.is_reel_url(link):
            return False, "❌ Not an Instagram reel link.", []

        ok, msg, files = self._download_via_ytdlp(link)
        if ok:
            return ok, msg, files
        ok, msg, files = self._download_via_hh_proxy(link)
        if ok:
            return ok, msg, files
        return (
            False,
            "❌ Could not download reel (Instagram blocked or reel unavailable).",
            [],
        )

    def cleanup_files(self, media_files: List[Dict]) -> None:
        for media in media_files:
            try:
                p = media.get("file_path")
                if p and os.path.isfile(p):
                    os.remove(p)
            except OSError as exc:
                logger.warning("IG reel cleanup failed: %s", exc)
