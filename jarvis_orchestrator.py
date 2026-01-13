#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Jarvis-Orchestrator (leichtgewichtig)
- Health-Checks für Services
- ruft Focus-Auto (timer) & Learn-Jarvis an
- prüft Konsole auf Fehlerpattern (soft)
- schreibt kompakte Status-Zusammenfassung
"""
import os, sys, pathlib, re, subprocess
from datetime import datetime, timezone, timedelta

ROOT = pathlib.Path("/root/ethbot")
LOGD = ROOT / "logs"
LOGD.mkdir(parents=True, exist_ok=True)
LOGF = LOGD / "jarvis_orchestrator.log"
SUMMARY = LOGD / "status_summary.txt"

def log(msg):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    line = f"{ts} [JARVIS] {msg}"
    print(line, flush=True)
    with open(LOGF, "a", encoding="utf-8") as f:
        f.write(line+"\n")

def run(cmd: str) -> tuple[int,str,str]:
    p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    out,err = p.communicate(timeout=60)
    return p.returncode, out.strip(), err.strip()

def is_active(unit: str) -> bool:
    rc, out, _ = run(f"systemctl is-active {unit}")
    return (rc==0 and out.strip()=="active")

def tail_console(n=200):
    fp = LOGD / "console.out"
    if not fp.exists(): return ""
    rc,out,err = run(f"tail -n {n} {fp}")
    return out

def main():
    lines = []
    # 1) Services ok?
    ethbot_ok = is_active("ethbot")
    focus_timer_ok = is_active("ethbot-focus.timer")
    learn_timer_ok = is_active("ethbot-learn.timer")

    lines.append(f"ethbot: {'active' if ethbot_ok else 'INACTIVE'}")
    lines.append(f"focus.timer: {'active' if focus_timer_ok else 'INACTIVE'}")
    lines.append(f"learn.timer: {'active' if learn_timer_ok else 'INACTIVE'}")

    # 2) Trigger Learn-Jarvis (oneshot), nur wenn Timer aktiv
    if learn_timer_ok:
        rc, out, err = run("systemctl start ethbot-learn.service")
        lines.append(f"learn.trigger: rc={rc}")

    # 3) Soft-Analyse Konsole
    con = tail_console(2000)
    softblocks = len(re.findall(r"regime soft-block", con))
    elapsed_errs = len(re.findall(r"elapsed_bars", con, re.I))
    safeguards = len(re.findall(r"\[SAFEGUARD\]", con))
    lines.append(f"console: soft-blocks={softblocks} safeguards={safeguards} elapsed_errs={elapsed_errs}")

    # 4) Focus-Auto einmal manuell anstoßen (idempotent)
    if focus_timer_ok:
        run("systemctl start ethbot-focus.service")
        lines.append("focus.trigger: ok")

    # 5) Summary schreiben
    SUMMARY.write_text("\n".join(lines) + "\n", encoding="utf-8")
    log(" | ".join(lines))
    return 0

if __name__ == "__main__":
    sys.exit(main())
