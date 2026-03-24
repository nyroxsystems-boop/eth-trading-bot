#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, json, time, pathlib

ROOT = pathlib.Path(os.getenv("ETHBOT_ROOT", str(pathlib.Path(__file__).resolve().parent)))
CACHED = ROOT / "cache"
LOGD = ROOT / "logs"
CACHED.mkdir(parents=True, exist_ok=True)
LOGD.mkdir(parents=True, exist_ok=True)
LOG = LOGD / "reconcile.log"

def log(msg: str):
    LOG.open("a", encoding="utf-8").write(msg.rstrip()+"\n")

def main():
    key = os.getenv("BINANCE_KEY")
    sec = os.getenv("BINANCE_SECRET")
    if not key or not sec:
        log("skip: no api keys")
        # Trotzdem leere Strukturen schreiben, damit Downstream nicht crasht
        (CACHED / "binance_open_orders.json").write_text("[]")
        (CACHED / "binance_balances.json").write_text("{}")
        return 0

    # Placeholder: Wenn du schon nen Client hast, hier importieren & echte Daten ziehen.
    # Ich schreibe hier kompatible Null-Strukturen (kein Fehler), damit Timer sauber läuft.
    (CACHED / "binance_open_orders.json").write_text("[]")
    (CACHED / "binance_balances.json").write_text(json.dumps({"USDT": 0.0, "ETH": 0.0}))
    log("ok: wrote empty placeholders (wire real client later)")
    return 0

if __name__ == "__main__":
    try:
        exit(main())
    except Exception as e:
        try: log(f"err: {e}")
        except Exception: pass
        raise
