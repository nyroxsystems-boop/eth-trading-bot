#!/usr/bin/env python3
# Berechnet dynamische SL/TP Levels; Ausgabe nur als Hilfswerte (kannst du im Bot nutzen)
import os, json
entry = float(os.getenv("ENTRY_PRICE","0"))
sl_pct = float(os.getenv("STOP_LOSS_PCT","0.0075"))   # 0.75%
tp_pct = float(os.getenv("TAKE_PROFIT_PCT","0.0150"))  # 1.5%
sl = entry * (1 - sl_pct)
tp = entry * (1 + tp_pct)
print(json.dumps({"entry":entry,"sl":sl,"tp":tp,"sl_pct":sl_pct,"tp_pct":tp_pct}))
