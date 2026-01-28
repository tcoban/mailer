# Unified Message Status Model

## Statuses

| Status | Meaning | Terminal | Retryable |
| --- | --- | --- | --- |
| QUEUED | Message accepted and waiting for provider submission. | No | Yes |
| RETRY_PENDING | Temporary failure; retry scheduled. | No | Yes |
| SENT | Provider accepted the message for delivery. | No | No |
| DELIVERED | Recipient confirmed delivery. | Yes | No |
| BOUNCED | Permanent bounce reported by provider. | Yes | No |
| FAILED | Permanent failure before delivery. | Yes | No |
| CANCELLED | Message intentionally stopped before delivery. | Yes | No |

## Allowed Transitions

| From | To |
| --- | --- |
| QUEUED | SENT, RETRY_PENDING, FAILED, CANCELLED |
| RETRY_PENDING | SENT, FAILED, CANCELLED |
| SENT | DELIVERED, BOUNCED, FAILED |
| DELIVERED | *(none)* |
| BOUNCED | *(none)* |
| FAILED | *(none)* |
| CANCELLED | *(none)* |

## Notes

- Status updates are monotonic: once a terminal state is reached, no further transitions are permitted.
- Provider errors must map to RETRY_PENDING for temporary failures and FAILED for permanent failures.
