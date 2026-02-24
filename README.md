# KOFMailer

KOFMailer is a high-performance, spec-first mail orchestration service built with Python, FastAPI, and SQLAlchemy. It is designed for reliability, scalability, and ease of deployment.

## 🚀 Key Features

- **Multi-Provider Support**: Built-in adapter for MS Graph, with a standardized interface for adding more.
- **Advanced Reliability**:
    - **Outbox Pattern**: Ensures message persistence before dispatch.
    - **Adaptive Throttling**: Intelligently handles provider rate limits (e.g., MS Graph 429).
    - **Circuit Breaker**: Prevents cascading failures during provider outages.
    - **Dead Letter Queue (DLQ)**: Robust handling and re-processing of failed messages.
- **Secure by Design**: PII encryption at rest and signed webhook verification.
- **Production Ready**: Full Docker/Docker Compose support, Prometheus metrics, and structured logging.

## 🛠️ Quick Start

### Prerequisites
- Docker & Docker Compose
- Python 3.11+ (for local development)

### One-Command Setup
```powershell
docker compose up --build
```

### Local Development
1. **Install Dependencies**:
   ```bash
   pip install -e ".[dev]"
   ```
2. **Environment Setup**:
   Copy `.env.example` to `.env` and fill in your secrets.
3. **Run Migrations**:
   ```bash
   alembic upgrade head
   ```
4. **Start API**:
   ```bash
   uvicorn src.main:app --reload
   ```

## 📚 Documentation

Detailed documentation is available in the `docs/` directory:
- [Architecture](docs/architecture.md)
- [Dispatch Specification](docs/dispatch-spec.md)
- [Status Model](docs/status-model.md)
- [MS Graph Adapter](docs/ms-graph-adapter.md)
- [Runbook](docs/runbook.md)

## 🧪 Testing

Run the full test suite with coverage:
```bash
pytest --cov=src
```

---
Built by the KOF Team.
