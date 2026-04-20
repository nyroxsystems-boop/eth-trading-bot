# Fehleranalyse & Fixes — ethbot_code

**Datum:** 2026-04-20
**Analysewerkzeug:** `pyflakes`, `autoflake`, `py_compile`
**Umfang:** 88 Python-Dateien (ohne `.venv`, `venv_local`, `archive`, `__pycache__`)

---

## Zusammenfassung

| Kategorie | Status | Anzahl |
|---|---|---|
| Syntaxfehler (py_compile) | OK | 0 |
| Unbenutzte Imports | Behoben | ~60 (in 54 Dateien) |
| Leere f-Strings (`f"..."` ohne Platzhalter) | Behoben | 38 |
| Doppelter Import (`jarvis/core.py`) | Behoben | 1 |
| Undefinierte Namen | Bedarf Review | 2 |
| Unbenutzte lokale Variablen | Bedarf Review | 25 |

**Gesamtänderung:** 55 Dateien geändert, −131 / +72 Zeilen (netto −59 Zeilen toter Code entfernt).

---

## Automatisch behobene Fehler

### 1. Unbenutzte Imports (54 Dateien)
Mit `autoflake --remove-all-unused-imports` entfernt. Beispiele:
- `api_v3.py`: `fastapi.Request` entfernt
- `data_collector.py`: `time`, `datetime.datetime`, `datetime.timezone` entfernt
- `main_v3.py`: `sys` entfernt
- `bot/shield.py`: `math`, `time`, `timedelta`, `defaultdict` entfernt
- `bot/brain.py`: `time`, `hashlib`, `timedelta`, `defaultdict` entfernt
- `bot/engine.py`: `bot.executor.get_current_price` (unbenutzt) entfernt
- … (vollständige Liste siehe `git diff --stat`)

### 2. Leere f-Strings (38 Vorkommen)
Umwandlung `f"..."` → `"..."` wenn kein Platzhalter `{...}` vorhanden. Das Präfix `f` ohne Platzhalter ist funktional irrelevant, aber irreführend und kostet minimal Laufzeit. Betroffen u. a.:
- `telegram_scheduler.py` (4×)
- `auto_learning_service.py` (2×)
- `neural_strategy_predictor.py` (2×)
- `rl_trading_agent.py` (3×)
- `account_manager.py` (2×)
- `bot/engine.py` (3×)
- `bot/market_intel.py` (5×)
- `bot/swarm.py` (3×)
- `bot/onchain.py` (2×)
- `tools/continuous_training.py` (3×)
- `tools/inject_test_strategies.py` (3×)
- `jarvis/watchdog.py` (1×)
- … u. a.

### 3. Doppelter `asyncio`-Import
- `jarvis/core.py`: `import asyncio` innerhalb des `__main__`-Blocks entfernt (Modul war bereits in Zeile 8 importiert).

---

## Noch zu prüfende Fehler (manueller Review empfohlen)

### A. Undefinierte Namen (potenzielle Logikbugs)

**1. `bot/engine.py:283`**
```python
trade_regime = getattr(pos, 'entry_regime', signal.regime if 'signal' in dir() else 'unknown')
```
- In diesem Zweig (`if state.is_in_position:`) wird `signal` nie gesetzt.
- `signal` ist auf Modulebene als `import signal as sig` importiert (Zeile 20), aber die Referenz `signal.regime` wäre ohnehin falsch (`signal` ist ein Standardmodul für Unix-Signale).
- Variable `signal` wird erst auf Zeile 300 im *anderen* Zweig (`elif not state.is_in_position:`) gesetzt.
- **Effekt:** Der ternäre Guard `'signal' in dir()` ist hier immer `False`, also fällt `trade_regime` immer auf `'unknown'` zurück.
- **Empfehlung:** Intent klären — soll hier `pos.entry_regime` als Default genügen? Dann:
  ```python
  trade_regime = getattr(pos, 'entry_regime', 'unknown')
  ```

**2. `bot/executor.py:306`**
```python
def fetch_klines(pair: str = "ETHUSDT", interval: str = "5m", lookback: int = 400) -> "pd.DataFrame":
    ...
    import pandas as pd
```
- Forward-Reference `"pd.DataFrame"` im Return-Typ. `pd` wird erst *innerhalb* der Funktion importiert.
- **Effekt:** Kein Laufzeitfehler (String-Annotation wird nicht evaluiert), aber statische Typ-Checker/IDE können den Typ nicht auflösen.
- **Empfehlung:** `import pandas as pd` auf Modulebene verschieben (Datei hat bereits `from __future__ import annotations`, dann entfällt das Problem ganz), oder Annotation auf `Any` setzen.

### B. Unbenutzte lokale Variablen (25)

Nicht automatisch gefixt — kann beabsichtigt sein (Debug-Hilfe, zukünftige Verwendung). Top-Treffer:

- `routes/copy_trading.py` (4×): `except Exception as e:` wobei `e` nicht geloggt wird → Exception-Swallowing. Sollte mit `logger.exception()` geloggt werden.
- `tools/continuous_training.py:86-87`: ebenfalls `except Exception as e` mit unbenutztem `e` und `status`.
- `bot/executor.py:38`: `last_err` wird nie zurückgegeben/geloggt. Wahrscheinlich beabsichtigt, aber prüfen.
- `bot/executor.py:148`: `resp` wird gesetzt aber nie verwendet.
- `bot/engine.py:775`: `swarm = get_swarm()` ohne Nutzung.
- `bot/brain.py:782`: `evals` ohne Nutzung.
- `bot/strategies/stat_arb.py:165`: `pos` ohne Nutzung.

Vollständige Liste: siehe Ausgabe von `python3 -m pyflakes .`

---

## Verifikation

```bash
# Syntax-Check aller Dateien
find . -name "*.py" -not -path "./.venv/*" -not -path "./venv_local/*" \
  -not -path "*/__pycache__/*" -not -path "./archive/*" \
  -exec python3 -m py_compile {} \;
# → keine Fehler

# Geänderte Dateien
git diff --stat   # 55 Dateien, +72/-131 Zeilen
```

---

## Empfohlene nächste Schritte

1. `bot/engine.py:283` — Intent klären und Ternär vereinfachen.
2. `bot/executor.py:306` — `pd`-Import auf Modulebene ziehen.
3. `routes/copy_trading.py` — 4× Exception-Swallowing durch `logger.exception()` ersetzen.
4. Optional: `pylint` / `ruff` für tiefergehende Analyse (Komplexität, Sicherheit).
5. Unit-Tests laufen lassen: `pytest tests/` — bisher nicht ausgeführt, weil `.env.bot` evtl. benötigt wird.
