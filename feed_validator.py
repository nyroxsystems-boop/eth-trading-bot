#!/usr/bin/env python3
import sys, time, re
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path("/root/ethbot")
LOGD = ROOT / "logs"
LOGD.mkdir(parents=True, exist_ok=True)
CONSOLE = LOGD / "console.out"
MAINLOG  = LOGD / "ethbot.log"
FEEDLOG  = LOGD / "feed.log"

def append_log(line: str):
    try:
        with FEEDLOG.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass

def now_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

def fail(code, reason):
    msg = f"{now_utc()} ✖ FAIL[{code}] {reason}"
    append_log(msg)
    print(reason, file=sys.stderr)
    sys.exit(code)

def ok(msg):
    line = f"{now_utc()} ✔ OK {msg}"
    append_log(line)
    print(msg)
    sys.exit(0)

# 1) console.out existiert & ist frisch
if not CONSOLE.exists():
    fail(10, "console.out fehlt")

age = time.time() - CONSOLE.stat().st_mtime
if age > 180:
    fail(11, f"console.out stale: {int(age)}s alt")

# 2) In den letzten Zeilen muss 'px=' vorkommen (binär-tolerant)
tail_b = b"\n".join(CONSOLE.read_bytes().splitlines()[-800:])
text = tail_b.decode("utf-8", "ignore")
if not re.search(r"\bpx=\d", text):
    fail(12, "keine px= Ticks im Console-Stream")

# 3) ADX Soft-Block nur WARN (keine Exit-Änderung)
if MAINLOG.exists():
    t2_b = b"\n".join(MAINLOG.read_bytes().splitlines()[-4000:])
    t2   = t2_b.decode("utf-8", "ignore")
    soft = len(re.findall(r"regime soft-block \| adx=0\.0", t2))
    if soft >= 20:
        append_log(f"{now_utc()} ⚠ WARN ADX=0.0 soft-block häufig ({soft} hits in last chunk)")

ok("Feed aktiv (console frisch, px=TICKS gefunden)")
