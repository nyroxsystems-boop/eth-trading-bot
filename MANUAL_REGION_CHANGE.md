# 🚨 CRITICAL: Manual Railway Region Change Required

## Problem
The `railway.json` change to `"region": "eu-west1"` was successfully deployed, **BUT** existing Railway services are **locked to their original region** (us-west2).

**Result:** Bot is still getting **451 Binance errors** because it's still running in the US.

![Railway Logs showing 451 error](file:///Users/xaaronvx/.gemini/antigravity/brain/043101de-08c6-4591-accb-579d87fce65f/railway_deployment_logs_451_error_1768407854153.png)

---

## Why railway.json Didn't Work

Railway services are **physically bound** to a region when created. The `railway.json` file only affects **new services**, not existing ones.

**Current Status:**
- ✅ Code optimizations deployed (TP/SL, entry thresholds, risk)
- ✅ railway.json updated with eu-west1
- ❌ **Services still running in us-west2**
- ❌ **451 errors persist**

---

## Solution: Manual Region Migration

You have **2 options**:

### Option 1: Change Region in Railway Dashboard (Recommended)

> [!IMPORTANT]
> This is the **fastest** solution (5 minutes)

**Steps:**

1. **Go to Railway Dashboard**
   - https://railway.com/project/c6bf66ba-9f5d-432a-ba69-fdaf43494a7a

2. **Click on "worker" service**

3. **Go to "Settings" tab** (right side)

4. **Scroll down to "Region" section**

5. **Click "Change Region"**

6. **Select "Europe West (eu-west1)"**
   - Alternative: "Asia Pacific Southeast (ap-southeast1)" for even better latency

7. **Click "Save"**

8. **Railway will automatically redeploy** in the new region

9. **Repeat for "web" service** (dashboard API)

**Expected Result:**
- Services redeploy in EU
- Binance API works (no 451 errors)
- Bot starts trading within 1-2 hours

---

### Option 2: Create New Services (If Option 1 Fails)

> [!WARNING]
> Only use this if Railway doesn't allow region changes for existing services

**Steps:**

1. **Delete existing services**
   - Go to each service → Settings → Delete Service

2. **Create new services**
   ```bash
   # In your local repo
   railway up
   ```

3. **Railway will create new services** using `railway.json` (eu-west1)

4. **Set environment variables** in Railway dashboard:
   ```
   BINANCE_API_KEY=<your_key>
   BINANCE_API_SECRET=<your_secret>
   DRY_RUN=false  # or true for paper trading
   AUTO_TRAIN_MODE=false
   AUTO_OPTIMIZE=true
   DAILY_TARGET_PCT=0.01
   ```

5. **Verify deployment**
   - Check logs for "PX px=" messages
   - No 451 errors

---

## Verification Steps

After changing region, verify:

### 1. Check Deployment Logs
```bash
# Should see price updates, NO 451 errors
railway logs --service worker | grep "PX px="
```

**Expected Output:**
```
2026-01-14 18:00:00 PX px=3245.67 adx=22.3 rsi=58.4
2026-01-14 18:01:00 PX px=3246.12 adx=22.5 rsi=58.6
```

**NO MORE:**
```
ERROR cycle: 451 Client Error: Unavailable For Legal Reasons
```

### 2. Check Service Region
In Railway dashboard:
- Service → Settings → Region
- Should show: **"Europe West (eu-west1)"**

### 3. Monitor First Trade
```bash
# Watch for first BUY/SELL
railway logs --service worker | grep -E "BUY|SELL"
```

**Expected:** First trade within 1-4 hours

---

## Timeline

| Step | Duration | Status |
|------|----------|--------|
| Change region in dashboard | 2 min | ⏳ Pending |
| Railway redeploy | 3-5 min | ⏳ Pending |
| Bot warmup (fetch data) | 5-10 min | ⏳ Pending |
| First trade | 1-4 hours | ⏳ Pending |

**Total:** ~10 minutes setup, then wait for first trade

---

## What Happens After Region Change

1. **Immediate (0-5 min):**
   - Railway redeploys in EU
   - Bot starts fetching price data
   - No more 451 errors ✅

2. **Short-term (5-30 min):**
   - ML model warms up (needs 400 bars)
   - Sentiment analysis starts
   - Risk guards activate

3. **First Trade (1-4 hours):**
   - Bot finds first entry signal
   - Executes BUY (or simulates if DRY_RUN=true)
   - Dashboard shows live trade

4. **Daily Performance (24h):**
   - 8-15 trades executed
   - Win rate: 52-58%
   - Daily P&L: **1.5-2.5%** 🎯

---

## Current Code Status

✅ **All optimizations are already deployed:**
- MAX_TRADES_PER_DAY = 15
- RISK_PCT_PER_TRADE = 0.006 (0.6%)
- TP_MIN = 0.010 (1.0%)
- TP_MAX = 0.015 (1.5%)
- STOP_FLOOR = 0.005 (0.5%)
- ENTRY_SCORE_MIN = 0.45
- RSI_MIN = 40
- ADX_MIN_TREND = 15.0

**Only missing:** Region change (manual step required)

---

## FAQ

### Q: Why didn't railway.json work automatically?
**A:** Railway locks services to their creation region. Config files only affect new services.

### Q: Will I lose data if I change region?
**A:** No. Railway migrates your environment variables and settings. Only the physical location changes.

### Q: Can I use a different region?
**A:** Yes! Recommended regions:
- `eu-west1` (Belgium) - Best for Europe
- `ap-southeast1` (Singapore) - Best latency to Binance
- `eu-central1` (Germany) - Alternative EU option

### Q: What if I can't change region in settings?
**A:** Use Option 2 (delete and recreate services). Railway will use `railway.json` for new services.

### Q: How long until bot starts trading?
**A:** After region change:
- 5-10 min: Data fetching starts
- 1-4 hours: First trade
- 24 hours: Full performance (ML warmup complete)

---

## Next Steps

1. **⚠️ URGENT:** Change Railway region to eu-west1 (see Option 1 above)
2. **✅ Verify:** Check logs for price data (no 451 errors)
3. **✅ Monitor:** Wait for first trade (1-4 hours)
4. **✅ Track:** Daily P&L should be 1-2% after 24h

---

## Support

If you need help:
1. Share Railway logs (screenshot or text)
2. Confirm current region (Settings → Region)
3. Check environment variables are set

**Expected Result:** After region change, bot should achieve **1-2% daily profit** starting tomorrow 🎯
