import { describe, it, expect, beforeAll, afterAll } from "vitest";
import http from "node:http";
import type { AddressInfo } from "node:net";
import { ProfileEventsClient, type ProfileRuntimeEvent } from "./sse";

describe("ProfileEventsClient SSE", () => {
  let server: http.Server;
  let serverUrl: string;
  let connectionCount = 0;
  const receivedHeaders: http.IncomingHttpHeaders[] = [];
  let currentRes: http.ServerResponse | null = null;

  beforeAll(async () => {
    server = http.createServer((req, res) => {
      connectionCount++;
      receivedHeaders.push(req.headers);
      currentRes = res;

      res.writeHead(200, {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        Connection: "keep-alive",
      });

      if (connectionCount === 1) {
        // Send first event and then abruptly close
        res.write(`id: evt-001\ndata: ${JSON.stringify({
          profile_id: "p1",
          desired_state: "running",
          observed_state: "starting",
        })}\n\n`);
        setTimeout(() => {
          res.destroy();
        }, 50);
      } else if (connectionCount === 2) {
        // Second connection, send second event
        res.write(`id: evt-002\ndata: ${JSON.stringify({
          profile_id: "p1",
          desired_state: "running",
          observed_state: "running",
        })}\n\n`);
      }
    });

    await new Promise<void>((resolve) => {
      server.listen(0, "127.0.0.1", () => resolve());
    });

    const addr = server.address() as AddressInfo;
    serverUrl = `http://127.0.0.1:${addr.port}/api/v1/events`;
  });

  afterAll(async () => {
    if (currentRes && !currentRes.destroyed) {
      currentRes.destroy();
    }
    await new Promise<void>((resolve) => {
      server.close(() => resolve());
    });
  });

  it("receives SSE events, recovers on disconnect, and passes Last-Event-ID header on reconnect", async () => {
    const receivedEvents: ProfileRuntimeEvent[] = [];
    const client = new ProfileEventsClient({
      url: serverUrl,
      reconnectIntervalMs: 50,
      maxReconnectIntervalMs: 100,
    });

    client.onEvent((event) => {
      receivedEvents.push(event);
    });

    client.start();

    // Wait for the client to receive the first event and reconnect for the second event
    await new Promise<void>((resolve, reject) => {
      const start = Date.now();
      const check = setInterval(() => {
        if (receivedEvents.length >= 2) {
          clearInterval(check);
          resolve();
        } else if (Date.now() - start > 4000) {
          clearInterval(check);
          reject(new Error(`Timeout waiting for 2 events, got: ${JSON.stringify(receivedEvents)}`));
        }
      }, 30);
    });

    client.close();

    expect(receivedEvents).toHaveLength(2);
    expect(receivedEvents[0]).toMatchObject({
      profile_id: "p1",
      desired_state: "running",
      observed_state: "starting",
    });
    expect(receivedEvents[1]).toMatchObject({
      profile_id: "p1",
      desired_state: "running",
      observed_state: "running",
    });

    // Check headers on second connection
    expect(receivedHeaders.length).toBeGreaterThanOrEqual(2);
    const reconnectHeaders = receivedHeaders[1];
    expect(reconnectHeaders["last-event-id"]).toBe("evt-001");
  });
});
