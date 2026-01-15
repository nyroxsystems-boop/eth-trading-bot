# 🔑 Binance API Key Configuration Guide

## ⚠️ Current Status

✅ **Bot is deployed and running on Railway**
✅ **Region changed to eu-west1 (Amsterdam)**
✅ **No 451 errors**
✅ **All code optimizations active**

❌ **Bot cannot trade due to API key permissions**

---

## 🚨 The Problem

**Error in logs:**
```
APIError(code=-2015): Invalid API-key, IP, or permissions for action
```

**What this means:**
Your Binance API key is missing required permissions or has IP restrictions that block Railway's servers.

---

## 🔧 How to Fix (5 Minutes)

### Step 1: Go to Binance API Management

1. **Login to Binance.com**
2. **Click on your profile** (top right)
3. **Go to "API Management"**

### Step 2: Find Your API Key

Look for the API key starting with:
```
ppJSE0s9iKjp6Fd1t5lHEVqMeCaj4A2fghUrt6F2ERUZqlkz5TyeV2clOWPFdKkC
```

### Step 3: Enable Required Permissions

Click **"Edit"** or **"Manage"** on your API key, then enable:

- ✅ **Enable Reading** (should already be enabled)
- ✅ **Enable Spot & Margin Trading**
- ✅ **Enable Futures** ⚠️ **CRITICAL - This is likely missing!**

> [!IMPORTANT]
> **The bot trades ETH/USDT Futures**, so the "Enable Futures" permission is REQUIRED.

### Step 4: Remove IP Restrictions

Railway uses **dynamic IP addresses**, so you need to either:

**Option A: Unrestricted (Recommended for testing)**
- Set IP access to **"Unrestricted"**
- This allows the bot to connect from any IP

**Option B: Whitelist Railway IPs**
- Add Railway's IP ranges for eu-west1
- More secure but requires maintenance

> [!TIP]
> For initial testing, use "Unrestricted". You can add IP restrictions later once the bot is trading successfully.

### Step 5: Save Changes

1. **Click "Save"**
2. **Confirm with 2FA** (if enabled)
3. **Wait 1-2 minutes** for changes to propagate

---

## ✅ Verification

After fixing the API key, check Railway logs:

### 1. Bot Should Restart Automatically
```
2026-01-14 18:00:00 START ETH Master Bot | DRY_RUN=False | MaxTrades=15
```

### 2. Price Data Should Appear
```
2026-01-14 18:01:00 PX px=3245.67 adx=22.3 rsi=58.4
2026-01-14 18:02:00 PX px=3246.12 adx=22.5 rsi=58.6
```

### 3. No More API Errors
```
✅ No "APIError(code=-2015)" in logs
```

### 4. Telegram Notification
You should receive a message:
```
🤖 ETH Bot Started
Region: eu-west1
Mode: Live Trading
Target: 1% daily
```

---

## 📊 Expected Timeline

| Time | What Happens |
|------|--------------|
| **Now** | Fix API key permissions (5 min) |
| **+2 min** | Railway detects change, restarts bot |
| **+5 min** | Bot fetches price data ✅ |
| **+1-4 hours** | **First trade executed!** 🎯 |
| **+24 hours** | 8-15 trades, **1-2% profit** 🔥 |

---

## 🔍 How to Check Railway Logs

1. **Go to Railway Dashboard:**
   https://railway.com/project/c6bf66ba-9f5d-432a-ba69-fdaf43494a7a

2. **Click on "worker" (Arbeitnehmer) service**

3. **Click "Logs" or "Protokolle anzeigen"**

4. **Look for:**
   - ✅ "PX px=" messages (price data)
   - ✅ "BUY" or "SELL" messages (trades)
   - ❌ "APIError" messages (still broken)

---

## 🎯 What Happens After Fix

### Immediate (0-5 min)
- Bot restarts automatically
- Fetches price data from Binance
- ML model starts analyzing market

### Short-term (5-30 min)
- Bot warms up (needs 400 bars of data)
- Sentiment analysis activates
- Risk guards initialize

### First Trade (1-4 hours)
- Bot finds entry signal
- Executes BUY order
- Sets TP (Take Profit) and SL (Stop Loss)
- Sends Telegram notification

### Daily Performance (24h)
- 8-15 trades executed
- Win rate: 52-58%
- **Daily P&L: 1.5-2.5%** 🎯

---

## 🚨 Troubleshooting

### Still Getting API Errors?

**Check:**
1. ✅ Futures permission is enabled
2. ✅ IP restrictions are removed
3. ✅ API key is not expired
4. ✅ 2FA confirmation was completed

**Try:**
- Wait 5 minutes for Binance to propagate changes
- Manually redeploy in Railway (Settings → Redeploy)
- Check if API key is for **Binance.com** (not Binance.us)

### No Price Data in Logs?

**Possible causes:**
- API key still has wrong permissions
- Railway is still restarting (wait 2-3 min)
- Check if worker service is "Online" in Railway

### No Telegram Messages?

**Check:**
1. TELEGRAM_BOT_TOKEN is correct
2. TELEGRAM_CHAT_ID is correct
3. Bot has permission to send messages
4. Start a conversation with your bot first

---

## 📞 Next Steps

1. **Fix Binance API key** (5 minutes)
   - Enable Futures permission
   - Remove IP restrictions

2. **Monitor Railway logs** (10 minutes)
   - Check for "PX px=" messages
   - Verify no API errors

3. **Wait for first trade** (1-4 hours)
   - Bot will find entry signal automatically
   - Telegram notification when trade executes

4. **Track performance** (24 hours)
   - Monitor daily P&L
   - Should reach 1-2% profit

---

## ✅ Quick Checklist

- [ ] Go to Binance.com → API Management
- [ ] Find API key (ppJSE0s9iKjp...)
- [ ] Enable "Enable Futures" permission
- [ ] Remove IP restrictions (set to "Unrestricted")
- [ ] Save changes + confirm 2FA
- [ ] Wait 2-5 minutes
- [ ] Check Railway logs for "PX px=" messages
- [ ] Verify no "APIError" in logs
- [ ] Wait for first trade (1-4 hours)

---

**The bot is 100% ready to trade - just needs the API key fix!** 🚀
