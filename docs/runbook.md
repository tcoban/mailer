# Mailer Runbook

## Message Status Semantics

The API, database, and worker share the unified status model defined in `docs/status-model.md`.

### Operational Guidance

- **QUEUED / RETRY_PENDING**
  - Worker retries are allowed only from these statuses.
  - Investigate high RETRY_PENDING counts for provider latency or outages.
- **SENT**
  - Provider accepted; delivery confirmation pending.
  - If messages remain in SENT for extended periods, check provider webhooks.
- **DELIVERED / BOUNCED / FAILED / CANCELLED**
  - Terminal. No further transitions permitted.
  - Use status_reason to distinguish between permanent failure causes.

### Alerts

- **Stuck messages**: QUEUED oder RETRY_PENDING older than 15 minutes.
- **Provider failures**: FAILED rate > 2% oder BOUNCED rate > 5% in 1 hour.

## Operational Procedures

### Docker Operations
- **Start Stack**: `docker compose up -d`
- **View Logs**: `docker compose logs -f app`
- **Rebuild**: `docker compose up --build`

### DLQ Management
When a message enters the Dead Letter Queue (DLQ):
1. Investigate the `status_reason` via the Admin API or DB.
2. Resolve the underlying issue (e.g., provider credentials, invalid recipient).
3. Replay the message using the Admin API:
   - Single: `POST /v1/admin/dlq/{id}/replay`
   - Bulk: `POST /v1/admin/dlq/replay-all`

