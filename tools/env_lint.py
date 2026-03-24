#!/usr/bin/env python3
import os, sys, stat, re
import pathlib
envf = str(pathlib.Path(os.getenv("ETHBOT_ROOT", str(pathlib.Path(__file__).resolve().parent.parent))) / ".env.bot")

def out(x): print(x, flush=True)

if not os.path.exists(envf):
    out(f"[ENV] missing: {envf}"); sys.exit(0)

st = os.stat(envf)
if (st.st_mode & stat.S_IRWXG) or (st.st_mode & stat.S_IRWXO):
    out("[ENV] warn: permissions too open (expect 600)")

txt = open(envf, "r", encoding="utf-8", errors="ignore").read()
def has_key(k): return re.search(rf"^{re.escape(k)}=", txt, flags=re.M) is not None

must = ["DRY_RUN","MAX_TRADES","FOCUS_MODE"]
missing = [k for k in must if not has_key(k)]
if missing:
    out("[ENV] warn: missing keys: " + ",".join(missing))

out("[ENV] ok: present; basic lint done.")
