import { afterEach, describe, expect, it } from "vitest";
import http from "node:http";
import type { AddressInfo } from "node:net";
import { ProfileEventsClient } from "./sse";

async function startServer(handler: http.RequestListener) {
  const server = http.createServer(handler);
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const { port } = server.address() as AddressInfo;
  return { server, url: `http://127.0.0.1:${port}/api/v1/events` };
}

describe("ProfileEventsClient hardening", () => {
  const servers: http.Server[] = [];
  afterEach(() => {
    for (const server of servers.splice(0)) server.close();
  });

  it("stops reconnecting and reports unauthorized on 401", async () => {
    let connections = 0;
    const { server, url } = await startServer((_req, res) => {
      connections += 1;
      res.writeHead(401, { "Content-Type": "application/json" });
      res.end("{}");
    });
    servers.push(server);
    let unauthorized = 0;
    const client = new ProfileEventsClient({
      url,
      reconnectIntervalMs: 10,
      onUnauthorized: () => {
        unauthorized += 1;
      },
    });
    client.start();
    await new Promise((resolve) => setTimeout(resolve, 100));
    client.stop();
    expect(unauthorized).toBe(1);
    expect(connections).toBe(1);
  });

  it("flushes a final event written without a trailing blank line", async () => {
    const { server, url } = await startServer((_req, res) => {
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
    const client = new ProfileEventsClient({ url, reconnectIntervalMs: 10 });
    client.onEvent((event) => {
      events.push(event.profile_id);
      client.stop();
    });
    client.start();
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(events).toEqual(["p1"]);
  });
});
