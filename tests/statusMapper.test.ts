import assert from "node:assert/strict";
import test from "node:test";

import { mapProviderError, mapProviderStatus } from "../worker/statusMapper.js";
import { MessageStatus } from "../src/status.js";

test("mapProviderStatus accepts valid transitions", () => {
  assert.equal(
    mapProviderStatus("sent", MessageStatus.Queued),
    MessageStatus.Sent,
  );
  assert.equal(
    mapProviderStatus("delivered", MessageStatus.Sent),
    MessageStatus.Delivered,
  );
});

test("mapProviderStatus rejects invalid transitions", () => {
  assert.throws(
    () => mapProviderStatus("delivered", MessageStatus.Queued),
    /Invalid status transition/,
  );
});

test("mapProviderError maps retryable provider failures", () => {
  assert.deepEqual(mapProviderError("temporary_failure"), {
    status: MessageStatus.RetryPending,
    reason: "TEMPORARY_PROVIDER_FAILURE",
  });
  assert.deepEqual(mapProviderError("temporary_failure", "PROVIDER_TEMP"), {
    status: MessageStatus.RetryPending,
    reason: "PROVIDER_TEMP",
  });
});

test("mapProviderError maps permanent failures", () => {
  assert.deepEqual(mapProviderError("permanent_failure"), {
    status: MessageStatus.Failed,
    reason: "PERMANENT_PROVIDER_FAILURE",
  });
  assert.deepEqual(mapProviderError("permanent_failure", "PROVIDER_PERM"), {
    status: MessageStatus.Failed,
    reason: "PROVIDER_PERM",
  });
});

test("mapProviderError uses provider update for non-failures", () => {
  assert.deepEqual(mapProviderError("delivered"), {
    status: MessageStatus.Delivered,
    reason: "PROVIDER_UPDATE",
  });
  assert.deepEqual(mapProviderError("delivered", "OK"), {
    status: MessageStatus.Delivered,
    reason: "OK",
  });
});
