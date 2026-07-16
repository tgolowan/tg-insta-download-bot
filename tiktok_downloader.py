import json
import logging
import os
import re
import subprocess
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import yt_dlp

from config import DOWNLOAD_PATH, MAX_FILE_SIZE, ERROR_MESSAGES

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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


def normalize_for_telegram(src: str) -> str:
    """
    Remux to h264/aac with square pixels — mobile Telegram mis-renders some TikTok HEVC files.
    Returns path to use (original if normalize skipped or failed).
    """
    base, _ = os.path.splitext(src)
    dst = f"{base}_tg.mp4"
    try:
        proc = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                src,
                "-map",
                "0:v:0",
                "-map",
                "0:a?",
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
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-movflags",
                "+faststart",
                dst,
            ],
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
        
        # TikTok ladders: forcing h264+mp4 often yields ~30 FPS AVC while TikTok publishes
        # smoother video on bytevc/hevc (~60 FPS). Prefer high FPS, then broader fallbacks.
        self.ydl_opts = {
            'format': (
                'bestvideo*[fps>=50]+bestaudio/'
                'bestvideo*+bestaudio/'
                'bestvideo+bestaudio/'
                'best'
            ),
            'format_sort': ['fps', 'res'],
            'merge_output_format': 'mp4',
            'outtmpl': os.path.join(DOWNLOAD_PATH, '%(id)s.%(ext)s'),
            'quiet': False,
            'no_warnings': False,
            'extract_flat': False,
            'noplaylist': True,
            # TikTok-specific options
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'referer': 'https://www.tiktok.com/',
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Referer': 'https://www.tiktok.com/',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-us,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
            },
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
    
    def download_video(self, url: str) -> Tuple[bool, str, List[Dict]]:
        """
        Download TikTok video and return media file info.
        
        Returns:
            Tuple of (success, message, media_files)
        """
        try:
            if not self.is_valid_tiktok_url(url):
                return False, ERROR_MESSAGES['invalid_link'], []
            
            # First, get video info to determine aspect ratio
            try:
                with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
            except yt_dlp.utils.DownloadError as e:
                error_msg = str(e)
                logger.error(f"Info extraction error: {error_msg}")
                
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

            # Download (same yt-dlp options as probe — no narrower h264 override).
            # Telegram may refuse some codecs as video messages; bot falls back to document.
            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                try:
                    ydl.download([url])
                    
                    # Find the downloaded file
                    video_id = info.get('id') or self.extract_video_id(url) or 'tiktok_video'
                    video_ext = info.get('ext', 'mp4')
                    
                    # Try multiple possible file names
                    possible_files = [
                        os.path.join(DOWNLOAD_PATH, f"{video_id}.{video_ext}"),
                        os.path.join(DOWNLOAD_PATH, f"{video_id}.mp4"),
                        os.path.join(DOWNLOAD_PATH, f"{info.get('display_id', video_id)}.{video_ext}"),
                        os.path.join(DOWNLOAD_PATH, f"{info.get('display_id', video_id)}.mp4"),
                    ]
                    
                    downloaded_file = None
                    for file_path in possible_files:
                        if os.path.exists(file_path):
                            downloaded_file = file_path
                            break
                    
                    # If still not found, try to find any recently created file in download directory
                    if not downloaded_file:
                        try:
                            files = [f for f in os.listdir(DOWNLOAD_PATH) if os.path.isfile(os.path.join(DOWNLOAD_PATH, f))]
                            if files:
                                # Get the most recently created file
                                files.sort(key=lambda x: os.path.getmtime(os.path.join(DOWNLOAD_PATH, x)), reverse=True)
                                # Check if it was created recently (within last 60 seconds)
                                most_recent = os.path.join(DOWNLOAD_PATH, files[0])
                                if time.time() - os.path.getmtime(most_recent) < 60:
                                    downloaded_file = most_recent
                        except Exception as e:
                            logger.warning(f"Error finding downloaded file: {e}")
                    
                    if not downloaded_file or not os.path.exists(downloaded_file):
                        logger.error(f"Downloaded file not found. Expected: {possible_files[0]}")
                        return False, "❌ Downloaded file not found. The download may have failed.", []
                    
                    # Check actual file size
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
                        "TikTok send meta width=%s height=%s duration=%s",
                        media_files[0].get("width"),
                        media_files[0].get("height"),
                        media_files[0].get("duration"),
                    )
                    
                    return True, f"✅ Successfully downloaded TikTok video", media_files
                    
                except yt_dlp.utils.DownloadError as e:
                    error_msg = str(e)
                    logger.error(f"Download error: {error_msg}")
                    
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

