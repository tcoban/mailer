import { MessageStatus, isValidTransition } from "../src/status";

type ProviderStatus =
  | "queued"
  | "accepted"
  | "sent"
  | "delivered"
  | "bounced"
  | "permanent_failure"
  | "temporary_failure"
  | "cancelled";

const providerToMessageStatus: Record<ProviderStatus, MessageStatus> = {
  queued: MessageStatus.Queued,
  accepted: MessageStatus.Sent,
  sent: MessageStatus.Sent,
  delivered: MessageStatus.Delivered,
  bounced: MessageStatus.Bounced,
  permanent_failure: MessageStatus.Failed,
  temporary_failure: MessageStatus.RetryPending,
  cancelled: MessageStatus.Cancelled,
};

export function mapProviderStatus(
  providerStatus: ProviderStatus,
  currentStatus: MessageStatus,
): MessageStatus {
  const nextStatus = providerToMessageStatus[providerStatus];
  if (!isValidTransition(currentStatus, nextStatus) && currentStatus !== nextStatus) {
    throw new Error(
      `Invalid status transition from ${currentStatus} to ${nextStatus} for provider status ${providerStatus}.`,
    );
  }
  return nextStatus;
}

export function mapProviderError(
  providerStatus: ProviderStatus,
  errorCode?: string,
): { status: MessageStatus; reason: string } {
  const status = providerToMessageStatus[providerStatus];
  if (status === MessageStatus.RetryPending) {
    return { status, reason: errorCode ?? "TEMPORARY_PROVIDER_FAILURE" };
  }
  if (status === MessageStatus.Failed) {
    return { status, reason: errorCode ?? "PERMANENT_PROVIDER_FAILURE" };
  }
  return { status, reason: errorCode ?? "PROVIDER_UPDATE" };
}
