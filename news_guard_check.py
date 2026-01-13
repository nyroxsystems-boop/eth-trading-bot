#!/usr/bin/env python3
import os, sys
if os.getenv("NEWS_ALERT", "0") == "1":
    print("[NEWS] BLOCK NEWS_ALERT=1")
    sys.exit(2)
print("[NEWS] ok")
sys.exit(0)
