import { describe, it, expect, beforeAll, afterEach, vi } from "vitest";
import http from "node:http";
import type { AddressInfo } from "node:net";
import {
  ProfileEventsClient,
  parseProfilePreviewEvent,
  type ProfilePreviewEvent,
  type ProfileRuntimeEvent,
} from "./sse";

const runtimePayload = {
  profile_id: "p1",
  desired_state: "running",
  observed_state: "running",
  failure_count: 0,
  restart_blocked: false,
  updated_at: "2026-01-01T00:00:00Z",
};

const previewPayload = {
  event: "profile_preview",
  profile_id: "p1",
  captured_at: "2026-01-01T00:00:05Z",
};

const previewPayload2 = {
  event: "profile_preview",
  profile_id: "p2",
  captured_at: "2026-01-01T00:00:09Z",
};

let REAL_FETCH: typeof globalThis.fetch;
let server: http.Server | null = null;

beforeAll(() => {
  REAL_FETCH = globalThis.fetch;
});

afterEach(async () => {
  vi.unstubAllGlobals();
  if (server) {
    const srv = server;
    server = null;
    srv.closeAllConnections();
    await new Promise<void>((resolve) => {
      srv.close(() => resolve());
    });
  }
});

function stubFetch(port: number): void {
  vi.stubGlobal(
    "fetch",
    (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input), `http://127.0.0.1:${port}`);
      return REAL_FETCH(
        `http://127.0.0.1:${port}${url.pathname}${url.search}`,
        init,
      );
    },
  );
}

async function startServer(body: string): Promise<void> {
  let connection = 0;
  const srv = http.createServer((_req, res) => {
    connection += 1;
    res.writeHead(200, {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
    });
    if (connection === 1) {
      res.end(body);
    } else {
      res.end();
    }
  });
  server = srv;
  await new Promise<void>((resolve) => {
    srv.listen(0, "127.0.0.1", () => resolve());
  });
  const addr = srv.address() as AddressInfo;
  stubFetch(addr.port);
}

function frame(lines: string[]): string {
  return `${lines.join("\n")}\n\n`;
}

function waitUntil(predicate: () => boolean, timeoutMs: number): Promise<void> {
  return new Promise((resolve) => {
    const start = Date.now();
    const check = setInterval(() => {
      if (predicate() || Date.now() - start > timeoutMs) {
        clearInterval(check);
        resolve();
      }
    }, 20);
  });
}

async function collect(expectedTotal: number): Promise<{
  runtime: ProfileRuntimeEvent[];
  preview: ProfilePreviewEvent[];
  errors: unknown[];
}> {
  const runtime: ProfileRuntimeEvent[] = [];
  const preview: ProfilePreviewEvent[] = [];
  const errors: unknown[] = [];
  const client = new ProfileEventsClient({
    reconnectIntervalMs: 10000,
    maxReconnectIntervalMs: 10000,
  });
  client.onEvent((event) => runtime.push(event));
  client.onPreviewEvent((event) => preview.push(event));
  client.onError((error) => errors.push(error));
  client.start();
  try {
    await waitUntil(
      () => runtime.length + preview.length >= expectedTotal,
      2000,
    );
  } finally {
    client.close();
  }
  return { runtime, preview, errors };
}

describe("ProfileEventsClient event-typed frames", () => {
  it("dispatches event-typed frames to their channels (default/runtime_state -> runtime, profile_preview -> preview)", async () => {
    const body =
      frame([`data: ${JSON.stringify(runtimePayload)}`]) +
      frame([
        "event: runtime_state",
        `data: ${JSON.stringify(runtimePayload)}`,
      ]) +
      frame([
        "event: profile_preview",
        `data: ${JSON.stringify(previewPayload)}`,
      ]) +
      frame([
        "event: profile_preview",
        `data: ${JSON.stringify(previewPayload2)}`,
      ]);
    await startServer(body);
    const { runtime, preview, errors } = await collect(4);

    expect(errors).toEqual([]);
    expect(runtime).toHaveLength(2);
    expect(runtime[0]).toMatchObject({
      profile_id: "p1",
      observed_state: "running",
    });
    expect(preview).toHaveLength(2);
    expect(preview[0]).toEqual(previewPayload);
    expect(preview[1]).toEqual(previewPayload2);
  });

  it("flushes a trailing frame with no blank line when the stream ends", async () => {
    const body =
      frame([`data: ${JSON.stringify(runtimePayload)}`]) +
      `event: profile_preview\ndata: ${JSON.stringify(previewPayload)}`;
    await startServer(body);
    const { runtime, preview, errors } = await collect(2);

    expect(errors).toEqual([]);
    expect(runtime).toHaveLength(1);
    expect(preview).toHaveLength(1);
    expect(preview[0]).toEqual(previewPayload);
  });

  it("ignores unknown event names without throwing and keeps parsing later frames", async () => {
    const body =
      frame([
        "event: future_event",
        `data: ${JSON.stringify(previewPayload)}`,
      ]) +
      frame([
        "event: profile_preview",
        `data: ${JSON.stringify(previewPayload)}`,
      ]);
    await startServer(body);
    const { runtime, preview, errors } = await collect(1);

    expect(errors).toEqual([]);
    expect(runtime).toHaveLength(0);
    expect(preview).toHaveLength(1);
    expect(preview[0]).toEqual(previewPayload);
  });
});

describe("parseProfilePreviewEvent", () => {
  it("accepts a well-formed preview event", () => {
    expect(parseProfilePreviewEvent(previewPayload)).toEqual(previewPayload);
  });

  it("rejects malformed preview payloads", () => {
    expect(parseProfilePreviewEvent(null)).toBeNull();
    expect(parseProfilePreviewEvent("text")).toBeNull();
    expect(
      parseProfilePreviewEvent({ ...previewPayload, event: "other" }),
    ).toBeNull();
    expect(
      parseProfilePreviewEvent({ ...previewPayload, profile_id: "" }),
    ).toBeNull();
    expect(
      parseProfilePreviewEvent({ ...previewPayload, captured_at: undefined }),
    ).toBeNull();
  });
});
