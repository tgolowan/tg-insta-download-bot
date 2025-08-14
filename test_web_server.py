#!/usr/bin/env python3
"""
Test script for web server functionality
"""

import os
import sys
import time
import threading
import requests

# Set test token for testing
os.environ['BOT_TOKEN'] = 'test_token_for_testing'

def test_web_server():
    """Test the web server functionality."""
    print("🧪 Testing web server functionality...")
    
    try:
        from bot import InstagramDownloadBot
        
        # Create bot instance
        bot = InstagramDownloadBot()
        
        # Start web server in background
        web_thread = threading.Thread(target=bot.start_web_server, daemon=True)
        web_thread.start()
        
        # Wait for server to start
        time.sleep(3)
        
        # Test health endpoint
        try:
            response = requests.get('http://localhost:8000/health', timeout=5)
            if response.status_code == 200:
                print("✅ Health endpoint working correctly")
                print(f"   Response: {response.json()}")
            else:
                print(f"❌ Health endpoint returned status {response.status_code}")
                return False
        except requests.exceptions.RequestException as e:
            print(f"❌ Failed to connect to health endpoint: {e}")
            return False
        
        # Test root endpoint
        try:
            response = requests.get('http://localhost:8000/', timeout=5)
            if response.status_code == 200:
                print("✅ Root endpoint working correctly")
                print(f"   Response: {response.text}")
            else:
                print(f"❌ Root endpoint returned status {response.status_code}")
                return False
        except requests.exceptions.RequestException as e:
            print(f"❌ Failed to connect to root endpoint: {e}")
            return False
        
        print("🎉 Web server test passed!")
        return True
        
    except Exception as e:
        print(f"❌ Web server test failed: {e}")
        return False

if __name__ == "__main__":
    success = test_web_server()
    sys.exit(0 if success else 1)
