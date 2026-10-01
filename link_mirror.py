"""Detect Instagram URLs and rewrite the host for a mirror-style link preview."""

from __future__ import annotations

import re
from typing import List, Optional, Sequence, Tuple
from urllib.parse import urlparse, urlunparse

_TRAILING = frozenset(".,);:!?\"]'\u00bb")

# [\w.-]*instagram.com matches www.instagram.com and www.zzinstagram.com (InstaFix mirrors).
_INSTAGRAM_PATH = r"(?:/[^\s\]\}\)<>\"']*)?"
_INSTAGRAM_HOST = r"[\w.-]*instagram\.com"
_INSTAGRAM_RE = re.compile(
    rf"(?:https?://{_INSTAGRAM_HOST}{_INSTAGRAM_PATH}|"
    rf"(?<![\w./]){_INSTAGRAM_HOST}{_INSTAGRAM_PATH})",
    re.IGNORECASE,
)


def is_canonical_instagram_host(netloc: str) -> bool:
    n = netloc.lower().removeprefix("www.")
    return n in ("instagram.com", "m.instagram.com")


def is_mirror_instagram_host(netloc: str) -> bool:
    n = netloc.lower().removeprefix("www.")
    if is_canonical_instagram_host(netloc):
        return False
    return n.endswith("instagram.com")


def canonical_instagram_url(url: str) -> str:
    """Normalize instagram.com or *instagram.com mirror links to www.instagram.com."""
    parsed = urlparse(_ensure_instagram_scheme(url))
    n = parsed.netloc.lower().removeprefix("www.")
    if not n.endswith("instagram.com"):
        return url
    if is_mirror_instagram_host(parsed.netloc) or is_canonical_instagram_host(
        parsed.netloc
    ):
        path = parsed.path or "/"
        return urlunparse(("https", "www.instagram.com", path, "", "", ""))
    return url


def is_instagram_link(url: str) -> bool:
    parsed = urlparse(_ensure_instagram_scheme(url))
    n = parsed.netloc.lower().removeprefix("www.")
    return is_canonical_instagram_host(parsed.netloc) or is_mirror_instagram_host(
        parsed.netloc
    )


def _ensure_instagram_scheme(url: str) -> str:
    u = url.strip()
    if not re.match(r"https?://", u, re.IGNORECASE):
        u = "https://" + u.lstrip("/")
    return u


def normalize_mirror_host(raw: str) -> str:
    h = raw.strip().lower().rstrip("/")
    return h.replace("www.", "", 1) if h.startswith("www.") else h


def instagram_url_to_mirror(url: str, mirror_host: str) -> str:
    parsed = urlparse(_ensure_instagram_scheme(url))
    if not is_instagram_link(url):
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
        u = _ensure_instagram_scheme(u)
        if is_instagram_link(u):
            found.append(canonical_instagram_url(u))
    return found


def collect_message_link_text(message) -> str:
    """Message text/caption plus hidden URLs from TEXT_LINK entities."""
    base = (message.text or message.caption or "").strip()
    chunks = [base] if base else []
    entities = message.entities or message.caption_entities or []
    for ent in entities:
        url = getattr(ent, "url", None)
        if url:
            chunks.append(url.strip())
    return "\n".join(c for c in chunks if c).strip()


def replace_instagram_hosts(text: str, mirror_host: str) -> Tuple[str, bool]:
    changed = False

    def repl(match: re.Match[str]) -> str:
        nonlocal changed
        raw_full = match.group(0)
        u, trailing = _strip_trailing_noise(raw_full)
        u = canonical_instagram_url(_ensure_instagram_scheme(u))
        if not u or not is_instagram_link(u):
            return raw_full
        changed = True
        return instagram_url_to_mirror(u, mirror_host) + trailing

    return _INSTAGRAM_RE.sub(repl, text), changed


def _unchecked_fallback_hosts(mirror_hosts: Sequence[str]) -> List[str]:
    """Hosts to try when probes fail — avoid broken instagram7 placeholders last."""
    from preview_check import PHOTO_POST_MIRROR_HOSTS, PREFERRED_MIRROR_HOSTS

    order = list(PHOTO_POST_MIRROR_HOSTS) + list(PREFERRED_MIRROR_HOSTS)
    seen: set[str] = set()
    ranked: List[str] = []
    for h in order:
        n = h.strip().lower().removeprefix("www.")
        if n and n not in seen:
            seen.add(n)
            ranked.append(n)
    for h in mirror_hosts:
        n = h.strip().lower().removeprefix("www.")
        if n and n not in seen:
            seen.add(n)
            ranked.append(n)
    return ranked


def _unchecked_fallback_host(mirror_hosts: Sequence[str]) -> str:
    """Prefer vx/kkclip over instagram7 when probes all fail."""
    return _unchecked_fallback_hosts(mirror_hosts)[0]


def mirror_host_for_instagram_url(
    instagram_url: str, mirror_hosts: Sequence[str]
) -> str:
    """Pick a mirror host for posts, reels, or stories (no HTTP probe)."""
    from preview_check import (
        PHOTO_POST_MIRROR_HOSTS,
        REEL_MIRROR_HOSTS,
        STORY_MIRROR_HOSTS,
        is_instagram_reel,
        is_instagram_story,
        is_photo_post,
    )

    if is_instagram_story(instagram_url):
        return STORY_MIRROR_HOSTS[0]
    if is_photo_post(instagram_url):
        ranked = _unchecked_fallback_hosts(mirror_hosts)
        for h in PHOTO_POST_MIRROR_HOSTS:
            n = h.strip().lower().removeprefix("www.")
            if n in ranked:
                return n
        return ranked[0]
    if is_instagram_reel(instagram_url):
        return REEL_MIRROR_HOSTS[0]
    return _unchecked_fallback_hosts(mirror_hosts)[0]


def fast_mirror_instagram_text(
    text: str, mirror_hosts: Sequence[str]
) -> Tuple[str, bool]:
    """Rewrite instagram.com URLs without HTTP probes (Railway timeout fallback)."""
    changed = False

    def repl(match: re.Match[str]) -> str:
        nonlocal changed
        raw_full = match.group(0)
        u, trailing = _strip_trailing_noise(raw_full)
        u = canonical_instagram_url(_ensure_instagram_scheme(u))
        if not u or not is_instagram_link(u):
            return raw_full
        changed = True
        host = mirror_host_for_instagram_url(u, mirror_hosts)
        return instagram_url_to_mirror(u, host) + trailing

    return _INSTAGRAM_RE.sub(repl, text), changed


def replace_instagram_hosts_checked(
    text: str,
    mirror_hosts: Sequence[str],
    *,
    verify_preview: bool = True,
    preview_timeout: float = 8.0,
    fallback_unchecked: bool = True,
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
        u = canonical_instagram_url(_ensure_instagram_scheme(u))
        if not u or not is_instagram_link(u):
            return raw_full

        from preview_check import is_instagram_story, is_photo_post, pick_working_mirror

        if not verify_preview:
            host = (
                mirror_host_for_instagram_url(u, mirror_hosts)
                if is_instagram_story(u)
                else mirror_hosts[0]
            )
            changed = True
            return instagram_url_to_mirror(u, host) + trailing

        if is_instagram_story(u):
            if fallback_unchecked:
                host = mirror_host_for_instagram_url(u, mirror_hosts)
                changed = True
                return instagram_url_to_mirror(u, host) + trailing
            return raw_full

        picked = pick_working_mirror(u, mirror_hosts, timeout=preview_timeout)
        if not picked:
            # For /p/ posts, a dead unchecked mirror is worse than an honest failure
            # notice. Mirrors commonly return placeholders for login/age-gated posts.
            if fallback_unchecked and not is_photo_post(u):
                # pick_working_mirror already probed hosts — avoid a second slow pass on Railway.
                host = mirror_host_for_instagram_url(u, mirror_hosts)
                changed = True
                return instagram_url_to_mirror(u, host) + trailing
            return raw_full
        mirrored, _host = picked
        changed = True
        return mirrored + trailing

    out = _INSTAGRAM_RE.sub(repl, text)
    return out, changed
