#!/usr/bin/env python3
"""
ethbot → Obsidian Bridge

Reads today's trades from logs/trades.csv, computes stats,
and injects/updates a "🤖 Bot Report" section inside the
matching Daily Note (02_Areas/Daily/YYYY-MM-DD.md) in the
Obsidian Vault.

Idempotent: re-running the script replaces the existing
Bot Report section instead of duplicating it.

Usage:
    python3 tools/obsidian_daily_report.py \
        --vault /path/to/ObsidianVault \
        [--date 2026-04-24] \
        [--logs-dir ./logs]

Env vars (used when CLI flags are omitted):
    OBSIDIAN_VAULT_PATH
    ETHBOT_LOGS_DIR
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ═══════════════════════════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════════════════════════

SECTION_START = "<!-- ethbot:report:start -->"
SECTION_END = "<!-- ethbot:report:end -->"
DAILY_SUBDIR = "02_Areas/Daily"
DAILY_TEMPLATE = """---
type: daily
created: {date_iso}
tags: [daily]
---

# {date_iso}

## Fokus heute

-

## Log

-

## Learnings

-

## Tomorrow

-
"""


# ═══════════════════════════════════════════════════════════════════
#  TRADE STATS
# ═══════════════════════════════════════════════════════════════════

@dataclass
class TradeStats:
    date_iso: str
    total_trades: int
    buys: int
    sells: int
    total_pnl: float
    realized_pnl: float  # sum over SELLs only
    winning_sells: int
    losing_sells: int
    best_trade: Optional[Tuple[str, float]]  # (pair, pnl)
    worst_trade: Optional[Tuple[str, float]]
    pairs_traded: List[str]
    open_positions: Dict[str, float]  # pair -> net_qty (positive = long exposure)

    @property
    def win_rate(self) -> float:
        closed = self.winning_sells + self.losing_sells
        return (self.winning_sells / closed * 100) if closed else 0.0


def load_trades(logs_dir: Path) -> List[dict]:
    """Read trades.csv into memory as list of dicts."""
    csv_path = logs_dir / "trades.csv"
    if not csv_path.exists():
        return []
    with csv_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def compute_stats(trades: List[dict], target_date: str) -> TradeStats:
    """Compute stats for a given ISO date (YYYY-MM-DD)."""
    todays: List[dict] = []
    all_up_to_today: List[dict] = []
    for t in trades:
        ts = t.get("timestamp", "")
        if not ts:
            continue
        # timestamps look like "2026-04-18 10:02:12"
        trade_date = ts.split(" ", 1)[0]
        if trade_date <= target_date:
            all_up_to_today.append(t)
        if trade_date == target_date:
            todays.append(t)

    # Compute open positions from ALL trades up to and including today.
    # net_qty > 0 means we're currently long that pair.
    net_qty: Dict[str, float] = defaultdict(float)
    for t in all_up_to_today:
        qty = _to_float(t.get("qty", 0))
        action = (t.get("action") or "").upper()
        pair = t.get("pair", "?")
        if action == "BUY":
            net_qty[pair] += qty
        elif action == "SELL":
            net_qty[pair] -= qty
    open_positions = {p: q for p, q in net_qty.items() if q > 1e-9}

    # Today-only aggregates.
    buys = sum(1 for t in todays if t.get("action", "").upper() == "BUY")
    sells = sum(1 for t in todays if t.get("action", "").upper() == "SELL")

    realized_pnl = 0.0
    winning_sells = 0
    losing_sells = 0
    best: Optional[Tuple[str, float]] = None
    worst: Optional[Tuple[str, float]] = None

    for t in todays:
        action = (t.get("action") or "").upper()
        if action != "SELL":
            continue
        pnl = _to_float(t.get("pnl", 0))
        realized_pnl += pnl
        if pnl > 0:
            winning_sells += 1
        elif pnl < 0:
            losing_sells += 1
        pair = t.get("pair", "?")
        if best is None or pnl > best[1]:
            best = (pair, pnl)
        if worst is None or pnl < worst[1]:
            worst = (pair, pnl)

    total_pnl = sum(_to_float(t.get("pnl", 0)) for t in todays)
    pairs_traded = sorted({t.get("pair", "?") for t in todays})

    return TradeStats(
        date_iso=target_date,
        total_trades=len(todays),
        buys=buys,
        sells=sells,
        total_pnl=total_pnl,
        realized_pnl=realized_pnl,
        winning_sells=winning_sells,
        losing_sells=losing_sells,
        best_trade=best,
        worst_trade=worst,
        pairs_traded=pairs_traded,
        open_positions=open_positions,
    )


def _to_float(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


# ═══════════════════════════════════════════════════════════════════
#  MARKDOWN RENDERING
# ═══════════════════════════════════════════════════════════════════

def render_section(stats: TradeStats) -> str:
    """Render the Bot Report markdown block (between sentinels)."""
    lines = [
        SECTION_START,
        "",
        "## 🤖 Bot Report",
        "",
        f"_auto-generated {datetime.now():%Y-%m-%d %H:%M} · [[ethbot]]_",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Trades heute | {stats.total_trades} (BUY: {stats.buys}, SELL: {stats.sells}) |",
        f"| Realized PnL (SELLs heute) | **${stats.realized_pnl:+.2f}** |",
        f"| Win-Rate | {stats.win_rate:.1f}% ({stats.winning_sells}W / {stats.losing_sells}L) |",
    ]
    if stats.best_trade:
        lines.append(f"| Best Trade | {stats.best_trade[0]} `${stats.best_trade[1]:+.2f}` |")
    if stats.worst_trade:
        lines.append(f"| Worst Trade | {stats.worst_trade[0]} `${stats.worst_trade[1]:+.2f}` |")
    if stats.pairs_traded:
        lines.append(f"| Pairs | {', '.join(stats.pairs_traded)} |")

    lines.append("")

    if stats.open_positions:
        lines.append("### 📌 Open Positions (Stand heute)")
        lines.append("")
        for pair, qty in sorted(stats.open_positions.items()):
            lines.append(f"- **{pair}** — qty {qty:.6f}")
        lines.append("")
    else:
        lines.append("_Keine offenen Positionen._")
        lines.append("")

    lines.append(SECTION_END)
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════
#  DAILY NOTE I/O
# ═══════════════════════════════════════════════════════════════════

def ensure_daily_note(vault: Path, target_date: str) -> Path:
    """Create the daily note from template if it doesn't exist. Return path."""
    daily_dir = vault / DAILY_SUBDIR
    daily_dir.mkdir(parents=True, exist_ok=True)
    note_path = daily_dir / f"{target_date}.md"
    if not note_path.exists():
        note_path.write_text(
            DAILY_TEMPLATE.format(date_iso=target_date),
            encoding="utf-8",
        )
    return note_path


def upsert_bot_report(note_path: Path, new_section: str) -> str:
    """Insert or replace the bot report section inside the daily note.

    Returns 'inserted' or 'replaced'.
    """
    content = note_path.read_text(encoding="utf-8")

    if SECTION_START in content and SECTION_END in content:
        start = content.index(SECTION_START)
        end = content.index(SECTION_END) + len(SECTION_END)
        updated = content[:start] + new_section + content[end:]
        note_path.write_text(updated, encoding="utf-8")
        return "replaced"

    # Append at end with separator.
    sep = "\n\n---\n\n" if not content.endswith("\n") else "\n---\n\n"
    note_path.write_text(content + sep + new_section + "\n", encoding="utf-8")
    return "inserted"


# ═══════════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="ethbot → Obsidian daily report")
    parser.add_argument(
        "--vault",
        default=os.getenv("OBSIDIAN_VAULT_PATH"),
        help="Path to Obsidian Vault (or set OBSIDIAN_VAULT_PATH)",
    )
    parser.add_argument(
        "--logs-dir",
        default=os.getenv("ETHBOT_LOGS_DIR", "logs"),
        help="Path to ethbot logs dir (default: ./logs)",
    )
    parser.add_argument(
        "--date",
        default=date.today().isoformat(),
        help="ISO date YYYY-MM-DD (default: today)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be written without touching files",
    )
    args = parser.parse_args()

    if not args.vault:
        sys.exit(
            "ERROR: --vault not provided and OBSIDIAN_VAULT_PATH env var not set."
        )

    vault = Path(args.vault).expanduser().resolve()
    if not vault.is_dir():
        sys.exit(f"ERROR: vault path is not a directory: {vault}")

    logs_dir = Path(args.logs_dir).expanduser().resolve()

    trades = load_trades(logs_dir)
    stats = compute_stats(trades, args.date)
    section = render_section(stats)

    if args.dry_run:
        print(f"# Would write to: {vault / DAILY_SUBDIR / f'{args.date}.md'}")
        print(section)
        return

    note_path = ensure_daily_note(vault, args.date)
    action = upsert_bot_report(note_path, section)

    print(f"✅ {action.upper()} bot report in {note_path}")
    print(f"   Trades today: {stats.total_trades} | Realized PnL: ${stats.realized_pnl:+.2f}")
    if stats.open_positions:
        print(f"   Open positions: {len(stats.open_positions)} ({', '.join(stats.open_positions)})")


if __name__ == "__main__":
    main()
