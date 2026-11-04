import { afterEach, describe, expect, it, vi } from "vitest";
import http from "node:http";
import type { AddressInfo } from "node:net";
import { ProfileEventsClient } from "./sse";

async function startServer(handler: http.RequestListener) {
  const server = http.createServer(handler);
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const { port } = server.address() as AddressInfo;
  // Same-origin fixture (t025): ProfileEventsClient no longer accepts a
  // url, so forward fetch to the test server by rewriting only the
  // origin of the client's same-origin resolved URL.
  const realFetch = globalThis.fetch;
  vi.stubGlobal("fetch", (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), `http://127.0.0.1:${port}`);
    return realFetch(`http://127.0.0.1:${port}${url.pathname}${url.search}`, init);
  });
  return { server, url: `http://127.0.0.1:${port}/api/v1/events` };
}

describe("ProfileEventsClient hardening", () => {
  const servers: http.Server[] = [];
  afterEach(() => {
    vi.unstubAllGlobals();
    for (const server of servers.splice(0)) server.close();
  });

  it("stops reconnecting and reports unauthorized on 401", async () => {
    let connections = 0;
    const { server } = await startServer((_req, res) => {
      connections += 1;
      res.writeHead(401, { "Content-Type": "application/json" });
      res.end("{}");
    });
    servers.push(server);
    let unauthorized = 0;
    const client = new ProfileEventsClient({
      reconnectIntervalMs: 10,
      onUnauthorized: () => {
        unauthorized += 1;
      },
    });
    client.start();
    // Poll for the unauthorized callback instead of a fixed sleep
    // (load-sensitive; same fix class as t025_test_f002), then keep a
    // short negative window: with a 10ms reconnect interval, an
    // erroneous reconnect after 401 would show up well within it.
    await vi.waitFor(() => expect(unauthorized).toBe(1));
    await new Promise((resolve) => setTimeout(resolve, 50));
    client.stop();
    expect(unauthorized).toBe(1);
    expect(connections).toBe(1);
  });

  it("flushes a final event written without a trailing blank line", async () => {
    const { server } = await startServer((_req, res) => {
      res.writeHead(200, { "Content-Type": "text/event-stream" });
      res.end(
        `id: tail-1\ndata: ${JSON.stringify({
          profile_id: "p1",
          desired_state: "running",
          observed_state: "running",
          failure_count: 0,
          restart_blocked: false,
          updated_at: "2026-01-01T00:00:00Z",
        })}`,
      );
    });
    servers.push(server);
    const events: string[] = [];
    const client = new ProfileEventsClient({ reconnectIntervalMs: 10 });
    client.onEvent((event) => {
      events.push(event.profile_id);
      client.stop();
    });
    client.start();
    // Poll instead of a fixed sleep: delivery timing depends on machine
    // load, the assertion itself is unchanged (t025 review t025_test_f002).
    await vi.waitFor(() => expect(events).toEqual(["p1"]));
  });
});
