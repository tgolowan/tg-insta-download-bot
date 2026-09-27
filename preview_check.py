"""Probe mirror URLs for Open Graph tags Telegram can unfurl."""

from __future__ import annotations

import logging
import re
from typing import List, Optional, Sequence, Tuple
from urllib.parse import urlparse

import httpx

from link_mirror import instagram_url_to_mirror

logger = logging.getLogger(__name__)

_FETCH_HEADERS = {
    "User-Agent": "TelegramBot (like TwitterBot)",
    "Accept": "text/html,application/xhtml+xml",
}

_OG_RE = re.compile(
    r'<meta[^>]+(?:property|name)=["\'](?:og:(?:image|video|title)|twitter:(?:card|image))["\']',
    re.IGNORECASE,
)

_PLACEHOLDER_MARKERS = (
    "instagram did not provide public media",
    "instagram7 fixed preview",
    "post not found",
    "oops, preview unavailable",
    "preview unavailable",
)

_FALLBACK_IMAGE_RE = re.compile(r"instagram7\.com/fallback/", re.IGNORECASE)
_OG_VIDEO_RE = re.compile(
    r'<meta[^>]+property=["\']og:video(?::secure_url)?["\'][^>]+content=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
_TWITTER_PLAYER_RE = re.compile(
    r'<meta[^>]+name=["\']twitter:card["\'][^>]+content=["\']player["\']',
    re.IGNORECASE,
)


def _is_instagram_origin(url: str) -> bool:
    host = urlparse(url).netloc.lower().removeprefix("www.")
    return host == "instagram.com" or host.endswith(".instagram.com")


def _is_instagram_cdn_image(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return any(
        part in host
        for part in ("cdninstagram.com", "fbcdn.net", "instagram.com")
    )


def page_likely_has_preview(html: str) -> bool:
    return preview_score(html) > 0


def _is_placeholder_preview(html: str) -> bool:
    if not html:
        return True
    sample = html[:120_000].lower()
    if any(marker in sample for marker in _PLACEHOLDER_MARKERS):
        return True
    return bool(_FALLBACK_IMAGE_RE.search(html[:120_000]))


_OG_IMAGE_RE = re.compile(
    r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
    re.IGNORECASE,
)


def is_photo_post(instagram_url: str) -> bool:
    path = urlparse(instagram_url).path.lower()
    return "/p/" in path


def is_instagram_reel(instagram_url: str) -> bool:
    path = urlparse(instagram_url).path.lower()
    return "/reel/" in path or "/reels/" in path


def is_instagram_story(instagram_url: str) -> bool:
    path = urlparse(instagram_url).path.lower()
    return "/stories/" in path


STORY_MIRROR_HOSTS = (
    "eeinstagram.com",
    "vxinstagram.com",
    "instagram7.com",
)

# InstaFix (zz → hh): reliable og:video for reels; ee/vx often fail on newer reels.
REEL_MIRROR_HOSTS = (
    "hhinstagram.com",
    "zzinstagram.com",
    "instagram7.com",
    "eeinstagram.com",
    "vxinstagram.com",
)


def _normalize_og_url(raw: str, page_url: str) -> str:
    u = raw.strip().replace("&amp;", "&")
    if u.startswith("//"):
        return "https:" + u
    if u.startswith("/"):
        from urllib.parse import urljoin

        return urljoin(page_url, u)
    return u


def _og_video_telegram_ready(
    raw_url: str, page_url: str, *, photo_post: bool = False
) -> bool:
    u = _normalize_og_url(raw_url, page_url).lower().split("?", 1)[0]
    if not u.startswith("http"):
        return False
    if any(u.endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif")):
        return False
    # vx/ee offload JPEGs on /p/ posts are mis-tagged as video.
    if photo_post and ("/offload/" in u or "/grid/" in u):
        return False
    return True


def _og_description_is_failure(html: str) -> bool:
    chunk = html[:80_000]
    m = re.search(
        r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']*)["\']',
        chunk,
        re.IGNORECASE,
    )
    if m:
        desc = m.group(1).strip().lower()
        if desc == "post not found" or desc.startswith("post not found"):
            return True
    title_m = re.search(
        r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']*)["\']',
        chunk,
        re.IGNORECASE,
    )
    if title_m:
        title = title_m.group(1).strip().lower()
        if "preview unavailable" in title or title == "oops, preview unavailable":
            return True
    return False


def preview_score(html: str, *, photo_post: bool = False, page_url: str = "") -> int:
    """
    Higher = better Telegram unfurl.
    Reels: absolute og:video. Photo posts (/p/): og:image (vx often mis-tags JPEG as og:video).
    """
    if not html or _is_placeholder_preview(html) or _og_description_is_failure(html):
        return 0
    chunk = html[:120_000]
    score = 0
    img_m = _OG_IMAGE_RE.search(chunk)
    vid_m = _OG_VIDEO_RE.search(chunk)
    base = page_url or ""

    if photo_post:
        if img_m:
            img_url = img_m.group(1)
            if _FALLBACK_IMAGE_RE.search(img_url):
                return 0
            score += 8
            if "instagram7.com/grid" in img_url.lower():
                score += 3
        # Ignore og:video on /p/ — mirrors often point to JPEGs, Telegram won't unfurl.
        if _TWITTER_PLAYER_RE.search(chunk) and score >= 8:
            score += 2
    else:
        if vid_m and base and _og_video_telegram_ready(
            vid_m.group(1), base, photo_post=False
        ):
            score += 10
            abs_vid = _normalize_og_url(vid_m.group(1), base)
            if abs_vid.lower().startswith("https://"):
                score += 2
        if _TWITTER_PLAYER_RE.search(chunk):
            score += 5
        if img_m:
            score += 3
    if re.search(
        r'<meta[^>]+property=["\']og:title["\']',
        chunk,
        re.IGNORECASE,
    ):
        score += 1
    if score == 0 and _OG_RE.search(chunk):
        score = 1
    return score


def _fetch_preview_html(
    url: str, timeout: float
) -> Tuple[Optional[str], Optional[str], int, Optional[str]]:
    """Return (body, final_url, http_status, content_type) or (None, None, 0, None)."""
    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=timeout,
            headers=_FETCH_HEADERS,
        ) as client:
            resp = client.get(url)
        return resp.text, str(resp.url), resp.status_code, resp.headers.get("content-type")
    except Exception as exc:
        logger.warning("Preview probe failed for %s: %s", url, exc)
        return None, None, 0, None


def fetch_preview_ok(url: str, timeout: float = 8.0) -> bool:
    return fetch_preview_score(url, timeout=timeout) > 0


def fetch_preview_score(
    url: str,
    timeout: float = 8.0,
    *,
    instagram_url: Optional[str] = None,
) -> int:
    html, final, status, content_type = _fetch_preview_html(url, timeout)
    if not final:
        return 0
    origin = instagram_url or url
    if is_instagram_story(origin) and "/stories/" not in urlparse(final).path.lower():
        return 0
    photo = is_photo_post(origin) or is_instagram_story(origin)
    ct = (content_type or "").lower()
    if photo and status < 400 and "image/" in ct and _is_instagram_cdn_image(final):
        logger.info(
            "Preview probe OK score=9 %s -> CDN image %s",
            url,
            urlparse(final).netloc,
        )
        return 9
    if not html:
        return 0
    if _is_instagram_origin(final):
        logger.info(
            "Preview probe %s -> redirect to instagram.com (no embed)",
            url,
        )
        return 0
    if status >= 400:
        logger.info("Preview probe %s -> HTTP %s", url, status)
        return 0
    photo = is_photo_post(instagram_url or url)
    score = preview_score(html, photo_post=photo, page_url=final)
    if score <= 0:
        logger.info("Preview probe %s -> placeholder or no usable OG (final %s)", url, final)
    else:
        logger.info(
            "Preview probe OK score=%s %s via %s",
            score,
            url,
            urlparse(final).netloc,
        )
    return score


def pick_working_mirror(
    instagram_url: str,
    mirror_hosts: Sequence[str],
    *,
    timeout: float = 8.0,
) -> Optional[Tuple[str, str]]:
    best: Optional[Tuple[str, str]] = None
    best_score = 0
    per_host = min(timeout, 6.0)
    photo = is_photo_post(instagram_url)
    hosts = _hosts_for_instagram_url(instagram_url, mirror_hosts)
    for host in hosts:
        host = host.strip()
        if not host:
            continue
        mirrored = instagram_url_to_mirror(instagram_url, host)
        score = fetch_preview_score(
            mirrored, timeout=per_host, instagram_url=instagram_url
        )
        if score > best_score:
            best_score = score
            best = (mirrored, host)
        if photo and score >= 10:
            break
        if not photo and score >= 10:
            break
    return best if best_score > 0 else None


PREFERRED_MIRROR_HOSTS = (
    "hhinstagram.com",
    "zzinstagram.com",
    "instagram7.com",
    "eeinstagram.com",
)
PHOTO_POST_MIRROR_HOSTS = (
    "vxinstagram.com",
    "kkclip.com",
    "eeinstagram.com",
    "instagram7.com",
)


def _hosts_for_instagram_url(
    instagram_url: str, mirror_hosts: Sequence[str]
) -> List[str]:
    """Stories: ee first. Photo /p/: vx + kkclip. Reels: instagram7 + ee."""
    if is_instagram_story(instagram_url):
        preferred = STORY_MIRROR_HOSTS
    elif is_photo_post(instagram_url):
        preferred = PHOTO_POST_MIRROR_HOSTS
    else:
        preferred = REEL_MIRROR_HOSTS
    normalized = []
    for h in mirror_hosts:
        n = h.strip().lower().removeprefix("www.")
        if n:
            normalized.append(n)
    ranked: List[str] = []
    for p in preferred:
        if p not in ranked:
            ranked.append(p)
    for n in normalized:
        if n not in ranked:
            ranked.append(n)
    return ranked


def mirror_host_chain(primary: str, fallbacks: Sequence[str]) -> List[str]:
    """eeinstagram first for reels; instagram7 strong for /p/ photo posts."""
    seen: set[str] = set()
    chain: List[str] = []

    def add(raw: str) -> None:
        n = raw.strip().lower().removeprefix("www.")
        if not n or n in seen:
            return
        seen.add(n)
        chain.append(n)

    for preferred in PREFERRED_MIRROR_HOSTS:
        add(preferred)
    add(primary)
    for h in fallbacks:
        add(h)
    return chain
