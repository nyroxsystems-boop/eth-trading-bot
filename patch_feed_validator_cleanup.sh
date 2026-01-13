#!/usr/bin/env bash
set -e

TARGET="/root/ethbot/feed_validator.py"
TS=$(date +%F_%H%M%S)
cp -a "$TARGET" "$TARGET.bak.$TS"

# Patch einfügen
python3 - <<'PY'
from pathlib import Path
p = Path("/root/ethbot/feed_validator.py")
txt = p.read_text().splitlines()
out = []
for line in txt:
    # alte Spam-Zeilen entfernen
    if "Feed stale: status=" in line:
        continue
    # Bedingung anpassen: nur warnen, wenn zu alt
    if "bot_send" in line and "stale" in line:
        line = "        if diff > threshold:\n            bot_send(f'⚠️ Feed stale! diff={diff}s > {threshold}s')"
    out.append(line)
p.write_text("\n".join(out))
print("✅ Feed Validator: Spam deaktiviert, nur Warnungen bleiben aktiv.")
PY

systemctl restart ethbot
echo "🔁 Service neu gestartet – keine 'status=ok'-Spam-Meldungen mehr!"
