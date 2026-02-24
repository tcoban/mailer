# Architektur

KOFMailer ist als zustandsloser Microservice in Python (FastAPI) implementiert. Er nutzt eine PostgreSQL-Datenbank für Persistenz (Outbox-Pattern) und Redis für Idempotency-Caching und Locks.

## Datenfluss & Komponenten

- **API Layer (FastAPI)**: Empfängt Requests, validiert Payloads (Pydantic), prüft Idempotency und schreibt Nachrichten in die `outbox`.
- **Worker Layer (Dispatcher)**: Ein Hintergrund-Task, der innerhalb des FastAPI-Lifesycles läuft. Er pollt die `outbox` mittels `SKIP LOCKED`, nutzt Circuit Breaker pro Provider und führt den Versand über Adapter aus.
- **Database (Postgres)**: Dient als zuverlässiger Message-Speicher. `AsyncPG` wird als Treiber für maximale Performance genutzt.
- **Cache (Redis)**: Speichert Idempotency-Responses (TTL 24h) und dient optional als Distributed Lock Provider.

## Idempotency

### Header
Clients **müssen** bei allen schreibenden Requests den Header `Idempotency-Key` (UUID) senden.

### Verhalten
Die Idempotency-Logik ist in `src/core/idempotency.py` implementiert:
1. **Miss**: Schlüssel unbekannt -> Request verarbeiten, Response in Redis + DB speichern.
2. **Hit**: Schlüssel bekannt + Hash identisch -> Gespeicherte Response zurückgeben (`Idempotency-Replayed: true`).
3. **Conflict**: Schlüssel bekannt + Hash abweichend -> `409 Conflict`.

## Background Worker Integration

Der `Dispatcher` wird beim Anwendungsstart über den FastAPI `lifespan` Kontextmanager gestartet:
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    dispatch_task = asyncio.create_task(dispatcher.run_loop())
    yield
    dispatch_task.cancel()
```
Dies stellt sicher, dass der Worker sauber mit dem Webserver startet und stoppt.

## MS Graph Integration
Details zu Request-Formaten und Fehlerbehandlung siehe `docs/ms-graph-adapter.md`.

