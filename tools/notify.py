#!/usr/bin/env python3
import os, sys, json, urllib.request, urllib.parse
BOT=os.getenv("TELEGRAM_BOT_TOKEN","").strip()
CHAT=os.getenv("TELEGRAM_CHAT_ID","").strip()
def send(msg: str):
    if not BOT or not CHAT: return 0
    url=f"https://api.telegram.org/bot{BOT}/sendMessage"
    data=urllib.parse.urlencode({"chat_id":CHAT,"text":msg,"parse_mode":"HTML","disable_web_page_preview":"true"}).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(url,data=data)) as r: r.read()
        return 0
    except Exception as e:
        print("telegram_error:",e,file=sys.stderr); return 1
if __name__=="__main__": send("✅ notify.py wired up.")
