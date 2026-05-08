"""
Detect Instagram URLs in text and rewrite the host for a kkclip-style mirror preview.
"""

from __future__ import annotations

import re
from typing import List, Tuple
from urllib.parse import urlparse, urlunparse

# Match instagram.com URLs; trim trailing punctuation that often wraps pasted links.
_URL_RE = re.compile(
    r"https?://(?:[\w-]+\.)*instagram\.com(?:/[^\s\]\}\)<>\"']*)?",
    re.IGNORECASE,
)
_TRAILING = frozenset(".,);:!?\"]'\u00bb")


def normalize_mirror_host(raw: str) -> str:
    h = raw.strip().lower().rstrip("/")
    return h.replace("www.", "", 1) if h.startswith("www.") else h


def instagram_url_to_mirror(url: str, mirror_host: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        parsed = urlparse("https://" + url)
    netloc = parsed.netloc.lower()
    if not netloc.endswith("instagram.com"):
        return url
    base = normalize_mirror_host(mirror_host)
    new_netloc = f"www.{base}"
    return urlunparse(("https", new_netloc, parsed.path or "/", parsed.params, parsed.query, parsed.fragment))


def _strip_trailing_noise(s: str) -> Tuple[str, str]:
    rest = ""
    u = s
    while u and u[-1] in _TRAILING:
        rest = u[-1] + rest
        u = u[:-1]
    return u, rest


def extract_instagram_urls(text: str) -> List[str]:
    found: List[str] = []
    for m in _URL_RE.finditer(text):
        u, _ = _strip_trailing_noise(m.group(0))
        netloc = urlparse(u).netloc.lower()
        if netloc.endswith("instagram.com"):
            found.append(u)
    return found


def replace_instagram_hosts(text: str, mirror_host: str) -> Tuple[str, bool]:
    """
    Rewrite every instagram.com URL in text to www.<mirror>.
    Returns (new_text, any_change).
    """
    changed = False

    def repl(match: re.Match[str]) -> str:
        nonlocal changed
        raw_full = match.group(0)
        u, trailing = _strip_trailing_noise(raw_full)
        if not u or not urlparse(u).netloc.lower().endswith("instagram.com"):
            return raw_full
        mirrored = instagram_url_to_mirror(u, mirror_host)
        changed = True
        return mirrored + trailing

    out = _URL_RE.sub(repl, text)
    return out, changed
