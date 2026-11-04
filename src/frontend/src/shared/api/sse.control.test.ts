import { describe, it, expect } from "vitest";
import { parseProfileRuntimeEvent } from "./sse";

// t031 AC-007: runtime_state events carry the human-priority control
// state; structurally invalid control payloads are rejected like any
// other malformed event instead of being coerced into state.

const baseEvent = {
  profile_id: "p1",
  desired_state: "running",
  observed_state: "running",
  runtime_instance_id: "inst_1",
  failure_count: 0,
  restart_blocked: false,
  updated_at: "2026-11-04T00:00:00+00:00",
};

const validControl = {
  profile_id: "p1",
  owner: "agent",
  generation: 3,
  agent_instance_id: "tok_1",
  agent_session_id: "exec-1",
  handoff_reason: null,
  handoff_detail: null,
  agent_reclaim_allowed: true,
  pending_supervisor_close: false,
  updated_at: "2026-11-04T00:00:00+00:00",
};

describe("parseProfileRuntimeEvent control (t031)", () => {
  it("accepts an event with a valid control state", () => {
    const event = parseProfileRuntimeEvent({
      ...baseEvent,
      control: validControl,
    });
    expect(event).not.toBeNull();
    expect(event?.control?.owner).toBe("agent");
    expect(event?.control?.generation).toBe(3);
  });

  it("accepts an event with control null or absent", () => {
    expect(
      parseProfileRuntimeEvent({ ...baseEvent, control: null }),
    ).not.toBeNull();
    expect(parseProfileRuntimeEvent({ ...baseEvent })).not.toBeNull();
  });

  it("rejects an event with an unknown control owner", () => {
    expect(
      parseProfileRuntimeEvent({
        ...baseEvent,
        control: { ...validControl, owner: "shared" },
      }),
    ).toBeNull();
  });

  it("rejects an event with a non-numeric generation", () => {
    expect(
      parseProfileRuntimeEvent({
        ...baseEvent,
        control: { ...validControl, generation: "3" },
      }),
    ).toBeNull();
  });

  it("rejects an event with a non-boolean reclaim flag", () => {
    expect(
      parseProfileRuntimeEvent({
        ...baseEvent,
        control: { ...validControl, agent_reclaim_allowed: "yes" },
      }),
    ).toBeNull();
  });
});
