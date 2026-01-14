# Railway Region Fix for Binance 451 Error

## Problem
Binance.com blocks all US IP addresses with **451 Unavailable For Legal Reasons** error.

Current Railway deployment is in `us-west2` region.

## Solution
Change Railway deployment region to Europe or Asia.

## Steps to Fix

### Option 1: Railway Dashboard (Recommended)

1. Go to Railway Dashboard: https://railway.com/project/c6bf66ba-9f5d-432a-ba69-fdaf43494a7a
2. Click on the **worker** service
3. Go to **Settings** tab
4. Scroll to **Region** section
5. Change from `us-west2` to **`eu-west1`** (Europe - Belgium)
   - Alternative: `ap-southeast1` (Singapore)
6. Click **Save**
7. Railway will automatically redeploy

### Option 2: Railway CLI

```bash
# Install Railway CLI if not installed
npm i -g @railway/cli

# Login
railway login

# Link to project
railway link c6bf66ba-9f5d-432a-ba69-fdaf43494a7a

# Change region
railway service --region eu-west1

# Redeploy
railway up
```

### Option 3: railway.json Configuration

Add to `railway.json`:

```json
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": {
    "builder": "DOCKERFILE"
  },
  "deploy": {
    "region": "eu-west1",
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 3
  }
}
```

Then commit and push:
```bash
git add railway.json
git commit -m "fix: change region to EU to avoid Binance 451 error"
git push
```

## Verification

After redeployment, check logs for successful API calls:

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

## Available Regions

| Region | Location | Latency to Binance |
|--------|----------|-------------------|
| `us-west2` | USA (Oregon) | ❌ BLOCKED |
| `eu-west1` | Belgium | ✅ ~20ms |
| `eu-central1` | Germany | ✅ ~25ms |
| `ap-southeast1` | Singapore | ✅ ~5ms (BEST) |
| `ap-northeast1` | Japan | ✅ ~10ms |

**Recommendation**: `eu-west1` (Europe) or `ap-southeast1` (Singapore)

## Post-Fix Checklist

- [ ] Railway region changed to EU/Asia
- [ ] Bot redeployed successfully
- [ ] Logs show price updates (no 451 errors)
- [ ] First trade executed within 24h
- [ ] Dashboard shows live data
