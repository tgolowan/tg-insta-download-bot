# 🚂 Railway Environment Variables Setup

## Required Variables (Set These First)

### 1. **BOT_TOKEN** (Required)
```
BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
```
- Get this from [@BotFather](https://t.me/BotFather) on Telegram
- This is the only required variable

## Recommended Variables (For Railway)

### 2. **Instagram Login Control**
```
IG_LOGIN_ON_START=false
IG_DISABLE_LOGIN=true
```
- **`IG_LOGIN_ON_START=false`** - Don't login when bot starts
- **`IG_DISABLE_LOGIN=true`** - Disable Instagram login completely
- This prevents 429 errors on Railway

### 3. **Rate Limiting (Important for Railway)**
```
MIN_REQUEST_INTERVAL_SECONDS=8
RATE_LIMIT_COOLDOWN_SECONDS=600
```
- **`MIN_REQUEST_INTERVAL_SECONDS=8`** - Wait 8 seconds between requests
- **`RATE_LIMIT_COOLDOWN_SECONDS=600`** - 10 minute cooldown after 429

### 4. **Bot Supervision**
```
RESTART_ON_STOP=true
```
- **`RESTART_ON_STOP=true`** - Auto-restart if bot stops

## Optional Variables (Only if needed)

### 5. **Instagram Credentials**
```
INSTAGRAM_USERNAME=your_username
INSTAGRAM_PASSWORD=your_password
```
- Only set these if you need access to private content
- **Warning**: May cause 429 errors on Railway

### 6. **Download Settings**
```
DOWNLOAD_PATH=./downloads
```
- Default: `./downloads`
- Railway will handle this automatically

## How to Set in Railway

### Step 1: Go to Railway Dashboard
1. Open [Railway Dashboard](https://railway.app/dashboard)
2. Select your project
3. Click on the **"Variables"** tab

### Step 2: Add Variables
1. Click **"New Variable"**
2. Add each variable one by one
3. Click **"Add"** after each one

### Step 3: Deploy
- Railway will automatically redeploy when you add variables
- Check the logs to ensure everything works

## Complete Railway Environment Setup

```env
# Required
BOT_TOKEN=your_actual_bot_token_here

# Instagram Control (Recommended for Railway)
IG_LOGIN_ON_START=false
IG_DISABLE_LOGIN=true

# Rate Limiting
MIN_REQUEST_INTERVAL_SECONDS=8
RATE_LIMIT_COOLDOWN_SECONDS=600

# Bot Supervision
RESTART_ON_STOP=true

# Optional (only if needed)
INSTAGRAM_USERNAME=
INSTAGRAM_PASSWORD=
DOWNLOAD_PATH=./downloads
```

## Why This Configuration?

### 🚫 **Avoid 429 Errors**
- `IG_DISABLE_LOGIN=true` prevents Instagram login attempts
- `MIN_REQUEST_INTERVAL_SECONDS=8` spaces out requests
- `RATE_LIMIT_COOLDOWN_SECONDS=600` handles rate limits gracefully

### 🔄 **Auto-Recovery**
- `RESTART_ON_STOP=true` ensures bot restarts if it stops
- Health checks monitor bot status
- Graceful error handling for all Instagram issues

### 📱 **Public Content Only**
- Bot will only download public Instagram posts
- No authentication required
- More reliable on Railway's infrastructure

## Testing Your Setup

1. **Deploy with these variables**
2. **Send `/start` to your bot**
3. **Try with a public Instagram link**
4. **Check Railway logs for any errors**

## If You Still Get 429s

1. **Increase intervals**:
   ```
   MIN_REQUEST_INTERVAL_SECONDS=15
   RATE_LIMIT_COOLDOWN_SECONDS=900
   ```

2. **Disable completely**:
   ```
   IG_DISABLE_LOGIN=true
   IG_LOGIN_ON_START=false
   ```

3. **Monitor usage** - Railway free tier has limits

---

🎯 **Key Point**: Start with `IG_DISABLE_LOGIN=true` to test basic functionality, then enable login only if you need private content access.
