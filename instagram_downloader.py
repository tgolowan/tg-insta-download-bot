import os
import re
import instaloader
import requests
from typing import List, Dict, Optional, Tuple
from urllib.parse import urlparse
import logging
from config import INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD, DOWNLOAD_PATH, MAX_FILE_SIZE, ERROR_MESSAGES

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class InstagramDownloader:
    def __init__(self):
        """Initialize Instagram downloader with session."""
        self.loader = instaloader.Instaloader(
            download_pictures=False,
            download_videos=False,
            download_video_thumbnails=False,
            download_geotags=False,
            download_comments=False,
            save_metadata=False,
            compress_json=False
        )
        
        # Create download directory
        os.makedirs(DOWNLOAD_PATH, exist_ok=True)
        
        # Login if credentials are provided
        if INSTAGRAM_USERNAME and INSTAGRAM_PASSWORD:
            try:
                self.loader.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
                logger.info("Successfully logged into Instagram")
            except Exception as e:
                logger.warning(f"Failed to login to Instagram: {e}")
    
    def is_valid_instagram_url(self, url: str) -> bool:
        """Check if the URL is a valid Instagram post URL."""
        if not url:
            return False
        
        # Parse URL
        parsed = urlparse(url)
        if parsed.netloc not in ['www.instagram.com', 'instagram.com']:
            return False
        
        # Check if it's a post URL (contains /p/ or /reel/)
        path = parsed.path
        return '/p/' in path or '/reel/' in path
    
    def extract_shortcode(self, url: str) -> Optional[str]:
        """Extract shortcode from Instagram URL."""
        if not self.is_valid_instagram_url(url):
            return None
        
        # Extract shortcode from /p/SHORTCODE/ or /reel/SHORTCODE/
        match = re.search(r'/(?:p|reel)/([^/]+)', url)
        return match.group(1) if match else None
    
    def download_post(self, url: str) -> Tuple[bool, str, List[Dict]]:
        """
        Download Instagram post and return media files info.
        
        Returns:
            Tuple of (success, message, media_files)
        """
        try:
            if not self.is_valid_instagram_url(url):
                return False, ERROR_MESSAGES['invalid_link'], []
            
            shortcode = self.extract_shortcode(url)
            if not shortcode:
                return False, ERROR_MESSAGES['invalid_link'], []
            
            # Get post
            post = instaloader.Post.from_shortcode(self.loader.context, shortcode)
            
            media_files = []
            
            # Handle different post types
            if post.is_video:
                # Single video
                video_info = self._download_video(post, shortcode)
                if video_info:
                    media_files.append(video_info)
            elif post.typename == 'GraphSidecar':
                # Carousel post
                for i, node in enumerate(post.get_sidecar_nodes()):
                    if node.is_video:
                        media_info = self._download_video(node, f"{shortcode}_{i}")
                    else:
                        media_info = self._download_image(node, f"{shortcode}_{i}")
                    
                    if media_info:
                        media_files.append(media_info)
            else:
                # Single image
                image_info = self._download_image(post, shortcode)
                if image_info:
                    media_files.append(image_info)
            
            if not media_files:
                return False, ERROR_MESSAGES['download_failed'], []
            
            return True, f"✅ Successfully downloaded {len(media_files)} media file(s)", media_files
            
        except instaloader.exceptions.PrivateProfileNotFollowedException:
            return False, ERROR_MESSAGES['private_account'], []
        except instaloader.exceptions.QueryBadStatusException:
            return False, ERROR_MESSAGES['rate_limited'], []
        except Exception as e:
            logger.error(f"Error downloading post: {e}")
            return False, ERROR_MESSAGES['download_failed'], []
    
    def _download_image(self, node, filename: str) -> Optional[Dict]:
        """Download image from Instagram node."""
        try:
            # Get the highest quality image URL
            image_url = node.display_url
            
            # Download image
            response = requests.get(image_url, stream=True)
            response.raise_for_status()
            
            # Check file size
            content_length = int(response.headers.get('content-length', 0))
            if content_length > MAX_FILE_SIZE:
                logger.warning(f"Image {filename} is too large: {content_length} bytes")
                return None
            
            # Save image
            file_path = os.path.join(DOWNLOAD_PATH, f"{filename}.jpg")
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            return {
                'type': 'image',
                'file_path': file_path,
                'file_size': os.path.getsize(file_path),
                'mime_type': 'image/jpeg'
            }
            
        except Exception as e:
            logger.error(f"Error downloading image {filename}: {e}")
            return None
    
    def _download_video(self, node, filename: str) -> Optional[Dict]:
        """Download video from Instagram node."""
        try:
            # Get video URL
            video_url = node.video_url
            
            # Download video
            response = requests.get(video_url, stream=True)
            response.raise_for_status()
            
            # Check file size
            content_length = int(response.headers.get('content-length', 0))
            if content_length > MAX_FILE_SIZE:
                logger.warning(f"Video {filename} is too large: {content_length} bytes")
                return None
            
            # Save video
            file_path = os.path.join(DOWNLOAD_PATH, f"{filename}.mp4")
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            return {
                'type': 'video',
                'file_path': file_path,
                'file_size': os.path.getsize(file_path),
                'mime_type': 'video/mp4'
            }
            
        except Exception as e:
            logger.error(f"Error downloading video {filename}: {e}")
            return None
    
    def cleanup_files(self, media_files: List[Dict]):
        """Clean up downloaded files after sending."""
        for media in media_files:
            try:
                if os.path.exists(media['file_path']):
                    os.remove(media['file_path'])
                    logger.info(f"Cleaned up {media['file_path']}")
            except Exception as e:
                logger.error(f"Error cleaning up {media['file_path']}: {e}")
