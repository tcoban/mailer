# Dispatch-Spezifikation

## Ziel
Diese Spezifikation beschreibt das verbindliche Dispatch-Verhalten für ausgehende E-Mails. Sie definiert die Datenbankstrategie für die Auswahl von Jobs, die notwendigen Felder im `mail_outbox`-Schema, den Backoff-Algorithmus sowie Konfigurationsparameter.

## Datenbankstrategie (SQL/Prisma)

### SQL: `SELECT … FOR UPDATE SKIP LOCKED`
Der Dispatcher MUSS konkurrierende Worker durch eine transaktionale Auswahl schützen.

**Normatives Vorgehen:**
1. Eine Transaktion BEGINnen.
2. Eine begrenzte Menge von Jobs auswählen, die
   - `status = 'queued'` sind,
   - `nextAttemptAt <= NOW()` sind,
   - `retryCount < maxAttempts` erfüllen.
3. Die ausgewählten Zeilen per `FOR UPDATE SKIP LOCKED` sperren.
4. Innerhalb derselben Transaktion den Status auf `dispatching` (oder `in_flight`) setzen und `lastAttemptAt` aktualisieren.
5. Transaktion COMMITten.

**Beispiel (PostgreSQL):**
```sql
BEGIN;

WITH candidates AS (
  SELECT id
  FROM mail_outbox
  WHERE status = 'queued'
    AND next_attempt_at <= NOW()
    AND retry_count < :max_attempts
  ORDER BY next_attempt_at ASC, id ASC
  LIMIT :batch_size
  FOR UPDATE SKIP LOCKED
)
UPDATE mail_outbox
SET status = 'dispatching',
    last_attempt_at = NOW()
FROM candidates
WHERE mail_outbox.id = candidates.id
RETURNING mail_outbox.*;

COMMIT;
```

### Prisma-Strategie
Prisma unterstützt `FOR UPDATE SKIP LOCKED` nicht direkt über die Query-API. Deshalb MUSS die Auswahl via `prisma.$transaction()` und `prisma.$queryRaw` erfolgen.

**Empfehlung:**
- Verwende eine einzelne `UPDATE … FROM candidates`-Query (wie oben), um Auswahl + Statuswechsel atomar abzubilden.
- Stelle sicher, dass die Isolationsebene mindestens `READ COMMITTED` ist.

## Schema: `mail_outbox`
Die Tabelle MUSS folgende Felder (zusätzlich zu bestehenden) enthalten:

| Feld            | Typ (Beispiel)        | Bedeutung |
|-----------------|-----------------------|-----------|
| `retryCount`    | `INTEGER NOT NULL`    | Anzahl der bisherigen Versandversuche. Beginnt bei 0. |
| `nextAttemptAt` | `TIMESTAMP NOT NULL`  | Zeitpunkt, ab dem der nächste Versuch erlaubt ist. |
| `lastError`     | `TEXT NULL`           | Letzte Fehlermeldung (kompakt, ggf. gekürzt). |
| `lastAttemptAt` | `TIMESTAMP NULL`      | Zeitpunkt des letzten Dispatch-Versuchs. |

Zusätzlich gelten folgende Regeln:
- `retryCount` wird bei jedem fehlgeschlagenen Versuch um 1 erhöht.
- `lastAttemptAt` wird bei jedem Versuch gesetzt (auch bei Erfolg).
- `lastError` wird bei Erfolg geleert oder auf `NULL` gesetzt.

## Backoff-Algorithmus und Konfiguration
Der Backoff ist exponentiell mit optionalem Jitter.

### Formel
Für `retryCount = n` (nach dem Inkrement) gilt:

```
base = DISPATCH_BACKOFF_BASE_SECONDS
max = DISPATCH_BACKOFF_MAX_SECONDS
jitter = DISPATCH_BACKOFF_JITTER (0.0–1.0)

raw = base * 2^n
capped = min(raw, max)
random_factor = 1 ± (jitter * rand())
backoff_seconds = capped * random_factor

nextAttemptAt = now + backoff_seconds
```

Wenn `jitter = 0`, ist der Backoff deterministisch.

### Konfigurationsparameter
Die Konfiguration MUSS folgende Parameter bereitstellen:

| Parameter | Typ | Default | Beschreibung |
|-----------|-----|---------|--------------|
| `DISPATCH_MAX_ATTEMPTS` | Integer | `5` | Maximale Anzahl an Dispatch-Versuchen pro Mail. |
| `DISPATCH_BACKOFF_BASE_SECONDS` | Integer | `30` | Basisintervall für exponentiellen Backoff. |
| `DISPATCH_BACKOFF_MAX_SECONDS` | Integer | `3600` | Obergrenze für Backoff. |
| `DISPATCH_BACKOFF_JITTER` | Float | `0.2` | Jitter-Faktor (0.0–1.0). |

**Regel:** Sobald `retryCount >= DISPATCH_MAX_ATTEMPTS`, MUSS der Status auf `failed` gesetzt werden, und es dürfen keine weiteren Versuche stattfinden.
