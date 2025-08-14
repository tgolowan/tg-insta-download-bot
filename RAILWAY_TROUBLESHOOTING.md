# 🚂 Railway Troubleshooting Guide

## Common Issues & Solutions

### 1. **429 Too Many Requests Error**
**Problem**: Instagram rate limiting on Railway
**Solution**: 
- Set `IG_DISABLE_LOGIN=true` in Railway environment variables
- Set `IG_LOGIN_ON_START=false` 
- Set `MIN_REQUEST_INTERVAL_SECONDS=8` (minimum 8 seconds between requests)
- Set `RATE_LIMIT_COOLDOWN_SECONDS=600` (10 minutes cooldown after 429)

### 2. **401 Unauthorized Error**
**Problem**: Instagram authentication issues
**Solution**:
- Ensure `IG_DISABLE_LOGIN=true` initially
- Only enable login if you have valid Instagram credentials
- Check if 2FA is enabled on Instagram account

### 3. **Bot Stopping Unexpectedly**
**Problem**: Application stopping on Railway
**Solution**:
- Set `RESTART_ON_STOP=true` (enabled by default)
- Bot will automatically restart after 5 seconds
- Check Railway logs for underlying errors

### 4. **Exception Errors**
**Problem**: `QueryBadStatusException` not found
**Solution**: ✅ **FIXED** - Updated to use correct exception names:
- `TooManyRequestsException` for rate limits
- `QueryReturnedForbiddenException` for 401/403
- `QueryReturnedBadRequestException` for bad requests
- `ConnectionException` for network issues

## Recommended Railway Environment Variables

```env
# Required
BOT_TOKEN=your_telegram_bot_token_here

# Instagram (set to false initially to avoid 429s)
IG_LOGIN_ON_START=false
IG_DISABLE_LOGIN=true

# Throttling (important for Railway)
MIN_REQUEST_INTERVAL_SECONDS=8
RATE_LIMIT_COOLDOWN_SECONDS=600

# Supervision
RESTART_ON_STOP=true

# Optional (only if you have valid credentials)
INSTAGRAM_USERNAME=
INSTAGRAM_PASSWORD=
```

## Railway-Specific Optimizations

### Rate Limiting
- **Minimum Interval**: 8 seconds between Instagram requests
- **Cooldown**: 10 minutes after receiving 429
- **Lazy Login**: Only login when absolutely necessary

### Auto-Restart
- **Supervisor Loop**: Bot automatically restarts on stop/crash
- **Health Checks**: `/health` endpoint for Railway monitoring
- **Graceful Handling**: Proper error handling for all Instagram exceptions

### Resource Management
- **Memory Efficient**: Automatic cleanup of downloaded files
- **Connection Pooling**: Reuse connections when possible
- **Error Recovery**: Graceful fallback for various failure modes

## Testing Your Fixes

1. **Deploy with new environment variables**
2. **Test with a simple Instagram link**
3. **Monitor Railway logs for errors**
4. **Check bot responsiveness**

## If Problems Persist

1. **Check Railway logs** for specific error messages
2. **Verify environment variables** are set correctly
3. **Test locally** with `python test_bot.py`
4. **Consider increasing intervals** if still getting 429s

## Performance Tips

- Start with `IG_DISABLE_LOGIN=true` to test basic functionality
- Only enable login if you need access to private content
- Monitor Railway resource usage
- Consider upgrading to Pro tier if hitting free tier limits

---

🎯 **Key Takeaway**: The bot is now much more Railway-friendly with proper rate limiting, exception handling, and auto-restart capabilities!
