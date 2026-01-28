# Architektur

## Idempotency

### Header

Clients **müssen** bei allen schreibenden Requests (z. B. `POST`, `PUT`, `PATCH`) den Header `Idempotency-Key` senden.

Beispiel:

```
Idempotency-Key: 7f2d9c6a-0a78-4d2d-9db0-8f6c2a9b0e0b
```

### Verhalten A/B/C

| Fall | Beschreibung | Verhalten |
| --- | --- | --- |
| A | Neuer Schlüssel | Request wird normal verarbeitet. Response (Status + Body) wird gemeinsam mit Request-Hash gespeichert. |
| B | Schlüssel existiert **und** Request-Hash identisch | Gespeicherte Response wird **ohne erneute Verarbeitung** zurückgegeben (`Idempotency-Replayed: true`). |
| C | Schlüssel existiert **aber** Request-Hash abweichend | Request wird **abgelehnt** (`409 Conflict`) und nicht verarbeitet. |

### Response-Verhalten bei Replay/Conflict

**Replay (Fall B)**
- HTTP-Status: identisch zum ursprünglichen Request (z. B. `201 Created`).
- Body: identisch zum ursprünglichen Body.
- Zusätzlicher Header: `Idempotency-Replayed: true`.

**Conflict (Fall C)**
- HTTP-Status: `409 Conflict`.
- Body (Problem+JSON):

```json
{
  "type": "https://docs.mailer.example/errors/idempotency-conflict",
  "title": "Idempotency conflict",
  "status": 409,
  "detail": "Idempotency-Key wurde bereits mit anderer Payload verwendet.",
  "instance": "/v1/messages"
}
```

### Datenhaltung & Cleanup

Idempotency-Einträge werden mit einem **TTL von 24 Stunden** persistiert.
Ein täglicher Cleanup-Job (z. B. per Cron oder Worker-Scheduler) löscht abgelaufene Einträge.

### Logging & Tracing

- Metrik/Log-Events (structured logging):
  - `idempotency.miss` (Fall A)
  - `idempotency.hit` (Fall B)
  - `idempotency.conflict` (Fall C)
- Tracing-Attribute (OpenTelemetry):
  - `idempotency.key`
  - `idempotency.result` (`miss|hit|conflict`)
  - `idempotency.request_hash`

Die Events werden auf INFO-Level geloggt, damit Idempotency-Hits bei Retry-Last sichtbar sind.
