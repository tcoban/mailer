# Phasen-Entscheidungen

## List-Endpoint

**Entscheidung:** Der List-Endpoint ist Teil von **Phase 1 (MVP)**.

### Filters (Query-Parameter)

- `status`: `QUEUED | RETRY_PENDING | SENT | DELIVERED | BOUNCED | FAILED | CANCELLED`
- `recipient`: Volltext/Teilstring-Suche über Empfänger-Adresse
- `campaign_id`: exakte Übereinstimmung
- `tag`: exakte Übereinstimmung (mehrfach möglich)
- `created_from` / `created_to`: ISO-8601 Zeitfenster
- `scheduled_from` / `scheduled_to`: ISO-8601 Zeitfenster

### Pagination

- Cursor-basierte Pagination über `cursor` + `limit`
- `limit` Default: `50`, Maximum: `200`
- Sortierung fix: `created_at` absteigend (neuste zuerst)
- Response enthält `next_cursor` (oder `null`, wenn Ende erreicht)

### Response-Schema (JSON)

```json
{
  "data": [
    {
      "id": "msg_123",
      "status": "SENT",
      "subject": "Welcome",
      "from": "no-reply@example.com",
      "to": ["user@example.com"],
      "campaign_id": "cmp_456",
      "tags": ["onboarding"],
      "created_at": "2024-05-01T12:00:00Z",
      "scheduled_at": "2024-05-01T12:05:00Z",
      "sent_at": "2024-05-01T12:05:30Z",
      "failed_reason": null,
      "metadata": {
        "provider": "ses",
        "message_id": "000000000000"
      }
    }
  ],
  "next_cursor": "eyJjcmVhdGVkX2F0IjoiMjAyNC0wNS0wMVQxMjowMDowMFoifQ=="
}
```
