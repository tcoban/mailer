import assert from "node:assert/strict";
import test from "node:test";

import {
  MessageStatus,
  isValidTransition,
  retryableStatuses,
  statusTransitions,
  terminalStatuses,
} from "../src/status.js";

test("statusTransitions covers every status", () => {
  const statuses = Object.values(MessageStatus);
  assert.deepEqual(Object.keys(statusTransitions).sort(), statuses.slice().sort());
});

test("isValidTransition returns true for allowed transitions", () => {
  assert.equal(isValidTransition(MessageStatus.Queued, MessageStatus.Sent), true);
  assert.equal(isValidTransition(MessageStatus.RetryPending, MessageStatus.Failed), true);
  assert.equal(isValidTransition(MessageStatus.Sent, MessageStatus.Delivered), true);
});

test("isValidTransition returns false for invalid transitions", () => {
  assert.equal(isValidTransition(MessageStatus.Delivered, MessageStatus.Sent), false);
  assert.equal(isValidTransition(MessageStatus.Cancelled, MessageStatus.RetryPending), false);
});

test("terminalStatuses contain only terminal states", () => {
  for (const status of terminalStatuses) {
    assert.equal(statusTransitions[status]?.length ?? 0, 0);
  }
});

test("retryableStatuses include queued and retry pending only", () => {
  assert.deepEqual(new Set(retryableStatuses), new Set([MessageStatus.Queued, MessageStatus.RetryPending]));
});
