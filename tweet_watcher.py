#!/usr/bin/env python3
import os, sys, time, json, urllib.request, urllib.parse, xml.etree.ElementTree as ET

import pathlib
_ROOT=pathlib.Path(os.getenv("ETHBOT_ROOT", str(pathlib.Path(__file__).resolve().parent)))
OUT=str(_ROOT/"run/news_block.json")
KEYWORDS = [
  "tariff", "ban", "sanction", "tax", "halt", "freeze", "ban crypto", "ban mining",
  "ETF delay", "SEC delays", "hack", "exploit", "outage", "halt trading", "emergency",
  "CPI", "FOMC", "rate hike", "jobs report", "inflation", "BlackRock ETF",
  "Trump", "Biden", "China", "SEC", "CFTC", "Treasury"
]
ACCOUNTS = ["POTUS", "elonmusk", "secgov", "GaryGensler", "Reuters", "Bloomberg", "CoinDesk", "WSJ"]

def write_block(msg, sev):
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump({"ts":time.time(), "severity":int(sev), "msg":msg}, open(OUT,"w",encoding="utf-8"))
    print(f"[TW] block set sev={sev} msg={msg}")

def from_rss(url, sev=2):
    try:
        with urllib.request.urlopen(url, timeout=8) as r:
            data=r.read()
        root=ET.fromstring(data)
        items=root.findall(".//item")
        for it in items[:8]:
            t=(it.findtext("title") or "") + " " + (it.findtext("description") or "")
            low=t.lower()
            if any(k.lower() in low for k in KEYWORDS):
                write_block(f"RSS:{t[:160]}", sev); return True
    except Exception as e:
        print(f"[TW] rss err {e}")
    return False

def from_x(query, max_results=10, sev=3):
    token=os.getenv("X_BEARER_TOKEN")
    if not token: return False
    try:
        q=urllib.parse.quote(query)
        url=f"https://api.x.com/2/tweets/search/recent?query={q}&max_results={max_results}"
        req=urllib.request.Request(url, headers={"Authorization":f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=8) as r:
            js=json.load(r)
        for d in js.get("data", []):
            text=d.get("text","")
            if any(k.lower() in text.lower() for k in KEYWORDS):
                write_block(f"X:{text[:160]}", sev); return True
    except Exception as e:
        print(f"[TW] x err {e}")
    return False

def main():
    hit=False
    # 1) X high-severity accounts/keywords (wenn API-Key existiert)
    if from_x("(" + " OR ".join(f"from:{a}" for a in ACCOUNTS) + ") ( " + " OR ".join(KEYWORDS) + " )", sev=3):
        hit=True
    # 2) Fallback RSS (mittlere Schwere)
    hit = from_rss("https://cryptopanic.com/rss/") or hit
    hit = from_rss("https://www.coindesk.com/arc/outboundfeeds/rss/", sev=2) or hit
    print("[TW] done, hit=", hit)

if __name__=="__main__":
    main()
