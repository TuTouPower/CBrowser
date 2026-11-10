import { afterEach, describe, expect, it, vi } from "vitest";
import {
  ProfileEventsClient,
  parseProfileRuntimeEvent,
  type ProfileRuntimeEvent,
} from "./sse";

const VALID_EVENT = {
  profile_id: "p1",
  display_number: 1,
  desired_state: "running",
  observed_state: "running",
  failure_count: 0,
  restart_blocked: false,
  updated_at: "2026-11-04T00:00:00Z",
};

interface FakeStream {
  response: Response;
  push: (chunk: string) => void;
  close: () => void;
  error: (err: unknown) => void;
}

function makeStream(): FakeStream {
  let controller!: ReadableStreamDefaultController<Uint8Array>;
  const stream = new ReadableStream<Uint8Array>({
    start(c) {
      controller = c;
    },
  });
  const encoder = new TextEncoder();
  return {
    response: new Response(stream, {
      status: 200,
      headers: { "Content-Type": "text/event-stream" },
    }),
    push: (chunk) => controller.enqueue(encoder.encode(chunk)),
    close: () => controller.close(),
    error: (err) => controller.error(err),
  };
}

function eventChunk(id: string, data: unknown): string {
  return `id: ${id}\ndata: ${JSON.stringify(data)}\n\n`;
}

async function settle(ms = 30): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

describe("ProfileEventsClient connection generations", () => {
  const fetchSpies: ReturnType<typeof vi.spyOn>[] = [];
  afterEach(() => {
    for (const spy of fetchSpies.splice(0)) spy.mockRestore();
  });

  function stubFetch(streams: FakeStream[]) {
    let calls = 0;
    const spy = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(async () => {
        const stream = streams[Math.min(calls, streams.length - 1)]!;
        calls += 1;
        return stream.response;
      });
    fetchSpies.push(spy);
    return { spy, calls: () => calls };
  }

  it("repeated start does not open another connection", async () => {
    const a = makeStream();
    const { calls } = stubFetch([a]);
    const client = new ProfileEventsClient({ reconnectIntervalMs: 20 });
    client.start();
    client.start();
    client.start();
    await settle();
    expect(calls()).toBe(1);
    client.stop();
  });

  it("only the current generation delivers events after an immediate stop/start", async () => {
    const a = makeStream();
    const b = makeStream();
    const { calls } = stubFetch([a, b]);
    const client = new ProfileEventsClient({ reconnectIntervalMs: 20 });
    const received: ProfileRuntimeEvent[] = [];
    client.onEvent((event) => received.push(event));

    client.start();
    await settle();
    client.stop();
    client.start();
    await settle();
    expect(calls()).toBe(2);

    a.push(eventChunk("a-1", { ...VALID_EVENT, profile_id: "stale" }));
    await settle();
    expect(received).toHaveLength(0);

    b.push(eventChunk("b-1", VALID_EVENT));
    await settle();
    expect(received).toHaveLength(1);
    expect(received[0]?.profile_id).toBe("p1");
    client.stop();
  });

  it("a superseded generation neither reports errors nor reconnects", async () => {
    const a = makeStream();
    const b = makeStream();
    const c = makeStream();
    const d = makeStream();
    const { calls } = stubFetch([a, b, c, d]);
    const client = new ProfileEventsClient({
      reconnectIntervalMs: 20,
      maxReconnectIntervalMs: 20,
    });
    const errors: unknown[] = [];
    client.onError((err) => errors.push(err));

    client.start();
    await settle();
    client.stop();
    client.start();
    await settle();
    expect(calls()).toBe(2);

    a.error(new Error("stale socket failure"));
    // Event-based barrier instead of a fixed sleep: drive the current
    // generation through two full reconnect cycles. Each completed cycle
    // proves at least one reconnect interval elapsed with the machinery
    // running, so a stale-generation reconnect (same interval, armed
    // earlier) would already have consumed an extra fetch call.
    b.close();
    await vi.waitFor(() => expect(calls()).toBe(3));
    c.close();
    await vi.waitFor(() => expect(calls()).toBe(4));
    expect(errors).toHaveLength(0);
    expect(calls()).toBe(4);
    client.stop();
  });

  it("after stop (logout), a failing stream triggers no reconnect and no error", async () => {
    const a = makeStream();
    const b = makeStream();
    const c = makeStream();
    const d = makeStream();
    const { calls } = stubFetch([a, b, c, d]);
    const client = new ProfileEventsClient({
      reconnectIntervalMs: 20,
      maxReconnectIntervalMs: 20,
    });
    const errors: unknown[] = [];
    client.onError((err) => errors.push(err));

    client.start();
    await settle();
    client.stop();
    a.error(new Error("socket failure after logout"));
    // Event-based barrier instead of a fixed sleep: restart the client
    // and drive the new generation through two full reconnect cycles.
    // The stopped generation's reconnect timer (same interval) was armed
    // at the error above, so by the time two later cycles have completed
    // it would already have consumed an extra fetch call if stop() had
    // failed to suppress it.
    client.start();
    await vi.waitFor(() => expect(calls()).toBe(2));
    b.error(new Error("current generation failure 1"));
    await vi.waitFor(() => expect(calls()).toBe(3));
    c.error(new Error("current generation failure 2"));
    await vi.waitFor(() => expect(calls()).toBe(4));
    expect(calls()).toBe(4);
    // Only the two current-generation failures may be reported; the
    // post-stop failure must not appear.
    expect(errors).toHaveLength(2);
    client.stop();
  });

  it("the current generation still reconnects when its stream ends", async () => {
    const a = makeStream();
    const b = makeStream();
    const { calls } = stubFetch([a, b]);
    const client = new ProfileEventsClient({
      reconnectIntervalMs: 20,
      maxReconnectIntervalMs: 20,
    });
    const received: ProfileRuntimeEvent[] = [];
    client.onEvent((event) => received.push(event));

    client.start();
    await settle();
    a.push(eventChunk("a-1", VALID_EVENT));
    a.close();
    await settle(90);
    expect(calls()).toBe(2);
    expect(received).toHaveLength(1);

    b.push(eventChunk("b-1", { ...VALID_EVENT, observed_state: "starting" }));
    await settle();
    expect(received).toHaveLength(2);
    client.stop();
  });

  it("malformed payloads go to error listeners and are never delivered as state", async () => {
    const a = makeStream();
    stubFetch([a]);
    const client = new ProfileEventsClient({ reconnectIntervalMs: 20 });
    const received: ProfileRuntimeEvent[] = [];
    const errors: unknown[] = [];
    client.onEvent((event) => received.push(event));
    client.onError((err) => errors.push(err));

    client.start();
    await settle();
    a.push(eventChunk("bad-1", { ...VALID_EVENT, observed_state: "levitating" }));
    a.push(eventChunk("bad-2", { desired_state: "running", observed_state: "running" }));
    a.push(eventChunk("bad-3", "not an object"));
    a.push("id: bad-4\ndata: {not json\n\n");
    await settle();
    expect(received).toHaveLength(0);
    expect(errors).toHaveLength(4);

    a.push(eventChunk("good-1", VALID_EVENT));
    await settle();
    expect(received).toHaveLength(1);
    client.stop();
  });
});

describe("parseProfileRuntimeEvent", () => {
  it("accepts a full legal event and search_defaults payloads", () => {
    expect(parseProfileRuntimeEvent(VALID_EVENT)).toEqual(VALID_EVENT);
    const withDefaults = {
      ...VALID_EVENT,
      search_defaults: {
        state: "failed",
        error_kind: "timeout",
        runtime_instance_id: "inst-1",
        request_id: null,
        updated_at: "2026-11-04T00:01:00Z",
      },
    };
    expect(parseProfileRuntimeEvent(withDefaults)).toEqual(withDefaults);
    expect(
      parseProfileRuntimeEvent({ ...VALID_EVENT, search_defaults: null }),
    ).not.toBeNull();
  });

  it("rejects unknown states and wrongly typed fields", () => {
    expect(
      parseProfileRuntimeEvent({ ...VALID_EVENT, desired_state: "paused" }),
    ).toBeNull();
    expect(
      parseProfileRuntimeEvent({ ...VALID_EVENT, failure_count: "3" }),
    ).toBeNull();
    expect(
      parseProfileRuntimeEvent({ ...VALID_EVENT, profile_id: "" }),
    ).toBeNull();
    expect(
      parseProfileRuntimeEvent({
        ...VALID_EVENT,
        search_defaults: { state: "unknown", runtime_instance_id: "i", updated_at: "t" },
      }),
    ).toBeNull();
    expect(parseProfileRuntimeEvent(null)).toBeNull();
    expect(parseProfileRuntimeEvent([VALID_EVENT])).toBeNull();
  });

  it("rejects events missing any field the generated type requires (A21)", () => {
    // A partial event must never be coerced into a legal runtime state by
    // merging with previously cached values.
    for (const field of [
      "profile_id",
      "desired_state",
      "observed_state",
      "failure_count",
      "restart_blocked",
      "updated_at",
    ] as const) {
      const partial: Record<string, unknown> = { ...VALID_EVENT };
      delete partial[field];
      expect(parseProfileRuntimeEvent(partial)).toBeNull();
    }
  });
});
