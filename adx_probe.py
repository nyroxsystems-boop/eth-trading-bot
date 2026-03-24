import re, pandas as pd
from pathlib import Path
from datetime import datetime, timedelta, timezone
from ta.trend import ADXIndicator

def compute_adx_safe(ohlc: pd.DataFrame):
    n = len(ohlc)
    if n < 3:
        return float("nan"), None
    # versuche Fenster von min(14, n-1) abwärts bis 3
    start = max(3, min(14, n - 1))
    for w in range(start, 2, -1):
        try:
            adx = ADXIndicator(ohlc["high"], ohlc["low"], ohlc["close"], window=w).adx().dropna()
            if not adx.empty:
                return float(adx.iloc[-1]), w
        except Exception:
            continue
    return float("nan"), None

_ROOT = Path(os.getenv("ETHBOT_ROOT", str(Path(__file__).resolve().parent)))
path = _ROOT / "logs" / "console.out"
lines = path.read_bytes().decode("utf-8","ignore").splitlines()[-20000:]

rows = []
rx_ts = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*?\bpx=([0-9]+(?:\.[0-9]+)?)")
rx_px = re.compile(r"\bpx=([0-9]+(?:\.[0-9]+)?)")

for ln in lines:
    m = rx_ts.search(ln)
    if m:
        ts = datetime.fromisoformat(m.group(1))
        rows.append((ts, float(m.group(2))))
        continue
    m2 = rx_px.search(ln)
    if m2:
        rows.append((None, float(m2.group(1))))

if len(rows) < 3:
    print("zu wenig Ticks:", len(rows))
    raise SystemExit(2)

# fehlende Timestamps auffüllen (1s-Abstand)
if all(ts is None for ts,_ in rows):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    rows = [(now - timedelta(seconds=len(rows)-i), px) for i, (_, px) in enumerate(rows)]
else:
    last_ts = None
    for i,(ts,px) in enumerate(rows):
        if ts is None:
            rows[i] = ((last_ts + timedelta(seconds=1)) if last_ts else datetime.now(timezone.utc).replace(tzinfo=None), px)
        last_ts = rows[i][0]

df = pd.DataFrame(rows, columns=["ts","price"]).sort_values("ts").set_index("ts")

# wähle die feinste Rule, die >=14 Kerzen ergibt
for rule in ("15s","30s","1min"):
    o = df["price"].resample(rule).first()
    h = df["price"].resample(rule).max()
    l = df["price"].resample(rule).min()
    c = df["price"].resample(rule).last()
    ohlc = pd.DataFrame({"open":o,"high":h,"low":l,"close":c}).dropna()
    if len(ohlc) >= 14:
        last_adx, win = compute_adx_safe(ohlc)
        print(f"candles={len(ohlc)} rule={rule} window={win if win else 'NA'} last_adx={last_adx if last_adx==last_adx else 'NaN'}")
        print(ohlc.tail(4).to_string())
        break
else:
    # keine Rule erreicht 14 Kerzen → zeig, was da ist
    last_adx, win = compute_adx_safe(ohlc)  # ohlc aus letzter Schleife
    print(f"zu wenig Candles: {len(ohlc)} (rule={rule}) window={win if win else 'NA'} last_adx={last_adx if last_adx==last_adx else 'NaN'}")
    print(ohlc.tail(4).to_string())
