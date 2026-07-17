"""Probe mirror URLs for Open Graph tags Telegram can unfurl."""

from __future__ import annotations

import logging
import re
from typing import List, Optional, Sequence, Tuple

import httpx

from link_mirror import instagram_url_to_mirror

logger = logging.getLogger(__name__)

# TelegramBot UA — some mirrors behave differently per client.
_FETCH_HEADERS = {
    "User-Agent": "TelegramBot (like TwitterBot)",
    "Accept": "text/html,application/xhtml+xml",
}

_OG_RE = re.compile(
    r'<meta[^>]+(?:property|name)=["\'](?:og:(?:image|video|title)|twitter:(?:card|image))["\']',
    re.IGNORECASE,
)


def page_likely_has_preview(html: str) -> bool:
    if not html:
        return False
    return bool(_OG_RE.search(html[:80_000]))


def fetch_preview_ok(url: str, timeout: float = 12.0) -> bool:
    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=timeout,
            headers=_FETCH_HEADERS,
        ) as client:
            resp = client.get(url)
        if resp.status_code >= 400:
            logger.info("Preview probe %s -> HTTP %s", url, resp.status_code)
            return False
        ok = page_likely_has_preview(resp.text)
        if not ok:
            logger.info("Preview probe %s -> no OG tags", url)
        return ok
    except Exception as exc:
        logger.warning("Preview probe failed for %s: %s", url, exc)
        return False


def pick_working_mirror(
    instagram_url: str,
    mirror_hosts: Sequence[str],
) -> Optional[Tuple[str, str]]:
    """Return (mirrored_url, host_used) for the first host that passes preview probe."""
    for host in mirror_hosts:
        host = host.strip()
        if not host:
            continue
        mirrored = instagram_url_to_mirror(instagram_url, host)
        if fetch_preview_ok(mirrored):
            return mirrored, host
    return None


def mirror_host_chain(primary: str, fallbacks: Sequence[str]) -> List[str]:
    seen = set()
    chain: List[str] = []
    for h in [primary, *fallbacks]:
        n = h.strip().lower().removeprefix("www.")
        if not n or n in seen:
            continue
        seen.add(n)
        chain.append(n)
    return chain
