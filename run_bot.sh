#!/bin/bash

# Instagram Download Bot Startup Script

echo "🚀 Starting Instagram Download Bot..."

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.8 or higher."
    exit 1
fi

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source venv/bin/activate

# Install/upgrade dependencies
echo "📥 Installing dependencies..."
pip install -r requirements.txt

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "⚠️  .env file not found. Creating from template..."
    cp env.example .env
    echo "📝 Please edit .env file with your bot token and Instagram credentials."
    echo "   Then run this script again."
    exit 1
fi

# Test the bot components
echo "🧪 Testing bot components..."
python test_bot.py

if [ $? -eq 0 ]; then
    echo "✅ All tests passed! Starting the bot..."
    echo "🤖 Bot is now running. Press Ctrl+C to stop."
    python bot.py
else
    echo "❌ Tests failed. Please fix the issues before running the bot."
    exit 1
fi
