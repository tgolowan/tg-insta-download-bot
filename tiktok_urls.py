"""Extract TikTok share URLs from arbitrary chat text."""

from __future__ import annotations

import re
from typing import List, Optional
from urllib.parse import urlparse

TIKTOK_URL_RE = re.compile(
    r"https?://(?:www\.|vm\.|vt\.|m\.)?tiktok\.com/[^\s<>\[\]()]+",
    re.IGNORECASE,
)
_TRAILING = frozenset(".,);:!?\"]'\u00bb")
_PHOTO_ID_RE = re.compile(r"/photo/(\d+)")


def extract_tiktok_urls(text: str) -> List[str]:
    seen = set()
    out: List[str] = []
    for m in TIKTOK_URL_RE.finditer(text):
        u = m.group(0)
        while u and u[-1] in _TRAILING:
            u = u[:-1]
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def is_tiktok_photo_url(url: str) -> bool:
    return "/photo/" in urlparse(url).path.lower()


def extract_tiktok_photo_id(url: str) -> Optional[str]:
    m = _PHOTO_ID_RE.search(urlparse(url).path)
    return m.group(1) if m else None
