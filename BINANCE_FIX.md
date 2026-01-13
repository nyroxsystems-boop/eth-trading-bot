# Quick Fix: Binance 451 Error

## Problem
Railway deployment shows: `451 Client Error: Unavailable For Legal Reasons`

## Fastest Solution: Use a Proxy

### 1. Get a Proxy Service
Recommended options:
- **Bright Data** (formerly Luminati): https://brightdata.com
- **Smartproxy**: https://smartproxy.com
- **Oxylabs**: https://oxylabs.io

Most offer free trials.

### 2. Add to Railway Environment Variables

Go to your Railway project → Worker service → Variables:

```bash
HTTPS_PROXY=http://username:password@proxy-server:port
HTTP_PROXY=http://username:password@proxy-server:port
```

Example:
```bash
HTTPS_PROXY=http://user123:pass456@proxy.example.com:8080
HTTP_PROXY=http://user123:pass456@proxy.example.com:8080
```

### 3. Restart the Service

Railway will automatically restart after adding variables.

---

## Alternative: Use Binance Testnet (For Testing)

If you just want to test the bot without real trading:

1. Sign up at: https://testnet.binance.vision
2. Get testnet API keys
3. Add to Railway:
   ```bash
   BINANCE_API_KEY=your_testnet_key
   BINANCE_API_SECRET=your_testnet_secret
   BINANCE_TESTNET=true
   ```

> [!NOTE]
> Testnet uses fake money but real market data. Perfect for testing!

---

## Alternative: Deploy to Different Region

In Railway:
1. Go to Service Settings
2. Change deployment region
3. Try: EU West or Asia Pacific

---

## Verify It's Fixed

Check Railway logs for:
```
✅ Successfully fetched klines from Binance
```

Instead of:
```
❌ 451 Client Error
```
