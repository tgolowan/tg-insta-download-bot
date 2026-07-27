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


def page_likely_has_preview(html: str) -> bool:
    return preview_score(html) > 0


def _is_placeholder_preview(html: str) -> bool:
    if not html:
        return True
    sample = html[:120_000].lower()
    if any(marker in sample for marker in _PLACEHOLDER_MARKERS):
        return True
    return bool(_FALLBACK_IMAGE_RE.search(html[:120_000]))


def preview_score(html: str) -> int:
    """
    Higher = better Telegram unfurl. Reels need og:video; instagram7 fallback PNGs score 0.
    """
    if not html or _is_placeholder_preview(html):
        return 0
    chunk = html[:120_000]
    score = 0
    if _OG_VIDEO_RE.search(chunk):
        score += 10
    if _TWITTER_PLAYER_RE.search(chunk):
        score += 5
    if re.search(
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
        chunk,
        re.IGNORECASE,
    ):
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


def _fetch_preview_html(url: str, timeout: float) -> Tuple[Optional[str], Optional[str], int]:
    """Return (html, final_url, http_status) or (None, None, 0) on failure."""
    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=timeout,
            headers=_FETCH_HEADERS,
        ) as client:
            resp = client.get(url)
        return resp.text, str(resp.url), resp.status_code
    except Exception as exc:
        logger.warning("Preview probe failed for %s: %s", url, exc)
        return None, None, 0


def fetch_preview_ok(url: str, timeout: float = 8.0) -> bool:
    return fetch_preview_score(url, timeout=timeout) > 0


def fetch_preview_score(url: str, timeout: float = 8.0) -> int:
    html, final, status = _fetch_preview_html(url, timeout)
    if not html or not final:
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
    score = preview_score(html)
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
    for host in mirror_hosts:
        host = host.strip()
        if not host:
            continue
        mirrored = instagram_url_to_mirror(instagram_url, host)
        score = fetch_preview_score(mirrored, timeout=per_host)
        if score > best_score:
            best_score = score
            best = (mirrored, host)
        if score >= 10:
            break
    return best if best_score > 0 else None


PREFERRED_MIRROR_HOSTS = ("eeinstagram.com", "instagram7.com")


def mirror_host_chain(primary: str, fallbacks: Sequence[str]) -> List[str]:
    """Build probe order; eeinstagram.com first (real og:video), then instagram7.com."""
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
