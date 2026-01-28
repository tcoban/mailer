# /internal/dispatch API

## Zweck
Der Endpunkt löst das Dispatching einer Batch von E-Mails aus und gibt die ausgewählten Jobs zurück. Die Auswahllogik richtet sich nach der Dispatch-Spezifikation.

## Request
```
POST /internal/dispatch
Content-Type: application/json
```

### Body
| Feld | Typ | Pflicht | Beschreibung |
|------|-----|---------|--------------|
| `batchSize` | Integer | nein | Maximale Anzahl von Mails, die pro Aufruf gelockt und dispatcht werden. Default: 50. |
| `dryRun` | Boolean | nein | Wenn `true`, nur Auswahl simulieren (keine Statusänderung). Default: `false`. |

**Beispiel:**
```json
{
  "batchSize": 25,
  "dryRun": false
}
```

## Response

### Erfolg (200)
```json
{
  "dispatched": 25,
  "maxAttempts": 5,
  "items": [
    {
      "id": "outbox_123",
      "retryCount": 2,
      "nextAttemptAt": "2024-07-20T12:30:00Z",
      "lastAttemptAt": "2024-07-20T12:00:00Z"
    }
  ]
}
```

**Felder:**
- `dispatched`: Anzahl der tatsächlich gelockten und dispatchten Items.
- `maxAttempts`: Aktueller Konfigurationswert.
- `items`: Liste der Items, die in der aktuellen Transaktion verarbeitet wurden.

### Kein Workload (200)
```json
{
  "dispatched": 0,
  "maxAttempts": 5,
  "items": []
}
```

## Fehlercodes

| Code | Bedeutung | Ursache |
|------|----------|--------|
| `400` | Invalid Request | Ungültige Body-Daten (z. B. `batchSize <= 0`). |
| `409` | Dispatch Conflict | Datenbank-Fehler beim Locking/Transaktion, oder konkurrierender Prozess. |
| `429` | Too Many Requests | Optional, wenn der Endpunkt gerate-limited wird. |
| `500` | Internal Error | Unerwarteter Fehler im Dispatch-Prozess. |

### Fehlerformat
```json
{
  "error": {
    "code": "DISPATCH_INVALID_REQUEST",
    "message": "batchSize must be a positive integer",
    "details": {
      "field": "batchSize"
    }
  }
}
```

**Code-Konvention:**
- `DISPATCH_INVALID_REQUEST` (HTTP 400)
- `DISPATCH_CONFLICT` (HTTP 409)
- `DISPATCH_RATE_LIMITED` (HTTP 429)
- `DISPATCH_INTERNAL_ERROR` (HTTP 500)
