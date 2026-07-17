"""Detect Instagram URLs and rewrite the host for a mirror-style link preview."""

from __future__ import annotations

import re
from typing import List, Optional, Sequence, Tuple
from urllib.parse import urlparse, urlunparse

_TRAILING = frozenset(".,);:!?\"]'\u00bb")

_INSTAGRAM_RE = re.compile(
    r"https?://(?:[\w-]+\.)*instagram\.com(?:/[^\s\]\}\)<>\"']*)?",
    re.IGNORECASE,
)


def normalize_mirror_host(raw: str) -> str:
    h = raw.strip().lower().rstrip("/")
    return h.replace("www.", "", 1) if h.startswith("www.") else h


def instagram_url_to_mirror(url: str, mirror_host: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        parsed = urlparse("https://" + url)
    netloc = parsed.netloc.lower().removeprefix("www.")
    if not netloc.endswith("instagram.com"):
        return url
    base = normalize_mirror_host(mirror_host)
    new_netloc = f"www.{base}"
    path = parsed.path or "/"
    # Mirrors only need /reel/ID/ or /p/ID/ — drop igsh/utm tracking (Telegram preview).
    return urlunparse(("https", new_netloc, path, "", "", ""))


def _strip_trailing_noise(s: str) -> Tuple[str, str]:
    rest = ""
    u = s
    while u and u[-1] in _TRAILING:
        rest = u[-1] + rest
        u = u[:-1]
    return u, rest


def extract_instagram_urls(text: str) -> List[str]:
    found: List[str] = []
    for m in _INSTAGRAM_RE.finditer(text):
        u, _ = _strip_trailing_noise(m.group(0))
        nl = urlparse(u).netloc.lower().removeprefix("www.")
        if nl.endswith("instagram.com"):
            found.append(u)
    return found


def replace_instagram_hosts(text: str, mirror_host: str) -> Tuple[str, bool]:
    changed = False

    def repl(match: re.Match[str]) -> str:
        nonlocal changed
        raw_full = match.group(0)
        u, trailing = _strip_trailing_noise(raw_full)
        nl = urlparse(u).netloc.lower().removeprefix("www.")
        if not u or not nl.endswith("instagram.com"):
            return raw_full
        changed = True
        return instagram_url_to_mirror(u, mirror_host) + trailing

    return _INSTAGRAM_RE.sub(repl, text), changed


def replace_instagram_hosts_checked(
    text: str,
    mirror_hosts: Sequence[str],
    *,
    verify_preview: bool = True,
) -> Tuple[str, bool]:
    """
    Rewrite instagram.com URLs using mirror_hosts in order.
    When verify_preview is True, probe each candidate URL before using it.
    URLs with no working mirror are left unchanged.
    """
    if not mirror_hosts:
        return text, False

    changed = False

    def repl(match: re.Match[str]) -> str:
        nonlocal changed
        raw_full = match.group(0)
        u, trailing = _strip_trailing_noise(raw_full)
        nl = urlparse(u).netloc.lower().removeprefix("www.")
        if not u or not nl.endswith("instagram.com"):
            return raw_full

        if not verify_preview:
            out = instagram_url_to_mirror(u, mirror_hosts[0]) + trailing
            changed = True
            return out

        from preview_check import pick_working_mirror

        picked = pick_working_mirror(u, mirror_hosts)
        if not picked:
            return raw_full
        mirrored, _host = picked
        changed = True
        return mirrored + trailing

    out = _INSTAGRAM_RE.sub(repl, text)
    return out, changed
