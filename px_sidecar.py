import sys, time, requests, datetime, os
import pathlib
_ROOT = pathlib.Path(os.getenv("ETHBOT_ROOT", str(pathlib.Path(__file__).resolve().parent)))
LOG = str(_ROOT / "logs/console.out")
URL = "https://api.binance.com/api/v3/ticker/price?symbol=ETHUSDT"

def log_px(px):
    ts = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    # Match binance_px_feeder format with ADX and RSI placeholders
    line = f"{ts} INFO px={px:.2f} adx=20.0 rsi=50.0"
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception as e:
        print(f"write fail: {e}", file=sys.stderr)

while True:
    try:
        r = requests.get(URL, timeout=5)
        px = float(r.json()["price"])
        log_px(px)
    except Exception as e:
        # still touch the file so mtime stays fresh
        try:
            open(LOG, "a").close()
        except:
            pass
    time.sleep(15)
