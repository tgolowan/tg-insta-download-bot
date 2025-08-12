# 🚂 Railway Deployment Guide

This guide will help you deploy your Instagram Download Bot on Railway.

## Prerequisites

- [Railway account](https://railway.app/)
- [GitHub repository](https://github.com/) with your bot code
- Telegram Bot Token from [@BotFather](https://t.me/BotFather)

## Step 1: Prepare Your Repository

Ensure your repository has these files:
- `bot.py` - Main bot file
- `requirements.txt` - Python dependencies
- `Procfile` - Railway process definition
- `runtime.txt` - Python version specification
- `railway.json` - Railway configuration

## Step 2: Deploy on Railway

### Option A: Deploy from GitHub

1. **Go to [Railway Dashboard](https://railway.app/dashboard)**
2. **Click "New Project"**
3. **Select "Deploy from GitHub repo"**
4. **Choose your repository**
5. **Click "Deploy Now"**

### Option B: Deploy from CLI

1. **Install Railway CLI:**
   ```bash
   npm install -g @railway/cli
   ```

2. **Login to Railway:**
   ```bash
   railway login
   ```

3. **Initialize and deploy:**
   ```bash
   railway init
   railway up
   ```

## Step 3: Configure Environment Variables

1. **In Railway Dashboard, go to your project**
2. **Click on "Variables" tab**
3. **Add these environment variables:**

```env
BOT_TOKEN=your_telegram_bot_token_here
INSTAGRAM_USERNAME=your_instagram_username
INSTAGRAM_PASSWORD=your_instagram_password
DOWNLOAD_PATH=./downloads
```

### Required Variables:

- **`BOT_TOKEN`** - Your Telegram bot token (required)
- **`PORT`** - Railway automatically sets this

### Optional Variables:

- **`INSTAGRAM_USERNAME`** - Instagram username for better access
- **`INSTAGRAM_PASSWORD`** - Instagram password for better access
- **`DOWNLOAD_PATH`** - Download directory (default: `./downloads`)

## Step 4: Deploy and Monitor

1. **Railway will automatically build and deploy your bot**
2. **Monitor the deployment logs for any errors**
3. **Check the bot status in Railway dashboard**

## Step 5: Test Your Bot

1. **Find your bot on Telegram**
2. **Send `/start` command**
3. **Test with an Instagram link**

## Railway-Specific Features

### Health Checks
- Railway automatically monitors the `/health` endpoint
- Bot will restart if health checks fail
- Health endpoint returns bot status and timestamp

### Auto-Restart
- Bot automatically restarts on failures
- Maximum 10 restart attempts
- Built-in error handling and recovery

### Logs
- View real-time logs in Railway dashboard
- Monitor bot performance and errors
- Debug issues easily

## Troubleshooting

### Common Issues:

1. **Build Failures:**
   - Check Python version compatibility
   - Verify all dependencies in `requirements.txt`
   - Check for syntax errors in code

2. **Runtime Errors:**
   - Check environment variables are set
   - Verify bot token is valid
   - Check Railway logs for detailed errors

3. **Bot Not Responding:**
   - Verify bot is running in Railway
   - Check if bot token is correct
   - Ensure bot has necessary permissions

### Debug Commands:

```bash
# View logs
railway logs

# Check status
railway status

# Restart service
railway service restart
```

## Performance Optimization

### Railway Recommendations:

1. **Use the latest Python version** (3.11+)
2. **Keep dependencies minimal** and up-to-date
3. **Implement proper error handling** to avoid crashes
4. **Use async/await** for better performance
5. **Monitor resource usage** in Railway dashboard

### Resource Limits:

- **Free Tier:** Limited resources, suitable for testing
- **Pro Tier:** Better performance for production use
- **Enterprise:** Custom resource allocation

## Monitoring and Maintenance

### Regular Checks:

1. **Monitor bot uptime** in Railway dashboard
2. **Check error logs** for issues
3. **Update dependencies** regularly
4. **Monitor Instagram rate limits**

### Updates:

1. **Push changes to GitHub**
2. **Railway automatically redeploys**
3. **Monitor deployment logs**
4. **Test bot functionality**

## Security Best Practices

1. **Never commit `.env` files** to Git
2. **Use Railway's built-in secret management**
3. **Regularly rotate bot tokens**
4. **Monitor bot usage for abuse**

## Support

- **Railway Documentation:** [docs.railway.app](https://docs.railway.app/)
- **Railway Discord:** [discord.gg/railway](https://discord.gg/railway)
- **GitHub Issues:** Report bugs in your repository

---

🎉 **Your bot is now deployed on Railway!** 

The bot will automatically start when you deploy and will be available 24/7 with Railway's infrastructure.
