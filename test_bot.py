#!/usr/bin/env python3
"""Smoke tests for the Instagram mirror bot."""

import os
import sys


def test_link_mirror():
    print("\nTesting link_mirror…")
    from link_mirror import instagram_url_to_mirror, replace_instagram_hosts

    mirror = instagram_url_to_mirror(
        "https://www.instagram.com/reel/AbCdE/", "kkclip.com"
    )
    assert mirror == "https://www.kkclip.com/reel/AbCdE/", mirror

    text = "Watch https://instagram.com/tv/foo/!"
    out, changed = replace_instagram_hosts(text, "kkclip.com")
    assert changed
    assert "://www.instagram.com" not in out and "://instagram.com" not in out
    assert out.endswith("/tv/foo/!")
    tracked = "https://www.instagram.com/reel/DS0Q8cfDLDA/?igsh=abc=="
    mirrored = instagram_url_to_mirror(tracked, "kkclip.com")
    assert mirrored == "https://www.kkclip.com/reel/DS0Q8cfDLDA/"
    assert "igsh" not in mirrored

    from link_mirror import extract_instagram_urls, replace_instagram_hosts_checked

    hyphen = "https://www.instagram.com/reel/Da-HxxeN_mz/?igsh=MTI2bm81am43Nzd6Zw=="
    assert extract_instagram_urls(hyphen)
    out, changed = replace_instagram_hosts_checked(
        hyphen,
        ("kkclip.com", "instagram7.com"),
        verify_preview=False,
    )
    assert changed
    assert "kkclip.com/reel/Da-HxxeN_mz/" in out
    print("   OK")


def test_preview_parse():
    print("\nTesting preview_check…")
    from preview_check import (
        mirror_host_chain,
        page_likely_has_preview,
        pick_working_mirror,
        preview_score,
    )

    assert page_likely_has_preview('<meta property="og:video" content="x">')
    assert not page_likely_has_preview("<html></html>")
    placeholder = (
        '<meta property="og:title" content="Instagram7 fixed preview">'
        '<meta property="og:image" content="https://www.instagram7.com/fallback/Ab.png">'
        "Instagram did not provide public media for this post."
    )
    assert preview_score(placeholder) == 0
    assert not page_likely_has_preview(placeholder)

    chain = mirror_host_chain("vxinstagram.com", ("kkclip.com", "vxinstagram.com"))
    assert chain[0] == "eeinstagram.com"
    assert chain[1] == "instagram7.com"
    assert "vxinstagram.com" in chain

    reel = "https://www.instagram.com/reel/DbIbyjgIlDZ/"
    picked = pick_working_mirror(reel, chain, timeout=15)
    assert picked is not None
    assert picked[1] in ("eeinstagram.com", "instagram7.com"), picked
    print("   OK")


def test_bot_import():
    print("\nTesting bot import…")
    os.environ["BOT_TOKEN"] = "dummy"
    import importlib

    import config

    importlib.reload(config)
    import bot as bot_mod

    importlib.reload(bot_mod)
    cls = getattr(bot_mod, "SocialLinksBot")
    cls()
    print("   OK")


def test_tiktok_urls():
    print("\nTesting TikTok URL extract…")
    from tiktok_urls import extract_tiktok_urls

    s = (
        "See https://www.tiktok.com/@user/video/123?q=1 "
        "and https://vm.tiktok.com/ZMabc/"
    )
    u = extract_tiktok_urls(s)
    assert len(u) >= 2
    print("   OK")


def main() -> int:
    print("Social links bot — smoke tests")
    tests = [test_link_mirror, test_preview_parse, test_tiktok_urls, test_bot_import]
    ok = True
    for t in tests:
        try:
            t()
        except Exception as e:
            print(f"   FAIL {t.__name__}: {e}")
            ok = False

    print(f"\nResult: {'all passed' if ok else 'some failed'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
