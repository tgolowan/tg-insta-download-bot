"""Extract TikTok share URLs from arbitrary chat text."""

from __future__ import annotations

import re
from typing import List

TIKTOK_URL_RE = re.compile(
    r"https?://(?:www\.|vm\.|vt\.|m\.)?tiktok\.com/[^\s<>\[\]()]+",
    re.IGNORECASE,
)
_TRAILING = frozenset(".,);:!?\"]'\u00bb")


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
