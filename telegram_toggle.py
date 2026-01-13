#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, json, time, urllib.parse, urllib.request, ssl, subprocess, pathlib

ROOT   = pathlib.Path("/root/ethbot")
STATE  = ROOT / "state" / "mode.json"
LOGF   = ROOT / "logs" / "toggle.log"

TOKEN  = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
ADMIN  = os.getenv("TELEGRAM_CHAT_ID", "").strip()  # erlaubter Chat
BASE   = f"https://api.telegram.org/bot{TOKEN}"

# UI Labels
BTN_LIVE = "🟢 Go Live"
BTN_DRY  = "🧪 Dry Run"
BTN_OK   = "✅ Bestätigen"
BTN_NO   = "↩️ Abbrechen"

def log(msg:str):
    LOGF.parent.mkdir(parents=True, exist_ok=True)
    with LOGF.open("a", encoding="utf-8") as f:
        f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg + "\n")

def http_get(path, params=None, timeout=30):
    if params: path += "?" + urllib.parse.urlencode(params)
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(BASE + path, timeout=timeout, context=ctx) as r:
        return json.loads(r.read().decode("utf-8"))

def http_post(path, data=None, timeout=30):
    data = urllib.parse.urlencode(data or {}).encode("utf-8")
    ctx = ssl.create_default_context()
    req = urllib.request.Request(BASE + path, data=data)
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return json.loads(r.read().decode("utf-8"))

def mode_read():
    try:
        return json.loads(STATE.read_text()).get("mode","dry")
    except Exception:
        return "dry"

def mode_write(newmode, by="system"):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({"mode":newmode, "by":by, "ts":int(time.time())}))
    log(f"mode set -> {newmode} by {by}")

def status_card(chat_id):
    m = mode_read()
    txt = (
        "🔧 *ETHBot Mode*\n"
        f"• Aktuell: *{('LIVE' if m=='live' else 'DRY')}*\n"
        "• Umschalten per Buttons unten.\n"
        "_Sicherheitsgurte: Key-Check, Systemd-Env, sauberer Restart._"
    )
    kb = [[{"text": BTN_LIVE, "callback_data": "ask_live"},
           {"text": BTN_DRY,  "callback_data": "ask_dry"}]]
    http_post("/sendMessage", {
        "chat_id": chat_id, "text": txt, "parse_mode": "Markdown",
        "reply_markup": json.dumps({"inline_keyboard": kb})
    })

def confirm_card(chat_id, target):
    txt = ("⚠️ *Bestätigung erforderlich*\n"
           f"Willst du wirklich auf *{target.upper()}* schalten?")
    kb = [[{"text": BTN_OK, "callback_data": f"do_{target}"},
           {"text": BTN_NO, "callback_data": "cancel"}]]
    http_post("/sendMessage", {
        "chat_id": chat_id, "text": txt, "parse_mode": "Markdown",
        "reply_markup": json.dumps({"inline_keyboard": kb})
    })

def api_keys_ok():
    # Minimal-Check: Keys vorhanden
    return bool(os.getenv("BINANCE_API_KEY","").strip() and os.getenv("BINANCE_API_SECRET","").strip())

def switch_mode(target_mode):
    # Set systemd environment + restart ethbot
    env_val = "false" if target_mode=="live" else "true"
    subprocess.run(["/bin/systemctl","set-environment", f"DRY_RUN={env_val}"], check=False)
    mode_write(target_mode, by="toggle")
    # Sauberer Restart
    subprocess.run(["/bin/systemctl","restart","ethbot"], check=False)

def handle_update(upd):
    # accept messages & callbacks only from ADMIN chat id (string compare)
    if "message" in upd:
        msg = upd["message"]
        chat_id = str(msg.get("chat",{}).get("id",""))
        if chat_id != ADMIN: return
        text = (msg.get("text") or "").strip().lower()
        if text in ("/start","menu","/menu","toggle"):
            status_card(chat_id)
        elif text in ("live","go live","start live"):
            confirm_card(chat_id, "live")
        elif text in ("dry","dry run"):
            confirm_card(chat_id, "dry")

    if "callback_query" in upd:
        cbq = upd["callback_query"]
        chat_id = str(cbq.get("message",{}).get("chat",{}).get("id",""))
        data = cbq.get("data","")
        if chat_id != ADMIN: return
        if data == "ask_live":
            confirm_card(chat_id, "live")
        elif data == "ask_dry":
            confirm_card(chat_id, "dry")
        elif data == "cancel":
            http_post("/answerCallbackQuery", {"callback_query_id": cbq["id"], "text": "Abgebrochen."})
            status_card(chat_id)
        elif data.startswith("do_"):
            target = data.replace("do_","")
            if target == "live" and not api_keys_ok():
                http_post("/answerCallbackQuery", {
                    "callback_query_id": cbq["id"],
                    "text": "Keys fehlen. Bitte BINANCE_API_KEY/SECRET setzen.", "show_alert": True
                })
                return
            http_post("/answerCallbackQuery", {"callback_query_id": cbq["id"], "text": f"Schalte {target.upper()} …"})
            switch_mode(target)
            # Status zurück spielen
            txt = f"✅ Modus ist jetzt *{mode_read().upper()}*. Service neu gestartet."
            http_post("/sendMessage", {"chat_id": chat_id, "text": txt, "parse_mode":"Markdown"})
            status_card(chat_id)

def main():
    if not TOKEN or not ADMIN:
        log("TOKEN oder ADMIN-ID fehlt – beende.")
        return
    # Once: initial card
    try:
        status_card(ADMIN)
    except Exception as e:
        log(f"status_card error: {e}")

    offset = None
    while True:
        try:
            params = {"timeout": 50}
            if offset: params["offset"] = offset
            res = http_get("/getUpdates", params, timeout=55)
            for upd in res.get("result", []):
                offset = upd["update_id"] + 1
                handle_update(upd)
        except Exception as e:
            log(f"poll err: {e}")
            time.sleep(2)

if __name__ == "__main__":
    main()
