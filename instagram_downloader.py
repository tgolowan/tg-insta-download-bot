import os
import re
import time
import instaloader
import requests
from typing import List, Dict, Optional, Tuple
from urllib.parse import urlparse
import logging
from config import (
    INSTAGRAM_USERNAME,
    INSTAGRAM_PASSWORD,
    IG_LOGIN_ON_START,
    DOWNLOAD_PATH,
    MAX_FILE_SIZE,
    MIN_REQUEST_INTERVAL_SECONDS,
    RATE_LIMIT_COOLDOWN_SECONDS,
    ERROR_MESSAGES,
)

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class InstagramDownloader:
    def __init__(self):
        """Initialize Instagram downloader with session and rate-limit controls."""
        self.loader = instaloader.Instaloader(
            download_pictures=False,
            download_videos=False,
            download_video_thumbnails=False,
            download_geotags=False,
            download_comments=False,
            save_metadata=False,
            compress_json=False
        )
        # Track last request time and a cool-down until timestamp
        self._last_request_epoch: float = 0.0
        self._cooldown_until_epoch: float = 0.0
        
        # Create download directory
        os.makedirs(DOWNLOAD_PATH, exist_ok=True)
        
        # Optional login on start; default is disabled to avoid 429s
        if IG_LOGIN_ON_START and not IG_DISABLE_LOGIN and INSTAGRAM_USERNAME and INSTAGRAM_PASSWORD:
            self._login_if_needed(force=True)

    def _login_if_needed(self, force: bool = False) -> None:
        """Login only when necessary. Avoid eager login to reduce 429s."""
        try:
            if IG_DISABLE_LOGIN or not (INSTAGRAM_USERNAME and INSTAGRAM_PASSWORD):
                return
            # If already logged in and no force requested, skip
            if hasattr(self.loader.context, "is_logged_in") and self.loader.context.is_logged_in and not force:
                return
            self.loader.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
            logger.info("Logged in to Instagram session")
        except instaloader.exceptions.BadCredentialsException:
            logger.error("Invalid Instagram credentials. Please check username/password.")
        except instaloader.exceptions.TwoFactorAuthRequiredException:
            logger.error("Two-factor authentication required. Please disable 2FA or use app-specific password.")
        except instaloader.exceptions.ConnectionException as e:
            logger.warning(f"Connection error during login: {e}")
        except Exception as err:
            logger.warning(f"Login failed: {err}")

    def _respect_rate_limits(self) -> None:
        """Throttle requests and respect cool-downs after 429s."""
        now = time.time()
        if now < self._cooldown_until_epoch:
            sleep_for = max(0.0, self._cooldown_until_epoch - now)
            logger.warning(f"Rate-limit cooldown active. Sleeping for {sleep_for:.0f}s")
            time.sleep(sleep_for)
        # Enforce minimum interval between requests
        since_last = now - self._last_request_epoch
        if since_last < MIN_REQUEST_INTERVAL_SECONDS:
            time.sleep(MIN_REQUEST_INTERVAL_SECONDS - since_last)
        self._last_request_epoch = time.time()
    
    def _can_access_without_login(self) -> bool:
        """Check if we can access Instagram content without login."""
        # If login is disabled, we can't access without it
        if IG_DISABLE_LOGIN:
            return False
        
        # If we have credentials, we can try login
        if INSTAGRAM_USERNAME and INSTAGRAM_PASSWORD:
            return True
        
        # Otherwise, we can only access public content
        return True
    

    
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
            
            # Login lazily only when necessary (e.g., private posts)
            # Respect throttle before making the request
            self._respect_rate_limits()
            
            # Try to get post without login first
            post = None
            try:
                post = instaloader.Post.from_shortcode(self.loader.context, shortcode)
            except instaloader.exceptions.QueryReturnedNotFoundException:
                # Try logging in and retry once in case it is private but accessible
                if not IG_DISABLE_LOGIN:
                    self._login_if_needed(force=False)
                    self._respect_rate_limits()
                    try:
                        post = instaloader.Post.from_shortcode(self.loader.context, shortcode)
                    except Exception as login_e:
                        logger.warning(f"Failed to get post even with login: {login_e}")
                        return False, ERROR_MESSAGES['private_account'], []
                else:
                    return False, ERROR_MESSAGES['private_account'], []
            except instaloader.exceptions.QueryReturnedForbiddenException as e:
                # Handle 401/403 errors - might need login
                if "401" in str(e) and not IG_DISABLE_LOGIN:
                    logger.info("Received 401, attempting login...")
                    self._login_if_needed(force=False)
                    self._respect_rate_limits()
                    try:
                        post = instaloader.Post.from_shortcode(self.loader.context, shortcode)
                    except Exception as login_e:
                        logger.warning(f"Failed to get post even with login: {login_e}")
                        return False, ERROR_MESSAGES['private_account'], []
                else:
                    return False, ERROR_MESSAGES['forbidden'], []
            except instaloader.exceptions.ConnectionException as e:
                # Handle connection issues
                if "401" in str(e):
                    if IG_DISABLE_LOGIN:
                        return False, ERROR_MESSAGES['instagram_unavailable'], []
                    else:
                        logger.info("Received 401 connection error, attempting login...")
                        self._login_if_needed(force=False)
                        self._respect_rate_limits()
                        try:
                            post = instaloader.Post.from_shortcode(self.loader.context, shortcode)
                        except Exception as login_e:
                            logger.warning(f"Failed to get post even with login: {login_e}")
                            return False, ERROR_MESSAGES['instagram_unavailable'], []
                else:
                    logger.error(f"Connection error: {e}")
                    return False, ERROR_MESSAGES['connection_error'], []
            
            if post is None:
                return False, ERROR_MESSAGES['download_failed'], []
            
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
        except instaloader.exceptions.TooManyRequestsException as e:
            # Trigger cooldown on rate limit
            self._cooldown_until_epoch = time.time() + RATE_LIMIT_COOLDOWN_SECONDS
            logger.warning(
                f"Rate limited by Instagram. Entering cooldown for {RATE_LIMIT_COOLDOWN_SECONDS}s"
            )
            return False, ERROR_MESSAGES['rate_limited'], []
        except instaloader.exceptions.QueryReturnedForbiddenException as e:
            # Handle 401/403 errors - might need login
            if "401" in str(e) or "403" in str(e):
                logger.warning("Access forbidden. This might be a private post or require login.")
                return False, ERROR_MESSAGES['private_account'], []
            return False, ERROR_MESSAGES['download_failed'], []
        except instaloader.exceptions.QueryReturnedBadRequestException as e:
            # Handle other bad request errors
            logger.error(f"Bad request to Instagram: {e}")
            return False, ERROR_MESSAGES['download_failed'], []
        except instaloader.exceptions.ConnectionException as e:
            # Handle connection issues
            logger.error(f"Connection error: {e}")
            return False, ERROR_MESSAGES['connection_error'], []
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
