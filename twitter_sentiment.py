#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, json, pathlib, time, sys, re, random, subprocess, shlex, math, urllib.request, urllib.parse

ROOT = pathlib.Path("/root/ethbot")
LOGD, CACHED, CONFD = ROOT/"logs", ROOT/"cache", ROOT/"config"
LOGD.mkdir(parents=True, exist_ok=True); CACHED.mkdir(parents=True, exist_ok=True)
CACHE_FILE = CACHED/"sentiment.json"; LOG_FILE = LOGD/"twitter_sentiment.log"
HANDLE_LIST = (CONFD/"influencers_eth.txt")

# ---- ENV ----
TWITTER_BEARER     = os.getenv("TWITTER_BEARER","").strip()
TWITTER_SENTIMENT  = os.getenv("TWITTER_SENTIMENT","0").strip()   # 1 = an
TW_MAX_READS       = int(os.getenv("TW_MAX_READS","20"))          # Limit pro Run (abgesenkt)
TW_NEEDLE          = os.getenv("TW_NEEDLE","(eth OR ethereum)")
TW_SCRAPE_FALLBACK = os.getenv("TW_SCRAPE_FALLBACK","1").strip()
SNS_BIN            = str(ROOT/".venv/bin/snscrape")

# Gewichtung
TW_WEIGHTED   = os.getenv("TW_WEIGHTED","1").strip() == "1"
W_LIKE        = float(os.getenv("TW_W_LIKE","0.10"))
W_RT          = float(os.getenv("TW_W_RETWEET","0.20"))
W_REPLY       = float(os.getenv("TW_W_REPLY","0.05"))
W_QUOTE       = float(os.getenv("TW_W_QUOTE","0.10"))

# Keywords
POS_BASE = {"pump","bull","rally","breakout","moon","rip","merge","deflation","l2","rollup","scaling","staking","mainnet","adoption","etf","approval","flippening","eip-4844","proto-danksharding"}
NEG_BASE = {"dump","bear","crash","risk","selloff","liquidation","rekt","hack","exploit","reorg","slashing","outage","denial","bug","ban","restrict","fee spike","delay"}

POS_EXTRA = set([x.strip().lower() for x in os.getenv("TW_POS_EXTRA","").split(",") if x.strip()])
NEG_EXTRA = set([x.strip().lower() for x in os.getenv("TW_NEG_EXTRA","").split(",") if x.strip()])
POS_WORDS = POS_BASE | POS_EXTRA
NEG_WORDS = NEG_BASE | NEG_EXTRA

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

def log(msg): LOG_FILE.open("a",encoding="utf-8").write(msg.rstrip()+"\n")

def write_cache(score: float, meta: dict):
    CACHE_FILE.write_text(json.dumps({"score": round(score,4), "ts": int(time.time()), **meta}, ensure_ascii=False))

def read_cache():
    try:    return json.loads(CACHE_FILE.read_text())
    except: return None

def kw_score(text: str):
    t = (text or "").lower()
    pos = any(k in t for k in POS_WORDS)
    neg = any(k in t for k in NEG_WORDS)
    return (1 if pos else 0) - (1 if neg else 0)

# ---------- API ----------
def _api_request(query: str, max_results: int):
    url = "https://api.twitter.com/2/tweets/search/recent?" + urllib.parse.urlencode({
        "query": query,
        "tweet.fields": "lang,public_metrics,created_at",
        "max_results": str(max(10, min(50, max_results))),
    })
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {TWITTER_BEARER}", "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return 200, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try: body = e.read().decode()[:400]
        except: body = str(e)
        return e.code, body
    except Exception as e:
        return -1, str(e)

def fetch_api_combined(handles):
    if not TWITTER_BEARER:
        log("skip: no TWITTER_BEARER"); return []
    if not handles:
        handles = ["coinbase","krakenfx","glassnode","QCPgroup","binance"]
    ors   = " OR ".join([f"from:{h}" for h in handles])
    query = f"({ors}) {TW_NEEDLE} lang:en -is:retweet -is:reply"
    rc, data = _api_request(query, TW_MAX_READS)
    if rc == 429:
        sleep_s = 45 + random.randint(0,30)
        log(f"api 429: backoff {sleep_s}s, retry once")
        time.sleep(sleep_s)
        rc, data = _api_request(query, TW_MAX_READS)
    if rc != 200:
        log(f"api_err rc={rc} msg={(data if isinstance(data,str) else str(data))[:300]}")
        return []
    out = []
    for t in (data.get("data") or []):
        if t.get("lang") in ("en","und"):
            pm = t.get("public_metrics", {}) or {}
            out.append({
                "text": t.get("text",""),
                "like": int(pm.get("like_count",0) or 0),
                "rt":   int(pm.get("retweet_count",0) or 0),
                "rep":  int(pm.get("reply_count",0) or 0),
                "quo":  int(pm.get("quote_count",0) or 0),
            })
            if len(out) >= TW_MAX_READS: break
    return out

# ---------- snscrape Fallback ----------
def _run(cmd: str, timeout=60):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout or ""), (r.stderr or "")
    except Exception as e:
        return 99, "", str(e)

def fetch_snscrape_combined(handles):
    if not os.path.isfile(SNS_BIN) or not os.access(SNS_BIN, os.X_OK):
        log("snscrape missing/not executable"); return []
    if not handles:
        handles = ["coinbase","krakenfx","glassnode","QCPgroup","binance"]
    ors   = " OR ".join([f"(from:{h})" for h in handles])
    query = f"({ors}) {TW_NEEDLE} lang:en"
    cmd   = f"{shlex.quote(SNS_BIN)} --jsonl --max-results {int(TW_MAX_READS)} twitter-search {shlex.quote(query)}"
    rc, out, err = _run(cmd, timeout=75)
    if rc != 0:
        log(f"snscrape_err rc={rc} stderr={err[:300]}")
        return []
    texts = []
    for ln in out.splitlines():
        try:
            obj = json.loads(ln)
            txt = obj.get("content") or obj.get("rawContent") or obj.get("text") or ""
        except Exception:
            txt = ln
        if txt:
            texts.append({"text": txt, "like":0, "rt":0, "rep":0, "quo":0})
            if len(texts) >= TW_MAX_READS: break
    return texts

# ---------- Main ----------
def main():
    log(f"env: TSENT={TWITTER_SENTIMENT} BEAR_LEN={len(TWITTER_BEARER)} SCRAPE_FB={TW_SCRAPE_FALLBACK} WEIGHTED={int(TW_WEIGHTED)}")
    if TWITTER_SENTIMENT != "1":
        log("skip: TWITTER_SENTIMENT=0"); return 0

    handles=[]
    if HANDLE_LIST.exists():
        handles = [x.strip() for x in HANDLE_LIST.read_text().splitlines() if x.strip() and not x.strip().startswith("#")]

    # 1) API
    items = fetch_api_combined(handles)
    source = "api"

    # 2) Cache + Fallback
    if not items:
        prev = read_cache()
        if prev:
            prev["ts"] = int(time.time())
            prev["source"] = prev.get("source","cache")
            write_cache(prev.get("score",0.0), {k:v for k,v in prev.items() if k!="score"})
            # quiet cache reuse
        if TW_SCRAPE_FALLBACK == "1":
            scr = fetch_snscrape_combined(handles)
            if scr:
                items  = scr
                source = "snscrape"
        if not items and not prev:
            write_cache(0.0, {"reason":"fetch_fail","source":"none","api":0,"n":0})
            log("warn: no tweets & no cache; wrote neutral 0.0")
            return 0

    if not items:  # Cache bereits geschrieben
        return 0

    # 3) Scoring (gewichtet)
    numer = 0.0
    denom = 0.0
    for it in items:
        base = kw_score(it["text"])
        if TW_WEIGHTED:
            w = 1.0 + W_LIKE*math.log1p(it["like"]) + W_RT*math.log1p(it["rt"]) + W_REPLY*math.log1p(it["rep"]) + W_QUOTE*math.log1p(it["quo"])
        else:
            w = 1.0
        numer += base * w
        denom += w
    score = (numer / denom) if denom > 0 else 0.0

    write_cache(score, {"n": len(items), "api": int(source=="api"), "source": source})
    log(f"ok: source={source} n={len(items)} score={score:.3f}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
