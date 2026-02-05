# MS Graph Adapter

## Ziel
Der Mailer nutzt Microsoft Graph als Service-Provider für den tatsächlichen Versand.
Dieser Adapter beschreibt Authentifizierung, Request-Formate, Fehlerbehandlung und
die Abbildung auf das interne Statusmodell.

## Authentifizierung (Client Credentials)
Der Mailer authentifiziert sich über OAuth2 Client-Credentials gegen den Tenant.

**Benötigte Konfiguration:**
- `MS_GRAPH_TENANT_ID`
- `MS_GRAPH_CLIENT_ID`
- `MS_GRAPH_CLIENT_SECRET`
- `MS_GRAPH_SCOPE` (Default: `https://graph.microsoft.com/.default`)
- `MS_GRAPH_BASE_URL` (Default: `https://graph.microsoft.com/v1.0`)

**Token-Flow:**
`POST https://login.microsoftonline.com/{tenantId}/oauth2/v2.0/token`
mit `client_id`, `client_secret`, `scope` und `grant_type=client_credentials`.

Tokens werden im Worker gecached und vor Ablauf erneuert.

## Versand (SendMail)
Für jede Nachricht wird Graph `sendMail` aufgerufen:

```
POST {MS_GRAPH_BASE_URL}/users/{from}/sendMail
Content-Type: application/json
Authorization: Bearer <token>
Prefer: outlook.body-content-type="html"
```

**Body (Beispiel):**
```json
{
  "message": {
    "subject": "Subject",
    "body": {
      "contentType": "HTML",
      "content": "<p>Hello</p>"
    },
    "from": {
      "emailAddress": {
        "address": "sender@example.com"
      }
    },
    "toRecipients": [
      { "emailAddress": { "address": "to@example.com" } }
    ],
    "ccRecipients": [],
    "bccRecipients": [],
    "attachments": [
      {
        "@odata.type": "#microsoft.graph.fileAttachment",
        "name": "invoice.pdf",
        "contentType": "application/pdf",
        "contentBytes": "base64..."
      }
    ]
  },
  "saveToSentItems": false
}
```

**Hinweise:**
- `from` MUSS ein Mailbox-Objekt im Tenant sein, das `sendMail` im App-Kontext erlaubt.
- `saveToSentItems=false` verhindert Postfach-Wachstum (kann per Config überschrieben werden).
- Attachments sind auf Graph-Limits zu beschränken; der Mailer validiert vor Versand.

## Provider Message ID
Graph `sendMail` liefert keinen Message-ID-Body zurück. Für `provider_message_id`
werden Request-IDs genutzt:
- `request-id` (Header) als primäre ID
- `client-request-id` falls gesetzt

Diese IDs dienen der Korrelation in Logs/Tracing.

## Fehlerabbildung auf Statusmodell
Der Adapter mappt Graph-Responses wie folgt:

| Graph Response | Interner Status | status_reason |
| --- | --- | --- |
| `202 Accepted` | `SENT` | `GRAPH_ACCEPTED` |
| `429 Too Many Requests` | `RETRY_PENDING` | `GRAPH_RATE_LIMITED` |
| `5xx` | `RETRY_PENDING` | `GRAPH_PROVIDER_5XX` |
| `4xx` (außer 429) | `FAILED` | `GRAPH_PROVIDER_4XX` |

**Retry-Backoff** folgt der Dispatch-Spezifikation in `docs/dispatch-spec.md`.

## Webhooks (Delivery)
Graph-Webhooks liefern `DELIVERED` und `BOUNCED` via Status-Events. Der Mailer
validiert Webhook-Signaturen und mappt Provider-Events auf das Statusmodell.

