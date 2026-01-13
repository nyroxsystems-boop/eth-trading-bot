#!/usr/bin/env python3
import subprocess, textwrap, os
from tools.notify import send
out = subprocess.run(["/root/ethbot/.venv/bin/python3","/root/ethbot/summary_48h.py"], capture_output=True, text=True)
msg = out.stdout.strip() or "(no summary)"
send("📊 <b>48h Summary</b>\n"+msg[:3800])  # safe length
