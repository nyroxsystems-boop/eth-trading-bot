# 📱 Daily Telegram Report - User Guide

## 🎯 What You Get

Every day at **00:00 UTC (01:00 CET)**, you'll receive a comprehensive performance report on Telegram!

---

## 📊 Report Format

```
📊 **Daily Performance Report**
━━━━━━━━━━━━━━━━━━━━
📅 Date: 2026-01-15
💰 P&L: +1.82% 🎯
📊 Trades: 12
🎲 Win Rate: 58.3%
📈 7-Day Avg: +1.45%
🎯 Target: 1.0%

🤖 **Auto-Optimization:**
⬇️ Reduced risk (overperforming)
New params saved.

━━━━━━━━━━━━━━━━━━━━
💡 Bot is running 24/7
Next report: Tomorrow 00:00 UTC
```

---

## 📈 What Each Metric Means

### 💰 P&L (Profit & Loss)
- **Your daily performance** in percentage
- **Emojis:**
  - 🎯 = Hit or exceeded 1% target
  - 📈 = Positive (but below target)
  - 📉 = Negative day

**Examples:**
- `+1.82% 🎯` = Great day! Above target
- `+0.65% 📈` = Profitable, but below 1%
- `-0.35% 📉` = Small loss (happens!)

### 📊 Trades
- **Number of trades executed** that day
- **Normal range:** 8-15 trades/day
- **Low trades (<5):** Market is ranging
- **High trades (>15):** Very volatile market

### 🎲 Win Rate
- **Percentage of profitable trades**
- **Target:** 52-58%
- **Calculation:** Wins / Total Closed Trades × 100

**Examples:**
- `58.3%` = Excellent! (7 wins out of 12 trades)
- `45.0%` = Below target (bot will adjust)
- `65.0%` = Very good! (bot will reduce risk)

### 📈 7-Day Average
- **Your average daily P&L** over the last 7 days
- **Shows consistency** of the bot
- **Target:** Around 1.0-1.5%

**Examples:**
- `+1.45%` = Very consistent!
- `+0.75%` = Needs optimization
- `+2.20%` = Overperforming (bot will reduce risk)

### 🎯 Target
- **Your daily profit goal** (default: 1.0%)
- Set via `DAILY_TARGET_PCT` environment variable

---

## 🤖 Auto-Optimization Actions

The bot automatically adjusts its parameters based on performance:

### ⬆️ Increased Aggression (Underperforming)
**When:** Daily P&L < 0.5% (half of target)

**What changes:**
- ✅ Position size +10% (bigger trades)
- ✅ ML threshold -5% (more trades)
- ✅ Risk per trade +5% (more aggressive)
- ✅ TP targets +5% (higher profit goals)

**Why:** Bot is too conservative, needs to take more opportunities

---

### ⬇️ Reduced Risk (Overperforming)
**When:** Daily P&L > 1.5% (150% of target)

**What changes:**
- ✅ Position size -5% (smaller trades)
- ✅ ML threshold +5% (fewer, better trades)
- ✅ Risk per trade -5% (more conservative)
- ✅ TP targets -5% (take profits faster)

**Why:** Bot is doing great, let's protect those gains!

---

### ✅ Maintaining Parameters (On Target)
**When:** Daily P&L between 0.8% and 1.2%

**What changes:**
- ✅ Nothing! Keep doing what works

**Why:** Performance is perfect, don't fix what isn't broken

---

### 🔄 Minor Adjustments
**When:** Daily P&L between 0.5% and 1.5% (but not perfectly on target)

**What changes:**
- ✅ Small tweaks to parameters
- ✅ Fine-tuning for consistency

**Why:** Close to target, just needs small adjustments

---

## 📅 When You'll Receive Reports

### Timing
- **Every day at 00:00 UTC**
- **01:00 CET (Central European Time)**
- **02:00 CEST (Summer Time)**

### First Report
- **Tomorrow morning** at 01:00 CET
- After the bot has traded for a full day

### What if I miss it?
- Check your Telegram chat history
- Reports are sent once per day
- You can also check Railway logs

---

## 🔍 Example Scenarios

### Scenario 1: Great Day! 🎉
```
📊 Daily Performance Report
━━━━━━━━━━━━━━━━━━━━
📅 Date: 2026-01-15
💰 P&L: +2.15% 🎯
📊 Trades: 14
🎲 Win Rate: 64.3%
📈 7-Day Avg: +1.65%
🎯 Target: 1.0%

🤖 Auto-Optimization:
⬇️ Reduced risk (overperforming)
New params saved.
```

**What this means:**
- ✅ Exceeded target by 115%!
- ✅ 14 trades executed
- ✅ 64% win rate (9 wins, 5 losses)
- ✅ 7-day average is strong
- 🤖 Bot will reduce risk to protect gains

---

### Scenario 2: Slow Day 😐
```
📊 Daily Performance Report
━━━━━━━━━━━━━━━━━━━━
📅 Date: 2026-01-16
💰 P&L: +0.45% 📈
📊 Trades: 6
🎲 Win Rate: 50.0%
📈 7-Day Avg: +1.25%
🎯 Target: 1.0%

🤖 Auto-Optimization:
⬆️ Increased aggression (underperforming)
New params saved.
```

**What this means:**
- ⚠️ Below target (only 0.45%)
- ⚠️ Only 6 trades (market was ranging)
- ⚠️ 50% win rate (3 wins, 3 losses)
- ✅ 7-day average still good
- 🤖 Bot will increase aggression tomorrow

---

### Scenario 3: Perfect Day! 🎯
```
📊 Daily Performance Report
━━━━━━━━━━━━━━━━━━━━
📅 Date: 2026-01-17
💰 P&L: +1.05% 🎯
📊 Trades: 11
🎲 Win Rate: 54.5%
📈 7-Day Avg: +1.15%
🎯 Target: 1.0%

🤖 Auto-Optimization:
✅ Maintaining parameters (on target)
New params saved.
```

**What this means:**
- ✅ Right on target!
- ✅ 11 trades (good activity)
- ✅ 55% win rate (6 wins, 5 losses)
- ✅ 7-day average consistent
- 🤖 Bot keeps current settings

---

## 🛠️ Troubleshooting

### I didn't receive a report
**Possible reasons:**
1. **First day:** Bot needs 24h of data
2. **Telegram issue:** Check bot token/chat ID
3. **Bot not running:** Check Railway logs

**Solution:**
- Check Railway logs for `[TELEGRAM] Daily report sent successfully`
- Verify `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are correct
- Make sure bot is running

### Report shows 0 trades
**Possible reasons:**
1. **Market is ranging:** No clear trends
2. **Bot is in cooldown:** After losses
3. **Daily target reached:** Bot stopped trading

**Solution:**
- This is normal! Bot waits for good opportunities
- Check next day's report
- Bot will resume when conditions improve

### Win rate is low (<45%)
**Possible reasons:**
1. **Market conditions:** Choppy/ranging market
2. **Learning phase:** Bot is still optimizing
3. **Bad luck:** Short-term variance

**Solution:**
- Auto-optimizer will adjust parameters
- Give it 3-7 days to optimize
- Check 7-day average (more important than single day)

---

## 📊 Reading the Trend

### Week 1: Learning Phase
```
Day 1: +0.50% 📈 (learning)
Day 2: +0.75% 📈 (improving)
Day 3: +1.20% 🎯 (getting there!)
Day 4: +1.50% 🎯 (nice!)
Day 5: +1.80% 🎯 (great!)
Day 6: +2.10% 🎯 (too good, reducing risk)
Day 7: +1.60% 🎯 (stable)

Week 1 Total: +10.45% 🔥
```

### Week 2: Optimization Phase
```
Day 8:  +1.70% 🎯
Day 9:  +1.90% 🎯
Day 10: +1.50% 🎯
Day 11: +2.00% 🎯
Day 12: +1.80% 🎯
Day 13: +1.60% 🎯
Day 14: +1.70% 🎯

Week 2 Total: +12.20% 🚀
```

### Week 3+: Mature Phase
```
Consistent 1.5-2.0% daily
Win rate stable at 55-60%
7-day average: +1.7%
Bot is fully optimized! ✅
```

---

## 🎯 What to Expect

### First Week
- **Daily P&L:** 0.5-1.5%
- **Win Rate:** 45-55%
- **Trades/Day:** 5-12
- **Status:** Learning & Optimizing

### Second Week
- **Daily P&L:** 1.0-2.0%
- **Win Rate:** 50-58%
- **Trades/Day:** 8-15
- **Status:** Optimized & Consistent

### Third Week+
- **Daily P&L:** 1.5-2.5%
- **Win Rate:** 52-60%
- **Trades/Day:** 10-15
- **Status:** Mature & Profitable

---

## 💡 Pro Tips

### 1. Don't Panic on Bad Days
- ❌ One bad day doesn't mean bot is broken
- ✅ Look at 7-day average instead
- ✅ Auto-optimizer will adjust

### 2. Trust the Process
- ❌ Don't manually change parameters
- ✅ Let auto-optimizer do its job
- ✅ Give it at least 1 week

### 3. Monitor Trends, Not Days
- ❌ Don't obsess over daily P&L
- ✅ Watch 7-day average
- ✅ Look for consistency

### 4. Celebrate Consistency
- ❌ Don't chase 5% days
- ✅ Aim for consistent 1-2% daily
- ✅ Compound growth is king!

---

## 📞 Need Help?

**If you see:**
- ❌ Negative P&L for 3+ days in a row
- ❌ Win rate below 40% consistently
- ❌ 7-day average below 0.5%

**Check:**
1. Railway logs for errors
2. Binance API permissions
3. Market conditions (is crypto crashing?)

**Remember:**
- Bot can't make money in all market conditions
- Ranging markets = fewer opportunities
- Trending markets = more profits

---

## 🎉 Success Metrics

**You're doing GREAT if:**
- ✅ 7-day average > 1.0%
- ✅ Win rate > 50%
- ✅ Consistent daily reports
- ✅ Auto-optimizer making adjustments

**You're doing AMAZING if:**
- 🔥 7-day average > 1.5%
- 🔥 Win rate > 55%
- 🔥 Monthly growth > 40%
- 🔥 Bot running 24/7 without issues

---

**Your first report arrives tomorrow at 01:00 CET!** 🎯

Check your Telegram and see how the bot performed! 📱💰
