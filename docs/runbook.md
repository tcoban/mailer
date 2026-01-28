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

- **Stuck messages**: QUEUED or RETRY_PENDING older than 15 minutes.
- **Provider failures**: FAILED rate > 2% or BOUNCED rate > 5% in 1 hour.
