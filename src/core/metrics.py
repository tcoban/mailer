"""
Prometheus metrics definitions for KOFMailer.

Uses prometheus-client (lightweight, no extra infrastructure).
"""

from prometheus_client import Counter, Histogram, Gauge, Info


# ---------------------------------------------------------------------------
# Application info
# ---------------------------------------------------------------------------
app_info = Info("kofmailer", "KOFMailer application metadata")
app_info.info({"version": "0.1.0"})


# ---------------------------------------------------------------------------
# HTTP layer
# ---------------------------------------------------------------------------
http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"],
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)


# ---------------------------------------------------------------------------
# Message lifecycle
# ---------------------------------------------------------------------------
messages_accepted_total = Counter(
    "messages_accepted_total",
    "Messages accepted via POST /messages",
)

messages_sent_total = Counter(
    "messages_sent_total",
    "Messages successfully sent to provider",
    ["provider"],
)

messages_failed_total = Counter(
    "messages_failed_total",
    "Messages that failed permanently",
    ["reason"],
)

messages_retried_total = Counter(
    "messages_retried_total",
    "Messages scheduled for retry",
    ["provider"],
)


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------
dispatch_batch_duration_seconds = Histogram(
    "dispatch_batch_duration_seconds",
    "Time to process a single dispatch batch",
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
)

dispatch_batch_size = Histogram(
    "dispatch_batch_size",
    "Number of messages in each dispatch batch",
    buckets=[1, 2, 5, 10, 20, 50],
)

outbox_depth = Gauge(
    "outbox_depth",
    "Current number of entries in the outbox table (approximate)",
)


# ---------------------------------------------------------------------------
# Circuit Breaker
# ---------------------------------------------------------------------------
circuit_breaker_state = Gauge(
    "circuit_breaker_state",
    "Circuit breaker state (0=CLOSED, 1=OPEN, 2=HALF_OPEN)",
    ["provider"],
)

circuit_breaker_failure_rate = Gauge(
    "circuit_breaker_failure_rate",
    "Current failure rate in the sliding window",
    ["provider"],
)


# ---------------------------------------------------------------------------
# DLQ
# ---------------------------------------------------------------------------
dlq_entries_total = Counter(
    "dlq_entries_total",
    "Messages moved to DLQ",
)

dlq_replayed_total = Counter(
    "dlq_replayed_total",
    "Messages replayed from DLQ back to outbox",
)
