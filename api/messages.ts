import { MessageStatus } from "../src/status";

type MessageRecord = {
  id: string;
  status: MessageStatus;
  statusReason?: string | null;
  providerMessageId?: string | null;
  createdAt: string;
  updatedAt: string;
};

type MessageListRecord = {
  id: string;
  status: MessageStatus;
  subject: string;
  from: string;
  to: string[];
  campaignId?: string | null;
  tags?: string[] | null;
  createdAt: string;
  scheduledAt?: string | null;
  sentAt?: string | null;
  failedReason?: string | null;
  metadata?: Record<string, unknown> | null;
};

type MessageResponse = {
  id: string;
  status: MessageStatus;
  status_reason?: string | null;
  provider_message_id?: string | null;
  created_at: string;
  updated_at: string;
};

type MessageListItem = {
  id: string;
  status: MessageStatus;
  subject: string;
  from: string;
  to: string[];
  campaign_id?: string | null;
  tags?: string[] | null;
  created_at: string;
  scheduled_at?: string | null;
  sent_at?: string | null;
  failed_reason?: string | null;
  metadata?: Record<string, unknown> | null;
};

type MessageListResponse = {
  data: MessageListItem[];
  next_cursor: string | null;
};

export function mapMessageResponse(record: MessageRecord): MessageResponse {
  return {
    id: record.id,
    status: record.status,
    status_reason: record.statusReason ?? null,
    provider_message_id: record.providerMessageId ?? null,
    created_at: record.createdAt,
    updated_at: record.updatedAt,
  };
}

export function mapMessageListItem(record: MessageListRecord): MessageListItem {
  return {
    id: record.id,
    status: record.status,
    subject: record.subject,
    from: record.from,
    to: record.to,
    campaign_id: record.campaignId ?? null,
    tags: record.tags ?? null,
    created_at: record.createdAt,
    scheduled_at: record.scheduledAt ?? null,
    sent_at: record.sentAt ?? null,
    failed_reason: record.failedReason ?? null,
    metadata: record.metadata ?? null,
  };
}

export function mapMessageListResponse(
  records: MessageListRecord[],
  nextCursor?: string | null,
): MessageListResponse {
  return {
    data: records.map(mapMessageListItem),
    next_cursor: nextCursor ?? null,
  };
}
