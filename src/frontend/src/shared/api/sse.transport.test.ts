import { describe, it, expect } from "vitest";
import { parseProfileRuntimeEvent } from "./sse";

// t026 AC-010: runtime_state events carry the layered transport
// observation; structurally invalid transport payloads are rejected
// like any other malformed event instead of being coerced into state.

const baseEvent = {
  profile_id: "p1",
  display_number: 1,
  desired_state: "running",
  observed_state: "running",
  runtime_instance_id: "inst_1",
  failure_count: 0,
  restart_blocked: false,
  updated_at: "2026-11-04T00:00:00+00:00",
};

const validTransport = {
  profile_id: "p1",
  runtime_instance_id: "inst_1",
  browser_state: "running",
  stream_state: "running",
  transport_state: "recovering",
  gateway_endpoint: "10.251.7.254",
  last_error: "gateway_missing",
  rejection_code: null,
};

describe("parseProfileRuntimeEvent transport (t026)", () => {
  it("accepts an event with a valid transport observation", () => {
    const event = parseProfileRuntimeEvent({
      ...baseEvent,
      transport: validTransport,
    });
    expect(event).not.toBeNull();
    expect(event?.transport?.transport_state).toBe("recovering");
  });

  it("accepts an event with transport null or absent", () => {
    expect(
      parseProfileRuntimeEvent({ ...baseEvent, transport: null }),
    ).not.toBeNull();
    expect(parseProfileRuntimeEvent({ ...baseEvent })).not.toBeNull();
  });

  it("rejects an event with an unknown transport_state", () => {
    expect(
      parseProfileRuntimeEvent({
        ...baseEvent,
        transport: { ...validTransport, transport_state: "half_open" },
      }),
    ).toBeNull();
  });

  it("rejects an event with an unknown layer state", () => {
    expect(
      parseProfileRuntimeEvent({
        ...baseEvent,
        transport: { ...validTransport, browser_state: "paused" },
      }),
    ).toBeNull();
  });
});
