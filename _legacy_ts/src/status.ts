export enum MessageStatus {
  Queued = "QUEUED",
  RetryPending = "RETRY_PENDING",
  Sent = "SENT",
  Delivered = "DELIVERED",
  Bounced = "BOUNCED",
  Failed = "FAILED",
  Cancelled = "CANCELLED",
}

export const statusTransitions: Record<MessageStatus, MessageStatus[]> = {
  [MessageStatus.Queued]: [
    MessageStatus.Sent,
    MessageStatus.RetryPending,
    MessageStatus.Failed,
    MessageStatus.Cancelled,
  ],
  [MessageStatus.RetryPending]: [
    MessageStatus.Sent,
    MessageStatus.Failed,
    MessageStatus.Cancelled,
  ],
  [MessageStatus.Sent]: [
    MessageStatus.Delivered,
    MessageStatus.Bounced,
    MessageStatus.Failed,
  ],
  [MessageStatus.Delivered]: [],
  [MessageStatus.Bounced]: [],
  [MessageStatus.Failed]: [],
  [MessageStatus.Cancelled]: [],
};

export function isValidTransition(from: MessageStatus, to: MessageStatus): boolean {
  return statusTransitions[from]?.includes(to) ?? false;
}

export const terminalStatuses = new Set<MessageStatus>([
  MessageStatus.Delivered,
  MessageStatus.Bounced,
  MessageStatus.Failed,
  MessageStatus.Cancelled,
]);

export const retryableStatuses = new Set<MessageStatus>([
  MessageStatus.Queued,
  MessageStatus.RetryPending,
]);
