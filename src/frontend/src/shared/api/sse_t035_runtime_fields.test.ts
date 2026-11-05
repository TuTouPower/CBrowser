import { describe, expect, it } from "vitest";

import { parseProfileRuntimeEvent } from "./sse";

const baseEvent = {
  profile_id: "p1",
  desired_state: "running",
  observed_state: "running",
  failure_count: 0,
  restart_blocked: false,
  updated_at: "2026-11-05T00:00:00+00:00",
};

describe("parseProfileRuntimeEvent t035 runtime fields", () => {
  it("accepts valid ISO-8601 timestamps and browser version fields", () => {
    expect(
      parseProfileRuntimeEvent({
        ...baseEvent,
        last_started_at: "2026-11-05T01:02:03+08:00",
        last_stopped_at: "2026-11-05T02:03:04.123Z",
        browser_product: "Chrome/146.0.0.0",
        browser_user_agent: "Mozilla/5.0",
      }),
    ).not.toBeNull();
  });

  it("accepts null and absent runtime fields", () => {
    expect(
      parseProfileRuntimeEvent({
        ...baseEvent,
        last_started_at: null,
        last_stopped_at: null,
        browser_product: null,
        browser_user_agent: null,
      }),
    ).not.toBeNull();
    expect(parseProfileRuntimeEvent({ ...baseEvent })).not.toBeNull();
  });

  it("rejects a non-ISO last_started_at", () => {
    expect(
      parseProfileRuntimeEvent({
        ...baseEvent,
        last_started_at: "not-a-timestamp",
      }),
    ).toBeNull();
  });

  it("rejects a timestamp without a timezone", () => {
    expect(
      parseProfileRuntimeEvent({
        ...baseEvent,
        last_stopped_at: "2026-11-05T01:02:03",
      }),
    ).toBeNull();
  });

  it("rejects a non-string browser field", () => {
    expect(
      parseProfileRuntimeEvent({ ...baseEvent, browser_product: 146 }),
    ).toBeNull();
    expect(
      parseProfileRuntimeEvent({ ...baseEvent, browser_user_agent: {} }),
    ).toBeNull();
  });
});
