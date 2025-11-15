# ⚡ Quick Deploy to Railway

## Commands to Run

```bash
# 1. Check what files changed
git status

# 2. Add all changes
git add .

# 3. Commit changes
git commit -m "Convert to TikTok downloader bot"

# 4. Push to GitHub
git push origin main
```

## After Pushing

1. **Railway will auto-deploy** if already connected
2. **Or connect manually:**
   - Go to Railway Dashboard
   - New Project → Deploy from GitHub
   - Select your repo

## Required Environment Variable

Only one variable needed:
```
BOT_TOKEN=your_telegram_bot_token_here
```

Set it in Railway Dashboard → Variables tab.

## That's It! 🎉

Your TikTok bot will be live in a few minutes.

