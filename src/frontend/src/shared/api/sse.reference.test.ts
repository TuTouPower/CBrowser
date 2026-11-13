/** t056 A31 / AC-012: the SSE client delivers groups_changed /
 * proxies_changed frames to a dedicated listener; runtime_state frames
 * keep going to the runtime listener. */

import { describe, it, expect, beforeAll, afterAll, vi } from "vitest";
import http from "node:http";
import type { AddressInfo } from "node:net";
import {
  ProfileEventsClient,
  type ReferenceChangedEvent,
} from "./sse";

describe("ProfileEventsClient reference-data events", () => {
  let server: http.Server;
  let serverUrl: string;
  let currentRes: http.ServerResponse | null = null;

  beforeAll(async () => {
    server = http.createServer((_req, res) => {
      currentRes = res;
      res.writeHead(200, {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        Connection: "keep-alive",
      });
      res.write(
        `event: groups_changed\ndata: ${JSON.stringify({
          event: "groups_changed",
          entity_id: "g1",
        })}\n\n`,
      );
      res.write(
        `event: proxies_changed\ndata: ${JSON.stringify({
          event: "proxies_changed",
          entity_id: null,
        })}\n\n`,
      );
      res.write(
        `data: ${JSON.stringify({
          profile_id: "p1",
          display_number: 1,
          desired_state: "running",
          observed_state: "running",
          failure_count: 0,
          restart_blocked: false,
          updated_at: "2026-01-01T00:00:00Z",
        })}\n\n`,
      );
    });

    await new Promise<void>((resolve) => {
      server.listen(0, "127.0.0.1", () => resolve());
    });

    const addr = server.address() as AddressInfo;
    serverUrl = `http://127.0.0.1:${addr.port}/api/v1/events`;
    const realFetch = globalThis.fetch;
    vi.stubGlobal("fetch", (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input), serverUrl);
      return realFetch(
        `http://127.0.0.1:${addr.port}${url.pathname}${url.search}`,
        init,
      );
    });
  });

  afterAll(async () => {
    vi.unstubAllGlobals();
    if (currentRes && !currentRes.destroyed) {
      currentRes.destroy();
    }
    await new Promise<void>((resolve) => {
      server.close(() => resolve());
    });
  });

  it("delivers reference events to onReferenceEvent and runtime state to onEvent", async () => {
    const receivedReference: ReferenceChangedEvent[] = [];
    const receivedRuntime: unknown[] = [];
    const client = new ProfileEventsClient();
    client.onReferenceEvent((event) => {
      receivedReference.push(event);
    });
    client.onEvent((event) => {
      receivedRuntime.push(event);
    });
    client.start();
    try {
      await vi.waitFor(() => {
        expect(receivedReference).toHaveLength(2);
        expect(receivedRuntime).toHaveLength(1);
      });
    } finally {
      client.stop();
    }
    expect(receivedReference[0]).toEqual({
      event: "groups_changed",
      entity_id: "g1",
    });
    expect(receivedReference[1]).toEqual({
      event: "proxies_changed",
      entity_id: null,
    });
  });
});
