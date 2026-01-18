import os
import re
import time
import yt_dlp
import requests
from typing import List, Dict, Optional, Tuple
from urllib.parse import urlparse, parse_qs
import logging
from config import DOWNLOAD_PATH, MAX_FILE_SIZE, ERROR_MESSAGES

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TikTokDownloader:
    def __init__(self):
        """Initialize TikTok downloader."""
        # Create download directory
        os.makedirs(DOWNLOAD_PATH, exist_ok=True)
        
        # Configure yt-dlp options for TikTok
        # Format selector: prefer MP4, then best quality
        # Note: We'll filter by aspect ratio programmatically after getting formats
        self.ydl_opts = {
            'format': 'best[ext=mp4]/best',
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
            
            # Log aspect ratio for debugging
            if width > 0 and height > 0:
                aspect_ratio = height / width if width > 0 else 1
                orientation = "vertical" if height > width else "horizontal" if width > height else "square"
                logger.info(f"Video dimensions: {width}x{height} ({orientation}, ratio: {aspect_ratio:.2f})")
            
            # Use simple format selector - yt-dlp will download the video matching the original aspect ratio
            # Prefer MP4 format, fallback to best available
            download_opts = self.ydl_opts.copy()
            download_opts['format'] = 'best[ext=mp4]/best'
            
            # Download the video with the correct format selector
            with yt_dlp.YoutubeDL(download_opts) as ydl:
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
                    
                    media_files = [{
                        'type': 'video',
                        'file_path': downloaded_file,
                        'file_size': file_size,
                        'mime_type': 'video/mp4',
                        'title': info.get('title', 'TikTok Video'),
                        'duration': info.get('duration', 0)
                    }]
                    
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

