#!/usr/bin/env python3
"""
Test script for Instagram Download Bot
Run this to test individual components before starting the full bot
"""

import os
import sys
from dotenv import load_dotenv

def test_imports():
    """Test if all required modules can be imported."""
    print("🔍 Testing imports...")
    
    try:
        from telegram import Update
        from telegram.ext import Application
        print("✅ python-telegram-bot imported successfully")
    except ImportError as e:
        print(f"❌ Failed to import python-telegram-bot: {e}")
        return False
    
    try:
        import instaloader
        print("✅ instaloader imported successfully")
    except ImportError as e:
        print(f"❌ Failed to import instaloader: {e}")
        return False
    
    try:
        import requests
        print("✅ requests imported successfully")
    except ImportError as e:
        print(f"❌ Failed to import requests: {e}")
        return False
    
    return True

def test_config():
    """Test configuration loading."""
    print("\n🔍 Testing configuration...")
    
    try:
        # Temporarily set a test token for testing
        import os
        os.environ['BOT_TOKEN'] = 'test_token_for_testing'
        
        from config import BOT_TOKEN, DOWNLOAD_PATH, MAX_FILE_SIZE
        print("✅ Configuration loaded successfully")
        print(f"   Download path: {DOWNLOAD_PATH}")
        print(f"   Max file size: {MAX_FILE_SIZE / 1024 / 1024:.1f}MB")
        return True
    except Exception as e:
        print(f"❌ Failed to load configuration: {e}")
        return False

def test_instagram_downloader():
    """Test Instagram downloader initialization."""
    print("\n🔍 Testing Instagram downloader...")
    
    try:
        # Ensure BOT_TOKEN is set for testing
        import os
        if 'BOT_TOKEN' not in os.environ:
            os.environ['BOT_TOKEN'] = 'test_token_for_testing'
        
        from instagram_downloader import InstagramDownloader
        downloader = InstagramDownloader()
        print("✅ Instagram downloader initialized successfully")
        
        # Test URL validation
        test_urls = [
            "https://www.instagram.com/p/ABC123/",
            "https://instagram.com/reel/XYZ789/",
            "https://example.com/not-instagram",
            "invalid-url"
        ]
        
        for url in test_urls:
            is_valid = downloader.is_valid_instagram_url(url)
            status = "✅" if is_valid else "❌"
            print(f"   {status} {url}")
        
        return True
    except Exception as e:
        print(f"❌ Failed to initialize Instagram downloader: {e}")
        return False

def test_bot_initialization():
    """Test bot initialization (without starting)."""
    print("\n🔍 Testing bot initialization...")
    
    try:
        # Ensure BOT_TOKEN is set for testing
        import os
        if 'BOT_TOKEN' not in os.environ:
            os.environ['BOT_TOKEN'] = 'test_token_for_testing'
        
        from bot import InstagramDownloadBot
        # Don't actually start the bot, just test initialization
        print("✅ Bot class imported successfully")
        return True
    except Exception as e:
        print(f"❌ Failed to import bot: {e}")
        return False

def test_environment():
    """Test environment setup."""
    print("\n🔍 Testing environment...")
    
    # Load environment variables
    load_dotenv()
    
    bot_token = os.getenv('BOT_TOKEN')
    if bot_token and bot_token != 'your_telegram_bot_token_here':
        print("✅ BOT_TOKEN found in environment")
    else:
        print("⚠️  BOT_TOKEN not set or using default value")
        print("   Please set BOT_TOKEN in your .env file")
    
    instagram_username = os.getenv('INSTAGRAM_USERNAME')
    if instagram_username and instagram_username != 'your_instagram_username':
        print("✅ INSTAGRAM_USERNAME found in environment")
    else:
        print("⚠️  INSTAGRAM_USERNAME not set (optional)")
    
    return True

def main():
    """Run all tests."""
    print("🚀 Instagram Download Bot - Component Tests\n")
    
    tests = [
        test_imports,
        test_config,
        test_instagram_downloader,
        test_bot_initialization,
        test_environment
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"❌ Test {test.__name__} failed with exception: {e}")
    
    print(f"\n📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! The bot should work correctly.")
        print("\nNext steps:")
        print("1. Set your BOT_TOKEN in the .env file")
        print("2. Optionally add Instagram credentials")
        print("3. Run: python bot.py")
    else:
        print("⚠️  Some tests failed. Please fix the issues before running the bot.")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
