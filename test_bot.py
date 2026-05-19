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
    assert "instagram.com" not in out
    assert out.endswith("/tv/foo/!")
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
    tests = [test_link_mirror, test_tiktok_urls, test_bot_import]
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
