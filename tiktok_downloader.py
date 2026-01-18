import os
import re
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
        # Prefer vertical formats (height >= width) which is typical for TikTok
        # Format selector: prefer vertical videos, then best quality MP4
        self.ydl_opts = {
            'format': 'best[height>=width][ext=mp4]/best[ext=mp4]/best',
            'outtmpl': os.path.join(DOWNLOAD_PATH, '%(id)s.%(ext)s'),
            'quiet': False,
            'no_warnings': False,
            'extract_flat': False,
            'noplaylist': True,
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
                logger.error(f"Info extraction error: {e}")
                if "Private video" in str(e) or "This video is not available" in str(e):
                    return False, ERROR_MESSAGES['private_account'], []
                return False, ERROR_MESSAGES['download_failed'], []
            except Exception as e:
                logger.error(f"Error extracting video info: {e}")
                return False, ERROR_MESSAGES['download_failed'], []
            
            if not info:
                return False, ERROR_MESSAGES['download_failed'], []
            
            # Check file size
            filesize = info.get('filesize') or info.get('filesize_approx', 0)
            if filesize and filesize > MAX_FILE_SIZE:
                return False, ERROR_MESSAGES['file_too_large'], []
            
            # Check video dimensions and create appropriate format selector
            width = info.get('width', 0)
            height = info.get('height', 0)
            
            # Create format selector based on video aspect ratio
            # Prefer formats that match the original video's orientation
            if width > 0 and height > 0:
                if height > width:
                    # Vertical video - prefer vertical formats (typical TikTok format)
                    format_selector = 'best[height>=width][ext=mp4]/best[ext=mp4]/best'
                elif width > height:
                    # Horizontal video - prefer horizontal formats
                    format_selector = 'best[width>=height][ext=mp4]/best[ext=mp4]/best'
                else:
                    # Square video
                    format_selector = 'best[ext=mp4]/best'
            else:
                # Fallback to default format selector
                format_selector = 'best[height>=width][ext=mp4]/best[ext=mp4]/best'
            
            # Create download options with the appropriate format selector
            download_opts = self.ydl_opts.copy()
            download_opts['format'] = format_selector
            
            # Download the video with the correct format selector
            with yt_dlp.YoutubeDL(download_opts) as ydl:
                try:
                    ydl.download([url])
                    
                    # Find the downloaded file
                    video_id = info.get('id') or self.extract_video_id(url) or 'tiktok_video'
                    video_ext = info.get('ext', 'mp4')
                    
                    # Look for the downloaded file
                    downloaded_file = os.path.join(DOWNLOAD_PATH, f"{video_id}.{video_ext}")
                    
                    if not os.path.exists(downloaded_file):
                        # Try to find any recently created file in download directory
                        files = [f for f in os.listdir(DOWNLOAD_PATH) if os.path.isfile(os.path.join(DOWNLOAD_PATH, f))]
                        if files:
                            # Get the most recently created file
                            files.sort(key=lambda x: os.path.getmtime(os.path.join(DOWNLOAD_PATH, x)), reverse=True)
                            downloaded_file = os.path.join(DOWNLOAD_PATH, files[0])
                    
                    if not os.path.exists(downloaded_file):
                        return False, ERROR_MESSAGES['download_failed'], []
                    
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
                    logger.error(f"Download error: {e}")
                    if "Private video" in str(e) or "This video is not available" in str(e):
                        return False, ERROR_MESSAGES['private_account'], []
                    return False, ERROR_MESSAGES['download_failed'], []
                except Exception as e:
                    logger.error(f"Error downloading TikTok video: {e}")
                    return False, ERROR_MESSAGES['download_failed'], []
                    
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

