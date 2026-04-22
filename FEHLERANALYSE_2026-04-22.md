# Fehleranalyse & Patch-Vorschläge — ethbot_code

**Datum:** 2026-04-22
**Analysewerkzeuge:** `py_compile`, `ruff 0.x`, `pytest`, manuelle Import-Graph-Prüfung
**Umfang:** 90 Python-Dateien (ohne `.venv`, `venv_local`, `archive`, `__pycache__`, `backups`)
**Hinweis:** Dieser Report enthält nur Vorschläge. Es wurden **keine** Dateien geändert.

---

## TL;DR

| Kategorie | Status | Anzahl |
|---|---|---|
| Syntaxfehler | OK | 0 / 90 |
| Produktions-Imports (main_v3.py → bot.engine, api_v3.py → api.v3_routes) | OK | Startet |
| Kritische Laufzeit-Bugs (Produktionscode) | **Aktion empfohlen** | 3 |
| Tote Module mit kaputten Imports (nicht im Hot-Path) | **Aktion empfohlen** | 4 Dateien |
| Silent-Exception-Swallowing | **Aktion empfohlen** | 4 Stellen |
| Kaputte PyTorch-Fallback-Logik | **Aktion empfohlen** | 2 Dateien |
| Pytest-Suite (stale Tests gegen archivierte Module) | **Aufräumen** | 65 fail / 58 error / 90 pass |
| Ruff Stil (W293/E501/W291) | Optional autofixbar | ~1840 |

**Die Produktionspfade (`main_v3.py` Worker + `api_v3.py` Web) starten und importieren sauber.** Die gefundenen kritischen Probleme betreffen entweder Logikbugs im Hot-Path (siehe #1) oder Dead-Code-Inseln, die bei zukünftiger Reaktivierung Fehler werfen würden (siehe #2–#4).

---

## 1. Kritische Bugs im Produktionscode

### 1.1 `bot/engine.py:316` — Ternär-Guard immer False (Logikbug)

```python
# Aktuell (Zeile 316):
trade_regime = getattr(pos, 'entry_regime', signal.regime if 'signal' in dir() else 'unknown')
```

**Problem:**
- `signal` ist auf Modulebene als `import signal as sig` importiert (Zeile 20) → der Name `signal` ist im Funktions-Scope **nie** gebunden.
- `'signal' in dir()` prüft den lokalen Scope der Funktion. In diesem Zweig (`if state.is_in_position:`) wird `signal` nie lokal gesetzt, der Guard ist **immer** `False`.
- Resultat: Der ternäre Ausdruck evaluiert immer zu `'unknown'`, der gesamte Branch ist toter Code.
- Der ähnliche Ausdruck auf Zeile 318 (`decision.votes if 'decision' in dir() else []`) funktioniert korrekt, weil `decision` auf Zeile 207 in der gleichen Funktion gesetzt wird.

**Impact:** Das RL-Optimizer-Learning erhält immer `regime='unknown'` statt des tatsächlichen Entry-Regimes → verzerrtes Lernen, schwächere RL-Gewichtung pro Regime.

**Patch-Vorschlag:**

```diff
--- a/bot/engine.py
+++ b/bot/engine.py
@@ -313,7 +313,7 @@
                 # Get the swarm votes that led to this trade
                 from bot.swarm import get_swarm
                 swarm = get_swarm()
-                trade_regime = getattr(pos, 'entry_regime', signal.regime if 'signal' in dir() else 'unknown')
+                trade_regime = getattr(pos, 'entry_regime', 'unknown')
                 rl.learn_from_trade(
                     votes=decision.votes if 'decision' in dir() else [],
                     regime=trade_regime,
```

---

### 1.2 `bot/executor.py:148` — SELL-Response wird nicht validiert

```python
# Zeile 148:
resp = client.order_market_sell(symbol=config.pair, quantity=round(qty, 5))
logger.info(f"[LIVE] SELL {qty:.5f} {config.base_asset} @ ~${price:.2f}")
return True
```

**Problem:**
- `resp` wird zugewiesen, aber nie geprüft (F841).
- Die Funktion gibt `True` zurück, egal ob die Order tatsächlich gefüllt wurde.
- Bei Binance-Fehlerstatus wird zwar eine Exception geworfen (vom `python-binance`-Client), aber wenn der Server eine Order mit status `EXPIRED`/`REJECTED` zurückgibt, würde das maskiert.

**Impact:** In einem Live-Trade kann der Bot glauben, er habe verkauft, obwohl die Position noch offen ist → offener Verlust wird nicht erkannt.

**Patch-Vorschlag:**

```diff
--- a/bot/executor.py
+++ b/bot/executor.py
@@ -145,9 +145,14 @@
         logger.warning(f"[LIVE] SELL blocked: {available:.5f} < {qty:.5f}")
         return False

-    resp = client.order_market_sell(symbol=config.pair, quantity=round(qty, 5))
-    logger.info(f"[LIVE] SELL {qty:.5f} {config.base_asset} @ ~${price:.2f}")
-    return True
+    resp = client.order_market_sell(symbol=config.pair, quantity=round(qty, 5))
+    status = resp.get("status") if isinstance(resp, dict) else None
+    if status not in ("FILLED", "PARTIALLY_FILLED"):
+        logger.error(f"[LIVE] SELL unexpected status: {status} resp={resp}")
+        return False
+    logger.info(f"[LIVE] SELL {qty:.5f} {config.base_asset} @ ~${price:.2f} (status={status})")
+    return True
```

---

### 1.3 `bot/executor.py:306` — Forward-Reference auf `pd.DataFrame`

```python
# Zeile 306:
def fetch_klines(...) -> "pd.DataFrame":
    ...
    import pandas as pd
```

**Problem:**
- `from __future__ import annotations` ist an Zeile 1 → alle Annotations sind sowieso lazy (Strings). Die Quotes sind redundant, aber ruff flagt F821 auf `pd`.
- Statische Typ-Checker/IDE können den Typ nicht auflösen.

**Impact:** Nur Kosmetik/Tooling. Kein Laufzeit-Fehler.

**Patch-Vorschlag (zwei Optionen — Option A empfohlen, da leichter zu warten):**

```diff
--- a/bot/executor.py
+++ b/bot/executor.py
@@ -11,6 +11,7 @@
 import logging
 import time
 import functools
+import pandas as pd
 import requests
 from bot.config import TradingConfig
 from bot.state import BotState
@@ -303,9 +304,8 @@

 @retry_api(max_retries=3, base_delay=1.0)
-def fetch_klines(pair: str = "ETHUSDT", interval: str = "5m", lookback: int = 400) -> "pd.DataFrame":
+def fetch_klines(pair: str = "ETHUSDT", interval: str = "5m", lookback: int = 400) -> pd.DataFrame:
     """Fetch OHLCV klines from Binance (with retry)."""
-    import pandas as pd

     base = "https://api.binance.com/api/v3/klines"
```

---

## 2. Tote Module mit kaputten Imports

Alle vier Module starten **nicht** bei `import` (ModuleNotFoundError bzw. NameError). Keines davon wird vom Produktions-Hot-Path (`main_v3.py` / `api_v3.py`) referenziert — prüft man mit `sys.modules` nach Import von `api_v3`+`main_v3`, tauchen sie nicht auf.

| Datei | Import-Fehler | Von wem referenziert |
|---|---|---|
| `auth_deps.py` | `No module named 'user_manager'` | `routes/admin.py`, `routes/copy_trading.py`, `tests/integration/*` |
| `routes/admin.py` | indirekt via `auth_deps` + `from user_manager import UserManager` | nirgends (APIRouter wird nicht mounted) |
| `routes/copy_trading.py` | indirekt via `auth_deps` | nirgends |
| `auto_learning_service.py` | `No module named 'continuous_backtester'` | nirgends |

`user_manager.py` und `continuous_backtester.py` liegen in `archive/old_root_scripts/`.

**Impact heute:** Keine, weil nicht geladen.
**Impact bei Reaktivierung / Tests:** Sofortiger ImportError.

**Empfehlungsoptionen:**

**Option A — Module in den Produktionspfad zurückholen (falls Copy-Trading/Admin-UI benötigt):**

```diff
--- a/auth_deps.py
+++ b/auth_deps.py
@@ -11,7 +11,11 @@
 from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
 from typing import Optional

-from user_manager import UserManager
+try:
+    from user_manager import UserManager
+except ModuleNotFoundError:
+    # Legacy location moved to archive during v3 refactor
+    from archive.old_root_scripts.user_manager import UserManager  # type: ignore
```

```diff
--- a/auto_learning_service.py
+++ b/auto_learning_service.py
@@ -8,7 +8,10 @@
 import os
 import time
 import logging
-from continuous_backtester import ContinuousBacktester
+try:
+    from continuous_backtester import ContinuousBacktester
+except ModuleNotFoundError:
+    from archive.old_root_scripts.continuous_backtester import ContinuousBacktester  # type: ignore
```

**Option B — Tote Dateien nach `archive/` verschieben (falls die Funktionalität im v3-Stack nicht mehr gebraucht wird):**

```bash
mkdir -p archive/unused_v2_routes
git mv auth_deps.py routes/admin.py routes/copy_trading.py auto_learning_service.py archive/unused_v2_routes/
```

> **Entscheidung liegt beim User.** Option A ist sicherer, wenn unklar ist, ob die Routen reaktiviert werden sollen.

---

## 3. PyTorch-Fallback defekt

### 3.1 `neural_strategy_predictor.py:25` / `rl_trading_agent.py`

```python
try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
    PYTORCH_AVAILABLE = True
except ImportError:
    PYTORCH_AVAILABLE = False
    print("⚠️ PyTorch not installed. Run: pip install torch")


class StrategyLSTM(nn.Module):   # ← NameError, wenn torch fehlt
    ...
```

**Problem:** Die Klassendefinition referenziert `nn.Module` auf Modulebene — ohne PyTorch scheitert der Import der ganzen Datei, der `PYTORCH_AVAILABLE = False`-Fallback wird **nie** wirksam.

**Impact:** Jeder Code, der `neural_strategy_predictor` oder `rl_trading_agent` importiert, stürzt ab, wenn torch nicht in der Umgebung ist. `requirements.txt` listet torch **nicht** (keine `torch` oder `pytorch` Zeile) — das bedeutet, auf einem frischen Deploy ohne torch wäre jeder Tooling-Skript, der diese Module lädt, tot.

**Patch-Vorschlag (stellvertretend für beide Dateien):**

```diff
--- a/neural_strategy_predictor.py
+++ b/neural_strategy_predictor.py
@@ -19,10 +19,16 @@
     PYTORCH_AVAILABLE = True
 except ImportError:
     PYTORCH_AVAILABLE = False
+    nn = None  # type: ignore
+    torch = None  # type: ignore
+    optim = None  # type: ignore
     print("⚠️ PyTorch not installed. Run: pip install torch")


-class StrategyLSTM(nn.Module):
+_BASE = nn.Module if PYTORCH_AVAILABLE else object
+
+
+class StrategyLSTM(_BASE):  # type: ignore[misc]
     """LSTM Neural Network for strategy score prediction"""

     def __init__(self, input_size: int = 8, hidden_size: int = 64, num_layers: int = 2, dropout: float = 0.2):
+        if not PYTORCH_AVAILABLE:
+            raise RuntimeError("PyTorch not installed — cannot instantiate StrategyLSTM")
         super(StrategyLSTM, self).__init__()
```

Analog für `rl_trading_agent.py`. Alternativ: `torch` in `requirements.txt` aufnehmen, falls die Module produktiv genutzt werden.

---

## 4. Silent Exception Swallowing — `routes/copy_trading.py`

4 Stellen fangen `Exception as e`, ohne `e` zu loggen (F841). Beispiel:

```python
# Zeilen 83-84, 116-117, 133-134, 172-173:
except Exception as e:
    return {"status": "success", "following": []}
```

**Problem:** Fehler in Abhängigkeiten (z. B. DB down, `_get_copy_engine` schlägt fehl) werden komplett verschluckt — das Frontend bekommt eine leere Liste und glaubt, alles sei ok.

**Patch-Vorschlag:**

```diff
--- a/routes/copy_trading.py
+++ b/routes/copy_trading.py
@@ -7,6 +7,10 @@

+import logging
 from fastapi import APIRouter, Depends
 from typing import Dict, Optional

 from auth_deps import get_current_user, get_current_user_optional

+logger = logging.getLogger("ethbot.routes.copy_trading")
+
 router = APIRouter(tags=["copy-trading"])
@@ -80,7 +84,8 @@
     try:
         engine = _get_copy_engine()
         following = engine.get_following(current_user["id"])
         return {"status": "success", "following": following}
-    except Exception as e:
+    except Exception:
+        logger.exception("get_following failed for user %s", current_user.get("id"))
         return {"status": "success", "following": []}
```

Gleiches Muster für Zeilen 94/95, 116/117, 133/134, 155/156, 172/173, 185/186.

---

## 5. `routes/admin.py:120, 361` — `raise ... from err` fehlt (B904)

```python
except Exception as e:
    raise HTTPException(status_code=500, detail=str(e))
```

**Problem:** Ohne `from e` maskiert FastAPI die ursprüngliche Exception, Stacktrace geht verloren.

**Patch-Vorschlag:**

```diff
     except Exception as e:
-        raise HTTPException(status_code=500, detail=str(e))
+        raise HTTPException(status_code=500, detail=str(e)) from e
```

An beiden Stellen identisch.

---

## 6. Pytest-Suite — 65 fail / 58 error / 90 pass

### 6.1 Collection-Fehler

- `tests/unit/test_auto_apply.py` → `No module named 'auto_apply'` (in `archive/old_root_scripts/auto_apply.py`)
- `tests/integration/test_pipeline.py` → `No module named 'user_manager'`

### 6.2 Laufzeit-Fehler (legacy Modulreferenzen)

Viele Tests laden archivierte v2-Module:
- `test_v2_system.py` → `signal_engine_v2`, `risk_manager_v2`
- `test_security_audit.py` → `src.core.advanced_guards`, `eth_master_bot`, `order_executor`, `user_manager`, `anti_martingale`, `ml_engine`
- `test_revenue_engine.py` → `revenue_engine`
- `test_multi_timeframe.py` → `multi_timeframe_analyzer`
- `test_api_endpoints.py` → benötigt `auth_deps` (siehe #2)

**Empfehlung:** Entweder die zugehörigen Module aus `archive/` wieder reaktivieren, oder die stale Tests nach `tests/archive/` verschieben und aus `pytest.ini` `testpaths` ausklammern.

### 6.3 Was grün läuft (90 Tests)

Darunter u. a.:
- `tests/unit/test_v2_system.py::TestEdgeValidator` (9/9 pass)
- `tests/unit/test_risk_manager.py` (mehrere pass, 1 F841-Warnung)
- `tests/unit/test_indicators.py`, `test_ml_engine.py` (teilweise)

→ Der Kern (edge validator, risk manager, indikatoren) ist getestet und grün.

---

## 7. Ruff Stil-Issues (niedrige Priorität)

Automatisch fixbar mit `ruff check --fix .`:

| Rule | Anzahl | Was |
|---|---|---|
| W293 | 1303 | Whitespace auf leerer Zeile |
| E501 | 457 | Zeile > 88 Zeichen |
| W291 | 79 | Trailing Whitespace |
| E402 | 66 | Import nicht am Dateianfang (oft beabsichtigt wg. conditional import) |
| E701 | 38 | Mehrere Statements auf einer Zeile |
| B008 | 30 | `Depends()` im Default — **false positive** für FastAPI-Idiom |
| F841 | 24 | Ungenutzte lokale Variable |
| E712 | 8 | `== True/False` statt Truthiness |
| E722 | 7 | `bare except:` (siehe #8) |
| F401 | 6 | Ungenutzter Import |

**Empfehlung:**

```bash
# Sicher und reversibel:
ruff check --fix --select W293,W291,F401,F541 .
git diff   # review
```

---

## 8. Weitere Detail-Befunde (Bedarf Review)

### 8.1 Bare Except (E722) — 7 Stellen

- `neural_strategy_predictor.py:394`
- `routes/admin.py:245, 272`
- `test_phase_manager.py:41, 82, 121, 190`

`except:` fängt auch `KeyboardInterrupt` und `SystemExit` → sollte immer `except Exception:` sein.

### 8.2 Ungenutzte Imports in `trade_store.py` (F401)

```python
# Zeilen 10, 12, 13:
import json            # unused
from datetime import datetime  # unused
from typing import ..., Optional  # Optional unused
```

Trivial autofixbar: `ruff check --fix trade_store.py`.

### 8.3 `bot/brain_store.py:9,14` — 3 ungenutzte Imports

`os`, `datetime.datetime`, `datetime.timezone`.

### 8.4 `bot/engine.py:920` — `swarm = get_swarm()` unbenutzt

```python
swarm = get_swarm()   # ← zugewiesen aber nie verwendet
```

Evtl. Nebeneffekt einer Singleton-Init — falls nicht, Zeile entfernen.

---

## 9. Empfohlene Reihenfolge

1. **Sofort (Logik-Bugs im Hot-Path):**
   - §1.1 `bot/engine.py:316` (trade_regime)
   - §1.2 `bot/executor.py:148` (SELL response check)

2. **Kurzfristig (verhindert zukünftige Crashes):**
   - §3 PyTorch-Fallback in `neural_strategy_predictor.py` + `rl_trading_agent.py`
   - §2 Entscheidung: Reaktivieren oder Archivieren von `auth_deps`, `routes/admin`, `routes/copy_trading`, `auto_learning_service`

3. **Mittel:**
   - §4 Silent exception swallowing in `copy_trading.py`
   - §5 `raise ... from err` in `admin.py`
   - §6 Pytest-Aufräumen

4. **Niedrig / optional:**
   - §7 Ruff-Autofix
   - §8 Detail-Refactorings

---

## Verifikation

```bash
# Syntax (bereits grün)
find . -name "*.py" \
  -not -path "./.venv/*" -not -path "./venv_local/*" \
  -not -path "*/__pycache__/*" -not -path "./archive/*" -not -path "./backups/*" \
  -exec python3 -m py_compile {} \;

# Import-Smoke-Test für Produktionspfad
python3 -c "import api_v3, main_v3; print('prod imports OK')"

# Tests ohne stale Legacy-Referenzen
python3 -m pytest tests/unit/test_edge_validator.py tests/unit/test_indicators.py \
  tests/unit/test_risk_manager.py -v
```

---

**Ende des Reports.**
