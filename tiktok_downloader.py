import json
import logging
import os
import re
import subprocess
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import httpx
import yt_dlp

from config import DOWNLOAD_PATH, MAX_FILE_SIZE, ERROR_MESSAGES
from tiktok_urls import extract_tiktok_photo_id, is_tiktok_photo_url

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_TIKTOK_HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.tiktok.com/",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-us,en;q=0.5",
}
_PHOTOMODE_IMAGE_RE = re.compile(
    r"https://p\d+-common-sign\.tiktokcdn[^\"'\s<>]+photomode-image\.jpeg[^\"'\s<>]*",
    re.IGNORECASE,
)


def probe_video_file(path: str) -> Dict[str, Any]:
    """
    Read width/height/duration from the file (ffprobe).
    Applies rotation so Telegram gets display dimensions (fixes mobile stretch).
    """
    meta: Dict[str, Any] = {"width": None, "height": None, "duration": None}
    try:
        proc = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height,duration,rotation,display_aspect_ratio,sample_aspect_ratio",
                "-of",
                "json",
                path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode != 0:
            return meta
        data = json.loads(proc.stdout or "{}")
        streams = data.get("streams") or []
        if not streams:
            return meta
        st = streams[0]
        w, h = st.get("width"), st.get("height")
        rot = st.get("rotation")
        if rot is not None:
            try:
                rot = int(rot)
            except (TypeError, ValueError):
                rot = 0
        else:
            rot = 0
        if w and h and rot in (90, 270, -90, -270):
            w, h = h, w
        meta["width"] = int(w) if w else None
        meta["height"] = int(h) if h else None
        dur = st.get("duration")
        if dur is not None:
            try:
                meta["duration"] = max(1, int(float(dur)))
            except (TypeError, ValueError):
                pass
    except Exception as exc:
        logger.warning("ffprobe failed for %s: %s", path, exc)
    return meta


def probe_has_audio(path: str) -> bool:
    try:
        proc = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "a",
                "-show_entries",
                "stream=codec_type",
                "-of",
                "csv=p=0",
                path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return proc.returncode == 0 and bool((proc.stdout or "").strip())
    except Exception as exc:
        logger.warning("ffprobe audio check failed for %s: %s", path, exc)
        return False


def normalize_for_telegram(src: str) -> str:
    """
    Remux to h264/aac with square pixels — mobile Telegram mis-renders some TikTok HEVC files.
    Returns path to use (original if normalize skipped or failed).
    """
    base, _ = os.path.splitext(src)
    dst = f"{base}_tg.mp4"
    has_audio = probe_has_audio(src)
    try:
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            src,
            "-map",
            "0:v:0",
        ]
        if has_audio:
            cmd += [
                "-map",
                "0:a:0",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-ar",
                "44100",
                "-shortest",
            ]
        else:
            logger.warning("normalize_for_telegram: no audio stream in %s", src)
        cmd += [
            "-vf",
            "setsar=1",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            dst,
        ]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if proc.returncode != 0 or not os.path.isfile(dst):
            logger.warning("ffmpeg normalize failed: %s", (proc.stderr or "")[-400:])
            return src
        if os.path.getsize(dst) > MAX_FILE_SIZE:
            os.remove(dst)
            return src
        os.remove(src)
        return dst
    except Exception as exc:
        logger.warning("ffmpeg normalize error: %s", exc)
        if os.path.isfile(dst):
            try:
                os.remove(dst)
            except OSError:
                pass
        return src


class TikTokDownloader:
    def __init__(self):
        """Initialize TikTok downloader."""
        # Create download directory
        os.makedirs(DOWNLOAD_PATH, exist_ok=True)
        
        # TikTok bytevc/hevc ladders are often video-only in the MP4; h264 muxes include audio.
        self.ydl_opts = {
            'format': (
                'best[vcodec^=avc][acodec!=none][ext=mp4]/'
                'best[vcodec=h264][acodec!=none]/'
                'download/best[acodec!=none]/b'
            ),
            'merge_output_format': 'mp4',
            'postprocessors': [
                {'key': 'FFmpegVideoRemuxer', 'preferedformat': 'mp4'},
            ],
            'outtmpl': os.path.join(DOWNLOAD_PATH, '%(id)s.%(ext)s'),
            'quiet': False,
            'no_warnings': False,
            'extract_flat': False,
            'noplaylist': True,
            'user_agent': _TIKTOK_HTTP_HEADERS["User-Agent"],
            'referer': 'https://www.tiktok.com/',
            'http_headers': dict(_TIKTOK_HTTP_HEADERS),
            # Retry options
            'retries': 3,
            'fragment_retries': 3,
            'ignoreerrors': False,
        }
    
    def is_valid_tiktok_url(self, url: str) -> bool:
        """Check if the URL is a valid TikTok URL."""
        if not url:
            return False
        
        # Parse URL
        parsed = urlparse(url)
        
        # Check TikTok domains
        tiktok_domains = [
            'www.tiktok.com',
            'tiktok.com',
            'vm.tiktok.com',
            'vt.tiktok.com',
            'm.tiktok.com'
        ]
        
        if parsed.netloc not in tiktok_domains:
            return False
        
        # Check if it's a video URL
        path = parsed.path
        return '/video/' in path or '/@' in path or bool(re.search(r'/[a-zA-Z0-9]+', path))
    
    def extract_video_id(self, url: str) -> Optional[str]:
        """Extract video ID from TikTok URL."""
        if not self.is_valid_tiktok_url(url):
            return None
        
        # Try to extract from /video/ID format
        match = re.search(r'/video/(\d+)', url)
        if match:
            return match.group(1)
        
        # Try to extract from short URLs
        match = re.search(r'/([a-zA-Z0-9]+)/?$', url)
        if match:
            return match.group(1)
        
        return None

    def _resolve_url(self, url: str) -> str:
        try:
            with httpx.Client(
                follow_redirects=True,
                timeout=20.0,
                headers=_TIKTOK_HTTP_HEADERS,
            ) as client:
                resp = client.get(url)
            return str(resp.url)
        except Exception as exc:
            logger.warning("TikTok URL resolve failed for %s: %s", url, exc)
            return url

    def content_key(self, url: str) -> str:
        """Stable id for deduping vm.tiktok + full tiktok.com links to the same post."""
        resolved = self._resolve_url(url)
        path = urlparse(resolved).path
        for pattern in (r"/video/(\d+)", r"/photo/(\d+)"):
            m = re.search(pattern, path)
            if m:
                return f"tiktok:{m.group(1)}"
        return resolved.split("?", 1)[0].rstrip("/")

    def _photo_urls_from_embed(self, item_id: str) -> List[str]:
        embed_url = f"https://www.tiktok.com/embed/v2/{item_id}"
        try:
            with httpx.Client(
                follow_redirects=True,
                timeout=20.0,
                headers=_TIKTOK_HTTP_HEADERS,
            ) as client:
                resp = client.get(embed_url)
            if resp.status_code >= 400:
                return []
            raw = _PHOTOMODE_IMAGE_RE.findall(resp.text)
        except Exception as exc:
            logger.warning("TikTok embed fetch failed for %s: %s", item_id, exc)
            return []

        seen: set[str] = set()
        out: List[str] = []
        for raw_url in raw:
            u = raw_url.replace("\\u0026", "&").replace("&amp;", "&")
            key_m = re.search(r"/tos-[^/]+/([^~?]+)", u)
            key = key_m.group(1) if key_m else u
            if key in seen:
                continue
            seen.add(key)
            out.append(u)
        return out

    def _photo_post_title(self, resolved_url: str) -> str:
        video_url = re.sub(r"/photo/", "/video/", resolved_url, count=1)
        try:
            with yt_dlp.YoutubeDL(
                {**self.ydl_opts, "quiet": True, "no_warnings": True}
            ) as ydl:
                info = ydl.extract_info(video_url, download=False)
            if info:
                return (info.get("title") or info.get("description") or "").strip()
        except Exception as exc:
            logger.warning("TikTok photo title probe failed: %s", exc)
        return "TikTok Photo"

    def _download_photo_post(
        self, url: str, resolved_url: str
    ) -> Tuple[bool, str, List[Dict]]:
        item_id = extract_tiktok_photo_id(resolved_url)
        if not item_id:
            return False, ERROR_MESSAGES["unsupported_type"], []

        image_urls = self._photo_urls_from_embed(item_id)
        if not image_urls:
            return False, (
                "❌ Could not load TikTok photo carousel. "
                "The post may be private or unavailable."
            ), []

        title = self._photo_post_title(resolved_url)
        media_files: List[Dict] = []

        try:
            with httpx.Client(
                follow_redirects=True,
                timeout=30.0,
                headers=_TIKTOK_HTTP_HEADERS,
            ) as client:
                for idx, image_url in enumerate(image_urls):
                    resp = client.get(image_url)
                    if resp.status_code >= 400:
                        logger.warning(
                            "TikTok photo %s image %s HTTP %s",
                            item_id,
                            idx,
                            resp.status_code,
                        )
                        continue
                    if len(resp.content) > MAX_FILE_SIZE:
                        return False, ERROR_MESSAGES["file_too_large"], []
                    ext = "jpg"
                    path = os.path.join(DOWNLOAD_PATH, f"{item_id}_{idx}.{ext}")
                    with open(path, "wb") as fh:
                        fh.write(resp.content)
                    media_files.append(
                        {
                            "type": "photo",
                            "file_path": path,
                            "file_size": len(resp.content),
                            "mime_type": resp.headers.get(
                                "content-type", "image/jpeg"
                            ),
                            "title": title,
                        }
                    )
        except Exception as exc:
            logger.error("TikTok photo download failed: %s", exc, exc_info=True)
            for media in media_files:
                try:
                    os.remove(media["file_path"])
                except OSError:
                    pass
            return False, f"❌ Error downloading TikTok photos: {exc}", []

        if not media_files:
            return False, ERROR_MESSAGES["unsupported_type"], []

        logger.info(
            "TikTok photo post %s: downloaded %s image(s)",
            item_id,
            len(media_files),
        )
        return True, "✅ Successfully downloaded TikTok photos", media_files

    def _find_downloaded_file(self, info: dict, url: str) -> Optional[str]:
        video_id = info.get('id') or self.extract_video_id(url) or 'tiktok_video'
        video_ext = info.get('ext', 'mp4')
        possible_files = [
            os.path.join(DOWNLOAD_PATH, f"{video_id}.{video_ext}"),
            os.path.join(DOWNLOAD_PATH, f"{video_id}.mp4"),
            os.path.join(DOWNLOAD_PATH, f"{info.get('display_id', video_id)}.{video_ext}"),
            os.path.join(DOWNLOAD_PATH, f"{info.get('display_id', video_id)}.mp4"),
        ]
        for file_path in possible_files:
            if os.path.exists(file_path):
                return file_path
        try:
            files = [
                f
                for f in os.listdir(DOWNLOAD_PATH)
                if os.path.isfile(os.path.join(DOWNLOAD_PATH, f))
            ]
            if files:
                files.sort(
                    key=lambda x: os.path.getmtime(os.path.join(DOWNLOAD_PATH, x)),
                    reverse=True,
                )
                most_recent = os.path.join(DOWNLOAD_PATH, files[0])
                if time.time() - os.path.getmtime(most_recent) < 120:
                    return most_recent
        except Exception as e:
            logger.warning("Error finding downloaded file: %s", e)
        return None

    def _run_download(self, url: str, ydl_opts: dict) -> Optional[str]:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if not info:
                return None
            return self._find_downloaded_file(info, url)
    
    def download_video(self, url: str) -> Tuple[bool, str, List[Dict]]:
        """
        Download TikTok video and return media file info.
        
        Returns:
            Tuple of (success, message, media_files)
        """
        try:
            if not self.is_valid_tiktok_url(url):
                return False, ERROR_MESSAGES['invalid_link'], []

            resolved = self._resolve_url(url)
            if is_tiktok_photo_url(resolved):
                return self._download_photo_post(url, resolved)

            # First, get video info to determine aspect ratio
            try:
                with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
            except yt_dlp.utils.DownloadError as e:
                error_msg = str(e)
                logger.error(f"Info extraction error: {error_msg}")

                if "Unsupported URL" in error_msg and "/photo/" in error_msg:
                    resolved = self._resolve_url(url)
                    if is_tiktok_photo_url(resolved):
                        return self._download_photo_post(url, resolved)
                
                # Provide more specific error messages
                if "Private video" in error_msg or "This video is not available" in error_msg:
                    return False, ERROR_MESSAGES['private_account'], []
                elif "Sign in to confirm your age" in error_msg or "age-restricted" in error_msg.lower():
                    return False, ERROR_MESSAGES['private_account'], []
                elif "Video unavailable" in error_msg or "unavailable" in error_msg.lower():
                    return False, "❌ Video is unavailable. It may have been deleted or is not accessible.", []
                elif "HTTP Error 403" in error_msg or "403" in error_msg:
                    return False, "❌ Access forbidden. TikTok may be blocking requests. Please try again later.", []
                elif "HTTP Error 429" in error_msg or "429" in error_msg or "rate limit" in error_msg.lower():
                    return False, ERROR_MESSAGES['rate_limited'], []
                elif "HTTP Error" in error_msg:
                    return False, f"❌ Connection error: {error_msg[:100]}", []
                else:
                    # Return more detailed error for debugging
                    return False, f"❌ Download failed: {error_msg[:150]}", []
            except Exception as e:
                error_msg = str(e)
                logger.error(f"Error extracting video info: {error_msg}", exc_info=True)
                return False, f"❌ Error: {error_msg[:150]}", []
            
            if not info:
                return False, ERROR_MESSAGES['download_failed'], []
            
            # Check file size
            filesize = info.get('filesize') or info.get('filesize_approx', 0)
            if filesize and filesize > MAX_FILE_SIZE:
                return False, ERROR_MESSAGES['file_too_large'], []
            
            # Check video dimensions to verify aspect ratio
            # Note: We use a simple format selector since yt-dlp doesn't support
            # height>=width comparisons. The downloaded video will match the original aspect ratio.
            width = info.get('width', 0)
            height = info.get('height', 0)
            
            logger.info(
                "TikTok merged probe fps=%s vcodec=%s acodec=%s %sx%s",
                info.get("fps"),
                info.get("vcodec"),
                info.get("acodec"),
                info.get("width"),
                info.get("height"),
            )

            # Download (retry without video-only ladders if mux has no audio).
            downloaded_file = None
            try:
                downloaded_file = self._run_download(url, self.ydl_opts)
                if downloaded_file and not probe_has_audio(downloaded_file):
                    logger.warning(
                        "TikTok file has no audio (%s); retrying with muxed format",
                        downloaded_file,
                    )
                    try:
                        os.remove(downloaded_file)
                    except OSError:
                        pass
                    retry_opts = {
                        **self.ydl_opts,
                        'format': (
                            'best[vcodec^=avc][acodec!=none]/'
                            'download/best[acodec!=none]/b'
                        ),
                    }
                    downloaded_file = self._run_download(url, retry_opts)

                if not downloaded_file or not os.path.exists(downloaded_file):
                    logger.error("Downloaded file not found for %s", url)
                    return False, "❌ Downloaded file not found. The download may have failed.", []

                if not probe_has_audio(downloaded_file):
                    logger.error("TikTok download still has no audio track: %s", downloaded_file)
                    os.remove(downloaded_file)
                    return False, "❌ Downloaded video has no audio. Try again later.", []

                file_size = os.path.getsize(downloaded_file)
                if file_size > MAX_FILE_SIZE:
                    os.remove(downloaded_file)
                    return False, ERROR_MESSAGES['file_too_large'], []

                downloaded_file = normalize_for_telegram(downloaded_file)
                file_size = os.path.getsize(downloaded_file)
                if file_size > MAX_FILE_SIZE:
                    os.remove(downloaded_file)
                    return False, ERROR_MESSAGES['file_too_large'], []

                vmeta = probe_video_file(downloaded_file)
                media_files = [{
                    'type': 'video',
                    'file_path': downloaded_file,
                    'file_size': file_size,
                    'mime_type': 'video/mp4',
                    'title': info.get('title', 'TikTok Video'),
                    'duration': vmeta.get('duration') or info.get('duration', 0),
                    'width': vmeta.get('width') or info.get('width'),
                    'height': vmeta.get('height') or info.get('height'),
                }]
                logger.info(
                    "TikTok send meta width=%s height=%s duration=%s has_audio=%s",
                    media_files[0].get("width"),
                    media_files[0].get("height"),
                    media_files[0].get("duration"),
                    probe_has_audio(downloaded_file),
                )

                return True, "✅ Successfully downloaded TikTok video", media_files

            except yt_dlp.utils.DownloadError as e:
                error_msg = str(e)
                logger.error(f"Download error: {error_msg}")

                if "Private video" in error_msg or "This video is not available" in error_msg:
                    return False, ERROR_MESSAGES['private_account'], []
                elif "Sign in to confirm your age" in error_msg or "age-restricted" in error_msg.lower():
                    return False, ERROR_MESSAGES['private_account'], []
                elif "Video unavailable" in error_msg or "unavailable" in error_msg.lower():
                    return False, "❌ Video is unavailable. It may have been deleted or is not accessible.", []
                elif "HTTP Error 403" in error_msg or "403" in error_msg:
                    return False, "❌ Access forbidden. TikTok may be blocking requests. Please try again later.", []
                elif "HTTP Error 429" in error_msg or "429" in error_msg or "rate limit" in error_msg.lower():
                    return False, ERROR_MESSAGES['rate_limited'], []
                elif "HTTP Error" in error_msg:
                    return False, f"❌ Connection error: {error_msg[:100]}", []
                else:
                    return False, f"❌ Download failed: {error_msg[:150]}", []
            except Exception as e:
                error_msg = str(e)
                logger.error(f"Error downloading TikTok video: {error_msg}", exc_info=True)
                return False, f"❌ Error: {error_msg[:150]}", []
                    
        except Exception as e:
            logger.error(f"Error processing TikTok URL: {e}")
            return False, ERROR_MESSAGES['download_failed'], []
    
    def cleanup_files(self, media_files: List[Dict]):
        """Clean up downloaded files after sending."""
        for media in media_files:
            try:
                if os.path.exists(media['file_path']):
                    os.remove(media['file_path'])
                    logger.info(f"Cleaned up {media['file_path']}")
            except Exception as e:
                logger.error(f"Error cleaning up {media['file_path']}: {e}")

