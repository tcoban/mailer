# KOFMailer – Konsolidierter Architekturvorschlag (angenommen)

## Zielbild (Kernpunkte)
- **KOFMailer** als interner **K8s ClusterIP Service** im Namespace `surveyweb`.
- **Clients (SurveyWeb/CIRET/FOMO)** sprechen ausschließlich KOFMailer an:
  - `POST /messages` (schnelle Annahme ≤ 200 ms, asynchroner Versand)
  - `GET /messages/{id}` (Statusabfrage)
- **Asynchroner Versand** über Airflow-Trigger via **interne Admin-Endpoints**
  - `POST /internal/dispatch/batch` (Batch-Verarbeitung)
  - `POST /internal/dispatch/{id}` (Einzel-Reprocessing)
- **Statusquellen**
  - Dispatch-Ergebnis: `SENT`/`FAILED`
  - Provider-Webhooks: `DELIVERED`/`BOUNCED`

## Konsolidiertes Zustandsmodell
Verbindliche Zustände und Übergänge:
- **Zustände**: `QUEUED`, `SENT`, `DELIVERED`, `BOUNCED`, `FAILED`, `CANCELLED`, `RETRY_PENDING`
- **Übergänge**:
  - `QUEUED → SENT`
  - `SENT → DELIVERED | BOUNCED`
  - `QUEUED → CANCELLED` (nur vor Versand)
  - `QUEUED | SENT | RETRY_PENDING → FAILED` (finaler Fehler)
  - `SENT → RETRY_PENDING` (bei transientem Fehler nach Annahme, z. B. 429/5xx)

## Authentifizierung & Secrets
- **Apps → KOFMailer**: Keycloak OAuth2 (Client-Credentials), Scopes
  - `mail.send`, `mail.status:read`
- **Airflow → KOFMailer**: Scope `mailer.worker`
- **KOFMailer → MS Graph**: Client-Credentials via Vault (Rotation möglich), Details in `docs/ms-graph-adapter.md`

## Persistenz (PostgreSQL 14+ / Prisma)
- **Tabellen**:
  - `messages` (Payload + Metadaten)
  - `mail_outbox` (Queue/Dispatch-Status, Retry, Backoff)
  - `mail_status` (Status-Events)
  - `idempotency_keys` (Replay-Schutz)
- **Indizes**:
  - Composite auf `(status, nextAttemptAt)` für Dispatch-Performance

## API-Contract (OpenAPI-first)
- **`POST /messages`**
  - Validierung: `from`, mindestens ein `to`, `subject`, `body` (text oder html)
  - Attachments Base64URL, feste Limits (Einzel/Gesamt)
  - Antwort: `202 { messageId }`
  - Optional: `Idempotency-Key`
- **`GET /messages/{id}`**
  - Liefert konsistenten Status inkl. `lastUpdate`, optional `providerMessageId`, `details`

## Dispatch & Retry
- **Dispatch-Logik** nutzt `SELECT … FOR UPDATE SKIP LOCKED`.
- **Backoff**: Exponentiell mit Cap + `maxAttempts` → danach `FAILED`.
- **Drosselung** über Airflow Pools/Parallelität.

## Observability & Betrieb
- **PII-arme Logs**, Trace-ID in allen Requests.
- **Prometheus-Metriken**: accepted, sent, delivered, bounced, failed, retry_pending.
- **Probes**: Liveness/Readiness (inkl. DB-Check).
- **HPA/PDB** & NetworkPolicies (nur Apps + Airflow).

## Ausdrückliche Annahme der User Stories
### Phase 1 (MVP, verpflichtend)
- **US-1** Datenmodell mit Prisma/PostgreSQL (inkl. JSONB, Indizes, Migration)
- **US-2** `POST /messages` (≤ 200 ms, Scope `mail.send`)
- **US-4** Dispatch via `/internal/dispatch` mit SKIP LOCKED
- **US-5** MS Graph Adapter (429/5xx/4xx Mapping)
- **US-7** Idempotenz (Idempotency-Key, Hash, Replay/Conflict)
- **US-8** Auth Middleware (Scopes: `mail.send`, `mail.status:read`, `mailer.worker`)
- **US-6** Webhooks Graph → `DELIVERED`/`BOUNCED`
- **US-9/11** Observability & Packaging
- **US-10** Airflow DAG (minütlicher Trigger)

### Phase 2 (nach MVP)
- **US-12** `GET /messages` (Listenansicht/Filter/Pagination)
- **US-13** Detaillierte Fehlergründe
- **US-14** `DELETE /messages/{id}` (Cancel bei `QUEUED`)
- **US-15** Callback Notification (Push to App)

## Vorteile des konsolidierten Vorschlags
- **Konsistentes Statusmodell** über API/DB/Worker hinweg → weniger Fehlerfälle.
- **Robuste Idempotenz** → verhindert Doppelversand bei Retries.
- **Skalierbarkeit** durch SKIP LOCKED + Airflow Parallelisierung.
- **Klare MVP-Grenze** reduziert Time-to-Ship.

## Nachteile / Trade-offs
- **Höhere Komplexität** (State-Machine, Idempotenz, Backoff-Logik).
- **Mehr DB-Last** durch Status- und Idempotenz-Tracking.
- **Airflow als zentrale Abhängigkeit** erfordert Betriebskompetenz.

## Definition of Ready (ausdrücklich bestätigt)
- Attachment-Limits, Timeouts, Backoff-Stufen, maxAttempts fixiert.
- Keycloak-Clients/Scopes existieren; Vault-Pfade definiert.
- Tabellen/Indizes/State-Transitions freigegeben.
- Namespace & NetworkPolicies freigegeben.

## Definition of Done (ausdrücklich bestätigt)
- `POST /messages` ≤ 200 ms, `202` mit `messageId`.
- Dispatch innerhalb 60 s → `SENT` oder `FAILED`.
- Webhooks liefern `DELIVERED/BOUNCED` deterministisch.
- Idempotenz aktiv (Replay/Conflict verlässlich).
- AuthZ via Scopes; Secrets ausschließlich aus Vault.
- Metriken/Alarme aktiv, Logs PII-arm.
- Pilot-Flows migriert, Messwerte dokumentiert.

## Annahme: Optimierter Vorschlag (konsistent mit Stories)
Der optimierte Vorschlag wird vollständig angenommen und ist fortan verbindlich
für Architektur, API-Vertrag und Zustandsmodell.

## Annahme: Optimierte Umsetzung in Phasen
Die Phasenaufteilung wird angenommen:
- **Phase 1 (MVP)** wie oben beschrieben.
- **Phase 2** wie oben beschrieben.
