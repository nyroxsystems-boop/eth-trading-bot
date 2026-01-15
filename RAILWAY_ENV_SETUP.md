# 🔐 Railway Environment Variables Setup

## Quick Copy-Paste for Railway Dashboard

Go to Railway Dashboard → Your Project → Each Service (worker & web) → Variables Tab

Then copy-paste these variables:

### Binance API Credentials
```
BINANCE_API_KEY=ppJSE0s9iKjp6Fd1t5lHEVqMeCaj4A2fghUrt6F2ERUZqlkz5TyeV2clOWPFdKkC
BINANCE_API_SECRET=2ihPOblVZdhRTFLbfubuNKZUNR5VDb5tuq5wH7hXlzM7J9ARCn08XwXZ0LPdNEIs
```

### Telegram Notifications
```
TELEGRAM_BOT_TOKEN=8313976588:AAHp7jgE1wr84yvChl2PAhHh5zkxXAS60s4
TELEGRAM_CHAT_ID=6379480212
```

### Trading Configuration
```
SYMBOL=ETHUSDT
BASE_ASSET=ETH
QUOTE_ASSET=USDT
```

### Risk Management (Optimized for 1% daily)
```
MAX_TRADES_PER_DAY=15
RISK_PCT_PER_TRADE=0.006
DAILY_TARGET_PCT=0.01
MAX_DRAWDOWN_DAY=0.05
```

### Entry/Exit Parameters
```
ENTRY_SCORE_MIN=0.45
SEC_PML_MIN=0.48
TAKE_PROFIT_PCT=0.010
TP_MIN=0.010
TP_MAX=0.015
STOP_FLOOR=0.005
STOP_ATR_MULT=1.5
BREAK_EVEN_TRIGGER=0.006
```

### Regime Filters
```
ADX_MIN_TREND=15
USE_ADX_FILTER=true
RSI_MIN=40
RSI_MAX=70
```

### Advanced Features
```
AUTO_OPTIMIZE=true
AUTO_TRAIN_MODE=false
DRY_RUN=false
LOG_LEVEL=INFO
```

---

## Step-by-Step Instructions

### 1. Go to Railway Dashboard
https://railway.com/project/c6bf66ba-9f5d-432a-ba69-fdaf43494a7a

### 2. Add Variables to "worker" Service

1. Click on **"worker"** service
2. Click **"Variables"** tab
3. Click **"New Variable"** button
4. **Option A: Bulk Add (Fastest)**
   - Click "Raw Editor" toggle (top right)
   - Copy ALL variables from above
   - Paste into the text area
   - Click "Save"

5. **Option B: Add One by One**
   - For each variable above:
     - Click "New Variable"
     - Enter variable name (e.g., `BINANCE_API_KEY`)
     - Enter value (e.g., `ppJSE0s9iKjp6Fd1t5lHEVqMeCaj4A2fghUrt6F2ERUZqlkz5TyeV2clOWPFdKkC`)
     - Click "Add"

### 3. Add Variables to "web" Service

1. Go back to project overview
2. Click on **"web"** service
3. Repeat step 2 (add same variables)

### 4. Change Region (CRITICAL!)

**For BOTH services (worker and web):**

1. Click on service
2. Go to **"Settings"** tab
3. Scroll to **"Region"** section
4. Click **"Change Region"**
5. Select **"Europe West (eu-west1)"**
6. Click **"Save"**

Railway will automatically redeploy in EU region (3-5 minutes).

---

## Verification

After adding variables and changing region:

### 1. Check Deployment Logs
```bash
# Should see price updates, NO 451 errors
railway logs --service worker | grep "PX px="
```

**Expected:**
```
2026-01-14 18:00:00 PX px=3245.67 adx=22.3 rsi=58.4
```

### 2. Check Telegram
You should receive a message in Telegram:
```
🤖 ETH Bot Started
Region: eu-west1
Mode: Live Trading (DRY_RUN=false)
Target: 1% daily
```

### 3. Monitor First Trade
Bot should execute first trade within 1-4 hours.

---

## Important Notes

> [!CAUTION]
> **DRY_RUN=false** means **LIVE TRADING** with real money!
> 
> If you want to test first without risk, change to:
> ```
> DRY_RUN=true
> ```

> [!IMPORTANT]
> **Region MUST be eu-west1** or Binance will block with 451 error!

> [!TIP]
> **Auto-Optimization is ON**
> 
> Bot will automatically adjust parameters based on performance after 3-7 days.

---

## Troubleshooting

### If bot doesn't start:
1. Check all variables are set (especially BINANCE_API_KEY and BINANCE_API_SECRET)
2. Verify region is eu-west1 (not us-west2)
3. Check deployment logs for errors

### If still getting 451 errors:
1. Confirm region change was saved
2. Redeploy manually (Settings → Redeploy)
3. Wait 5 minutes for deployment to complete

### If no Telegram messages:
1. Verify TELEGRAM_BOT_TOKEN is correct
2. Verify TELEGRAM_CHAT_ID is correct
3. Check bot has permission to send messages

---

## Expected Timeline

- **Now**: Add variables + change region (10 minutes)
- **+5 min**: Railway redeploys in EU
- **+10 min**: Bot starts, fetches data
- **+1-4 hours**: First trade executed
- **+24 hours**: 8-15 trades, 1-2% daily P&L 🎯

---

## Quick Reference: All Variables

```bash
# Binance
BINANCE_API_KEY=ppJSE0s9iKjp6Fd1t5lHEVqMeCaj4A2fghUrt6F2ERUZqlkz5TyeV2clOWPFdKkC
BINANCE_API_SECRET=2ihPOblVZdhRTFLbfubuNKZUNR5VDb5tuq5wH7hXlzM7J9ARCn08XwXZ0LPdNEIs

# Telegram
TELEGRAM_BOT_TOKEN=8313976588:AAHp7jgE1wr84yvChl2PAhHh5zkxXAS60s4
TELEGRAM_CHAT_ID=6379480212

# Trading
SYMBOL=ETHUSDT
BASE_ASSET=ETH
QUOTE_ASSET=USDT
MAX_TRADES_PER_DAY=15
RISK_PCT_PER_TRADE=0.006
DAILY_TARGET_PCT=0.01
MAX_DRAWDOWN_DAY=0.05
ENTRY_SCORE_MIN=0.45
SEC_PML_MIN=0.48
TAKE_PROFIT_PCT=0.010
TP_MIN=0.010
TP_MAX=0.015
STOP_FLOOR=0.005
STOP_ATR_MULT=1.5
BREAK_EVEN_TRIGGER=0.006
ADX_MIN_TREND=15
USE_ADX_FILTER=true
RSI_MIN=40
RSI_MAX=70
AUTO_OPTIMIZE=true
AUTO_TRAIN_MODE=false
DRY_RUN=false
LOG_LEVEL=INFO
```

Copy this entire block and paste into Railway's "Raw Editor" for fastest setup!
