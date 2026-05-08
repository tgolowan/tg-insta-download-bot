#!/usr/bin/env python3
"""Smoke tests for the Instagram mirror bot."""

import os
import sys


def test_link_mirror():
    print("\nTesting link_mirror…")
    from link_mirror import replace_instagram_hosts, instagram_url_to_mirror

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
    cls = getattr(bot_mod, "IgMirrorTelegramBot")
    cls()
    print("   OK")


def main() -> int:
    print("Instagram mirror bot — smoke tests")
    tests = [test_link_mirror, test_bot_import]
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
