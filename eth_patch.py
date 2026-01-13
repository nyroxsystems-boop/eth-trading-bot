#!/usr/bin/env python3
import sys, time, re
from pathlib import Path
def find_func_span(src, func):
    import re
    start_pat = re.compile(rf"(?m)^[ \t]*def\s+{re.escape(func)}\s*\([^)]*\)\s*:\s*\n")
    m = start_pat.search(src)
    if not m: return None
    start, body_start = m.start(), m.end()
    end_pat = re.compile(r"(?m)^[ \t]*(def\s+|class\s+|if\s+__name__\s*==\s*['\"]__main__['\"])")
    m2 = end_pat.search(src, body_start)
    end = m2.start() if m2 else len(src)
    return start, end
if len(sys.argv) < 4:
    print("Usage: eth_patch.py <file.py> <function_name> <patch_file>"); sys.exit(1)
target, func, patchf = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
src = target.read_text(encoding="utf-8")
span = find_func_span(src, func)
if not span: print(f"[!] Funktion '{func}' nicht gefunden."); sys.exit(2)
s, e = span
new_block = patchf.read_text(encoding="utf-8").rstrip() + "\n"
header_pat = re.compile(rf"(?ms)^[ \t]*def\s+{re.escape(func)}\s*\([^)]*\)\s*:\s*\n")
header_m = header_pat.search(src, s, e)
if not header_m: print("[!] Header nicht gefunden."); sys.exit(3)
header = header_m.group(0)
import re as _re
if not _re.match(rf"(?ms)^[ \t]*def\s+{_re.escape(func)}\s*\(", new_block):
    body = "\n".join(("    "+l if l.strip() else l) for l in new_block.splitlines()) + "\n"
    replacement = header + body
else:
    replacement = new_block
backup = target.with_suffix(target.suffix + f".bak.{time.strftime('%Y%m%d_%H%M%S')}")
backup.write_text(src, encoding="utf-8")
target.write_text(src[:s] + replacement + src[e:], encoding="utf-8")
print(f"[✓] '{func}' ersetzt. Backup -> {backup}")
