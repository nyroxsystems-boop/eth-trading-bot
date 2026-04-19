from __future__ import annotations
"""
ML Feature Collector — Records every signal evaluation for ML training.

Every time the bot evaluates a pair (buy or skip), we log:
- All indicator values (features)
- The bot's decision (buy/skip)
- The OUTCOME (did price go up/down in next 5/15/30 candles?)

This builds the training dataset for the ML predictor.
The outcome is filled in RETROACTIVELY once we know what happened.
"""
import csv
import json
import os
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("ethbot.ml_collector")

FEATURE_DIR = Path(os.getenv("LOG_DIR", "./logs")) / "ml_features"
FEATURE_DIR.mkdir(parents=True, exist_ok=True)

# Feature columns we record per evaluation
FEATURE_COLS = [
    "timestamp",
    "pair",
    "price",
    # Technical indicators
    "rsi14",
    "adx14",
    "atr",
    "atr_pct",
    "ema20",
    "ema50",
    "macd",
    "macd_sig",
    "bb_lo",
    "bb_hi",
    "volume_ratio",
    "vwap",
    "vwap_dev",
    # Signal scores
    "score",
    "signal_count",
    "signals_str",
    # Market intelligence
    "fg_value",
    "fg_signal",
    "news_sentiment",
    "funding_rate",
    "oi_signal",
    "intel_composite",
    # Multi-timeframe
    "mtf_boost",
    # Regime
    "regime",
    # Decision
    "action",  # "BUY" or "SKIP"
    # Outcome (filled retroactively)
    "outcome_5",   # Price change after 5 candles (%)
    "outcome_15",  # Price change after 15 candles (%)
    "outcome_30",  # Price change after 30 candles (%)
    "outcome_label",  # 1 = profitable trade, 0 = not
]


def _get_csv_path(pair: str) -> Path:
    """Get CSV path for a specific pair."""
    return FEATURE_DIR / f"features_{pair}.csv"


def _ensure_header(pair: str):
    """Create CSV with header if it doesn't exist."""
    path = _get_csv_path(pair)
    if not path.exists() or path.stat().st_size == 0:
        with open(path, "w", newline="") as f:
            csv.writer(f).writerow(FEATURE_COLS)


def record_evaluation(
    pair: str,
    df,  # pandas DataFrame with indicators
    signal,  # Signal dataclass
    intel_data: dict | None = None,
    mtf_boost: float = 0.0,
    action: str = "SKIP",
):
    """
    Record a complete feature snapshot for ML training.
    Called on EVERY evaluation, not just buys.
    """
    try:
        _ensure_header(pair)
        row = df.iloc[-1]

        # Build feature dict
        features = {
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            "pair": pair,
            "price": round(float(row["close"]), 4),
            # Technical
            "rsi14": round(float(row.get("rsi14", 50)), 2),
            "adx14": round(float(row.get("adx14", 25)), 2),
            "atr": round(float(row.get("atr", 0)), 4),
            "atr_pct": round(signal.atr_pct, 6) if signal else 0,
            "ema20": round(float(row.get("ema20", 0)), 4),
            "ema50": round(float(row.get("ema50", 0)), 4),
            "macd": round(float(row.get("macd", 0)), 6),
            "macd_sig": round(float(row.get("macd_sig", 0)), 6),
            "bb_lo": round(float(row.get("bb_lo", 0)), 4),
            "bb_hi": round(float(row.get("bb_hi", 0)), 4),
            "volume_ratio": round(float(row.get("volume_ratio", 1)), 4),
            "vwap": round(float(row.get("vwap", 0)), 4),
            "vwap_dev": round(float(row.get("vwap_dev", 0)), 6),
            # Scores
            "score": round(signal.score, 4) if signal else 0,
            "signal_count": len(signal.signals) if signal else 0,
            "signals_str": "|".join(signal.signals) if signal else "",
            # Intel
            "fg_value": intel_data.get("fear_greed", {}).get("value", 50) if intel_data else 50,
            "fg_signal": intel_data.get("fear_greed", {}).get("signal", 0) if intel_data else 0,
            "news_sentiment": intel_data.get("news_sentiment", {}).get("signal", 0) if intel_data else 0,
            "funding_rate": intel_data.get("funding_rate", {}).get("rate", 0) if intel_data else 0,
            "oi_signal": intel_data.get("open_interest", {}).get("signal", 0) if intel_data else 0,
            "intel_composite": 0,  # Filled by caller
            # MTF
            "mtf_boost": round(mtf_boost, 4),
            # Regime
            "regime": signal.regime if signal else "unknown",
            # Decision
            "action": action,
            # Outcomes (filled later)
            "outcome_5": "",
            "outcome_15": "",
            "outcome_30": "",
            "outcome_label": "",
        }

        path = _get_csv_path(pair)
        with open(path, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FEATURE_COLS)
            writer.writerow(features)

    except Exception as e:
        logger.warning(f"ML collector error ({pair}): {e}")


def backfill_outcomes(pair: str):
    """
    Fill in outcome columns using Triple-Barrier Method (López de Prado).

    CRITICAL FIX: Previous implementation had look-ahead bias.
    Now uses Triple-Barrier:
      Label = +1 if TP (1.0%) hit first
      Label = -1 if SL (0.7%) hit first
      Label =  0 if timeout (30 candles) without either

    The key: we walk forward from the evaluation candle and check
    which barrier is touched FIRST, simulating real-time execution.
    """
    try:
        from bot.executor import fetch_klines

        path = _get_csv_path(pair)
        if not path.exists():
            return

        # Read all rows
        rows = []
        with open(path, "r") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        if not rows:
            return

        # Get recent klines for price lookup
        df = fetch_klines(pair, "5m", lookback=200)
        if df is None or len(df) < 30:
            return

        prices = df["close"].values.tolist()
        highs = df["high"].values.tolist() if "high" in df.columns else prices
        lows = df["low"].values.tolist() if "low" in df.columns else prices

        updated = 0
        for row in rows:
            # Skip if already filled
            if row.get("outcome_5"):
                continue

            entry_price = float(row.get("price", 0))
            if entry_price <= 0:
                continue

            # Find how many candles ago this evaluation was
            ts = row.get("timestamp", "")
            if not ts:
                continue

            try:
                eval_time = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                age_minutes = (datetime.now(timezone.utc) - eval_time).total_seconds() / 60
            except Exception:
                continue

            if age_minutes < 150:  # Need at least 30 candles (150 min at 5m)
                continue

            candles_ago = int(age_minutes / 5)
            idx_now = len(prices) - 1
            idx_entry = max(0, idx_now - candles_ago)

            if candles_ago < 30 or idx_entry + 30 > idx_now:
                continue

            # ── TRIPLE BARRIER METHOD ──
            # Walk forward from entry candle and check barriers
            tp_pct = 1.0    # Take-profit: +1.0%
            sl_pct = 0.7    # Stop-loss: -0.7%
            max_bars = 30   # Timeout: 30 candles

            tp_price = entry_price * (1 + tp_pct / 100)
            sl_price = entry_price * (1 - sl_pct / 100)

            barrier_hit = 0  # 0=timeout, 1=TP, -1=SL
            exit_bar = max_bars
            exit_price = prices[min(idx_entry + max_bars, idx_now)]

            for bar in range(1, max_bars + 1):
                idx = idx_entry + bar
                if idx > idx_now:
                    break

                bar_high = highs[idx] if idx < len(highs) else prices[idx]
                bar_low = lows[idx] if idx < len(lows) else prices[idx]

                # Check SL first (conservative — if both hit same bar, SL wins)
                if bar_low <= sl_price:
                    barrier_hit = -1
                    exit_bar = bar
                    exit_price = sl_price
                    break
                elif bar_high >= tp_price:
                    barrier_hit = 1
                    exit_bar = bar
                    exit_price = tp_price
                    break

            # Record outcomes
            pnl_pct = ((exit_price / entry_price) - 1) * 100

            # Also record raw price changes at fixed intervals
            p5 = prices[min(idx_entry + 5, idx_now)]
            p15 = prices[min(idx_entry + 15, idx_now)]
            p30 = prices[min(idx_entry + 30, idx_now)]

            row["outcome_5"] = f"{((p5 / entry_price) - 1) * 100:.4f}"
            row["outcome_15"] = f"{((p15 / entry_price) - 1) * 100:.4f}"
            row["outcome_30"] = f"{((p30 / entry_price) - 1) * 100:.4f}"

            # Triple-Barrier Label:
            # 1 = TP hit first (profitable), 0 = SL hit first or timeout
            row["outcome_label"] = "1" if barrier_hit == 1 else "0"
            updated += 1

        if updated > 0:
            # Write back
            with open(path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=FEATURE_COLS)
                writer.writeheader()
                writer.writerows(rows)
            logger.info(f"ML backfill [{pair}]: {updated} rows labeled (Triple-Barrier)")

    except Exception as e:
        logger.warning(f"ML backfill error ({pair}): {e}")


def get_training_data(pair: str = None) -> list:
    """
    Load labeled training data from all pairs (or specific pair).
    Returns list of dicts with features + outcome labels.
    """
    rows = []
    if pair:
        pairs = [pair]
    else:
        pairs = [f.stem.replace("features_", "") for f in FEATURE_DIR.glob("features_*.csv")]

    for p in pairs:
        path = _get_csv_path(p)
        if not path.exists():
            continue
        try:
            with open(path, "r") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get("outcome_label"):  # Only labeled rows
                        rows.append(row)
        except Exception:
            continue

    return rows


def get_stats() -> dict:
    """Get stats about collected training data."""
    stats = {}
    total = 0
    labeled = 0
    buys = 0

    for f in FEATURE_DIR.glob("features_*.csv"):
        pair = f.stem.replace("features_", "")
        try:
            with open(f, "r") as fh:
                reader = csv.DictReader(fh)
                rows = list(reader)
                pair_total = len(rows)
                pair_labeled = sum(1 for r in rows if r.get("outcome_label"))
                pair_buys = sum(1 for r in rows if r.get("action") == "BUY")
                stats[pair] = {
                    "total": pair_total,
                    "labeled": pair_labeled,
                    "buys": pair_buys,
                    "skips": pair_total - pair_buys,
                }
                total += pair_total
                labeled += pair_labeled
                buys += pair_buys
        except Exception:
            continue

    return {
        "pairs": stats,
        "total_evaluations": total,
        "total_labeled": labeled,
        "total_buys": buys,
        "total_skips": total - buys,
        "ready_for_training": labeled >= 100,
    }
