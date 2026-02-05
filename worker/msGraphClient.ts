import { MessageStatus } from "../src/status";

export type GraphConfig = {
  tenantId: string;
  clientId: string;
  clientSecret: string;
  scope: string;
  baseUrl: string;
  timeoutMs: number;
  saveToSentItems: boolean;
};

export type GraphRecipient = {
  address: string;
  name?: string;
};

export type GraphAttachment = {
  name: string;
  contentType: string;
  contentBytes: string;
};

export type GraphMessageInput = {
  subject: string;
  from: GraphRecipient;
  to: GraphRecipient[];
  cc?: GraphRecipient[];
  bcc?: GraphRecipient[];
  replyTo?: GraphRecipient[];
  body: {
    contentType: "HTML" | "Text";
    content: string;
  };
  attachments?: GraphAttachment[];
};

export type GraphSendResult = {
  status: MessageStatus;
  reason: string;
  providerMessageId: string | null;
  retryAfterSeconds: number | null;
  rawStatus: number | null;
};

type TokenCache = {
  accessToken: string;
  expiresAt: number;
};

const DEFAULT_SCOPE = "https://graph.microsoft.com/.default";
const DEFAULT_BASE_URL = "https://graph.microsoft.com/v1.0";
const DEFAULT_TIMEOUT_MS = 15_000;

export function loadGraphConfig(env: NodeJS.ProcessEnv = process.env): GraphConfig {
  const tenantId = env.MS_GRAPH_TENANT_ID ?? "";
  const clientId = env.MS_GRAPH_CLIENT_ID ?? "";
  const clientSecret = env.MS_GRAPH_CLIENT_SECRET ?? "";
  if (!tenantId || !clientId || !clientSecret) {
    throw new Error("Missing MS Graph credentials (tenant/client/clientSecret).");
  }
  return {
    tenantId,
    clientId,
    clientSecret,
    scope: env.MS_GRAPH_SCOPE ?? DEFAULT_SCOPE,
    baseUrl: env.MS_GRAPH_BASE_URL ?? DEFAULT_BASE_URL,
    timeoutMs: Number(env.MS_GRAPH_TIMEOUT_MS ?? DEFAULT_TIMEOUT_MS),
    saveToSentItems: env.MS_GRAPH_SAVE_TO_SENT_ITEMS === "true",
  };
}

export class MsGraphClient {
  private readonly config: GraphConfig;
  private tokenCache: TokenCache | null = null;

  constructor(config: GraphConfig) {
    this.config = config;
  }

  async sendMail(message: GraphMessageInput): Promise<GraphSendResult> {
    const token = await this.getAccessToken();
    const url = `${this.config.baseUrl}/users/${encodeURIComponent(
      message.from.address,
    )}/sendMail`;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), this.config.timeoutMs);

    try {
      const response = await fetch(url, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
          Prefer: 'outlook.body-content-type="html"',
        },
        body: JSON.stringify({
          message: buildGraphMessage(message),
          saveToSentItems: this.config.saveToSentItems,
        }),
        signal: controller.signal,
      });

      const providerMessageId = extractProviderMessageId(response.headers);
      const retryAfterSeconds = parseRetryAfter(response.headers.get("retry-after"));
      return mapGraphResponse(response.status, providerMessageId, retryAfterSeconds);
    } catch (error) {
      const reason =
        error instanceof Error && error.name === "AbortError"
          ? "GRAPH_TIMEOUT"
          : "GRAPH_NETWORK_ERROR";
      return {
        status: MessageStatus.RetryPending,
        reason,
        providerMessageId: null,
        retryAfterSeconds: null,
        rawStatus: null,
      };
    } finally {
      clearTimeout(timeout);
    }
  }

  private async getAccessToken(): Promise<string> {
    if (this.tokenCache && this.tokenCache.expiresAt > Date.now() + 30_000) {
      return this.tokenCache.accessToken;
    }

    const url = `https://login.microsoftonline.com/${this.config.tenantId}/oauth2/v2.0/token`;
    const params = new URLSearchParams({
      client_id: this.config.clientId,
      client_secret: this.config.clientSecret,
      scope: this.config.scope,
      grant_type: "client_credentials",
    });

    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: params.toString(),
    });

    if (!response.ok) {
      throw new Error(`MS Graph token request failed (${response.status}).`);
    }
    const payload = (await response.json()) as {
      access_token: string;
      expires_in: number;
    };
    this.tokenCache = {
      accessToken: payload.access_token,
      expiresAt: Date.now() + payload.expires_in * 1000,
    };
    return payload.access_token;
  }
}

function buildGraphMessage(message: GraphMessageInput) {
  return {
    subject: message.subject,
    body: {
      contentType: message.body.contentType,
      content: message.body.content,
    },
    from: { emailAddress: toEmailAddress(message.from) },
    toRecipients: message.to.map(toRecipient),
    ccRecipients: message.cc?.map(toRecipient) ?? [],
    bccRecipients: message.bcc?.map(toRecipient) ?? [],
    replyTo: message.replyTo?.map(toRecipient) ?? [],
    attachments: message.attachments?.map((attachment) => ({
      "@odata.type": "#microsoft.graph.fileAttachment",
      name: attachment.name,
      contentType: attachment.contentType,
      contentBytes: attachment.contentBytes,
    })),
  };
}

function toRecipient(recipient: GraphRecipient) {
  return { emailAddress: toEmailAddress(recipient) };
}

function toEmailAddress(recipient: GraphRecipient) {
  return {
    address: recipient.address,
    name: recipient.name,
  };
}

function extractProviderMessageId(headers: Headers): string | null {
  return headers.get("request-id") ?? headers.get("client-request-id");
}

function parseRetryAfter(value: string | null): number | null {
  if (!value) {
    return null;
  }
  const parsed = Number(value);
  if (Number.isFinite(parsed)) {
    return parsed;
  }
  const date = Date.parse(value);
  if (Number.isNaN(date)) {
    return null;
  }
  return Math.max(0, Math.round((date - Date.now()) / 1000));
}

function mapGraphResponse(
  status: number,
  providerMessageId: string | null,
  retryAfterSeconds: number | null,
): GraphSendResult {
  if (status === 202) {
    return {
      status: MessageStatus.Sent,
      reason: "GRAPH_ACCEPTED",
      providerMessageId,
      retryAfterSeconds,
      rawStatus: status,
    };
  }
  if (status === 429) {
    return {
      status: MessageStatus.RetryPending,
      reason: "GRAPH_RATE_LIMITED",
      providerMessageId,
      retryAfterSeconds,
      rawStatus: status,
    };
  }
  if (status >= 500) {
    return {
      status: MessageStatus.RetryPending,
      reason: "GRAPH_PROVIDER_5XX",
      providerMessageId,
      retryAfterSeconds,
      rawStatus: status,
    };
  }
  return {
    status: MessageStatus.Failed,
    reason: "GRAPH_PROVIDER_4XX",
    providerMessageId,
    retryAfterSeconds,
    rawStatus: status,
  };
}
