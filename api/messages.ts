import { MessageStatus } from "../src/status";

type MessageRecord = {
  id: string;
  status: MessageStatus;
  statusReason?: string | null;
  providerMessageId?: string | null;
  createdAt: string;
  updatedAt: string;
};

type MessageResponse = {
  id: string;
  status: MessageStatus;
  status_reason?: string | null;
  provider_message_id?: string | null;
  created_at: string;
  updated_at: string;
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
