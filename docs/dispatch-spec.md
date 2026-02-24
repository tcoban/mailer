# Dispatch-Spezifikation

Diese Spezifikation beschreibt das verbindliche Dispatch-Verhalten für ausgehende E-Mails im Python-Rebuild.

## Datenbankstrategie (SQLAlchemy Async)

### SQL: `SELECT … FOR UPDATE SKIP LOCKED`
Der Dispatcher schützt konkurrierende Worker durch eine transaktionale Auswahl auf Basis von `SKIP LOCKED`.

**Vorgehen:**
1. Dynamische `batch_size` ermitteln (siehe Adaptive Throttling).
2. Jobs auswählen, die:
   - In der Tabelle `outbox` liegen.
   - `next_attempt_at <= NOW()` sind.
3. Zeilen per `with_for_update(skip_locked=True)` sperren.
4. Nachrichten parallel verarbeiten (`asyncio.gather`).
5. Transaktion COMMITten.

## Schema: `outbox`
Die Tabelle enthält folgende steuernde Felder:

| Feld | Typ | Bedeutung |
| --- | --- | --- |
| `retry_count` | `INTEGER` | Anzahl der bisherigen Versandversuche. |
| `next_attempt_at` | `TIMESTAMP` | Zeitpunkt für den nächsten erlaubten Versuch. |
| `last_attempt_at` | `TIMESTAMP` | Zeitpunkt des letzten Dispatch-Versuchs. |

## Backoff-Algorithmus
Der Backoff ist exponentiell ohne Jitter (Stand: Implementierung Phase 4).

### Formel
Für `retry_count = n` (nach Inkrement) gilt:
```
retry_after = BASE_BACKOFF * (2 ** (n - 1))
next_attempt_at = now + retry_after
```
*Hinweis: Der Provider kann diesen Wert im Header `Retry-After` explizit überschreiben.*

## Adaptive Throttling
Der Dispatcher passt seinen Durchsatz dynamisch an das Feedback des Providers (z. B. MS Graph 429) an:

| Event | Aktion |
| --- | --- |
| **HTTP 429** | `batch_size` halbieren, `poll_interval` verdoppeln. |
| **Erfolg** | `batch_size` schrittweise erhöhen, `poll_interval` reduzieren. |

Konstanten:
- `MAX_RETRIES`: 5
- `BASE_BACKOFF`: 30s
- `BATCH_SIZE` (Standard): 10

