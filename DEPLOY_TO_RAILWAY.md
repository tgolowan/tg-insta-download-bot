# 🚂 Deploy TikTok Bot to Railway

## Quick Deploy Steps

### 1. Commit Your Changes

```bash
# Add all files
git add .

# Commit changes
git commit -m "Convert bot from Instagram to TikTok downloader"

# Push to your repository
git push origin main
```

### 2. Deploy on Railway

#### Option A: If Railway is already connected to your GitHub repo
- Railway will automatically detect the push and redeploy
- Go to Railway Dashboard → Your Project → Deployments
- Wait for the build to complete

#### Option B: Connect Railway to GitHub (First Time)
1. Go to [Railway Dashboard](https://railway.app/dashboard)
2. Click **"New Project"**
3. Select **"Deploy from GitHub repo"**
4. Choose your repository
5. Railway will automatically detect it's a Python project
6. Click **"Deploy Now"**

### 3. Set Environment Variables

In Railway Dashboard → Your Project → Variables, add:

```env
BOT_TOKEN=your_telegram_bot_token_here
RESTART_ON_STOP=true
DOWNLOAD_PATH=./downloads
```

**That's it!** No Instagram credentials needed for TikTok.

### 4. Verify Deployment

1. Check Railway logs for any errors
2. Send `/start` to your bot on Telegram
3. Test with a TikTok link

## What Changed

✅ **Removed:**
- Instagram downloader (`instagram_downloader.py`)
- Instagram credentials and login logic
- Rate limiting for Instagram
- All Instagram-specific configuration

✅ **Added:**
- TikTok downloader (`tiktok_downloader.py`)
- yt-dlp for TikTok video downloads
- Simplified configuration (no auth needed)
- Support for all TikTok URL formats

## Files Changed

- `bot.py` - Updated to use TikTokDownloader
- `tiktok_downloader.py` - New TikTok downloader
- `config.py` - Removed Instagram settings
- `requirements.txt` - Replaced instaloader with yt-dlp
- `env.example` - Simplified environment variables

## Railway Configuration

The bot will automatically:
- ✅ Detect Python project
- ✅ Install dependencies from `requirements.txt`
- ✅ Run `python bot.py` (from Procfile)
- ✅ Start health check server on port from Railway
- ✅ Auto-restart on failures

## Troubleshooting

If deployment fails:
1. Check Railway logs for error messages
2. Verify `BOT_TOKEN` is set correctly
3. Ensure all files are committed and pushed
4. Check that `requirements.txt` has correct dependencies

## Next Steps After Deploy

1. **Test the bot:**
   - Send `/start` command
   - Paste a TikTok link
   - Verify video downloads correctly

2. **Monitor:**
   - Check Railway logs regularly
   - Monitor resource usage
   - Watch for any errors

3. **Enjoy:**
   - Your TikTok download bot is ready! 🎉

